"""The shared integrity-error handler.

Worth its own tests because the typed branches were dead: `IntegrityError.orig` is
SQLAlchemy's asyncpg wrapper, not an `asyncpg.exceptions.*` instance, so the
isinstance checks never matched and every violation answered a generic 400. No
test noticed, because nothing asserted a 409 from this helper.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.exceptions import (
    handle_integrity_errors,
    reference_conflict_detail,
)


class _AsyncpgError(Exception):
    """Stands in for the asyncpg exception SQLAlchemy wraps."""

    def __init__(self, detail: str | None = None, constraint_name: str | None = None):
        super().__init__(detail or "")
        self.detail = detail
        self.constraint_name = constraint_name


def _integrity_error(sqlstate: str | None, detail: str | None = None) -> IntegrityError:
    """Build the exception shape SQLAlchemy actually raises on asyncpg."""
    wrapper = Exception("wrapped")
    wrapper.sqlstate = sqlstate  # type: ignore[attr-defined]
    wrapper.__cause__ = _AsyncpgError(detail)
    return IntegrityError("INSERT ...", {}, wrapper)


async def _status_for(sqlstate: str | None, detail: str | None = None) -> HTTPException:
    with pytest.raises(HTTPException) as excinfo:
        async with handle_integrity_errors():
            raise _integrity_error(sqlstate, detail)
    return excinfo.value


class TestStatusMapping:
    async def test_unique_violation_is_a_conflict(self) -> None:
        raised = await _status_for("23505", "Key (id)=(dairy) already exists.")
        assert raised.status_code == 409

    async def test_a_missing_reference_is_a_bad_request(self) -> None:
        raised = await _status_for(
            "23503", 'Key (category)=(nope) is not present in table "category".'
        )
        assert raised.status_code == 400

    async def test_a_still_referenced_row_is_a_conflict(self) -> None:
        """Both directions share SQLSTATE 23503; only DETAIL tells them apart."""
        raised = await _status_for(
            "23503",
            'Key (id)=(3) is still referenced from table "inventory_item".',
        )
        assert raised.status_code == 409

    async def test_a_missing_required_field_is_a_bad_request(self) -> None:
        raised = await _status_for("23502", "Failing row contains (null, ...).")
        assert raised.status_code == 400

    async def test_an_unrecognised_violation_is_a_bad_request(self) -> None:
        assert (await _status_for("23514")).status_code == 400
        assert (await _status_for(None)).status_code == 400

    async def test_nothing_is_raised_when_the_block_succeeds(self) -> None:
        async with handle_integrity_errors():
            pass


class TestNoLeakedDatabaseText:
    """`detail` reaches the cook verbatim through the frontend API client, and
    asyncpg's DETAIL line quotes the offending row's values."""

    @pytest.mark.parametrize(
        ("sqlstate", "detail"),
        [
            ("23505", "Key (barcode)=(5901234123457) already exists."),
            ("23503", 'Key (category)=(secret) is not present in table "category".'),
            ("23503", 'Key (id)=(3) is still referenced from table "inventory_item".'),
            ("23502", "Failing row contains (1, Valio Maito, null)."),
        ],
    )
    async def test_the_database_detail_never_reaches_the_response(
        self, sqlstate: str, detail: str
    ) -> None:
        raised = await _status_for(sqlstate, detail)
        assert "Key (" not in raised.detail
        assert "Failing row" not in raised.detail
        assert detail not in raised.detail


class TestReferenceConflictDetail:
    def test_one_reference_reads_as_a_sentence(self) -> None:
        assert (
            reference_conflict_detail({"inventory_item": 1})
            == "Cannot delete: still referenced by 1 inventory item."
        )

    def test_counts_are_pluralised(self) -> None:
        assert "3 inventory items" in reference_conflict_detail({"inventory_item": 3})

    def test_several_kinds_are_listed(self) -> None:
        detail = reference_conflict_detail(
            {"inventory_item": 2, "store_product_alias": 1, "shopping_list_item": 4}
        )
        assert "2 inventory items" in detail
        assert "1 receipt name alias" in detail
        assert "and 4 shopping list items" in detail

    def test_zero_counts_are_ignored(self) -> None:
        assert "0 " not in reference_conflict_detail(
            {"inventory_item": 0, "store_product_alias": 2}
        )

    def test_an_unlabelled_table_still_produces_a_sentence(self) -> None:
        detail = reference_conflict_detail({"some_new_table": 1})
        assert detail.startswith("Cannot delete:")
        assert "some new table" in detail

    def test_no_references_still_produces_a_sentence(self) -> None:
        assert reference_conflict_detail({}).startswith("Cannot delete:")
