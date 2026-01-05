# Home Assistant Integration Specification

## Overview

Fridge Logger integrates with Home Assistant to enable smart home automations around food inventory. Users can receive expiry notifications, trigger voice commands, display inventory status on dashboards, and build custom automations.

## Integration Approaches

### Phase 1: REST API Endpoints
HA's built-in REST sensor platform consumes our API directly. No custom code needed on HA side — users just add YAML configuration.

### Phase 3: HACS Custom Integration
Native HA integration distributed via HACS. Provides config flow UI, proper device/entity model, and services for automations.

---

## Phase 1: REST API for Home Assistant

### Endpoint: `GET /api/ha/status`

Single endpoint optimized for HA REST sensor consumption. Returns all metrics in one call (HA REST platform works best with single-resource, multiple-sensor pattern).

**Response:**
```json
{
  "inventory": {
    "total_items": 47,
    "expiring_today": 2,
    "expiring_tomorrow": 3,
    "expiring_this_week": 8,
    "expired": 1,
    "low_stock": 4
  },
  "categories": {
    "dairy": 12,
    "produce": 8,
    "meat": 5,
    "frozen": 10,
    "pantry": 12
  },
  "alerts": {
    "has_expired": true,
    "has_expiring_today": true,
    "needs_shopping": true
  },
  "last_updated": "2026-01-05T10:30:00Z"
}
```

### Endpoint: `GET /api/ha/expiring`

List of items expiring soon (for detailed notifications).

**Query params:**
- `days` — Items expiring within N days (default: 3)
- `limit` — Max items to return (default: 10)

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Milk",
      "category": "dairy",
      "expiry_date": "2026-01-05",
      "days_until_expiry": 0,
      "quantity_percent": 40
    },
    {
      "id": "uuid",
      "name": "Chicken breast",
      "category": "meat",
      "expiry_date": "2026-01-06",
      "days_until_expiry": 1,
      "quantity_percent": 100
    }
  ],
  "count": 2
}
```

### Endpoint: `GET /api/ha/low-stock`

Items running low (for shopping reminders).

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Eggs",
      "category": "dairy",
      "quantity_percent": 15,
      "on_shopping_list": false
    }
  ],
  "count": 1
}
```

### Endpoint: `POST /api/ha/consume`

Mark item as consumed (for voice assistant integration).

**Request:**
```json
{
  "item_id": "uuid",
  "amount": "half"  // "quarter", "half", "three_quarters", "all"
}
```

**Alternative — by name (fuzzy match):**
```json
{
  "name": "milk",
  "amount": "quarter"
}
```

**Response:**
```json
{
  "success": true,
  "item": {
    "name": "Milk",
    "quantity_before": 75,
    "quantity_after": 50
  }
}
```

### Endpoint: `POST /api/ha/shopping/add`

Add item to shopping list (for voice assistant).

**Request:**
```json
{
  "name": "milk",
  "priority": "normal"  // "urgent", "normal", "low"
}
```

---

## Home Assistant Configuration Examples

### Basic REST Sensors

```yaml
# configuration.yaml
rest:
  - resource: http://fridge-logger.local/api/ha/status
    scan_interval: 300  # 5 minutes
    sensor:
      - name: "Fridge Total Items"
        value_template: "{{ value_json.inventory.total_items }}"
        unit_of_measurement: "items"
        icon: mdi:fridge
        
      - name: "Fridge Expiring Today"
        value_template: "{{ value_json.inventory.expiring_today }}"
        unit_of_measurement: "items"
        icon: mdi:clock-alert
        
      - name: "Fridge Expiring This Week"
        value_template: "{{ value_json.inventory.expiring_this_week }}"
        unit_of_measurement: "items"
        icon: mdi:calendar-week
        
      - name: "Fridge Expired"
        value_template: "{{ value_json.inventory.expired }}"
        unit_of_measurement: "items"
        icon: mdi:alert-circle
        
      - name: "Fridge Low Stock"
        value_template: "{{ value_json.inventory.low_stock }}"
        unit_of_measurement: "items"
        icon: mdi:cart-arrow-down

    binary_sensor:
      - name: "Fridge Has Expired Items"
        value_template: "{{ value_json.alerts.has_expired }}"
        device_class: problem
        
      - name: "Fridge Has Expiring Today"
        value_template: "{{ value_json.alerts.has_expiring_today }}"
        device_class: problem
        
      - name: "Fridge Needs Shopping"
        value_template: "{{ value_json.alerts.needs_shopping }}"
        icon: mdi:cart
```

### REST Commands for Actions

```yaml
# configuration.yaml
rest_command:
  fridge_consume_item:
    url: http://fridge-logger.local/api/ha/consume
    method: POST
    content_type: application/json
    payload: '{"name": "{{ name }}", "amount": "{{ amount }}"}'
    
  fridge_add_to_shopping:
    url: http://fridge-logger.local/api/ha/shopping/add
    method: POST
    content_type: application/json
    payload: '{"name": "{{ name }}", "priority": "{{ priority | default(''normal'') }}"}'
```

---

## Automation Examples

### Expiry Notification

```yaml
automation:
  - alias: "Fridge Expiry Morning Alert"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.fridge_expiring_today
        above: 0
    action:
      - service: notify.mobile_app_phone
        data:
          title: "🥛 Food Expiring Today"
          message: "{{ states('sensor.fridge_expiring_today') }} items expiring today. Check your fridge!"
          data:
            actions:
              - action: URI
                title: "Open Fridge Logger"
                uri: "http://fridge-logger.local"
```

### Voice Assistant Integration

```yaml
# Intent script for "I used the milk"
intent_script:
  UseFridgeItem:
    speech:
      text: "OK, I've marked {{ item }} as {{ amount }} used."
    action:
      - service: rest_command.fridge_consume_item
        data:
          name: "{{ item }}"
          amount: "{{ amount | default('quarter') }}"

# Conversation trigger
conversation:
  intents:
    UseFridgeItem:
      - "I used [the] {item}"
      - "I finished [the] {item}"
      - "mark {item} as {amount} used"
      - "used {amount} of [the] {item}"
```

### TTS Morning Report

```yaml
automation:
  - alias: "Morning Fridge Report"
    trigger:
      - platform: time
        at: "07:30:00"
    condition:
      - condition: state
        entity_id: binary_sensor.someone_home
        state: "on"
    action:
      - service: tts.speak
        target:
          entity_id: tts.google_en
        data:
          media_player_entity_id: media_player.kitchen_speaker
          message: >
            Good morning. 
            {% if states('sensor.fridge_expiring_today') | int > 0 %}
              You have {{ states('sensor.fridge_expiring_today') }} items expiring today.
            {% endif %}
            {% if states('sensor.fridge_low_stock') | int > 0 %}
              {{ states('sensor.fridge_low_stock') }} items are running low.
            {% endif %}
```

### Shopping List Sync

```yaml
automation:
  - alias: "Add Low Stock to Shopping List"
    trigger:
      - platform: state
        entity_id: binary_sensor.fridge_needs_shopping
        to: "on"
    action:
      - service: shopping_list.add_item
        data:
          name: "Check Fridge Logger for low stock items"
```

---

## Phase 3: HACS Custom Integration

### Features

| Feature | Description |
|---------|-------------|
| **Config Flow** | UI-based setup (no YAML required) |
| **Device** | Single "Fridge Logger" device with all entities |
| **Sensors** | Numeric sensors for counts |
| **Binary Sensors** | Alert states |
| **Services** | `fridge_logger.consume`, `fridge_logger.add_to_shopping` |
| **Events** | `fridge_logger_item_expiring`, `fridge_logger_item_consumed` |

### Entity Model

```
Device: Fridge Logger
├── sensor.fridge_logger_total_items
├── sensor.fridge_logger_expiring_today
├── sensor.fridge_logger_expiring_week
├── sensor.fridge_logger_expired
├── sensor.fridge_logger_low_stock
├── binary_sensor.fridge_logger_has_expired
├── binary_sensor.fridge_logger_has_expiring
└── binary_sensor.fridge_logger_needs_shopping
```

### Services

**fridge_logger.consume**
```yaml
service: fridge_logger.consume
data:
  item: "milk"           # Name or ID
  amount: "half"         # quarter, half, three_quarters, all
```

**fridge_logger.add_to_shopping**
```yaml
service: fridge_logger.add_to_shopping
data:
  item: "milk"
  priority: "urgent"     # urgent, normal, low
```

**fridge_logger.refresh**
```yaml
service: fridge_logger.refresh
# Force refresh all sensors
```

### Events

**fridge_logger_item_expiring**
```yaml
event_type: fridge_logger_item_expiring
data:
  item_id: "uuid"
  item_name: "Milk"
  days_until_expiry: 1
```

**fridge_logger_item_low**
```yaml
event_type: fridge_logger_item_low
data:
  item_id: "uuid"
  item_name: "Eggs"
  quantity_percent: 15
```

---

## Security Considerations

### Authentication Options

1. **None (local network only)** — Default for homelab
2. **API Key** — Header-based authentication
3. **HA Long-Lived Token** — If calling back to HA

### Recommended Setup

```yaml
# Fridge Logger .env
HA_API_ENABLED=true
HA_API_KEY=your-secret-key  # Optional

# Home Assistant configuration.yaml
rest:
  - resource: http://fridge-logger.local/api/ha/status
    headers:
      Authorization: "Bearer your-secret-key"
```

---

## Dashboard Card Examples

### Simple Glance Card

```yaml
type: glance
title: Fridge Status
entities:
  - entity: sensor.fridge_total_items
    name: Total
  - entity: sensor.fridge_expiring_today
    name: Today
  - entity: sensor.fridge_expiring_this_week
    name: This Week
  - entity: sensor.fridge_low_stock
    name: Low Stock
```

### Conditional Alert Card

```yaml
type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.fridge_expiring_today
    above: 0
card:
  type: markdown
  content: |
    ## ⚠️ Items Expiring Today
    Check your fridge! {{ states('sensor.fridge_expiring_today') }} items need attention.
```

### Button Card for Quick Actions

```yaml
type: button
name: "Used Some Milk"
icon: mdi:cup
tap_action:
  action: call-service
  service: rest_command.fridge_consume_item
  data:
    name: milk
    amount: quarter
```
