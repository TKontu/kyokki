"""Reply texts. Plain text only (no parse mode), so product names need no escaping."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.schemas.receipt import ReceiptResponse, ReceiptStatus

TELEGRAM_TEXT_LIMIT = 4096
MAX_NEW_NAMES = 8
MAX_NAME_CHARS = 60

_STORE_NAMES = {
    "s-group": "S-group",
    "k-group": "K-group",
    "lidl": "Lidl",
    "tokmanni": "Tokmanni",
}


def help_text() -> str:
    return (
        "Share receipts here and Kyokki reads them.\n"
        "- Order PDFs (S-kaupat, K-Ruoka)\n"
        "- S-Group and K-Plussa app receipts or screenshots\n"
        "- Photos of paper receipts, best sent as a file (uncompressed)\n"
        "You get a summary when a receipt has been read. Review it on the iPad.\n"
        "\n"
        "Commands:\n"
        "/list - the shopping list, numbered\n"
        "/add <name> [amount] [unit] - add to the list, e.g. /add milk 2 l\n"
        "/bought <number or name> - tick a line bought, e.g. /bought 2\n"
        "/used <name> [amount] [unit] - record something used up, e.g. /used milk 2 dl\n"
        "/help - this text"
    )


def unknown_chat_text(chat_id: int) -> str:
    return (
        f"This bot is private. Your chat id is {chat_id}.\n"
        "To use it, add the id to TELEGRAM_ALLOWED_CHAT_IDS and restart kyokki-telegram."
    )


def received_text(ahead: int) -> str:
    if ahead <= 0:
        return "Received, reading the receipt…"
    return f"Received, queued ({ahead} ahead)…"


def unsupported_text() -> str:
    return "Unsupported file. Send a PDF, JPEG, PNG or WebP receipt."


def too_large_text() -> str:
    return "The file is over 20 MB, which bots cannot download. Send a smaller file."


def download_failed_text() -> str:
    return "Could not download the file from Telegram. Try sending it again."


def failure_text(reason: str | None) -> str:
    """A cook-facing sentence for a failed receipt.

    ``reason`` may be the raw error stored on the receipt, which can carry pipeline
    internals (a gateway URL, an HTTP status, an exception string, a model name). This
    never echoes any part of it back; it only classifies it into one of a few fixed,
    safe sentences. The caller is responsible for logging the raw reason, at INFO.
    """
    lowered = (reason or "").lower()
    if "deleted" in lowered:
        text = "The receipt was deleted. Scan it again if you still have it."
    elif (
        "stale" in lowered
        or "queued again" in lowered
        or "stopped processing" in lowered
    ):
        text = "The reader is busy, try again later. It is saved; retry it on the iPad."
    else:
        text = "Couldn't read the receipt. It is saved; retry it on the iPad."
    return text[:TELEGRAM_TEXT_LIMIT]


def _store(receipt: ReceiptResponse) -> str:
    chain = receipt.store_chain
    if not chain:
        return "Unknown store"
    return _STORE_NAMES.get(chain, chain[:1].upper() + chain[1:])


def _date(receipt: ReceiptResponse) -> str:
    day = receipt.purchase_date
    if day is None:
        return "date not read"
    return f"{day.day}.{day.month}.{day.year}"


def _short(name: str) -> str:
    return name if len(name) <= MAX_NAME_CHARS else name[: MAX_NAME_CHARS - 1] + "…"


def result_text(receipt: ReceiptResponse) -> str:
    """E.g. ``S-group, 2.1.2026: 49 items, 3 matched. New: A, B, … (+38). Review on the iPad.``"""
    items = receipt.items
    matched = sum(1 for item in items if item.product_id is not None)
    noun = "item" if len(items) == 1 else "items"
    lines = [
        f"{_store(receipt)}, {_date(receipt)}: {len(items)} {noun}, {matched} matched."
    ]

    new_names = [_short(item.name) for item in items if item.product_id is None]
    if new_names:
        shown = ", ".join(new_names[:MAX_NEW_NAMES])
        rest = len(new_names) - MAX_NEW_NAMES
        lines.append(f"New: {shown}, … (+{rest})" if rest > 0 else f"New: {shown}")

    if receipt.extraction_method == "heuristic":
        lines.append(
            "Read without the AI model; names are as printed. "
            "Retry on the iPad when the model is back."
        )
    lines.append("Review on the iPad.")
    return "\n".join(lines)[:TELEGRAM_TEXT_LIMIT]


def review_url(public_url: str | None, receipt_id: UUID) -> str | None:
    """The receipt's review page on the PWA, or None when no public URL is configured."""
    base = (public_url or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/receipt/{receipt_id}"


def with_review_link(text: str, public_url: str | None, receipt_id: UUID) -> str:
    """``text`` ending with a line linking to the review page (CL5), within the limit."""
    url = review_url(public_url, receipt_id)
    if url is None:
        return text
    link = "\n" + url
    return text[: TELEGRAM_TEXT_LIMIT - len(link)] + link


def duplicate_text(receipt: ReceiptResponse) -> str:
    status = receipt.processing_status
    if status in (ReceiptStatus.COMPLETED, ReceiptStatus.CONFIRMED):
        return "Already received.\n" + result_text(receipt)
    if status == ReceiptStatus.FAILED:
        return "Already received, but it could not be read. Retry it on the iPad."
    return "Already received, it is still being read."


# Commands (CL3)

MAX_CANDIDATES = 5
_PRIORITY_NOTES = {"urgent": " (urgent)", "low": " (low)"}


def amount_text(value: Decimal) -> str:
    """``2.00`` as ``2``, ``1.50`` as ``1.5``: no trailing zeros, no exponent."""
    text = format(Decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def shopping_list_text(rows: Sequence[Any]) -> str:
    """Numbered open lines, ``1. Milk — 2 l (urgent)``, in the order given."""
    lines = [
        f"{number}. {_short(str(row.name))} — {amount_text(row.quantity)} {row.unit}"
        f"{_PRIORITY_NOTES.get(str(row.priority), '')}"
        for number, row in enumerate(rows, start=1)
    ]
    return "\n".join(lines)[:TELEGRAM_TEXT_LIMIT]


def list_empty_text() -> str:
    return "The shopping list is empty."


def added_text(name: str, quantity: Decimal, unit: str, *, linked: bool) -> str:
    link = (
        "linked to the product"
        if linked
        else "not linked to a product, so a restock will not tick it off"
    )
    return f"Added {_short(name)} — {amount_text(quantity)} {unit} ({link})."


def add_usage_text() -> str:
    return "Say what to add, e.g. /add milk or /add milk 2 l."


def unknown_unit_text(unit: str) -> str:
    return f"Unknown unit {_short(unit)!r}. Use l, dl, cl, ml, kg, g, tsp, tbsp or pcs."


def bought_usage_text() -> str:
    return "Say which line, e.g. /bought 2 (the number from /list) or /bought milk."


def bought_text(name: str) -> str:
    return f"Ticked {_short(name)} as bought."


def list_changed_text() -> str:
    return "The list has changed since your last /list. Send /list and try again."


def no_such_number_text(number: int, count: int) -> str:
    noun = "line" if count == 1 else "lines"
    return f"There is no line {number}: your last /list had {count} {noun}."


def bought_not_found_text(name: str) -> str:
    return f"Nothing on the list is called {_short(name)!r}. Send /list to see it."


def bought_ambiguous_text(names: Sequence[str]) -> str:
    shown = ", ".join(_short(name) for name in names[:MAX_CANDIDATES])
    rest = len(names) - MAX_CANDIDATES
    more = f", … (+{rest})" if rest > 0 else ""
    return f"Several lines match: {shown}{more}. Send /list and tick one by number."


def used_usage_text() -> str:
    return "Say what was used, e.g. /used eggs or /used milk 2 dl."


def used_text(name: str, before: Decimal, after: Decimal, unit: str) -> str:
    return f"Used {_short(name)}: {amount_text(before)} → {amount_text(after)} {unit}."


def used_needs_amount_text(name: str, unit: str) -> str:
    return (
        f"How much {_short(name)} was used? "
        f"Add the amount, e.g. /used {_short(name).lower()} 2 {unit}."
    )


def not_found_text(name: str) -> str:
    return f"No product is called {_short(name)!r}. Nothing changed."


def ambiguous_text(name: str, candidates: Sequence[str]) -> str:
    lines = [f"Which one is {_short(name)!r}? Nothing changed. Try one of:"]
    lines.extend(f"- {_short(candidate)}" for candidate in candidates[:MAX_CANDIDATES])
    return "\n".join(lines)


def insufficient_text(name: str, available: Decimal, unit: str) -> str:
    return (
        f"Only {amount_text(available)} {unit} of {_short(name)} is in stock. "
        "Nothing changed."
    )


def invalid_consume_text(reason: str) -> str:
    return f"Nothing changed: {reason[:200]}"
