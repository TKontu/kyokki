# Handoff: Backend — Scanner API complete, pipeline bugs fixed

## Current State

**Branch**: `main` (up to date, PR #21 merged)
**Tests**: 93 non-DB tests passing; DB tests require PostgreSQL (not available in dev env)

### All complete
- Full CRUD API: categories, products, inventory, receipts, shopping list
- Receipt processing pipeline: MinerU OCR → vLLM extraction → RapidFuzz matching
- WebSocket real-time broadcasts (Redis pub/sub)
- Open Food Facts integration (barcode → auto-create product)
- Universal Scanner API: `POST /api/scanner/scan`, mode management, station tracking
- Scanner pipeline fixes: CORS env config, Redis resilience, OFF unit parsing, UNIQUE constraint on `off_product_id`, station_id validation, consume capping feedback

## Next Priorities

### GS1 DataMatrix Parser (2-3h)
- File: `backend/app/services/gs1_parser.py` (stub exists)
- Parse AIs: (17) expiry YYMMDD, (10) batch, (310x) weight
- Wire into `POST /api/scanner/scan` — if GS1 expiry found, use it instead of category default
- Tests: common GS1 format cases

### Home Assistant Integration (see `docs/HOME_ASSISTANT_SPEC.md`)
- `GET /api/ha/status` — aggregated inventory stats
- `GET /api/ha/expiring` — items expiring soon
- `POST /api/ha/consume` — consume by name (voice command)

### Celery Async Receipt Processing (optional, low priority)
- Currently synchronous in the request cycle
- Only needed if large receipts cause timeout issues in practice

## Key Files

```
backend/app/
  api/endpoints/scanner.py       # Scanner endpoints + station_id validation
  services/scanner_service.py    # Mode management, station tracking, scan processing
  services/off_service.py        # OFF client + parse_off_quantity helper
  services/broadcast_helpers.py  # WebSocket broadcast helpers + Redis client
  crud/product_master.py         # enrich_product_from_off_data + IntegrityError guard
  models/product_master.py       # UniqueConstraint on off_product_id
  core/config.py                 # ALLOWED_ORIGINS field_validator

backend/tests/
  api/test_scanner.py            # 33 scanner tests (mode, stations, validation, resilience)
  services/test_off_service.py   # 17 parse_off_quantity tests + enrichment tests
```

## Environment

```bash
# Run non-DB tests
/projects/kyokki_2/.venv/bin/pytest tests/api/test_scanner.py tests/services/test_off_service.py -v

# Lint
/projects/kyokki_2/.venv/bin/ruff check .
# 15 pre-existing errors in receipt.py, matching_service.py, test files — not our code
```

### stack.env
`ALLOWED_ORIGINS` must be set to LAN IP for production (e.g. `http://192.168.0.x:3000`)
