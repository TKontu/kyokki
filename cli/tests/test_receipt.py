"""`kyokki receipt`: upload, status and confirm, against a mocked API."""

import itertools

import httpx
import pytest
from conftest import PRODUCT_ID, RECEIPT_ID, FakeApi, Runner

from kyokki import cli, commands

ANOTHER_PRODUCT_ID = "aaaaaaaa-1111-4111-8111-111111111111"

MATCHED_ITEM = {
    "index": 0,
    "line_id": "11111111-1111-1111-1111-111111111111",
    "name": "KEVYTMAITO 1L",
    "generic_name": "Milk",
    "quantity": 1.0,
    "unit": "dl",
    "product_id": PRODUCT_ID,
    "product_name": "Milk",
    "match_source": "alias",
    "verified": True,
    "non_food": False,
}

UNMATCHED_ITEM = {
    "index": 1,
    "line_id": "22222222-2222-2222-2222-222222222222",
    "name": "TUNTEMATON TUOTE",
    "generic_name": None,
    "quantity": 2.0,
    "unit": "pcs",
    "product_id": None,
    "product_name": None,
    "match_source": "none",
    "verified": False,
    "non_food": False,
}

NON_FOOD_ITEM = {
    "index": 2,
    "line_id": "33333333-3333-3333-3333-333333333333",
    "name": "PAPERIPYYHE",
    "generic_name": None,
    "quantity": 1.0,
    "unit": "pcs",
    "product_id": None,
    "product_name": None,
    "match_source": "none",
    "verified": False,
    "non_food": True,
}

RECEIPT_WITH_UNMATCHED = {
    "id": RECEIPT_ID,
    "processing_status": "completed",
    "store_chain": "s-market",
    "purchase_date": "2026-09-20",
    "error": None,
    "items": [MATCHED_ITEM, UNMATCHED_ITEM, NON_FOOD_ITEM],
}

RECEIPT_ALL_MATCHED = {
    "id": RECEIPT_ID,
    "processing_status": "completed",
    "store_chain": "s-market",
    "purchase_date": "2026-09-20",
    "error": None,
    "items": [MATCHED_ITEM, NON_FOOD_ITEM],
}

CONFIRM_RESULT = {
    "success": True,
    "items_created": 1,
    "products_created": 0,
    "aliases_learned": 1,
    "error": None,
}

CONFIRM_PATH = f"/api/receipts/{RECEIPT_ID}/confirm"
RECEIPT_GET_PATH = f"/api/receipts/{RECEIPT_ID}"


# --- upload ---------------------------------------------------------------------


def test_receipt_upload_sends_the_file_and_prints_status(
    api: FakeApi, run: Runner, tmp_path
) -> None:
    upload_file = tmp_path / "receipt.jpg"
    upload_file.write_bytes(b"hello-receipt-bytes")
    api.on(
        "POST",
        "/api/receipts/scan",
        201,
        {"id": RECEIPT_ID, "processing_status": "queued"},
    )
    result = run("receipt", "upload", str(upload_file))
    assert result.code == 0
    assert api.last.method == "POST"
    assert api.last.url.path == "/api/receipts/scan"
    assert b"hello-receipt-bytes" in api.last.content
    assert "multipart/form-data" in api.last.headers["content-type"]
    document = result.json()
    assert document["id"] == RECEIPT_ID
    assert document["processing_status"] == "queued"


def test_receipt_upload_missing_file_is_usage_error(api: FakeApi, run: Runner) -> None:
    result = run("receipt", "upload", "/no/such/file-for-kyokki-tests.jpg")
    assert result.code == 2
    assert api.requests == []


def test_receipt_upload_unreadable_file_is_usage_error(
    api: FakeApi, run: Runner, tmp_path
) -> None:
    # A directory can't be read as a file.
    result = run("receipt", "upload", str(tmp_path))
    assert result.code == 2
    assert api.requests == []


def test_receipt_upload_duplicate_is_conflict_with_the_existing_id(
    api: FakeApi, run: Runner, tmp_path
) -> None:
    upload_file = tmp_path / "receipt.jpg"
    upload_file.write_bytes(b"dup")
    api.error(
        "POST",
        "/api/receipts/scan",
        409,
        {"message": "Receipt already uploaded", "receipt_id": RECEIPT_ID},
    )
    result = run("receipt", "upload", str(upload_file))
    assert result.code == 6
    detail = result.json()
    assert detail["code"] == "conflict"
    assert RECEIPT_ID in detail["message"]


def test_receipt_upload_too_large_is_a_usage_error(
    api: FakeApi, run: Runner, tmp_path
) -> None:
    # The real server's detail is a plain string (F6): `HTTPException(413, detail=str(exc))`.
    upload_file = tmp_path / "receipt.jpg"
    upload_file.write_bytes(b"x")
    api.error("POST", "/api/receipts/scan", 413, "Receipt is 25 MB; the limit is 20 MB")
    result = run("receipt", "upload", str(upload_file))
    assert result.code == 2
    detail = result.json()
    assert "20 MB" in detail["message"]


def test_receipt_upload_wait_polls_until_completed(
    api: FakeApi, run: Runner, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_file = tmp_path / "receipt.jpg"
    upload_file.write_bytes(b"x")
    api.on(
        "POST",
        "/api/receipts/scan",
        201,
        {"id": RECEIPT_ID, "processing_status": "queued"},
    )
    answers = iter(
        [
            {"id": RECEIPT_ID, "processing_status": "queued"},
            {"id": RECEIPT_ID, "processing_status": "processing"},
            RECEIPT_ALL_MATCHED,
        ]
    )
    api.routes[("GET", RECEIPT_GET_PATH)] = lambda request: httpx.Response(
        200, json=next(answers)
    )
    monkeypatch.setattr(commands.time, "sleep", lambda seconds: None)
    result = run("receipt", "upload", str(upload_file), "--wait")
    assert result.code == 0
    document = result.json()
    assert document["processing_status"] == "completed"
    gets = [r for r in api.requests if r.method == "GET"]
    assert len(gets) == 3


def test_receipt_upload_wait_times_out(
    api: FakeApi, run: Runner, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_file = tmp_path / "receipt.jpg"
    upload_file.write_bytes(b"x")
    api.on(
        "POST",
        "/api/receipts/scan",
        201,
        {"id": RECEIPT_ID, "processing_status": "queued"},
    )
    api.on(
        "GET",
        RECEIPT_GET_PATH,
        200,
        {"id": RECEIPT_ID, "processing_status": "processing"},
    )
    monkeypatch.setattr(commands.time, "sleep", lambda seconds: None)
    clock = itertools.chain([0.0], itertools.repeat(10_000.0))
    monkeypatch.setattr(commands.time, "monotonic", lambda: next(clock))
    result = run("receipt", "upload", str(upload_file), "--wait", "--timeout", "1")
    assert result.code == 1
    assert result.json()["code"] == "timeout"
    gets = [r for r in api.requests if r.method == "GET"]
    assert len(gets) == 1


def test_receipt_upload_default_timeout_is_1800_seconds() -> None:
    # F2: the server's per-receipt budget is ~28 min; 600s produced false timeouts.
    parser = cli.build_parser()
    args = parser.parse_args(["receipt", "upload", "somefile.jpg"])
    assert args.timeout == 1800
    assert commands.DEFAULT_RECEIPT_WAIT_TIMEOUT == 1800


# --- status -----------------------------------------------------------------


def test_receipt_status_prints_the_lines(api: FakeApi, run: Runner, tty: None) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run("receipt", "status", RECEIPT_ID)
    assert result.code == 0
    assert "completed" in result.out
    assert "Milk" in result.out
    assert "(unmatched)" in result.out


def test_receipt_status_unknown_id_is_not_found(api: FakeApi, run: Runner) -> None:
    api.error("GET", RECEIPT_GET_PATH, 404, f"Receipt '{RECEIPT_ID}' not found")
    result = run("receipt", "status", RECEIPT_ID)
    assert result.code == 3


def test_receipt_status_other_404_stays_an_error(api: FakeApi, run: Runner) -> None:
    api.error("GET", RECEIPT_GET_PATH, 404, "Not Found")
    result = run("receipt", "status", RECEIPT_ID)
    assert result.code == 1


# --- confirm ------------------------------------------------------------------


def test_receipt_confirm_all_matched_sends_the_matched_lines(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_ALL_MATCHED)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched")
    assert result.code == 0
    assert api.last.method == "POST"
    assert api.last_json() == {
        "items": [
            {
                "line_id": MATCHED_ITEM["line_id"],
                "product_id": PRODUCT_ID,
                "quantity": 1.0,
                "unit": "dl",
                "purchase_date": "2026-09-20",
            }
        ],
        "non_food_indexes": [NON_FOOD_ITEM["index"]],
    }


def test_receipt_confirm_refuses_on_unmatched_food_lines(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched")
    assert result.code == 6
    detail = result.json()
    assert "TUNTEMATON TUOTE" in detail["message"]
    assert "--assign" in detail["message"]
    assert "--new" in detail["message"]
    assert "--skip-unmatched" in detail["message"]
    assert all(r.method == "GET" for r in api.requests)


def test_receipt_confirm_skip_unmatched_leaves_them_out(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched", "--skip-unmatched")
    assert result.code == 0
    body = api.last_json()
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == PRODUCT_ID


def test_receipt_confirm_skip_unmatched_notes_the_count(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched", "--skip-unmatched")
    assert result.code == 0
    assert "skipped 1" in result.out


def test_receipt_confirm_dry_run_sends_nothing(api: FakeApi, run: Runner) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--skip-unmatched",
        "--dry-run",
    )
    assert result.code == 0
    assert all(r.method == "GET" for r in api.requests)
    document = result.json()
    assert document["dry_run"] is True
    assert document["skipped_unmatched"] == 1
    assert document["items"][0]["product_id"] == PRODUCT_ID


def test_receipt_confirm_needs_purchase_date_when_receipt_has_none(
    api: FakeApi, run: Runner
) -> None:
    receipt = {**RECEIPT_ALL_MATCHED, "purchase_date": None}
    api.on("GET", RECEIPT_GET_PATH, 200, receipt)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched")
    assert result.code == 2
    assert all(r.method == "GET" for r in api.requests)


def test_receipt_confirm_uses_the_explicit_purchase_date(
    api: FakeApi, run: Runner
) -> None:
    receipt = {**RECEIPT_ALL_MATCHED, "purchase_date": None}
    api.on("GET", RECEIPT_GET_PATH, 200, receipt)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--purchase-date",
        "2026-09-30",
    )
    assert result.code == 0
    assert api.last_json()["items"][0]["purchase_date"] == "2026-09-30"


@pytest.mark.parametrize(
    "status", ["uploaded", "queued", "processing", "failed", "confirmed"]
)
def test_receipt_confirm_refuses_when_not_ready(
    api: FakeApi, run: Runner, status: str
) -> None:
    api.on(
        "GET",
        RECEIPT_GET_PATH,
        200,
        {"id": RECEIPT_ID, "processing_status": status, "items": []},
    )
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched")
    assert result.code == 6
    assert all(r.method == "GET" for r in api.requests)


def test_receipt_confirm_already_confirmed_409_is_conflict(
    api: FakeApi, run: Runner
) -> None:
    # F3/F6: the real server sends a plain-string detail for this 409.
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_ALL_MATCHED)
    api.error("POST", CONFIRM_PATH, 409, "Receipt already confirmed")
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched")
    assert result.code == 6


def test_receipt_confirm_invalid_item_400_is_a_usage_error(
    api: FakeApi, run: Runner
) -> None:
    # F3/F6: a 400 (e.g. a product deleted since `status`) is usage, not conflict.
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_ALL_MATCHED)
    api.error("POST", CONFIRM_PATH, 400, "Item 0: unknown product")
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched")
    assert result.code == 2


def test_receipt_confirm_requires_all_matched_flag(api: FakeApi, run: Runner) -> None:
    result = run("receipt", "confirm", RECEIPT_ID)
    assert result.code == 2
    assert api.requests == []


def test_receipt_confirm_needs_a_uuid(run: Runner) -> None:
    result = run("receipt", "confirm", "not-a-uuid", "--all-matched")
    assert result.code == 2


# --- confirm: --assign and --new (F1) ------------------------------------------


def test_receipt_confirm_assign_sends_the_given_product_id(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--assign",
        f"1={ANOTHER_PRODUCT_ID}",
    )
    assert result.code == 0
    body = api.last_json()
    assert len(body["items"]) == 2
    assigned = next(i for i in body["items"] if i["product_id"] == ANOTHER_PRODUCT_ID)
    assert assigned["line_id"] == UNMATCHED_ITEM["line_id"]
    assert assigned["quantity"] == UNMATCHED_ITEM["quantity"]
    assert assigned["unit"] == UNMATCHED_ITEM["unit"]
    assert assigned["purchase_date"] == "2026-09-20"


def test_receipt_confirm_new_sends_name_and_category(api: FakeApi, run: Runner) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched", "--new", "1=dairy")
    assert result.code == 0
    body = api.last_json()
    created = next(i for i in body["items"] if "category" in i)
    assert created["name"] == UNMATCHED_ITEM["name"]  # no generic_name: falls back
    assert created["category"] == "dairy"
    assert "product_id" not in created


def test_receipt_confirm_new_prefers_the_generic_name(
    api: FakeApi, run: Runner
) -> None:
    receipt = {
        **RECEIPT_WITH_UNMATCHED,
        "items": [
            MATCHED_ITEM,
            {**UNMATCHED_ITEM, "generic_name": "Tahini"},
            NON_FOOD_ITEM,
        ],
    }
    api.on("GET", RECEIPT_GET_PATH, 200, receipt)
    api.on("POST", CONFIRM_PATH, 200, CONFIRM_RESULT)
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched", "--new", "1=pantry")
    assert result.code == 0
    created = next(i for i in api.last_json()["items"] if "category" in i)
    assert created["name"] == "Tahini"


def test_receipt_confirm_assign_unknown_line_is_a_usage_error(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--assign",
        f"99={PRODUCT_ID}",
    )
    assert result.code == 2
    assert all(r.method == "GET" for r in api.requests)


def test_receipt_confirm_assign_a_non_food_line_is_a_usage_error(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt", "confirm", RECEIPT_ID, "--all-matched", "--assign", f"2={PRODUCT_ID}"
    )
    assert result.code == 2
    assert all(r.method == "GET" for r in api.requests)


def test_receipt_confirm_assigning_the_same_line_twice_is_a_usage_error(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--assign",
        f"1={ANOTHER_PRODUCT_ID}",
        "--assign",
        f"1={PRODUCT_ID}",
    )
    assert result.code == 2


def test_receipt_confirm_assign_and_new_the_same_line_is_a_usage_error(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--assign",
        f"1={ANOTHER_PRODUCT_ID}",
        "--new",
        "1=dairy",
    )
    assert result.code == 2


def test_receipt_confirm_assign_needs_a_line_equals_uuid(run: Runner) -> None:
    result = run(
        "receipt", "confirm", RECEIPT_ID, "--all-matched", "--assign", "1=not-a-uuid"
    )
    assert result.code == 2


def test_receipt_confirm_assign_needs_the_equals_sign(run: Runner) -> None:
    result = run("receipt", "confirm", RECEIPT_ID, "--all-matched", "--assign", "nope")
    assert result.code == 2


def test_receipt_confirm_dry_run_with_assign_shows_the_product(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--assign",
        f"1={ANOTHER_PRODUCT_ID}",
        "--dry-run",
    )
    assert result.code == 0
    assert ANOTHER_PRODUCT_ID in result.out


def test_receipt_confirm_dry_run_with_new_shows_the_category(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.on("GET", RECEIPT_GET_PATH, 200, RECEIPT_WITH_UNMATCHED)
    result = run(
        "receipt",
        "confirm",
        RECEIPT_ID,
        "--all-matched",
        "--new",
        "1=pantry",
        "--dry-run",
    )
    assert result.code == 0
    assert "pantry" in result.out
