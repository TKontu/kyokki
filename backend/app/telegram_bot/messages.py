"""Reply texts. Plain text only (no parse mode), so product names need no escaping."""

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
        "You get a summary when a receipt has been read. Review it on the iPad."
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
    detail = (reason or "unknown error").strip()
    if len(detail) > 200:
        detail = detail[:199] + "…"
    return f"Could not read this receipt: {detail}\nIt is saved; retry it on the iPad."


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


def duplicate_text(receipt: ReceiptResponse) -> str:
    status = receipt.processing_status
    if status in (ReceiptStatus.COMPLETED, ReceiptStatus.CONFIRMED):
        return "Already received.\n" + result_text(receipt)
    if status == ReceiptStatus.FAILED:
        return "Already received, but it could not be read. Retry it on the iPad."
    return "Already received, it is still being read."
