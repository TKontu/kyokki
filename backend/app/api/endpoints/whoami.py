"""``GET /api/whoami``: which API token the caller presented (AG1).

Included from ``main.py`` with the same ``require_token`` dependency as the rest
of /api, which has already put the caller on ``request.state``.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.auth import configured_tokens

router = APIRouter()


class WhoAmIResponse(BaseModel):
    name: str | None
    scopes: list[str]
    auth_enabled: bool


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(request: Request) -> WhoAmIResponse:
    return WhoAmIResponse(
        name=request.state.api_client,
        scopes=list(request.state.api_scopes),
        auth_enabled=bool(configured_tokens()),
    )
