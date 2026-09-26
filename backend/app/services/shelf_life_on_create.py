"""A new product gets its own shelf life soon after it is created (Q19).

Creating a product has to store some number - `default_shelf_life_days` is NOT NULL - so it
takes the category's placeholder, or for a receipt line the extraction model's `sl`. On the
homelab 54 of 65 products still carried the placeholder, and the fridge view went red two days
after the shop. The dedicated estimator (`catalog_estimates`) is the authority on both, so
every path that creates products schedules it once its own transaction has committed:

    quick add, stock add     when the product was new
    receipt confirm          every product the confirm created, in one batched request
    POST /products           never: the cook typed that number

It runs as a FastAPI background task, after the response has gone: the cook never waits for
the model. It opens its own session, because the request's is closed by then, and it never
raises - there is nobody left to raise to. A model that cannot answer leaves the placeholder
where it was, with one warning line, and "Re-estimate" on the products page can try again.
"""

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.logging import get_logger
from app.models.product_master import ProductMaster
from app.services.broadcast_helpers import broadcast_inventory_update
from app.services.catalog_estimates import estimate_products
from app.services.llm_extractor import LLMExtractionError

logger = get_logger(__name__)


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    """A session of the task's own. Looked up at call time, so the tests can rebind it."""
    return app_session.AsyncSessionLocal()


def schedule_estimates(
    background_tasks: BackgroundTasks, product_ids: Sequence[UUID]
) -> None:
    """Ask about these new products once the response has been sent. None: nothing."""
    if product_ids:
        background_tasks.add_task(estimate_new_products, list(product_ids))


async def estimate_new_products(product_ids: Sequence[UUID]) -> None:
    """Estimate and apply these products' shelf lives, then broadcast the stock that moved.

    Never raises. See the module docstring for why and for what schedules it.
    """
    if not product_ids:
        return
    ids = [str(product_id) for product_id in product_ids]
    try:
        async with open_session() as db:
            products = list(
                (
                    await db.execute(
                        select(ProductMaster).where(ProductMaster.id.in_(product_ids))
                    )
                )
                .scalars()
                .all()
            )
            result = await estimate_products(db, products, apply=True)
    except LLMExtractionError as exc:
        logger.warning(
            "No shelf-life estimate for new products; keeping the placeholder",
            extra={"product_ids": ids, "error": str(exc)},
        )
        return
    except Exception as exc:  # noqa: BLE001 - a background task has nobody to raise to
        logger.warning(
            "Estimating new products failed; keeping the placeholder",
            extra={"product_ids": ids, "error": repr(exc)},
        )
        return

    if result.considered and not result.answered:
        logger.warning(
            "No usable shelf-life estimate for new products; keeping the placeholder",
            extra={"product_ids": ids, "considered": result.considered},
        )
        return

    for item in result.moved:
        try:
            await broadcast_inventory_update(
                inventory_item_id=item.id,
                action="updated",
                current_quantity=item.current_quantity,
                status=item.status,
            )
        except Exception as exc:  # noqa: BLE001 - the estimate is already committed
            logger.warning(
                "Could not broadcast a re-dated item",
                extra={"inventory_item_id": str(item.id), "error": repr(exc)},
            )

    logger.info(
        "New products estimated",
        extra={
            "product_ids": ids,
            "answered": result.answered,
            "changes": len(result.changes),
            "items_redated": len(result.moved),
        },
    )
