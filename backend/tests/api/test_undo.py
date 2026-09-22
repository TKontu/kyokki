"""One general undo: the most recent change to stock, reversed, one step at a time."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_log import ConsumptionLog

URL = "/api/inventory/undo"
IN_A_WEEK = str(date.today() + timedelta(days=7))


@pytest.fixture
async def cream(client: AsyncClient, seeded_db: AsyncSession) -> dict:
    """A product whose pack keeps three days once opened, so opening moves the expiry."""
    response = await client.post(
        "/api/products",
        json={
            "canonical_name": "Cream",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 14,
            "opened_shelf_life_days": 3,
            "unit_type": "volume",
            "default_unit": "dl",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _item(client: AsyncClient, product_id: str, quantity: float = 10) -> dict:
    response = await client.post(
        "/api/inventory",
        json={
            "product_master_id": product_id,
            "initial_quantity": quantity,
            "current_quantity": quantity,
            "unit": "dl",
            "expiry_date": IN_A_WEEK,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _get(client: AsyncClient, item_id: str) -> dict:
    return (await client.get(f"/api/inventory/{item_id}")).json()


async def _consume(client: AsyncClient, item_id: str, quantity: float) -> None:
    response = await client.post(
        f"/api/inventory/{item_id}/consume", json={"quantity": quantity}
    )
    assert response.status_code == 200, response.text


async def _undo(client: AsyncClient) -> dict:
    """Undo whatever the preview says is next, as the header button does."""
    preview = (await client.get(URL)).json()
    assert preview is not None, "nothing to undo"
    response = await client.post(URL, json={"batch_id": preview["batch_id"]})
    assert response.status_code == 200, response.text
    return response.json()


def _state(item: dict) -> dict:
    keys = (
        "current_quantity",
        "initial_quantity",
        "status",
        "opened_date",
        "expiry_date",
        "consumed_at",
    )
    return {key: item[key] for key in keys}


class TestNothingToUndo:
    async def test_a_fresh_kitchen_has_nothing_to_undo(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(URL)

        assert response.status_code == 200
        assert response.json() is None

    async def test_undoing_nothing_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(URL, json={"batch_id": str(uuid4())})

        assert response.status_code == 409

    async def test_history_from_before_undo_existed_is_not_undoable(
        self, client: AsyncClient, seeded_db: AsyncSession, cream: dict
    ) -> None:
        """Rows logged before this change do not know what they overwrote."""
        item = await _item(client, cream["id"])
        seeded_db.add(
            ConsumptionLog(
                inventory_item_id=UUID(item["id"]),
                product_master_id=UUID(cream["id"]),
                action="use_partial",
                quantity_consumed=Decimal("1"),
                quantity_after=Decimal("9"),
                batch_id=uuid4(),
                previous=None,
            )
        )
        await seeded_db.commit()

        assert (await client.get(URL)).json() is None


class TestThePreview:
    async def test_it_says_what_the_next_undo_will_reverse(
        self, client: AsyncClient, cream: dict
    ) -> None:
        item = await _item(client, cream["id"])
        await _consume(client, item["id"], 2.5)

        preview = (await client.get(URL)).json()

        assert preview["batch_id"]
        assert preview["logged_at"]
        assert preview["steps"] == [
            {
                "inventory_item_id": item["id"],
                "product_name": "Cream",
                "unit": "dl",
                "action": "use_partial",
                "quantity_consumed": 2.5,
            }
        ]


class TestUndoingAConsume:
    async def test_the_item_is_as_it_was_before(
        self, client: AsyncClient, cream: dict
    ) -> None:
        """Quantity, status, the opened date and the shortened expiry all go back."""
        item = await _item(client, cream["id"])
        before = _state(await _get(client, item["id"]))
        await _consume(client, item["id"], 2.5)
        opened = await _get(client, item["id"])
        assert opened["expiry_date"] != before["expiry_date"]

        await _undo(client)

        assert _state(await _get(client, item["id"])) == before

    async def test_finishing_an_item_is_undone_too(
        self, client: AsyncClient, cream: dict
    ) -> None:
        item = await _item(client, cream["id"])
        await _consume(client, item["id"], 10)

        await _undo(client)

        back = await _get(client, item["id"])
        assert (back["current_quantity"], back["status"]) == (10.0, "sealed")
        assert back["consumed_at"] is None

    async def test_the_history_forgets_it(
        self, client: AsyncClient, cream: dict
    ) -> None:
        """An undone helping was never eaten, so it must not count as eaten."""
        item = await _item(client, cream["id"])
        await _consume(client, item["id"], 1)

        await _undo(client)

        rows = (await client.get("/api/consumption-log")).json()
        assert rows == []

    async def test_pressing_it_again_steps_further_back(
        self, client: AsyncClient, cream: dict
    ) -> None:
        item = await _item(client, cream["id"])
        for _ in range(3):
            await _consume(client, item["id"], 1)

        await _undo(client)
        assert (await _get(client, item["id"]))["current_quantity"] == 8.0
        await _undo(client)
        await _undo(client)

        assert (await _get(client, item["id"]))["current_quantity"] == 10.0
        assert (await client.get(URL)).json() is None

    async def test_the_newest_change_is_undone_whichever_item_it_was(
        self, client: AsyncClient, cream: dict
    ) -> None:
        first = await _item(client, cream["id"])
        second = await _item(client, cream["id"])
        await _consume(client, first["id"], 1)
        await _consume(client, second["id"], 2)

        await _undo(client)

        assert (await _get(client, first["id"]))["current_quantity"] == 9.0
        assert (await _get(client, second["id"]))["current_quantity"] == 10.0


class TestUndoingEverythingElse:
    async def test_mark_as_gone_comes_back_as_it_was(
        self, client: AsyncClient, cream: dict
    ) -> None:
        item = await _item(client, cream["id"])
        await _consume(client, item["id"], 4)
        before = _state(await _get(client, item["id"]))
        await client.patch(f"/api/inventory/{item['id']}", json={"status": "discarded"})

        await _undo(client)

        assert _state(await _get(client, item["id"])) == before

    async def test_a_cleared_shelf_comes_back_in_one_step(
        self, client: AsyncClient, cream: dict
    ) -> None:
        items = [await _item(client, cream["id"]) for _ in range(3)]
        await client.post(
            "/api/inventory/discard", json={"ids": [i["id"] for i in items]}
        )

        preview = (await client.get(URL)).json()
        undone = await _undo(client)

        assert len(preview["steps"]) == 3
        assert undone == {"undone": 3}
        for item in items:
            assert (await _get(client, item["id"]))["status"] == "sealed"

    async def test_a_correction_above_full_is_undone_with_its_new_full(
        self, client: AsyncClient, cream: dict
    ) -> None:
        item = await _item(client, cream["id"])
        await client.patch(
            f"/api/inventory/{item['id']}", json={"current_quantity": 15}
        )

        await _undo(client)

        back = await _get(client, item["id"])
        assert (back["current_quantity"], back["initial_quantity"]) == (10.0, 10.0)

    async def test_undoing_a_restore_puts_it_back_in_the_bin(
        self, client: AsyncClient, cream: dict
    ) -> None:
        item = await _item(client, cream["id"])
        await client.patch(f"/api/inventory/{item['id']}", json={"status": "discarded"})
        await client.patch(f"/api/inventory/{item['id']}", json={"status": "opened"})

        await _undo(client)

        assert (await _get(client, item["id"]))["status"] == "discarded"


class TestSomeoneElseGotThereFirst:
    async def test_a_stale_undo_is_refused_and_changes_nothing(
        self, client: AsyncClient, cream: dict
    ) -> None:
        """The iPad showed "Undo: -1 Cream", then the Telegram bot consumed something."""
        item = await _item(client, cream["id"])
        await _consume(client, item["id"], 1)
        shown = (await client.get(URL)).json()
        await _consume(client, item["id"], 2)

        response = await client.post(URL, json={"batch_id": shown["batch_id"]})

        assert response.status_code == 409
        assert (await _get(client, item["id"]))["current_quantity"] == 7.0

    async def test_a_deleted_item_takes_its_undo_with_it(
        self, client: AsyncClient, cream: dict
    ) -> None:
        kept = await _item(client, cream["id"])
        deleted = await _item(client, cream["id"])
        await _consume(client, kept["id"], 1)
        await _consume(client, deleted["id"], 1)
        await client.delete(f"/api/inventory/{deleted['id']}")

        await _undo(client)

        assert (await _get(client, kept["id"]))["current_quantity"] == 10.0


async def test_every_row_knows_its_batch(
    client: AsyncClient, seeded_db: AsyncSession, cream: dict
) -> None:
    """A bulk clear shares one batch; separate taps do not."""
    items = [await _item(client, cream["id"]) for _ in range(2)]
    await _consume(client, items[0]["id"], 1)
    await client.post("/api/inventory/discard", json={"ids": [i["id"] for i in items]})

    rows = (await seeded_db.execute(select(ConsumptionLog))).scalars().all()
    batches = {str(row.batch_id) for row in rows if row.action == "discard"}
    assert len(batches) == 1
    assert all(row.previous is not None for row in rows)
