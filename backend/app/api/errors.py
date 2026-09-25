"""Stable, machine-readable errors for the agent-facing routes (AG2).

An agent branches on ``detail.code``; ``message`` is for a person reading the log. Raised as
an ordinary ``HTTPException``, so the response is ``{"detail": {"code": ..., ...}}`` with no
app-level handler. Pydantic's 422s are left exactly as FastAPI writes them.
"""

from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException, status

AgentErrorCode = Literal[
    "not_found", "ambiguous", "insufficient_stock", "invalid", "conflict"
]

STATUS_FOR: dict[str, int] = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "ambiguous": status.HTTP_409_CONFLICT,
    "insufficient_stock": status.HTTP_409_CONFLICT,
    "invalid": status.HTTP_400_BAD_REQUEST,
    "conflict": status.HTTP_409_CONFLICT,
}


def _json(value: Any) -> Any:
    """Decimals as JSON numbers (DEC-2), everything else as given."""
    if isinstance(value, Decimal):
        return float(value)
    return value


class AgentError(HTTPException):
    """An HTTP error whose ``detail`` is ``{code, message, candidates?, hint?, ...}``."""

    def __init__(
        self,
        code: AgentErrorCode,
        message: str,
        *,
        candidates: list[dict[str, Any]] | None = None,
        hint: str | None = None,
        **extra: Any,
    ) -> None:
        detail: dict[str, Any] = {"code": code, "message": message}
        if candidates is not None:
            detail["candidates"] = candidates
        if hint is not None:
            detail["hint"] = hint
        detail.update({key: _json(value) for key, value in extra.items()})
        super().__init__(status_code=STATUS_FOR[code], detail=detail)
        self.code = code
