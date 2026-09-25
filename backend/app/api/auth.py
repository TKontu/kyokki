"""Bearer-token access control for /api (AG1).

``require_token`` is attached to the whole ``/api`` router in ``main.py``. With no
``KYOKKI_API_TOKENS`` configured it lets everything through (anonymous), so the API
behaves as it always has. With tokens configured:

- ``Authorization: Bearer <secret>`` is required (a WebSocket may send ``?token=``
  instead, since browsers cannot set WebSocket headers);
- ``GET``/``HEAD``/``OPTIONS`` and WebSockets need ``read``, every other method ``write``;
- missing or unknown token -> 401, a read token on a write -> 403, a rejected
  WebSocket is closed with 1008.

The liveness and readiness probes stay open: the container healthcheck polls
``/api/health/live`` and cannot carry a token.

Secrets and their hashes are never logged, returned or put in an exception.
"""

import hmac

from fastapi import HTTPException, WebSocketException, status
from starlette.requests import HTTPConnection

from app.core.api_tokens import ApiToken, Scope, hash_secret, parse_token_entries
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
OPEN_PATHS = frozenset({"/api/health", "/api/health/live"})


def configured_tokens() -> list[ApiToken]:
    """Read per request, so a settings change (or a test's monkeypatch) applies."""
    return parse_token_entries(settings.KYOKKI_API_TOKENS)


def _presented_secret(conn: HTTPConnection, *, websocket: bool) -> str | None:
    header = conn.headers.get("authorization")
    if header:
        scheme, _, value = header.partition(" ")
        value = value.strip()
        if scheme.lower() == "bearer" and value:
            return value
        return None
    if websocket:
        return conn.query_params.get("token") or None
    return None


def _find(tokens: list[ApiToken], secret: str) -> ApiToken | None:
    digest = hash_secret(secret)
    found = None
    # Compare against every entry, so timing does not reveal which one matched.
    for token in tokens:
        if hmac.compare_digest(token.sha256, digest):
            found = token
    return found


def _reject(
    conn: HTTPConnection,
    *,
    websocket: bool,
    status_code: int,
    message: str,
    token_name: str | None,
) -> Exception:
    logger.warning(
        "api_auth_rejected",
        extra={
            "status": status_code,
            "reason": message,
            "token_name": token_name,
            # url.path has no query string, where a WebSocket token would sit
            "path": conn.url.path,
            "method": conn.scope.get("method", "WEBSOCKET"),
        },
    )
    if websocket:
        return WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=message)
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return HTTPException(
        status_code=status_code,
        detail={"code": "auth", "message": message},
        headers=headers,
    )


def require_token(conn: HTTPConnection) -> None:
    """FastAPI dependency: authenticate the caller and record who it is.

    Sets ``conn.state.api_client`` (token name, or None when anonymous) and
    ``conn.state.api_scopes``.
    """
    conn.state.api_client = None
    conn.state.api_scopes = ()
    tokens = configured_tokens()
    if not tokens or conn.url.path in OPEN_PATHS:
        return

    websocket = conn.scope["type"] == "websocket"
    secret = _presented_secret(conn, websocket=websocket)
    token = _find(tokens, secret) if secret else None
    if token is None:
        raise _reject(
            conn,
            websocket=websocket,
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="A valid API token is required",
            token_name=None,
        )

    needed: Scope = (
        "read" if websocket or conn.scope.get("method") in READ_METHODS else "write"
    )
    if not token.allows(needed):
        raise _reject(
            conn,
            websocket=websocket,
            status_code=status.HTTP_403_FORBIDDEN,
            message=f"This token does not have the '{needed}' scope",
            token_name=token.name,
        )

    conn.state.api_client = token.name
    conn.state.api_scopes = token.scopes
