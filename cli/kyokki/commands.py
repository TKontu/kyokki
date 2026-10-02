"""What each command asks the API, and how it reads to a person.

Each handler returns the document ``--json`` prints and a function that renders it for a
terminal. The CLI picks one; the handler never prints.
"""

import argparse
import mimetypes
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kyokki import output
from kyokki.api import CONFLICT, ERROR, NOT_FOUND, USAGE, Api, CliError, usage_error

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def looks_like_uuid(value: str) -> bool:
    return bool(UUID_PATTERN.match(value))


@dataclass
class Outcome:
    document: Any
    human: Callable[[], str]
    replayed: bool = False
    notes: list[str] = field(default_factory=list)
    # The human text is a body to pass through unchanged, not a line to print.
    raw: bool = False


@dataclass
class Context:
    api: Api
    args: argparse.Namespace
    idempotency_key: str | None


def _date(value: Any) -> str | None:
    return None if value is None else str(value)


# --- doctor -------------------------------------------------------------------


def doctor(ctx: Context) -> Outcome:
    try:
        ctx.api.request("GET", "/api/health/live", expect=dict)
    except CliError as exc:
        # No answer at all already says "cannot reach"; a 2xx that is not JSON says so.
        if exc.status is None or exc.code == "bad_response":
            raise
        raise CliError(
            ERROR,
            {
                "code": "unreachable",
                "message": f"cannot reach {ctx.api.url}: /api/health/live "
                f"answered {exc.status}",
            },
            exc.status,
        ) from exc
    me = ctx.api.request("GET", "/api/whoami", expect=dict).body
    document = {
        "url": ctx.api.url,
        "reachable": True,
        "name": me.get("name"),
        "scopes": me.get("scopes", []),
        "auth_enabled": me.get("auth_enabled"),
    }

    def human() -> str:
        scopes = ", ".join(document["scopes"]) or "(none)"
        return "\n".join(
            [
                f"url: {document['url']}",
                "live: reachable",
                f"token: {document['name'] or '(none)'}",
                f"scopes: {scopes}",
                f"auth: {'on' if document['auth_enabled'] else 'off'}",
            ]
        )

    return Outcome(document, human)


# --- stock --------------------------------------------------------------------


def stock_list(ctx: Context) -> Outcome:
    a = ctx.args
    rows = ctx.api.request(
        "GET",
        "/api/stock",
        params={
            "q": a.q,
            "location": a.location,
            "expiring_days": a.expiring,
            "category": a.category,
        },
        expect=list,
    ).body

    def human() -> str:
        if not rows:
            return "No stock."
        return output.table(
            ["PRODUCT", "TOTAL", "UNIT", "EXPIRES", "WHERE", "CATEGORY"],
            [
                [
                    row.get("product_name", ""),
                    output.number(row.get("total")),
                    row.get("unit", ""),
                    f"{row.get('earliest_expiry', '')}"
                    + (" !" if row.get("expiring") else ""),
                    _locations(row.get("locations") or {}),
                    row.get("category", ""),
                ]
                for row in rows
            ],
        )

    return Outcome(rows, human)


def _locations(locations: dict[str, Any]) -> str:
    if len(locations) == 1:
        return next(iter(locations))
    return ", ".join(
        f"{loc} {output.number(total)}" for loc, total in locations.items()
    )


def stock_add(ctx: Context) -> Outcome:
    a = ctx.args
    body: dict[str, Any] = (
        {"product_id": a.name} if looks_like_uuid(a.name) else {"name": a.name}
    )
    body["quantity"] = a.quantity
    optional = {
        "unit": a.unit,
        "category": a.category,
        "location": a.location,
        "expiry_date": _date(a.expiry),
        "purchase_date": _date(a.purchased),
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    try:
        answer = ctx.api.request(
            "POST",
            "/api/stock/add",
            body=body,
            idempotency_key=ctx.idempotency_key,
            expect=dict,
        )
    except CliError as exc:
        raise _unknown_id_as_not_found(exc, body) from None
    result = answer.body

    def human() -> str:
        item = result.get("item") or {}
        line = (
            f"Added {output.number(item.get('current_quantity'))} "
            f"{item.get('unit', '')} {item.get('product_name', a.name)}"
        )
        if item.get("location"):
            line += f" to {item['location']}"
        if item.get("expiry_date"):
            line += f", expires {item['expiry_date']}"
        if result.get("product_created"):
            line += " (new product)"
        if item.get("id"):
            line += f"\nitem {item['id']}"
        return line

    return Outcome(result, human, answer.replayed)


def _unknown_id_as_not_found(exc: CliError, body: dict[str, Any]) -> CliError:
    """add answers an unknown product id with 400 ``invalid``, consume with 404
    ``not_found``; the CLI reports both as not found (exit 3)."""
    detail = exc.detail
    if (
        "product_id" in body
        and exc.status == 400
        and isinstance(detail, dict)
        and detail.get("code") == "invalid"
        and "not found" in str(detail.get("message", ""))
    ):
        return CliError(NOT_FOUND, {**detail, "code": "not_found"}, exc.status)
    return exc


def stock_consume(ctx: Context) -> Outcome:
    a = ctx.args
    body: dict[str, Any] = (
        {"product_id": a.name} if looks_like_uuid(a.name) else {"product": a.name}
    )
    body.update({"amount": a.amount, "unit": a.unit})
    if a.location:
        body["location"] = a.location
    body["allow_partial"] = a.allow_partial
    body["dry_run"] = a.dry_run
    answer = ctx.api.request(
        "POST",
        "/api/stock/consume",
        body=body,
        idempotency_key=None if a.dry_run else ctx.idempotency_key,
        expect=dict,
    )
    result = answer.body

    def human() -> str:
        unit = result.get("unit", a.unit)
        consumed = result.get("consumed") or []
        if consumed and all(c.get("unit") == unit for c in consumed):
            taken: Any = sum(float(c.get("amount", 0)) for c in consumed)
        else:
            taken = (result.get("requested") or {}).get("amount", a.amount)
        verb = "Would consume" if result.get("dry_run") else "Consumed"
        left = "would be left" if result.get("dry_run") else "left"
        lines = [
            f"{verb} {output.number(float(taken))} {unit} of "
            f"{result.get('product_name', a.name)}; "
            f"{output.number(result.get('remaining_total'))} {unit} {left}"
        ]
        for used in consumed:
            lines.append(
                f"  item {used.get('item_id')}: {output.number(used.get('amount'))} "
                f"{used.get('unit')}, {output.number(used.get('remaining'))} "
                f"{used.get('unit')} remaining ({used.get('status')})"
            )
        return "\n".join(lines)

    return Outcome(result, human, answer.replayed)


# --- product ------------------------------------------------------------------


def product_resolve(ctx: Context) -> Outcome:
    result = ctx.api.request(
        "GET", "/api/products/resolve", params={"name": ctx.args.name}, expect=dict
    ).body

    def human() -> str:
        lines = []
        match = result.get("match")
        if match:
            lines.append(
                f"Match: {match.get('name')} ({match.get('source')}) "
                f"{match.get('product_id')}"
            )
        else:
            lines.append("No match.")
        if result.get("candidates"):
            lines.append(candidates_table(result["candidates"]))
        if result.get("suggestion"):
            lines.append(f"Suggestion for a new product: {result['suggestion']}")
        return "\n".join(lines)

    return Outcome(result, human)


def candidates_table(candidates: list[dict[str, Any]]) -> str:
    return output.table(
        ["PRODUCT_ID", "NAME", "SCORE", "SOURCE"],
        [
            [
                c.get("product_id", ""),
                c.get("name", ""),
                f"{float(c.get('score', 0)):.2f}",
                c.get("source", ""),
            ]
            for c in candidates
        ],
    )


def product_name_add(ctx: Context) -> Outcome:
    a = ctx.args
    answer = ctx.api.request(
        "POST",
        f"/api/products/{a.product_id}/names",
        body={"name": a.name},
        idempotency_key=ctx.idempotency_key,
        expect=dict,
    )
    entry = answer.body

    def human() -> str:
        name = entry.get("name", a.name)
        if answer.status == 201:
            return f"Learned '{name}' for product {a.product_id}"
        return f"Already its name: '{name}'"

    return Outcome(entry, human, answer.replayed)


# --- category -----------------------------------------------------------------


def category_list(ctx: Context) -> Outcome:
    categories = ctx.api.request("GET", "/api/categories", expect=list).body

    def human() -> str:
        return output.table(
            ["ID", "ICON", "NAME"],
            [
                [c.get("id", ""), c.get("icon") or "", c.get("display_name", "")]
                for c in categories
            ],
        )

    return Outcome(categories, human)


# --- shopping -----------------------------------------------------------------

SHOPPING_PATH = "/api/shopping/"
# What `shopping add NAME` with no AMOUNT UNIT asks for: the API needs both.
DEFAULT_SHOPPING_AMOUNT = 1
DEFAULT_SHOPPING_UNIT = "pcs"
GENERATE_SOURCES = {"low-stock": "low_stock"}
# The API's largest page; list asks for pages of this size until one comes back short.
SHOPPING_PAGE_SIZE = 500
# The router's plain-string 404 for an unknown item id (a coded not_found is exit 3
# already). Any other 404, a wrong route or a proxy's page, stays an error (exit 1).
ITEM_NOT_FOUND = re.compile(r"^Shopping list item \S+ not found$")
# handle_integrity_errors' 400 for an insert that points at a missing row.
MISSING_REFERENCE = "Referenced record does not exist."


def _item_not_found(exc: CliError) -> CliError:
    """The router's plain-string 404 for an unknown item is not found (exit 3)."""
    detail = exc.detail
    if (
        exc.status == 404
        and isinstance(detail, dict)
        and detail.get("code") == "http_404"
        and ITEM_NOT_FOUND.match(str(detail.get("message", "")))
    ):
        return CliError(NOT_FOUND, {**detail, "code": "not_found"}, exc.status)
    return exc


def _unknown_product(exc: CliError, product_id: str | None) -> CliError:
    """add with an unknown --product-id gets a foreign-key 400; that is not found."""
    detail = exc.detail
    if (
        product_id
        and exc.status == 400
        and isinstance(detail, dict)
        and detail.get("message") == MISSING_REFERENCE
    ):
        return CliError(
            NOT_FOUND,
            {"code": "not_found", "message": f"no product has the id {product_id}"},
            exc.status,
        )
    return exc


def shopping_list(ctx: Context) -> Outcome:
    a = ctx.args
    items: list[Any] = []
    previous: list[Any] | None = None
    while True:
        page = ctx.api.request(
            "GET",
            SHOPPING_PATH,
            params={
                "include_purchased": "true" if a.all else None,
                "priority": a.priority,
                "limit": SHOPPING_PAGE_SIZE,
                "skip": len(items),
            },
            expect=list,
        ).body
        # A server that ignored skip would answer the same page for ever.
        if page == previous:
            break
        items.extend(page)
        if len(page) < SHOPPING_PAGE_SIZE:
            break
        previous = page

    def human() -> str:
        if not items:
            return "The shopping list is empty."
        headers = ["NAME", "AMOUNT", "UNIT", "PRIORITY", "ID"]
        if a.all:
            headers.insert(4, "DONE")
        rows = []
        for item in items:
            row = [
                item.get("name", ""),
                output.number(item.get("quantity")),
                item.get("unit", ""),
                item.get("priority", ""),
                item.get("id", ""),
            ]
            if a.all:
                row.insert(4, "yes" if item.get("is_purchased") else "no")
            rows.append(row)
        return output.table(headers, rows)

    return Outcome(items, human)


def shopping_add(ctx: Context) -> Outcome:
    a = ctx.args
    if not a.name.strip():
        raise usage_error("NAME is empty; say what to buy")
    if (a.amount is None) != (a.unit is None):
        raise usage_error("give AMOUNT and UNIT together, or neither (1 pcs)")
    if a.product_id and a.amount is None:
        raise usage_error(
            "--product-id needs AMOUNT UNIT: a linked item's amount must be in the "
            "product's unit, or generate skips the item; e.g. shopping add milk 1 l "
            "--product-id ID"
        )
    body: dict[str, Any] = {
        "name": a.name,
        "quantity": DEFAULT_SHOPPING_AMOUNT if a.amount is None else a.amount,
        "unit": DEFAULT_SHOPPING_UNIT if a.unit is None else a.unit,
    }
    if a.priority:
        body["priority"] = a.priority
    if a.product_id:
        body["product_master_id"] = a.product_id
    try:
        answer = ctx.api.request(
            "POST",
            SHOPPING_PATH,
            body=body,
            idempotency_key=ctx.idempotency_key,
            expect=dict,
        )
    except CliError as exc:
        raise _unknown_product(exc, a.product_id) from None
    item = answer.body

    def human() -> str:
        return (
            f"Added {output.number(item.get('quantity'))} {item.get('unit', '')} "
            f"{item.get('name', a.name)} to the shopping list "
            f"({item.get('priority', 'normal')})\nitem {item.get('id')}"
        )

    return Outcome(item, human, answer.replayed)


def shopping_done(ctx: Context) -> Outcome:
    a = ctx.args
    try:
        answer = ctx.api.request(
            "POST",
            f"{SHOPPING_PATH}{a.item_id}/purchase",
            params={"purchased": "false" if a.undo else "true"},
            idempotency_key=ctx.idempotency_key,
            expect=dict,
        )
    except CliError as exc:
        raise _item_not_found(exc) from None
    item = answer.body

    def human() -> str:
        name = item.get("name", a.item_id)
        if item.get("is_purchased"):
            return f"Bought {name}"
        return f"Back on the list: {name}"

    return Outcome(item, human, answer.replayed)


def shopping_remove(ctx: Context) -> Outcome:
    a = ctx.args
    # No Idempotency-Key: the server ignores it on DELETE, so nothing could replay.
    # Deleting is safe to repeat instead; a repeat of one that applied is exit 3.
    try:
        ctx.api.request("DELETE", f"{SHOPPING_PATH}{a.item_id}")
    except CliError as exc:
        if exc.code == "connection" and isinstance(exc.detail, dict):
            exc.detail["hint"] = (
                "rerun the same command: removing twice removes nothing more, and "
                "exit 3 then means the item is already removed"
            )
        raise _item_not_found(exc) from None
    document = {"id": a.item_id, "removed": True}

    def human() -> str:
        return f"Removed {a.item_id} from the shopping list"

    return Outcome(document, human)


def shopping_generate(ctx: Context) -> Outcome:
    a = ctx.args
    body = {"sources": [GENERATE_SOURCES[a.source]], "dry_run": a.dry_run}
    try:
        answer = ctx.api.request(
            "POST",
            f"{SHOPPING_PATH}generate",
            body=body,
            idempotency_key=None if a.dry_run else ctx.idempotency_key,
            expect=dict,
        )
    except CliError as exc:
        # A bad sources shape is 400 or 422 depending on the server's version: usage.
        if exc.status in (400, 422) and exc.exit_code != USAGE:
            raise CliError(USAGE, exc.detail, exc.status) from None
        raise
    result = answer.body

    def human() -> str:
        dry = bool(result.get("dry_run"))
        groups = [
            ("Would add" if dry else "Added", "added"),
            ("Would update" if dry else "Updated", "updated"),
            ("Unchanged (already on the list)", "unchanged"),
            ("Skipped", "skipped"),
        ]
        blocks = []
        for title, key in groups:
            lines = result.get(key) or []
            if lines:
                rows = [f"{title}:", *(f"  {_generate_line(line)}" for line in lines)]
                blocks.append("\n".join(rows))
        if not blocks:
            return "Nothing is short; the shopping list is unchanged."
        return "\n".join(blocks)

    return Outcome(result, human, answer.replayed)


def _generate_line(line: dict[str, Any]) -> str:
    unit = line.get("unit", "")
    text = str(line.get("name", ""))
    if line.get("need") is not None:
        text += (
            f" {output.number(line['need'])} {unit}"
            f" (on hand {output.number(line.get('on_hand'))},"
            f" min {output.number(line.get('min_stock'))} {unit})"
        )
    if line.get("reason"):
        text += f": {line['reason']}"
    return text


def shopping_export(ctx: Context) -> Outcome:
    a = ctx.args
    text = ctx.api.request(
        "GET",
        f"{SHOPPING_PATH}export",
        params={"format": a.format},
        expect="text",
    ).body
    return Outcome({"format": a.format, "text": text}, lambda: str(text), raw=True)


# --- receipt --------------------------------------------------------------------

RECEIPT_PATH = "/api/receipts/"
# Not yet read: status/confirm both treat these as "not ready yet".
IN_PROGRESS_STATUSES = {"uploaded", "queued", "processing"}
RECEIPT_POLL_SECONDS = 5
# The server's per-receipt budget is ~28 min: MinerU OCR (120s) plus up to three
# sequential model calls at 420s each, with margin (`receipt_stale_minutes` in
# backend/app/core/config.py). 600s produced a false timeout on a receipt needing a
# re-read. cli.py's `--timeout` default reads this constant, so there is one number.
DEFAULT_RECEIPT_WAIT_TIMEOUT = 1800
# The router's plain-string 404 for an unknown receipt id.
RECEIPT_NOT_FOUND = re.compile(r"^Receipt '\S+' not found$")
# Why a receipt is not ready for `confirm`, keyed on processing_status.
NOT_READY_REASON = {
    "uploaded": "is still queued",
    "queued": "is still queued",
    "processing": "is still processing",
    "failed": "failed to process",
    "confirmed": "is already confirmed",
}


def _receipt_not_found(exc: CliError) -> CliError:
    """The router's plain-string 404 for an unknown receipt id is not found (exit 3)."""
    detail = exc.detail
    if (
        exc.status == 404
        and isinstance(detail, dict)
        and detail.get("code") == "http_404"
        and RECEIPT_NOT_FOUND.match(str(detail.get("message", "")))
    ):
        return CliError(NOT_FOUND, {**detail, "code": "not_found"}, exc.status)
    return exc


def _duplicate_as_conflict(exc: CliError) -> CliError:
    """The scan endpoint's 409 for a file already uploaded: conflict (exit 6), the
    existing receipt id folded into the message when the API gives one."""
    if exc.status != 409:
        return exc
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    message = str(detail.get("message") or "the receipt was already uploaded")
    receipt_id = detail.get("receipt_id")
    if receipt_id:
        message = f"{message} (receipt {receipt_id})"
    return CliError(
        CONFLICT, {**detail, "code": "conflict", "message": message}, exc.status
    )


def _too_large_as_usage(exc: CliError) -> CliError:
    """413 from /scan (over the server's upload cap): a usage error (exit 2), like a
    bad argument, not the generic http_413 (exit 1). The server's own message already
    names the file's size and the limit; only the code and exit change."""
    if exc.status != 413:
        return exc
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc)}
    return CliError(USAGE, {**detail, "code": "usage"}, exc.status)


def _not_ready(receipt: dict[str, Any]) -> CliError | None:
    """None when the receipt is ``completed`` (ready to confirm); otherwise the
    conflict (exit 6) to raise instead of sending anything."""
    status = receipt.get("processing_status")
    if status == "completed":
        return None
    reason = NOT_READY_REASON.get(str(status), f"is not ready to confirm ({status})")
    message = f"receipt {receipt.get('id')} {reason}, not ready to confirm"
    if status == "failed" and receipt.get("error"):
        message += f": {receipt['error']}"
    return CliError(
        CONFLICT, {"code": "conflict", "message": message, "status": status}
    )


def _read_file(path_text: str) -> tuple[str, bytes]:
    path = Path(path_text)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise usage_error(f"cannot read {path_text!r}: {exc}") from None
    return path.name, content


def _receipt_line_row(item: dict[str, Any]) -> list[str]:
    product = item.get("product_name")
    if product:
        product = f"{product} (verified)" if item.get("verified") else product
    return [
        str(item.get("index", "")),
        item.get("name", ""),
        item.get("generic_name") or "",
        product or "(unmatched)",
        output.number(item.get("quantity")),
        item.get("unit", ""),
        "yes" if item.get("non_food") else "",
    ]


def _receipt_human(receipt: dict[str, Any]) -> str:
    lines = [f"receipt {receipt.get('id')}: {receipt.get('processing_status')}"]
    if receipt.get("store_chain"):
        lines.append(f"store: {receipt['store_chain']}")
    if receipt.get("purchase_date"):
        lines.append(f"purchase date: {receipt['purchase_date']}")
    if receipt.get("error"):
        lines.append(f"error: {receipt['error']}")
    items = receipt.get("items") or []
    if items:
        lines.append(
            output.table(
                ["#", "NAME", "GENERIC", "PRODUCT", "QUANTITY", "UNIT", "NON-FOOD"],
                [_receipt_line_row(item) for item in items],
            )
        )
    elif receipt.get("processing_status") == "completed":
        lines.append("No lines were read.")
    return "\n".join(lines)


def _wait_for_receipt(api: Api, receipt_id: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    receipt: dict[str, Any] = api.request(
        "GET", f"{RECEIPT_PATH}{receipt_id}", expect=dict
    ).body
    while receipt.get("processing_status") in IN_PROGRESS_STATUSES:
        if time.monotonic() >= deadline:
            raise CliError(
                ERROR,
                {
                    "code": "timeout",
                    "message": f"timed out after {timeout:g}s waiting for receipt "
                    f"{receipt_id} to finish processing (still "
                    f"{receipt.get('processing_status')})",
                },
            )
        time.sleep(RECEIPT_POLL_SECONDS)
        receipt = api.request("GET", f"{RECEIPT_PATH}{receipt_id}", expect=dict).body
    return receipt


def receipt_upload(ctx: Context) -> Outcome:
    a = ctx.args
    name, content = _read_file(a.file)
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        answer = ctx.api.request(
            "POST",
            f"{RECEIPT_PATH}scan",
            files={"file": (name, content, content_type)},
            expect=dict,
        )
    except CliError as exc:
        raise _too_large_as_usage(_duplicate_as_conflict(exc)) from None
    receipt = answer.body
    if a.wait:
        receipt = _wait_for_receipt(ctx.api, str(receipt.get("id")), a.timeout)

    def human() -> str:
        return _receipt_human(receipt)

    return Outcome(receipt, human)


def receipt_status(ctx: Context) -> Outcome:
    a = ctx.args
    try:
        receipt = ctx.api.request(
            "GET", f"{RECEIPT_PATH}{a.receipt_id}", expect=dict
        ).body
    except CliError as exc:
        raise _receipt_not_found(exc) from None

    def human() -> str:
        return _receipt_human(receipt)

    return Outcome(receipt, human)


def _check_line(
    index: int, by_index: dict[int, dict[str, Any]], seen: set[int]
) -> dict[str, Any]:
    """The line --assign/--new names: it must exist, be food, and not already be
    claimed by an earlier --assign/--new (exit 2 otherwise)."""
    item = by_index.get(index)
    if item is None:
        raise usage_error(f"no line {index} on this receipt; see kyokki receipt status")
    if item.get("non_food"):
        raise usage_error(f"line {index} is non-food; it is never stocked")
    if index in seen:
        raise usage_error(f"line {index} is named more than once (--assign/--new)")
    seen.add(index)
    return item


def _resolve_overrides(
    assign: list[tuple[int, str]],
    new: list[tuple[int, str]],
    by_index: dict[int, dict[str, Any]],
) -> tuple[dict[int, str], dict[int, str]]:
    """``--assign LINE=PRODUCT_ID`` and ``--new LINE=CATEGORY``, validated against the
    receipt's own lines. Raises a usage error (exit 2) for an unknown line, a non-food
    line, or a line named twice, across both options together."""
    seen: set[int] = set()
    assignments: dict[int, str] = {}
    for index, product_id in assign:
        _check_line(index, by_index, seen)
        assignments[index] = product_id
    categories: dict[int, str] = {}
    for index, category in new:
        _check_line(index, by_index, seen)
        categories[index] = category
    return assignments, categories


def _confirm_line(
    item: dict[str, Any],
    purchase_date: str,
    assignments: dict[int, str],
    categories: dict[int, str],
) -> dict[str, Any]:
    index = int(item["index"])
    line: dict[str, Any] = (
        {"line_id": str(item["line_id"])} if item.get("line_id") else {"index": index}
    )
    if index in categories:
        line["name"] = item.get("generic_name") or item.get("name")
        line["category"] = categories[index]
    else:
        line["product_id"] = assignments.get(index, item.get("product_id"))
    line["quantity"] = item.get("quantity")
    line["unit"] = item.get("unit")
    line["purchase_date"] = purchase_date
    return line


def _confirm_line_preview(line: dict[str, Any]) -> str:
    where = line.get("line_id") or f"index {line.get('index')}"
    what = (
        f"new product {line['name']!r} ({line['category']})"
        if "category" in line
        else f"product {line['product_id']}"
    )
    return (
        f"  {where}: {what} {output.number(line['quantity'])} {line['unit']}, "
        f"purchased {line['purchase_date']}"
    )


def receipt_confirm(ctx: Context) -> Outcome:
    a = ctx.args
    try:
        receipt = ctx.api.request(
            "GET", f"{RECEIPT_PATH}{a.receipt_id}", expect=dict
        ).body
    except CliError as exc:
        raise _receipt_not_found(exc) from None

    not_ready = _not_ready(receipt)
    if not_ready:
        raise not_ready

    purchase_date = _date(a.purchase_date) or receipt.get("purchase_date")
    if not purchase_date:
        raise usage_error(
            "the receipt has no purchase date; pass --purchase-date YYYY-MM-DD"
        )

    items = receipt.get("items") or []
    by_index = {item.get("index"): item for item in items}
    assignments, categories = _resolve_overrides(a.assign, a.new, by_index)
    overridden = set(assignments) | set(categories)

    food = [item for item in items if not item.get("non_food")]
    non_food = [item for item in items if item.get("non_food")]
    matched = [
        item
        for item in food
        if item.get("product_id") or item.get("index") in overridden
    ]
    unmatched = [
        item
        for item in food
        if not item.get("product_id") and item.get("index") not in overridden
    ]

    if unmatched and not a.skip_unmatched:
        listed = "; ".join(
            f"#{item.get('index')} {item.get('name')}" for item in unmatched
        )
        raise CliError(
            CONFLICT,
            {
                "code": "conflict",
                "message": f"{len(unmatched)} food line(s) are unmatched, so nothing "
                f"was sent: {listed}; resolve them with --assign/--new, or pass "
                "--skip-unmatched to leave them out",
                "unmatched": [
                    {"index": item.get("index"), "name": item.get("name")}
                    for item in unmatched
                ],
            },
        )

    confirmed_items = [
        _confirm_line(item, purchase_date, assignments, categories) for item in matched
    ]
    body = {
        "items": confirmed_items,
        "non_food_indexes": [item.get("index") for item in non_food],
    }
    skipped = len(unmatched)

    if a.dry_run:
        document = {**body, "dry_run": True, "skipped_unmatched": skipped}

        def dry_run_human() -> str:
            lines = [f"Would confirm receipt {a.receipt_id}:"]
            lines.extend(_confirm_line_preview(line) for line in confirmed_items)
            if non_food:
                lines.append(f"  ({len(non_food)} non-food line(s) left out)")
            if skipped:
                lines.append(f"  ({skipped} unmatched line(s) skipped)")
            return "\n".join(lines)

        return Outcome(document, dry_run_human)

    try:
        answer = ctx.api.request(
            "POST", f"{RECEIPT_PATH}{a.receipt_id}/confirm", body=body, expect=dict
        )
    except CliError as exc:
        # No `_confirm_conflict` here on purpose (F3): the confirm endpoint has no
        # Idempotency-Key, but its 400/409 both carry a plain-string detail, which
        # `error_from`'s own STRING_DETAIL_EXIT table already maps correctly - 400
        # (an item the server rejected, e.g. a since-deleted product_id) to usage
        # (exit 2), 409 (already confirmed) to conflict (exit 6).
        raise _receipt_not_found(exc) from None
    result = answer.body

    def human() -> str:
        lines = [
            f"Confirmed receipt {a.receipt_id}: "
            f"{result.get('items_created', 0)} item(s) created, "
            f"{result.get('products_created', 0)} new product(s), "
            f"{result.get('aliases_learned', 0)} alias(es) learned"
        ]
        if skipped:
            lines.append(f"skipped {skipped} unmatched line(s)")
        return "\n".join(lines)

    return Outcome(result, human)
