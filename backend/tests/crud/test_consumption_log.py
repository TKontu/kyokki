"""Which way a `correct` row moved the quantity (the undo preview's direction field).

Pure unit tests against plain, uncommitted `ConsumptionLog` rows: no database needed, since
`correction_direction` only reads columns already on the row.
"""

from decimal import Decimal

from app.crud.consumption_log import correction_direction
from app.models.consumption_log import ConsumptionLog


def _row(
    action: str = "correct",
    quantity_after: str = "7",
    previous: dict | None = None,
) -> ConsumptionLog:
    return ConsumptionLog(
        action=action,
        quantity_consumed=Decimal("3"),
        quantity_after=Decimal(quantity_after),
        unit="dl",
        previous=previous,
    )


def test_a_correction_that_raised_the_quantity_reads_up() -> None:
    row = _row(quantity_after="7", previous={"current_quantity": "4"})

    assert correction_direction(row) == "up"


def test_a_correction_that_lowered_the_quantity_reads_down() -> None:
    row = _row(quantity_after="4", previous={"current_quantity": "7"})

    assert correction_direction(row) == "down"


def test_a_row_with_no_previous_snapshot_has_no_direction() -> None:
    """A row logged before undo existed - `previous` is NULL - cannot say which way it went."""
    row = _row(previous=None)

    assert correction_direction(row) is None


def test_a_row_whose_previous_snapshot_lacks_the_quantity_has_no_direction() -> None:
    """An old row whose snapshot shape did not carry `current_quantity` - nothing to compare."""
    row = _row(previous={"status": "sealed"})

    assert correction_direction(row) is None


def test_every_action_but_correct_has_no_direction() -> None:
    for action in ("use_partial", "use_full", "discard", "restore"):
        row = _row(action=action, previous={"current_quantity": "4"})

        assert correction_direction(row) is None, action


def test_a_correction_that_left_the_quantity_unchanged_has_no_direction() -> None:
    """Should not happen in practice (the caller only logs a `correct` when it moved), but a
    row that somehow says otherwise reads as unknown rather than guessing a side."""
    row = _row(quantity_after="7", previous={"current_quantity": "7"})

    assert correction_direction(row) is None
