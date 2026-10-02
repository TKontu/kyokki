"""Q18-G2: the endpoints around a product's generated icon.

`GET /products/{id}/icon.png` serves the stored image to an `<img src>`; `POST
/products/{id}/icon` is Regenerate (a new seed every time, optionally with the cook's hint;
409 when generation is not configured); `DELETE /products/{id}/icon` drops it for the
category emoji; renaming a product regenerates it, but only when generation is configured.
Responses carry `icon_status`, `icon_version` and `generation_enabled`.
"""

from datetime import date
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import settings
from app.models.inventory_item import InventoryItem
from app.models.product_master import EmojiMatch, ProductMaster
from app.services import product_icons


def _fake_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (8, 8), (228, 69, 58, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


FAKE_PNG = _fake_png()


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, session_factory) -> None:
    """The render job opens its own session; here it is the test's."""
    monkeypatch.setattr(product_icons, "open_session", session_factory)


@pytest.fixture
def comfyui_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generation configured: `COMFYUI_BASE_URL` set. Nothing here ever reaches the network -
    see the `model` fixture, which stubs the client itself."""
    monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "http://comfyui.test")


@pytest.fixture
def model(comfyui_enabled: None):
    """The ComfyUI client, answering with one fake PNG every time."""
    with patch.object(
        product_icons.comfyui, "render", new=AsyncMock(return_value=[FAKE_PNG])
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


async def _product(
    db: AsyncSession,
    name: str = "Rye bread",
    *,
    emoji_match: EmojiMatch | None = None,
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="bread",
        storage_type="pantry",
        default_shelf_life_days=5,
        unit_type="count",
        default_unit="pcs",
        emoji_match=emoji_match.value if emoji_match else None,
    )
    db.add(product)
    await db.commit()
    return product


async def _reload(db: AsyncSession, product_id: UUID | str) -> ProductMaster:
    return (
        await db.execute(
            select(ProductMaster)
            .where(ProductMaster.id == UUID(str(product_id)))
            .options(undefer(ProductMaster.icon_image))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _generated(client: AsyncClient, db: AsyncSession) -> ProductMaster:
    product = await _product(db)
    response = await client.post(f"/api/products/{product.id}/icon", json={})
    assert response.status_code == 202
    return await _reload(db, product.id)


class TestRegenerate:
    async def test_it_answers_202_and_the_image_lands(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db)

        response = await client.post(f"/api/products/{product.id}/icon", json={})

        assert response.status_code == 202
        assert response.json()["icon_status"] == "pending"
        stored = await _reload(seeded_db, product.id)
        assert stored.icon_status == "ready"
        assert stored.icon_image is not None
        assert stored.icon_seed is not None
        broadcast.assert_awaited()

    async def test_the_cooks_hint_reaches_the_subject(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db, "Karelian pasty")

        await client.post(
            f"/api/products/{product.id}/icon",
            json={"hint": "oval rye pastry with rice filling"},
        )

        (workflow,), _ = model.await_args
        assert "oval rye pastry with rice filling" in workflow["3"]["inputs"]["text"]
        assert "Karelian pasty" in workflow["3"]["inputs"]["text"]

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

    async def test_a_regenerate_brings_back_a_cleared_icon(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)
        await client.delete(f"/api/products/{product.id}/icon")

        await client.post(f"/api/products/{product.id}/icon", json={})

        assert (await _reload(seeded_db, product.id)).icon_status == "ready"

    async def test_each_regenerate_uses_a_new_seed(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)
        first_seed = product.icon_seed

        await client.post(f"/api/products/{product.id}/icon", json={})

        assert (await _reload(seeded_db, product.id)).icon_seed != first_seed

    async def test_disabled_answers_409_and_generates_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        """`COMFYUI_BASE_URL` is empty by default in every test (no `comfyui_enabled`)."""
        product = await _product(seeded_db)

        response = await client.post(f"/api/products/{product.id}/icon", json={})

        assert response.status_code == 409
        assert (await _reload(seeded_db, product.id)).icon_status is None

    async def test_refuses_an_exact_emoji_product(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        """F5 (planner ruling): that image could never show, so the sheet should not even
        be allowed to ask for one."""
        product = await _product(seeded_db, emoji_match=EmojiMatch.EXACT)

        response = await client.post(f"/api/products/{product.id}/icon", json={})

        assert response.status_code == 409
        assert "exact emoji" in response.json()["detail"]
        model.assert_not_awaited()
        assert (await _reload(seeded_db, product.id)).icon_status is None

    async def test_refuses_a_cook_emoji_product(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db, emoji_match=EmojiMatch.COOK)

        response = await client.post(f"/api/products/{product.id}/icon", json={})

        assert response.status_code == 409
        model.assert_not_awaited()

    async def test_still_allowed_on_a_cleared_product(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        """F5: Regenerate un-clears - the cook's latest ask wins."""
        product = await _generated(client, seeded_db)
        await client.delete(f"/api/products/{product.id}/icon")

        response = await client.post(f"/api/products/{product.id}/icon", json={})

        assert response.status_code == 202
        assert (await _reload(seeded_db, product.id)).icon_status == "ready"


class TestUseCategoryEmoji:
    async def test_it_drops_the_image(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)
        broadcast.reset_mock()

        response = await client.delete(f"/api/products/{product.id}/icon")

        assert response.status_code == 200
        body = response.json()
        assert body["icon_status"] == "cleared"
        assert body["icon_version"] is None
        stored = await _reload(seeded_db, product.id)
        assert stored.icon_image is None
        assert stored.icon_seed is None
        broadcast.assert_awaited_once()
        assert broadcast.await_args.kwargs["action"] == "icon_updated"
        served = await client.get(f"/api/products/{product.id}/icon.png")
        assert served.status_code == 404

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        response = await client.delete(f"/api/products/{uuid4()}/icon")

        assert response.status_code == 404

    async def test_works_even_when_generation_is_not_configured(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        """Clearing is a local database change; it needs no ComfyUI."""
        product = await _product(seeded_db)

        response = await client.delete(f"/api/products/{product.id}/icon")

        assert response.status_code == 200
        assert response.json()["icon_status"] == "cleared"


class TestServeThePng:
    async def test_the_image_is_served_with_nosniff_etag_and_cache(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)

        response = await client.get(f"/api/products/{product.id}/icon.png")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")
        assert response.content == product.icon_image
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["etag"] == f'"{product.icon_version}"'
        assert "max-age" in response.headers["cache-control"]
        assert "private" in response.headers["cache-control"]

    async def test_a_matching_etag_is_304(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)

        response = await client.get(
            f"/api/products/{product.id}/icon.png",
            headers={"If-None-Match": f'"{product.icon_version}"'},
        )

        assert response.status_code == 304
        assert response.content == b""

    async def test_no_image_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        response = await client.get(f"/api/products/{product.id}/icon.png")

        assert response.status_code == 404

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(f"/api/products/{uuid4()}/icon.png")

        assert response.status_code == 404

    async def test_it_does_not_clash_with_the_product_route(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        response = await client.get(f"/api/products/{product.id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(product.id)


class TestRenameRegenerates:
    async def test_a_new_name_queues_a_regenerate(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _product(seeded_db, "Rye bred")

        response = await client.patch(
            f"/api/products/{product.id}", json={"canonical_name": "Rye bread"}
        )

        assert response.status_code == 200
        model.assert_awaited_once()
        (workflow,), _ = model.await_args
        assert "Rye bread" in workflow["3"]["inputs"]["text"]
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

    async def test_renaming_an_exact_emoji_product_queues_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        """F2 review: a rename goes through the automatic gate, same as any other
        automatic scheduling - not Regenerate's explicit path (which would have bypassed
        it, since `request_redraw` used to pre-mark the row pending)."""
        product = await _product(seeded_db, "Rye bred", emoji_match=EmojiMatch.EXACT)

        response = await client.patch(
            f"/api/products/{product.id}", json={"canonical_name": "Rye bread"}
        )

        assert response.status_code == 200
        model.assert_not_awaited()
        assert (await _reload(seeded_db, product.id)).icon_status is None

    async def test_a_rename_with_generation_off_queues_and_breaks_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        """`COMFYUI_BASE_URL` empty (no `comfyui_enabled`): the rename itself still succeeds,
        and the product is never left stuck `pending` with nothing to resolve it."""
        product = await _product(seeded_db, "Rye bred")

        response = await client.patch(
            f"/api/products/{product.id}", json={"canonical_name": "Rye bread"}
        )

        assert response.status_code == 200
        assert (await _reload(seeded_db, product.id)).icon_status is None


class TestResponseFields:
    async def test_a_product_says_where_its_icon_stands(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)

        body = (await client.get(f"/api/products/{product.id}")).json()

        assert body["icon_status"] == "ready"
        assert body["icon_version"] == product.icon_version
        assert "icon_image" not in body
        assert "icon_svg" not in body

    async def test_a_product_never_generated_has_nulls(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        body = (await client.get(f"/api/products/{product.id}")).json()

        assert body["icon_status"] is None
        assert body["icon_version"] is None

    async def test_generation_enabled_follows_the_setting(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        assert (await client.get(f"/api/products/{product.id}")).json()[
            "generation_enabled"
        ] is False

    async def test_generation_enabled_when_configured(
        self, client: AsyncClient, seeded_db: AsyncSession, comfyui_enabled: None
    ) -> None:
        product = await _product(seeded_db)

        assert (await client.get(f"/api/products/{product.id}")).json()[
            "generation_enabled"
        ] is True

    async def test_an_inventory_item_carries_its_products_icon_version(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        product = await _generated(client, seeded_db)
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
    assert stored.icon_image is not None
    return stored


class TestEveryCreatePathGeneratesTheIcon:
    """Review #7 and #10 (Q18) still apply: a new product's icon is actually stored,
    whichever way it came in. The render call is stubbed and the job's session is the
    test's (see `_own_session`), as `test_estimate_on_create.py` does for the estimate.
    """

    async def test_quick_add(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        response = await client.post("/api/inventory/quick-add", json=NEW_LINE)

        assert response.status_code == 201
        await _stored(seeded_db, response.json()["product_master_id"])
        (workflow,), _ = model.await_args
        assert "Tomato" in workflow["3"]["inputs"]["text"]

    async def test_stock_add(
        self, client: AsyncClient, seeded_db: AsyncSession, model, broadcast
    ) -> None:
        response = await client.post("/api/stock/add", json=NEW_LINE)

        assert response.status_code == 201
        assert response.json()["product_created"] is True
        await _stored(seeded_db, response.json()["item"]["product_master_id"])

    async def test_receipt_confirm_generates_each_new_product(
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

    async def test_enrich_updating_a_product_generates_nothing(
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

    async def test_every_create_path_generates_nothing_when_disabled(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        """`COMFYUI_BASE_URL` empty (no `comfyui_enabled`, no `model`): creation still
        succeeds, and the new product is simply never generated - never stuck `pending`."""
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Oat drink",
                "category": "dairy",
                "storage_type": "pantry",
                "default_shelf_life_days": 200,
                "unit_type": "count",
                "default_unit": "pcs",
            },
        )

        assert response.status_code == 201
        stored = await _reload(seeded_db, response.json()["id"])
        assert stored.icon_status is None
        assert stored.icon_image is None
