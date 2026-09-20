"""What a stored item's status may become, and when (H23).

Until this, the rules lived inside `apply_quantity_status` and were reachable two ways: derived
from the quantity, or set outright by a client PATCHing `status`, which suppressed the derivation
entirely. Three things followed from having no table:

- **`discarded` did not freeze anything.** The discard was logged, the quantity left alone, and no
  writer checked the status first - so consuming a discarded item walked it back into the list.
- **A correction above full kept a stale label**, because `initial_quantity` was raised first and
  the "below full" test then read false.
- **Any status could follow any other**, `discarded -> sealed` included.

The table below is the whole vocabulary of legal moves. It is pure - no session, no I/O - so it
can be read by tests on both sides of the wire; `contracts/status-transitions.json` holds the
cases and `frontend/lib/consumption.ts` answers to the same ones.
"""

from decimal import Decimal
from enum import StrEnum

# Statuses. The column is a plain string; this is the single vocabulary (H24 will move this
# beside the others and give it a database constraint).
SEALED = "sealed"
OPENED = "opened"
PARTIAL = "partial"
EMPTY = "empty"
DISCARDED = "discarded"

#: Thrown away. Frozen: the only move out is an explicit restore.
FROZEN_STATUSES = (DISCARDED,)

#: At or above this share of the full amount, an opened pack still reads `opened` (MVP-C2).
#: `frontend/lib/consumption.ts` carries the same number and the shared fixture pins both.
PARTIAL_THRESHOLD = Decimal("0.75")


class ItemEvent(StrEnum):
    """What happened to the food, which is what decides the move."""

    CONSUME = "consume"  # some of it was eaten or used
    CORRECT = "correct"  # the cook says the amount was wrong
    DISCARD = "discard"  # it was thrown away
    RESTORE = "restore"  # ...that was a mis-tap


class ItemFrozen(Exception):
    """A write was attempted against an item that has been thrown away."""

    def __init__(self, status: str, event: ItemEvent) -> None:
        super().__init__(
            f"An item marked '{status}' cannot be changed by '{event}'. "
            "Restore it first if it was not really thrown away."
        )
        self.status = status
        self.event = event


def is_frozen(status: str) -> bool:
    """Whether this status refuses writes."""
    return status in FROZEN_STATUSES


def next_status(
    *,
    current: str,
    event: ItemEvent,
    initial: Decimal,
    remaining: Decimal,
    opened: bool,
) -> str:
    """The status this item moves to, or raise if the move is not allowed.

    `opened` is whether the pack has ever been opened - `opened_date is not None` - which is the
    one piece of history the status alone cannot carry. It decides the full-again case: a sealed
    pack corrected upward is still sealed, and anything that was opened reads `opened`, because
    a jar does not re-seal itself.

    Raises:
        ItemFrozen: the item was thrown away and the event is not `RESTORE`.
    """
    if is_frozen(current) and event is not ItemEvent.RESTORE:
        raise ItemFrozen(current, event)

    if event is ItemEvent.DISCARD:
        return DISCARDED
    if event is ItemEvent.RESTORE:
        # Back into the kitchen, never as `sealed`: it was in the bin.
        return EMPTY if remaining <= 0 else OPENED

    if remaining <= 0:
        return EMPTY
    if remaining >= initial:
        return SEALED if current == SEALED and not opened else OPENED
    return PARTIAL if remaining / initial < PARTIAL_THRESHOLD else OPENED


def opens_the_pack(current: str, new: str) -> bool:
    """Whether this move is the one that first opens a sealed pack.

    The edge Q5's opened clock hangs on, named rather than re-derived at the call site.
    """
    return current == SEALED and new in (OPENED, PARTIAL, EMPTY)
