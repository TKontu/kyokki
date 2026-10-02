"""Q18-G2: the icon backfill script's summary (F12 review).

A non-ready outcome used to be bucketed as "failed" across the board, which hid a product
deleted mid-job ("gone") and one still pending or raced with another writer ("pending")
behind an actual render failure. The script itself (products_to_generate,
still_needs_generation, draw_icon) is the real behaviour under test here; `backfill()` is
the thin loop and summary around it.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from scripts import backfill_icons
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.product_master import IconStatus, ProductMaster
from app.services import product_icons


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


@pytest.fixture(autouse=True)
def _comfyui_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "http://comfyui.test")


@pytest.fixture
def broadcast():
    with patch(
        "app.services.product_icons.broadcast_product_update", new_callable=AsyncMock
    ):
        yield


async def _product(db: AsyncSession, name: str = "Quark") -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
    )
    db.add(product)
    await db.commit()
    return product


def _sessions_for(db: AsyncSession):
    @asynccontextmanager
    async def factory():
        yield db

    return factory


class TestTheSummaryBuckets:
    async def test_a_generated_product_counts_as_ready(
        self, db_session: AsyncSession, categories, broadcast, monkeypatch
    ) -> None:
        monkeypatch.setattr(product_icons, "open_session", _sessions_for(db_session))
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        product = await _product(db_session)

        with patch.object(
            product_icons.comfyui, "render", new=AsyncMock(return_value=[png])
        ):
            counts = await backfill_icons.backfill(
                None, False, sessions=_sessions_for(db_session)
            )

        assert counts["ready"] == 1
        assert counts["failed"] == counts["pending"] == counts["gone"] == 0
        assert (
            await db_session.get(ProductMaster, product.id, populate_existing=True)
        ).icon_status == "ready"

    async def test_a_render_failure_counts_as_failed(
        self, db_session: AsyncSession, categories, broadcast, monkeypatch
    ) -> None:
        monkeypatch.setattr(product_icons, "open_session", _sessions_for(db_session))
        await _product(db_session)

        with patch.object(
            product_icons.comfyui,
            "render",
            new=AsyncMock(side_effect=RuntimeError("down")),
        ):
            counts = await backfill_icons.backfill(
                None, False, sessions=_sessions_for(db_session)
            )

        assert counts == {
            "ready": 0,
            "failed": 1,
            "pending": 0,
            "gone": 0,
            "skipped": 0,
        }

    async def test_a_product_deleted_mid_job_counts_as_gone(
        self, db_session: AsyncSession, categories, broadcast, monkeypatch
    ) -> None:
        monkeypatch.setattr(product_icons, "open_session", _sessions_for(db_session))
        product = await _product(db_session)

        async def delete_it(product_id, hint=None):
            await db_session.delete(await db_session.get(ProductMaster, product_id))
            await db_session.commit()

        with patch.object(product_icons, "draw_icon", new=delete_it):
            counts = await backfill_icons.backfill(
                None, False, sessions=_sessions_for(db_session)
            )

        assert counts == {
            "ready": 0,
            "failed": 0,
            "pending": 0,
            "gone": 1,
            "skipped": 0,
        }
        assert (
            product.id is not None
        )  # the fixture row existed; this is just documentation

    async def test_a_job_still_pending_counts_as_pending_not_failed(
        self, db_session: AsyncSession, categories, broadcast, monkeypatch
    ) -> None:
        """A second Regenerate from the API racing in, or the job simply not done yet by the
        time this prints, must not be called "failed"."""
        monkeypatch.setattr(product_icons, "open_session", _sessions_for(db_session))
        await _product(db_session)

        async def leave_pending(product_id, hint=None):
            row = await db_session.get(ProductMaster, product_id)
            row.icon_status = IconStatus.PENDING  # type: ignore[assignment]
            row.icon_seed = 1  # type: ignore[assignment]
            await db_session.commit()

        with patch.object(product_icons, "draw_icon", new=leave_pending):
            counts = await backfill_icons.backfill(
                None, False, sessions=_sessions_for(db_session)
            )

        assert counts == {
            "ready": 0,
            "failed": 0,
            "pending": 1,
            "gone": 0,
            "skipped": 0,
        }

    async def test_a_dry_run_lists_without_generating(
        self, db_session: AsyncSession, categories, capsys
    ) -> None:
        await _product(db_session, "Skyr")

        counts = await backfill_icons.backfill(
            None, True, sessions=_sessions_for(db_session)
        )

        assert counts == {
            "ready": 0,
            "failed": 0,
            "pending": 0,
            "gone": 0,
            "skipped": 0,
        }
        assert "would generate" in capsys.readouterr().out

    async def test_refuses_to_run_for_real_when_disabled(
        self, db_session: AsyncSession, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")

        counts = await backfill_icons.backfill(
            None, False, sessions=_sessions_for(db_session)
        )

        assert counts == {
            "ready": 0,
            "failed": 0,
            "pending": 0,
            "gone": 0,
            "skipped": 0,
        }
        assert "Refusing to run" in capsys.readouterr().out

    async def test_dry_run_still_lists_when_disabled(
        self, db_session: AsyncSession, categories, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        await _product(db_session, "Skyr")

        await backfill_icons.backfill(None, True, sessions=_sessions_for(db_session))

        assert "would generate" in capsys.readouterr().out
