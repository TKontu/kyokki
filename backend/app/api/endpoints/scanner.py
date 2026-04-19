"""Scanner API endpoints — barcode scanning, mode management, station monitoring."""

import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import scanner_service
from app.services.off_service import OffApiError, OffProductNotFoundError

router = APIRouter()

VALID_MODES = {"add", "consume", "lookup"}

# Allowed station_id characters: alphanumeric, hyphens, underscores, max 64 chars
_STATION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _validate_station_id(v: str | None) -> str | None:
    if v is not None and not _STATION_ID_RE.match(v):
        raise ValueError(
            "station_id must be 1–64 alphanumeric characters, hyphens, or underscores"
        )
    return v


# --- Schemas ---


class ScanRequest(BaseModel):
    barcode: str
    mode: str | None = None
    station_id: str | None = None
    quantity: Decimal = Decimal("1")

    @field_validator("station_id")
    @classmethod
    def validate_station_id(cls, v: str | None) -> str | None:
        return _validate_station_id(v)


class ScanResponse(BaseModel):
    success: bool
    action: str
    product: dict | None
    inventory_item: dict | None
    message: str


class SetModeRequest(BaseModel):
    mode: str
    station_id: str | None = None

    @field_validator("station_id")
    @classmethod
    def validate_station_id(cls, v: str | None) -> str | None:
        return _validate_station_id(v)


class ModeResponse(BaseModel):
    mode: str
    station_id: str | None
    is_global: bool


class SetModeResponse(BaseModel):
    success: bool
    mode: str
    station_id: str | None
    message: str


class StationInfo(BaseModel):
    station_id: str
    mode: str
    last_scan: str | None
    scan_count: int
    online: bool


class StationsResponse(BaseModel):
    stations: list[StationInfo]
    total_stations: int
    online_stations: int


# --- Endpoints ---


@router.post("/scan")
async def scan_barcode(
    request: ScanRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Process a scanned barcode.

    Resolves the effective mode (request > station Redis > global Redis > 'add'),
    then performs the action and broadcasts via WebSocket.
    """
    if not request.barcode.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Barcode cannot be empty"
        )

    # Resolve mode: explicit request overrides Redis
    if request.mode and request.mode in VALID_MODES:
        mode = request.mode
    elif request.mode and request.mode not in VALID_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode '{request.mode}'. Must be one of: {', '.join(sorted(VALID_MODES))}",
        )
    else:
        mode, _ = await scanner_service.get_mode(request.station_id)

    try:
        result = await scanner_service.process_scan(
            db=db,
            barcode=request.barcode.strip(),
            mode=mode,
            station_id=request.station_id,
            quantity=request.quantity,
        )
    except OffProductNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with barcode '{request.barcode}' not found",
        ) from e
    except OffApiError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Open Food Facts API unavailable",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    response.status_code = (
        status.HTTP_201_CREATED
        if result["action"] == "product_created_and_added"
        else status.HTTP_200_OK
    )
    return ScanResponse(**result)


@router.get("/mode", response_model=ModeResponse)
async def get_scanner_mode(
    station_id: str | None = Query(None, description="Station ID for per-station mode"),
) -> ModeResponse:
    """Get the current scanning mode (per-station or global)."""
    mode, is_global = await scanner_service.get_mode(station_id)
    return ModeResponse(mode=mode, station_id=station_id, is_global=is_global)


@router.post("/mode", response_model=SetModeResponse)
async def set_scanner_mode(request: SetModeRequest) -> SetModeResponse:
    """Set the scanning mode globally or for a specific station."""
    if request.mode not in VALID_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode '{request.mode}'. Must be one of: {', '.join(sorted(VALID_MODES))}",
        )

    await scanner_service.set_mode(request.mode, request.station_id)

    scope = f"station '{request.station_id}'" if request.station_id else "global"
    return SetModeResponse(
        success=True,
        mode=request.mode,
        station_id=request.station_id,
        message=f"Scanner mode set to '{request.mode}' for {scope}",
    )


@router.get("/stations", response_model=StationsResponse)
async def list_stations() -> StationsResponse:
    """List all active scanning stations and their current state."""
    stations = await scanner_service.get_all_stations()
    station_list = [StationInfo(**s) for s in stations]
    return StationsResponse(
        stations=station_list,
        total_stations=len(station_list),
        online_stations=sum(1 for s in station_list if s.online),
    )
