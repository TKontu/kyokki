"""Helpers the fixtures share.

They live outside ``conftest.py`` so the database-name guard - the thing standing
between a local ``pytest`` run and the dev database - can be tested directly.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url

TEST_DB_SUFFIX = "_test"

# CREATE DATABASE cannot run from inside the database being created.
MAINTENANCE_DB = "postgres"


class UnsafeTestDatabase(RuntimeError):
    """The suite was about to run against something that is not a test database."""


def derive_test_database_url(database_url: str) -> str:
    """Return ``database_url`` pointing at ``<database>_test``.

    Idempotent, and it keeps the password readable: SQLAlchemy's ``str(url)``
    renders it as ``***``, which cannot connect.
    """
    url = make_url(database_url)
    name = url.database or ""
    if not name:
        raise UnsafeTestDatabase(
            f"{url.drivername} URL has no database name; cannot derive a test database"
        )
    if not name.endswith(TEST_DB_SUFFIX):
        url = url.set(database=f"{name}{TEST_DB_SUFFIX}")
    return url.render_as_string(hide_password=False)


def guard_test_database(database_url: str) -> str:
    """Raise unless ``database_url`` names a test database.

    The fixtures create and truncate tables. Before H01 they did that to whatever
    ``settings.DATABASE_URL`` pointed at, which locally is the dev database.
    """
    url = make_url(database_url)
    name = url.database or ""
    if not name.endswith(TEST_DB_SUFFIX):
        raise UnsafeTestDatabase(
            f"refusing to run the test suite against database {name!r}: "
            f"the name must end in {TEST_DB_SUFFIX!r}"
        )
    return database_url


def maintenance_url(database_url: str) -> str:
    """The same server, connected to the default database."""
    url = make_url(database_url).set(database=MAINTENANCE_DB)
    return url.render_as_string(hide_password=False)
