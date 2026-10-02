"""Waste rate and trend on the Gone screen (planner ruling, 2026-10-02).

GET /api/consumption-log/waste and /waste/trend. Built on the same history as
test_consumption_log.py; this file owns the waste-stats endpoints specifically.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_log import ConsumptionLog

HELSINKI = ZoneInfo("Europe/Helsinki")

URL = "/api/consumption-log/waste"


async def _product(
    client: AsyncClient, name: str, *, category: str = "dairy", unit: str = "dl"
) -> dict:
    response = await client.post(
        "/api/products",
        json={
            "canonical_name": name,
            "category": category,
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume" if unit == "dl" else "weight",
            "default_unit": unit,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _item(client: AsyncClient, product_id: str, unit: str = "dl") -> dict:
    response = await client.post(
        "/api/inventory",
        json={
            "product_master_id": product_id,
            "initial_quantity": 10,
            "current_quantity": 10,
            "unit": unit,
            "expiry_date": "2099-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _consume(client: AsyncClient, item_id: str, quantity: float = 10) -> None:
    response = await client.post(
        f"/api/inventory/{item_id}/consume", json={"quantity": quantity}
    )
    assert response.status_code == 200, response.text


async def _discard(client: AsyncClient, item_id: str) -> None:
    response = await client.patch(
        f"/api/inventory/{item_id}", json={"status": "discarded"}
    )
    assert response.status_code == 200, response.text


async def _restore(client: AsyncClient, item_id: str) -> None:
    response = await client.post("/api/inventory/restore", json={"ids": [item_id]})
    assert response.status_code == 200, response.text


async def _set_logged_at(
    db: AsyncSession, inventory_item_id: str, action: str, logged_at: datetime
) -> None:
    """Back-date the row the client's event just wrote, for trend and `since` tests."""
    await db.execute(
        update(ConsumptionLog)
        .where(
            ConsumptionLog.inventory_item_id == UUID(inventory_item_id),
            ConsumptionLog.action == action,
        )
        .values(logged_at=logged_at)
    )
    await db.commit()


class TestTheWasteRate:
    async def test_it_counts_events_not_amounts(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Milk")
        eaten = await _item(client, product["id"])
        binned_a = await _item(client, product["id"])
        binned_b = await _item(client, product["id"])
        await _consume(client, eaten["id"])
        await _discard(client, binned_a["id"])
        await _discard(client, binned_b["id"])

        stats = (await client.get(URL)).json()

        assert (stats["discarded"], stats["finished"], stats["total"]) == (2, 1, 3)
        assert stats["rate"] == pytest.approx(2 / 3)

    async def test_corrections_part_uses_and_restores_are_excluded(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Milk")
        partial = await _item(client, product["id"])
        corrected = await _item(client, product["id"])
        discarded = await _item(client, product["id"])
        await _consume(client, partial["id"], 3)  # use_partial, not "gone"
        await client.patch(
            f"/api/inventory/{corrected['id']}", json={"current_quantity": 5}
        )  # correct
        await _discard(client, discarded["id"])

        stats = (await client.get(URL)).json()

        assert (stats["discarded"], stats["finished"], stats["total"]) == (1, 0, 1)

    async def test_a_restored_discard_is_not_waste(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Milk")
        item = await _item(client, product["id"])
        await _discard(client, item["id"])

        await _restore(client, item["id"])

        stats = (await client.get(URL)).json()

        assert (stats["discarded"], stats["finished"], stats["total"]) == (0, 0, 0)
        assert stats["rate"] is None

    async def test_since_bounds_the_window(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Milk")
        old_item = await _item(client, product["id"])
        new_item = await _item(client, product["id"])
        await _discard(client, old_item["id"])
        await _discard(client, new_item["id"])
        now = datetime.now(UTC)
        await _set_logged_at(
            seeded_db, old_item["id"], "discard", now - timedelta(days=5)
        )
        await _set_logged_at(seeded_db, new_item["id"], "discard", now)

        stats = (
            await client.get(
                URL, params={"since": (now - timedelta(hours=1)).isoformat()}
            )
        ).json()

        assert stats["discarded"] == 1

    async def test_an_empty_history_has_no_rate(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        stats = (await client.get(URL)).json()

        assert stats == {
            "discarded": 0,
            "finished": 0,
            "total": 0,
            "rate": None,
            "categories": [],
        }


class TestCategoryBreakdown:
    async def test_a_category_needs_three_events_to_appear(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        dairy = await _product(client, "Milk", category="dairy")
        meat = await _product(client, "Mince", category="meat")
        for _ in range(2):
            item = await _item(client, dairy["id"])
            await _discard(client, item["id"])
        lone = await _item(client, meat["id"])
        await _discard(client, lone["id"])

        stats = (await client.get(URL)).json()

        assert stats["categories"] == []

    async def test_the_worst_category_comes_first(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        dairy = await _product(client, "Milk", category="dairy")
        meat = await _product(client, "Mince", category="meat")
        item = await _item(client, dairy["id"])
        await _discard(client, item["id"])
        for _ in range(2):
            item = await _item(client, dairy["id"])
            await _consume(client, item["id"])
        for _ in range(3):
            item = await _item(client, meat["id"])
            await _discard(client, item["id"])

        stats = (await client.get(URL)).json()

        assert [c["category"] for c in stats["categories"]] == ["meat", "dairy"]
        assert stats["categories"][0]["rate"] == 1.0
        assert stats["categories"][0]["display_name"] == "Meat & Poultry"


class TestTheTrend:
    URL = f"{URL}/trend"

    async def test_it_returns_eight_weeks_oldest_first(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(self.URL)

        assert response.status_code == 200
        weeks = response.json()["weeks"]
        assert len(weeks) == 8
        starts = [w["week_start"] for w in weeks]
        assert starts == sorted(starts)

    async def test_a_fresh_event_shows_up_in_this_weeks_bar(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Milk")
        item = await _item(client, product["id"])
        await _discard(client, item["id"])

        weeks = (await client.get(self.URL)).json()["weeks"]

        assert weeks[-1]["discarded"] == 1
        assert weeks[-1]["rate"] == 1.0

    async def test_a_restored_discard_is_excluded_from_the_trend(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(client, "Milk")
        item = await _item(client, product["id"])
        await _discard(client, item["id"])
        await _restore(client, item["id"])

        weeks = (await client.get(self.URL)).json()["weeks"]

        assert all(w["discarded"] == 0 for w in weeks)

    async def test_an_event_lands_in_its_own_iso_week_in_helsinki_time(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """A Sunday 23:30 Europe/Helsinki event belongs to the week ending that Sunday, not
        the week after - proved here through the endpoint (the SQL itself is pinned against a
        fixed, DST-exercising date in tests/services/test_waste_stats.py; this picks a recent
        Sunday so the event always falls inside the real 8-week trend the endpoint computes
        from the actual clock).
        """
        now_local = datetime.now(HELSINKI)
        days_since_sunday = (now_local.weekday() + 1) % 7
        # A full week further back, so it is never "this week" by construction.
        target_sunday = now_local.date() - timedelta(days=days_since_sunday + 7)
        sunday_2330_utc = datetime(
            target_sunday.year,
            target_sunday.month,
            target_sunday.day,
            23,
            30,
            tzinfo=HELSINKI,
        ).astimezone(UTC)
        week_start = target_sunday - timedelta(
            days=6
        )  # the Monday that started that week

        product = await _product(client, "Milk")
        item = await _item(client, product["id"])
        await _discard(client, item["id"])
        await _set_logged_at(seeded_db, item["id"], "discard", sunday_2330_utc)

        weeks = (await client.get(self.URL)).json()["weeks"]

        hit = [w for w in weeks if w["discarded"] == 1]
        assert len(hit) == 1
        assert hit[0]["week_start"] == week_start.isoformat()
