"""POST /api/receipts/share: the PWA as an Android share target (frontier item 10).

Android navigates to the share action with a multipart form post, so the endpoint answers
with a 303 to a page rather than JSON: one receipt opens its review page, several open the
list, and nothing accepted lands on the scan page with a failure note.
"""

import logging
import shutil
from io import BytesIO
from unittest.mock import AsyncMock, patch

import anyio
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.receipt import Receipt

SHARE = "/api/receipts/share"


@pytest.fixture(autouse=True)
def no_unplanned_re_read():
    """Sharing only queues a receipt; nothing here may reach the model gateway."""
    with patch(
        "app.services.receipt_processing.extract_unaccounted_lines",
        new_callable=AsyncMock,
        side_effect=AssertionError("unexpected targeted re-read"),
    ) as retry:
        yield retry


@pytest.fixture
async def test_db(db_session: AsyncSession):
    """Route the app to the test session and clean the stored receipt files afterwards."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield db_session
    app.dependency_overrides.clear()

    receipts_dir = anyio.Path("data/receipts")
    if await receipts_dir.exists():
        shutil.rmtree(str(receipts_dir))
        await receipts_dir.mkdir(parents=True, exist_ok=True)


def _image(name: str, content: bytes) -> tuple[str, tuple[str, BytesIO, str]]:
    return ("receipts", (name, BytesIO(content), "image/jpeg"))


async def _receipt_ids(db: AsyncSession) -> list[str]:
    rows = await db.execute(select(Receipt.id))
    return [str(r) for r in rows.scalars().all()]


async def _receipt_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Receipt))).scalar_one()


class TestShareReceipts:
    async def test_one_image_opens_its_review_page(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(
            SHARE,
            files=[_image("receipt.jpg", b"fake shared image")],
            follow_redirects=False,
        )

        assert response.status_code == 303
        ids = await _receipt_ids(test_db)
        assert len(ids) == 1
        assert response.headers["location"] == f"/receipt/{ids[0]}"

    async def test_a_shared_pdf_is_accepted(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(
            SHARE,
            files=[
                (
                    "receipts",
                    ("order.pdf", BytesIO(b"%PDF-1.4 shared"), "application/pdf"),
                )
            ],
            follow_redirects=False,
        )

        assert response.status_code == 303
        ids = await _receipt_ids(test_db)
        assert response.headers["location"] == f"/receipt/{ids[0]}"

    async def test_two_files_open_the_receipt_list(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(
            SHARE,
            files=[_image("a.jpg", b"fake image a"), _image("b.jpg", b"fake image b")],
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/receipts"
        assert await _receipt_count(test_db) == 2

    async def test_an_unsupported_file_does_not_stop_the_good_one(
        self, client: AsyncClient, test_db: AsyncSession, caplog
    ) -> None:
        secret = b"private note text that must not be logged"
        with caplog.at_level(logging.DEBUG):
            response = await client.post(
                SHARE,
                files=[
                    ("receipts", ("note.txt", BytesIO(secret), "text/plain")),
                    _image("good.jpg", b"fake good image"),
                ],
                follow_redirects=False,
            )

        assert response.status_code == 303
        ids = await _receipt_ids(test_db)
        assert len(ids) == 1
        assert response.headers["location"] == f"/receipt/{ids[0]}"
        assert "private note text" not in caplog.text

    async def test_only_unsupported_files_land_on_scan_with_a_failure(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(
            SHARE,
            files=[("receipts", ("note.txt", BytesIO(b"plain text"), "text/plain"))],
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/scan?shared=failed"
        assert await _receipt_count(test_db) == 0

    async def test_a_file_over_the_size_limit_is_skipped(
        self, client: AsyncClient, test_db: AsyncSession, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "MAX_RECEIPT_UPLOAD_BYTES", 10)
        response = await client.post(
            SHARE,
            files=[_image("big.jpg", b"this image is over ten bytes")],
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/scan?shared=failed"
        assert await _receipt_count(test_db) == 0

    async def test_no_files_land_on_scan_with_a_failure(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(
            SHARE, data={"title": "Shared"}, follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/scan?shared=failed"

    async def test_an_empty_post_lands_on_scan_with_a_failure(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(SHARE, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/scan?shared=failed"

    async def test_the_same_file_twice_is_one_receipt(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        content = b"fake image shared twice"
        response = await client.post(
            SHARE,
            files=[_image("a.jpg", content), _image("a-copy.jpg", content)],
            follow_redirects=False,
        )

        assert response.status_code == 303
        ids = await _receipt_ids(test_db)
        assert len(ids) == 1
        assert response.headers["location"] == f"/receipt/{ids[0]}"

    async def test_an_already_uploaded_file_opens_the_existing_receipt(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        content = b"%PDF-1.4 uploaded earlier"
        first = await client.post(
            "/api/receipts/scan",
            files={"file": ("order.pdf", BytesIO(content), "application/pdf")},
        )
        assert first.status_code == 201

        response = await client.post(
            SHARE,
            files=[("receipts", ("order.pdf", BytesIO(content), "application/pdf"))],
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == f"/receipt/{first.json()['id']}"
        assert await _receipt_count(test_db) == 1

    async def test_android_title_text_and_url_fields_are_accepted(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.post(
            SHARE,
            data={
                "title": "Receipt",
                "text": "Shared from Gallery",
                "url": "https://example.com/r",
            },
            files=[_image("receipt.jpg", b"fake image with fields")],
            follow_redirects=False,
        )

        assert response.status_code == 303
        ids = await _receipt_ids(test_db)
        assert response.headers["location"] == f"/receipt/{ids[0]}"
