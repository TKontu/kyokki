"""Post-MVP frontier item 13, phase 2: display names on Gone and shopping rows.

Operator ruling (2026-10-02): the system gets a selectable display language; receipts and
their printed text stay as scanned. Phase 1 (#162) carried a product's per-language name onto
inventory items (`product_display_names`); this is the same carry onto the two other places a
product's name shows up read-only - the consumption log (Gone) and the shopping list.
"""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _product(
    client: AsyncClient, name: str = "Milk", *, category: str = "dairy"
) -> dict:
    response = await client.post(
        "/api/products",
        json={
            "canonical_name": name,
            "category": category,
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "dl",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _set_finnish_name(client: AsyncClient, product_id: str, name: str) -> None:
    response = await client.patch(
        f"/api/products/{product_id}", json={"display_names": {"fi": name}}
    )
    assert response.status_code == 200, response.text


class TestShoppingItemDisplayNames:
    async def test_an_item_linked_to_a_named_product_carries_its_display_names(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client)
        await _set_finnish_name(client, product["id"], "Maito")

        response = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": product["id"],
                "name": product["canonical_name"],
                "quantity": "2",
                "unit": "dl",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["product_display_names"] == {"fi": "Maito"}

    async def test_a_free_text_item_carries_an_empty_map(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/shopping/",
            json={"name": "Tin foil", "quantity": "1", "unit": "pcs"},
        )

        assert response.status_code == 201, response.text
        assert response.json()["product_display_names"] == {}

    async def test_an_item_whose_product_has_no_display_name_carries_an_empty_map(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Oat milk")

        response = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": product["id"],
                "name": product["canonical_name"],
                "quantity": "1",
                "unit": "dl",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["product_display_names"] == {}

    async def test_a_cook_renamed_item_keeps_an_empty_map_so_its_own_wording_is_kept(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """A row whose `name` no longer matches the product's canonical name - the cook
        retyped it - must not have a translation substituted over that wording."""
        product = await _product(client)
        await _set_finnish_name(client, product["id"], "Maito")

        response = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": product["id"],
                "name": "Semi-skimmed, the good one",
                "quantity": "2",
                "unit": "dl",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["product_display_names"] == {}
        assert response.json()["name"] == "Semi-skimmed, the good one"

    async def test_the_names_still_show_reading_the_list_back(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client)
        await _set_finnish_name(client, product["id"], "Maito")
        created = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": product["id"],
                "name": product["canonical_name"],
                "quantity": "2",
                "unit": "dl",
            },
        )
        assert created.status_code == 201, created.text

        listed = await client.get("/api/shopping/")
        assert listed.status_code == 200
        (item,) = [row for row in listed.json() if row["id"] == created.json()["id"]]
        assert item["product_display_names"] == {"fi": "Maito"}

    async def test_the_names_still_show_after_an_update(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client)
        await _set_finnish_name(client, product["id"], "Maito")
        created = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": product["id"],
                "name": product["canonical_name"],
                "quantity": "2",
                "unit": "dl",
            },
        )
        assert created.status_code == 201, created.text

        updated = await client.patch(
            f"/api/shopping/{created.json()['id']}", json={"quantity": "3"}
        )

        assert updated.status_code == 200, updated.text
        assert updated.json()["product_display_names"] == {"fi": "Maito"}


class TestConsumptionLogDisplayNames:
    async def test_a_discarded_items_row_carries_its_products_display_names(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Yoghurt")
        await _set_finnish_name(client, product["id"], "Jogurtti")

        created = await client.post(
            "/api/inventory",
            json={
                "product_master_id": product["id"],
                "initial_quantity": 10,
                "current_quantity": 10,
                "unit": "dl",
                "expiry_date": str(date.today() + timedelta(days=7)),
            },
        )
        assert created.status_code == 201, created.text

        discarded = await client.patch(
            f"/api/inventory/{created.json()['id']}", json={"status": "discarded"}
        )
        assert discarded.status_code == 200, discarded.text

        logged = await client.get("/api/consumption-log")
        assert logged.status_code == 200
        (row,) = [
            entry
            for entry in logged.json()
            if entry["inventory_item_id"] == created.json()["id"]
        ]
        assert row["product_display_names"] == {"fi": "Jogurtti"}

    async def test_a_row_whose_product_has_no_display_name_carries_an_empty_map(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Rye bread")

        created = await client.post(
            "/api/inventory",
            json={
                "product_master_id": product["id"],
                "initial_quantity": 10,
                "current_quantity": 10,
                "unit": "dl",
                "expiry_date": str(date.today() + timedelta(days=7)),
            },
        )
        assert created.status_code == 201, created.text

        discarded = await client.patch(
            f"/api/inventory/{created.json()['id']}", json={"status": "discarded"}
        )
        assert discarded.status_code == 200, discarded.text

        logged = await client.get("/api/consumption-log")
        (row,) = [
            entry
            for entry in logged.json()
            if entry["inventory_item_id"] == created.json()["id"]
        ]
        assert row["product_display_names"] == {}
