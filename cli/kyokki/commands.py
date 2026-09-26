"""What each command asks the API, and how it reads to a person.

Each handler returns the document ``--json`` prints and a function that renders it for a
terminal. The CLI picks one; the handler never prints.
"""

import argparse
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kyokki import output
from kyokki.api import ERROR, NOT_FOUND, USAGE, Api, CliError, usage_error

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
