# Handoff: Increment 1.6 Complete — Frontend Increment 1.7 Next

## Completed This Session

- **InventoryList component** (Increment 1.6): uses `useInventoryList` hook, renders `InventoryItemCard` per item, loading skeleton / error / empty states, 23 tests — all passing
- `frontend/components/inventory/index.ts` barrel export updated

## Next Steps

- [ ] **Increment 1.7**: Wire `InventoryList` into `frontend/app/page.tsx`, manual smoke test with backend
- [ ] **GS1 DataMatrix parser**: `backend/app/services/gs1_parser.py` — parse AI (17) expiry, (310x) weight; wire into scanner scan endpoint

## Key Files

- `frontend/components/inventory/InventoryList.tsx` — Increment 1.6, ready to wire into page
- `frontend/components/inventory/InventoryItemCard.tsx` — Increment 1.5
- `frontend/components/inventory/index.ts` — barrel exports (ExpiryBadge, QuantityBar, InventoryItemCard, InventoryList)
- `frontend/hooks/useInventory.ts` — TanStack Query hooks for inventory CRUD
- `backend/app/services/scanner_service.py` — scanner logic, fully fixed

## Context

- pytest venv: `/projects/kyokki_2/.venv/bin/pytest`
- 93 backend non-DB tests passing; DB tests need PostgreSQL (not available in this env)
- `stack.env` `ALLOWED_ORIGINS` must be set to LAN IP for production deployment
- `InventoryItem` type does not carry `productName` — `InventoryList` accepts optional `productNames: Record<string, string>` prop (product_master_id → name); falls back to truncated UUID
