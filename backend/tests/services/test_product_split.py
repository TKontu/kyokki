"""Splitting wrongly joined items off a product, and undoing it (CL8 L2).

`docs/PRODUCT_IDENTITY_SPEC.md`, "Undoing a wrong join: split". The production case: the
stew (`KARJALANPAISTI`) was joined to the rice-pie product, so the pie learned the stew's
shelf life and the next stew line went to the pie by alias.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product_name import learn_product_name
from app.db.seed_categories import seed_categories
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.product_reassignment import ProductReassignment
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.services.product_resolution import ProductResolution, ResolvableLine
from app.services.product_split import (
    InvalidSplit,
    NameExists,
    NewProduct,
    StaleReassignment,
    UnknownProduct,
    UnknownReassignment,
    product_sources,
    split_items,
    undo_split,
)

TODAY = date.today()
CHAIN = "s-group"
PIE_LINE = "VUOKSEN RIISIPIIRAKKA 15KPL"
STEW_LINE = "KARJALANPAISTI"
STEW_GENERIC = "Karelian beef stew"


@dataclass
class Kitchen:
    """The pie product holding three pie purchases and three stew purchases."""

    pie: ProductMaster
    pie_items: list[InventoryItem] = field(default_factory=list)
    stew_items: list[InventoryItem] = field(default_factory=list)
    hand_added: InventoryItem | None = None

    @property
    def pie_calculated(self) -> InventoryItem:
        return self.pie_items[-1]

    @property
    def stew_calculated(self) -> InventoryItem:
        return self.stew_items[-1]

    @property
    def stew_ids(self) -> list[UUID]:
        return [UUID(str(item.id)) for item in self.stew_items]


async def make_receipt(db: AsyncSession, bought: date) -> Receipt:
    receipt = Receipt(
        image_path=f"{uuid4()}.jpg",
        store_chain=CHAIN,
        purchase_date=bought,
        processing_status="confirmed",
        ocr_structured={
            "lines": [
                {
                    "line_id": str(uuid4()),
                    "name": PIE_LINE,
                    "generic_name": "Karelian pie",
                },
                {
                    "line_id": str(uuid4()),
                    "name": STEW_LINE,
                    "generic_name": STEW_GENERIC,
                    "shelf_life_days": 5,
                },
            ]
        },
    )
    db.add(receipt)
    await db.flush()
    return receipt


async def make_item(
    db: AsyncSession,
    product: ProductMaster,
    *,
    bought: date,
    keeps: int,
    source: str,
    line: int | None,
    status: str = "sealed",
) -> InventoryItem:
    receipt = await make_receipt(db, bought) if line is not None else None
    item = InventoryItem(
        product_master_id=product.id,
        receipt_id=receipt.id if receipt else None,
        receipt_line_index=line,
        receipt_line_text=(PIE_LINE, STEW_LINE)[line] if line is not None else None,
        initial_quantity=Decimal("1"),
        current_quantity=Decimal("0") if status == "empty" else Decimal("1"),
        unit="pcs",
        status=status,
        purchase_date=bought,
        expiry_date=bought + timedelta(days=keeps),
        expiry_source=source,
        location="main_fridge",
    )
    db.add(item)
    await db.flush()
    return item


async def log_use(db: AsyncSession, item: InventoryItem) -> None:
    db.add(
        ConsumptionLog(
            inventory_item_id=item.id,
            product_master_id=item.product_master_id,
            action="use_partial",
            quantity_consumed=Decimal("0.5"),
            quantity_after=Decimal("0.5"),
            unit="pcs",
        )
    )
    await db.flush()


async def build_kitchen(db: AsyncSession) -> Kitchen:
    await seed_categories(db)
    pie = ProductMaster(
        canonical_name="Karelian pie",
        category="ready_meals",
        storage_type="refrigerator",
        # Learned from all five of the cook's dates below: the median of 2,6,2,6,2
        default_shelf_life_days=2,
        shelf_life_source="cook",
        unit_type="count",
        default_unit="pcs",
        default_quantity=Decimal("1"),
    )
    db.add(pie)
    await db.flush()
    await learn_product_name(db, pie, "Karelian pie", "canonical")
    # The stew line's generic name, taught by the model when the stew was confirmed
    await learn_product_name(db, pie, STEW_GENERIC, "model")
    db.add_all(
        [
            StoreProductAlias(
                product_master_id=pie.id,
                store_chain=CHAIN,
                receipt_name=PIE_LINE,
                source="cook",
                manually_verified=True,
                confidence_score=1.0,
                occurrence_count=3,
            ),
            StoreProductAlias(
                product_master_id=pie.id,
                store_chain=CHAIN,
                receipt_name=STEW_LINE,
                source="model",
                manually_verified=False,
                confidence_score=0.5,
                occurrence_count=2,
            ),
        ]
    )
    kitchen = Kitchen(pie=pie)
    for days_ago in (10, 8, 6):
        kitchen.pie_items.append(
            await make_item(
                db,
                pie,
                bought=TODAY - timedelta(days=days_ago),
                keeps=2,
                source="manual",
                line=0,
                status="empty",
            )
        )
    kitchen.pie_items.append(
        await make_item(db, pie, bought=TODAY, keeps=2, source="calculated", line=0)
    )
    for days_ago in (9, 7):
        kitchen.stew_items.append(
            await make_item(
                db,
                pie,
                bought=TODAY - timedelta(days=days_ago),
                keeps=6,
                source="manual",
                line=1,
                status="empty",
            )
        )
    kitchen.stew_items.append(
        await make_item(
            db,
            pie,
            bought=TODAY - timedelta(days=1),
            keeps=2,
            source="calculated",
            line=1,
        )
    )
    kitchen.hand_added = await make_item(
        db, pie, bought=TODAY, keeps=2, source="calculated", line=None
    )
    await log_use(db, kitchen.pie_calculated)
    await log_use(db, kitchen.stew_calculated)
    await log_use(db, kitchen.stew_items[0])
    await db.commit()
    return kitchen


@pytest.fixture
async def kitchen(db_session: AsyncSession) -> Kitchen:
    return await build_kitchen(db_session)


async def reload(db: AsyncSession, model: Any, row_id: Any) -> Any:
    return await db.get(model, row_id, populate_existing=True)


async def split_stew(db: AsyncSession, kitchen: Kitchen, **kwargs: Any):
    return await split_items(
        db,
        UUID(str(kitchen.pie.id)),
        kitchen.stew_ids,
        new=NewProduct(name="Karelian stew", category="ready_meals"),
        **kwargs,
    )


async def snapshot(db: AsyncSession) -> dict[str, Any]:
    """Everything a split touches, to compare a round trip against."""
    db.expire_all()
    items = {
        row.id: (row.product_master_id, row.expiry_date, row.expiry_source)
        for row in (await db.execute(select(InventoryItem))).scalars()
    }
    logs = {
        row.id: row.product_master_id
        for row in (await db.execute(select(ConsumptionLog))).scalars()
    }
    aliases = {
        (row.store_chain, row.receipt_name): (
            row.product_master_id,
            row.source,
            row.manually_verified,
            row.confidence_score,
            row.occurrence_count,
        )
        for row in (await db.execute(select(StoreProductAlias))).scalars()
    }
    names = {
        row.name: (row.product_master_id, row.source)
        for row in (await db.execute(select(ProductName))).scalars()
    }
    products = {
        row.id: (row.canonical_name, row.default_shelf_life_days, row.shelf_life_source)
        for row in (await db.execute(select(ProductMaster))).scalars()
    }
    return {
        "items": items,
        "logs": logs,
        "aliases": aliases,
        "names": names,
        "products": products,
    }


class TestSplitRestoresBothShelfLives:
    async def test_split_restores_both_products_shelf_lives(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)

        pie = await reload(db_session, ProductMaster, kitchen.pie.id)
        stew = await reload(db_session, ProductMaster, result.target.id)
        assert result.target_created is True
        assert stew.canonical_name == "Karelian stew"
        assert stew.category == "ready_meals"
        assert (pie.default_shelf_life_days, pie.shelf_life_source) == (2, "cook")
        assert (stew.default_shelf_life_days, stew.shelf_life_source) == (6, "cook")

        # Calculated items re-dated on both, each by its own product's shelf life
        moved = await reload(db_session, InventoryItem, kitchen.stew_calculated.id)
        assert moved.product_master_id == stew.id
        assert moved.expiry_date == TODAY - timedelta(days=1) + timedelta(days=6)
        stayed = await reload(db_session, InventoryItem, kitchen.pie_calculated.id)
        assert stayed.expiry_date == TODAY + timedelta(days=2)

        assert result.source_shelf_life.days == 2
        assert result.source_shelf_life.source == "cook"
        assert result.source_shelf_life.observations_left == 3
        assert sorted(result.moved_item_ids) == sorted(kitchen.stew_ids)

    async def test_the_source_learns_when_the_moved_dates_were_holding_it(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        """Splitting the pies off instead leaves the stew learning 6, the pies 2."""
        pie_ids = [UUID(str(item.id)) for item in kitchen.pie_items]
        result = await split_items(
            db_session,
            UUID(str(kitchen.pie.id)),
            pie_ids,
            new=NewProduct(name="Rice pie", category="ready_meals"),
        )

        source = await reload(db_session, ProductMaster, kitchen.pie.id)
        target = await reload(db_session, ProductMaster, result.target.id)
        assert source.default_shelf_life_days == 6
        assert target.default_shelf_life_days == 2
        assert result.source_shelf_life.days == 6
        assert result.source_shelf_life.observations_left == 2


class TestHistoryFollows:
    async def test_consumption_logs_follow_their_items(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)

        per_product = dict(
            (
                await db_session.execute(
                    select(ConsumptionLog.product_master_id, func.count()).group_by(
                        ConsumptionLog.product_master_id
                    )
                )
            ).all()
        )
        assert per_product == {kitchen.pie.id: 1, result.target.id: 2}

    async def test_consumed_items_move_too(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)

        used_up = await reload(db_session, InventoryItem, kitchen.stew_items[0].id)
        assert used_up.status == "empty"
        assert used_up.product_master_id == result.target.id


class TestKeysFollow:
    async def test_the_next_receipt_resolves_the_printed_name_to_the_target(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)

        resolved = await ProductResolution(db_session).resolve(
            [ResolvableLine(line_id="next", printed=STEW_LINE, generic="Karelian pie")],
            chain=CHAIN,
            allow_model=False,
        )
        assert resolved["next"].product is not None
        assert resolved["next"].product.id == result.target.id
        assert resolved["next"].source == "alias"
        assert resolved["next"].verified is True

        alias = (
            await db_session.execute(
                select(StoreProductAlias).where(
                    StoreProductAlias.receipt_name == STEW_LINE
                )
            )
        ).scalar_one()
        assert (alias.source, alias.manually_verified) == ("cook", True)
        assert result.moved_keys[0].kind == "alias"
        assert {(k.kind, k.value, k.store_chain) for k in result.moved_keys} == {
            ("alias", STEW_LINE, CHAIN),
            ("name", "karelian beef stew", None),
        }

    async def test_the_pie_keeps_its_own_alias_and_canonical_name(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        await split_stew(db_session, kitchen)

        pie_alias = (
            await db_session.execute(
                select(StoreProductAlias).where(
                    StoreProductAlias.receipt_name == PIE_LINE
                )
            )
        ).scalar_one()
        assert pie_alias.product_master_id == kitchen.pie.id
        canonical = (
            await db_session.execute(
                select(ProductName).where(ProductName.name == "karelian pie")
            )
        ).scalar_one()
        assert canonical.product_master_id == kitchen.pie.id

    async def test_a_model_name_from_the_moved_line_is_forgotten(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        await split_stew(db_session, kitchen)

        forgotten = (
            await db_session.execute(
                select(ProductName).where(ProductName.name == "karelian beef stew")
            )
        ).scalar_one_or_none()
        assert forgotten is None

    async def test_a_cook_name_from_the_moved_line_is_kept(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        name = (
            await db_session.execute(
                select(ProductName).where(ProductName.name == "karelian beef stew")
            )
        ).scalar_one()
        name.source = "cook"
        await db_session.commit()

        await split_stew(db_session, kitchen)

        kept = await reload(db_session, ProductName, name.id)
        assert kept is not None
        assert kept.product_master_id == kitchen.pie.id

    async def test_move_keys_false_leaves_the_keys(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        before = await snapshot(db_session)

        result = await split_stew(db_session, kitchen, move_keys=False)

        after = await snapshot(db_session)
        assert after["aliases"] == before["aliases"]
        assert (
            after["names"]["karelian beef stew"]
            == before["names"]["karelian beef stew"]
        )
        assert result.moved_keys == []

    async def test_a_missing_alias_is_created_for_the_target(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        alias = (
            await db_session.execute(
                select(StoreProductAlias).where(
                    StoreProductAlias.receipt_name == STEW_LINE
                )
            )
        ).scalar_one()
        await db_session.delete(alias)
        await db_session.commit()

        result = await split_stew(db_session, kitchen)

        created = (
            await db_session.execute(
                select(StoreProductAlias).where(
                    StoreProductAlias.receipt_name == STEW_LINE
                )
            )
        ).scalar_one()
        assert created.product_master_id == result.target.id
        assert (created.source, created.manually_verified) == ("cook", True)


class TestRefusals:
    async def test_a_new_name_that_is_already_a_product_name(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        with pytest.raises(NameExists) as caught:
            await split_items(
                db_session,
                UUID(str(kitchen.pie.id)),
                kitchen.stew_ids,
                new=NewProduct(name="  karelian PIE ", category="ready_meals"),
            )
        assert caught.value.product_id == kitchen.pie.id
        assert caught.value.name == "Karelian pie"

    async def test_a_model_taught_name_counts_as_existing(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        with pytest.raises(NameExists):
            await split_items(
                db_session,
                UUID(str(kitchen.pie.id)),
                kitchen.stew_ids,
                new=NewProduct(name=STEW_GENERIC, category="ready_meals"),
            )

    @pytest.mark.parametrize(
        "case",
        ["empty", "foreign", "unknown_item", "same_target", "category", "name"],
    )
    async def test_invalid_requests_change_nothing(
        self, db_session: AsyncSession, kitchen: Kitchen, case: str
    ) -> None:
        other = ProductMaster(
            canonical_name="Rye bread",
            category="bread",
            storage_type="pantry",
            default_shelf_life_days=5,
            unit_type="count",
            default_unit="pcs",
        )
        db_session.add(other)
        await db_session.flush()
        foreign = await make_item(
            db_session, other, bought=TODAY, keeps=5, source="calculated", line=None
        )
        await db_session.commit()
        before = await snapshot(db_session)

        pie_id = UUID(str(kitchen.pie.id))
        new = NewProduct(name="Karelian stew", category="ready_meals")
        kwargs: dict[str, Any] = {"new": new}
        ids = kitchen.stew_ids
        if case == "empty":
            ids = []
        elif case == "foreign":
            ids = [*ids, UUID(str(foreign.id))]
        elif case == "unknown_item":
            ids = [*ids, uuid4()]
        elif case == "same_target":
            kwargs = {"target_product_id": pie_id}
        elif case == "category":
            kwargs = {"new": NewProduct(name="Karelian stew", category="nope")}
        elif case == "name":
            kwargs = {"new": NewProduct(name="   ", category="ready_meals")}

        with pytest.raises(InvalidSplit):
            await split_items(db_session, pie_id, ids, **kwargs)

        assert await snapshot(db_session) == before

    async def test_unknown_source_and_target(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        with pytest.raises(UnknownProduct):
            await split_items(
                db_session,
                uuid4(),
                kitchen.stew_ids,
                new=NewProduct(name="Karelian stew", category="ready_meals"),
            )
        with pytest.raises(UnknownProduct):
            await split_items(
                db_session,
                UUID(str(kitchen.pie.id)),
                kitchen.stew_ids,
                target_product_id=uuid4(),
            )


class TestUndo:
    async def test_undo_restores_exactly_and_deletes_the_created_product(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        before = await snapshot(db_session)
        result = await split_stew(db_session, kitchen)

        undone = await undo_split(db_session, result.reassignment_id)

        assert sorted(undone.restored_item_ids) == sorted(kitchen.stew_ids)
        after = await snapshot(db_session)
        assert after == before
        assert await db_session.get(ProductMaster, result.target.id) is None
        record = await reload(db_session, ProductReassignment, result.reassignment_id)
        assert record.undone_at is not None

    async def test_undo_into_an_existing_target_restores_its_shelf_life(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        stew = ProductMaster(
            canonical_name="Beef stew",
            category="ready_meals",
            storage_type="refrigerator",
            default_shelf_life_days=4,
            shelf_life_source="model",
            unit_type="count",
            default_unit="pcs",
        )
        db_session.add(stew)
        await db_session.commit()
        before = await snapshot(db_session)

        result = await split_items(
            db_session,
            UUID(str(kitchen.pie.id)),
            kitchen.stew_ids,
            target_product_id=UUID(str(stew.id)),
        )
        assert result.target_created is False
        learned = await reload(db_session, ProductMaster, stew.id)
        assert (learned.default_shelf_life_days, learned.shelf_life_source) == (
            6,
            "cook",
        )

        await undo_split(db_session, result.reassignment_id)

        assert await snapshot(db_session) == before

    async def test_undo_twice_is_stale(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)
        await undo_split(db_session, result.reassignment_id)

        with pytest.raises(StaleReassignment):
            await undo_split(db_session, result.reassignment_id)

    async def test_an_item_moved_since_makes_it_stale(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)
        await split_items(
            db_session,
            UUID(str(result.target.id)),
            [kitchen.stew_ids[0]],
            new=NewProduct(name="Beef casserole", category="ready_meals"),
        )

        with pytest.raises(StaleReassignment):
            await undo_split(db_session, result.reassignment_id)

    async def test_unknown_reassignment(self, db_session: AsyncSession) -> None:
        with pytest.raises(UnknownReassignment):
            await undo_split(db_session, uuid4())

    async def test_a_created_product_with_other_items_is_kept(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        result = await split_stew(db_session, kitchen)
        target = await reload(db_session, ProductMaster, result.target.id)
        extra = await make_item(
            db_session, target, bought=TODAY, keeps=6, source="calculated", line=None
        )
        await db_session.commit()

        await undo_split(db_session, result.reassignment_id)

        kept = await reload(db_session, ProductMaster, result.target.id)
        assert kept is not None
        still = await reload(db_session, InventoryItem, extra.id)
        assert still.product_master_id == result.target.id


class TestSources:
    async def test_groups_by_chain_and_printed_text(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        sources = await product_sources(db_session, UUID(str(kitchen.pie.id)))

        by_key = {source.key: source for source in sources}
        assert set(by_key) == {
            "line:s-group:karjalanpaisti",
            "line:s-group:vuoksen riisipiirakka 15kpl",
            "manual",
        }
        stew = by_key["line:s-group:karjalanpaisti"]
        assert stew.label == STEW_LINE
        assert stew.store_chain == CHAIN
        assert stew.kind == "receipt"
        assert stew.item_ids == [UUID(str(kitchen.stew_calculated.id))]
        assert (stew.active_count, stew.total_count) == (1, 3)
        assert stew.first_seen == TODAY - timedelta(days=9)
        assert stew.last_seen == TODAY - timedelta(days=1)

        manual = by_key["manual"]
        assert (manual.label, manual.store_chain, manual.kind) == ("", None, "manual")
        assert manual.item_ids == [UUID(str(kitchen.hand_added.id))]  # type: ignore[union-attr]
        assert (manual.active_count, manual.total_count) == (1, 1)

        pie = by_key["line:s-group:vuoksen riisipiirakka 15kpl"]
        assert (pie.active_count, pie.total_count) == (1, 4)

    async def test_sorted_by_last_seen_newest_first(
        self, db_session: AsyncSession, kitchen: Kitchen
    ) -> None:
        sources = await product_sources(db_session, UUID(str(kitchen.pie.id)))

        last_seen = [source.last_seen for source in sources]
        assert last_seen == sorted(last_seen, reverse=True)  # type: ignore[type-var]
        assert sources[-1].key == "line:s-group:karjalanpaisti"

    async def test_unknown_product(self, db_session: AsyncSession) -> None:
        with pytest.raises(UnknownProduct):
            await product_sources(db_session, uuid4())
