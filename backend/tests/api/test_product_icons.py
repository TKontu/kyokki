"""Q18: the endpoints around a product's drawn icon.

`GET /products/{id}/icon.svg` serves the stored drawing to an `<img src>` under a policy that
loads and runs nothing; `POST /products/{id}/icon` redraws it (optionally with the cook's
hint), `DELETE /products/{id}/icon` drops it for the category emoji, and renaming a product
redraws it. Responses carry `icon_status` and an `icon_version` for the URL.
"""

from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services import product_icons

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    '<circle cx="24" cy="24" r="16" fill="#E4453A" stroke="#2B2B2B" stroke-width="2"/>'
    "</svg>"
)


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, session_factory) -> None:
    """The drawing job opens its own session; here it is the test's."""
    monkeypatch.setattr(product_icons, "open_session", session_factory)


@pytest.fixture
def model():
    """The gateway, answering with SVG every time."""
    with patch.object(
        product_icons, "_complete", new=AsyncMock(return_value=SVG)
    ) as mock:
        yield mock


@pytest.fixture
def broadcast():
    with (
        patch(
            "app.api.endpoints.products.broadcast_product_update",
            new_callable=AsyncMock,
        ) as endpoint,
        patch(
            "app.services.product_icons.broadcast_product_update",
            new_callable=AsyncMock,
        ),
    ):
        yield endpoint


async def _product(db: AsyncSession, name: str = "Rye bread") -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="bread",
        storage_type="pantry",
        default_shelf_life_days=5,
        unit_type="count",
        default_unit="pcs",
    )
    db.add(product)
    await db.commit()
    return product


async def _reload(db: AsyncSession, product_id: UUID | str) -> ProductMaster:
    return (
        await db.execute(
            select(ProductMaster)
            .where(ProductMaster.id == UUID(str(product_id)))
            .options(undefer(ProductMaster.icon_svg))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _drawn(client: AsyncClient, db: AsyncSession) -> ProductMaster:
    product = await _product(db)
    response = await client.post(f"/api/products/{product.id}/icon", json={})
    assert response.status_code == 202
    return await _reload(db, product.id)


class TestRedraw:
    async def test_it_answers_202_and_the_drawing_lands(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)

        response = await client.post(f"/api/products/{product.id}/icon", json={})

        assert response.status_code == 202
        assert response.json()["icon_status"] == "pending"
        stored = await _reload(seeded_db, product.id)
        assert stored.icon_status == "ready"
        assert stored.icon_svg is not None and "<circle" in stored.icon_svg
        broadcast.assert_awaited()

    async def test_the_cooks_hint_reaches_the_model(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db, "Karelian pasty")

        await client.post(
            f"/api/products/{product.id}/icon",
            json={"hint": "oval rye pastry with rice filling"},
        )

        assert "oval rye pastry with rice filling" in model.await_args.args[0]

    async def test_no_body_is_fine(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)

        response = await client.post(f"/api/products/{product.id}/icon")

        assert response.status_code == 202

    async def test_an_overlong_hint_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)

        response = await client.post(
            f"/api/products/{product.id}/icon", json={"hint": "x" * 201}
        )

        assert response.status_code == 422
        model.assert_not_awaited()

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        response = await client.post(f"/api/products/{uuid4()}/icon", json={})

        assert response.status_code == 404
        model.assert_not_awaited()

    async def test_a_redraw_brings_back_a_cleared_icon(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _drawn(client, seeded_db)
        await client.delete(f"/api/products/{product.id}/icon")

        await client.post(f"/api/products/{product.id}/icon", json={})

        assert (await _reload(seeded_db, product.id)).icon_status == "ready"


class TestUseCategoryEmoji:
    async def test_it_drops_the_drawing(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _drawn(client, seeded_db)
        broadcast.reset_mock()

        response = await client.delete(f"/api/products/{product.id}/icon")

        assert response.status_code == 200
        body = response.json()
        assert body["icon_status"] == "cleared"
        assert body["icon_version"] is None
        stored = await _reload(seeded_db, product.id)
        assert stored.icon_svg is None
        broadcast.assert_awaited_once()
        assert broadcast.await_args.kwargs["action"] == "icon_updated"
        served = await client.get(f"/api/products/{product.id}/icon.svg")
        assert served.status_code == 404

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        response = await client.delete(f"/api/products/{uuid4()}/icon")

        assert response.status_code == 404


class TestServeTheSvg:
    async def test_the_drawing_is_served_as_svg_under_a_strict_policy(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _drawn(client, seeded_db)

        response = await client.get(f"/api/products/{product.id}/icon.svg")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert response.text == product.icon_svg
        # Nothing loads or runs: the sanitiser strips every style, so none is allowed (#12).
        assert response.headers["content-security-policy"] == "default-src 'none'"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["etag"] == f'"{product.icon_version}"'
        assert "max-age" in response.headers["cache-control"]

    async def test_a_matching_etag_is_304(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _drawn(client, seeded_db)

        response = await client.get(
            f"/api/products/{product.id}/icon.svg",
            headers={"If-None-Match": f'"{product.icon_version}"'},
        )

        assert response.status_code == 304
        assert response.content == b""

    async def test_no_drawing_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        response = await client.get(f"/api/products/{product.id}/icon.svg")

        assert response.status_code == 404

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(f"/api/products/{uuid4()}/icon.svg")

        assert response.status_code == 404

    async def test_it_does_not_clash_with_the_product_route(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        response = await client.get(f"/api/products/{product.id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(product.id)


class TestRenameRedraws:
    async def test_a_new_name_queues_a_redraw(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db, "Rye bred")

        response = await client.patch(
            f"/api/products/{product.id}", json={"canonical_name": "Rye bread"}
        )

        assert response.status_code == 200
        model.assert_awaited_once()
        assert "Rye bread (category: bread)" in model.await_args.args[0]
        assert (await _reload(seeded_db, product.id)).icon_status == "ready"

    async def test_the_same_name_does_not(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)

        await client.patch(
            f"/api/products/{product.id}",
            json={"canonical_name": "Rye bread", "default_shelf_life_days": 6},
        )

        model.assert_not_awaited()

    async def test_other_fields_do_not(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)

        await client.patch(
            f"/api/products/{product.id}", json={"default_shelf_life_days": 6}
        )

        model.assert_not_awaited()

    async def test_the_cooks_emoji_choice_survives_a_rename(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)
        await client.delete(f"/api/products/{product.id}/icon")

        await client.patch(
            f"/api/products/{product.id}", json={"canonical_name": "Dark rye"}
        )

        model.assert_not_awaited()
        assert (await _reload(seeded_db, product.id)).icon_status == "cleared"


class TestResponseFields:
    async def test_a_product_says_where_its_icon_stands(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _drawn(client, seeded_db)

        body = (await client.get(f"/api/products/{product.id}")).json()

        assert body["icon_status"] == "ready"
        assert body["icon_version"] == product.icon_version
        assert "icon_svg" not in body

    async def test_a_product_never_drawn_has_nulls(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        body = (await client.get(f"/api/products/{product.id}")).json()

        assert body["icon_status"] is None
        assert body["icon_version"] is None

    async def test_an_inventory_item_carries_its_products_icon_version(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _drawn(client, seeded_db)
        plain = await _product(seeded_db, "Plain bread")
        for p in (product, plain):
            seeded_db.add(
                InventoryItem(
                    product_master_id=p.id,
                    receipt_id=None,
                    initial_quantity=1,
                    current_quantity=1,
                    unit="pcs",
                    purchase_date=date(2026, 9, 26),
                    expiry_date=date(2026, 10, 1),
                    expiry_source="calculated",
                    status="sealed",
                    location="pantry",
                )
            )
        await seeded_db.commit()

        items = (await client.get("/api/inventory")).json()

        by_name = {i["product_name"]: i for i in items}
        assert by_name["Rye bread"]["product_icon_version"] == product.icon_version
        assert by_name["Plain bread"]["product_icon_version"] is None
        assert by_name["Plain bread"]["category_icon"]


NEW_LINE = {
    "name": "Tomato",
    "category": "produce",
    "quantity": 4,
    "unit": "pcs",
    "purchase_date": "2026-09-01",
}


async def _stored(db: AsyncSession, product_id: str) -> ProductMaster:
    stored = await _reload(db, product_id)
    assert stored.icon_status == "ready", stored.icon_status
    assert stored.icon_svg is not None and "<circle" in stored.icon_svg
    return stored


class TestEveryCreatePathDrawsTheIcon:
    """Review #7 and #10: a new product's icon is actually stored, whichever way it came in.

    The drawing call is stubbed and the job's session is the test's (see `_own_session`),
    as `test_estimate_on_create.py` does for the estimate.
    """

    async def test_quick_add(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        response = await client.post("/api/inventory/quick-add", json=NEW_LINE)

        assert response.status_code == 201
        await _stored(seeded_db, response.json()["product_master_id"])
        assert "Tomato (category: produce)" in model.await_args.args[0]

    async def test_stock_add(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        response = await client.post("/api/stock/add", json=NEW_LINE)

        assert response.status_code == 201
        assert response.json()["product_created"] is True
        await _stored(seeded_db, response.json()["item"]["product_master_id"])

    async def test_receipt_confirm_draws_each_new_product(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        from app.models.receipt import Receipt

        receipt = Receipt(
            image_path="receipts/q18.jpg",
            processing_status="completed",
            ocr_structured={"lines": []},
            items_extracted=0,
        )
        seeded_db.add(receipt)
        await seeded_db.commit()
        lines = [
            {**NEW_LINE, "name": "Tomato", "category": "produce", "quantity": 1},
            {**NEW_LINE, "name": "Orange", "category": "fruits", "quantity": 1},
        ]

        response = await client.post(
            f"/api/receipts/{receipt.id}/confirm", json={"items": lines}
        )

        assert response.status_code == 200
        assert response.json()["products_created"] == 2
        items = (
            (
                await seeded_db.execute(
                    select(InventoryItem).where(InventoryItem.receipt_id == receipt.id)
                )
            )
            .scalars()
            .all()
        )
        for item in items:
            await _stored(seeded_db, str(item.product_master_id))
        assert model.await_count == 2

    async def test_post_products(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Rye bread",
                "category": "bread",
                "storage_type": "pantry",
                "default_shelf_life_days": 5,
                "unit_type": "count",
                "default_unit": "pcs",
            },
        )

        assert response.status_code == 201
        await _stored(seeded_db, response.json()["id"])

    async def test_enrich_creating_a_product(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        enriched = {
            "canonical_name": "Valio Whole Milk 1L",
            "category": "dairy",
            "off_product_id": "5901234123457",
            "off_data": {"product_name": "Valio Whole Milk"},
        }
        with patch(
            "app.api.endpoints.products.enrich_product_from_off", return_value=enriched
        ):
            response = await client.post("/api/products/enrich?barcode=5901234123457")

        assert response.status_code == 201
        await _stored(seeded_db, response.json()["id"])

    async def test_enrich_updating_a_product_draws_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        existing = await _product(seeded_db, "Old name")
        existing.off_product_id = "5901234123457"  # type: ignore[assignment]
        await seeded_db.commit()
        enriched = {
            "canonical_name": "Valio Whole Milk 1L",
            "category": "dairy",
            "off_product_id": "5901234123457",
            "off_data": {"product_name": "Valio Whole Milk"},
        }
        with patch(
            "app.api.endpoints.products.enrich_product_from_off", return_value=enriched
        ):
            response = await client.post("/api/products/enrich?barcode=5901234123457")

        assert response.status_code == 200
        model.assert_not_awaited()
