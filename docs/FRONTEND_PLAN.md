# Frontend Architecture & Implementation Plan

## Overview

This document outlines the complete frontend architecture for the Kyokki PWA, designed specifically for an always-on iPad mounted in a kitchen.

**Target:** iPad (landscape orientation, 10-11" screen, touch-optimized)
**Stack:** Next.js 14, TypeScript, Tailwind CSS, Zustand, TanStack Query, PWA

---

## 1. Architecture Decisions

### 1.1 Component Pattern: Compound Components

We'll use compound components for complex UI elements, allowing flexible composition while maintaining encapsulation.

```tsx
// Usage
<InventoryItem>
  <InventoryItem.Name />
  <InventoryItem.QuantityBar />
  <InventoryItem.ExpiryBadge />
  <InventoryItem.Actions />
</InventoryItem>
```

### 1.2 State Management Strategy

| State Type | Solution | Scope |
|------------|----------|-------|
| **Server state** | TanStack Query | API data, caching, sync |
| **UI state** | Zustand | Sidebar open, modals, scanner mode |
| **Form state** | React Hook Form | Input validation |
| **Offline queue** | Zustand + IndexedDB | Pending mutations |

### 1.3 Data Fetching Pattern

```tsx
// Queries for reads
const { data: inventory } = useQuery({
  queryKey: ['inventory', context],
  queryFn: () => api.inventory.list({ context }),
  staleTime: 30_000,  // 30s for always-on display
})

// Mutations for writes with optimistic updates
const consumeMutation = useMutation({
  mutationFn: api.inventory.consume,
  onMutate: async (data) => {
    // Optimistic update
    queryClient.setQueryData(['inventory'], old => ...)
  },
  onError: (err, data, context) => {
    // Rollback on error
    queryClient.setQueryData(['inventory'], context.previousData)
  }
})
```

### 1.4 Offline Strategy

```
User Action → Check Online?
  ├─ Online → API Call → Update Cache → UI Feedback
  └─ Offline → Queue in IndexedDB → Optimistic UI → Sync on Reconnect
```

**Queued Operations:**
- Consumption actions
- Quantity adjustments
- Receipt confirmations

**NOT Queued (require connection):**
- Receipt OCR (needs server processing)
- Product search

---

## 2. Directory Structure

```
frontend/
├── src/
│   ├── app/                          # Next.js App Router
│   │   ├── layout.tsx                # Root layout + providers
│   │   ├── page.tsx                  # Main inventory view
│   │   ├── scan/
│   │   │   └── page.tsx              # Receipt camera capture
│   │   ├── receipt/
│   │   │   └── [id]/
│   │   │       └── page.tsx          # Receipt review/confirm
│   │   ├── shopping/
│   │   │   └── page.tsx              # Shopping list
│   │   └── settings/
│   │       └── page.tsx              # App settings
│   │
│   ├── components/
│   │   ├── ui/                       # Base UI components
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── ProgressBar.tsx
│   │   │   ├── Toast.tsx
│   │   │   ├── Skeleton.tsx
│   │   │   ├── Badge.tsx
│   │   │   └── index.ts              # Barrel export
│   │   │
│   │   ├── inventory/                # Inventory feature
│   │   │   ├── InventoryList.tsx     # Virtualized list container
│   │   │   ├── InventoryItem.tsx     # Compound component
│   │   │   ├── QuantityBar.tsx       # Visual quantity indicator
│   │   │   ├── ExpiryBadge.tsx       # Color-coded expiry
│   │   │   ├── ConsumptionSheet.tsx  # Bottom sheet for consumption
│   │   │   ├── CategoryFilter.tsx    # Horizontal filter pills
│   │   │   └── index.ts
│   │   │
│   │   ├── receipt/                  # Receipt scanning feature
│   │   │   ├── CameraCapture.tsx     # Full-screen camera
│   │   │   ├── ReceiptPreview.tsx    # Captured image preview
│   │   │   ├── ParsedItemList.tsx    # Extracted items
│   │   │   ├── ItemCorrection.tsx    # Edit parsed item modal
│   │   │   ├── ProcessingStatus.tsx  # OCR progress indicator
│   │   │   └── index.ts
│   │   │
│   │   ├── shopping/                 # Shopping list feature
│   │   │   ├── ShoppingList.tsx
│   │   │   ├── ShoppingItem.tsx
│   │   │   ├── AddItemModal.tsx
│   │   │   ├── PrioritySelector.tsx
│   │   │   └── index.ts
│   │   │
│   │   ├── scanner/                  # Hardware scanner
│   │   │   ├── ScannerListener.tsx   # Global keyboard listener
│   │   │   ├── ScannerModeSelector.tsx
│   │   │   ├── ScanFeedback.tsx      # Visual + audio feedback
│   │   │   └── index.ts
│   │   │
│   │   └── layout/                   # App layout
│   │       ├── AppShell.tsx          # Main layout wrapper
│   │       ├── Sidebar.tsx           # Left sidebar
│   │       ├── ContextSelector.tsx   # Meal context buttons
│   │       ├── ExpiringPanel.tsx     # Expiring items summary
│   │       ├── ActionBar.tsx         # Bottom/right action buttons
│   │       ├── OfflineIndicator.tsx  # Connection status
│   │       └── index.ts
│   │
│   ├── hooks/                        # Custom hooks
│   │   ├── useInventory.ts           # Inventory CRUD + queries
│   │   ├── useReceipt.ts             # Receipt upload + polling
│   │   ├── useShopping.ts            # Shopping list operations
│   │   ├── useScanner.ts             # Hardware scanner detection
│   │   ├── useWebSocket.ts           # Real-time updates
│   │   ├── useOffline.ts             # Offline queue management
│   │   ├── useToast.ts               # Toast notifications
│   │   └── useMediaQuery.ts          # Responsive helpers
│   │
│   ├── stores/                       # Zustand stores
│   │   ├── uiStore.ts                # UI state (modals, sidebar)
│   │   ├── scannerStore.ts           # Scanner mode, last scan
│   │   ├── offlineStore.ts           # Offline action queue
│   │   └── index.ts
│   │
│   ├── lib/                          # Utilities
│   │   ├── api/                      # API client
│   │   │   ├── client.ts             # Fetch wrapper
│   │   │   ├── inventory.ts          # Inventory endpoints
│   │   │   ├── receipts.ts           # Receipt endpoints
│   │   │   ├── shopping.ts           # Shopping endpoints
│   │   │   ├── products.ts           # Product endpoints
│   │   │   └── index.ts
│   │   ├── websocket.ts              # WebSocket manager
│   │   ├── storage.ts                # IndexedDB helpers
│   │   ├── dates.ts                  # Date formatting
│   │   ├── constants.ts              # App constants
│   │   └── utils.ts                  # General utilities
│   │
│   ├── types/                        # TypeScript types
│   │   ├── inventory.ts
│   │   ├── receipt.ts
│   │   ├── shopping.ts
│   │   ├── product.ts
│   │   ├── api.ts
│   │   └── index.ts
│   │
│   └── styles/
│       └── globals.css               # Tailwind + custom styles
│
├── public/
│   ├── manifest.json                 # PWA manifest
│   ├── sw.js                         # Service worker
│   ├── icons/                        # App icons
│   │   ├── icon-192.png
│   │   ├── icon-512.png
│   │   └── apple-touch-icon.png
│   └── sounds/                       # Scanner feedback
│       ├── scan-success.mp3
│       └── scan-error.mp3
│
├── next.config.js
├── tailwind.config.js
├── tsconfig.json
└── package.json
```

---

## 3. Component Specifications

### 3.1 UI Components (Base Layer)

#### Button
```tsx
interface ButtonProps {
  variant: 'primary' | 'secondary' | 'ghost' | 'danger'
  size: 'sm' | 'md' | 'lg' | 'xl'  // xl = 56px for main actions
  fullWidth?: boolean
  loading?: boolean
  disabled?: boolean
  icon?: ReactNode
  children: ReactNode
}

// Touch targets: sm=36px, md=44px, lg=48px, xl=56px
```

#### ProgressBar
```tsx
interface ProgressBarProps {
  value: number          // 0-100
  max?: number           // Default 100
  variant: 'quantity' | 'expiry'
  showLabel?: boolean
}

// quantity: Blue gradient
// expiry: Red(≤1d) → Orange(2-3d) → Yellow(4-5d) → Green(>5d)
```

#### Modal
```tsx
interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  size: 'sm' | 'md' | 'lg' | 'fullscreen'
  children: ReactNode
}

// iPad: 'lg' = 600px wide, 'fullscreen' for camera/forms
```

#### Toast
```tsx
interface ToastProps {
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
  duration?: number      // Default 3000ms
  action?: {
    label: string
    onClick: () => void
  }
}
```

### 3.2 Inventory Components

#### InventoryItem (Compound)
```tsx
// Container
<InventoryItem item={item} onSelect={handleSelect}>
  <InventoryItem.Image />      {/* Product image or category icon */}
  <InventoryItem.Name />       {/* Product name + brand */}
  <InventoryItem.Quantity />   {/* QuantityBar + text */}
  <InventoryItem.Expiry />     {/* ExpiryBadge */}
  <InventoryItem.Actions />    {/* Quick consume buttons */}
</InventoryItem>

// Layout: Horizontal card
// [Image] [Name/Brand] [=====Quantity=====] [Expiry] [Actions]
```

#### ConsumptionSheet
```tsx
// Bottom sheet triggered by InventoryItem selection
// Shows consumption options based on unit_type:

// For proportional (liquids, spreads):
[1/4] [1/2] [3/4] [Empty]

// For countable (eggs, yogurts):
[-1] [-2] [-3] [Custom...]

// For single items:
[Mark as Used] [Mark as Discarded]
```

#### ExpiryBadge
```tsx
// Color coding:
// 🔴 Red:    Expired or expires today
// 🟠 Orange: 1-2 days
// 🟡 Yellow: 3-5 days
// 🟢 Green:  >5 days
// ⚪ Gray:   Unknown expiry

// Display: "2d" / "Today" / "Expired" / "5d+"
```

### 3.3 Receipt Components

#### CameraCapture
```tsx
// Full-screen camera view
// - Preview from rear camera
// - Large capture button (center bottom)
// - Flash toggle (top right)
// - Cancel button (top left)
// - Grid overlay option
// - Auto-capture on stability (optional)

// After capture:
// - Preview with retake/confirm buttons
// - Crop handles (optional)
```

#### ParsedItemList
```tsx
interface ParsedItem {
  id: string
  receipt_name: string       // Raw from receipt
  matched_product?: Product  // Matched product
  confidence: number         // Match confidence 0-1
  quantity: number
  unit: string
  status: 'matched' | 'new' | 'uncertain' | 'skipped'
}

// Display:
// [✓] Valio Milk 1L          ← High confidence match
// [?] "VALIO MAIT 1L"        ← Low confidence, needs review
// [+] Unknown Product        ← New product, will create
// [—] PANTTI 0,15            ← Skipped (deposit)
```

#### ItemCorrection
```tsx
// Modal for correcting parsed items:
// - Original text (read-only)
// - Product search/select
// - Quantity adjustment
// - "Create new product" option
// - "Skip this item" option
```

### 3.4 Layout Components

#### AppShell
```tsx
// iPad landscape layout:
//
// ┌─────────────────────────────────────────────────────────┐
// │ [Sidebar]  │        [Main Content]         │ [Actions]  │
// │            │                               │            │
// │ Context    │  ┌─────────────────────────┐  │ [Scan]     │
// │ Selector   │  │                         │  │            │
// │            │  │    Inventory List       │  │ [Add]      │
// │ ────────── │  │    (Scrollable)         │  │            │
// │            │  │                         │  │ [Shop]     │
// │ Expiring   │  │                         │  │            │
// │ Panel      │  └─────────────────────────┘  │            │
// │            │                               │            │
// └─────────────────────────────────────────────────────────┘
//
// Widths: Sidebar=240px, Main=flexible, Actions=80px
```

#### Sidebar
```tsx
// Fixed left sidebar containing:
// 1. App logo/title
// 2. ContextSelector (meal context)
// 3. ExpiringPanel (warning counts)
// 4. Category filters (optional collapse)
// 5. Scanner mode indicator
// 6. Connection status
```

#### ContextSelector
```tsx
// Meal context buttons:
// [🌅 Breakfast] [🌞 Lunch] [🌆 Dinner] [🍿 Snack] [👨‍🍳 Cooking] [All]

// Auto-selection based on time:
// 06:00-10:00 → Breakfast
// 11:00-14:00 → Lunch
// 17:00-21:00 → Dinner
// Others → All

// Manual override persists for 30 minutes
```

---

## 4. State Management Details

### 4.1 UI Store (Zustand)

```typescript
interface UIState {
  // Sidebar
  sidebarCollapsed: boolean
  
  // Modals
  activeModal: 'consumption' | 'add-item' | 'correction' | 'settings' | null
  modalData: unknown
  
  // Context
  mealContext: MealContext | 'all'
  contextOverrideExpiry: number | null  // Timestamp when override expires
  
  // Selection
  selectedItemId: string | null
  
  // Actions
  toggleSidebar: () => void
  openModal: (modal: string, data?: unknown) => void
  closeModal: () => void
  setMealContext: (context: MealContext | 'all') => void
  selectItem: (id: string | null) => void
}
```

### 4.2 Scanner Store (Zustand)

```typescript
interface ScannerState {
  mode: 'add' | 'consume' | 'lookup'
  lastScan: {
    barcode: string
    timestamp: number
    result: ScanResult
  } | null
  isProcessing: boolean
  
  setMode: (mode: ScannerMode) => void
  recordScan: (barcode: string, result: ScanResult) => void
  clearLastScan: () => void
}
```

### 4.3 Offline Store (Zustand + IndexedDB)

```typescript
interface OfflineState {
  isOnline: boolean
  pendingActions: OfflineAction[]
  syncInProgress: boolean
  lastSyncAt: number | null
  
  queueAction: (action: OfflineAction) => void
  syncPendingActions: () => Promise<void>
  clearQueue: () => void
}

interface OfflineAction {
  id: string
  type: 'consume' | 'adjust' | 'add' | 'delete'
  payload: unknown
  timestamp: number
  retryCount: number
}
```

---

## 5. API Client Design

### 5.1 Base Client

```typescript
// lib/api/client.ts
class APIClient {
  private baseURL: string
  private onError?: (error: APIError) => void
  
  constructor(config: APIConfig) {
    this.baseURL = config.baseURL
    this.onError = config.onError
  }
  
  async request<T>(
    method: string,
    path: string,
    options?: RequestOptions
  ): Promise<T> {
    const url = `${this.baseURL}${path}`
    
    try {
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        body: options?.body ? JSON.stringify(options.body) : undefined,
      })
      
      if (!response.ok) {
        throw new APIError(response.status, await response.json())
      }
      
      return response.json()
    } catch (error) {
      if (error instanceof APIError) {
        this.onError?.(error)
        throw error
      }
      // Network error - queue for offline
      throw new NetworkError('Network request failed')
    }
  }
  
  get<T>(path: string, params?: Record<string, string>) { ... }
  post<T>(path: string, body: unknown) { ... }
  patch<T>(path: string, body: unknown) { ... }
  delete<T>(path: string) { ... }
}
```

### 5.2 Resource Clients

```typescript
// lib/api/inventory.ts
export const inventoryAPI = {
  list: (params: InventoryListParams) => 
    client.get<InventoryItem[]>('/inventory', params),
    
  get: (id: string) => 
    client.get<InventoryItem>(`/inventory/${id}`),
    
  consume: (id: string, data: ConsumeData) =>
    client.post<InventoryItem>(`/inventory/${id}/consume`, data),
    
  reconcile: (items: ReconcileData[]) =>
    client.post<void>('/inventory/reconcile', { items }),
}
```

---

## 6. Custom Hooks

### 6.1 useInventory

```typescript
export function useInventory(options?: UseInventoryOptions) {
  const { context = 'all', category } = options ?? {}
  
  // Query
  const query = useQuery({
    queryKey: ['inventory', { context, category }],
    queryFn: () => inventoryAPI.list({ context, category }),
    staleTime: 30_000,
    refetchInterval: 30_000,  // Auto-refresh for always-on
  })
  
  // Mutations
  const consumeMutation = useMutation({
    mutationFn: (data: ConsumeData) => inventoryAPI.consume(data.id, data),
    onMutate: async (data) => {
      await queryClient.cancelQueries(['inventory'])
      const previous = queryClient.getQueryData(['inventory'])
      
      // Optimistic update
      queryClient.setQueryData(['inventory'], (old: InventoryItem[]) =>
        old.map(item => 
          item.id === data.id 
            ? { ...item, current_quantity: item.current_quantity - data.quantity }
            : item
        )
      )
      
      return { previous }
    },
    onError: (err, data, context) => {
      queryClient.setQueryData(['inventory'], context?.previous)
      toast.error('Failed to update. Will retry when online.')
    },
    onSettled: () => {
      queryClient.invalidateQueries(['inventory'])
    },
  })
  
  return {
    items: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    consume: consumeMutation.mutate,
    isConsuming: consumeMutation.isPending,
  }
}
```

### 6.2 useScanner

```typescript
export function useScanner() {
  const { mode, setMode, recordScan } = useScannerStore()
  const [buffer, setBuffer] = useState('')
  const lastKeyTime = useRef(0)
  
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const now = Date.now()
      
      // Detect rapid keystrokes (scanner input is fast)
      if (now - lastKeyTime.current < 50) {
        // Likely scanner input
        if (e.key === 'Enter') {
          // Complete barcode
          processScan(buffer)
          setBuffer('')
        } else if (e.key.length === 1) {
          setBuffer(prev => prev + e.key)
        }
      } else {
        // Reset buffer - too slow for scanner
        setBuffer(e.key.length === 1 ? e.key : '')
      }
      
      lastKeyTime.current = now
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [buffer, mode])
  
  const processScan = async (barcode: string) => {
    // Validate barcode format
    if (!isValidBarcode(barcode)) return
    
    // Play feedback sound
    playSound('scan')
    
    // Process based on mode
    switch (mode) {
      case 'add':
        await addByBarcode(barcode)
        break
      case 'consume':
        await consumeByBarcode(barcode)
        break
      case 'lookup':
        await lookupBarcode(barcode)
        break
    }
  }
  
  return { mode, setMode }
}
```

### 6.3 useOffline

```typescript
export function useOffline() {
  const { isOnline, pendingActions, queueAction, syncPendingActions } = useOfflineStore()
  
  // Monitor online status
  useEffect(() => {
    const handleOnline = () => {
      useOfflineStore.setState({ isOnline: true })
      syncPendingActions()  // Auto-sync when back online
    }
    
    const handleOffline = () => {
      useOfflineStore.setState({ isOnline: false })
    }
    
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])
  
  // Persist queue to IndexedDB
  useEffect(() => {
    persistQueue(pendingActions)
  }, [pendingActions])
  
  return {
    isOnline,
    pendingCount: pendingActions.length,
    queueAction,
    sync: syncPendingActions,
  }
}
```

---

## 7. PWA Configuration

### 7.1 manifest.json

```json
{
  "name": "Kyokki",
  "short_name": "Kyokki",
  "description": "Kitchen inventory management - track all groceries, dry goods, and consumables",
  "start_url": "/",
  "display": "standalone",
  "orientation": "landscape",
  "theme_color": "#3b82f6",
  "background_color": "#f8fafc",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ],
  "screenshots": [
    {
      "src": "/screenshots/inventory.png",
      "sizes": "1024x768",
      "type": "image/png",
      "form_factor": "wide"
    }
  ]
}
```

### 7.2 Service Worker Strategy

```javascript
// public/sw.js (using Workbox patterns)

// Cache strategies:
// 1. App shell (HTML, CSS, JS) → Cache first, update in background
// 2. API responses → Network first, fallback to cache
// 3. Images → Cache first with expiration
// 4. Fonts → Cache first, long expiration

// Offline fallback:
// - Serve cached inventory data
// - Queue mutations for later sync
// - Show offline indicator
```

### 7.3 next.config.js

```javascript
const withPWA = require('next-pwa')({
  dest: 'public',
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === 'development',
})

module.exports = withPWA({
  reactStrictMode: true,
  images: {
    domains: ['images.openfoodfacts.org'],  // Product images
  },
})
```

---

## 8. Styling System

### 8.1 Tailwind Config

```javascript
// tailwind.config.js
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Expiry colors
        'expiry-expired': '#ef4444',   // red-500
        'expiry-urgent': '#f97316',    // orange-500
        'expiry-warning': '#eab308',   // yellow-500
        'expiry-ok': '#22c55e',        // green-500
        
        // Priority colors
        'priority-urgent': '#ef4444',
        'priority-normal': '#3b82f6',
        'priority-low': '#6b7280',
      },
      spacing: {
        // Touch targets
        'touch': '44px',
        'touch-lg': '56px',
      },
      minHeight: {
        'touch': '44px',
        'touch-lg': '56px',
      },
      minWidth: {
        'touch': '44px',
        'touch-lg': '56px',
      },
      fontSize: {
        // Larger for iPad readability
        'ipad-sm': ['16px', '24px'],
        'ipad-base': ['18px', '28px'],
        'ipad-lg': ['20px', '30px'],
      },
    },
  },
  plugins: [],
}
```

### 8.2 CSS Custom Properties

```css
/* globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* Layout */
  --sidebar-width: 240px;
  --action-bar-width: 80px;
  --header-height: 64px;
  
  /* Touch */
  --touch-target: 44px;
  --touch-target-lg: 56px;
  
  /* Animation */
  --transition-fast: 150ms;
  --transition-normal: 300ms;
}

/* Prevent text selection on iPad */
.no-select {
  -webkit-user-select: none;
  user-select: none;
  -webkit-touch-callout: none;
}

/* Prevent pull-to-refresh */
body {
  overscroll-behavior: none;
}

/* Safe area for notched iPads */
.safe-area-inset {
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
}
```

---

## 9. Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Basic app structure and inventory display

**Tasks:**
1. Project setup (Next.js, TypeScript, Tailwind, PWA)
2. API client foundation
3. Type definitions
4. UI components: Button, Card, Badge, ProgressBar
5. AppShell layout
6. Inventory list (static, no mutations)
7. Basic routing

**Deliverable:** Static inventory view with mock data

### Phase 2: Core Interactions (Week 2)
**Goal:** Full inventory CRUD with consumption

**Tasks:**
1. TanStack Query setup
2. Zustand stores
3. InventoryItem compound component
4. ConsumptionSheet
5. ExpiryBadge with calculations
6. CategoryFilter
7. ContextSelector with time-based auto-selection
8. WebSocket connection for real-time updates

**Deliverable:** Working inventory with consumption actions

### Phase 3: Receipt Scanning (Week 3)
**Goal:** Receipt capture and review flow

**Tasks:**
1. CameraCapture component
2. Receipt upload API integration
3. Polling for OCR status
4. ParsedItemList display
5. ItemCorrection modal
6. Confirm and add to inventory

**Deliverable:** Complete receipt scanning flow

### Phase 4: Hardware Scanner (Week 4)
**Goal:** Barcode scanner support

**Tasks:**
1. useScanner hook (keystroke detection)
2. ScannerModeSelector
3. ScanFeedback (visual + audio)
4. Add/Consume/Lookup modes
5. Product lookup by barcode

**Deliverable:** Working hardware scanner integration

### Phase 5: Shopping & Polish (Week 5)
**Goal:** Shopping list and offline support

**Tasks:**
1. Shopping list components
2. Add item modal with search
3. Priority flags
4. Offline queue (IndexedDB)
5. Sync on reconnect
6. Toast notifications
7. Dark mode (optional)

**Deliverable:** Feature-complete MVP

### Phase 6: Testing & Optimization (Week 6)
**Goal:** Production ready

**Tasks:**
1. Component tests (Vitest + Testing Library)
2. E2E tests (Playwright)
3. Performance optimization (React.memo, virtualization)
4. Accessibility audit
5. PWA testing on actual iPad
6. Documentation

**Deliverable:** Production-ready PWA

---

## 10. File Count Estimate

| Directory | Files | Notes |
|-----------|-------|-------|
| `app/` | 6 | Pages + layout |
| `components/ui/` | 8 | Base components |
| `components/inventory/` | 7 | Inventory feature |
| `components/receipt/` | 6 | Receipt feature |
| `components/shopping/` | 5 | Shopping feature |
| `components/scanner/` | 4 | Scanner feature |
| `components/layout/` | 7 | Layout components |
| `hooks/` | 8 | Custom hooks |
| `stores/` | 4 | Zustand stores |
| `lib/api/` | 6 | API client |
| `lib/` | 5 | Utilities |
| `types/` | 6 | TypeScript types |
| **Total** | **~72** | Excluding configs |

---

## 11. Dependencies

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
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0",
    "idb": "^8.0.0",
    "@tanstack/react-virtual": "^3.0.0",
    "react-hook-form": "^7.48.0",
    "zod": "^3.22.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "@types/react": "^18.2.0",
    "@types/node": "^20.0.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "next-pwa": "^5.6.0",
    "vitest": "^1.0.0",
    "@testing-library/react": "^14.0.0",
    "@playwright/test": "^1.40.0"
  }
}
```

---

## 12. Open Questions / Decisions Needed

1. **Image handling:** Should we use next/image with remote images from Open Food Facts, or proxy through our backend?

2. **Virtualization:** Use @tanstack/react-virtual for inventory list, or only enable when >100 items?

3. **Camera library:** Native HTML5 getUserMedia or a library like react-webcam?

4. **Animation:** Add subtle animations (Framer Motion) or keep it minimal for performance?

5. **Error boundaries:** Per-page or per-feature error boundaries?

6. **i18n:** Support Finnish/Swedish/English now, or English-only MVP?

---

## Next Steps

1. Review and approve this plan
2. Set up project skeleton
3. Implement Phase 1 foundation
4. Iterate based on real device testing
