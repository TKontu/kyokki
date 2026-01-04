# Infrastructure & AI/ML — Development TODO

## Infrastructure

### Docker Compose

```yaml
services:
  traefik:
    image: traefik:v3.0
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik:/etc/traefik

  frontend:
    build: ./frontend
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.frontend.rule=Host(`fridge.local`)"

  api:
    build: ./backend
    labels:
      - "traefik.http.routers.api.rule=PathPrefix(`/api`)"
    depends_on: [postgres, redis]

  celery-worker:
    build: ./backend
    command: celery -A app.tasks worker -l info

  postgres:
    image: postgres:15-alpine
    volumes: [postgres_data:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
```

### Tasks
- [ ] Docker Compose (dev + prod overrides)
- [ ] Traefik SSL (self-signed or mkcert)
- [ ] Volume structure: `./data/images/receipts/`, `./data/backups/`
- [ ] Backup script (pg_dump, cron)
- [ ] Makefile (dev, prod, logs, shell, backup, migrate)

---

## OCR Pipeline

### File Type Routing
PDFs (S-Group digital receipts) don't need OCR — extract text directly.

```python
import pdfplumber

def extract_text(file_path: str) -> str:
    if file_path.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            return '\n'.join(page.extract_text() for page in pdf.pages)
    return mineru_ocr(file_path)  # Images need OCR
```

- [ ] PDF text extraction (pdfplumber)
- [ ] Image OCR (MinerU client)
- [ ] File type routing

### MinerU Integration
```python
class MinerUClient:
    def __init__(self, host: str):
        self.host = host
    
    async def extract_text(self, image_path: str) -> str:
        # POST image to MinerU, return extracted text
        pass
```

- [ ] MinerU client
- [ ] Error handling + retry

### Store Parsers

**Detection**
```python
STORE_DETECTORS = {
    'sgroup': ['S-KAUPAT', 'Prisma', 'S-market', 'HOK-ELANTO'],
    'kgroup': ['K-market', 'K-Citymarket', 'K-Supermarket'],
    'lidl': ['Lidl', 'lidl.fi'],
}
```

**S-Group** (from actual receipt PDF)
```
KEVYTMAITOJUOMA LAKTON 1,28          ← Product + price
0,386 KG 3,89 €/KG                   ← Weight (next line)
3 KPL 1,88 €/KPL                     ← Quantity (next line)
NORM. 5,64                           ← Skip
ALENNUS -1,14                        ← Skip
```

**K-Group** (from actual receipt photo)
```
Pilsner Urquell 4,4% 0,5l tlk    3,04
Tolkkipantti 0,15                0,15    ← Skip (deposit)
  1 KPL    0,15 €/KPL                    ← Quantity (indented)
```

**Lidl** (from actual e-kuitti)
```
Grillimaisteri bratwurst         3,29 B  ← Product + VAT code
Lidl Plus -säästösi             -0,37    ← Discount → associate
0,436 kg x 3,39 EUR/kg                   ← Weight (inline)
  2 x 2,89    EUR                        ← Quantity (next line)
```

**Skip Patterns**
```python
SKIP = [r'^YHTEENSÄ', r'[Tt]olkkipantti', r'^NORM\.', 
        r'^ALENNUS', r'PLUSSA-ETU', r'^ALV', r'Kortti:']
```

- [ ] Base parser
- [ ] S-Group parser
- [ ] K-Group parser  
- [ ] Lidl parser (handle discount association)
- [ ] Tests with actual receipts

---

## Product Matching

### Matching Strategy
```
Receipt Text → Exact Alias Match → Fuzzy Match → OFF Lookup → Ollama → Manual
```

### Fuzzy Matching
```python
from rapidfuzz import fuzz, process

def match(query: str, candidates: list[str], threshold=80):
    matches = process.extract(query, candidates, scorer=fuzz.token_sort_ratio)
    return [m for m in matches if m[1] >= threshold]
```

- [ ] RapidFuzz integration
- [ ] Normalization (lowercase, remove units like "kpl", "kg")
- [ ] Confidence scoring

---

## Open Food Facts Integration

```python
class OFFClient:
    BASE_URL = "https://world.openfoodfacts.org/api/v2/product"
    
    async def lookup(self, barcode: str) -> dict | None:
        resp = await self.client.get(f"{self.BASE_URL}/{barcode}")
        if resp.status_code == 200:
            return resp.json().get("product")
        return None
```

**Data to extract:**
- product_name (prefer user's language)
- brands
- categories → map to system categories
- image_url
- nutriscore_grade
- nutriments

- [ ] OFF client
- [ ] Response caching (store in product_master.off_data)
- [ ] Category mapping
- [ ] Graceful fallback on miss

---

## GS1 DataMatrix Parsing

```python
def parse_gs1(data: str) -> dict:
    """Parse GS1 element string."""
    result = {}
    # AI patterns: (01) GTIN, (17) expiry, (10) batch, (310x) weight
    # Example: ]d201034531200000211712310010ABC123
    # → GTIN: 03453120000021, Expiry: 2031-12-17, Batch: ABC123
    
    # Use FNC1 separator (ASCII 29) or fixed lengths
    pass
```

- [ ] GS1 AI parser
- [ ] Date parsing (YYMMDD → date, handle century)
- [ ] Weight parsing (variable decimal point)
- [ ] Integration with scanner input

---

## Ollama Fallback

```python
class OllamaClient:
    async def identify_product(self, text: str) -> dict:
        prompt = f"""
        Receipt line: {text}
        Identify: product name, category, typical shelf life days.
        JSON format.
        """
        resp = await self.client.post(f"{self.host}/api/generate", json={
            "model": self.model,
            "prompt": prompt,
            "stream": False
        })
        return parse_json(resp.json()["response"])
```

- [ ] Ollama client
- [ ] Product identification prompt
- [ ] Category inference
- [ ] Error handling (timeout, parse failure)

---

## Celery Tasks

```python
@celery_app.task
def process_receipt(receipt_id: str):
    receipt = get_receipt(receipt_id)
    
    # 1. OCR
    text = mineru.extract_text(receipt.image_path)
    
    # 2. Parse
    parser = detect_parser(text)
    items = parser.parse(text)
    
    # 3. Match
    matched = [match_product(item) for item in items]
    
    # 4. Save + notify
    save_results(receipt_id, matched)
    broadcast_complete(receipt_id)
```

- [ ] Receipt processing task
- [ ] Stock check task (after consumption)
- [ ] Scheduled expiry check (Celery beat, daily)

---

## Environment Variables

```env
# Infrastructure
POSTGRES_HOST=postgres
POSTGRES_PASSWORD=xxx
REDIS_HOST=redis

# OCR
MINERU_HOST=http://192.168.0.xxx:8000

# AI
OLLAMA_HOST=http://192.168.0.247:11434
OLLAMA_MODEL=qwen2-vl:7b

# Matching
FUZZY_THRESHOLD=80
OFF_CACHE_TTL_DAYS=30
```

---

## Testing

- [ ] OCR with sample receipt images
- [ ] Parser tests per store chain
- [ ] Matching tests (exact, fuzzy, miss)
- [ ] GS1 parsing tests
- [ ] Integration test: image → inventory
