"""Confirm turns reviewed receipt lines into products, inventory and learned aliases (MVP-R2)."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.inventory_item import InventoryItem
from app.models.non_food_name import NonFoodName
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.schemas.receipt import ConfirmedItemCreate, ReceiptStatus
from app.services.receipt_confirm import (
    InvalidConfirmItem,
    ReceiptNotConfirmable,
    ReceiptNotFound,
    confirm_receipt,
)

PURCHASED = date(2026, 1, 2)

LINES = [
    {"name": "VALIO KEVYTMAITO 1L", "generic_name": "Milk", "category": "dairy"},
    {
        "name": "SNELLMAN NAUDAN JAUHELIHA 10%",
        "generic_name": "Ground beef",
        "category": "meat",
    },
    {"name": "MUOVIKASSI", "generic_name": "Plastic bag", "category": None},
    {"name": "PIRKKA HERNEET", "generic_name": "Peas", "category": "frozen"},
    {"name": "REAL RUISLEIPÄ", "generic_name": "Rye bread", "category": "bread"},
    {
        "name": "ATRIA NAUDAN JAUHELIHA 17%",
        "generic_name": "Ground beef",
        "category": "meat",
    },
]


@pytest.fixture(autouse=True)
def broadcasts():
    with (
        patch(
            "app.services.receipt_confirm.broadcast_inventory_update",
            new_callable=AsyncMock,
        ) as inventory,
        patch(
            "app.services.receipt_confirm.broadcast_receipt_status",
            new_callable=AsyncMock,
        ) as receipt,
    ):
        yield inventory, receipt


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    for order, (category_id, days) in enumerate(
        [("dairy", 7), ("meat", 3), ("frozen", 180), ("bread", 5)]
    ):
        db_session.add(
            Category(
                id=category_id,
                display_name=category_id.title(),
                icon="*",
                default_shelf_life_days=days,
                meal_contexts=[],
                sort_order=order,
            )
        )
    await db_session.commit()


@pytest.fixture
async def milk(db_session: AsyncSession, categories) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Milk",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="volume",
        default_unit="dl",
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def _receipt(
    db: AsyncSession,
    status: str = ReceiptStatus.COMPLETED,
    store_chain: str | None = "s-group",
) -> Receipt:
    receipt = Receipt(
        id=uuid4(),
        image_path=f"data/receipts/{uuid4()}.pdf",
        store_chain=store_chain,
        purchase_date=PURCHASED,
        processing_status=status,
        ocr_structured={"method": "text", "lines": [dict(line) for line in LINES]},
        items_extracted=len(LINES),
        items_matched=0,
    )
    db.add(receipt)
    await db.commit()
    return receipt


@pytest.fixture
async def receipt(db_session: AsyncSession, categories) -> Receipt:
    return await _receipt(db_session)


def _item(**fields) -> ConfirmedItemCreate:
    data = {"quantity": 1, "unit": "pcs", "purchase_date": PURCHASED, **fields}
    return ConfirmedItemCreate(**data)


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _inventory(db: AsyncSession) -> list[InventoryItem]:
    result = await db.execute(select(InventoryItem).order_by(InventoryItem.created_at))
    return list(result.scalars().all())


async def _aliases(db: AsyncSession) -> list[StoreProductAlias]:
    result = await db.execute(
        select(StoreProductAlias).order_by(StoreProductAlias.receipt_name)
    )
    return list(result.scalars().all())


class TestMixedConfirm:
    async def test_matched_new_and_skipped_lines(self, db_session, receipt, milk):
        result = await confirm_receipt(
            db_session,
            receipt.id,
            [
                _item(index=0, product_id=milk.id, quantity=10, unit="dl"),
                _item(
                    index=1, name="Ground beef", category="meat", quantity=400, unit="g"
                ),
                # line 2 (MUOVIKASSI) is skipped: not sent
            ],
        )

        assert (
            result.items_created,
            result.products_created,
            result.aliases_learned,
        ) == (
            2,
            1,
            2,
        )
        beef = (
            await db_session.execute(
                select(ProductMaster).where(
                    ProductMaster.canonical_name == "Ground beef"
                )
            )
        ).scalar_one()
        assert beef.category == "meat"
        assert beef.storage_type == "refrigerator"
        assert beef.default_shelf_life_days == 3
        assert beef.unit_type == "weight"
        assert beef.default_unit == "g"
        assert float(beef.default_quantity) == 400

        milk_item, beef_item = await _inventory(db_session)
        assert milk_item.product_master_id == milk.id
        assert milk_item.expiry_date == PURCHASED + timedelta(days=10)
        assert milk_item.expiry_source == "calculated"
        assert milk_item.receipt_id == receipt.id
        assert milk_item.status == "sealed"
        assert beef_item.product_master_id == beef.id
        assert float(beef_item.current_quantity) == 400
        assert beef_item.unit == "g"

        aliases = await _aliases(db_session)
        assert [(a.receipt_name, a.product_master_id) for a in aliases] == [
            ("SNELLMAN NAUDAN JAUHELIHA 10%", beef.id),
            ("VALIO KEVYTMAITO 1L", milk.id),
        ]
        assert all(a.store_chain == "s-group" for a in aliases)
        assert all(a.manually_verified and a.occurrence_count == 1 for a in aliases)
        assert all(a.confidence_score == 1.0 for a in aliases)

        await db_session.refresh(receipt)
        assert receipt.processing_status == ReceiptStatus.CONFIRMED

    async def test_empty_confirm_marks_the_receipt_confirmed(self, db_session, receipt):
        result = await confirm_receipt(db_session, receipt.id, [])

        assert result.items_created == 0
        await db_session.refresh(receipt)
        assert receipt.processing_status == ReceiptStatus.CONFIRMED

    async def test_broadcasts_after_commit(self, db_session, receipt, milk, broadcasts):
        inventory, receipt_status = broadcasts

        await confirm_receipt(db_session, receipt.id, [_item(product_id=milk.id)])

        (created,) = await _inventory(db_session)
        inventory.assert_awaited_once()
        assert inventory.await_args.kwargs["inventory_item_id"] == created.id
        assert inventory.await_args.kwargs["action"] == "created"
        assert inventory.await_args.kwargs["product_name"] == "Milk"
        receipt_status.assert_awaited_once()
        assert receipt_status.await_args.kwargs["status"] == ReceiptStatus.CONFIRMED


class TestLocationsAndOverrides:
    async def test_location_follows_the_product_category(self, db_session, receipt):
        await confirm_receipt(
            db_session,
            receipt.id,
            [_item(index=1), _item(index=3), _item(index=4)],
        )

        by_name = {}
        for item in await _inventory(db_session):
            product = await db_session.get(ProductMaster, item.product_master_id)
            by_name[product.canonical_name] = item.location
        assert by_name == {
            "Ground beef": "main_fridge",
            "Peas": "freezer",
            "Rye bread": "pantry",
        }

    async def test_location_and_expiry_overrides(self, db_session, receipt, milk):
        await confirm_receipt(
            db_session,
            receipt.id,
            [
                _item(
                    product_id=milk.id,
                    location="freezer",
                    expiry_date=date(2026, 3, 1),
                )
            ],
        )

        (item,) = await _inventory(db_session)
        assert item.location == "freezer"
        assert item.expiry_date == date(2026, 3, 1)
        assert item.expiry_source == "manual"


class TestProductReuse:
    async def test_new_name_reuses_an_existing_product_ignoring_case(
        self, db_session, receipt, milk
    ):
        result = await confirm_receipt(
            db_session, receipt.id, [_item(name="  mILK ", category="dairy")]
        )

        assert result.products_created == 0
        (item,) = await _inventory(db_session)
        assert item.product_master_id == milk.id

    async def test_two_brands_of_one_generic_product_create_one_product(
        self, db_session, receipt
    ):
        result = await confirm_receipt(
            db_session, receipt.id, [_item(index=1), _item(index=5)]
        )

        assert result.products_created == 1
        assert await _count(db_session, ProductMaster) == 1
        first, second = await _inventory(db_session)
        assert first.product_master_id == second.product_master_id
        # Each printed name is learned for the one generic product
        assert [a.receipt_name for a in await _aliases(db_session)] == [
            "ATRIA NAUDAN JAUHELIHA 17%",
            "SNELLMAN NAUDAN JAUHELIHA 10%",
        ]

    async def test_name_and_category_fall_back_to_the_line(self, db_session, receipt):
        await confirm_receipt(db_session, receipt.id, [_item(index=3)])

        product = (await db_session.execute(select(ProductMaster))).scalar_one()
        assert product.canonical_name == "Peas"
        assert product.category == "frozen"
        assert product.storage_type == "freezer"

    async def test_explicit_name_overrides_the_line(self, db_session, receipt):
        await confirm_receipt(
            db_session, receipt.id, [_item(index=3, name="Green peas")]
        )

        product = (await db_session.execute(select(ProductMaster))).scalar_one()
        assert product.canonical_name == "Green peas"
        assert product.category == "frozen"


class TestInvalidItemsWriteNothing:
    async def _assert_nothing_written(self, db: AsyncSession, receipt: Receipt):
        assert await _count(db, InventoryItem) == 0
        assert await _count(db, StoreProductAlias) == 0
        await db.refresh(receipt)
        assert receipt.processing_status == ReceiptStatus.COMPLETED

    async def test_new_product_without_a_category(self, db_session, receipt, milk):
        with pytest.raises(InvalidConfirmItem, match="Category required"):
            await confirm_receipt(
                db_session,
                receipt.id,
                [_item(index=0, product_id=milk.id), _item(index=2)],
            )

        await self._assert_nothing_written(db_session, receipt)
        assert await _count(db_session, ProductMaster) == 1

    async def test_unknown_category(self, db_session, receipt):
        with pytest.raises(InvalidConfirmItem, match="Unknown category"):
            await confirm_receipt(
                db_session, receipt.id, [_item(name="Tofu", category="vegan")]
            )
        await self._assert_nothing_written(db_session, receipt)

    async def test_unknown_product_id(self, db_session, receipt):
        with pytest.raises(InvalidConfirmItem, match="not found"):
            await confirm_receipt(db_session, receipt.id, [_item(product_id=uuid4())])
        await self._assert_nothing_written(db_session, receipt)

    async def test_index_out_of_range(self, db_session, receipt):
        with pytest.raises(InvalidConfirmItem, match="line 99"):
            await confirm_receipt(db_session, receipt.id, [_item(index=99)])
        await self._assert_nothing_written(db_session, receipt)


class TestAliasLearning:
    async def test_second_receipt_with_the_same_printed_name_counts_up(
        self, db_session, receipt, milk
    ):
        await confirm_receipt(
            db_session, receipt.id, [_item(index=0, product_id=milk.id)]
        )
        second = await _receipt(db_session)
        await confirm_receipt(
            db_session, second.id, [_item(index=0, product_id=milk.id)]
        )

        (alias,) = await _aliases(db_session)
        assert alias.occurrence_count == 2

    async def test_choosing_another_product_corrects_the_alias(
        self, db_session, receipt, milk
    ):
        db_session.add(
            StoreProductAlias(
                product_master_id=milk.id,
                store_chain="s-group",
                receipt_name="PIRKKA HERNEET",
                manually_verified=False,
                confidence_score=0.5,
                occurrence_count=1,
            )
        )
        await db_session.commit()

        await confirm_receipt(db_session, receipt.id, [_item(index=3)])

        (alias,) = await _aliases(db_session)
        peas = (
            await db_session.execute(
                select(ProductMaster).where(ProductMaster.canonical_name == "Peas")
            )
        ).scalar_one()
        assert alias.product_master_id == peas.id
        assert alias.manually_verified is True
        assert alias.occurrence_count == 2

    async def test_receipt_without_a_store_learns_for_unknown(
        self, db_session, categories, milk
    ):
        receipt = await _receipt(db_session, store_chain=None)

        await confirm_receipt(
            db_session, receipt.id, [_item(index=0, product_id=milk.id)]
        )

        (alias,) = await _aliases(db_session)
        assert alias.store_chain == "unknown"

    async def test_item_without_an_index_learns_nothing(
        self, db_session, receipt, milk
    ):
        result = await confirm_receipt(
            db_session, receipt.id, [_item(product_id=milk.id)]
        )

        assert result.aliases_learned == 0
        assert await _count(db_session, StoreProductAlias) == 0


class TestReceiptState:
    async def test_missing_receipt(self, db_session, categories):
        with pytest.raises(ReceiptNotFound):
            await confirm_receipt(db_session, uuid4(), [])

    async def test_confirmed_receipt_cannot_be_confirmed_again(
        self, db_session, receipt, milk
    ):
        await confirm_receipt(db_session, receipt.id, [_item(product_id=milk.id)])

        with pytest.raises(ReceiptNotConfirmable, match="already confirmed"):
            await confirm_receipt(db_session, receipt.id, [_item(product_id=milk.id)])
        assert await _count(db_session, InventoryItem) == 1

    @pytest.mark.parametrize(
        "status",
        [ReceiptStatus.UPLOADED, ReceiptStatus.PROCESSING, ReceiptStatus.FAILED],
    )
    async def test_unread_receipt_is_not_ready(self, db_session, categories, status):
        receipt = await _receipt(db_session, status=status)

        with pytest.raises(ReceiptNotConfirmable, match="not ready"):
            await confirm_receipt(db_session, receipt.id, [])


class TestConfirmedItemSchema:
    def test_needs_a_product_a_name_or_a_line(self):
        with pytest.raises(ValidationError, match="product_id, name, index or line_id"):
            ConfirmedItemCreate(quantity=1, unit="pcs", purchase_date=PURCHASED)

    def test_units_still_convert(self):
        item = _item(index=0, quantity=1.5, unit="l")
        assert (item.quantity, item.unit) == (15, "dl")

    def test_location_is_validated(self):
        with pytest.raises(ValidationError):
            _item(index=0, location="garage")


class TestNonFoodMemory:
    """Q1: the cook should not be asked about the same paper towels every week."""

    async def _confirm(self, db_session, receipt, items, non_food_indexes):
        return await confirm_receipt(db_session, receipt.id, items, non_food_indexes)

    async def test_a_marked_line_is_remembered_by_its_printed_name(
        self, db_session: AsyncSession, receipt, categories
    ):
        await self._confirm(db_session, receipt, [], [2])  # MUOVIKASSI

        rows = (await db_session.execute(select(NonFoodName))).scalars().all()
        assert [(r.receipt_name, r.store_chain, r.times_seen) for r in rows] == [
            ("MUOVIKASSI", "s-group", 1)
        ]

    async def test_a_line_merely_skipped_teaches_nothing(
        self, db_session: AsyncSession, receipt, categories
    ):
        """Not buying something for the fridge is not the same as saying it is not food."""
        await self._confirm(db_session, receipt, [], [])

        assert (await db_session.execute(select(NonFoodName))).scalars().all() == []

    async def test_an_index_off_the_end_is_ignored(
        self, db_session: AsyncSession, receipt, categories
    ):
        await self._confirm(db_session, receipt, [], [99, -1])

        assert (await db_session.execute(select(NonFoodName))).scalars().all() == []

    async def _reopen(self, db_session: AsyncSession, receipt) -> None:
        """Put the receipt back to `completed` so it can be confirmed again."""
        row = await db_session.get(Receipt, receipt.id)
        row.processing_status = ReceiptStatus.COMPLETED
        await db_session.commit()

    async def test_a_line_the_cook_includes_is_not_also_remembered(
        self, db_session: AsyncSession, receipt, categories
    ):
        """Nothing cross-checked the two lists, so correcting a wrong household
        guess taught the alias *and* wrote the non-food memory in one request,
        and the line was hidden again on the next receipt (H08)."""
        await self._confirm(db_session, receipt, [_item(index=3)], [3])

        assert (await db_session.execute(select(NonFoodName))).scalars().all() == []

    async def test_including_a_line_forgets_what_was_learned_before(
        self, db_session: AsyncSession, receipt, categories
    ):
        """Nothing in the codebase deleted a non_food_name row, so a misjudgement
        hid that product from every future receipt with no way back."""
        await self._confirm(db_session, receipt, [], [3])
        assert (await db_session.execute(select(NonFoodName))).scalars().all() != []

        await self._reopen(db_session, receipt)
        await self._confirm(db_session, receipt, [_item(index=3)], [3])

        assert (await db_session.execute(select(NonFoodName))).scalars().all() == []

    async def test_the_other_folded_lines_are_still_remembered(
        self, db_session: AsyncSession, receipt, categories
    ):
        await self._confirm(db_session, receipt, [_item(index=3)], [2, 3])

        rows = (await db_session.execute(select(NonFoodName))).scalars().all()
        assert [r.receipt_name for r in rows] == ["MUOVIKASSI"]


class TestLearningProvenance:
    """The six situations of `docs/PRODUCT_RESOLUTION_SPEC.md` §3.4.

    Before H14 confirm wrote `manually_verified=True` for every included line, so a
    proposal the cook merely did not notice became a key that won outright for every
    later receipt from that chain. Only the cook's own act produces verified memory now.
    """

    async def _confirm_with(
        self, db_session: AsyncSession, receipt, resolution: dict, item
    ):
        """Put a resolution on line 0 and confirm that line."""
        lines = list(receipt.ocr_structured["lines"])
        lines[0] = {**lines[0], "resolution": resolution}
        row = await db_session.get(Receipt, receipt.id)
        row.ocr_structured = {**receipt.ocr_structured, "lines": lines}
        await db_session.commit()
        return await confirm_receipt(db_session, receipt.id, [item], [])

    async def _alias(self, db_session: AsyncSession) -> StoreProductAlias:
        return (
            (
                await db_session.execute(
                    select(StoreProductAlias).where(
                        StoreProductAlias.receipt_name == "VALIO KEVYTMAITO 1L"
                    )
                )
            )
            .scalars()
            .one()
        )

    async def test_keeping_a_name_result_is_a_verified_key(
        self, db_session: AsyncSession, receipt, milk
    ):
        await self._confirm_with(
            db_session,
            receipt,
            {"product_id": str(milk.id), "source": "name", "verified": True},
            _item(index=0, product_id=milk.id),
        )

        alias = await self._alias(db_session)
        assert (alias.source, alias.manually_verified) == ("name", True)

    async def test_keeping_a_selected_result_is_not_verified(
        self, db_session: AsyncSession, receipt, milk
    ):
        """The model proposed it from a shortlist and the cook did not contradict it.
        That is worth remembering, but it is not the cook's word."""
        await self._confirm_with(
            db_session,
            receipt,
            {"product_id": str(milk.id), "source": "selected", "verified": False},
            _item(index=0, product_id=milk.id),
        )

        alias = await self._alias(db_session)
        assert (alias.source, alias.manually_verified) == ("model", False)

    async def test_changing_the_product_is_the_cooks_word(
        self, db_session: AsyncSession, receipt, milk, categories
    ):
        """The case that matters most: a wrong proposal the cook corrects becomes
        verified memory, so the next receipt resolves it by key with no model call."""
        other = ProductMaster(
            id=uuid4(),
            canonical_name="Oat drink",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="dl",
        )
        db_session.add(other)
        await db_session.commit()

        await self._confirm_with(
            db_session,
            receipt,
            {"product_id": str(milk.id), "source": "selected", "verified": False},
            _item(index=0, product_id=other.id),
        )

        alias = await self._alias(db_session)
        assert (alias.source, alias.manually_verified) == ("cook", True)
        assert alias.product_master_id == other.id

    async def test_an_unresolved_line_the_cook_names_is_the_cooks_word(
        self, db_session: AsyncSession, receipt, categories
    ):
        await self._confirm_with(
            db_session,
            receipt,
            {"product_id": None, "source": "none", "verified": False},
            _item(index=0, name="Light milk", category="dairy"),
        )

        alias = await self._alias(db_session)
        assert (alias.source, alias.manually_verified) == ("cook", True)

    async def test_a_machine_mapping_never_demotes_the_cooks(
        self, db_session: AsyncSession, receipt, milk
    ):
        """Reinforcing an alias the cook corrected must not hand it back to the model."""
        await self._confirm_with(
            db_session,
            receipt,
            {"product_id": None, "source": "none", "verified": False},
            _item(index=0, product_id=milk.id),
        )
        before = await self._alias(db_session)
        assert (before.source, before.manually_verified) == ("cook", True)

        row = await db_session.get(Receipt, receipt.id)
        row.processing_status = ReceiptStatus.COMPLETED
        await db_session.commit()
        await self._confirm_with(
            db_session,
            receipt,
            {"product_id": str(milk.id), "source": "selected", "verified": False},
            _item(index=0, product_id=milk.id),
        )

        after = await self._alias(db_session)
        assert (after.source, after.manually_verified) == ("cook", True)
        assert after.occurrence_count == 2

    async def test_a_skipped_line_teaches_nothing(
        self, db_session: AsyncSession, receipt, milk
    ):
        await confirm_receipt(db_session, receipt.id, [], [])

        assert (
            await db_session.execute(select(StoreProductAlias))
        ).scalars().all() == []
