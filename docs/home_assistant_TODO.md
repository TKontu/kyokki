# Home Assistant Integration — Development TODO

**Spec:** [HOME_ASSISTANT_SPEC.md](./HOME_ASSISTANT_SPEC.md)

---

## Phase 1: REST API Endpoints

### Backend Tasks

**New route file:** `app/api/routes/home_assistant.py`

- [ ] `GET /api/ha/status` — Aggregated status endpoint
  ```python
  @router.get("/ha/status")
  async def ha_status(db: AsyncSession = Depends(get_db)):
      # Single query-optimized endpoint for HA REST sensors
      return {
          "inventory": {
              "total_items": await count_inventory(db),
              "expiring_today": await count_expiring(db, days=0),
              "expiring_tomorrow": await count_expiring(db, days=1),
              "expiring_this_week": await count_expiring(db, days=7),
              "expired": await count_expired(db),
              "low_stock": await count_low_stock(db),
          },
          "alerts": {
              "has_expired": expired > 0,
              "has_expiring_today": expiring_today > 0,
              "needs_shopping": low_stock > 0,
          },
          "last_updated": datetime.utcnow().isoformat(),
      }
  ```

- [ ] `GET /api/ha/expiring` — List expiring items
  - Query params: `days` (default 3), `limit` (default 10)
  - Returns item name, category, expiry date, days until expiry

- [ ] `GET /api/ha/low-stock` — List low stock items
  - Returns item name, category, quantity percent, shopping list status

- [ ] `POST /api/ha/consume` — Consume item (voice assistant)
  - Accept by `item_id` OR `name` (fuzzy match)
  - Amount: `quarter`, `half`, `three_quarters`, `all`
  - Return success + before/after quantities

- [ ] `POST /api/ha/shopping/add` — Add to shopping list
  - Accept item name, priority
  - Fuzzy match to existing products

### Service Layer

- [ ] `ha_service.py` — HA-specific business logic
  - `get_aggregated_status()` — Optimized single-query stats
  - `consume_by_name(name, amount)` — Fuzzy match + consume
  - `get_expiring_items(days, limit)` — Formatted for HA

### Optional: Authentication

- [ ] Config option: `HA_API_KEY`
- [ ] Middleware to check `Authorization: Bearer {key}` header
- [ ] Skip auth if key not configured (local network trust)

---

## Phase 1: Documentation

- [ ] Add HA configuration examples to README
- [ ] Document all `/api/ha/*` endpoints
- [ ] Example automations in docs/
- [ ] Dashboard card YAML examples

---

## Phase 3: HACS Custom Integration

### Repository Structure

```
kyokki-ha/
├── custom_components/
│   └── kyokki/
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── services.yaml
│       └── strings.json
├── hacs.json
└── README.md
```

### Tasks

**Setup**
- [ ] Create separate repository for HA integration
- [ ] `manifest.json` with requirements, version, dependencies
- [ ] `hacs.json` for HACS compatibility

**Config Flow**
- [ ] `config_flow.py` — UI-based configuration
  - Step 1: Enter Kyokki URL
  - Step 2: Optional API key
  - Validation: Test connection to `/api/ha/status`

**Data Coordinator**
- [ ] `coordinator.py` — DataUpdateCoordinator pattern
  - Fetch `/api/ha/status` every 5 minutes
  - Handle connection errors gracefully
  - Expose data to sensors

**Sensors**
- [ ] `sensor.py` — Numeric sensors
  - `kyokki_total_items`
  - `kyokki_expiring_today`
  - `kyokki_expiring_week`
  - `kyokki_expired`
  - `kyokki_low_stock`

**Binary Sensors**
- [ ] `binary_sensor.py` — Alert states
  - `kyokki_has_expired` (device_class: problem)
  - `kyokki_has_expiring` (device_class: problem)
  - `kyokki_needs_shopping`

**Services**
- [ ] `services.yaml` — Service definitions
- [ ] Service handlers in `__init__.py`
  - `kyokki.consume` — POST to `/api/ha/consume`
  - `kyokki.add_to_shopping` — POST to `/api/ha/shopping/add`
  - `kyokki.refresh` — Force coordinator update

**Device**
- [ ] Register as single device "Kyokki"
- [ ] Device info: name, manufacturer, model, sw_version

**Translations**
- [ ] `strings.json` — English
- [ ] `translations/en.json`

---

## Testing

### Phase 1 Tests
- [ ] Test `/api/ha/status` returns expected format
- [ ] Test `/api/ha/consume` with name fuzzy matching
- [ ] Test auth header when `HA_API_KEY` configured
- [ ] Test HA REST sensor config actually works

### Phase 3 Tests
- [ ] Config flow validation tests
- [ ] Coordinator update tests
- [ ] Service call tests

---

## Example HA Configs to Include in Docs

### Minimal Setup
```yaml
rest:
  - resource: http://kyokki.local/api/ha/status
    scan_interval: 300
    sensor:
      - name: "Fridge Expiring Today"
        value_template: "{{ value_json.inventory.expiring_today }}"
```

### Full Setup
```yaml
rest:
  - resource: http://kyokki.local/api/ha/status
    scan_interval: 300
    sensor:
      - name: "Fridge Total Items"
        value_template: "{{ value_json.inventory.total_items }}"
        icon: mdi:fridge
      - name: "Fridge Expiring Today"
        value_template: "{{ value_json.inventory.expiring_today }}"
        icon: mdi:clock-alert
      - name: "Fridge Expiring This Week"
        value_template: "{{ value_json.inventory.expiring_this_week }}"
        icon: mdi:calendar-week
      - name: "Fridge Low Stock"
        value_template: "{{ value_json.inventory.low_stock }}"
        icon: mdi:cart-arrow-down
    binary_sensor:
      - name: "Fridge Has Expiring Today"
        value_template: "{{ value_json.alerts.has_expiring_today }}"
        device_class: problem

rest_command:
  fridge_consume:
    url: http://kyokki.local/api/ha/consume
    method: POST
    content_type: application/json
    payload: '{"name": "{{ name }}", "amount": "{{ amount | default(''quarter'') }}"}'
```

### Automation: Morning Alert
```yaml
automation:
  - alias: "Fridge Morning Alert"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.fridge_expiring_today
        above: 0
    action:
      - service: notify.mobile_app
        data:
          title: "🥛 Food Expiring"
          message: "{{ states('sensor.fridge_expiring_today') }} items expiring today"
```

---

## Environment Variables

```env
# Optional — if not set, no auth required
HA_API_KEY=your-secret-key

# For future: callback to HA for events
HA_WEBHOOK_URL=http://homeassistant.local:8123/api/webhook/kyokki
HA_WEBHOOK_SECRET=webhook-secret
```

---

## Priority

| Task | Priority | Phase |
|------|----------|-------|
| `/api/ha/status` endpoint | High | 1 |
| `/api/ha/consume` endpoint | Medium | 1 |
| Documentation + examples | Medium | 1 |
| HACS integration | Low | 3 |

Phase 1 REST endpoints let users integrate immediately. HACS integration is polish for better UX.
