"""API endpoint for reading the consumption history back (H46)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import consumption_log as crud_consumption_log
from app.db.session import get_db
from app.schemas.consumption_log import (
    ActionSummary,
    CategoryWaste,
    ConsumptionAction,
    ConsumptionLogResponse,
    WasteStats,
    WasteTrend,
    WasteWeek,
)
from app.services import waste_stats

router = APIRouter()


@router.get("", response_model=list[ConsumptionLogResponse])
async def list_consumption_log(
    action: list[ConsumptionAction] | None = Query(None),
    product_master_id: UUID | None = None,
    inventory_item_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ConsumptionLogResponse]:
    """Get a page of the consumption history, newest first.

    Waste is `?action=discard`. Deleting an item deletes its history with it, so this is what
    happened to the food that is still on record, not a ledger that can never lose a row.

    Args:
        action: Only these kinds of event; repeat the parameter for several. Unknown values
            are rejected (422).
        product_master_id: Only this product's events, across all its items.
        inventory_item_id: Only this item's events.
        since: Only events logged at or after this moment.
        until: Only events logged before this moment.
        limit: Page size, 1-200.
        offset: How many of the newest events to skip.
        db: Database session.

    Returns:
        Log rows sorted by logged_at (most recent first), each with its product's name and
        the unit its quantities are in.
    """
    logs = await crud_consumption_log.list_consumption_logs(
        db,
        actions=action,
        product_master_id=product_master_id,
        inventory_item_id=inventory_item_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return [ConsumptionLogResponse.model_validate(log) for log in logs]


@router.get("/summary", response_model=dict[str, ActionSummary])
async def summarise_consumption_log(
    since: datetime | None = None,
    until: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, ActionSummary]:
    """What happened in a window, per action: how many times, and how much of each unit.

    The Gone screen's header ("Thrown away 8 · 1.4 kg, 6 pcs") over a window the list would
    need several pages to cover, and the seam the later metrics work reads.

    Args:
        since: Only events logged at or after this moment.
        until: Only events logged before this moment.
        db: Database session.

    Returns:
        A mapping of action to its counts; actions with nothing in the window are absent.
    """
    summary = await crud_consumption_log.summarise_consumption(
        db, since=since, until=until
    )
    return {action: ActionSummary(**counts) for action, counts in summary.items()}


@router.get("/waste", response_model=WasteStats)
async def waste_rate(
    since: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> WasteStats:
    """ "You threw away X of Y things (Z %)", for a window, plus where it is worst.

    Counted by events (items), not amounts - grams and pieces do not add up. A discard a later
    restore undid is not waste; corrections, part-uses and restores never enter this count,
    exactly as the Gone list leaves them out (planner ruling, 2026-10-02).

    Args:
        since: Only events logged at or after this moment; omitted means every event on record.
        db: Database session.

    Returns:
        The window's discarded/finished counts and rate, plus every category with at least 3
        events, worst waste rate first.
    """
    figures = await waste_stats.waste_figures(db, since=since)
    return WasteStats(
        discarded=figures.discarded,
        finished=figures.finished,
        total=figures.total,
        rate=figures.rate,
        categories=[
            CategoryWaste(
                category=category.category,
                display_name=category.display_name,
                discarded=category.discarded,
                finished=category.finished,
                total=category.total,
                rate=category.rate,
            )
            for category in figures.categories
        ],
    )


@router.get("/waste/trend", response_model=WasteTrend)
async def waste_trend(
    weeks: int = Query(waste_stats.TREND_WEEKS, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
) -> WasteTrend:
    """The waste rate and counts per ISO week for the last `weeks` weeks, oldest first.

    Weeks are Europe/Helsinki (the app's timezone), Monday start. The window filter on
    `GET .../waste` does not apply here - the trend always looks back from today.

    Args:
        weeks: How many ISO weeks to return, most recent included. Defaults to 8.
        db: Database session.

    Returns:
        One entry per week, oldest first; weeks with nothing logged still appear, at 0 %.
    """
    figures = await waste_stats.trend_figures(db, weeks=weeks)
    return WasteTrend(
        weeks=[
            WasteWeek(
                week_start=week.week_start,
                discarded=week.discarded,
                finished=week.finished,
                total=week.total,
                rate=week.rate,
            )
            for week in figures
        ]
    )
