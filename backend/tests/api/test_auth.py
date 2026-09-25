"""Agent access tokens on /api (AG1).

With ``KYOKKI_API_TOKENS`` empty the API is open (the autouse fixture in conftest
empties it for every test); these tests configure tokens themselves.
"""

import logging
from collections.abc import AsyncGenerator

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.api.auth import require_token
from app.core.api_tokens import hash_secret
from app.core.config import settings

READ_SECRET = "read-secret-value-0123456789"
WRITE_SECRET = "write-secret-value-9876543210"
TOKENS = [
    f"dashboard:read:{hash_secret(READ_SECRET)}",
    f"hermes:write:{hash_secret(WRITE_SECRET)}",
]


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
def tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "KYOKKI_API_TOKENS", TOKENS)


def _probe_app() -> FastAPI:
    """A minimal app wired like main.py, so write success needs no database."""
    router = APIRouter()

    @router.api_route("/probe", methods=["GET", "HEAD"])
    async def probe_get(request: Request) -> dict:
        return {"client": request.state.api_client}

    @router.post("/probe")
    async def probe_post(request: Request) -> dict:
        return {"client": request.state.api_client}

    @router.delete("/probe")
    async def probe_delete() -> dict:
        return {}

    @router.websocket("/probe-ws")
    async def probe_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(str(websocket.state.api_client))
        await websocket.close()

    probe = FastAPI()
    probe.include_router(router, prefix="/api", dependencies=[Depends(require_token)])
    return probe


@pytest.fixture
async def probe() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=_probe_app()), base_url="http://test"
    ) as ac:
        yield ac


class TestNoTokensConfigured:
    async def test_everything_is_open(self, probe: AsyncClient) -> None:
        assert (await probe.get("/api/probe")).json() == {"client": None}
        assert (await probe.post("/api/probe")).status_code == 200

    async def test_a_presented_token_is_ignored(self, probe: AsyncClient) -> None:
        response = await probe.post("/api/probe", headers=bearer("anything"))
        assert response.status_code == 200

    async def test_whoami_reports_auth_disabled(self, client: AsyncClient) -> None:
        response = await client.get("/api/whoami")
        assert response.status_code == 200
        assert response.json() == {"name": None, "scopes": [], "auth_enabled": False}


@pytest.mark.usefixtures("tokens")
class TestTokensConfigured:
    async def test_missing_token_is_401(self, probe: AsyncClient) -> None:
        response = await probe.get("/api/probe")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["detail"]["code"] == "auth"
        assert response.json()["detail"]["message"]

    async def test_unknown_token_is_401(self, probe: AsyncClient) -> None:
        response = await probe.get("/api/probe", headers=bearer("nope"))
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "auth"

    @pytest.mark.parametrize(
        "header", ["Basic abc", "Bearer", "Bearer ", WRITE_SECRET, "Token x"]
    )
    async def test_malformed_header_is_401(
        self, probe: AsyncClient, header: str
    ) -> None:
        response = await probe.get("/api/probe", headers={"Authorization": header})
        assert response.status_code == 401

    async def test_scheme_is_case_insensitive(self, probe: AsyncClient) -> None:
        response = await probe.get(
            "/api/probe", headers={"Authorization": f"bearer {READ_SECRET}"}
        )
        assert response.status_code == 200

    async def test_query_token_is_not_accepted_over_http(
        self, probe: AsyncClient
    ) -> None:
        response = await probe.get(f"/api/probe?token={READ_SECRET}")
        assert response.status_code == 401

    async def test_read_token_can_read(self, probe: AsyncClient) -> None:
        response = await probe.get("/api/probe", headers=bearer(READ_SECRET))
        assert response.status_code == 200
        assert response.json() == {"client": "dashboard"}

    async def test_read_token_can_head(self, probe: AsyncClient) -> None:
        response = await probe.head("/api/probe", headers=bearer(READ_SECRET))
        assert response.status_code == 200

    async def test_head_without_a_token_is_401(self, probe: AsyncClient) -> None:
        assert (await probe.head("/api/probe")).status_code == 401

    @pytest.mark.parametrize("method", ["POST", "DELETE"])
    async def test_read_token_cannot_write(
        self, probe: AsyncClient, method: str
    ) -> None:
        response = await probe.request(
            method, "/api/probe", headers=bearer(READ_SECRET)
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "auth"

    async def test_write_token_can_write(self, probe: AsyncClient) -> None:
        response = await probe.post("/api/probe", headers=bearer(WRITE_SECRET))
        assert response.status_code == 200
        assert response.json() == {"client": "hermes"}

    async def test_write_token_can_read(self, probe: AsyncClient) -> None:
        response = await probe.get("/api/probe", headers=bearer(WRITE_SECRET))
        assert response.status_code == 200

    async def test_tokens_are_read_per_request(
        self, probe: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert (await probe.get("/api/probe")).status_code == 401
        monkeypatch.setattr(settings, "KYOKKI_API_TOKENS", [])
        assert (await probe.get("/api/probe")).status_code == 200


@pytest.mark.usefixtures("tokens")
class TestRealApp:
    async def test_existing_routes_need_a_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/categories")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "auth"

    async def test_read_token_cannot_post_to_a_real_route(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/categories", json={}, headers=bearer(READ_SECRET)
        )
        assert response.status_code == 403

    async def test_write_token_creates_a_category(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/categories",
            json={
                "id": "ag1-spices",
                "display_name": "Spices",
                "default_shelf_life_days": 180,
                "sort_order": 130,
            },
            headers=bearer(WRITE_SECRET),
        )
        assert response.status_code == 201

    async def test_whoami_names_the_caller(self, client: AsyncClient) -> None:
        response = await client.get("/api/whoami", headers=bearer(WRITE_SECRET))
        assert response.status_code == 200
        assert response.json() == {
            "name": "hermes",
            "scopes": ["read", "write"],
            "auth_enabled": True,
        }

    async def test_whoami_for_a_read_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/whoami", headers=bearer(READ_SECRET))
        assert response.json() == {
            "name": "dashboard",
            "scopes": ["read"],
            "auth_enabled": True,
        }

    async def test_whoami_needs_a_token(self, client: AsyncClient) -> None:
        assert (await client.get("/api/whoami")).status_code == 401

    async def test_liveness_stays_open(self, client: AsyncClient) -> None:
        """The container healthcheck polls /api/health/live without a token."""
        response = await client.get("/api/health/live")
        assert response.status_code == 200

    async def test_readiness_is_not_rejected(self, client: AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code not in (401, 403)

    async def test_root_stays_open(self, client: AsyncClient) -> None:
        assert (await client.get("/")).status_code == 200

    async def test_cors_preflight_needs_no_token(self, client: AsyncClient) -> None:
        response = await client.options(
            "/api/categories",
            headers={
                "Origin": settings.ALLOWED_ORIGINS[0],
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


@pytest.mark.usefixtures("tokens")
class TestWebSocket:
    def test_rejected_without_a_token(self) -> None:
        with (
            TestClient(_probe_app()) as tc,
            pytest.raises(WebSocketDisconnect) as exc,
            tc.websocket_connect("/api/probe-ws") as ws,
        ):
            ws.receive_text()
        assert exc.value.code == 1008

    def test_accepts_a_query_token(self) -> None:
        with (
            TestClient(_probe_app()) as tc,
            tc.websocket_connect(f"/api/probe-ws?token={READ_SECRET}") as ws,
        ):
            assert ws.receive_text() == "dashboard"

    def test_accepts_the_header(self) -> None:
        with (
            TestClient(_probe_app()) as tc,
            tc.websocket_connect("/api/probe-ws", headers=bearer(WRITE_SECRET)) as ws,
        ):
            assert ws.receive_text() == "hermes"


@pytest.mark.usefixtures("tokens")
class TestLogging:
    async def test_rejection_is_logged_without_the_secret(
        self, probe: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        await probe.get("/api/probe", headers=bearer("wrong-secret-xyz"))
        await probe.post("/api/probe", headers=bearer(READ_SECRET))

        rejections = [
            r for r in caplog.records if r.getMessage() == "api_auth_rejected"
        ]
        assert len(rejections) == 2
        assert rejections[0].__dict__["path"] == "/api/probe"
        assert rejections[0].__dict__["token_name"] is None
        assert rejections[1].__dict__["token_name"] == "dashboard"
        self._assert_no_secret(caplog, "wrong-secret-xyz")

    async def test_success_logs_no_secret(
        self, probe: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        await probe.post("/api/probe", headers=bearer(WRITE_SECRET))
        await probe.get("/api/probe", headers=bearer(READ_SECRET))
        self._assert_no_secret(caplog)

    def test_websocket_rejection_logs_no_secret(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        with (
            TestClient(_probe_app()) as tc,
            pytest.raises(WebSocketDisconnect),
            tc.websocket_connect("/api/probe-ws?token=wrong-ws-secret") as ws,
        ):
            ws.receive_text()
        self._assert_no_secret(caplog, "wrong-ws-secret")

    @staticmethod
    def _assert_no_secret(caplog: pytest.LogCaptureFixture, *extra: str) -> None:
        forbidden = [READ_SECRET, WRITE_SECRET, *extra]
        forbidden += [hash_secret(s) for s in forbidden]
        for record in caplog.records:
            rendered = f"{record.getMessage()} {record.__dict__}"
            for value in forbidden:
                assert value not in rendered
