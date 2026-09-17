"""The suite must never touch the database the application is configured with.

Before H01 the fixtures ran `create_all`/`drop_all` against `settings.DATABASE_URL`
itself, so a local `pytest` run with the compose stack up wiped the dev database.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from tests.support import (
    UnsafeTestDatabase,
    derive_test_database_url,
    guard_test_database,
    maintenance_url,
)

DEV_URL = "postgresql+asyncpg://kyokki_user:s3cret@localhost/kyokki"


class TestDerivedUrl:
    def test_appends_the_test_suffix_to_the_configured_database(self) -> None:
        assert derive_test_database_url(DEV_URL) == (
            "postgresql+asyncpg://kyokki_user:s3cret@localhost/kyokki_test"
        )

    def test_is_idempotent(self) -> None:
        once = derive_test_database_url(DEV_URL)
        assert derive_test_database_url(once) == once

    def test_keeps_the_password_usable(self) -> None:
        """SQLAlchemy's ``str(url)`` masks the password as ``***``; the fixtures
        need a URL that can actually connect."""
        assert "s3cret" in derive_test_database_url(DEV_URL)
        assert "***" not in derive_test_database_url(DEV_URL)

    def test_refuses_a_url_with_no_database_name(self) -> None:
        with pytest.raises(UnsafeTestDatabase):
            derive_test_database_url(
                "postgresql+asyncpg://kyokki_user:s3cret@localhost"
            )


class TestGuard:
    def test_accepts_a_test_database(self) -> None:
        guard_test_database(derive_test_database_url(DEV_URL))

    def test_refuses_the_configured_database(self) -> None:
        with pytest.raises(UnsafeTestDatabase) as excinfo:
            guard_test_database(DEV_URL)
        assert "kyokki" in str(excinfo.value)

    def test_never_reveals_the_password(self) -> None:
        with pytest.raises(UnsafeTestDatabase) as excinfo:
            guard_test_database(DEV_URL)
        assert "s3cret" not in str(excinfo.value)


class TestMaintenanceUrl:
    def test_points_at_the_default_database(self) -> None:
        """``CREATE DATABASE`` cannot run from inside the database being created."""
        assert maintenance_url(DEV_URL).endswith("/postgres")


async def _probe(db_session: AsyncSession) -> None:
    """Assert the table is clean, then commit a row into it.

    Run from two tests: if a committed row survived the first test, the second fails.
    """
    total = await db_session.scalar(select(func.count()).select_from(Category))
    assert total == 0, "a previous test's committed rows are still visible"

    db_session.add(
        Category(
            id="isolation-probe",
            display_name="Isolation probe",
            icon="🔬",
            default_shelf_life_days=1,
            meal_contexts=[],
            sort_order=99,
        )
    )
    await db_session.commit()


class TestRollbackIsolation:
    async def test_first_writer(self, db_session: AsyncSession) -> None:
        await _probe(db_session)

    async def test_second_writer_sees_a_clean_database(
        self, db_session: AsyncSession
    ) -> None:
        await _probe(db_session)


class TestFixtureTarget:
    async def test_the_engine_never_points_at_the_configured_database(
        self, db_engine
    ) -> None:
        """The guard above only helps if the fixtures actually use the derived URL."""
        from app.core.config import settings

        assert db_engine.url.database == f"{settings.POSTGRES_DB}{'_test'}"
        assert db_engine.url.database != settings.POSTGRES_DB
