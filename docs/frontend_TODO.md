# Frontend — Granular Incremental Development TODO

**Stack:** Next.js 14, TypeScript, Tailwind, PWA, Zustand, React Query
**Approach:** 47 small increments with full test coverage from day 1
**Estimated Time:** ~170 hours (4-5 weeks)

> **📋 See detailed implementation plan:** `/home/linux/.claude/plans/reactive-swinging-stream.md`

---

## Directory Structure

```
frontend/
├── src/
│   ├── app/                        # Next.js App Router
│   │   ├── layout.tsx              # Root layout + providers
│   │   ├── page.tsx                # Main inventory view
│   │   ├── scan/page.tsx           # Receipt camera
│   │   ├── receipt/[id]/page.tsx   # Receipt review
│   │   ├── shopping/page.tsx       # Shopping list (Phase 2+)
│   │   └── settings/page.tsx       # Settings (Phase 2+)
│   ├── components/
│   │   ├── ui/                     # Button, Card, Modal, ProgressBar, Toast, Badge, Skeleton
│   │   ├── inventory/              # InventoryList, InventoryItem, ExpiryBadge, QuantityBar, ConsumptionSheet, CategoryFilter
│   │   ├── receipt/                # CameraCapture, ReceiptPreview, ParsedItemList, ItemCorrection, ProcessingStatus
│   │   ├── shopping/               # ShoppingList, ShoppingItem (Phase 2+)
│   │   ├── scanner/                # Hardware scanner components (Phase 2+)
│   │   └── layout/                 # AppShell, Sidebar, ActionBar, ExpiringPanel, OfflineIndicator
│   ├── hooks/
│   │   ├── useInventory.ts         # Inventory queries + mutations
│   │   ├── useReceipts.ts          # Receipt upload + polling
│   │   ├── useCategories.ts        # Category queries
│   │   ├── useWebSocket.ts         # Real-time updates
│   │   ├── useOffline.ts           # Offline queue management
│   │   ├── useToast.ts             # Toast notifications
│   │   └── useScanner.ts           # Hardware scanner (Phase 2+)
│   ├── stores/                     # Zustand stores
│   │   ├── uiStore.ts              # UI state (modals, selections)
│   │   ├── offlineStore.ts         # Offline action queue
│   │   └── scannerStore.ts         # Scanner state (Phase 2+)
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts           # Base fetch wrapper
│   │   │   ├── errors.ts           # APIError, NetworkError
│   │   │   ├── inventory.ts        # Inventory endpoints
│   │   │   ├── receipts.ts         # Receipt endpoints
│   │   │   ├── categories.ts       # Category endpoints
│   │   │   ├── products.ts         # Product endpoints (Phase 2+)
│   │   │   └── index.ts
│   │   ├── queryClient.ts          # TanStack Query config
│   │   ├── websocket.ts            # WebSocket manager
│   │   ├── storage.ts              # IndexedDB helpers
│   │   ├── camera.ts               # Camera utilities
│   │   ├── dates.ts                # Date formatting
│   │   └── utils.ts                # General utilities
│   └── types/
│       ├── inventory.ts            # InventoryItem types
│       ├── product.ts              # Product types
│       ├── category.ts             # Category types
│       ├── receipt.ts              # Receipt types
│       ├── api.ts                  # APIError, PaginatedResponse
│       └── index.ts
├── public/
│   ├── manifest.json               # PWA manifest
│   ├── icons/                      # App icons (192, 512)
│   └── sounds/                     # Scanner feedback (Phase 2+)
├── e2e/                            # Playwright E2E tests
├── next.config.js
├── tailwind.config.js              # iPad touch targets (44px min)
├── jest.config.js
├── playwright.config.ts
└── package.json
```

---

## Phase 0: Foundation Setup (15h)

### ✅ Increment 0.1: Project Initialization (4h)
- [ ] Initialize Next.js 14 with App Router, TypeScript
- [ ] Configure env: `NEXT_PUBLIC_API_URL=http://localhost:8000/api`
- [ ] Create folder structure
- [ ] Test: Dev server starts

### ✅ Increment 0.2: Tailwind + Testing (4h)
- [ ] Install Tailwind with iPad touch tokens (`min-h-touch: 44px`, `min-h-touch-lg: 56px`)
- [ ] Configure Jest + React Testing Library
- [ ] Create first smoke test
- [ ] Test: `npm test` passes

### ✅ Increment 0.3: TypeScript Types (3h)
- [ ] Mirror backend schemas: `InventoryItem`, `Product`, `Category`, `Receipt`, etc.
- [ ] Add API types: `APIError`, `PaginatedResponse`
- [ ] Test: Types compile, type guards tested

### ✅ Increment 0.4: API Client Foundation (4h)
- [ ] Create base fetch wrapper with error handling
- [ ] Add APIError, NetworkError classes
- [ ] Configure CORS and base URL
- [ ] Test: Success/error cases with MSW (Mock Service Worker)

---

## Phase 1: Inventory Viewing (26h)

### ✅ Increment 1.1: Base UI Components (6h)
- [ ] `Button` (variants: primary/secondary/ghost/danger, sizes: sm/md/lg/xl)
- [ ] `Card`, `Badge`, `Skeleton`
- [ ] Test: All variants, touch targets ≥44px, accessibility

### ✅ Increment 1.2: Inventory API Integration (4h)
- [ ] Install TanStack Query
- [ ] Create inventory API methods: `list()`, `get()`, `consume()`, etc.
- [ ] Create `useInventory` hook with queries and mutations
- [ ] Test: Mock API with MSW, optimistic updates

### ✅ Increment 1.3: ExpiryBadge Component (3h)
- [ ] Color logic: Red ≤1d, Orange 2-3d, Yellow 4-5d, Green >5d
- [ ] Date utilities: `getDaysUntilExpiry()`, `formatExpiryDate()`
- [ ] Test: All color states, edge cases

### ✅ Increment 1.4: QuantityBar Component (3h)
- [ ] Progress bar: current/initial quantity ratio
- [ ] Gradient colors based on percentage
- [ ] Display text label (e.g., "750 ml / 1000 ml")
- [ ] Test: Percentages, colors, decimal rendering

### ✅ Increment 1.5: InventoryItem Component (5h)
- [ ] Compound component with subcomponents: Image, Name, Quantity, Expiry, Actions
- [ ] Horizontal card layout
- [ ] Click handler for selection
- [ ] Test: Full data, missing fields, interactions

### ✅ Increment 1.6: InventoryList Display (4h)
- [ ] Scrollable container using `useInventory` hook
- [ ] Loading skeleton, error state, empty state
- [ ] Render InventoryItem for each item
- [ ] Test: All states with MSW

### ✅ Increment 1.7: Main Page Integration (2h)
- [ ] Update `/app/page.tsx` to render InventoryList
- [ ] Basic header with title
- [ ] Test: Integration test, manual smoke test with backend

---

## Phase 2: Consumption Actions (20h)

### ✅ Increment 2.1: UI Store (3h)
- [ ] Install Zustand
- [ ] Create UI store: modal state, selected item
- [ ] Actions: `openModal()`, `closeModal()`, `selectItem()`
- [ ] Test: State updates

### ✅ Increment 2.2: Modal Component (4h)
- [ ] Portal rendering, backdrop, ESC key, focus trap
- [ ] Sizes: sm, md, lg, fullscreen
- [ ] Test: Open/close, backdrop click, accessibility

### ✅ Increment 2.3: ConsumptionSheet Component (6h)
- [ ] Bottom sheet with proportional buttons: 1/4, 1/2, 3/4, Done
- [ ] Calculate quantity, call consume mutation
- [ ] Loading/error states
- [ ] Test: Calculations (1/4 of 1000ml = 250ml), mutations

### ✅ Increment 2.4: Toast Notification System (4h)
- [ ] Toast component with auto-dismiss
- [ ] useToast hook
- [ ] Types: success, error, warning, info
- [ ] Test: Display, auto-dismiss, multiple toasts

### ✅ Increment 2.5: Wire Consumption Flow (3h)
- [ ] Click InventoryItem → open ConsumptionSheet → consume → update list
- [ ] Optimistic UI update
- [ ] Toast notifications
- [ ] Test: Full flow, rollback on error, manual E2E

---

## Phase 3: Layout & Navigation (20h)

### ✅ Increment 3.1: AppShell Layout (4h)
- [ ] Three-column CSS Grid: Sidebar (240px), Main (flex), Actions (80px)
- [ ] Responsive breakpoints
- [ ] Test: Column widths

### ✅ Increment 3.2: Sidebar (2h)
- [ ] Left sidebar with logo/title
- [ ] Test: Rendering

### ✅ Increment 3.3: CategoryFilter (5h)
- [ ] Category API client + `useCategories` hook
- [ ] Horizontal filter pills with "All" option
- [ ] Wire to InventoryList filtering
- [ ] Test: Filter selection, integration

### ✅ Increment 3.4: ExpiringPanel (4h)
- [ ] Sidebar widget showing count of expiring items (≤3 days)
- [ ] Color indicators (red/orange)
- [ ] Click to filter main list
- [ ] Test: Count calculations

### ✅ Increment 3.5: ActionBar (3h)
- [ ] Right column with "Scan Receipt" button (56px touch target)
- [ ] Test: Rendering, touch target size

### ✅ Increment 3.6: Integrate Layout (2h)
- [ ] Update root layout with AppShell
- [ ] Integrate Sidebar, ActionBar, InventoryList
- [ ] Manual UI/UX review on iPad

---

## Phase 4: Receipt Scanning (43h)

### ✅ Increment 4.1: Camera API Setup (3h)
- [ ] Research `getUserMedia` API
- [ ] Camera permission utility
- [ ] Test: Permission handling, iPad Safari compatibility

### ✅ Increment 4.2: CameraCapture Component (6h)
- [ ] Full-screen camera preview
- [ ] Capture button (center bottom), cancel (top left), flash toggle
- [ ] Capture to canvas → Blob
- [ ] Test: Mock video, capture triggers

### ✅ Increment 4.3: Receipt Upload API (4h)
- [ ] Receipt API client: `upload()`, `get()`, `list()`
- [ ] `useReceipts` hook
- [ ] FormData upload with progress
- [ ] Test: Upload with mock file

### ✅ Increment 4.4: Scan Page (3h)
- [ ] `/app/scan/page.tsx` with CameraCapture
- [ ] Navigation from ActionBar
- [ ] Test: Routing

### ✅ Increment 4.5: ReceiptPreview Component (4h)
- [ ] Display captured image
- [ ] Retake/Upload buttons
- [ ] Upload progress indicator
- [ ] Navigate to receipt detail on success
- [ ] Test: Retake, upload, navigation

### ✅ Increment 4.6: ProcessingStatus Component (3h)
- [ ] Loading spinner with status messages
- [ ] Poll receipt status every 2s
- [ ] Transition to review when status = "completed"
- [ ] Test: Polling, status transitions

### ✅ Increment 4.7: ParsedItemList Component (5h)
- [ ] Display extracted items with icons: ✓ matched, ? uncertain, + new, — skipped
- [ ] Color-code by confidence (green >0.8, yellow 0.5-0.8, red <0.5)
- [ ] Click handler for correction
- [ ] Test: Confidence levels, icons

### ✅ Increment 4.8: Receipt Detail Page (4h)
- [ ] `/app/receipt/[id]/page.tsx`
- [ ] Fetch receipt by ID
- [ ] Show ProcessingStatus or ParsedItemList based on status
- [ ] "Confirm All" button (placeholder)
- [ ] Test: Dynamic routing, states

### ✅ Increment 4.9: ItemCorrection Modal (6h)
- [ ] Modal to edit parsed items
- [ ] Product search/select dropdown
- [ ] Quantity adjustment input
- [ ] "Create new product", "Skip this item" options
- [ ] Test: Form validation, product search, submit

### ✅ Increment 4.10: Confirm Receipt Action (5h)
- [ ] "Confirm All" button adds items to inventory
- [ ] Bulk create inventory items
- [ ] Success toast with count
- [ ] Navigate to inventory
- [ ] Test: Manual E2E (scan → review → confirm → see in inventory)

---

## Phase 5: Real-time & Offline (24h)

### ✅ Increment 5.1: WebSocket Manager (5h)
- [ ] WebSocket client with connection/reconnection
- [ ] Message parsing
- [ ] `useWebSocket` hook
- [ ] Test: Connection lifecycle, messages

### ✅ Increment 5.2: WebSocket Integration (3h)
- [ ] Connect useWebSocket to InventoryList
- [ ] Parse "item_updated" messages
- [ ] Invalidate queries on updates
- [ ] Test: Query invalidation, manual test with two clients

### ✅ Increment 5.3: Offline Store (4h)
- [ ] Zustand offline store
- [ ] Online/offline detection
- [ ] Action queue (consume, adjust, etc.)
- [ ] Sync function
- [ ] Test: Queue add/remove, online/offline state

### ✅ Increment 5.4: IndexedDB Storage (5h)
- [ ] Install `idb` library
- [ ] IndexedDB wrapper: save/load/clear queue
- [ ] Persist offline actions
- [ ] Test: CRUD with fake-indexeddb

### ✅ Increment 5.5: Offline Queue Integration (4h)
- [ ] Queue consumption actions when offline
- [ ] Auto-sync on reconnect
- [ ] Pending indicator in UI
- [ ] Test: Manual (disconnect WiFi → consume → reconnect)

### ✅ Increment 5.6: OfflineIndicator Component (3h)
- [ ] Visual indicator showing connection status
- [ ] Pending action count
- [ ] Add to Sidebar
- [ ] Test: Status changes

---

## Phase 6: PWA & Polish (22h)

### ✅ Increment 6.1: PWA Manifest (2h)
- [ ] Create `manifest.json`
- [ ] Icons (192x192, 512x512)
- [ ] Display: standalone, orientation: landscape
- [ ] Test: "Add to Home Screen" on iPad

### ✅ Increment 6.2: Service Worker (5h)
- [ ] Install `next-pwa`
- [ ] Cache app shell (HTML, CSS, JS)
- [ ] Network-first for API responses
- [ ] Test: Offline app launch

### ✅ Increment 6.3: ProgressBar Component (3h)
- [ ] Generic progress bar for loading
- [ ] Determinate and indeterminate modes
- [ ] Use in upload progress
- [ ] Test: Modes, color variants

### ✅ Increment 6.4: Error Boundary (3h)
- [ ] React error boundary with fallback UI
- [ ] Log errors
- [ ] Add to root layout
- [ ] Test: Error caught, fallback shown

### ✅ Increment 6.5: Loading States (4h)
- [ ] Consistent loading skeletons for all lists
- [ ] Page-level loading indicators
- [ ] Test: Skeleton dimensions

### ✅ Increment 6.6: Accessibility Audit (4h)
- [ ] Run axe-core tests
- [ ] Fix ARIA labels, keyboard navigation, focus indicators, color contrast
- [ ] Test: axe-core passes, screen reader

### ✅ Increment 6.7: E2E Tests (6h)
- [ ] Install Playwright
- [ ] Write E2E tests: view inventory, consume item, scan receipt, offline queue
- [ ] CI integration
- [ ] Test: All E2E pass locally

---

## iPad-Specific Optimizations

### Touch Targets
```css
.touch-target { min-height: 44px; min-width: 44px; }
.touch-lg { min-height: 56px; }
```

### Landscape Layout
```
┌──────────┬────────────────────┬──────────┐
│ Sidebar  │  Main Content      │ Actions  │
│ (240px)  │  (Flex, scrolls)   │ (80px)   │
└──────────┴────────────────────┴──────────┘
```

### Always-On Features
- Auto-refresh every 30s (TanStack Query `refetchInterval`)
- WebSocket reconnect on wake from sleep
- Prevent screen timeout (use iPad Guided Access)

### Offline-First
- IndexedDB for offline queue
- Optimistic UI updates
- Auto-sync on reconnect

---

## Key Dependencies

```json
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@tanstack/react-query": "^5.0.0",
    "zustand": "^4.4.0",
    "date-fns": "^3.0.0",
    "lucide-react": "^0.300.0",
    "idb": "^8.0.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "@types/react": "^18.2.0",
    "@types/node": "^20.0.0",
    "tailwindcss": "^3.4.0",
    "jest": "^29.7.0",
    "@testing-library/react": "^14.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@playwright/test": "^1.40.0",
    "msw": "^2.0.0"
  }
}
```

---

## Testing Strategy

- **Unit Tests**: Jest + React Testing Library for all components
- **Integration Tests**: MSW (Mock Service Worker) for API mocking
- **E2E Tests**: Playwright for critical user flows
- **Coverage Goal**: >80% for critical paths

---

## Backend API Integration

**Base URL**: `http://localhost:8000/api`

**Available Endpoints**:
- `GET /api/inventory?location=&status=&expiring_days=`
- `POST /api/inventory/{id}/consume` → `{"quantity": decimal}`
- `POST /api/receipts/scan` (multipart/form-data)
- `GET /api/receipts/{id}` → `processing_status: "queued" | "processing" | "completed" | "failed"`
- `GET /api/categories`
- `GET /api/products?search=`

**WebSocket**: Backend listens to Redis "item_updates" channel for real-time broadcasts

---

## Next Steps

1. ✅ **Plan Approved** - Granular incremental approach ready
2. 🚀 **Start Increment 0.1** - Initialize Next.js 14 project
3. 📊 **Track Progress** - Use TodoWrite tool for each increment
4. 🔄 **Iterate** - Adjust increment scope based on reality
5. 🧪 **Test Continuously** - Full coverage from day 1

---

**Progress**: 0/47 increments completed (~0% done)
