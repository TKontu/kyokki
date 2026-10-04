"""Post-MVP frontier item 13: a display language, and product names in it.

Operator ruling (2026-10-02): "the system should have selectable display language. But of
course if the receipts are finnish the input data should kept as original." Products are
generic and English since MVP-R2; `display_names` adds an optional name per language on the
product (and, derived, on each inventory item), written only by the cook (`PATCH
/products/{id}`) or proposed by the model for a brand-new product. It is never a resolution
key: a receipt line still resolves only through `product_name`/`canonical_name`.
"""

from datetime import date, timedelta
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product_name import product_for_name


async def _create_product(
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


class TestSupportedLanguages:
    async def test_it_lists_finnish_but_not_english(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get("/api/products/languages")

        assert response.status_code == 200
        assert response.json() == ["fi"]


class TestProductDisplayNames:
    async def test_a_new_product_has_no_display_name_yet(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        assert product["display_names"] == {}

    async def test_the_cook_can_set_a_finnish_name(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        response = await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["display_names"] == {"fi": "Maito"}
        assert body["display_name_sources"] == {"fi": "cook"}

        reread = await client.get(f"/api/products/{product['id']}")
        assert reread.json()["display_names"] == {"fi": "Maito"}

    async def test_setting_it_again_replaces_it_not_adds_another(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )
        response = await client.patch(
            f"/api/products/{product['id']}",
            json={"display_names": {"fi": "Kermamaito"}},
        )

        assert response.status_code == 200
        assert response.json()["display_names"] == {"fi": "Kermamaito"}

    async def test_an_unsupported_language_code_is_rejected(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        response = await client.patch(
            f"/api/products/{product['id']}",
            json={"display_names": {"sv": "Mjölk"}},
        )

        assert response.status_code == 422

    async def test_an_empty_name_clears_it(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """F2 review: `{"fi": ""}` used to store an empty cook row that blocked a
        future proposal for good - a language already "had" a row, so nothing ever
        filled it in again."""
        product = await _create_product(client)
        await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )

        response = await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": ""}}
        )

        assert response.status_code == 200, response.text
        assert response.json()["display_names"] == {}
        assert response.json()["display_name_sources"] == {}

    async def test_a_whitespace_only_name_clears_it_too(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)
        await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )

        response = await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "   "}}
        )

        assert response.status_code == 200, response.text
        assert response.json()["display_names"] == {}

    async def test_clearing_a_language_with_no_row_is_a_no_op(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        response = await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": ""}}
        )

        assert response.status_code == 200, response.text
        assert response.json()["display_names"] == {}

    async def test_a_name_over_100_characters_is_a_400(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        response = await client.patch(
            f"/api/products/{product['id']}",
            json={"display_names": {"fi": "M" * 101}},
        )

        assert response.status_code == 400
        reread = await client.get(f"/api/products/{product['id']}")
        assert reread.json()["display_names"] == {}

    async def test_a_name_of_exactly_100_characters_is_accepted(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)
        name = "M" * 100

        response = await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": name}}
        )

        assert response.status_code == 200, response.text
        assert response.json()["display_names"] == {"fi": name}

    async def test_other_fields_are_untouched_when_only_the_name_changes(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        response = await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["canonical_name"] == "Milk"
        assert body["default_shelf_life_days"] == 7

    async def test_display_names_never_affect_resolution(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """A cook-set Finnish name is not a synonym (the spec's own line): the English
        canonical name is still the only word this product resolves to."""
        product = await _create_product(client, "Milk")
        await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )

        resolved = await product_for_name(seeded_db, "Milk")
        assert resolved is not None
        assert str(resolved.id) == product["id"]

        not_resolved = await product_for_name(seeded_db, "Maito")
        assert not_resolved is None


class TestInventoryCarriesProductDisplayNames:
    async def test_an_inventory_item_carries_its_products_display_names(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)
        await client.patch(
            f"/api/products/{product['id']}", json={"display_names": {"fi": "Maito"}}
        )

        today = date.today()
        created = await client.post(
            "/api/inventory",
            json={
                "product_master_id": product["id"],
                "initial_quantity": 1000,
                "current_quantity": 1000,
                "unit": "dl",
                "expiry_date": str(today + timedelta(days=7)),
                "location": "main_fridge",
            },
        )
        assert created.status_code == 201, created.text

        listed = await client.get("/api/inventory")
        assert listed.status_code == 200
        (item,) = [row for row in listed.json() if row["id"] == created.json()["id"]]
        assert item["product_display_names"] == {"fi": "Maito"}

    async def test_an_item_whose_product_has_no_display_name_carries_an_empty_map(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        today = date.today()
        created = await client.post(
            "/api/inventory",
            json={
                "product_master_id": product["id"],
                "initial_quantity": 1000,
                "current_quantity": 1000,
                "unit": "dl",
                "expiry_date": str(today + timedelta(days=7)),
                "location": "main_fridge",
            },
        )
        assert created.status_code == 201, created.text

        listed = await client.get("/api/inventory")
        (item,) = [row for row in listed.json() if row["id"] == created.json()["id"]]
        assert item["product_display_names"] == {}


class TestMinStockQuantity:
    """Folded into this lane: an editable Minimum stock field, which A1's auto-shopping
    needs (`min_stock_quantity` already exists in the API; only the PATCH path is new
    here - the field itself was already in `ProductMasterUpdate`)."""

    async def test_the_cook_can_set_a_minimum_stock(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _create_product(client)

        response = await client.patch(
            f"/api/products/{product['id']}", json={"min_stock_quantity": 5}
        )

        assert response.status_code == 200
        assert response.json()["min_stock_quantity"] == "5" or (
            float(response.json()["min_stock_quantity"]) == 5.0
        )


class TestHandAddedProductGetsAProposalToo:
    """F4 (review of PR #162): `POST /products` typed the English name, so it schedules
    a Finnish proposal too - the same way it already schedules the icon directly,
    without going through `schedule_estimates` (which this path never calls, since the
    cook's own shelf life must never be re-estimated)."""

    async def test_it_schedules_the_proposal(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        from unittest.mock import patch

        with patch(
            "app.api.endpoints.products.display_names.schedule_display_names"
        ) as scheduled:
            response = await client.post(
                "/api/products",
                json={
                    "canonical_name": "Hand Added Milk",
                    "category": "dairy",
                    "storage_type": "refrigerator",
                    "default_shelf_life_days": 7,
                    "unit_type": "volume",
                    "default_unit": "dl",
                },
            )

        assert response.status_code == 201, response.text
        scheduled.assert_called_once()
        (tasks_arg, ids_arg), _ = scheduled.call_args
        assert [str(i) for i in ids_arg] == [response.json()["id"]]


class TestRenameReproposesTheDisplayName:
    """Task 1 (2026-10-03 production backfill finding): a rename re-proposes the
    Finnish name through the same rename hook that already reschedules the icon."""

    async def test_a_rename_schedules_a_reproposal(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        from unittest.mock import patch

        product = await _create_product(client, "Rye crispbread")

        with patch(
            "app.api.endpoints.products.display_names.schedule_display_name_rename"
        ) as scheduled:
            response = await client.patch(
                f"/api/products/{product['id']}", json={"canonical_name": "Rye bread"}
            )

        assert response.status_code == 200, response.text
        scheduled.assert_called_once()
        (tasks_arg, product_id_arg), _ = scheduled.call_args
        assert str(product_id_arg) == product["id"]

    async def test_not_renaming_does_not_schedule_a_reproposal(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        from unittest.mock import patch

        product = await _create_product(client, "Milk")

        with patch(
            "app.api.endpoints.products.display_names.schedule_display_name_rename"
        ) as scheduled:
            response = await client.patch(
                f"/api/products/{product['id']}", json={"default_shelf_life_days": 5}
            )

        assert response.status_code == 200, response.text
        scheduled.assert_not_called()

    async def test_a_rename_re_proposes_a_model_name_end_to_end(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        session_factory,
    ) -> None:
        """No mocked scheduling this time: the background task really runs (FastAPI
        runs `BackgroundTasks` before the response is sent over `ASGITransport`), with
        the job's own session rebound to the test's (it opens its own, exactly like
        the icon and emoji jobs do - `tests/api/test_product_emoji.py`'s own pattern)
        and the gateway mocked at `_post_proposal`."""
        import json as _json
        from unittest.mock import AsyncMock, patch

        from app.crud import product_master as crud_product
        from app.services import display_names as display_names_module

        product = await _create_product(client, "Coffee oat milk")
        subject = await crud_product.get_display_name_subject(
            seeded_db, UUID(product["id"])
        )
        assert subject is not None
        await crud_product.set_display_name(
            seeded_db, subject, language="fi", name="Kauramaito", source="model"
        )
        await seeded_db.commit()

        reply = _json.dumps({"r": [{"i": 1, "fi": "Kahvillinen kauramaito"}]})
        with (
            patch.object(display_names_module, "open_session", session_factory),
            patch.object(
                display_names_module,
                "_post_proposal",
                new_callable=AsyncMock,
                return_value=reply,
            ),
        ):
            response = await client.patch(
                f"/api/products/{product['id']}",
                json={"canonical_name": "Coffee flavoured oat milk"},
            )

        assert response.status_code == 200, response.text
        reread = await client.get(f"/api/products/{product['id']}")
        assert reread.json()["display_names"] == {"fi": "Kahvillinen kauramaito"}
        assert reread.json()["display_name_sources"] == {"fi": "model"}

    async def test_a_rename_never_re_proposes_a_cook_name_end_to_end(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        session_factory,
    ) -> None:
        from unittest.mock import AsyncMock, patch

        from app.services import display_names as display_names_module

        product = await _create_product(client, "Milk")
        await client.patch(
            f"/api/products/{product['id']}",
            json={"display_names": {"fi": "Oma maito"}},
        )

        with (
            patch.object(display_names_module, "open_session", session_factory),
            patch.object(
                display_names_module, "_post_proposal", new_callable=AsyncMock
            ) as proposal,
        ):
            response = await client.patch(
                f"/api/products/{product['id']}", json={"canonical_name": "Whole milk"}
            )

        assert response.status_code == 200, response.text
        proposal.assert_not_awaited()
        reread = await client.get(f"/api/products/{product['id']}")
        assert reread.json()["display_names"] == {"fi": "Oma maito"}
