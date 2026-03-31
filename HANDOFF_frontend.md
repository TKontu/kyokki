# Handoff: Kyokki Frontend — Increment 1.4 In Progress

## Completed

**Phase 0: Foundation Setup** ✅ (4/4 increments)
- Next.js 14 + TypeScript + Tailwind + App Router
- Jest + RTL infrastructure, iPad-optimized touch targets
- TypeScript types mirroring all backend Pydantic schemas
- Base API client with error handling
- PR #8 merged to main

**Phase 1: Inventory Viewing** — Increments 1.1–1.3 ✅

- **Increment 1.1**: `Button`, `Card`, `Badge`, `Skeleton` UI components with full test coverage
- **Increment 1.2**: `lib/api/inventory.ts` + `useInventory` hook with TanStack Query
- **Increment 1.3**: `ExpiryBadge` component + date utilities (`getDaysUntilExpiry`, `formatExpiryDate`, `getExpiryStatus`, `getExpiryColorClasses`)
  - PR #15 merged

## In Progress

**Increment 1.4: QuantityBar Component** — branch `feature/frontend-increment-1.4-quantitybar`

- `frontend/components/inventory/QuantityBar.tsx` — **written and functionally complete**
- `frontend/components/inventory/__tests__/QuantityBar.test.tsx` — **written, 41/42 tests passing**
- `frontend/components/inventory/index.ts` — barrel export file created

**One failing test** (must fix before PR):
- File: `components/inventory/__tests__/QuantityBar.test.tsx:44`
- Test: `"should handle zero current quantity"`
- Cause: `getByText(/0/)` is too broad — matches both `"0 / 1000 ml"` and `"0%"` when current=0
- Fix: Use `getByText(/0 \/ 1000/)` or a more specific query

## Next Steps

- [ ] Fix failing test at `QuantityBar.test.tsx:44` (1-line change)
- [ ] Run `npm test` to confirm 201/201 pass
- [ ] Commit and push, create PR for Increment 1.4
- [ ] **Increment 1.5**: InventoryItem Component (5h)
  - Compose `ExpiryBadge` + `QuantityBar` into a full inventory item card
  - Show product name, category, location, expiry, quantity
  - Touch-target compliant (≥44px interactive areas)
- [ ] **Increment 1.6**: InventoryList Display (4h)
- [ ] **Increment 1.7**: Main Page Integration (2h)

## Key Files

- `frontend/components/inventory/QuantityBar.tsx` — progress bar, color-coded by % remaining (green ≥75%, yellow ≥50%, orange ≥25%, red <25%), compact mode supported
- `frontend/components/inventory/__tests__/QuantityBar.test.tsx` — 42 tests covering color, width, formatting, accessibility, edge cases
- `frontend/components/inventory/index.ts` — barrel export (ExpiryBadge, QuantityBar)
- `frontend/components/inventory/ExpiryBadge.tsx` — expiry color badge (from Increment 1.3)
- `frontend/lib/dates.ts` — date utilities
- `frontend/hooks/useInventory.ts` — TanStack Query hooks for inventory CRUD

## Context

### Current Branch
- **Branch**: `feature/frontend-increment-1.4-quantitybar`
- **Base**: `main`
- **Test count**: 201 total (1 failing — see above)

### Technical Decisions

1. **Jest mocks over MSW**: Node polyfill issues with MSW; using `global.fetch` mocks. Not worth revisiting until Phase 2.
2. **Type Safety First**: Zero `any` usage. All frontend types mirror backend schemas exactly.
3. **iPad-First**: Custom Tailwind tokens for 44px/56px touch targets.
4. **TDD**: Tests written alongside every component.

### Development Commands

```bash
# Frontend (from /projects/kyokki_2/frontend)
npm test              # Run all tests
npm run test:watch    # Watch mode
npm run dev           # Dev server (localhost:3000)
npm run build         # Production build
npm run lint          # ESLint
```

---

**Recommendation**: Run `/clear` to start fresh, then fix the one failing test and create the PR.
