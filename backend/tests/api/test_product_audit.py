"""CL8 L4: `GET /api/audit/product-joins`, read-only."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias

URL = "/api/audit/product-joins"
STEW = "KARJALANPAISTI"
RICE_PIE = "VUOKSEN RIISIPIIRAKKA 15KPL"
TABLES = (
    "product_master",
    "inventory_item",
    "receipt",
    "store_product_alias",
    "product_name",
    "consumption_log",
)


def _line(name: str, product: ProductMaster, source: str) -> dict[str, Any]:
    return {
        "name": name,
        "generic_name": "Karelian pie",
        "line_id": str(uuid4()),
        "product_id": str(product.id),
        "product_name": str(product.canonical_name),
        "match_source": source,
        "resolution": {"source": source, "verified": source == "alias"},
    }


@pytest.fixture
async def stew(seeded_db: AsyncSession) -> ProductMaster:
    """The production shape: a `selected` stew line and two alias rice-pie lines."""
    db = seeded_db
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Karelian stew",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="count",
        default_unit="pcs",
        default_quantity=Decimal("1"),
    )
    db.add(product)
    await db.flush()
    db.add(
        StoreProductAlias(
            product_master_id=product.id,
            store_chain="s-group",
            receipt_name=RICE_PIE,
            source="cook",
            manually_verified=True,
            occurrence_count=2,
        )
    )
    db.add(
        StoreProductAlias(
            product_master_id=product.id,
            store_chain="s-group",
            receipt_name=STEW,
            source="model",
            manually_verified=False,
            occurrence_count=1,
        )
    )
    db.add(
        ProductName(product_master_id=product.id, name="karelian pie", source="model")
    )
    for purchased, lines in (
        (date(2026, 9, 30), [_line(RICE_PIE, product, "alias")]),
        (
            date(2026, 10, 6),
            [_line(STEW, product, "selected"), _line(RICE_PIE, product, "alias")],
        ),
    ):
        receipt = Receipt(
            id=uuid4(),
            store_chain="s-group",
            purchase_date=purchased,
            image_path="data/receipts/none.jpg",
            processing_status="confirmed",
            ocr_structured={"lines": lines},
        )
        db.add(receipt)
        await db.flush()
        for index, stored in enumerate(lines):
            db.add(
                InventoryItem(
                    product_master_id=product.id,
                    receipt_id=receipt.id,
                    receipt_line_index=index,
                    receipt_line_text=stored["name"],
                    initial_quantity=Decimal("1"),
                    current_quantity=Decimal("1"),
                    unit="pcs",
                    status="sealed",
                    purchase_date=purchased,
                    expiry_date=purchased,
                )
            )
    await db.commit()
    return product


async def _snapshot(db: AsyncSession) -> dict[str, list[Any]]:
    snapshot: dict[str, list[Any]] = {}
    for table in TABLES:
        rows = await db.execute(text(f"SELECT * FROM {table} ORDER BY id"))
        snapshot[table] = [tuple(row) for row in rows.all()]
    return snapshot


async def test_lists_the_production_case(
    client: AsyncClient, stew: ProductMaster
) -> None:
    response = await client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"products", "model_names", "unverified_aliases"}
    entry = next(p for p in body["products"] if p["product_id"] == str(stew.id))
    assert entry["product_name"] == "Karelian stew"
    assert {g["label"] for g in entry["groups"]} == {STEW, RICE_PIE}
    group = next(g for g in entry["groups"] if g["label"] == RICE_PIE)
    assert set(group) == {
        "label",
        "store_chain",
        "match_sources",
        "generic_names",
        "active_count",
        "total_count",
        "first_seen",
        "last_seen",
    }
    assert group["first_seen"] == "2026-09-30"
    assert group["last_seen"] == "2026-10-06"
    assert group["total_count"] == 2
    assert entry["reasons"]
    assert isinstance(entry["min_similarity"], float)

    model_name = next(n for n in body["model_names"] if n["name"] == "karelian pie")
    assert model_name["product_id"] == str(stew.id)
    assert model_name["item_count"] == 3
    alias = next(a for a in body["unverified_aliases"] if a["receipt_name"] == STEW)
    assert alias["occurrence_count"] == 1
    assert alias["store_chain"] == "s-group"
    assert all(a["receipt_name"] != RICE_PIE for a in body["unverified_aliases"])


async def test_writes_nothing(
    client: AsyncClient,
    seeded_db: AsyncSession,
    stew: ProductMaster,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = await _snapshot(seeded_db)

    async def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the audit must not commit")

    monkeypatch.setattr(seeded_db, "commit", refuse)
    response = await client.get(URL)
    monkeypatch.undo()

    assert response.status_code == 200
    assert not seeded_db.new and not seeded_db.dirty and not seeded_db.deleted
    assert await _snapshot(seeded_db) == before


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_is_get_only(
    client: AsyncClient, seeded_db: AsyncSession, method: str
) -> None:
    response = await client.request(method, URL)

    assert response.status_code == 405


async def test_empty_catalog(client: AsyncClient, seeded_db: AsyncSession) -> None:
    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "products": [],
        "model_names": [],
        "unverified_aliases": [],
    }
