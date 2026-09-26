"""kyokki shopping: the requests each command makes, what it prints, and its exit codes."""

import shlex
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from conftest import ITEM_ID, PRODUCT_ID, TOKEN, FakeApi, Runner

from kyokki import idempotency

LIST_PATH = "/api/shopping/"
PURCHASE_PATH = f"/api/shopping/{ITEM_ID}/purchase"
ITEM_PATH = f"/api/shopping/{ITEM_ID}"
GENERATE_PATH = "/api/shopping/generate"
EXPORT_PATH = "/api/shopping/export"

SHOPPING_ITEM = {
    "id": ITEM_ID,
    "product_master_id": PRODUCT_ID,
    "name": "Milk",
    "quantity": 10.0,
    "unit": "dl",
    "priority": "urgent",
    "source": "manual",
    "is_purchased": False,
    "added_at": "2026-09-26T10:00:00Z",
    "purchased_at": None,
}

OTHER_ID = "11111111-2222-4333-8444-555555555555"

GENERATED = {
    "added": [
        {
            "product_id": PRODUCT_ID,
            "name": "milk",
            "need": 10.0,
            "unit": "dl",
            "on_hand": 2.0,
            "min_stock": 5.0,
            "item_id": ITEM_ID,
            "reason": None,
        }
    ],
    "updated": [
        {
            "product_id": OTHER_ID,
            "name": "eggs",
            "need": 12.0,
            "unit": "pcs",
            "on_hand": 0.0,
            "min_stock": 6.0,
            "item_id": OTHER_ID,
            "reason": None,
        }
    ],
    "unchanged": [
        {
            "product_id": OTHER_ID,
            "name": "butter",
            "need": 500.0,
            "unit": "g",
            "on_hand": 100.0,
            "min_stock": 250.0,
            "item_id": OTHER_ID,
            "reason": None,
        }
    ],
    "skipped": [
        {
            "product_id": OTHER_ID,
            "name": "flour",
            "need": None,
            "unit": "g",
            "on_hand": None,
            "min_stock": 1000.0,
            "item_id": None,
            "reason": "an item is in pcs, which cannot be counted in g",
        }
    ],
    "dry_run": False,
}

EXPORT_TEXT = "- Milk 10 dl\n- eggs 12 pcs\n"
EXPORT_MARKDOWN = "- [ ] Milk (10 dl)\n- [ ] eggs (12 pcs)\n"


def text_answer(body: str, media_type: str) -> httpx.Response:
    return httpx.Response(
        200, content=body.encode("utf-8"), headers={"Content-Type": media_type}
    )


def _times_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


# --- shopping list --------------------------------------------------------------


def test_list_asks_for_open_items(api: FakeApi, run: Runner) -> None:
    api.on("GET", LIST_PATH, body=[SHOPPING_ITEM])
    result = run("shopping", "list")
    assert result.code == 0
    assert api.last.method == "GET"
    assert api.last.url.path == LIST_PATH
    assert dict(api.last.url.params) == {}
    assert api.last.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Idempotency-Key" not in api.last.headers
    assert result.json() == [SHOPPING_ITEM]


def test_list_all_and_priority(api: FakeApi, run: Runner) -> None:
    api.on("GET", LIST_PATH, body=[])
    assert run("shopping", "list", "--all", "--priority", "urgent").code == 0
    assert dict(api.last.url.params) == {
        "include_purchased": "true",
        "priority": "urgent",
    }


def test_list_rejects_an_unknown_priority(api: FakeApi, run: Runner) -> None:
    result = run("shopping", "list", "--priority", "someday")
    assert result.code == 2
    assert result.json()["code"] == "usage"
    assert api.requests == []


def test_list_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", LIST_PATH, body=[SHOPPING_ITEM])
    result = run("shopping", "list")
    assert result.code == 0
    lines = result.out.splitlines()
    assert "NAME" in lines[0] and "PRIORITY" in lines[0] and "ID" in lines[0]
    assert "Milk" in lines[1] and "10" in lines[1] and "dl" in lines[1]
    assert "urgent" in lines[1] and ITEM_ID in lines[1]


def test_list_human_all_marks_purchased(api: FakeApi, run: Runner, tty: None) -> None:
    bought = {**SHOPPING_ITEM, "is_purchased": True}
    api.on("GET", LIST_PATH, body=[bought])
    result = run("shopping", "list", "--all")
    assert "DONE" in result.out.splitlines()[0]
    assert "yes" in result.out.splitlines()[1]


def test_list_human_empty(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", LIST_PATH, body=[])
    result = run("shopping", "list")
    assert result.code == 0
    assert "shopping list is empty" in result.out.lower()


# --- shopping add ---------------------------------------------------------------


def test_add_with_amount_unit_priority_and_product(api: FakeApi, run: Runner) -> None:
    api.on("POST", LIST_PATH, 201, SHOPPING_ITEM)
    result = run(
        "shopping",
        "add",
        "Milk",
        "1",
        "l",
        "--priority",
        "urgent",
        "--product-id",
        PRODUCT_ID,
    )
    assert result.code == 0
    assert api.last.method == "POST"
    assert api.last.url.path == LIST_PATH
    assert api.last_json() == {
        "name": "Milk",
        "quantity": 1,
        "unit": "l",
        "priority": "urgent",
        "product_master_id": PRODUCT_ID,
    }
    assert len(api.last.headers["Idempotency-Key"]) == 64
    assert result.json() == {**SHOPPING_ITEM, "replayed": False}


def test_add_without_amount_is_one_piece(api: FakeApi, run: Runner) -> None:
    api.on("POST", LIST_PATH, 201, SHOPPING_ITEM)
    assert run("shopping", "add", "dish soap").code == 0
    assert api.last_json() == {"name": "dish soap", "quantity": 1, "unit": "pcs"}


def test_add_amount_without_unit_is_usage(api: FakeApi, run: Runner) -> None:
    result = run("shopping", "add", "Milk", "2")
    assert result.code == 2
    assert result.json()["code"] == "usage"
    assert api.requests == []


@pytest.mark.parametrize(
    "argv",
    [
        ["shopping", "add", "Milk", "0", "dl"],
        ["shopping", "add", "Milk", "lots", "dl"],
        ["shopping", "add", "Milk", "--priority", "someday"],
        ["shopping", "add", "Milk", "--product-id", "milk"],
    ],
)
def test_add_rejects_bad_arguments(api: FakeApi, run: Runner, argv: list[str]) -> None:
    assert run(*argv).code == 2
    assert api.requests == []


def test_add_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("POST", LIST_PATH, 201, SHOPPING_ITEM)
    result = run("shopping", "add", "Milk", "1", "l")
    assert result.code == 0
    assert "Added 10 dl Milk" in result.out
    assert ITEM_ID in result.out


def test_add_explicit_idempotency_key(api: FakeApi, run: Runner) -> None:
    api.on("POST", LIST_PATH, 201, SHOPPING_ITEM)
    run("shopping", "add", "Milk", "--idempotency-key", "shop-1")
    assert api.last.headers["Idempotency-Key"] == "shop-1"


def test_add_replayed(api: FakeApi, run: Runner) -> None:
    api.on("POST", LIST_PATH, 201, SHOPPING_ITEM, {"Idempotent-Replayed": "true"})
    result = run("shopping", "add", "Milk")
    assert result.json() == {**SHOPPING_ITEM, "replayed": True}
    assert "replayed" in result.err


def test_add_422_is_usage(api: FakeApi, run: Runner) -> None:
    detail = [{"loc": ["body", "unit"], "msg": "Unknown unit", "type": "value_error"}]
    api.error("POST", LIST_PATH, 422, detail)
    result = run("shopping", "add", "Milk", "1", "cups")
    assert result.code == 2
    assert result.json() == detail


# --- shopping done ----------------------------------------------------------------


def test_done_marks_purchased(api: FakeApi, run: Runner) -> None:
    bought = {**SHOPPING_ITEM, "is_purchased": True}
    api.on("POST", PURCHASE_PATH, body=bought)
    result = run("shopping", "done", ITEM_ID)
    assert result.code == 0
    assert api.last.method == "POST"
    assert dict(api.last.url.params) == {"purchased": "true"}
    assert api.last.content == b""
    assert len(api.last.headers["Idempotency-Key"]) == 64
    assert result.json() == {**bought, "replayed": False}


def test_done_undo(api: FakeApi, run: Runner) -> None:
    api.on("POST", PURCHASE_PATH, body=SHOPPING_ITEM)
    assert run("shopping", "done", ITEM_ID, "--undo").code == 0
    assert dict(api.last.url.params) == {"purchased": "false"}


def test_done_and_undo_derive_different_keys(api: FakeApi, run: Runner) -> None:
    api.on("POST", PURCHASE_PATH, body=SHOPPING_ITEM)
    run("shopping", "done", ITEM_ID)
    done_key = api.last.headers["Idempotency-Key"]
    run("shopping", "done", ITEM_ID, "--undo")
    assert api.last.headers["Idempotency-Key"] != done_key


def test_done_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("POST", PURCHASE_PATH, body={**SHOPPING_ITEM, "is_purchased": True})
    assert "Bought Milk" in run("shopping", "done", ITEM_ID).out
    api.on("POST", PURCHASE_PATH, body=SHOPPING_ITEM)
    assert "Back on the list: Milk" in run("shopping", "done", ITEM_ID, "--undo").out


def test_done_needs_a_uuid(api: FakeApi, run: Runner) -> None:
    assert run("shopping", "done", "milk").code == 2
    assert api.requests == []


# --- shopping remove --------------------------------------------------------------


def test_remove_deletes(api: FakeApi, run: Runner) -> None:
    api.routes[("DELETE", ITEM_PATH)] = httpx.Response(204)
    result = run("shopping", "remove", ITEM_ID)
    assert result.code == 0
    assert api.last.method == "DELETE"
    assert api.last.url.path == ITEM_PATH
    assert len(api.last.headers["Idempotency-Key"]) == 64
    assert result.json() == {"id": ITEM_ID, "removed": True, "replayed": False}


def test_remove_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.routes[("DELETE", ITEM_PATH)] = httpx.Response(204)
    result = run("shopping", "remove", ITEM_ID)
    assert result.code == 0
    assert f"Removed {ITEM_ID}" in result.out


def test_remove_needs_a_uuid(api: FakeApi, run: Runner) -> None:
    assert run("shopping", "remove", "milk").code == 2
    assert api.requests == []


# --- 404 on an item id --------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "argv"),
    [
        ("POST", PURCHASE_PATH, ["shopping", "done", ITEM_ID]),
        ("DELETE", ITEM_PATH, ["shopping", "remove", ITEM_ID]),
    ],
)
@pytest.mark.parametrize(
    "detail",
    [
        f"Shopping list item {ITEM_ID} not found",
        {"code": "not_found", "message": f"Shopping list item {ITEM_ID} not found"},
    ],
    ids=["string", "coded"],
)
def test_an_unknown_item_is_not_found(
    api: FakeApi,
    run: Runner,
    method: str,
    path: str,
    argv: list[str],
    detail: Any,
) -> None:
    api.error(method, path, 404, detail)
    result = run(*argv)
    assert result.code == 3
    body = result.json()
    assert body["code"] == "not_found"
    assert ITEM_ID in body["message"]


def test_an_unknown_item_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.error("DELETE", ITEM_PATH, 404, f"Shopping list item {ITEM_ID} not found")
    result = run("shopping", "remove", ITEM_ID)
    assert result.code == 3
    assert result.err.startswith("error")
    assert "not found" in result.err


# --- shopping generate --------------------------------------------------------------


def test_generate(api: FakeApi, run: Runner) -> None:
    api.on("POST", GENERATE_PATH, body=GENERATED)
    result = run("shopping", "generate")
    assert result.code == 0
    assert api.last.method == "POST"
    assert api.last_json() == {"sources": ["low_stock"], "dry_run": False}
    assert len(api.last.headers["Idempotency-Key"]) == 64
    assert result.json() == {**GENERATED, "replayed": False}


def test_generate_from_low_stock_dry_run_sends_no_key(
    api: FakeApi, run: Runner
) -> None:
    api.on("POST", GENERATE_PATH, body={**GENERATED, "dry_run": True})
    result = run(
        "shopping",
        "generate",
        "--from",
        "low-stock",
        "--dry-run",
        "--idempotency-key",
        "k",
    )
    assert result.code == 0
    assert api.last_json() == {"sources": ["low_stock"], "dry_run": True}
    assert "Idempotency-Key" not in api.last.headers
    assert result.json() == {**GENERATED, "dry_run": True, "replayed": False}


def test_generate_rejects_an_unknown_source(api: FakeApi, run: Runner) -> None:
    assert run("shopping", "generate", "--from", "recipes").code == 2
    assert api.requests == []


def test_generate_human_groups_the_lines(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("POST", GENERATE_PATH, body=GENERATED)
    result = run("shopping", "generate")
    assert result.code == 0
    out = result.out
    for heading in ("Added", "Updated", "Unchanged", "Skipped"):
        assert heading in out
    assert out.index("Added") < out.index("milk") < out.index("Updated")
    assert out.index("Updated") < out.index("eggs") < out.index("Unchanged")
    assert out.index("Unchanged") < out.index("butter") < out.index("Skipped")
    assert "an item is in pcs, which cannot be counted in g" in out
    assert "10 dl" in out


def test_generate_human_dry_run_and_nothing(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.on("POST", GENERATE_PATH, body={**GENERATED, "dry_run": True})
    assert "Would add" in run("shopping", "generate", "--dry-run").out
    empty = {"added": [], "updated": [], "unchanged": [], "skipped": []}
    api.on("POST", GENERATE_PATH, body={**empty, "dry_run": False})
    assert "Nothing is short" in run("shopping", "generate").out


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (400, {"code": "invalid", "message": "Unknown source 'x'"}),
        (400, "sources must be a list"),
        (400, {"code": "surprise", "message": "bad shape"}),
        (422, [{"loc": ["body", "sources"], "msg": "Input should be a valid list"}]),
    ],
    ids=["invalid", "string", "other-code", "422"],
)
def test_generate_400_and_422_are_usage(
    api: FakeApi, run: Runner, status: int, detail: Any
) -> None:
    api.error("POST", GENERATE_PATH, status, detail)
    result = run("shopping", "generate")
    assert result.code == 2


def test_generate_key_reuse_is_conflict(api: FakeApi, run: Runner) -> None:
    detail = {"code": "conflict", "message": "Idempotency-Key reused"}
    api.error("POST", GENERATE_PATH, 409, detail)
    result = run("shopping", "generate")
    assert result.code == 6
    assert result.json() == detail


# --- shopping export ------------------------------------------------------------------


def test_export_text_passes_through(api: FakeApi, run: Runner, tty: None) -> None:
    api.routes[("GET", EXPORT_PATH)] = text_answer(
        EXPORT_TEXT, "text/plain; charset=utf-8"
    )
    result = run("shopping", "export")
    assert result.code == 0
    assert dict(api.last.url.params) == {"format": "text"}
    assert result.out == EXPORT_TEXT


def test_export_markdown_passes_through(api: FakeApi, run: Runner, tty: None) -> None:
    api.routes[("GET", EXPORT_PATH)] = text_answer(
        EXPORT_MARKDOWN, "text/markdown; charset=utf-8"
    )
    result = run("shopping", "export", "--format", "markdown")
    assert result.code == 0
    assert dict(api.last.url.params) == {"format": "markdown"}
    assert result.out == EXPORT_MARKDOWN


def test_export_empty_prints_nothing(api: FakeApi, run: Runner, tty: None) -> None:
    api.routes[("GET", EXPORT_PATH)] = text_answer("", "text/plain; charset=utf-8")
    result = run("shopping", "export")
    assert result.code == 0
    assert result.out == ""


def test_export_json(api: FakeApi, run: Runner) -> None:
    api.routes[("GET", EXPORT_PATH)] = text_answer(
        EXPORT_MARKDOWN, "text/markdown; charset=utf-8"
    )
    result = run("shopping", "export", "--format", "markdown")
    assert result.code == 0
    assert result.json() == {"format": "markdown", "text": EXPORT_MARKDOWN}
    assert "Idempotency-Key" not in api.last.headers


@pytest.mark.parametrize(
    "answer",
    [
        text_answer("<html><body>Please log in</body></html>", "text/html"),
        httpx.Response(200, json={"items": []}),
    ],
    ids=["html", "json"],
)
@pytest.mark.parametrize("json_mode", [True, False], ids=["json", "tty"])
def test_export_that_is_not_text_is_bad_response(
    api: FakeApi,
    run: Runner,
    monkeypatch: pytest.MonkeyPatch,
    answer: httpx.Response,
    json_mode: bool,
) -> None:
    from kyokki import output

    monkeypatch.setattr(output, "stdout_is_tty", lambda: not json_mode)
    api.routes[("GET", EXPORT_PATH)] = answer
    result = run("shopping", "export")
    assert result.code == 1
    assert "Please log in" not in result.out
    if json_mode:
        assert result.json()["code"] == "bad_response"
    else:
        assert result.err.startswith("error")


def test_export_rejects_an_unknown_format(api: FakeApi, run: Runner) -> None:
    assert run("shopping", "export", "--format", "pdf").code == 2
    assert api.requests == []


# --- errors shared by every command -------------------------------------------------

EVERY_COMMAND: list[tuple[str, str, list[str]]] = [
    ("GET", LIST_PATH, ["shopping", "list"]),
    ("POST", LIST_PATH, ["shopping", "add", "Milk", "1", "l"]),
    ("POST", PURCHASE_PATH, ["shopping", "done", ITEM_ID]),
    ("DELETE", ITEM_PATH, ["shopping", "remove", ITEM_ID]),
    ("POST", GENERATE_PATH, ["shopping", "generate"]),
    ("GET", EXPORT_PATH, ["shopping", "export"]),
]
MUTATIONS = [case for case in EVERY_COMMAND if case[0] != "GET"]
IDS = [" ".join(case[2][:2]) for case in EVERY_COMMAND]
MUTATION_IDS = [" ".join(case[2][:2]) for case in MUTATIONS]


@pytest.mark.parametrize(("method", "path", "argv"), EVERY_COMMAND, ids=IDS)
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_7(
    api: FakeApi, run: Runner, method: str, path: str, argv: list[str], status: int
) -> None:
    detail = {"code": "auth", "message": "no"}
    api.error(method, path, status, detail)
    result = run(*argv)
    assert result.code == 7
    assert result.json() == detail


@pytest.mark.parametrize(("method", "path", "argv"), EVERY_COMMAND, ids=IDS)
def test_a_connect_error_is_connection(
    api: FakeApi, run: Runner, method: str, path: str, argv: list[str]
) -> None:
    api.down = True
    result = run(*argv)
    assert result.code == 1
    assert result.json()["code"] == "connection"
    assert "nothing was sent" in result.json()["message"]


@pytest.mark.parametrize(("method", "path", "argv"), MUTATIONS, ids=MUTATION_IDS)
def test_a_read_timeout_on_a_mutation_is_unknown_outcome(
    api: FakeApi, run: Runner, method: str, path: str, argv: list[str]
) -> None:
    api.routes[(method, path)] = _times_out
    result = run(*argv, "--verbose")
    assert result.code == 1
    detail = result.json()
    key = api.last.headers["Idempotency-Key"]
    assert detail["code"] == "unknown_outcome"
    assert "may have been applied" in detail["message"]
    assert detail["idempotency_key"] == key
    assert detail["retry"] == shlex.join(
        ["kyokki", *argv, "--verbose", "--idempotency-key", key]
    )


@pytest.mark.parametrize(
    ("method", "path", "argv"),
    [
        ("GET", LIST_PATH, ["shopping", "list"]),
        ("GET", EXPORT_PATH, ["shopping", "export"]),
        ("POST", GENERATE_PATH, ["shopping", "generate", "--dry-run"]),
    ],
    ids=["list", "export", "generate --dry-run"],
)
def test_a_read_timeout_without_a_key_is_connection(
    api: FakeApi, run: Runner, method: str, path: str, argv: list[str]
) -> None:
    api.routes[(method, path)] = _times_out
    result = run(*argv)
    assert result.code == 1
    assert result.json()["code"] == "connection"
    assert "Idempotency-Key" not in api.last.headers


@pytest.mark.parametrize(("method", "path", "argv"), MUTATIONS, ids=MUTATION_IDS)
def test_the_key_is_stable_across_json_and_verbose(
    api: FakeApi,
    run: Runner,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    argv: list[str],
) -> None:
    now = datetime(2026, 9, 26, 10, 15, 3, tzinfo=UTC)
    monkeypatch.setattr(idempotency, "utc_now", lambda: now)
    status = 204 if method == "DELETE" else 200
    body = None if method == "DELETE" else SHOPPING_ITEM
    if path == GENERATE_PATH:
        body = GENERATED
    api.on(method, path, status, body)
    keys = []
    for extra in ([], ["--json"], ["--verbose"], ["--json", "--verbose"]):
        assert run(*argv, *extra).code == 0
        keys.append(api.last.headers["Idempotency-Key"])
    assert set(keys) == {idempotency.derive_key(argv, now)}


@pytest.mark.parametrize(("method", "path", "argv"), MUTATIONS, ids=MUTATION_IDS)
def test_a_reused_key_is_conflict(
    api: FakeApi, run: Runner, method: str, path: str, argv: list[str]
) -> None:
    detail = {"code": "conflict", "message": "Idempotency-Key reused"}
    api.error(method, path, 409, detail)
    result = run(*argv)
    assert result.code == 6
    assert result.json() == detail


@pytest.mark.parametrize(
    ("method", "path", "argv"),
    [case for case in EVERY_COMMAND if case[1] != EXPORT_PATH and case[0] != "DELETE"],
)
def test_a_success_that_is_not_json_is_bad_response(
    api: FakeApi, run: Runner, method: str, path: str, argv: list[str]
) -> None:
    api.routes[(method, path)] = text_answer("<html>login</html>", "text/html")
    result = run(*argv)
    assert result.code == 1
    assert result.json()["code"] == "bad_response"
