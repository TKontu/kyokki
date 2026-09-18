"""What the cook has told us is not food (Q1).

The model names household products and answers ``household`` for their category, but it does
not always. Once the cook has confirmed that a printed name is not food, remembering it is what
stops the same paper towels being offered every week.

Keyed like ``store_product_alias``: the normalised printed name plus the store chain, so both
agree on what "the same line" means.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.non_food_name import NonFoodName
from app.services.matching_service import normalize_receipt_name


async def known_non_food(db: AsyncSession, store_chain: str | None) -> set[str]:
    """Normalised printed names already known to be non-food.

    A name learned at one chain counts at every chain: a compost bag is a compost bag.
    """
    rows = (await db.execute(select(NonFoodName))).scalars().all()
    return {str(row.receipt_name) for row in rows}


async def forget_non_food(
    db: AsyncSession, store_chain: str, receipt_names: list[str]
) -> int:
    """Drop printed names the cook has now treated as food. Returns rows deleted.

    Nothing else in the codebase deletes a `non_food_name` row, so before this a
    misjudgement - the model calling a food line household, the cook not noticing -
    hid that product from every future receipt with no way back.
    """
    names = [n for n in (normalize_receipt_name(raw) for raw in receipt_names) if n]
    if not names:
        return 0
    deleted = await db.execute(
        delete(NonFoodName)
        .where(
            NonFoodName.store_chain == store_chain,
            NonFoodName.receipt_name.in_(names),
        )
        .returning(NonFoodName.id)
    )
    return len(deleted.scalars().all())


async def remember_non_food(
    db: AsyncSession, store_chain: str, receipt_names: list[str]
) -> int:
    """Record printed names as not food. Returns how many rows were touched."""
    touched = 0
    now = datetime.now(UTC)
    for raw in receipt_names:
        name = normalize_receipt_name(raw)
        if not name:
            continue
        existing = (
            (
                await db.execute(
                    select(NonFoodName).where(
                        NonFoodName.store_chain == store_chain,
                        NonFoodName.receipt_name == name,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            db.add(
                NonFoodName(
                    store_chain=store_chain,
                    receipt_name=name,
                    times_seen=1,
                    last_seen=now,
                )
            )
        else:
            row: Any = existing  # Column-typed model: assign plain values
            row.times_seen = (row.times_seen or 0) + 1
            row.last_seen = now
        touched += 1
    return touched
