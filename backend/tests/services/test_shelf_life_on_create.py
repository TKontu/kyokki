"""Q19: a new product gets its own shelf life soon after it is created.

Creation has to store some number - the column is NOT NULL - so it takes the category's
placeholder, or the extraction model's `sl` for a receipt line. The dedicated estimator is the
authority on both, so each create path schedules it in the background. It opens its own
session, because the request's is closed by the time it runs, and it never raises: a model that
cannot answer leaves the placeholder where it was.
"""

import logging
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import SEED_CATEGORIES
from app.services import shelf_life_on_create
from app.services.catalog_estimates import Estimate, EstimateRequest
from app.services.generic_products import ProductResolver, build_inventory_item
from app.services.llm_extractor import LLMExtractionError
from app.services.shelf_life_on_create import (
    estimate_new_products,
    schedule_estimates,
)

PRODUCE_DAYS = next(
    c["default_shelf_life_days"] for c in SEED_CATEGORIES if c["id"] == "produce"
)
BOUGHT = date(2026, 9, 1)


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, session_factory) -> None:
    """The task opens its own session; here it is the test's, so its rows are visible."""
    monkeypatch.setattr(shelf_life_on_create, "open_session", session_factory)


@pytest.fixture
def broadcast():
    with patch(
        "app.services.shelf_life_on_create.broadcast_inventory_update",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


def _says(days: int, opened: int | None = None):
    """An estimator that answers `days` for every product it is asked about."""

    async def answer(products: list[EstimateRequest]) -> list[Estimate]:
        return [
            Estimate(id=p.id, shelf_life_days=days, opened_shelf_life_days=opened)
            for p in products
        ]

    return patch(
        "app.services.catalog_estimates.estimate_shelf_lives",
        new=AsyncMock(side_effect=answer),
    )


async def _stocked(db: AsyncSession, name: str, **kwargs):
    product, _ = await ProductResolver(db).resolve(
        name=name, category="produce", unit="pcs", quantity=1, **kwargs
    )
    item = build_inventory_item(product, quantity=1, purchase_date=BOUGHT)
    db.add(item)
    await db.commit()
    return product, item


class TestEstimateNewProducts:
    async def test_the_estimate_lands_and_the_food_moves_with_it(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product, item = await _stocked(db_session, "Tomato")
        assert item.expiry_date == BOUGHT + timedelta(days=PRODUCE_DAYS)

        with _says(14, opened=None):
            await estimate_new_products([product.id])

        await db_session.refresh(product)
        await db_session.refresh(item)
        assert product.default_shelf_life_days == 14
        assert product.shelf_life_source == "model"
        assert item.expiry_date == BOUGHT + timedelta(days=14)
        broadcast.assert_awaited_once()
        assert broadcast.await_args.kwargs["inventory_item_id"] == item.id
        assert broadcast.await_args.kwargs["action"] == "updated"

    async def test_all_the_products_go_in_one_request(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        tomato, _ = await _stocked(db_session, "Tomato")
        carrot, _ = await _stocked(db_session, "Carrot")

        with _says(20) as estimator:
            await estimate_new_products([tomato.id, carrot.id])

        estimator.assert_awaited_once()
        (asked,) = estimator.await_args.args
        assert {r.id for r in asked} == {str(tomato.id), str(carrot.id)}

    async def test_it_replaces_the_extraction_models_first_guess(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        """The receipt's `sl` is only the first value until the estimator's lands."""
        product, _ = await _stocked(db_session, "Tomato", shelf_life_days=5)
        assert product.shelf_life_source == "model"

        with _says(14):
            await estimate_new_products([product.id])

        await db_session.refresh(product)
        assert product.default_shelf_life_days == 14
        assert product.shelf_life_source == "model"

    async def test_a_number_the_cook_chose_is_never_asked_about(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product, _ = await _stocked(db_session, "Tomato")
        product.default_shelf_life_days = 4
        product.shelf_life_source = "cook"
        await db_session.commit()

        with _says(14) as estimator:
            await estimate_new_products([product.id])

        estimator.assert_not_awaited()
        await db_session.refresh(product)
        assert (product.default_shelf_life_days, product.shelf_life_source) == (
            4,
            "cook",
        )

    async def test_an_opened_life_is_filled_only_when_missing(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        known, _ = await _stocked(db_session, "Sour cream", opened_shelf_life_days=5)
        missing, _ = await _stocked(db_session, "Ham")

        with _says(14, opened=4):
            await estimate_new_products([known.id, missing.id])

        await db_session.refresh(known)
        await db_session.refresh(missing)
        assert known.opened_shelf_life_days == 5
        assert missing.opened_shelf_life_days == 4

    async def test_a_model_that_cannot_answer_leaves_the_placeholder(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        product, item = await _stocked(db_session, "Tomato")

        with (
            patch(
                "app.services.catalog_estimates.estimate_shelf_lives",
                new=AsyncMock(side_effect=LLMExtractionError("gateway is down")),
            ),
            caplog.at_level(logging.WARNING),
        ):
            await estimate_new_products([product.id])  # does not raise

        await db_session.refresh(product)
        await db_session.refresh(item)
        assert product.default_shelf_life_days == PRODUCE_DAYS
        assert product.shelf_life_source == "category"
        assert item.expiry_date == BOUGHT + timedelta(days=PRODUCE_DAYS)
        broadcast.assert_not_awaited()
        warnings = [
            r for r in caplog.records if r.name.endswith("shelf_life_on_create")
        ]
        assert [r.levelno for r in warnings] == [logging.WARNING]

    async def test_no_usable_answer_is_a_warning_too(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        product, _ = await _stocked(db_session, "Tomato")

        with (
            patch(
                "app.services.catalog_estimates.estimate_shelf_lives",
                new_callable=AsyncMock,
                return_value=[],
            ),
            caplog.at_level(logging.WARNING),
        ):
            await estimate_new_products([product.id])

        await db_session.refresh(product)
        assert product.shelf_life_source == "category"
        warnings = [
            r for r in caplog.records if r.name.endswith("shelf_life_on_create")
        ]
        assert [r.levelno for r in warnings] == [logging.WARNING]

    async def test_anything_else_going_wrong_never_escapes(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        """It runs after the response; an exception there has nobody to go to."""
        product, _ = await _stocked(db_session, "Tomato")

        with (
            patch(
                "app.services.catalog_estimates.estimate_shelf_lives",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            caplog.at_level(logging.WARNING),
        ):
            await estimate_new_products([product.id])

        await db_session.refresh(product)
        assert product.shelf_life_source == "category"

    async def test_a_product_that_is_gone_is_skipped(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        with _says(14) as estimator:
            await estimate_new_products([uuid4()])

        estimator.assert_not_awaited()

    async def test_nothing_to_do_opens_nothing(self, monkeypatch) -> None:
        opened = []
        monkeypatch.setattr(shelf_life_on_create, "open_session", opened.append)

        await estimate_new_products([])

        assert opened == []


class TestScheduleEstimates:
    def test_it_adds_one_task_for_all_the_products(self) -> None:
        tasks = BackgroundTasks()
        ids = [uuid4(), uuid4()]

        schedule_estimates(tasks, ids)

        (task,) = tasks.tasks
        assert task.func is estimate_new_products
        assert task.args == (ids,)

    def test_no_products_schedules_nothing(self) -> None:
        tasks = BackgroundTasks()

        schedule_estimates(tasks, [])

        assert tasks.tasks == []
