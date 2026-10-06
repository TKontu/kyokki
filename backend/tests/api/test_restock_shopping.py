"""CL2: new stock ticks its shopping items bought.

Each way stock is added - receipt confirm, the iPad's quick add and the agent's
`/stock/add` - marks the product's open shopping items purchased
(`services/min_stock.py::after_stock_increase`). The rules themselves (free-text and
other products untouched, an already-bought item kept as it was) are covered in
`tests/services/test_min_stock.py`; this checks that every caller wires it in.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.shopping_list_item import ShoppingListItem


@pytest.fixture(autouse=True)
def inventory_broadcasts():
    with (
        patch(
            "app.api.endpoints.inventory.broadcast_inventory_update",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.endpoints.stock.broadcast_inventory_update",
            new_callable=AsyncMock,
        ),
    ):
        yield


@pytest.fixture
def shopping_broadcast():
    with patch(
        "app.services.min_stock.broadcast_shopping_list_update", new_callable=AsyncMock
    ) as mock:
        yield mock


async def _product(db: AsyncSession, name: str = "Milk") -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
    )
    db.add(product)
    await db.commit()
    return product


async def _open_item(
    db: AsyncSession, product: ProductMaster, *, source: str = "manual"
) -> ShoppingListItem:
    item = ShoppingListItem(
        id=uuid4(),
        product_master_id=product.id,
        name=product.canonical_name,
        quantity=Decimal("10"),
        unit="dl",
        priority="normal",
        source=source,
        is_purchased=False,
    )
    db.add(item)
    await db.commit()
    return item


async def _reload(db: AsyncSession, item_id) -> ShoppingListItem:
    rows = await db.execute(
        select(ShoppingListItem)
        .where(ShoppingListItem.id == item_id)
        .execution_options(populate_existing=True)
    )
    return rows.scalar_one()


async def test_receipt_confirm_ticks_the_products_open_items(
    client: AsyncClient, seeded_db: AsyncSession, shopping_broadcast
) -> None:
    milk = await _product(seeded_db)
    manual = await _open_item(seeded_db, milk)
    auto = await _open_item(seeded_db, milk, source="auto_restock")
    receipt = Receipt(
        id=uuid4(),
        image_path=f"data/receipts/{uuid4()}.jpg",
        processing_status="completed",
        ocr_structured={"lines": [{"name": "VALIO MAITO 1L", "price": 1.49}]},
        items_extracted=1,
        items_matched=0,
    )
    seeded_db.add(receipt)
    await seeded_db.commit()

    response = await client.post(
        f"/api/receipts/{receipt.id}/confirm",
        json={
            "items": [
                {
                    "index": 0,
                    "product_id": str(milk.id),
                    "quantity": 1,
                    "unit": "pcs",
                    "purchase_date": "2026-10-06",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    for item_id in (manual.id, auto.id):
        row = await _reload(seeded_db, item_id)
        assert row.is_purchased is True
        assert row.purchased_at is not None
    assert shopping_broadcast.await_count == 2


async def test_quick_add_ticks_the_products_open_items(
    client: AsyncClient, seeded_db: AsyncSession, shopping_broadcast
) -> None:
    milk = await _product(seeded_db)
    item = await _open_item(seeded_db, milk)

    response = await client.post(
        "/api/inventory/quick-add",
        json={"product_id": str(milk.id), "quantity": 10, "unit": "dl"},
    )

    assert response.status_code == 201, response.text
    row = await _reload(seeded_db, item.id)
    assert row.is_purchased is True
    assert row.purchased_at is not None
    shopping_broadcast.assert_awaited_once()
    assert shopping_broadcast.await_args.kwargs["action"] == "purchased"


@pytest.mark.parametrize("url", ["/api/inventory/quick-add", "/api/stock/add"])
async def test_a_failing_hook_does_not_fail_the_stock_request(
    client: AsyncClient, seeded_db: AsyncSession, shopping_broadcast, url
) -> None:
    milk = await _product(seeded_db)
    milk_id = milk.id
    item = await _open_item(seeded_db, milk)
    item_id = item.id

    with patch(
        "app.services.min_stock.crud_shopping.get_by_product",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        response = await client.post(
            url, json={"product_id": str(milk_id), "quantity": 10, "unit": "dl"}
        )

    assert response.status_code == 201, response.text
    body = response.json()
    if url == "/api/stock/add":
        body = body["item"]
    assert body["product_master_id"] == str(milk_id)
    row = await _reload(seeded_db, item_id)
    assert (row.is_purchased, row.purchased_at) == (False, None)
    shopping_broadcast.assert_not_awaited()


async def test_receipt_confirm_answers_even_when_the_hook_fails(
    client: AsyncClient, seeded_db: AsyncSession, shopping_broadcast
) -> None:
    milk = await _product(seeded_db)
    milk_id = milk.id
    await _open_item(seeded_db, milk)
    receipt = Receipt(
        id=uuid4(),
        image_path=f"data/receipts/{uuid4()}.jpg",
        processing_status="completed",
        ocr_structured={"lines": [{"name": "VALIO MAITO 1L", "price": 1.49}]},
        items_extracted=1,
        items_matched=0,
    )
    seeded_db.add(receipt)
    await seeded_db.commit()
    receipt_id = receipt.id

    with patch(
        "app.services.min_stock.crud_shopping.get_by_product",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm",
            json={
                "items": [
                    {
                        "index": 0,
                        "product_id": str(milk_id),
                        "quantity": 1,
                        "unit": "pcs",
                        "purchase_date": "2026-10-06",
                    }
                ]
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["items_created"] == 1
    shopping_broadcast.assert_not_awaited()


async def test_stock_add_ticks_the_products_open_items_and_a_replay_does_not(
    client: AsyncClient, seeded_db: AsyncSession, shopping_broadcast
) -> None:
    milk = await _product(seeded_db)
    item = await _open_item(seeded_db, milk)
    body = {"product_id": str(milk.id), "quantity": 10, "unit": "dl"}
    headers = {"Idempotency-Key": "restock-1"}

    first = await client.post("/api/stock/add", json=body, headers=headers)

    assert first.status_code == 201, first.text
    row = await _reload(seeded_db, item.id)
    assert row.is_purchased is True
    assert row.purchased_at is not None
    assert shopping_broadcast.await_count == 1

    # A new item added after the first request: a replay of that request did not add
    # any stock, so it must not tick this one.
    later = await _open_item(seeded_db, milk)
    replay = await client.post("/api/stock/add", json=body, headers=headers)

    assert replay.status_code == 201, replay.text
    assert replay.json() == first.json()
    row = await _reload(seeded_db, later.id)
    assert (row.is_purchased, row.purchased_at) == (False, None)
    assert shopping_broadcast.await_count == 1
