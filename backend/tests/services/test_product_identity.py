"""Exact keys only (CL8 L1, `docs/PRODUCT_IDENTITY_SPEC.md`).

Production, 2026-10-06: S-group line ``KARJALANPAISTI`` (Karelian stew) got the generic name
"Karelian pie", selection picked the existing pie product, and confirm stocked the stew on
it. From here on a name joins a product only on an exact key; everything else is a
suggestion the cook accepts, confirm refuses a silent name join with ``name_exists``, and
every new item records how it joined.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product_master import update_product
from app.crud.product_name import learn_product_name
from app.models.category import Category
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.schemas.inventory_item import QuickAddRequest
from app.schemas.product_master import ProductMasterUpdate
from app.schemas.receipt import (
    ConfirmedItemCreate,
    ReceiptStatus,
    items_from_structured,
)
from app.services.llm_extractor import LLMExtractionError
from app.services.product_identity import (
    KeyJoin,
    Suggestion,
    decide_line,
    decide_name,
)
from app.services.product_resolution import ProductResolution, ResolvableLine
from app.services.quick_add import quick_add
from app.services.receipt_confirm import NameExists, confirm_receipt
from app.services.stock import add_stock

PURCHASED = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def _quiet_broadcasts():
    with (
        patch(
            "app.services.receipt_confirm.broadcast_inventory_update",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.receipt_confirm.broadcast_receipt_status",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.quick_add.broadcast_inventory_update",
            new_callable=AsyncMock,
        ),
    ):
        yield


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    for order, category_id in enumerate(("ready_meals", "dairy")):
        db_session.add(
            Category(
                id=category_id,
                display_name=category_id.title(),
                icon="*",
                default_shelf_life_days=4,
                sort_order=order,
            )
        )
    await db_session.commit()


async def _product(db: AsyncSession, name: str) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="ready_meals",
        storage_type="refrigerator",
        default_shelf_life_days=4,
        unit_type="count",
        default_unit="pcs",
    )
    db.add(product)
    await db.flush()
    await learn_product_name(db, product, name, "canonical")
    await db.commit()
    return product


@pytest.fixture
async def pie(db_session: AsyncSession, categories) -> ProductMaster:
    return await _product(db_session, "Karelian pie")


async def _alias(
    db: AsyncSession,
    product: ProductMaster,
    printed: str,
    *,
    chain: str,
    verified: bool,
    source: str = "cook",
) -> None:
    db.add(
        StoreProductAlias(
            product_master_id=product.id,
            store_chain=chain,
            receipt_name=printed,
            source=source,
            manually_verified=verified,
            occurrence_count=1,
            last_seen=datetime.now(UTC),
        )
    )
    await db.commit()


def _line(printed: str, generic: str | None = None) -> ResolvableLine:
    return ResolvableLine(
        line_id=printed, printed=printed, generic=generic, category="ready_meals"
    )


class TestKarjalanpaistiNeverResolvesToKarelianPie:
    """The spec's acceptance case, against a stub that always picks candidate 0."""

    async def test_a_selection_that_picks_the_pie_is_only_a_suggestion(
        self, db_session: AsyncSession, pie, _no_model_selection
    ) -> None:
        _no_model_selection.side_effect = lambda lines: {
            line.line_id: line.candidate_ids[0] for line in lines
        }

        resolved = await ProductResolution(db_session).resolve(
            [_line("KARJALANPAISTI", "Karelian pie")], chain="s-group"
        )

        result = resolved["KARJALANPAISTI"]
        assert result.product is None
        assert result.source == "none"
        assert result.suggestion is not None
        assert result.suggestion.reason == "selected"
        assert result.suggestion.product.id == pie.id
        blob = result.as_dict()
        assert blob["product_id"] is None
        assert blob["suggestion"]["reason"] == "selected"

    async def test_a_selection_that_fails_leaves_no_product(
        self, db_session: AsyncSession, pie, _no_model_selection
    ) -> None:
        _no_model_selection.side_effect = LLMExtractionError("gateway down")

        resolved = await ProductResolution(db_session).resolve(
            [_line("KARJALANPAISTI", "Karelian pie")], chain="s-group"
        )

        result = resolved["KARJALANPAISTI"]
        assert result.product is None
        # The Q37 hit stays on offer, unticked: never the product.
        assert result.suggestion is None or result.suggestion.reason == "generic_name"

    async def test_a_selection_that_answers_null_keeps_the_generic_name_suggestion(
        self, db_session: AsyncSession, pie, _no_model_selection
    ) -> None:
        _no_model_selection.side_effect = lambda lines: {}

        resolved = await ProductResolution(db_session).resolve(
            [_line("KARJALANPAISTI", "Karelian pie")], chain="s-group"
        )

        result = resolved["KARJALANPAISTI"]
        assert result.product is None
        assert result.suggestion is not None
        assert (result.suggestion.reason, result.suggestion.product.id) == (
            "generic_name",
            pie.id,
        )


class TestKeysAndSuggestions:
    async def test_a_verified_alias_at_this_chain_is_a_key(
        self, db_session: AsyncSession, pie
    ) -> None:
        await _alias(
            db_session, pie, "KARJALANPIIRAKKA", chain="s-group", verified=True
        )

        decision = await decide_line(db_session, "KARJALANPIIRAKKA", None, "s-group")

        assert isinstance(decision, KeyJoin)
        assert (decision.product.id, decision.source, decision.key) == (
            pie.id,
            "alias",
            "KARJALANPIIRAKKA",
        )

    async def test_a_verified_alias_at_another_chain_only_suggests(
        self, db_session: AsyncSession, pie
    ) -> None:
        await _alias(db_session, pie, "KARJALANPIIRAKKA", chain="lidl", verified=True)

        decision = await decide_line(db_session, "KARJALANPIIRAKKA", None, "s-group")

        assert isinstance(decision, Suggestion)
        assert (decision.product.id, decision.reason, decision.store_chain) == (
            pie.id,
            "other_chain_alias",
            "lidl",
        )
        assert decision.as_dict()["store_chain"] == "lidl"

    async def test_an_unverified_alias_at_this_chain_only_suggests(
        self, db_session: AsyncSession, pie
    ) -> None:
        await _alias(
            db_session,
            pie,
            "KARJALANPIIRAKKA",
            chain="s-group",
            verified=False,
            source="model",
        )

        decision = await decide_line(db_session, "KARJALANPIIRAKKA", None, "s-group")

        assert isinstance(decision, Suggestion)
        assert decision.reason == "unverified_alias"
        assert "store_chain" not in decision.as_dict()

    async def test_this_chains_unverified_alias_outranks_another_chains(
        self, db_session: AsyncSession, pie, categories
    ) -> None:
        stew = await _product(db_session, "Karelian stew")
        await _alias(db_session, pie, "X", chain="lidl", verified=True)
        await _alias(db_session, stew, "X", chain="s-group", verified=False)

        decision = await decide_line(db_session, "X", None, "s-group")

        assert isinstance(decision, Suggestion)
        assert (decision.reason, decision.product.id) == ("unverified_alias", stew.id)

    async def test_a_printed_name_equal_to_a_model_name_only_suggests(
        self, db_session: AsyncSession, pie
    ) -> None:
        await learn_product_name(db_session, pie, "Karjalanpaisti", "model")
        await db_session.commit()

        decision = await decide_line(db_session, "KARJALANPAISTI", None, "s-group")

        assert isinstance(decision, Suggestion)
        assert (decision.reason, decision.product.id) == ("model_name", pie.id)

    async def test_a_printed_name_equal_to_a_canonical_name_is_a_key(
        self, db_session: AsyncSession, pie
    ) -> None:
        decision = await decide_line(db_session, "KARELIAN PIE", None, "s-group")

        assert isinstance(decision, KeyJoin)
        assert (decision.product.id, decision.source, decision.key) == (
            pie.id,
            "name",
            "karelian pie",
        )

    async def test_a_generic_name_the_cook_taught_is_a_key(
        self, db_session: AsyncSession, pie
    ) -> None:
        await learn_product_name(db_session, pie, "Rice pie", "cook")
        await db_session.commit()

        decision = await decide_line(
            db_session, "VUOKSEN RIISIPIIRAKKA", "Rice pie", None
        )

        assert isinstance(decision, KeyJoin)
        assert (decision.source, decision.key) == ("name", "rice pie")

    async def test_a_generic_name_equal_to_a_canonical_name_only_suggests(
        self, db_session: AsyncSession, pie
    ) -> None:
        decision = await decide_line(db_session, "KARJALANPAISTI", "Karelian pie", None)

        assert isinstance(decision, Suggestion)
        assert decision.reason == "generic_name"

    async def test_suggested_lines_are_not_sent_to_selection(
        self, db_session: AsyncSession, pie, _no_model_selection
    ) -> None:
        await _alias(db_session, pie, "KARJALANPIIRAKKA", chain="lidl", verified=True)

        resolved = await ProductResolution(db_session).resolve(
            [_line("KARJALANPIIRAKKA")], chain="s-group"
        )

        assert resolved["KARJALANPIIRAKKA"].suggestion.reason == "other_chain_alias"
        _no_model_selection.assert_not_awaited()

    async def test_decide_name_ignores_model_names(
        self, db_session: AsyncSession, pie
    ) -> None:
        await learn_product_name(db_session, pie, "Karelian stew", "model")
        await db_session.commit()

        assert await decide_name(db_session, "karelian stew") is None
        joined = await decide_name(db_session, " karelian  PIE ")
        assert joined is not None and joined.product.id == pie.id


# --- confirm -------------------------------------------------------------------------


def _blob(
    *,
    product: ProductMaster | None = None,
    source: str = "none",
    suggestion: dict | None = None,
    join_key: str | None = None,
) -> dict:
    blob: dict = {
        "product_id": str(product.id) if product else None,
        "source": source,
        "verified": product is not None,
        "candidates": [],
        "suggestion": suggestion,
    }
    if join_key:
        blob["join_key"] = join_key
    return blob


async def _receipt(db: AsyncSession, lines: list[dict]) -> Receipt:
    receipt = Receipt(
        id=uuid4(),
        image_path=f"data/receipts/{uuid4()}.pdf",
        store_chain="s-group",
        purchase_date=PURCHASED,
        processing_status=ReceiptStatus.COMPLETED,
        ocr_structured={
            "method": "text",
            "lines": [{"line_id": str(uuid4()), **line} for line in lines],
        },
        items_extracted=len(lines),
        items_matched=0,
    )
    db.add(receipt)
    await db.commit()
    return receipt


def _stew_line(pie: ProductMaster) -> dict:
    """KARJALANPAISTI as served after this lane: no product, pie only suggested."""
    return {
        "name": "KARJALANPAISTI",
        "generic_name": "Karelian pie",
        "category": "ready_meals",
        "product_id": None,
        "match_source": None,
        "resolution": _blob(
            suggestion={
                "product_id": str(pie.id),
                "product_name": "Karelian pie",
                "reason": "selected",
            }
        ),
    }


def _item(**fields) -> ConfirmedItemCreate:
    return ConfirmedItemCreate(
        **{"quantity": 1, "unit": "pcs", "purchase_date": PURCHASED, **fields}
    )


async def _count(db: AsyncSession, model) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


class TestConfirmRefusesASilentNameJoin:
    async def test_the_served_generic_name_answers_name_exists_and_writes_nothing(
        self, db_session: AsyncSession, pie
    ) -> None:
        receipt = await _receipt(db_session, [_stew_line(pie)])
        line_id = receipt.ocr_structured["lines"][0]["line_id"]
        receipt_id, pie_id = receipt.id, pie.id
        before = {
            model: await _count(db_session, model)
            for model in (InventoryItem, StoreProductAlias, ProductName, ProductMaster)
        }

        with pytest.raises(NameExists) as caught:
            await confirm_receipt(db_session, receipt_id, [_item(index=0)])

        (clash,) = caught.value.clashes
        assert clash.as_dict() == {
            "position": 0,
            "line_id": line_id,
            "index": 0,
            "name": "Karelian pie",
            "product_id": str(pie_id),
            "product_name": "Karelian pie",
        }
        assert str(caught.value) == "1 line names a product that already exists"
        for model, count in before.items():
            assert await _count(db_session, model) == count, model
        status = await db_session.scalar(
            select(Receipt.processing_status).where(Receipt.id == receipt_id)
        )
        assert status == ReceiptStatus.COMPLETED

    async def test_every_clashing_item_is_listed(
        self, db_session: AsyncSession, pie
    ) -> None:
        receipt = await _receipt(
            db_session,
            [
                _stew_line(pie),
                {"name": "MAITO", "generic_name": "Oat drink", "category": "dairy"},
                {"name": "PIIRAKKA", "generic_name": "Rice pie", "category": "dairy"},
            ],
        )

        with pytest.raises(NameExists) as caught:
            await confirm_receipt(
                db_session,
                receipt.id,
                [_item(index=0), _item(index=1), _item(index=2, name="KARELIAN pie")],
            )

        assert [(c.position, c.index) for c in caught.value.clashes] == [(0, 0), (2, 2)]
        assert str(caught.value) == "2 lines name a product that already exists"

    async def test_a_free_item_typed_as_an_existing_name_joins_it(
        self, db_session: AsyncSession, pie, categories
    ) -> None:
        """CONTRACT §2 amendment (2026-10-18): an item with no receipt line - the
        review screen's hand-added "missed" item - is a typed name, like quick add."""
        milk = await _product(db_session, "Milk")
        receipt = await _receipt(db_session, [_stew_line(pie)])

        result = await confirm_receipt(db_session, receipt.id, [_item(name="milk")])

        assert result.products_created == 0
        item = (await db_session.execute(select(InventoryItem))).scalar_one()
        assert (item.product_master_id, item.join_source, item.join_key) == (
            milk.id,
            "name",
            "milk",
        )

    async def test_a_line_item_named_as_an_existing_name_is_name_exists(
        self, db_session: AsyncSession, pie, categories
    ) -> None:
        milk = await _product(db_session, "Milk")
        milk_id = milk.id
        receipt = await _receipt(
            db_session,
            [{"name": "VALIO MAITO", "generic_name": "Milk", "category": "dairy"}],
        )

        with pytest.raises(NameExists) as caught:
            await confirm_receipt(db_session, receipt.id, [_item(index=0)])

        assert [c.product_id for c in caught.value.clashes] == [milk_id]

    async def test_a_free_item_never_joins_a_model_name(
        self, db_session: AsyncSession, pie
    ) -> None:
        await learn_product_name(db_session, pie, "Karelian stew", "model")
        await db_session.commit()
        receipt = await _receipt(db_session, [_stew_line(pie)])

        result = await confirm_receipt(
            db_session,
            receipt.id,
            [_item(name="Karelian stew", category="ready_meals")],
        )

        assert result.products_created == 1
        item = (await db_session.execute(select(InventoryItem))).scalar_one()
        assert item.product_master_id != pie.id
        assert item.join_source == "created"

    async def test_a_model_name_neither_blocks_nor_joins(
        self, db_session: AsyncSession, pie
    ) -> None:
        await learn_product_name(db_session, pie, "Karelian stew", "model")
        await db_session.commit()
        receipt = await _receipt(db_session, [_stew_line(pie)])

        await confirm_receipt(
            db_session, receipt.id, [_item(index=0, name="Karelian stew")]
        )

        (item,) = (await db_session.execute(select(InventoryItem))).scalars().all()
        assert item.product_master_id != pie.id
        assert (item.join_source, item.join_key) == ("created", "karelian stew")
        alias = (await db_session.execute(select(StoreProductAlias))).scalar_one()
        assert (alias.source, alias.manually_verified) == ("cook", True)

    async def test_an_accepted_suggestion_is_learned_as_cook_accepted(
        self, db_session: AsyncSession, pie
    ) -> None:
        receipt = await _receipt(db_session, [_stew_line(pie)])

        await confirm_receipt(
            db_session,
            receipt.id,
            [_item(index=0, product_id=pie.id, accepted_suggestion=True)],
        )

        alias = (await db_session.execute(select(StoreProductAlias))).scalar_one()
        assert (alias.product_master_id, alias.source, alias.manually_verified) == (
            pie.id,
            "cook_accepted",
            True,
        )
        item = (await db_session.execute(select(InventoryItem))).scalar_one()
        assert (item.join_source, item.join_key) == (
            "accepted_suggestion",
            "KARJALANPAISTI",
        )
        # The generic name was the model's word, and accepting the product does not
        # make it the cook's.
        row = (
            await db_session.execute(
                select(ProductName).where(ProductName.name == "karelian pie")
            )
        ).scalar_one()
        assert row.source == "canonical"

    async def test_a_search_pick_is_the_cooks_word(
        self, db_session: AsyncSession, pie, categories
    ) -> None:
        stew = await _product(db_session, "Karelian stew")
        receipt = await _receipt(db_session, [_stew_line(pie)])

        await confirm_receipt(
            db_session, receipt.id, [_item(index=0, product_id=stew.id)]
        )

        alias = (await db_session.execute(select(StoreProductAlias))).scalar_one()
        assert (alias.product_master_id, alias.source, alias.manually_verified) == (
            stew.id,
            "cook",
            True,
        )
        item = (await db_session.execute(select(InventoryItem))).scalar_one()
        assert (item.join_source, item.join_key) == ("cook_pick", "KARJALANPAISTI")

    async def test_a_kept_key_records_its_key(
        self, db_session: AsyncSession, pie
    ) -> None:
        receipt = await _receipt(
            db_session,
            [
                {
                    "name": "KARJALANPIIRAKKA",
                    "generic_name": "Karelian pie",
                    "category": "ready_meals",
                    "product_id": str(pie.id),
                    "product_name": "Karelian pie",
                    "match_source": "alias",
                    "resolution": {
                        **_blob(
                            product=pie, source="alias", join_key="KARJALANPIIRAKKA"
                        ),
                        "alias_source": "cook",
                    },
                }
            ],
        )

        await confirm_receipt(
            db_session, receipt.id, [_item(index=0, product_id=pie.id)]
        )

        item = (await db_session.execute(select(InventoryItem))).scalar_one()
        assert (item.join_source, item.join_key) == ("alias", "KARJALANPIIRAKKA")

    async def test_a_new_product_records_created(
        self, db_session: AsyncSession, pie
    ) -> None:
        receipt = await _receipt(db_session, [_stew_line(pie)])

        await confirm_receipt(
            db_session, receipt.id, [_item(index=0, name="Karelian stew")]
        )

        item = (await db_session.execute(select(InventoryItem))).scalar_one()
        assert (item.join_source, item.join_key) == ("created", "karelian stew")


class TestConfirmEndpoint:
    async def test_name_exists_is_a_409_with_every_clash(
        self, client: AsyncClient, test_db: AsyncSession, categories
    ) -> None:
        pie = await _product(test_db, "Karelian pie")
        receipt = await _receipt(test_db, [_stew_line(pie)])
        line_id = receipt.ocr_structured["lines"][0]["line_id"]
        pie_id = pie.id

        response = await client.post(
            f"/api/receipts/{receipt.id}/confirm",
            json={
                "items": [
                    {
                        "index": 0,
                        "quantity": 1,
                        "unit": "pcs",
                        "purchase_date": PURCHASED.isoformat(),
                    }
                ]
            },
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "name_exists"
        assert detail["message"] == "1 line names a product that already exists"
        assert detail["items"] == [
            {
                "position": 0,
                "line_id": line_id,
                "index": 0,
                "name": "Karelian pie",
                "product_id": str(pie_id),
                "product_name": "Karelian pie",
            }
        ]


# --- quick add and stock add ---------------------------------------------------------


class TestQuickAdd:
    async def test_a_model_name_does_not_join(
        self, db_session: AsyncSession, pie
    ) -> None:
        await learn_product_name(db_session, pie, "Karelian stew", "model")
        await db_session.commit()

        result = await quick_add(
            db_session,
            QuickAddRequest(
                name="karelian stew", category="ready_meals", quantity=Decimal("1")
            ),
        )

        assert result.product_created is True
        assert result.item.product_master_id != pie.id
        assert (result.item.join_source, result.item.join_key) == (
            "created",
            "karelian stew",
        )

    async def test_a_canonical_name_joins(self, db_session: AsyncSession, pie) -> None:
        result = await quick_add(
            db_session, QuickAddRequest(name="Karelian pie", quantity=Decimal("1"))
        )

        assert result.product_created is False
        assert result.item.product_master_id == pie.id
        assert (result.item.join_source, result.item.join_key) == (
            "quick_add",
            "karelian pie",
        )

    async def test_the_agents_stock_add_records_agent(
        self, db_session: AsyncSession, pie
    ) -> None:
        result = await add_stock(
            db_session, QuickAddRequest(name="Karelian pie", quantity=Decimal("1"))
        )

        item = await db_session.get(InventoryItem, result.response.item.id)
        assert item is not None
        assert (item.product_master_id, item.join_source, item.join_key) == (
            pie.id,
            "agent",
            "karelian pie",
        )


# --- rename --------------------------------------------------------------------------


class TestRenameAsks:
    async def test_keep_old_name_false_forgets_the_old_name(
        self, db_session: AsyncSession, pie
    ) -> None:
        await update_product(
            db_session,
            pie.id,
            ProductMasterUpdate(canonical_name="Karelian stew", keep_old_name=False),
        )

        assert await decide_name(db_session, "Karelian pie") is None
        joined = await decide_name(db_session, "Karelian stew")
        assert joined is not None and joined.product.id == pie.id

    async def test_by_default_the_old_name_is_kept(
        self, db_session: AsyncSession, pie
    ) -> None:
        await update_product(
            db_session, pie.id, ProductMasterUpdate(canonical_name="Karelian stew")
        )

        joined = await decide_name(db_session, "Karelian pie")
        assert joined is not None and joined.product.id == pie.id


# --- serving -------------------------------------------------------------------------


def _old_line(source: str, verified: bool) -> dict:
    product_id = str(uuid4())
    return {
        "name": "KARJALANPAISTI",
        "generic_name": "Karelian pie",
        "category": "ready_meals",
        "quantity": 1,
        "product_id": product_id,
        "product_name": "Karelian pie",
        "product_storage_type": "freezer",
        "match_source": source,
        "resolution": {
            "product_id": product_id,
            "source": source,
            "verified": verified,
            "candidates": [],
        },
    }


class TestServing:
    @pytest.mark.parametrize(
        ("source", "verified", "reason"),
        [
            ("selected", False, "selected"),
            ("alias", False, "unverified_alias"),
            ("name", False, "model_name"),
        ],
    )
    async def test_an_old_non_key_reads_as_a_suggestion(
        self, source: str, verified: bool, reason: str
    ) -> None:
        line = _old_line(source, verified)

        (item,) = items_from_structured({"lines": [line]})

        assert item.product_id is None
        assert item.product_name is None
        assert item.match_source == "none"
        assert item.verified is False
        assert item.suggestion is not None
        assert str(item.suggestion.product_id) == line["product_id"]
        assert (item.suggestion.product_name, item.suggestion.reason) == (
            "Karelian pie",
            reason,
        )
        assert item.suggestion.store_chain is None
        # The suggested product's storage is not the line's until accepted.
        assert item.storage_type == "refrigerator"

    @pytest.mark.parametrize("source", ["alias", "name"])
    async def test_an_old_verified_key_stays_a_key(self, source: str) -> None:
        line = _old_line(source, True)

        (item,) = items_from_structured({"lines": [line]})

        assert str(item.product_id) == line["product_id"]
        assert (item.match_source, item.verified, item.suggestion) == (
            source,
            True,
            None,
        )

    async def test_a_new_blob_is_read_as_stored(self) -> None:
        product_id = str(uuid4())
        line = {
            "name": "KARJALANPIIRAKKA",
            "generic_name": "Karelian pie",
            "category": "ready_meals",
            "quantity": 1,
            "product_id": None,
            "resolution": {
                "product_id": None,
                "source": "none",
                "verified": False,
                "candidates": [],
                "suggestion": {
                    "product_id": product_id,
                    "product_name": "Karelian pie",
                    "reason": "other_chain_alias",
                    "store_chain": "lidl",
                },
            },
        }

        (item,) = items_from_structured({"lines": [line]})

        assert item.product_id is None
        assert item.match_source == "none"
        assert item.suggestion is not None
        assert (item.suggestion.reason, item.suggestion.store_chain) == (
            "other_chain_alias",
            "lidl",
        )
