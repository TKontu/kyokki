"""Icon curation (operator ask 2026-10-03): the cook marks a good generated icon
canonical on the product sheet; Settings lists and downloads the marked icons as a bundle.

Gated behind `ICON_CURATION_ENABLED` (false by default in every test here unless
`curation_enabled` is used): the marking routes (`PUT`/`DELETE /marks/{id}`) answer 404
when it is off. `GET /status` always answers - the frontend uses it to decide whether to
show the curation UI at all.
"""

from __future__ import annotations

import io
import json
import zipfile
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.product_master import EmojiMatch, IconStatus, ProductMaster


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), (12, 34, 56, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


FAKE_PNG = _png()


@pytest.fixture
def curation_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ICON_CURATION_ENABLED", True)


async def _product(
    db: AsyncSession,
    name: str = "Quark",
    *,
    icon_status: IconStatus | None = IconStatus.READY,
    icon_seed: int | None = 42,
    icon_image: bytes | None = FAKE_PNG,
    emoji_match: EmojiMatch | None = None,
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
        icon_status=icon_status.value if icon_status else None,
        icon_seed=icon_seed,
        icon_image=icon_image,
        emoji_match=emoji_match.value if emoji_match else None,
    )
    db.add(product)
    await db.commit()
    return product


class TestStatus:
    async def test_disabled_by_default(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get("/api/icon-library/status")

        assert response.status_code == 200
        assert response.json()["curation_enabled"] is False

    async def test_enabled_reports_true(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        response = await client.get("/api/icon-library/status")

        assert response.json()["curation_enabled"] is True

    async def test_marked_count_reflects_the_database(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db)
        await client.put(f"/api/icon-library/marks/{product.id}")

        response = await client.get("/api/icon-library/status")

        assert response.json()["marked_count"] == 1


class TestMark:
    async def test_a_markable_product_can_be_marked(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db)

        response = await client.put(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(product.id)
        assert body["name"] == "Quark"
        assert body["marked_at"] is not None

    async def test_a_pending_icon_refuses(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db, icon_status=IconStatus.PENDING)

        response = await client.put(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "conflict"

    async def test_a_library_icon_refuses(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        """A library icon's `icon_seed` is NULL - it is already in the library."""
        product = await _product(seeded_db, icon_seed=None)

        response = await client.put(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 409

    async def test_an_exact_emoji_win_refuses(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db, emoji_match=EmojiMatch.EXACT)

        response = await client.put(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 409

    async def test_a_cook_emoji_win_refuses(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db, emoji_match=EmojiMatch.COOK)

        response = await client.put(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 409

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        response = await client.put(f"/api/icon-library/marks/{uuid4()}")

        assert response.status_code == 404

    async def test_disabled_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """`ICON_CURATION_ENABLED` is false by default (no `curation_enabled` fixture)."""
        product = await _product(seeded_db)

        response = await client.put(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 404


class TestUnmark:
    async def test_unmarking_a_marked_product(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db)
        await client.put(f"/api/icon-library/marks/{product.id}")

        response = await client.delete(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 200
        assert response.json()["marked_at"] is None

    async def test_unmarking_a_never_marked_product_is_a_no_op(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db)

        response = await client.delete(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 200

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        response = await client.delete(f"/api/icon-library/marks/{uuid4()}")

        assert response.status_code == 404

    async def test_disabled_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        response = await client.delete(f"/api/icon-library/marks/{product.id}")

        assert response.status_code == 404


class TestListMarks:
    async def test_lists_marked_products(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        marked = await _product(seeded_db, "Quark")
        unmarked = await _product(seeded_db, "Leek", icon_seed=99)
        await client.put(f"/api/icon-library/marks/{marked.id}")

        response = await client.get("/api/icon-library/marks")

        assert response.status_code == 200
        names = {entry["name"] for entry in response.json()}
        assert names == {"Quark"}
        assert str(unmarked.id) not in {entry["id"] for entry in response.json()}

    async def test_empty_when_nothing_marked(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        response = await client.get("/api/icon-library/marks")

        assert response.json() == []


class TestBundle:
    async def test_it_zips_every_marked_icon(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db, "Quark")
        await client.put(f"/api/icon-library/marks/{product.id}")

        response = await client.get("/api/icon-library/bundle.zip")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert "icon_library/quark.png" in archive.namelist()
        assert "index.json" in archive.namelist()
        index = json.loads(archive.read("index.json"))
        assert index["quark"]["sha256"]
        assert index["quark"]["source"].startswith("curated:")

    async def test_it_is_empty_when_nothing_is_marked(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        response = await client.get("/api/icon-library/bundle.zip")

        assert response.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        index = json.loads(archive.read("index.json"))
        assert index == {}


class TestProductResponseField:
    """`icon_canonical_at` (schemas/product_master.py): read-only, mirrors the mark."""

    async def test_it_appears_on_the_product_once_marked(
        self, client: AsyncClient, seeded_db: AsyncSession, curation_enabled: None
    ) -> None:
        product = await _product(seeded_db, "Quark")
        before = await client.get(f"/api/products/{product.id}")
        assert before.json()["icon_canonical_at"] is None

        await client.put(f"/api/icon-library/marks/{product.id}")

        after = await client.get(f"/api/products/{product.id}")
        assert after.json()["icon_canonical_at"] is not None
