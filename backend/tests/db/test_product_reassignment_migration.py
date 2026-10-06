"""CL8 L0: item provenance columns, `product_reassignment`, and the `receipt_line_id` backfill."""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"


def _load_migration():
    (path,) = VERSIONS.glob("*_product_reassignment.py")
    spec = importlib.util.spec_from_file_location(
        "product_reassignment_migration", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_telegram_receipt_message(self) -> None:
        assert _load_migration().down_revision == "d8f3a61c2b57"

    def test_it_is_the_only_head(self) -> None:
        (head,) = _script().get_heads()
        assert head == _load_migration().revision


async def _item(
    db: AsyncSession, product: ProductMaster, receipt: Receipt, index: int | None
) -> InventoryItem:
    item = InventoryItem(
        product_master_id=product.id,
        receipt_id=receipt.id,
        receipt_line_index=index,
        initial_quantity=Decimal("1"),
        current_quantity=Decimal("1"),
        unit="pcs",
        status="sealed",
        expiry_date=date(2026, 10, 10),
        location="main_fridge",
    )
    db.add(item)
    await db.flush()
    return item


class TestTheBackfill:
    async def test_receipt_line_id_comes_from_the_line_at_the_index(
        self, db_session: AsyncSession
    ) -> None:
        await seed_categories(db_session)
        product = ProductMaster(
            canonical_name="Karelian pie",
            category="ready_meals",
            storage_type="refrigerator",
            default_shelf_life_days=3,
            unit_type="count",
            default_unit="pcs",
            default_quantity=Decimal("1"),
        )
        db_session.add(product)
        line_id = uuid4()
        receipt = Receipt(
            image_path="x.jpg",
            ocr_structured={
                "lines": [
                    {"line_id": str(line_id), "name": "VUOKSEN RIISIPIIRAKKA"},
                    {"line_id": "not-a-uuid", "name": "KARJALANPAISTI"},
                ]
            },
        )
        db_session.add(receipt)
        await db_session.flush()
        filled = await _item(db_session, product, receipt, 0)
        malformed = await _item(db_session, product, receipt, 1)
        out_of_range = await _item(db_session, product, receipt, 7)
        no_line = await _item(db_session, product, receipt, None)
        await db_session.commit()

        await db_session.run_sync(
            lambda session: _load_migration().backfill(session.connection())
        )

        found = dict(
            (
                await db_session.execute(
                    select(InventoryItem.id, InventoryItem.receipt_line_id)
                )
            ).all()
        )
        assert found[filled.id] == line_id
        assert isinstance(found[filled.id], UUID)
        assert found[malformed.id] is None
        assert found[out_of_range.id] is None
        assert found[no_line.id] is None
