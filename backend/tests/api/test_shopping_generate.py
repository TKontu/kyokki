"""AG6: POST /api/shopping/generate - a shopping list from what is below its minimum."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_key import IdempotencyKey
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem

URL = "/api/shopping/generate"
TODAY = date.today()


@pytest.fixture(autouse=True)
def broadcast():
    with patch(
        "app.api.endpoints.shopping.broadcast_shopping_list_update",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


async def _product(
    db: AsyncSession, name: str, *, min_stock: str, reorder: str | None = None
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
        min_stock_quantity=Decimal(min_stock),
        reorder_quantity=Decimal(reorder) if reorder is not None else None,
    )
    db.add(product)
    await db.commit()
    return product


async def _stock(db: AsyncSession, product: ProductMaster, quantity: str) -> None:
    db.add(
        InventoryItem(
            id=uuid4(),
            product_master_id=product.id,
            initial_quantity=Decimal(quantity),
            current_quantity=Decimal(quantity),
            unit="dl",
            status="sealed",
            expiry_date=TODAY + timedelta(days=7),
            location="main_fridge",
        )
    )
    await db.commit()


async def _open_item(
    db: AsyncSession, product: ProductMaster, quantity: str, *, unit: str = "dl"
) -> ShoppingListItem:
    item = ShoppingListItem(
        id=uuid4(),
        product_master_id=product.id,
        name=product.canonical_name,
        quantity=Decimal(quantity),
        unit=unit,
        priority="normal",
        source="manual",
        is_purchased=False,
    )
    db.add(item)
    await db.commit()
    return item


async def _count(db: AsyncSession, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar())


async def _quantities(db: AsyncSession) -> list[Decimal]:
    rows = await db.execute(
        select(ShoppingListItem.quantity).order_by(ShoppingListItem.quantity)
    )
    return list(rows.scalars().all())


class TestGenerate:
    async def test_adds_what_is_low(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        milk_id = str(milk.id)
        await _stock(seeded_db, milk, "4")

        response = await client.post(URL, json={"sources": ["low_stock"]})

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is False
        assert body["updated"] == body["unchanged"] == body["skipped"] == []
        [line] = body["added"]
        assert line["product_id"] == milk_id
        assert (line["name"], line["need"], line["unit"]) == ("Milk", 6, "dl")
        assert (line["on_hand"], line["min_stock"]) == (4, 10)
        assert line["item_id"]
        assert await _count(seeded_db, ShoppingListItem) == 1
        broadcast.assert_awaited_once()
        kwargs = broadcast.await_args.kwargs
        assert kwargs["action"] == "created"
        assert str(kwargs["shopping_list_item_id"]) == line["item_id"]
        assert (kwargs["name"], kwargs["quantity"], kwargs["unit"]) == (
            "Milk",
            Decimal("6"),
            "dl",
        )

    async def test_raises_an_open_item_and_broadcasts_the_update(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        await _open_item(seeded_db, milk, "2")
        butter = await _product(seeded_db, "Butter", min_stock="5")
        await _open_item(seeded_db, butter, "9")

        response = await client.post(URL, json={"sources": ["low_stock"]})

        assert response.status_code == 200
        body = response.json()
        assert body["added"] == []
        assert [line["name"] for line in body["updated"]] == ["Milk"]
        assert [line["name"] for line in body["unchanged"]] == ["Butter"]
        assert await _quantities(seeded_db) == [Decimal("9"), Decimal("10")]
        broadcast.assert_awaited_once()
        assert broadcast.await_args.kwargs["action"] == "updated"
        assert broadcast.await_args.kwargs["quantity"] == Decimal("10")

    async def test_running_it_again_adds_no_duplicate(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        await _stock(seeded_db, milk, "4")

        await client.post(URL, json={"sources": ["low_stock"]})
        again = await client.post(URL, json={"sources": ["low_stock"]})

        assert again.status_code == 200
        assert again.json()["added"] == []
        assert len(again.json()["unchanged"]) == 1
        assert await _count(seeded_db, ShoppingListItem) == 1
        assert broadcast.await_count == 1

    async def test_a_dry_run_writes_and_broadcasts_nothing(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        await _stock(seeded_db, milk, "4")

        response = await client.post(
            URL, json={"sources": ["low_stock"], "dry_run": True}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        [line] = body["added"]
        assert (line["need"], line["item_id"]) == (6, None)
        assert await _count(seeded_db, ShoppingListItem) == 0
        broadcast.assert_not_awaited()

    @pytest.mark.parametrize(
        "sources",
        [
            [],
            ["recipe"],
            ["low_stock", "nope"],
            "low_stock",
            {"recipe": {"id": "abc"}},
            ["low_stock", {"recipe": {"id": "abc"}}],
            None,
            [3],
        ],
    )
    async def test_anything_but_known_sources_is_invalid(
        self, client: AsyncClient, seeded_db, broadcast, sources
    ) -> None:
        response = await client.post(URL, json={"sources": sources})

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid"
        assert "low_stock" in detail["message"]
        assert await _count(seeded_db, ShoppingListItem) == 0
        broadcast.assert_not_awaited()

    async def test_no_sources_at_all_is_invalid(
        self, client: AsyncClient, seeded_db
    ) -> None:
        response = await client.post(URL, json={})

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid"

    async def test_dry_run_is_still_a_validated_bool(
        self, client: AsyncClient, seeded_db
    ) -> None:
        response = await client.post(
            URL, json={"sources": ["low_stock"], "dry_run": "maybe"}
        )

        assert response.status_code == 422

    async def test_an_open_item_that_cannot_hold_the_need_is_skipped(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        milk_id = str(milk.id)
        await _stock(seeded_db, milk, "4")
        open_item = await _open_item(seeded_db, milk, "300", unit="g")
        open_item_id = str(open_item.id)

        response = await client.post(URL, json={"sources": ["low_stock"]})

        assert response.status_code == 200
        body = response.json()
        assert body["added"] == body["updated"] == body["unchanged"] == []
        [line] = body["skipped"]
        assert (line["product_id"], line["item_id"]) == (milk_id, open_item_id)
        assert (line["need"], line["on_hand"], line["min_stock"]) == (6, 4, 10)
        assert line["reason"] == (
            "the open list item is in g, which cannot hold a need in dl"
        )
        assert await _count(seeded_db, ShoppingListItem) == 1
        broadcast.assert_not_awaited()


class TestIdempotency:
    async def test_a_repeated_key_replays_without_a_second_write(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        await _stock(seeded_db, milk, "4")
        headers = {"Idempotency-Key": "generate-1"}
        body = {"sources": ["low_stock"]}

        first = await client.post(URL, json=body, headers=headers)
        second = await client.post(URL, json=body, headers=headers)

        assert (first.status_code, second.status_code) == (200, 200)
        # A second real run would answer "unchanged"; the replay answers "added".
        assert second.json() == first.json()
        assert len(second.json()["added"]) == 1
        assert second.headers.get("Idempotent-Replayed") == "true"
        assert await _count(seeded_db, ShoppingListItem) == 1
        assert await _count(seeded_db, IdempotencyKey) == 1
        assert broadcast.await_count == 1

    async def test_the_same_key_with_another_body_is_a_conflict(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        await _stock(seeded_db, milk, "4")
        headers = {"Idempotency-Key": "generate-2"}
        await client.post(URL, json={"sources": ["low_stock"]}, headers=headers)

        response = await client.post(
            URL, json={"sources": ["low_stock", "low_stock"]}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "conflict"
        assert await _count(seeded_db, ShoppingListItem) == 1

    async def test_a_dry_run_is_not_remembered(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk", min_stock="10")
        await _stock(seeded_db, milk, "4")
        headers = {"Idempotency-Key": "generate-3"}

        await client.post(
            URL, json={"sources": ["low_stock"], "dry_run": True}, headers=headers
        )
        real = await client.post(URL, json={"sources": ["low_stock"]}, headers=headers)

        assert real.status_code == 200
        assert real.json()["dry_run"] is False
        assert await _count(seeded_db, ShoppingListItem) == 1
