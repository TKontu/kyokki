# Handoff: Frontend — Phase 1 Inventory Viewing (Increment 1.7 next)

## Current State

**Branch**: `main`

**Phase 0 complete** — Next.js 14, TypeScript, Tailwind (iPad touch tokens), Jest/RTL, base API client

**Phase 1 increments done**:
- 1.1: `Button`, `Card`, `Badge` (`StatusBadge`), `Skeleton`
- 1.2: `lib/api/inventory.ts` + `useInventory` hook (TanStack Query)
- 1.3: `ExpiryBadge` + date utilities (`getDaysUntilExpiry`, `formatExpiryDate`, `getExpiryStatus`)
- 1.4: `QuantityBar` — color-coded progress bar (green ≥75%, yellow ≥50%, orange ≥25%, red <25%), compact mode
- 1.5: `InventoryItemCard` — composes ExpiryBadge + QuantityBar + StatusBadge; inactive state for empty/discarded; optional consume/edit actions
- 1.6: `InventoryList` — uses `useInventoryList`, renders `InventoryItemCard` per item; loading skeleton / error / empty states; optional `productNames` map prop

## Next Steps

### Increment 1.7: Main Page Integration (2h)
- Update `frontend/app/page.tsx` with InventoryList
- Basic header
- Manual smoke test with backend running

### Then Phase 2: Consumption Actions
- Zustand UI store → modal → ConsumptionSheet (1/4, 1/2, 3/4, Done buttons)
- Toast notifications

## Key Files

```
frontend/components/inventory/
  InventoryList.tsx           # Increment 1.6 — list with all states
  InventoryItemCard.tsx       # Increment 1.5 — full item card
  QuantityBar.tsx             # Progress bar
  ExpiryBadge.tsx             # Expiry color badge
  index.ts                    # Barrel exports

frontend/components/ui/
  Button.tsx, Card.tsx, Badge.tsx, Skeleton.tsx

frontend/lib/api/inventory.ts   # API methods
frontend/hooks/useInventory.ts  # TanStack Query hooks
frontend/lib/dates.ts           # Date utilities
frontend/types/                 # All backend schema mirrors
```

## Technical Notes

- `InventoryItem` does NOT carry `productName` — `InventoryList` accepts `productNames: Record<string, string>` (product_master_id → name), falls back to `Product <truncated-id>`
- No frontend product API module yet — Increment 1.7 will need to handle product name resolution
- `StatusBadge` maps: `sealed`→success, `opened`→info, `partial`→warning, `empty`→default, `discarded`→error
- Jest mocks use `global.fetch`, not MSW (Node polyfill issues — not worth fixing)
- All touch targets ≥44px (Tailwind `min-h-touch` token)

## Dev Commands

```bash
# from /projects/kyokki_2/frontend
npm test          # run all tests
npm run dev       # localhost:3000
npm run build     # production build
```
