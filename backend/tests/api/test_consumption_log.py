"""H46: the consumption history, read back through GET /api/consumption-log."""

from datetime import date, timedelta
from urllib.parse import quote
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

URL = "/api/consumption-log"


async def _product(
    client: AsyncClient, name: str, unit: str = "dl", unit_type: str = "volume"
) -> dict:
    response = await client.post(
        "/api/products",
        json={
            "canonical_name": name,
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": unit_type,
            "default_unit": unit,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _item(
    client: AsyncClient, product_id: str, quantity: int = 10, unit: str = "dl"
) -> dict:
    response = await client.post(
        "/api/inventory",
        json={
            "product_master_id": product_id,
            "initial_quantity": quantity,
            "current_quantity": quantity,
            "unit": unit,
            "expiry_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _consume(client: AsyncClient, item_id: str, quantity: float) -> None:
    response = await client.post(
        f"/api/inventory/{item_id}/consume", json={"quantity": quantity}
    )
    assert response.status_code == 200, response.text


async def _discard(client: AsyncClient, item_id: str) -> None:
    response = await client.patch(
        f"/api/inventory/{item_id}", json={"status": "discarded"}
    )
    assert response.status_code == 200, response.text


@pytest.fixture
async def milk(client: AsyncClient, seeded_db: AsyncSession) -> dict:
    return await _product(client, "Milk")


@pytest.fixture
async def cream(client: AsyncClient, seeded_db: AsyncSession) -> dict:
    """Measured in grams, so a summary has two units to keep apart."""
    return await _product(client, "Cream", unit="g", unit_type="weight")


class TestReadingTheHistory:
    async def test_nothing_happened_yet(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(URL)

        assert response.status_code == 200
        assert response.json() == []

    async def test_each_row_can_be_read_on_its_own(
        self, client: AsyncClient, milk: dict
    ) -> None:
        item = await _item(client, milk["id"])
        await _consume(client, item["id"], 3)

        (row,) = (await client.get(URL)).json()

        assert row["inventory_item_id"] == item["id"]
        assert row["product_master_id"] == milk["id"]
        assert row["product_name"] == "Milk"
        assert row["unit"] == "dl"
        assert row["action"] == "use_partial"
        assert (row["quantity_consumed"], row["quantity_after"]) == (3.0, 7.0)
        assert row["logged_at"]

    async def test_newest_first(self, client: AsyncClient, milk: dict) -> None:
        item = await _item(client, milk["id"])
        await _consume(client, item["id"], 1)
        await _consume(client, item["id"], 2)
        await _discard(client, item["id"])

        actions = [row["action"] for row in (await client.get(URL)).json()]

        assert actions == ["discard", "use_partial", "use_partial"]

    async def test_waste_is_the_discard_rows(
        self, client: AsyncClient, milk: dict
    ) -> None:
        eaten = await _item(client, milk["id"])
        binned = await _item(client, milk["id"], quantity=4)
        await _consume(client, eaten["id"], 10)
        await _discard(client, binned["id"])

        rows = (await client.get(URL, params={"action": "discard"})).json()

        assert [(r["inventory_item_id"], r["quantity_consumed"]) for r in rows] == [
            (binned["id"], 4.0)
        ]

    async def test_several_actions_at_once(
        self, client: AsyncClient, milk: dict
    ) -> None:
        item = await _item(client, milk["id"])
        await _consume(client, item["id"], 2)
        await _consume(client, item["id"], 8)
        await _discard(client, item["id"])

        rows = (
            await client.get(
                URL, params=[("action", "use_full"), ("action", "use_partial")]
            )
        ).json()

        assert sorted(r["action"] for r in rows) == ["use_full", "use_partial"]

    async def test_by_product_and_by_item(
        self, client: AsyncClient, milk: dict, cream: dict
    ) -> None:
        first = await _item(client, milk["id"])
        second = await _item(client, milk["id"])
        other = await _item(client, cream["id"], unit="g")
        for item in (first, second, other):
            await _consume(client, item["id"], 1)

        by_product = (
            await client.get(URL, params={"product_master_id": milk["id"]})
        ).json()
        by_item = (
            await client.get(URL, params={"inventory_item_id": second["id"]})
        ).json()

        assert sorted(r["inventory_item_id"] for r in by_product) == sorted(
            [first["id"], second["id"]]
        )
        assert [r["inventory_item_id"] for r in by_item] == [second["id"]]

    async def test_since_and_until_bound_the_window(
        self, client: AsyncClient, milk: dict
    ) -> None:
        item = await _item(client, milk["id"])
        for amount in (1, 2, 3):
            await _consume(client, item["id"], amount)
        newest, middle, oldest = (await client.get(URL)).json()

        window = (
            await client.get(
                URL,
                params={"since": middle["logged_at"], "until": newest["logged_at"]},
            )
        ).json()

        # `since` is inclusive and `until` is not, so windows laid end to end never overlap
        assert [r["id"] for r in window] == [middle["id"]]
        assert oldest["id"] not in [r["id"] for r in window]

    async def test_pages_do_not_overlap(self, client: AsyncClient, milk: dict) -> None:
        item = await _item(client, milk["id"])
        for _ in range(5):
            await _consume(client, item["id"], 1)
        everything = [r["id"] for r in (await client.get(URL)).json()]

        first = (await client.get(URL, params={"limit": 2})).json()
        second = (await client.get(URL, params={"limit": 2, "offset": 2})).json()

        assert [r["id"] for r in first + second] == everything[:4]

    async def test_the_record_outlives_the_item(
        self, client: AsyncClient, milk: dict
    ) -> None:
        """Deleting an item used to delete its history; metrics would then miss the waste."""
        item = await _item(client, milk["id"])
        await _consume(client, item["id"], 1)

        await client.delete(f"/api/inventory/{item['id']}")

        (row,) = (await client.get(URL)).json()
        assert row["inventory_item_id"] is None
        assert row["item_status"] is None
        # Detached, and still readable: 1 what?
        assert (row["quantity_consumed"], row["unit"]) == (1.0, "dl")
        assert row["product_name"] == "Milk"


class TestWhetherItCanComeBack:
    async def test_a_row_says_where_its_item_stands_now(
        self, client: AsyncClient, milk: dict
    ) -> None:
        """The Gone screen offers "Put it back" on exactly the rows whose item is in the bin."""
        binned = await _item(client, milk["id"])
        eaten = await _item(client, milk["id"])
        await _discard(client, binned["id"])
        await _consume(client, eaten["id"], 10)

        rows = {
            r["inventory_item_id"]: r["item_status"]
            for r in (await client.get(URL)).json()
        }

        assert rows[binned["id"]] == "discarded"
        assert rows[eaten["id"]] == "empty"

    async def test_it_follows_the_item_back_out_of_the_bin(
        self, client: AsyncClient, milk: dict
    ) -> None:
        item = await _item(client, milk["id"])
        await _discard(client, item["id"])

        await client.post("/api/inventory/restore", json={"ids": [item["id"]]})

        discarded = [
            r for r in (await client.get(URL)).json() if r["action"] == "discard"
        ]
        assert [r["item_status"] for r in discarded] == ["opened"]


class TestTheSummary:
    """The Gone screen's header, and the seam the later metrics work reads."""

    async def test_it_counts_events_and_totals_each_unit(
        self, client: AsyncClient, milk: dict, cream: dict
    ) -> None:
        litres = await _item(client, milk["id"], quantity=10)
        grams = await _item(client, cream["id"], quantity=400, unit="g")
        eaten = await _item(client, milk["id"], quantity=5)
        await _discard(client, litres["id"])
        await _discard(client, grams["id"])
        await _consume(client, eaten["id"], 5)

        summary = (await client.get(f"{URL}/summary")).json()

        assert summary["discard"] == {"events": 2, "totals": {"dl": 10.0, "g": 400.0}}
        assert summary["use_full"] == {"events": 1, "totals": {"dl": 5.0}}

    async def test_it_counts_nothing_before_the_window(
        self, client: AsyncClient, milk: dict
    ) -> None:
        item = await _item(client, milk["id"])
        await _discard(client, item["id"])
        (row,) = (await client.get(URL)).json()

        before = (
            await client.get(f"{URL}/summary", params={"since": row["logged_at"]})
        ).json()
        after = (
            await client.get(f"{URL}/summary", params={"until": row["logged_at"]})
        ).json()

        assert before["discard"]["events"] == 1
        assert after == {}

    async def test_an_empty_history_summarises_to_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        assert (await client.get(f"{URL}/summary")).json() == {}


class TestRefusedAtTheDoor:
    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 201},
            {"offset": -1},
            {"action": "adjust"},
            {"product_master_id": "not-a-uuid"},
            {"since": "yesterday"},
        ],
    )
    async def test_bad_parameters_are_422(
        self, client: AsyncClient, seeded_db: AsyncSession, params: dict
    ) -> None:
        response = await client.get(URL, params=params)

        assert response.status_code == 422

    async def test_an_unknown_item_is_an_empty_history(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(f"{URL}?inventory_item_id={quote(str(uuid4()))}")

        assert response.status_code == 200
        assert response.json() == []
