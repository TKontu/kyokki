"""Q26 (item provenance) and Q28 (receipt audit): read models, service layer."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.services import receipt_audit
from app.services.generic_products import build_inventory_item

PURCHASED = date(2026, 9, 26)


async def _receipt(db: AsyncSession, *, status: str, **fields) -> Receipt:
    fields.setdefault("image_path", f"data/receipts/{uuid4()}.jpg")
    fields.setdefault("store_chain", "s-group")
    fields.setdefault("purchase_date", PURCHASED)
    receipt = Receipt(
        id=uuid4(),
        processing_status=status,
        items_extracted=0,
        items_matched=0,
        **fields,
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)
    return receipt


class TestGetItemSource:
    """Q26: which printed line an inventory item came from."""

    async def test_unknown_item_raises(self, db_session: AsyncSession):
        with pytest.raises(receipt_audit.ItemNotFound):
            await receipt_audit.get_item_source(db_session, uuid4())

    async def test_item_without_receipt_is_none(
        self, db_session: AsyncSession, sample_product: ProductMaster
    ):
        item = build_inventory_item(
            sample_product, quantity=Decimal("1"), purchase_date=PURCHASED
        )
        db_session.add(item)
        await db_session.commit()

        source = await receipt_audit.get_item_source(db_session, item.id)

        assert source is None

    async def test_item_with_a_line_returns_it(
        self, db_session: AsyncSession, sample_product: ProductMaster
    ):
        receipt = await _receipt(db_session, status="confirmed")
        item = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        item.receipt_line_index = 2
        item.receipt_line_text = "KOKKIKARTANO KERMAINEN LOHIKEITTO"
        db_session.add(item)
        await db_session.commit()

        source = await receipt_audit.get_item_source(db_session, item.id)

        assert source is not None
        assert source.receipt_id == receipt.id
        assert source.store_chain == "s-group"
        assert source.purchase_date == PURCHASED
        assert source.line_index == 2
        assert source.line_text == "KOKKIKARTANO KERMAINEN LOHIKEITTO"

    async def test_item_confirmed_before_line_tracking_has_no_line(
        self, db_session: AsyncSession, sample_product: ProductMaster
    ):
        """No backfill (spec): an item from before Q26 shows the receipt, not a line."""
        receipt = await _receipt(db_session, status="confirmed")
        item = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        db_session.add(item)
        await db_session.commit()

        source = await receipt_audit.get_item_source(db_session, item.id)

        assert source is not None
        assert source.receipt_id == receipt.id
        assert source.line_index is None
        assert source.line_text is None


class TestBuildReceiptAudit:
    """Q28: everything the cook can check about how a receipt became stock."""

    async def test_unknown_receipt_raises(self, db_session: AsyncSession):
        with pytest.raises(receipt_audit.ReceiptNotFound):
            await receipt_audit.build_receipt_audit(db_session, uuid4())

    async def test_not_yet_confirmed_lines_are_pending(self, db_session: AsyncSession):
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_raw_text="MAITO 1,49\n",
            ocr_structured={
                "lines": [{"name": "VALIO MAITO 1L", "price": 1.49}],
                "raw_completion": '{"lines": []}',
            },
        )

        audit = await receipt_audit.build_receipt_audit(db_session, receipt.id)

        assert audit.processing_status == "completed"
        assert audit.ocr_raw_text == "MAITO 1,49\n"
        assert audit.model_raw_answer == '{"lines": []}'
        # The fixture's file was never actually written to disk
        assert audit.file_content_type is None
        assert len(audit.lines) == 1
        assert audit.lines[0] == receipt_audit.ReceiptAuditLine(
            index=0, name="VALIO MAITO 1L", price=1.49, outcome="pending", items=[]
        )
        assert audit.unlinked_items == []

    async def test_confirmed_lines_show_their_outcome(
        self, db_session: AsyncSession, sample_product: ProductMaster
    ):
        receipt = await _receipt(
            db_session,
            status="confirmed",
            ocr_structured={
                "lines": [
                    {"name": "VALIO MAITO 1L", "price": 1.49},
                    {"name": "MUOVIKASSI", "price": 0.10, "non_food": True},
                    {"name": "PIRKKA HERNEET", "price": 0.99},
                ]
            },
        )
        stocked = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        stocked.receipt_line_index = 0
        stocked.receipt_line_text = "VALIO MAITO 1L"
        db_session.add(stocked)
        await db_session.commit()

        audit = await receipt_audit.build_receipt_audit(db_session, receipt.id)

        outcomes = {line.index: line.outcome for line in audit.lines}
        assert outcomes == {0: "stocked", 1: "household", 2: "skipped"}
        stocked_line = next(line for line in audit.lines if line.index == 0)
        assert len(stocked_line.items) == 1
        assert stocked_line.items[0].id == stocked.id
        assert stocked_line.items[0].product_id == sample_product.id
        assert stocked_line.items[0].product_name == sample_product.canonical_name
        assert audit.unlinked_items == []

    async def test_legacy_items_with_no_line_index_are_unlinked(
        self, db_session: AsyncSession, sample_product: ProductMaster
    ):
        """Pre-Q26 confirms: no line index exists, so the item cannot be attributed."""
        receipt = await _receipt(
            db_session,
            status="confirmed",
            ocr_structured={"lines": [{"name": "VALIO MAITO 1L", "price": 1.49}]},
        )
        legacy_item = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        db_session.add(legacy_item)
        await db_session.commit()

        audit = await receipt_audit.build_receipt_audit(db_session, receipt.id)

        assert audit.lines[0].outcome == "skipped"
        assert audit.lines[0].items == []
        assert len(audit.unlinked_items) == 1
        assert audit.unlinked_items[0].id == legacy_item.id

    async def test_tolerates_receipts_without_a_lines_key(
        self, db_session: AsyncSession
    ):
        """Receipts written before MVP-R1b store `products`, not `lines` (H04-style tolerance)."""
        receipt = await _receipt(
            db_session, status="completed", ocr_structured={"products": []}
        )

        audit = await receipt_audit.build_receipt_audit(db_session, receipt.id)

        assert audit.lines == []
        assert audit.model_raw_answer is None

    async def test_file_content_type_reflects_the_stored_file(
        self, db_session: AsyncSession, tmp_path, monkeypatch
    ):
        upload_dir = tmp_path / "data" / "receipts"
        upload_dir.mkdir(parents=True)
        monkeypatch.setattr(receipt_audit, "UPLOAD_DIR", upload_dir.resolve())
        target = upload_dir / "abc.png"
        target.write_bytes(b"fake")
        receipt = await _receipt(db_session, status="completed", image_path=str(target))

        audit = await receipt_audit.build_receipt_audit(db_session, receipt.id)

        assert audit.file_content_type == "image/png"


class TestResolveReceiptFile:
    """The file endpoint must not become a path-traversal or arbitrary-file read."""

    def test_a_file_inside_the_upload_dir_resolves(self, tmp_path, monkeypatch):
        upload_dir = tmp_path / "data" / "receipts"
        upload_dir.mkdir(parents=True)
        target = upload_dir / "abc.jpg"
        target.write_bytes(b"fake")
        monkeypatch.setattr(receipt_audit, "UPLOAD_DIR", upload_dir.resolve())

        receipt = Receipt(
            id=uuid4(), image_path=str(target), processing_status="completed"
        )

        resolved = receipt_audit.resolve_receipt_file(receipt)

        assert resolved == target.resolve()

    def test_a_path_outside_the_upload_dir_is_refused(self, tmp_path, monkeypatch):
        upload_dir = tmp_path / "data" / "receipts"
        upload_dir.mkdir(parents=True)
        monkeypatch.setattr(receipt_audit, "UPLOAD_DIR", upload_dir.resolve())

        outside = tmp_path / "secret.txt"
        outside.write_text("nope")
        receipt = Receipt(
            id=uuid4(), image_path=str(outside), processing_status="completed"
        )

        assert receipt_audit.resolve_receipt_file(receipt) is None

    def test_traversal_via_dotdot_is_refused(self, tmp_path, monkeypatch):
        upload_dir = tmp_path / "data" / "receipts"
        upload_dir.mkdir(parents=True)
        monkeypatch.setattr(receipt_audit, "UPLOAD_DIR", upload_dir.resolve())

        (tmp_path / "secret.txt").write_text("nope")
        receipt = Receipt(
            id=uuid4(),
            image_path=str(upload_dir / ".." / "secret.txt"),
            processing_status="completed",
        )

        assert receipt_audit.resolve_receipt_file(receipt) is None

    def test_a_missing_file_is_refused(self, tmp_path, monkeypatch):
        upload_dir = tmp_path / "data" / "receipts"
        upload_dir.mkdir(parents=True)
        monkeypatch.setattr(receipt_audit, "UPLOAD_DIR", upload_dir.resolve())

        receipt = Receipt(
            id=uuid4(),
            image_path=str(upload_dir / "gone.jpg"),
            processing_status="completed",
        )

        assert receipt_audit.resolve_receipt_file(receipt) is None


class TestContentTypeFor:
    @pytest.mark.parametrize(
        ("suffix", "expected"),
        [
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".png", "image/png"),
            (".webp", "image/webp"),
            (".pdf", "application/pdf"),
            (".bin", "application/octet-stream"),
        ],
    )
    def test_known_and_unknown_suffixes(self, suffix, expected):
        assert receipt_audit.content_type_for(Path(f"x{suffix}")) == expected
