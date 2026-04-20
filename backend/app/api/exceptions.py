"""Reusable exception handlers for API endpoints."""

from contextlib import asynccontextmanager

import asyncpg
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError


@asynccontextmanager
async def handle_integrity_errors():
    """Async context manager that converts SQLAlchemy IntegrityErrors to HTTPExceptions.

    Maps asyncpg-typed constraint violations to appropriate HTTP status codes,
    independent of PostgreSQL locale or constraint naming.

    Usage:
        async with handle_integrity_errors():
            return await crud.create(db, data)
    """
    try:
        yield
    except IntegrityError as e:
        orig = e.orig
        if isinstance(orig, asyncpg.exceptions.ForeignKeyViolationError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Referenced record does not exist. {orig.detail}",
            ) from e
        if isinstance(orig, asyncpg.exceptions.UniqueViolationError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Record already exists. {orig.detail}",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint violation.",
        ) from e
