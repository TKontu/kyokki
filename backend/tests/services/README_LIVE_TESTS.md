# Live Service Integration Tests

This directory contains integration tests that make **real API calls** to external services (vLLM and MinerU). These tests are **excluded from the default test run** to prevent failures when services are unavailable.

## Test Files

- `test_llm_extractor.py` - Unit tests with mocked vLLM responses (run by default)
- `test_ocr_service.py` - Unit tests with mocked MinerU responses (run by default)
- `test_live_services.py` - **Live integration tests** (requires actual services running)

## Running Live Tests

### Prerequisites

1. **vLLM service** running at `http://192.168.0.247:9003` with `qwen3-8B` model loaded
2. **MinerU service** running at `http://192.168.0.136:8000`
3. Sample files in `samples/` directory:
   - `samples/s_group_receipt.pdf` (S-Group PDF receipt)
   - `samples/kesko_receipt.jpg` (optional, for image OCR tests)

### Run vLLM Tests Only

```bash
# Inside Docker container
docker compose exec kyokki-api pytest tests/services/test_live_services.py -m requires_vllm -v

# Or from backend directory
pytest tests/services/test_live_services.py -m requires_vllm -v
```

**Tests included:**
- vLLM service accessibility check
- Simple Finnish receipt extraction
- English receipt extraction (language-agnostic test)
- Store hint extraction
- Model configuration verification

### Run MinerU Tests Only

```bash
docker compose exec kyokki-api pytest tests/services/test_live_services.py -m requires_mineru -v
```

**Tests included:**
- MinerU service accessibility check
- Image OCR extraction (requires `samples/kesko_receipt.jpg`)
- PDF extraction with pdfplumber fallback

### Run All Live Service Tests

```bash
docker compose exec kyokki-api pytest tests/services/test_live_services.py -m "requires_vllm or requires_mineru" -v
```

### Run End-to-End Pipeline Tests

Requires both vLLM and MinerU services running:

```bash
docker compose exec kyokki-api pytest tests/services/test_live_services.py::TestLiveEndToEndPipeline -v
```

**Tests included:**
- PDF → pdfplumber → vLLM → structured data
- Image → MinerU → vLLM → structured data

## Default Test Behavior

**By default**, when you run `pytest` or `pytest tests/`, the live service tests are **automatically excluded** via the pytest configuration in `pytest.ini`:

```ini
addopts = -m "not requires_mineru and not requires_vllm"
```

This ensures CI/CD pipelines and local development don't fail when external services are unavailable.

## Test Markers

- `@pytest.mark.requires_vllm` - Test requires vLLM service
- `@pytest.mark.requires_mineru` - Test requires MinerU service
- Both markers can be combined for end-to-end tests

## Expected Output

### vLLM Test Example

```
tests/services/test_live_services.py::TestLiveVLLMService::test_vllm_extraction_with_simple_receipt PASSED

Extracted store: Prisma Jyväskylä, chain: s-group
Extracted 3 products:
  1. Maito (Milk) - 1.0 l
  2. Ruisleipä (Rye bread) - 1.0 pcs
  3. Juusto (Cheese) - 1.0 pcs
```

### MinerU Test Example

```
tests/services/test_live_services.py::TestLiveMinerUService::test_mineru_with_pdf_fallback PASSED

Extracted 1247 characters from PDF
```

### End-to-End Test Example

```
tests/services/test_live_services.py::TestLiveEndToEndPipeline::test_end_to_end_ocr_and_extraction_with_pdf PASSED

=== Step 1: OCR Extraction ===
Extracted 1247 characters

=== Step 2: LLM Product Extraction ===
Store: Prisma
Chain: s-group
Country: FI, Language: fi

Extracted 12 products:
  1. Maito
     English: Milk
     Quantity: 1.0 l
     Price: 1.49
  ...
```

## Troubleshooting

### vLLM Connection Errors

```
Cannot connect to vLLM service at http://192.168.0.247:9003/v1
```

**Solutions:**
- Verify vLLM service is running: `curl http://192.168.0.247:9003/v1/models`
- Check model is loaded: ensure `qwen3-8B` is available
- Verify network connectivity from Docker container

### MinerU Connection Errors

```
Cannot connect to MinerU service at http://192.168.0.136:8000
```

**Solutions:**
- Verify MinerU service is running
- Check network connectivity from Docker container
- Ensure service is accepting connections

### Sample Files Not Found

```
SKIPPED: Sample PDF not found at samples/s_group_receipt.pdf
```

**Solutions:**
- Ensure sample files are mounted in Docker: check `docker-compose.yml` has `./samples:/app/samples`
- Verify files exist in `samples/` directory

## Notes

- Tests make **real API calls** and may be slow (10-30 seconds per test)
- LLM extraction quality depends on model performance (qwen3-8B)
- OCR quality depends on image/PDF quality
- Tests include verbose output to help debug extraction issues
