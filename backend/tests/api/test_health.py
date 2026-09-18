"""Liveness and readiness (H03).

`/api/health` used to return `{"status": "ok"}` from a function with no
dependencies, so it could not fail while the process was alive and the runbook's
"both return healthy" proved nothing.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestLiveness:
    """Deliberately cheap: this is what the container healthcheck polls, so a
    database that is slow to start must never restart the API."""

    async def test_liveness_needs_nothing(self, client: AsyncClient) -> None:
        response = await client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadiness:
    async def test_everything_up_is_ok(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        with patch(
            "app.services.broadcast_helpers.get_redis_client", new_callable=AsyncMock
        ) as redis:
            redis.return_value.ping = AsyncMock()
            response = await client.get("/api/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["postgres"] == "ok"
        assert body["redis"] == "ok"

    async def test_redis_down_is_a_503(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        with patch(
            "app.services.broadcast_helpers.get_redis_client",
            new_callable=AsyncMock,
            side_effect=ConnectionError("no route to host"),
        ):
            response = await client.get("/api/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["redis"] == "unavailable"
        assert body["postgres"] == "ok"

    async def test_postgres_down_is_a_503(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """The session exists but the server went away mid-query."""
        with (
            patch(
                "app.api.endpoints.health._check_postgres",
                new_callable=AsyncMock,
                side_effect=ConnectionError("server closed the connection"),
            ),
            patch(
                "app.services.broadcast_helpers.get_redis_client",
                new_callable=AsyncMock,
            ) as redis,
        ):
            redis.return_value.ping = AsyncMock()
            response = await client.get("/api/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["postgres"] == "unavailable"

    async def test_a_hanging_dependency_does_not_hang_the_request(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """The budget is what makes this safe to poll from a dashboard."""
        import asyncio

        async def never_answers():
            await asyncio.sleep(3600)

        with (
            patch("app.api.endpoints.health.READINESS_TIMEOUT_SECONDS", 0.01),
            patch(
                "app.services.broadcast_helpers.get_redis_client",
                new_callable=AsyncMock,
            ) as redis,
        ):
            redis.return_value.ping = never_answers
            response = await client.get("/api/health")

        assert response.status_code == 503
        assert response.json()["redis"] == "unavailable"


class TestRoot:
    async def test_root_endpoint_returns_welcome_message(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Kyokki" in data["message"]
