# Home Assistant: REST API (Phase 1)

What shipped for `docs/HOME_ASSISTANT_SPEC.md`'s Phase 1: five endpoints under `/api/ha/*`,
behind the same bearer auth as the rest of `/api` (`backend/app/api/auth.py`, AG1). A token
with `read` scope covers the three `GET`s; `consume` and `shopping/add` need `write`.

## Endpoints

| Method | Path                     | Notes |
| ------ | ------------------------ | ----- |
| GET    | `/api/ha/status`         | `total_items`, `expiring_within_3_days`, `expired`, `by_location`, `last_updated` |
| GET    | `/api/ha/expiring`       | `?days=N` (default 3), `?limit=N` (default 10); each item carries its own `expired` flag |
| GET    | `/api/ha/low-stock`      | Read-only; never writes to the shopping list |
| GET    | `/api/ha/runout`         | `?within_days=N`; when each product will run out, soonest first. Read-only |
| POST   | `/api/ha/consume`        | `{"name", "amount", "unit"}` - by product name, like the agent's `stock consume` |
| POST   | `/api/ha/shopping/add`   | `{"name", "amount"?, "unit"?, "priority"?}` - `amount`/`unit` default to 1 pcs, `priority` to `normal` |

`consume` and `shopping/add` honour an `Idempotency-Key` header (a retry with the same key
and body replays the first response) and broadcast over the app's usual WebSocket channel.
Errors use the agent API's stable shape: `{"detail": {"code": "...", "message": "..."}}`,
e.g. `ambiguous` (409, with `candidates`) when a name matches more than one product, or
`insufficient_stock` (409) when there isn't enough.

`consume` writes the stock change and remembers the `Idempotency-Key` response in two
separate commits (so the remembered body can be HA's own shape rather than the agent
API's); a crash between them means a client retry after the crash could consume twice.
This is the same accepted tradeoff `POST /api/stock/add` already lives with, not a new
risk `/api/ha/*` introduces.

## Home Assistant configuration

Set `HA_API_TOKEN` to a token configured in Kyokki's `KYOKKI_API_TOKENS` (`write` scope, so
it covers both the sensors and the actions below), and put the real secret in HA's own
`secrets.yaml` rather than inline.

```yaml
# configuration.yaml
rest:
  - resource: http://kyokki.local/api/ha/status
    scan_interval: 300  # 5 minutes
    headers:
      Authorization: !secret kyokki_ha_token  # "Bearer <token>"
    sensor:
      - name: "Fridge Total Items"
        value_template: "{{ value_json.total_items }}"
        unit_of_measurement: "items"
        icon: mdi:fridge

      - name: "Fridge Expiring Within 3 Days"
        value_template: "{{ value_json.expiring_within_3_days }}"
        unit_of_measurement: "items"
        icon: mdi:clock-alert

      - name: "Fridge Expired"
        value_template: "{{ value_json.expired }}"
        unit_of_measurement: "items"
        icon: mdi:alert-circle
        # by_location is a dict, e.g. {"main_fridge": 30, "freezer": 10, "pantry": 7}
        json_attributes_template: "{{ value_json.by_location | tojson }}"

    binary_sensor:
      - name: "Fridge Has Expired Items"
        value_template: "{{ value_json.expired | int > 0 }}"
        device_class: problem
```

```yaml
# secrets.yaml
kyokki_ha_token: "Bearer your-token-secret-here"
```

### Low-stock sensor

```yaml
# configuration.yaml
rest:
  - resource: http://kyokki.local/api/ha/low-stock
    scan_interval: 900  # 15 minutes
    headers:
      Authorization: !secret kyokki_ha_token
    sensor:
      - name: "Fridge Low Stock"
        value_template: "{{ value_json.count }}"
        unit_of_measurement: "items"
        icon: mdi:cart-arrow-down
        json_attributes_template: "{{ value_json.items | tojson }}"
```

`sensor.fridge_low_stock`'s own attributes then carry the full list (name, category,
`quantity_percent`, `on_shopping_list`), readable in a template as
`state_attr('sensor.fridge_low_stock', 'items')`.

### Run-out sensor

A daily use rate from the last 60 days of `consumption_log` (no seasonality -
`backend/app/services/runout.py`), filtered to what runs out soon:

```yaml
# configuration.yaml
rest:
  - resource: http://kyokki.local/api/ha/runout?within_days=7
    scan_interval: 1800  # 30 minutes
    headers:
      Authorization: !secret kyokki_ha_token
    sensor:
      - name: "Fridge Running Out Soon"
        value_template: "{{ value_json.count }}"
        unit_of_measurement: "items"
        icon: mdi:timer-sand
        json_attributes_template: "{{ value_json.items | tojson }}"
```

`sensor.fridge_running_out_soon`'s attributes carry the list (`name`, `unit`,
`days_left`, `runs_out_on`, `status`); a product with too little history reports
`insufficient_history` with `days_left` null, and one already gone reports `out` with
`days_left` 0.

### REST commands for actions

```yaml
# configuration.yaml
rest_command:
  fridge_consume_item:
    url: http://kyokki.local/api/ha/consume
    method: POST
    headers:
      Authorization: !secret kyokki_ha_token
    content_type: application/json
    payload: '{"name": "{{ name }}", "amount": {{ amount }}, "unit": "{{ unit }}"}'

  fridge_add_to_shopping:
    url: http://kyokki.local/api/ha/shopping/add
    method: POST
    headers:
      Authorization: !secret kyokki_ha_token
    content_type: application/json
    payload: '{"name": "{{ name }}", "priority": "{{ priority | default(''normal'') }}"}'
```

```yaml
# Intent script for "I used two decilitres of milk"
intent_script:
  UseFridgeItem:
    speech:
      text: "OK, I've marked {{ amount }} {{ unit }} of {{ item }} as used."
    action:
      - service: rest_command.fridge_consume_item
        data:
          name: "{{ item }}"
          amount: "{{ amount }}"
          unit: "{{ unit }}"
```

An ambiguous name (`rest_command`'s response has a 409 and a `candidates` list) is a
response HA can branch on with a `response_variable`; the original spec's "milk" vs.
"oat milk" example is exactly this case.

See `docs/HOME_ASSISTANT_SPEC.md` for the full JSON shapes, the dashboard and automation
examples that still apply unchanged, and Phase 3 (a HACS custom integration, not built yet).
