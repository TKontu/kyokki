"""Reusable exception handlers for API endpoints."""

from collections.abc import Mapping
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger

logger = get_logger(__name__)

# PostgreSQL SQLSTATE codes (class 23, integrity constraint violation). These are
# the discriminator because `IntegrityError.orig` is SQLAlchemy's asyncpg *wrapper*
# (AsyncAdapt_asyncpg_dbapi.IntegrityError), not the asyncpg exception itself - so
# the isinstance checks this module used before never matched, and every violation
# fell through to the generic 400. The wrapper carries `sqlstate`, and the original
# asyncpg error with its DETAIL line is its `__cause__`.
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
NOT_NULL_VIOLATION = "23502"

# How a referencing table is named to the cook. The frontend renders `detail`
# verbatim, so these are user-facing copy, not table names.
REFERENCE_LABELS: dict[str, tuple[str, str]] = {
    "inventory_item": ("inventory item", "inventory items"),
    "store_product_alias": ("receipt name alias", "receipt name aliases"),
    "shopping_list_item": ("shopping list item", "shopping list items"),
    "consumption_log": ("consumption entry", "consumption entries"),
    "product_master": ("product", "products"),
}


def _label(table: str, count: int) -> str:
    singular, plural = REFERENCE_LABELS.get(
        table, (table.replace("_", " "), f"{table.replace('_', ' ')} rows")
    )
    return f"{count} {singular if count == 1 else plural}"


def reference_conflict_detail(counts: Mapping[str, int]) -> str:
    """A sentence naming what still points at the row the caller wants deleted.

    Kept separate from the delete endpoints so both of them, and the tests, agree
    on the wording.
    """
    named = [_label(table, count) for table, count in counts.items() if count]
    if not named:
        return "Cannot delete: something else still refers to this."
    listed = named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"
    return f"Cannot delete: still referenced by {listed}."


@asynccontextmanager
async def handle_integrity_errors():
    """Convert SQLAlchemy IntegrityErrors into HTTPExceptions a caller can act on.

    Maps asyncpg-typed constraint violations to status codes, independent of the
    PostgreSQL locale or constraint naming.

    The raw ``DETAIL`` line is never returned. It quotes the offending row's
    values - a product name, a barcode, an id - and the frontend prints `detail`
    to the cook as-is (`lib/api/client.ts`). It is logged instead.

    Usage:
        async with handle_integrity_errors():
            return await crud.create(db, data)
    """
    try:
        yield
    except IntegrityError as e:
        orig = e.orig
        # The asyncpg exception under SQLAlchemy's wrapper; it carries DETAIL.
        cause = getattr(orig, "__cause__", None)
        sqlstate = getattr(orig, "sqlstate", None) or getattr(cause, "sqlstate", None)
        db_detail = getattr(cause, "detail", None)

        logger.warning(
            "Database constraint violation",
            extra={
                "sqlstate": sqlstate,
                "constraint": getattr(cause, "constraint_name", None),
                "db_detail": db_detail,
            },
        )

        if sqlstate == FOREIGN_KEY_VIOLATION:
            # One SQLSTATE covers both directions. On an insert the row being
            # pointed at is missing; on a delete the row still has children, and
            # only then does PostgreSQL say "is still referenced".
            if db_detail and "is still referenced from table" in db_detail:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot delete: something else still refers to this.",
                ) from e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Referenced record does not exist.",
            ) from e

        if sqlstate == UNIQUE_VIOLATION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Record already exists.",
            ) from e

        if sqlstate == NOT_NULL_VIOLATION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A required field is missing.",
            ) from e

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint violation.",
        ) from e
