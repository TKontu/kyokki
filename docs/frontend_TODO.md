# Frontend — Development TODO

**Stack:** Next.js 14, TypeScript, Tailwind, PWA, Zustand, React Query

## Directory Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              # Main inventory
│   │   ├── scan/page.tsx         # Receipt scanner
│   │   ├── receipt/[id]/page.tsx # Receipt review
│   │   ├── shopping/page.tsx     # Shopping list
│   │   └── settings/page.tsx
│   ├── components/
│   │   ├── ui/                   # Button, Card, Modal, ProgressBar, Toast
│   │   ├── inventory/            # InventoryList, InventoryItem, ConsumptionButtons
│   │   ├── receipt/              # CameraCapture, ParsedItemList, ItemCorrection
│   │   ├── shopping/             # ShoppingList, ShoppingItem
│   │   └── layout/               # Sidebar, ContextSelector, ActionButtons
│   ├── hooks/
│   │   ├── useInventory.ts
│   │   ├── useReceipt.ts
│   │   ├── useShopping.ts
│   │   ├── useScanner.ts
│   │   ├── useWebSocket.ts
│   │   └── useOffline.ts
│   ├── stores/
│   │   ├── uiStore.ts
│   │   └── offlineStore.ts
│   ├── lib/
│   │   ├── api.ts
│   │   └── websocket.ts
│   └── types/
├── public/
│   ├── manifest.json
│   └── icons/
├── next.config.js
├── tailwind.config.js
└── package.json
```

---

## Phase 1 Tasks

### Setup
- [ ] Next.js 14 with App Router
- [ ] Tailwind with touch-optimized config
- [ ] PWA manifest + service worker
- [ ] React Query + Zustand

### Core Components

**UI Components**
- [ ] Button (44px min touch target, variants)
- [ ] Card (inventory item container)
- [ ] ProgressBar (quantity indicator, color-coded)
- [ ] Modal (full-screen on iPad)
- [ ] Toast (success/error feedback)

**Inventory Components**
- [ ] InventoryList (virtualized)
- [ ] InventoryItem (name, quantity bar, expiry badge, actions)
- [ ] ConsumptionButtons (proportional: 1/4, 1/2, 3/4, Done; count: -1, -2, -3)
- [ ] ExpiryBadge (color: 🔴≤1d, 🟠2-3d, 🟡4-5d, 🟢>5d)
- [ ] CategoryFilter (horizontal pills)

**Receipt Components**
- [ ] CameraCapture (full-screen, capture button, preview)
- [ ] ParsedItemList (extracted items with match status)
- [ ] ItemCorrection (modal to fix parsed item)
- [ ] ConfirmButton (add X items)

**Layout Components**
- [ ] Sidebar (context selector, expiring panel, actions)
- [ ] ContextSelector (breakfast, lunch, dinner, snack, cooking)
- [ ] ExpiringPanel (🔴 X items, 🟡 Y items)
- [ ] ActionButtons (Scan Receipt, Add Manual)

### Pages
- [ ] Main inventory view with context sorting
- [ ] Receipt scan page (camera)
- [ ] Receipt review page (confirm/edit items)
- [ ] Settings page (context times, expiry warnings)

### State & Data
- [ ] useInventory hook (React Query)
- [ ] useReceipt hook (upload, poll status, confirm)
- [ ] useWebSocket hook (real-time updates)
- [ ] useOffline hook (queue actions, sync on reconnect)
- [ ] API client

---

## Phase 2 Tasks

### Hardware Scanner Support
- [ ] useScanner hook (detect rapid keystrokes)
- [ ] Scanner mode toggle UI (Add / Consume / Lookup)
- [ ] Scan feedback (visual + sound)
- [ ] Last scanned item display

### Shopping List
- [ ] ShoppingList component
- [ ] ShoppingItem (priority indicator, quantity, purchased toggle)
- [ ] Add item modal (search product or free text)
- [ ] Priority toggle (Urgent/Normal/Low)
- [ ] Shopping page

### Multi-Receipt Batch
- [ ] Receipt queue UI (thumbnails)
- [ ] Queue indicator badge
- [ ] Process All button
- [ ] Consolidated review screen

### Enhanced Features
- [ ] Product search with autocomplete
- [ ] Consumption history view
- [ ] Dark mode

---

## Phase 3 Tasks

### Sync Recovery UI
- [ ] Swipe to "Mark as Gone"
- [ ] "Clear All Expired" button
- [ ] Quick quantity adjustment
- [ ] "Just Bought" flow

### Stock Alerts
- [ ] Low stock indicator on inventory items
- [ ] Shopping list auto-added items highlight

---

## iPad-Specific

### Touch Optimization
```css
.touch-target { min-height: 44px; min-width: 44px; }
.touch-lg { min-height: 56px; }
```

### Landscape Layout
- Fixed sidebar (left)
- Main content (scrollable center)
- Action buttons (right)

### Always-On
- Auto-refresh every 30s
- WebSocket reconnect on wake
- Prevent screen timeout (Guided Access)

### Offline
- Cache inventory in IndexedDB
- Queue consumption actions
- Sync on reconnect

---

## PWA Config

```json
{
  "name": "Kyokki",
  "short_name": "Fridge",
  "display": "standalone",
  "orientation": "landscape",
  "theme_color": "#3b82f6"
}
```

---

## Dependencies

```json
{
  "@tanstack/react-query": "^5.0.0",
  "zustand": "^4.4.0",
  "idb": "^7.1.0",
  "date-fns": "^2.30.0",
  "lucide-react": "^0.294.0"
}
```
