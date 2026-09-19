"""Shared pytest fixtures for all tests."""

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.category import Category
from app.models.product_master import ProductMaster
from tests.support import (
    derive_test_database_url,
    guard_test_database,
    maintenance_url,
)

# Anything reaching one of these needs PostgreSQL.
DB_FIXTURES = frozenset(
    {"db_engine", "db_session", "session_factory", "test_db", "seeded_db"}
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply ``requires_db`` from fixture use.

    The marker was declared in pytest.ini but written on a single test, so
    deselecting it deselected nothing while ~380 tests needed a database.
    """
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker("requires_db")


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for endpoints that do not touch the database.

    Endpoints that do need one take ``test_db`` or ``seeded_db`` as well, which
    points ``get_db`` at the test session.
    """
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def sample_receipt_data() -> dict:
    """Sample receipt data for testing"""
    return {
        "store": "S-Market",
        "date": "2024-01-04",
        "items": [
            {"name": "Maito 1L", "price": 1.49, "quantity": 1},
            {"name": "Leipä 500g", "price": 2.29, "quantity": 2},
            {"name": "Juusto 200g", "price": 3.99, "quantity": 1},
        ],
        "total": 10.06,
    }


@pytest.fixture
def sample_product_data() -> dict:
    """Sample product data dict for testing (non-database)."""
    return {
        "name": "Maito",
        "category": "dairy",
        "default_shelf_life_days": 7,
        "opened_shelf_life_days": 3,
    }


@pytest.fixture
async def sample_category(db_session: AsyncSession) -> Category:
    """Return the ``dairy`` category, creating it if the test has not seeded it.

    Tests may combine this fixture with ``seed_categories`` (which already inserts
    ``dairy``), so it must be idempotent instead of blindly inserting.
    """
    existing = await db_session.get(Category, "dairy")
    if existing is not None:
        return existing

    category = Category(
        id="dairy",
        display_name="Dairy",
        icon="🥛",
        default_shelf_life_days=7,
        meal_contexts=["breakfast"],
        sort_order=1,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


@pytest.fixture
async def sample_product(
    db_session: AsyncSession, sample_category: Category
) -> ProductMaster:
    """Create sample product in database for tests."""
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Test Milk 1L",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
        default_quantity=Decimal("1000"),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def _create_database_if_missing(url: str) -> None:
    import asyncpg
    from sqlalchemy.engine import make_url

    target = make_url(url)
    admin = make_url(maintenance_url(url))
    connection = await asyncpg.connect(
        host=admin.host,
        port=admin.port or 5432,
        user=admin.username,
        password=admin.password,
        database=admin.database,
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target.database
        )
        if not exists:
            # The name is derived from POSTGRES_DB by tests.support, never user input.
            await connection.execute(f'CREATE DATABASE "{target.database}"')
    finally:
        await connection.close()


async def _create_schema(url: str) -> None:
    """Rebuild the test database's schema from the models, once per session.

    Dropped first, not just created: ``create_all`` skips tables that already exist,
    so a test database made before a schema change kept the old shape for ever. That
    let H11's unique index pass locally and fail in CI, which builds its database with
    ``alembic upgrade head`` on every run.

    Only ever reached for a database whose name ends in ``_test`` (``guard_test_database``),
    and tests roll back rather than persist, so there is nothing here to lose.
    """
    # app.db.base is what alembic/env.py uses; it registers every model.
    from app.db.base import Base

    engine = create_async_engine(url, echo=False)
    try:
        async with engine.begin() as conn:
            # The trigram index on product_name needs the extension (H13); alembic
            # creates it in production, create_all does not.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """``<POSTGRES_DB>_test`` - never the database the application is configured with.

    Pure: it derives and guards a name without connecting, so it is safe for the
    autouse fixture below to depend on even when PostgreSQL is not running.

    Settings are imported here rather than at module scope so that a malformed env
    file fails the tests that need one instead of making the suite uncollectable.
    """
    from app.core.config import settings

    return guard_test_database(derive_test_database_url(settings.DATABASE_URL))


@pytest.fixture(scope="session", autouse=True)
def _point_the_app_at_the_test_database(test_database_url: str) -> None:
    """Rebind the application's module-level engine, for the whole session.

    Several tests drive endpoints through ``client`` without overriding ``get_db``,
    so the request opens its own session from ``app.db.session``. Before H01 that
    session talked to the dev database for real, and only the fixture's ``drop_all``
    cleaned up afterwards. Rebinding makes the dev database unreachable from the
    suite even when a test forgets the override.

    ``seed_categories`` captured ``AsyncSessionLocal`` by value at import time, so
    its copy has to be replaced too.
    """
    import app.db.seed_categories as app_seed
    import app.db.session as app_session

    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app_session.engine = engine
    app_session.AsyncSessionLocal = factory
    app_seed.AsyncSessionLocal = factory


@pytest.fixture(scope="session")
def _database_ready(test_database_url: str) -> str:
    """Create the test database and its schema once per session.

    Synchronous on purpose. pytest-asyncio gives every test its own event loop, so
    a session-scoped *async* fixture would hand later tests objects bound to a loop
    that has already closed; ``asyncio.run`` keeps this one-time setup in its own.
    """
    try:
        # Creating the database needs a connection to the maintenance database,
        # which a locked-down role may not have. CI does not need it at all: its
        # POSTGRES_DB is already kyokki_test and the workflow migrates it. Only
        # _create_schema has to succeed, and it fails loudly if the database is
        # genuinely missing.
        with contextlib.suppress(Exception):
            asyncio.run(_create_database_if_missing(test_database_url))
        asyncio.run(_create_schema(test_database_url))
    except Exception:
        if os.environ.get("KYOKKI_TEST_REQUIRE_DB"):
            # CI provides PostgreSQL; a connection failure there is a real failure,
            # not a reason to silently skip the whole DB-backed suite.
            raise
        pytest.skip("PostgreSQL not available")

    return test_database_url


@pytest.fixture
async def db_engine(_database_ready: str):
    """An engine on the test database. The schema is already there."""
    engine = create_async_engine(_database_ready, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def committed_db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """A session whose commits are real, cleaned up by truncating afterwards.

    ``db_session`` below is the default and keeps everything inside one
    rolled-back transaction, which a second connection cannot see. Row locking and
    ``claim_next`` are exactly the behaviours that need two connections, so those
    tests take this instead.
    """
    from app.db.base import Base

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        async with db_engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """A session inside a transaction that is always rolled back.

    ``join_transaction_mode="create_savepoint"`` lets the code under test - and the
    fixtures above - commit for real while every row still disappears when the outer
    transaction rolls back. Before H01 isolation came from dropping and recreating
    every table around each test, against the database ``settings`` pointed at.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


@pytest.fixture
async def test_db(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """``db_session`` with the app's ``get_db`` dependency pointed at it."""
    from app.db.session import get_db
    from app.main import app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def seeded_db(test_db: AsyncSession) -> AsyncSession:
    """``test_db`` plus the seeded categories that product and inventory FKs need."""
    from app.db.seed_categories import seed_categories

    await seed_categories(test_db)
    await test_db.commit()
    return test_db


@pytest.fixture(autouse=True)
async def _dispose_app_engine() -> AsyncGenerator[None, None]:
    """Drop the application's pooled DB connections after each test.

    pytest-asyncio runs every test in its own event loop. Endpoints that are not
    behind a ``get_db`` override use the module-level engine in ``app.db.session``;
    its pool would otherwise hand a connection created in a previous test's (now
    closed) loop to the next test, which fails with "event loop is closed" style
    errors. Disposing in the loop that created the connections avoids that.

    The cached broadcast Redis client in ``app.services.broadcast_helpers`` has the
    same lifetime problem, so it is closed here as well.
    """
    yield

    from app.db.session import engine as app_engine
    from app.services.broadcast_helpers import close_redis_client

    await app_engine.dispose()
    await close_redis_client()


@pytest.fixture(autouse=True)
def _no_model_selection():
    """No test may reach the LLM gateway by accident.

    `ProductResolution` asks the model to choose between candidates for lines that
    deterministic keys could not resolve (H13). With the gateway reachable that is a
    real HTTP request, so an ordinary unit test would depend on the homelab being up
    and take seconds. Selection answers nothing unless a test says otherwise, which is
    also the "model unavailable" path the resolver is required to survive.

    The catalog refresh (Q11) is the second such call and gets the same treatment: it
    answers with nothing, so a test that does not say otherwise proposes no changes.
    """
    from unittest.mock import AsyncMock, patch

    with (
        patch(
            "app.services.product_resolution.select_products",
            new_callable=AsyncMock,
            return_value={},
        ) as selection,
        patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        yield selection


@pytest.fixture
def session_factory(db_session: AsyncSession):
    """A session factory handing out the test session without closing it.

    For code that opens its own sessions (the receipt worker, the Telegram bot).
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield db_session

    return factory


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing broadcasts."""
    from unittest.mock import AsyncMock

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()
    return mock_redis
