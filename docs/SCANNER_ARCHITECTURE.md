# Barcode Scanner Architecture - Flexible Multi-Device Approach

## Overview

The Kyokki barcode scanning system uses a **backend-centric API** that supports multiple input methods:
- 📱 **iPad PWA** with camera scanning (QuaggaJS/ZXing)
- 🍓 **Raspberry Pi stations** with USB barcode scanners
- ⌨️ **Direct USB** scanners on compatible devices (future)

This architecture provides maximum flexibility - users can start with iPad camera scanning and add dedicated Pi scanning stations as needed.

---

## Architecture Principles

### 1. Backend-Centric Design
All barcode processing happens on the backend. Frontend devices (iPad, Pi) are just input sources.

### 2. Universal API
The same API endpoints serve all input methods - no special handling per device type.

### 3. Stateless Scanning
Each scan is independent. Mode state (add/consume/lookup) is stored in Redis and can be per-station or global.

### 4. Real-Time Feedback
All scanning actions broadcast via WebSocket for instant UI updates across all connected devices.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Input Methods                           │
├─────────────────────────────────────────────────────────────┤
│  📱 iPad PWA          🍓 Pi Station 1      🍓 Pi Station 2   │
│  Camera Scanner      USB Scanner          USB Scanner        │
│  QuaggaJS/ZXing      evdev (Python)       evdev (Python)     │
└─────────────────┬───────────────┬───────────────┬───────────┘
                  │               │               │
                  │  HTTP POST /api/scanner/scan  │
                  │               │               │
                  ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│              Backend Scanner API (FastAPI)                   │
├─────────────────────────────────────────────────────────────┤
│  POST   /api/scanner/scan        Process barcode            │
│  GET    /api/scanner/mode        Get current mode           │
│  POST   /api/scanner/mode        Set mode (add/consume)     │
│  GET    /api/scanner/stations    List active stations       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ├──> OFF Integration (enrich product)
                  ├──> Product CRUD (create if not exists)
                  ├──> Inventory CRUD (add/consume)
                  └──> WebSocket Broadcast (real-time updates)
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    All Connected Devices                     │
│  📱 iPad (shows real-time updates)                           │
│  🍓 Pi Stations (optional LCD feedback)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## API Specification

### POST /api/scanner/scan
Process a scanned barcode and perform the configured action.

**Request:**
```json
{
  "barcode": "5901234123457",
  "mode": "add",  // Optional: add, consume, lookup. Falls back to global/station mode
  "station_id": "kitchen-pi",  // Optional: identifies the scanning station
  "quantity": 1  // Optional: defaults to 1
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "action": "product_created_and_added",
  "product": {
    "id": "uuid",
    "canonical_name": "Valio Whole Milk 1L",
    "category": "dairy",
    "storage_type": "refrigerator"
  },
  "inventory_item": {
    "id": "uuid",
    "initial_quantity": 1000,
    "current_quantity": 1000,
    "unit": "ml"
  },
  "message": "Added Valio Whole Milk 1L to inventory"
}
```

**Response (200 OK - Product Already Exists):**
```json
{
  "success": true,
  "action": "inventory_added",
  "product": {...},
  "inventory_item": {...},
  "message": "Added existing product to inventory"
}
```

**Response (200 OK - Consume Mode):**
```json
{
  "success": true,
  "action": "inventory_consumed",
  "inventory_item": {
    "id": "uuid",
    "current_quantity": 500,
    "status": "partial"
  },
  "message": "Consumed 500ml of Valio Whole Milk 1L"
}
```

**Error Responses:**
- `404` - Product not found in OFF and barcode doesn't match existing product
- `400` - Invalid barcode format or missing required fields
- `503` - OFF API unavailable (will still work if product exists locally)

---

### GET /api/scanner/mode
Get the current scanning mode.

**Query Parameters:**
- `station_id` (optional) - Get mode for specific station

**Response:**
```json
{
  "mode": "add",  // add, consume, lookup
  "station_id": "kitchen-pi",  // null if global
  "is_global": false
}
```

---

### POST /api/scanner/mode
Set the scanning mode.

**Request:**
```json
{
  "mode": "add",  // add, consume, lookup
  "station_id": "kitchen-pi"  // Optional: set per-station, else global
}
```

**Response:**
```json
{
  "success": true,
  "mode": "add",
  "station_id": "kitchen-pi",
  "message": "Scanner mode set to 'add' for station 'kitchen-pi'"
}
```

---

### GET /api/scanner/stations
List all active scanning stations (for monitoring).

**Response:**
```json
{
  "stations": [
    {
      "station_id": "kitchen-pi",
      "mode": "add",
      "last_scan": "2026-01-09T10:30:00Z",
      "scan_count": 42,
      "online": true
    },
    {
      "station_id": "pantry-pi",
      "mode": "consume",
      "last_scan": "2026-01-09T09:15:00Z",
      "scan_count": 18,
      "online": false
    }
  ],
  "total_stations": 2,
  "online_stations": 1
}
```

---

## Workflow Examples

### Example 1: iPad Camera Scan (Add Mode)
```
1. User opens scanner page in iPad PWA
2. Selects "Add to Inventory" mode
3. Points camera at barcode
4. QuaggaJS detects barcode: "5901234123457"
5. Frontend: POST /api/scanner/scan
   {
     "barcode": "5901234123457",
     "mode": "add",
     "station_id": "ipad-main"
   }
6. Backend:
   - Checks if product exists locally
   - Not found → Calls OFF API
   - Creates product: "Valio Whole Milk 1L"
   - Adds to inventory
   - Broadcasts WebSocket update
7. Frontend receives WebSocket update
8. Shows success message: "Added Valio Whole Milk 1L"
```

### Example 2: Raspberry Pi Station Scan (Consume Mode)
```
1. Pi station configured in "consume" mode
2. User scans milk barcode with USB scanner
3. Pi service reads barcode: "5901234123457"
4. Pi: POST /api/scanner/scan
   {
     "barcode": "5901234123457",
     "station_id": "kitchen-pi"
   }
   (mode comes from station config)
5. Backend:
   - Gets mode from Redis: "consume"
   - Finds product in database
   - Finds inventory item
   - Reduces quantity by default unit
   - Broadcasts WebSocket update
6. Pi LCD shows: "Consumed Valio Milk ✓"
7. iPad (in living room) updates inventory list automatically
```

### Example 3: Lookup Mode (Product Info)
```
1. User switches iPad to "Lookup" mode
2. Scans unknown product
3. Backend fetches from OFF
4. Returns product info without modifying inventory
5. User sees: name, category, nutrition, expiry estimate
6. Option to add to inventory if desired
```

---

## Deployment Scenarios

### Scenario 1: iPad Only (Minimal Setup)
**Hardware:** iPad with camera
**Cost:** $0 (use existing device)
**Setup Time:** < 5 minutes

```
User → iPad PWA (camera) → Backend API → Inventory
```

**Pros:**
- No additional hardware
- Works immediately
- Portable

**Cons:**
- Slower than USB scanner
- Requires opening camera each time
- Camera angle can be awkward

---

### Scenario 2: iPad + Single Pi Station (Recommended)
**Hardware:** iPad + Pi 3B+ + USB scanner
**Cost:** ~$50-80
**Setup Time:** 30 minutes

```
Kitchen:  Pi Station (USB scanner) → Backend API
Anywhere: iPad PWA → WebSocket → Live updates
```

**Pros:**
- Fast scanning in kitchen (most common location)
- iPad for browsing/managing
- Both devices stay in sync
- Best of both worlds

**Cons:**
- Requires Pi setup
- One-time hardware cost

---

### Scenario 3: Multiple Pi Stations (Power User)
**Hardware:** iPad + 3× Pi + USB scanners
**Cost:** ~$150-200
**Setup Time:** 1-2 hours

```
Kitchen Pi   → Backend API
Pantry Pi    → Backend API
Garage Pi    → Backend API
iPad PWA     → WebSocket → Live updates
```

**Pros:**
- Instant scanning anywhere in home
- Each station can have different mode
- Central monitoring via iPad
- Professional warehouse-like setup

**Cons:**
- Higher cost
- More setup/maintenance
- Overkill for most users

---

## Raspberry Pi Implementation

### Hardware Requirements
- **Raspberry Pi 3B+** (or newer, 4/5 also work)
- **USB Barcode Scanner** ($20-40)
  - Keyboard wedge mode (simplest)
  - Or serial/HID mode (more control)
- **MicroSD Card** (16GB minimum)
- **Power Supply** (5V 2.5A)
- **Optional:** LCD display for feedback
- **Optional:** Physical button for mode switching (GPIO)

### Software Stack
```python
# /opt/kyokki-scanner/scanner_service.py
import evdev
import requests
import sqlite3
import time
from pathlib import Path

BACKEND_URL = "http://kyokki-api.local:8000"
STATION_ID = "kitchen-pi"
OFFLINE_DB = Path("/opt/kyokki-scanner/offline_queue.db")

def main():
    """Main scanner service loop"""
    device = find_scanner_device()

    while True:
        try:
            barcode = read_barcode(device)
            if barcode:
                process_scan(barcode)
        except Exception as e:
            log_error(e)
            time.sleep(1)

def read_barcode(device):
    """Read from USB HID scanner"""
    barcode = ""
    for event in device.read_loop():
        if event.type == evdev.ecodes.EV_KEY:
            data = evdev.categorize(event)
            if data.keystate == 1:  # Key down
                if data.keycode == 'KEY_ENTER':
                    return barcode
                else:
                    barcode += key_to_char(data.keycode)
    return None

def process_scan(barcode):
    """Send to backend, queue if offline"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/scanner/scan",
            json={"barcode": barcode, "station_id": STATION_ID},
            timeout=5
        )

        if response.ok:
            show_success(response.json()['message'])
            process_offline_queue()  # Sync any queued scans
        else:
            show_error(response.status_code)

    except requests.RequestException:
        # Network down - queue for later
        queue_offline(barcode)
        show_offline_indicator()

def queue_offline(barcode):
    """Store scan in SQLite for later sync"""
    conn = sqlite3.connect(OFFLINE_DB)
    conn.execute(
        "INSERT INTO queue (barcode, scanned_at) VALUES (?, ?)",
        (barcode, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
```

### Systemd Service
```ini
# /etc/systemd/system/kyokki-scanner.service
[Unit]
Description=Kyokki Barcode Scanner Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/kyokki-scanner
ExecStart=/usr/bin/python3 /opt/kyokki-scanner/scanner_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Installation Script
```bash
#!/bin/bash
# install.sh - Raspberry Pi scanner setup

set -e

echo "Installing Kyokki Scanner Service..."

# Install dependencies
sudo apt update
sudo apt install -y python3-pip python3-evdev

# Create service directory
sudo mkdir -p /opt/kyokki-scanner
sudo cp scanner_service.py /opt/kyokki-scanner/
sudo cp requirements.txt /opt/kyokki-scanner/
sudo pip3 install -r /opt/kyokki-scanner/requirements.txt

# Configure station ID
read -p "Enter station ID (e.g., kitchen-pi): " STATION_ID
sed -i "s/STATION_ID = .*/STATION_ID = \"$STATION_ID\"/" /opt/kyokki-scanner/scanner_service.py

# Install systemd service
sudo cp kyokki-scanner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kyokki-scanner
sudo systemctl start kyokki-scanner

echo "Installation complete!"
echo "Service status:"
sudo systemctl status kyokki-scanner
```

---

## WebSocket Messages

### Scanner Action Message
```json
{
  "type": "scanner_action",
  "timestamp": "2026-01-09T10:30:00Z",
  "entity_id": "inventory-item-uuid",
  "data": {
    "action": "inventory_added",
    "barcode": "5901234123457",
    "product_name": "Valio Whole Milk 1L",
    "station_id": "kitchen-pi",
    "mode": "add",
    "quantity": 1000,
    "unit": "ml"
  }
}
```

---

## Redis State Storage

### Mode State Keys
```
scanner:mode:global = "add"              # Global fallback mode
scanner:mode:kitchen-pi = "add"          # Per-station mode
scanner:mode:pantry-pi = "consume"       # Each station can differ
scanner:mode:ipad-main = "lookup"        # iPad can have own mode
```

### Station Tracking Keys
```
scanner:station:kitchen-pi:last_scan = "2026-01-09T10:30:00Z"
scanner:station:kitchen-pi:scan_count = "42"
scanner:station:kitchen-pi:online = "true"
```

**TTL:** Station online status expires after 5 minutes of no scans

---

## Development Roadmap

### Phase 1: Backend Scanner API (2-3 hours) ⭐ START HERE
**Priority:** HIGH - Foundation for all scanning methods

```
1. Create scanner.py endpoint
2. Implement scan processing logic
3. Integrate with OFF enrichment
4. Mode state management (Redis)
5. WebSocket broadcasts
6. Write 15-20 tests
```

**Deliverable:** Working API that accepts barcode scans

---

### Phase 2A: iPad PWA Scanning (1-2 hours)
**Priority:** MEDIUM - Enables immediate use

```
1. Add QuaggaJS or ZXing to frontend
2. Create Scanner page component
3. Mode selector UI
4. Integration with backend API
5. Visual feedback
```

**Deliverable:** iPad can scan with camera

---

### Phase 2B: Raspberry Pi Station (2-3 hours)
**Priority:** MEDIUM - Enhanced experience

```
1. Python scanner service
2. Offline queue implementation
3. Systemd service
4. Installation scripts
5. Optional: LCD feedback
6. Optional: GPIO mode button
```

**Deliverable:** Standalone Pi scanning station

---

## Cost-Benefit Analysis

| Solution | Cost | Setup Time | Scan Speed | Convenience | Recommended For |
|----------|------|------------|------------|-------------|-----------------|
| iPad Camera Only | $0 | 5 min | Slow | Medium | Testing, minimal use |
| iPad + 1 Pi Station | $50-80 | 30 min | Fast | High | Most users ⭐ |
| iPad + Multiple Pi | $150-200 | 1-2 hrs | Very Fast | Very High | Power users |

**Recommendation:** Start with Phase 1 + 2A (iPad camera), add Pi station later if needed.

---

## Next Steps

1. ✅ **Implement Backend Scanner API** (Sprint 1)
   - Foundation for everything
   - Works with curl/Postman for testing
   - ~2-3 hours with TDD

2. **Choose frontend approach:**
   - **Option A:** iPad PWA camera (faster to ship)
   - **Option B:** Pi station first (better UX, requires hardware)
   - **Option C:** Both in parallel (full-stack sprint)

3. **Optional enhancements:**
   - LCD display on Pi
   - GPIO mode switch button
   - Audio feedback (beeps)
   - Multi-station monitoring dashboard

---

**Status:** Architecture documented, ready for implementation

**Recommended Start:** Backend Scanner API (Phase 1)
