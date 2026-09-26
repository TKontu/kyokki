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
from kyokki.api import ERROR, NOT_FOUND, Api, CliError

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
