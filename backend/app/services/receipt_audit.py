"""Q26 (item provenance) and Q28 (receipt audit).

Q26: which printed receipt line an inventory item came from, for the item's sheet.
Q28: everything the cook can check about how a receipt became stock - the original file, the
OCR text, the model's raw answer, and each printed line's outcome.

Everything above reads only. `record_stocked_lines` is the one write: a hard-deleted
`InventoryItem` leaves no trace of itself anywhere (no soft-delete column, no audit table),
so confirm's own stocked lines must be marked on the receipt itself, from the confirm
endpoint, or a line a cook already stocked and then removed reads back as `skipped` -
indistinguishable from one they genuinely left out (follow-up from round 2026-09-30-1).
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.schemas.receipt import (
    ItemSourceResponse,
    ReceiptAuditItemRef,
    ReceiptAuditLine,
    ReceiptAuditResponse,
    ReceiptLineOutcome,
    ReceiptStatus,
)

# Every receipt file is written under here (app/crud/receipt.py's `create_receipt`), relative
# to the process's working directory. Resolved once, so a crafted or stale `image_path` can be
# checked against it rather than trusted.
UPLOAD_DIR = Path("data/receipts").resolve()

CONTENT_TYPE_FOR_SUFFIX = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"


class ItemNotFound(LookupError):
    """No inventory item with that id."""


class ReceiptNotFound(LookupError):
    """No receipt with that id."""


async def record_stocked_lines(
    db: AsyncSession,
    receipt: Receipt,
    inventory_items: Sequence[tuple[InventoryItem, ProductMaster]],
) -> None:
    """Mark, on the receipt's own stored lines, which ones produced stock at confirm.

    Called once, right after confirm, from the confirm endpoint. Nothing else ever
    records this: an `InventoryItem` carries its `receipt_line_index` while it exists,
    but a hard delete removes the row outright (`crud.inventory_item.delete_inventory_item`
    does a plain `db.delete`, no soft-delete column, and nothing else logs it - unlike a
    discard, which only changes `status`). Without this mark, the audit view cannot tell
    "the cook never stocked this line" from "the cook stocked it and it is gone since" -
    both look identical once the item row is gone.

    A no-op, and no extra commit, when nothing changed (the common case: re-reading an
    already-marked line, or a receipt with no `lines` to mark).
    """
    structured = (
        receipt.ocr_structured if isinstance(receipt.ocr_structured, dict) else None
    )
    lines = structured.get("lines") if structured else None
    if not isinstance(lines, list):
        return

    changed = False
    for item, _product in inventory_items:
        index = cast("int | None", item.receipt_line_index)
        if index is None or not (0 <= index < len(lines)):
            continue
        line = lines[index]
        if isinstance(line, dict) and not line.get("stocked_at_confirm"):
            line["stocked_at_confirm"] = True
            changed = True

    if changed:
        flag_modified(receipt, "ocr_structured")
        await db.commit()


async def get_item_source(db: AsyncSession, item_id: UUID) -> ItemSourceResponse | None:
    """Where an item's receipt line came from (Q26), or None with no receipt.

    Raises:
        ItemNotFound: no inventory item with this id.
    """
    item = await db.get(InventoryItem, item_id)
    if item is None:
        raise ItemNotFound(f"Inventory item '{item_id}' not found")

    receipt_id = cast(UUID | None, item.receipt_id)
    if receipt_id is None:
        return None
    receipt = await db.get(Receipt, receipt_id)
    if receipt is None:
        return None

    return ItemSourceResponse(
        receipt_id=receipt_id,
        store_chain=cast("str | None", receipt.store_chain),
        purchase_date=cast("Any", receipt.purchase_date),
        line_text=cast("str | None", item.receipt_line_text),
        line_index=cast("int | None", item.receipt_line_index),
    )


def resolve_receipt_file(receipt: Receipt) -> Path | None:
    """The receipt's stored original, only if it resolves inside the upload directory.

    `receipt.image_path` is never client input, but a row from before this endpoint
    existed - or a compromised one - could still name a path anywhere, so every caller
    goes through this rather than opening the column's value directly (spec constraint:
    no path-traversal, no arbitrary-file read).
    """
    raw = cast(str, receipt.image_path) or ""
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None
    if not resolved.is_relative_to(UPLOAD_DIR):
        return None
    if not resolved.is_file():
        return None
    return resolved


def content_type_for(path: Path) -> str:
    """The `Content-Type` to serve a receipt file under, from its stored suffix."""
    return CONTENT_TYPE_FOR_SUFFIX.get(path.suffix.lower(), DEFAULT_CONTENT_TYPE)


def _raw_text(structured: dict[str, Any], key: str) -> str | None:
    raw = structured.get(key)
    return raw if isinstance(raw, str) else None


def _model_raw_answer(structured: dict[str, Any]) -> str | None:
    """The model's raw completion for this receipt, when one was stored (#131)."""
    return _raw_text(structured, "raw_completion")


def _model_raw_answer_retry(structured: dict[str, Any]) -> str | None:
    """The targeted re-read's raw completion (Q27), when the first read missed lines."""
    return _raw_text(structured, "raw_completion_retry")


async def _stocked_items(
    db: AsyncSession, receipt_id: UUID
) -> tuple[dict[int, list[ReceiptAuditItemRef]], list[ReceiptAuditItemRef]]:
    """Inventory items this receipt produced, grouped by the line they came from.

    Items with no line index (confirmed before Q26) come back separately: they cannot be
    attributed to any one line, so the audit lists them as their own section rather than
    guessing.
    """
    result = await db.execute(
        select(InventoryItem, ProductMaster.canonical_name)
        .join(ProductMaster, InventoryItem.product_master_id == ProductMaster.id)
        .where(InventoryItem.receipt_id == receipt_id)
    )
    by_index: dict[int, list[ReceiptAuditItemRef]] = {}
    unlinked: list[ReceiptAuditItemRef] = []
    for item, product_name in result.all():
        ref = ReceiptAuditItemRef(
            id=cast(UUID, item.id),
            product_id=cast("UUID | None", item.product_master_id),
            product_name=product_name,
        )
        index = cast("int | None", item.receipt_line_index)
        if index is None:
            unlinked.append(ref)
        else:
            by_index.setdefault(int(index), []).append(ref)
    return by_index, unlinked


async def build_receipt_audit(
    db: AsyncSession, receipt_id: UUID
) -> ReceiptAuditResponse:
    """Everything the cook can check about how a receipt became stock (Q28).

    Raises:
        ReceiptNotFound: no receipt with this id.
    """
    receipt = await db.get(Receipt, receipt_id)
    if receipt is None:
        raise ReceiptNotFound(f"Receipt '{receipt_id}' not found")

    structured: dict[str, Any] = (
        receipt.ocr_structured if isinstance(receipt.ocr_structured, dict) else {}
    )
    raw_lines = structured.get("lines")
    raw_lines = raw_lines if isinstance(raw_lines, list) else []

    confirmed = receipt.processing_status == ReceiptStatus.CONFIRMED
    stocked_by_index: dict[int, list[ReceiptAuditItemRef]] = {}
    unlinked_items: list[ReceiptAuditItemRef] = []
    if confirmed:
        stocked_by_index, unlinked_items = await _stocked_items(db, receipt_id)

    lines: list[ReceiptAuditLine] = []
    for index, raw_line in enumerate(raw_lines):
        if not isinstance(raw_line, dict) or not raw_line.get("name"):
            continue
        stocked = stocked_by_index.get(index)
        outcome: ReceiptLineOutcome
        if not confirmed:
            outcome = "pending"
        elif stocked:
            outcome = "stocked"
        elif raw_line.get("stocked_at_confirm"):
            # `record_stocked_lines` marked this line when it was confirmed; the item(s)
            # it produced are gone now (hard-deleted - nothing else leaves a trace), but
            # that is not the same as the cook having left the line out.
            outcome = "removed"
        elif raw_line.get("non_food") or raw_line.get("confirmed_non_food"):
            # `non_food`: the model's or a remembered name's guess at extraction time.
            # `confirmed_non_food`: the cook folded this line away *in this confirm*
            # (`receipt_confirm._mark_confirmed_non_food`) - a never-seen line has no
            # other record of that on this receipt.
            outcome = "household"
        else:
            outcome = "skipped"
        price = raw_line.get("price")
        hint = raw_line.get("reanalyse_hint")
        lines.append(
            ReceiptAuditLine(
                index=index,
                name=str(raw_line["name"]),
                price=float(price) if isinstance(price, int | float) else None,
                outcome=outcome,
                items=stocked or [],
                reanalysed=bool(raw_line.get("reanalysed")),
                reanalyse_hint=hint if isinstance(hint, str) else None,
            )
        )

    file_path = resolve_receipt_file(receipt)

    return ReceiptAuditResponse(
        id=cast(UUID, receipt.id),
        store_chain=cast("str | None", receipt.store_chain),
        purchase_date=cast("Any", receipt.purchase_date),
        processing_status=cast(ReceiptStatus, receipt.processing_status),
        created_at=cast("Any", receipt.created_at),
        ocr_raw_text=cast("str | None", receipt.ocr_raw_text),
        model_raw_answer=_model_raw_answer(structured),
        model_raw_answer_retry=_model_raw_answer_retry(structured),
        file_content_type=content_type_for(file_path) if file_path else None,
        lines=lines,
        unlinked_items=unlinked_items,
    )
