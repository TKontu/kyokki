# Home Assistant: REST API (Phase 1)

What shipped for `docs/HOME_ASSISTANT_SPEC.md`'s Phase 1: five endpoints under `/api/ha/*`,
behind the same bearer auth as the rest of `/api` (`backend/app/api/auth.py`, AG1). A token
with `read` scope covers the three `GET`s; `consume` and `shopping/add` need `write`.

## Endpoints

| Method | Path                     | Notes |
| ------ | ------------------------ | ----- |
| GET    | `/api/ha/status`         | `total_items`, `expiring_within_3_days`, `expired`, `by_location`, `last_updated` |
| GET    | `/api/ha/expiring`       | `?days=N` (default 3), `?limit=N` (default 10) |
| GET    | `/api/ha/low-stock`      | Read-only; never writes to the shopping list |
| POST   | `/api/ha/consume`        | `{"name", "amount", "unit"}` - by product name, like the agent's `stock consume` |
| POST   | `/api/ha/shopping/add`   | `{"name", "amount"?, "unit"?}` - `amount`/`unit` default to 1 pcs |

`consume` and `shopping/add` honour an `Idempotency-Key` header (a retry with the same key
and body replays the first response) and broadcast over the app's usual WebSocket channel.
Errors use the agent API's stable shape: `{"detail": {"code": "...", "message": "..."}}`,
e.g. `ambiguous` (409, with `candidates`) when a name matches more than one product, or
`insufficient_stock` (409) when there isn't enough.

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

    binary_sensor:
      - name: "Fridge Has Expired Items"
        value_template: "{{ value_json.expired | int > 0 }}"
        device_class: problem
```

```yaml
# secrets.yaml
kyokki_ha_token: "Bearer your-token-secret-here"
```

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
    payload: '{"name": "{{ name }}"}'
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
