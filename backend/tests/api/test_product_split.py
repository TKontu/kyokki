"""The split API (CL8 L2): GET /products/{id}/sources, POST /products/{id}/split and
POST /products/reassignments/{id}/undo, exactly as the round's contract says."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_master import ProductMaster
from tests.services.test_product_split import (
    CHAIN,
    STEW_LINE,
    Kitchen,
    build_kitchen,
)


@pytest.fixture
async def kitchen(test_db: AsyncSession) -> Kitchen:
    return await build_kitchen(test_db)


@pytest.fixture
def broadcasts() -> Iterator[dict[str, AsyncMock]]:
    with (
        patch(
            "app.services.product_split.broadcast_inventory_update",
            new_callable=AsyncMock,
        ) as inventory,
        patch(
            "app.services.product_split.broadcast_product_update",
            new_callable=AsyncMock,
        ) as product,
    ):
        yield {"inventory": inventory, "product": product}


@pytest.fixture
def estimates() -> Iterator[MagicMock]:
    with patch("app.api.endpoints.products.schedule_estimates") as scheduled:
        yield scheduled


def stew_body(kitchen: Kitchen, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "item_ids": [str(item_id) for item_id in kitchen.stew_ids],
        "target": {"new": {"name": "Karelian stew", "category": "ready_meals"}},
    }
    body.update(overrides)
    return body


class TestSources:
    async def test_lists_the_groups(
        self, client: AsyncClient, kitchen: Kitchen
    ) -> None:
        response = await client.get(f"/api/products/{kitchen.pie.id}/sources")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["product_id"] == str(kitchen.pie.id)
        stew = next(
            s for s in body["sources"] if s["key"] == "line:s-group:karjalanpaisti"
        )
        assert stew == {
            "key": "line:s-group:karjalanpaisti",
            "label": STEW_LINE,
            "store_chain": CHAIN,
            "kind": "receipt",
            "item_ids": [str(kitchen.stew_calculated.id)],
            "active_count": 1,
            "total_count": 3,
            "first_seen": stew["first_seen"],
            "last_seen": stew["last_seen"],
        }
        assert len(stew["first_seen"]) == 10
        manual = next(s for s in body["sources"] if s["kind"] == "manual")
        assert manual["label"] == ""
        assert manual["store_chain"] is None

    async def test_unknown_product(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.get(f"/api/products/{uuid4()}/sources")
        assert response.status_code == 404


class TestSplit:
    async def test_split_to_a_new_product(
        self,
        client: AsyncClient,
        kitchen: Kitchen,
        broadcasts: dict[str, AsyncMock],
        estimates: MagicMock,
    ) -> None:
        pie_id = str(kitchen.pie.id)

        response = await client.post(
            f"/api/products/{pie_id}/split", json=stew_body(kitchen)
        )

        assert response.status_code == 200, response.text
        body = response.json()
        UUID(body["reassignment_id"])
        assert body["target_created"] is True
        assert body["source_product"]["id"] == pie_id
        assert body["target_product"]["canonical_name"] == "Karelian stew"
        assert sorted(body["moved_item_ids"]) == sorted(
            str(item_id) for item_id in kitchen.stew_ids
        )
        assert {"kind": "alias", "value": STEW_LINE, "store_chain": CHAIN} in body[
            "moved_keys"
        ]
        assert body["source_shelf_life"] == {
            "days": 2,
            "source": "cook",
            "observations_left": 3,
        }
        target_id = body["target_product"]["id"]
        estimates.assert_called_once()
        assert [str(i) for i in estimates.call_args.args[1]] == [target_id]

        # Broadcasts: every moved item, and both products
        updated = {
            str(call.kwargs["inventory_item_id"])
            for call in broadcasts["inventory"].await_args_list
            if call.kwargs["action"] == "updated"
        }
        assert set(body["moved_item_ids"]) <= updated
        products = {
            str(call.kwargs["product_id"])
            for call in broadcasts["product"].await_args_list
        }
        assert products == {pie_id, target_id}

    async def test_split_to_an_existing_product(
        self,
        client: AsyncClient,
        kitchen: Kitchen,
        test_db: AsyncSession,
        broadcasts: dict[str, AsyncMock],
        estimates: MagicMock,
    ) -> None:
        stew = ProductMaster(
            canonical_name="Beef stew",
            category="ready_meals",
            storage_type="refrigerator",
            default_shelf_life_days=4,
            unit_type="count",
            default_unit="pcs",
        )
        test_db.add(stew)
        await test_db.commit()

        response = await client.post(
            f"/api/products/{kitchen.pie.id}/split",
            json=stew_body(kitchen, target={"product_id": str(stew.id)}),
        )

        assert response.status_code == 200, response.text
        assert response.json()["target_created"] is False
        assert response.json()["target_product"]["id"] == str(stew.id)
        estimates.assert_not_called()

    async def test_move_keys_defaults_to_true_and_can_be_off(
        self, client: AsyncClient, kitchen: Kitchen, broadcasts, estimates
    ) -> None:
        response = await client.post(
            f"/api/products/{kitchen.pie.id}/split",
            json=stew_body(kitchen, move_keys=False),
        )

        assert response.status_code == 200, response.text
        assert response.json()["moved_keys"] == []

    async def test_name_exists(
        self, client: AsyncClient, kitchen: Kitchen, broadcasts, estimates
    ) -> None:
        response = await client.post(
            f"/api/products/{kitchen.pie.id}/split",
            json=stew_body(
                kitchen,
                target={"new": {"name": "karelian pie", "category": "ready_meals"}},
            ),
        )

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "name_exists",
            "product_id": str(kitchen.pie.id),
            "name": "Karelian pie",
        }

    @pytest.mark.parametrize("case", ["empty", "foreign", "same", "category", "name"])
    async def test_invalid(
        self,
        client: AsyncClient,
        kitchen: Kitchen,
        broadcasts,
        estimates,
        case: str,
    ) -> None:
        pie_id = str(kitchen.pie.id)
        body = stew_body(kitchen)
        if case == "empty":
            body["item_ids"] = []
        elif case == "foreign":
            body["item_ids"].append(str(uuid4()))
        elif case == "same":
            body["target"] = {"product_id": pie_id}
        elif case == "category":
            body["target"] = {"new": {"name": "Karelian stew", "category": "nope"}}
        elif case == "name":
            body["target"] = {"new": {"name": " ", "category": "ready_meals"}}

        response = await client.post(f"/api/products/{pie_id}/split", json=body)

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "invalid"
        assert detail["message"]

    async def test_unknown_product_and_target(
        self, client: AsyncClient, kitchen: Kitchen, broadcasts, estimates
    ) -> None:
        response = await client.post(
            f"/api/products/{uuid4()}/split", json=stew_body(kitchen)
        )
        assert response.status_code == 404

        response = await client.post(
            f"/api/products/{kitchen.pie.id}/split",
            json=stew_body(kitchen, target={"product_id": str(uuid4())}),
        )
        assert response.status_code == 404


class TestUndo:
    async def test_undo_restores_and_broadcasts(
        self,
        client: AsyncClient,
        kitchen: Kitchen,
        test_db: AsyncSession,
        broadcasts: dict[str, AsyncMock],
        estimates,
    ) -> None:
        pie_id = str(kitchen.pie.id)
        split = (
            await client.post(f"/api/products/{pie_id}/split", json=stew_body(kitchen))
        ).json()
        broadcasts["inventory"].reset_mock()
        broadcasts["product"].reset_mock()

        response = await client.post(
            f"/api/products/reassignments/{split['reassignment_id']}/undo"
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["reassignment_id"] == split["reassignment_id"]
        assert sorted(body["restored_item_ids"]) == sorted(split["moved_item_ids"])
        target_id = split["target_product"]["id"]
        assert await test_db.get(ProductMaster, UUID(target_id)) is None

        updated = {
            str(call.kwargs["inventory_item_id"])
            for call in broadcasts["inventory"].await_args_list
            if call.kwargs["action"] == "updated"
        }
        assert set(body["restored_item_ids"]) <= updated
        products = {
            str(call.kwargs["product_id"])
            for call in broadcasts["product"].await_args_list
        }
        assert products == {pie_id, target_id}

    async def test_undo_twice_is_stale(
        self, client: AsyncClient, kitchen: Kitchen, broadcasts, estimates
    ) -> None:
        split = (
            await client.post(
                f"/api/products/{kitchen.pie.id}/split", json=stew_body(kitchen)
            )
        ).json()
        url = f"/api/products/reassignments/{split['reassignment_id']}/undo"
        assert (await client.post(url)).status_code == 200

        response = await client.post(url)

        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "stale"}

    async def test_unknown_reassignment_routes_to_undo(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """The route is not shadowed by a `/{product_id}/...` route: 404, not 405/422."""
        response = await client.post(f"/api/products/reassignments/{uuid4()}/undo")

        assert response.status_code == 404
        assert "reassignment" in str(response.json()["detail"]).lower()
