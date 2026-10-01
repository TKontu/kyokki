"""Q18 build: the endpoints around a product's exact emoji.

`GET /products/emoji/reference` lists the pickable emoji; `PUT /products/{id}/emoji` is the
cook's own choice (an emoji sets `cook`, null sets `cleared`); `POST .../emoji/confirm` and
`.../emoji/reject` settle a model proposal; `GET /products?emoji_match=proposed` feeds the
review list. Every mutation broadcasts over the existing icon WebSocket path.
"""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import product_master as crud_product
from app.models.inventory_item import InventoryItem
from app.models.product_master import EmojiMatch, ProductMaster
from app.services import product_emoji, shelf_life_on_create


@pytest.fixture
def broadcast():
    with patch(
        "app.api.endpoints.products.broadcast_product_update", new_callable=AsyncMock
    ) as mock:
        yield mock


async def _product(
    db: AsyncSession,
    name: str = "Gouda",
    *,
    category: str = "cheese",
    emoji: str | None = None,
    emoji_match: EmojiMatch | None = None,
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
        emoji=emoji,
        emoji_match=emoji_match.value if emoji_match else None,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _reload(db: AsyncSession, product_id: UUID | str) -> ProductMaster:
    return await db.get(ProductMaster, UUID(str(product_id)), populate_existing=True)  # type: ignore[return-value]


class TestEmojiReference:
    async def test_it_lists_pickable_emoji_and_drops_household(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/products/emoji/reference")

        assert response.status_code == 200
        entries = response.json()
        assert {"emoji": "🥦", "name": "broccoli"} in entries
        assert not any(e["name"] == "soap" for e in entries)


class TestSetCookEmoji:
    async def test_the_cook_can_pick_an_emoji(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        product = await _product(seeded_db, "Mystery Item", category="snacks")

        response = await client.put(
            f"/api/products/{product.id}/emoji", json={"emoji": "🥨"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["emoji"] == "🥨"
        assert body["emoji_match"] == "cook"
        broadcast.assert_awaited_once()

    async def test_the_cook_can_clear_it(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        product = await _product(
            seeded_db, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT
        )

        response = await client.put(
            f"/api/products/{product.id}/emoji", json={"emoji": None}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["emoji"] is None
        assert body["emoji_match"] == "cleared"

    async def test_an_emoji_outside_the_reference_list_is_400(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, "Mystery Item", category="snacks")

        response = await client.put(
            f"/api/products/{product.id}/emoji", json={"emoji": "🚀"}
        )

        assert response.status_code == 400

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.put(
            f"/api/products/{uuid4()}/emoji", json={"emoji": "🥨"}
        )

        assert response.status_code == 404


class TestConfirmReject:
    async def test_confirming_makes_it_exact_and_shows_on_the_tile(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        product = await _product(
            seeded_db,
            "Brand New Thing",
            category="snacks",
            emoji="🥨",
            emoji_match=EmojiMatch.PROPOSED,
        )

        response = await client.post(f"/api/products/{product.id}/emoji/confirm")

        assert response.status_code == 200
        body = response.json()
        assert body["emoji_match"] == "exact"
        assert body["emoji"] == "🥨"
        learned = await crud_product.get_learned_emoji(seeded_db, "brand new thing")
        assert learned == "🥨"
        broadcast.assert_awaited_once()

    async def test_confirming_a_non_proposed_emoji_is_409(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, "Gouda")

        response = await client.post(f"/api/products/{product.id}/emoji/confirm")

        assert response.status_code == 409

    async def test_confirming_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(f"/api/products/{uuid4()}/emoji/confirm")

        assert response.status_code == 404

    async def test_rejecting_makes_it_none(
        self, client: AsyncClient, seeded_db: AsyncSession, broadcast
    ) -> None:
        product = await _product(
            seeded_db,
            "Brand New Thing",
            category="snacks",
            emoji="🥨",
            emoji_match=EmojiMatch.PROPOSED,
        )

        response = await client.post(f"/api/products/{product.id}/emoji/reject")

        assert response.status_code == 200
        body = response.json()
        assert body["emoji_match"] == "none"
        assert body["emoji"] is None

    async def test_rejecting_a_non_proposed_emoji_is_409(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, "Gouda")

        response = await client.post(f"/api/products/{product.id}/emoji/reject")

        assert response.status_code == 409


class TestListFilter:
    async def test_emoji_match_proposed_feeds_the_review_list(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        await _product(
            seeded_db,
            "Brand New Thing",
            category="snacks",
            emoji="🥨",
            emoji_match=EmojiMatch.PROPOSED,
        )
        await _product(seeded_db, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT)

        response = await client.get("/api/products", params={"emoji_match": "proposed"})

        assert response.status_code == 200
        names = {p["canonical_name"] for p in response.json()}
        assert names == {"Brand New Thing"}

    async def test_with_no_filter_every_product_is_listed(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        await _product(seeded_db, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT)
        await _product(seeded_db, "Mozzarella", emoji_match=EmojiMatch.NONE)

        response = await client.get("/api/products")

        assert response.status_code == 200
        assert len(response.json()) == 2


class TestProductResponseShape:
    async def test_the_response_carries_emoji_and_emoji_match(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(
            seeded_db, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT
        )

        response = await client.get(f"/api/products/{product.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["emoji"] == "🧀"
        assert body["emoji_match"] == "exact"

    async def test_a_never_looked_up_product_has_null_emoji_fields(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, "Gouda")

        response = await client.get(f"/api/products/{product.id}")

        body = response.json()
        assert body["emoji"] is None
        assert body["emoji_match"] is None


class TestInventoryProductEmoji:
    """`InventoryItemResponse.product_emoji` (Q18 build): derived from `product_master`,
    the model it belongs to is owned by a sibling lane this round."""

    async def test_shown_when_exact(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(
            seeded_db, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT
        )
        await _item(seeded_db, product)

        response = await client.get("/api/inventory")

        assert response.status_code == 200
        (item,) = [
            i for i in response.json() if i["product_master_id"] == str(product.id)
        ]
        assert item["product_emoji"] == "🧀"

    async def test_shown_when_cook(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(
            seeded_db,
            "Mystery Item",
            category="snacks",
            emoji="🥨",
            emoji_match=EmojiMatch.COOK,
        )
        await _item(seeded_db, product)

        response = await client.get("/api/inventory")

        (item,) = [
            i for i in response.json() if i["product_master_id"] == str(product.id)
        ]
        assert item["product_emoji"] == "🥨"

    async def test_hidden_when_only_proposed(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(
            seeded_db,
            "Brand New Thing",
            category="snacks",
            emoji="🥨",
            emoji_match=EmojiMatch.PROPOSED,
        )
        await _item(seeded_db, product)

        response = await client.get("/api/inventory")

        (item,) = [
            i for i in response.json() if i["product_master_id"] == str(product.id)
        ]
        assert item["product_emoji"] is None

    async def test_hidden_when_never_looked_up(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, "Gouda")
        await _item(seeded_db, product)

        response = await client.get("/api/inventory")

        (item,) = [
            i for i in response.json() if i["product_master_id"] == str(product.id)
        ]
        assert item["product_emoji"] is None


async def _item(db: AsyncSession, product: ProductMaster) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal("1"),
        current_quantity=Decimal("1"),
        unit="pcs",
        status="sealed",
        purchase_date=date(2026, 9, 1),
        expiry_date=date(2026, 9, 20),
        expiry_source="calculated",
        location="main_fridge",
    )
    db.add(item)
    await db.commit()
    return item


# --- end to end: a product created for real, with BackgroundTasks actually running -------


@pytest.fixture
def _background_jobs_use_the_test_session(session_factory) -> None:
    """Both background jobs open their own session; here it is the test's, so the rows
    they write are visible to the test's own assertions afterwards."""
    with (
        patch.object(shelf_life_on_create, "open_session", session_factory),
        patch.object(product_emoji, "open_session", session_factory),
    ):
        yield


class TestEndToEndOnCreate:
    """A product created through the real quick-add endpoint, with BackgroundTasks really
    running (PR #137 review, finding 4): before this, the lookup, the queueing and the
    model call were each tested in isolation, but nothing drove a create endpoint all the
    way through to a stored `emoji`/`emoji_match`."""

    async def test_a_table_name_ends_up_exact_and_shows_on_the_tile(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        _background_jobs_use_the_test_session,
    ) -> None:
        response = await client.post(
            "/api/inventory/quick-add",
            json={
                "name": "Gouda",
                "category": "cheese",
                "quantity": 1,
                "unit": "pcs",
                "purchase_date": "2026-09-01",
            },
        )

        assert response.status_code == 201
        product_id = response.json()["product_master_id"]

        product = await client.get(f"/api/products/{product_id}")
        assert product.json()["emoji"] == "🧀"
        assert product.json()["emoji_match"] == "exact"

        inventory = await client.get("/api/inventory")
        (item,) = [i for i in inventory.json() if i["product_master_id"] == product_id]
        assert item["product_emoji"] == "🧀"

    async def test_an_unknown_name_ends_up_proposed_with_the_model_stubbed(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        _background_jobs_use_the_test_session,
    ) -> None:
        async def fake_post_proposal(payload: dict) -> str:
            return json.dumps({"r": [{"i": 1, "e": "🥨", "m": "exact"}]})

        with patch.object(product_emoji, "_post_proposal", new=fake_post_proposal):
            response = await client.post(
                "/api/inventory/quick-add",
                json={
                    "name": "Brand New Snack Nobody Has Heard Of",
                    "category": "snacks",
                    "quantity": 1,
                    "unit": "pcs",
                    "purchase_date": "2026-09-01",
                },
            )

        assert response.status_code == 201
        product_id = response.json()["product_master_id"]

        product = await client.get(f"/api/products/{product_id}")
        body = product.json()
        assert body["emoji_match"] == "proposed"
        assert body["emoji"] == "🥨"

        inventory = await client.get("/api/inventory")
        (item,) = [i for i in inventory.json() if i["product_master_id"] == product_id]
        # A proposal is never shown on the tile until a person confirms it.
        assert item["product_emoji"] is None
