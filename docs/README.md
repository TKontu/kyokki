# Kyokki

Self-hosted kitchen inventory system. Scan receipts, track what's in your fridge, reduce food waste.

## Why This Works

Most food inventory apps fail because managing the system is more work than the benefit. Kyokki solves this:

- **Receipt scanning** — Add 10+ items in one photo
- **Smart defaults** — Expiry estimated by category (meat: 5 days, cheese: 25 days)
- **Approximate tracking** — [1/4] [1/2] [3/4] [Done] buttons, not gram-counting
- **Context-aware** — Shows breakfast items in the morning
- **Local-first** — Runs on your homelab, no cloud

## Features

### Phase 1 (MVP)
- 📷 Receipt scanning with MinerU OCR
- 📦 Inventory tracking with approximate quantities
- ⏰ Category-based expiry estimation
- 🎯 One-tap consumption logging
- 📱 iPad PWA, always-on display

### Phase 2
- 🔍 Hardware barcode scanner support
- 🌐 Open Food Facts integration
- 📊 GS1 DataMatrix scanning (real expiry dates!)
- 🛒 Shopping list with urgent flags
- 📥 Multi-receipt batch processing

### Phase 3
- 📉 Minimum stock alerts & auto-shopping
- 📈 Consumption analytics
- 👨‍👩‍👧 Multi-user support

### Phase 4
- 🍳 Recipe integration
- 📅 Meal planning

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Homelab server (16GB+ RAM)
- MinerU OCR running on homelab
- OpenAI-compatible LLM endpoint (vLLM or Ollama) on the homelab
- iPad for primary interface

### Installation

Full runbook: [DEPLOY.md](./DEPLOY.md). In short:

```bash
git clone https://github.com/TKontu/kyokki.git
cd kyokki
cp stack.env.example stack.env
# Edit stack.env: POSTGRES_PASSWORD, MINERU_BASE_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm kyokki-api alembic upgrade head
docker compose -f docker-compose.prod.yml run --rm kyokki-api python -m app.db.seed_categories
```

Open `http://<host>:17301` on the iPad and add it to the Home Screen.

## Usage

### Scan Receipt
1. Tap 📷 Scan
2. Photograph receipt
3. Review extracted items (correct if needed)
4. Confirm to add to inventory

### Log Consumption
- Tap item in inventory
- Select [1/4] [1/2] [3/4] or [Done]
- Item updates instantly

### Handle Out-of-Sync
- Swipe item → "Mark as Gone"
- Use "Clear Expired" for batch cleanup
- "Quick Add" for items bought without receipt

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | required |
| `MINERU_BASE_URL` | MinerU OCR endpoint | required |
| `LLM_BASE_URL` | OpenAI-compatible chat endpoint (vLLM/Ollama) | required |
| `LLM_API_KEY` | Key for that endpoint (`ollama` if none) | required |
| `LLM_MODEL` | Model name for receipt extraction | see `stack.env.example` |

### Category Expiry Defaults
```python
meat: 5 days
milk: 5 days
dairy: 7 days
cheese: 25 days
produce: 5 days
frozen: 90 days
pantry: 365 days
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md)

```
iPad PWA → Traefik → FastAPI + Celery → PostgreSQL
                           ↓
              MinerU OCR / Open Food Facts / Ollama
```

## Development

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## License

MIT
