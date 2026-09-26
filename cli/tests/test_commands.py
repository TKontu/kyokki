"""Every command: the request it makes and what it prints."""

import json

from conftest import ITEM_ID, PRODUCT_ID, TOKEN, URL, FakeApi, Runner

STOCK_ROW = {
    "product_id": PRODUCT_ID,
    "product_name": "Milk",
    "category": "dairy",
    "category_icon": "🥛",
    "unit": "dl",
    "total": 15.0,
    "item_count": 2,
    "earliest_expiry": "2026-09-28",
    "locations": {"main_fridge": 15.0},
    "expiring": True,
}

ITEM = {
    "id": ITEM_ID,
    "product_id": PRODUCT_ID,
    "product_name": "Milk",
    "initial_quantity": 10.0,
    "current_quantity": 10.0,
    "unit": "dl",
    "status": "sealed",
    "location": "main_fridge",
    "purchase_date": "2026-09-26",
    "expiry_date": "2026-10-03",
    "category": "dairy",
    "category_name": "Dairy",
    "category_icon": "🥛",
    "created_at": "2026-09-26T10:00:00Z",
}

CONSUMED = {
    "product_id": PRODUCT_ID,
    "product_name": "Milk",
    "requested": {"amount": 2.0, "unit": "dl"},
    "consumed": [
        {
            "item_id": ITEM_ID,
            "amount": 2.0,
            "unit": "dl",
            "remaining": 8.0,
            "status": "opened",
        }
    ],
    "remaining_total": 13.0,
    "unit": "dl",
    "dry_run": False,
}


# --- doctor -----------------------------------------------------------------


def whoami(api: FakeApi) -> None:
    api.on("GET", "/api/health/live", body={"status": "ok"})
    api.on(
        "GET",
        "/api/whoami",
        body={"name": "hermes", "scopes": ["read", "write"], "auth_enabled": True},
    )


def test_doctor_checks_liveness_then_whoami(api: FakeApi, run: Runner) -> None:
    whoami(api)
    result = run("doctor")
    assert result.code == 0
    assert [r.url.path for r in api.requests] == ["/api/health/live", "/api/whoami"]
    assert api.last.headers["Authorization"] == f"Bearer {TOKEN}"
    body = result.json()
    assert body == {
        "url": URL,
        "reachable": True,
        "name": "hermes",
        "scopes": ["read", "write"],
        "auth_enabled": True,
    }


def test_doctor_human(api: FakeApi, run: Runner, tty: None) -> None:
    whoami(api)
    result = run("doctor")
    assert result.code == 0
    assert "reachable" in result.out
    assert "hermes" in result.out
    assert "read, write" in result.out
    assert "auth: on" in result.out


def test_doctor_unreachable_is_1(api: FakeApi, run: Runner) -> None:
    api.down = True
    result = run("doctor")
    assert result.code == 1
    assert "cannot reach" in (result.out + result.err)


def test_doctor_liveness_failing_is_1(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/health/live", 503, {"detail": "down"})
    assert run("doctor").code == 1


def test_doctor_auth_failure_is_7(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/health/live", body={"status": "ok"})
    api.error("GET", "/api/whoami", 401, {"code": "auth", "message": "Unknown token"})
    result = run("doctor")
    assert result.code == 7
    assert result.json() == {"code": "auth", "message": "Unknown token"}


# --- stock list ---------------------------------------------------------------


def test_stock_list_sends_filters(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/stock", body=[STOCK_ROW])
    result = run(
        "stock",
        "list",
        "--q",
        "milk",
        "--location",
        "main_fridge",
        "--expiring",
        "3",
        "--category",
        "dairy",
    )
    assert result.code == 0
    request = api.last
    assert request.method == "GET"
    assert dict(request.url.params) == {
        "q": "milk",
        "location": "main_fridge",
        "expiring_days": "3",
        "category": "dairy",
    }
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Idempotency-Key" not in request.headers
    assert result.json() == [STOCK_ROW]


def test_stock_list_without_filters_sends_no_query(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/stock", body=[])
    assert run("stock", "list").code == 0
    assert api.last.url.query == b""


def test_stock_list_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", "/api/stock", body=[STOCK_ROW])
    result = run("stock", "list")
    assert result.code == 0
    lines = result.out.splitlines()
    assert "PRODUCT" in lines[0]
    assert "Milk" in lines[1] and "15" in lines[1] and "dl" in lines[1]
    assert "2026-09-28" in lines[1] and "main_fridge" in lines[1]


def test_stock_list_human_empty(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", "/api/stock", body=[])
    result = run("stock", "list")
    assert result.code == 0
    assert "No stock" in result.out


def test_stock_list_rejects_bad_location(api: FakeApi, run: Runner) -> None:
    result = run("stock", "list", "--location", "garage")
    assert result.code == 2
    assert api.requests == []


# --- stock add ----------------------------------------------------------------


def test_stock_add_by_name(api: FakeApi, run: Runner) -> None:
    api.on(
        "POST",
        "/api/stock/add",
        201,
        {"item": ITEM, "product_created": True},
    )
    result = run(
        "stock",
        "add",
        "Milk",
        "1.5",
        "l",
        "--category",
        "dairy",
        "--location",
        "main_fridge",
        "--expiry",
        "2026-10-03",
        "--purchased",
        "2026-09-26",
    )
    assert result.code == 0
    assert api.last.method == "POST"
    assert api.last_json() == {
        "name": "Milk",
        "quantity": 1.5,
        "unit": "l",
        "category": "dairy",
        "location": "main_fridge",
        "expiry_date": "2026-10-03",
        "purchase_date": "2026-09-26",
    }
    assert len(api.last.headers["Idempotency-Key"]) == 64
    assert result.json() == {"item": ITEM, "product_created": True}


def test_stock_add_minimal_by_id(api: FakeApi, run: Runner) -> None:
    api.on("POST", "/api/stock/add", 201, {"item": ITEM, "product_created": False})
    assert run("stock", "add", PRODUCT_ID, "2").code == 0
    assert api.last_json() == {"product_id": PRODUCT_ID, "quantity": 2}


def test_stock_add_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("POST", "/api/stock/add", 201, {"item": ITEM, "product_created": True})
    result = run("stock", "add", "Milk", "10", "dl", "--category", "dairy")
    assert result.code == 0
    assert "Added 10 dl Milk" in result.out
    assert "new product" in result.out
    assert "2026-10-03" in result.out


def test_stock_add_explicit_idempotency_key(api: FakeApi, run: Runner) -> None:
    api.on("POST", "/api/stock/add", 201, {"item": ITEM, "product_created": False})
    run("stock", "add", "Milk", "1", "--idempotency-key", "my-key-1")
    assert api.last.headers["Idempotency-Key"] == "my-key-1"


def test_stock_add_rejects_bad_quantity_and_date(api: FakeApi, run: Runner) -> None:
    assert run("stock", "add", "Milk", "zero").code == 2
    assert run("stock", "add", "Milk", "0").code == 2
    assert run("stock", "add", "Milk", "-1").code == 2
    assert run("stock", "add", "Milk", "1", "--expiry", "3.10.2026").code == 2
    assert api.requests == []


# --- stock consume ------------------------------------------------------------


def test_stock_consume_by_name(api: FakeApi, run: Runner) -> None:
    api.on("POST", "/api/stock/consume", body=CONSUMED)
    result = run(
        "stock",
        "consume",
        "Milk",
        "2",
        "dl",
        "--location",
        "main_fridge",
        "--allow-partial",
    )
    assert result.code == 0
    assert api.last_json() == {
        "product": "Milk",
        "amount": 2,
        "unit": "dl",
        "location": "main_fridge",
        "allow_partial": True,
        "dry_run": False,
    }
    assert "Idempotency-Key" in api.last.headers
    assert result.json() == CONSUMED


def test_stock_consume_by_id(api: FakeApi, run: Runner) -> None:
    api.on("POST", "/api/stock/consume", body=CONSUMED)
    assert run("stock", "consume", PRODUCT_ID.upper(), "0.5", "dl").code == 0
    body = api.last_json()
    assert body["product_id"] == PRODUCT_ID.upper()
    assert "product" not in body
    assert body["amount"] == 0.5


def test_stock_consume_dry_run_sends_no_key(api: FakeApi, run: Runner) -> None:
    api.on("POST", "/api/stock/consume", body={**CONSUMED, "dry_run": True})
    result = run(
        "stock", "consume", "Milk", "2", "dl", "--dry-run", "--idempotency-key", "k"
    )
    assert result.code == 0
    assert api.last_json()["dry_run"] is True
    assert "Idempotency-Key" not in api.last.headers


def test_stock_consume_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("POST", "/api/stock/consume", body=CONSUMED)
    result = run("stock", "consume", "Milk", "2", "dl")
    assert result.code == 0
    assert "Consumed 2 dl of Milk" in result.out
    assert "13 dl left" in result.out


def test_stock_consume_human_dry_run(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("POST", "/api/stock/consume", body={**CONSUMED, "dry_run": True})
    result = run("stock", "consume", "Milk", "2", "dl", "--dry-run")
    assert "Would consume 2 dl of Milk" in result.out


def test_stock_consume_needs_a_unit(api: FakeApi, run: Runner) -> None:
    assert run("stock", "consume", "Milk", "2").code == 2
    assert api.requests == []


def test_replayed_answer_is_noted(api: FakeApi, run: Runner, tty: None) -> None:
    api.on(
        "POST",
        "/api/stock/consume",
        body=CONSUMED,
        headers={"Idempotent-Replayed": "true"},
    )
    result = run("stock", "consume", "Milk", "2", "dl")
    assert result.code == 0
    assert "replayed" in result.err


# --- product ------------------------------------------------------------------


def test_product_resolve(api: FakeApi, run: Runner) -> None:
    body = {
        "match": {"product_id": PRODUCT_ID, "name": "milk", "source": "canonical"},
        "candidates": [],
        "suggestion": None,
    }
    api.on("GET", "/api/products/resolve", body=body)
    result = run("product", "resolve", "Milk")
    assert result.code == 0
    assert dict(api.last.url.params) == {"name": "Milk"}
    assert result.json() == body


def test_product_resolve_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on(
        "GET",
        "/api/products/resolve",
        body={
            "match": None,
            "candidates": [
                {
                    "product_id": PRODUCT_ID,
                    "name": "milk",
                    "score": 0.62,
                    "source": "canonical",
                }
            ],
            "suggestion": "maito",
        },
    )
    result = run("product", "resolve", "maito")
    assert result.code == 0
    assert "No match" in result.out
    assert "milk" in result.out and "0.62" in result.out and PRODUCT_ID in result.out
    assert "maito" in result.out


def test_product_name_add(api: FakeApi, run: Runner) -> None:
    entry = {"id": ITEM_ID, "name": "maito", "source": "cook", "removable": True}
    api.on("POST", f"/api/products/{PRODUCT_ID}/names", 201, entry)
    result = run("product", "name", "add", PRODUCT_ID, "Maito")
    assert result.code == 0
    assert api.last_json() == {"name": "Maito"}
    assert "Idempotency-Key" in api.last.headers
    assert result.json() == entry


def test_product_name_add_human(api: FakeApi, run: Runner, tty: None) -> None:
    entry = {"id": ITEM_ID, "name": "maito", "source": "cook", "removable": True}
    api.on("POST", f"/api/products/{PRODUCT_ID}/names", 201, entry)
    assert "Learned" in run("product", "name", "add", PRODUCT_ID, "Maito").out
    api.on("POST", f"/api/products/{PRODUCT_ID}/names", 200, entry)
    assert "Already" in run("product", "name", "add", PRODUCT_ID, "Maito").out


def test_product_name_add_needs_a_uuid(api: FakeApi, run: Runner) -> None:
    assert run("product", "name", "add", "milk", "maito").code == 2
    assert api.requests == []


# --- category -----------------------------------------------------------------

CATEGORIES = [
    {"id": "dairy", "display_name": "Dairy", "icon": "🥛"},
    {"id": "meat", "display_name": "Meat", "icon": None},
]


def test_category_list(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/categories", body=CATEGORIES)
    result = run("category", "list")
    assert result.code == 0
    assert result.json() == CATEGORIES


def test_category_list_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", "/api/categories", body=CATEGORIES)
    lines = run("category", "list").out.splitlines()
    assert any("dairy" in line and "Dairy" in line for line in lines)
    assert any("meat" in line and "Meat" in line for line in lines)


# --- configuration ------------------------------------------------------------


def test_flags_override_environment(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/categories", body=[])
    run("--url", "http://other:9000/", "--token", "other-token", "category", "list")
    assert str(api.last.url) == "http://other:9000/api/categories"
    assert api.last.headers["Authorization"] == "Bearer other-token"


def test_global_options_work_after_the_command(api: FakeApi, run: Runner) -> None:
    api.on("GET", "/api/categories", body=[])
    run("category", "list", "--url", "http://other:9000", "--json")
    assert api.last.url.host == "other"


def test_missing_url_is_usage_error(
    api: FakeApi, run: Runner, monkeypatch: object
) -> None:
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.delenv("KYOKKI_URL")
    result = run("stock", "list")
    assert result.code == 2
    assert "KYOKKI_URL" in result.err
    assert api.requests == []


def test_no_token_sends_no_authorization(
    api: FakeApi, run: Runner, monkeypatch: object
) -> None:
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.delenv("KYOKKI_TOKEN")
    api.on("GET", "/api/categories", body=[])
    assert run("category", "list").code == 0
    assert "Authorization" not in api.last.headers


def test_json_flag_on_a_tty(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", "/api/categories", body=CATEGORIES)
    result = run("--json", "category", "list")
    assert json.loads(result.out) == CATEGORIES


def test_no_command_prints_help_and_is_usage(run: Runner) -> None:
    result = run()
    assert result.code == 2
    assert "usage: kyokki" in result.out + result.err
