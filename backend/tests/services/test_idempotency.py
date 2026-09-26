"""AG2: `Idempotency-Key` storage - a retry replays, it does not re-run."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_key import IdempotencyKey
from app.services import idempotency
from app.services.idempotency import IdempotencyClaim, IdempotencyConflict

ROUTE = "POST /api/stock/consume"


def _claim(key: str = "k-1", body: object = None) -> IdempotencyClaim:
    return idempotency.claim_for(key, ROUTE, body if body is not None else {"a": 1})


class TestTheHash:
    def test_key_order_does_not_matter(self) -> None:
        assert idempotency.request_hash({"a": 1, "b": [1, 2]}) == (
            idempotency.request_hash({"b": [1, 2], "a": 1})
        )

    def test_a_different_body_is_a_different_hash(self) -> None:
        assert idempotency.request_hash({"a": 1}) != idempotency.request_hash({"a": 2})

    def test_it_is_sha256_hex(self) -> None:
        digest = idempotency.request_hash({})
        assert len(digest) == 64
        int(digest, 16)

    def test_no_key_no_claim(self) -> None:
        assert idempotency.claim_for(None, ROUTE, {}) is None
        assert idempotency.claim_for("", ROUTE, {}) is None


class TestReplay:
    async def test_nothing_stored_is_nothing_to_replay(
        self, db_session: AsyncSession
    ) -> None:
        assert await idempotency.replay(db_session, _claim()) is None

    async def test_the_same_body_replays_the_stored_response(
        self, db_session: AsyncSession
    ) -> None:
        await idempotency.remember(db_session, _claim(), 201, {"ok": True})
        await db_session.commit()

        stored = await idempotency.replay(db_session, _claim())

        assert stored is not None
        assert (stored.status_code, stored.body) == (201, {"ok": True})

    async def test_a_different_body_is_a_conflict(
        self, db_session: AsyncSession
    ) -> None:
        await idempotency.remember(db_session, _claim(), 200, {"ok": True})
        await db_session.commit()

        with pytest.raises(IdempotencyConflict):
            await idempotency.replay(db_session, _claim(body={"a": 2}))

    async def test_the_same_key_on_another_route_is_separate(
        self, db_session: AsyncSession
    ) -> None:
        await idempotency.remember(db_session, _claim(), 200, {"ok": True})
        await db_session.commit()

        other = idempotency.claim_for("k-1", "POST /api/stock/add", {"a": 2})

        assert await idempotency.replay(db_session, other) is None

    async def test_older_than_a_day_is_new_and_overwritten(
        self, db_session: AsyncSession
    ) -> None:
        await idempotency.remember(db_session, _claim(), 200, {"first": True})
        await db_session.commit()
        row = (await db_session.execute(select(IdempotencyKey))).scalar_one()
        row.created_at = datetime.now(UTC) - timedelta(hours=25)  # type: ignore[assignment]
        await db_session.commit()

        fresh = _claim(body={"a": 2})
        assert await idempotency.replay(db_session, fresh) is None
        await idempotency.remember(db_session, fresh, 201, {"second": True})
        await db_session.commit()

        stored = await idempotency.replay(db_session, fresh)
        assert stored is not None
        assert stored.body == {"second": True}
        count = await db_session.execute(
            select(func.count()).select_from(IdempotencyKey)
        )
        assert count.scalar_one() == 1
