"""The repo-shipped icon library (operator ask 2026-10-03): a loader over
`app/resources/icon_library/index.json` plus the PNGs beside it.

Read once and cached, exactly like `app.services.icon_subjects`; a sha256 mismatch or a
missing file is logged at WARNING and ignored rather than served.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.icon_library as icon_library
from app.models.product_master import EmojiMatch, IconStatus, ProductMaster
from app.services.icon_library import lookup


def _write_library(tmp_path, monkeypatch, entries: dict[str, bytes]) -> None:
    """One PNG file per entry, keyed by its (already normalised-looking) name, plus a
    matching index.json. `entries` maps the canonical name to the file's raw bytes."""
    index = {}
    for name, data in entries.items():
        file_name = f"{name.lower().replace(' ', '_')}.png"
        (tmp_path / file_name).write_bytes(data)
        index[name] = {
            "file": file_name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "subject": None,
            "seed": 123,
            "source": "generated:test-host",
            "exported_at": "2026-10-03T00:00:00+00:00",
        }
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(icon_library, "_INDEX_PATH", index_path)
    icon_library._cache.cache_clear()


class TestLookup:
    def test_an_unknown_product_has_no_library_icon(
        self, tmp_path, monkeypatch
    ) -> None:
        _write_library(tmp_path, monkeypatch, {})

        assert lookup("Quark") is None

    def test_a_known_product_is_found(self, tmp_path, monkeypatch) -> None:
        _write_library(tmp_path, monkeypatch, {"Quark": b"fake-png-bytes"})

        assert lookup("Quark") == b"fake-png-bytes"

    def test_the_lookup_is_case_and_space_insensitive(
        self, tmp_path, monkeypatch
    ) -> None:
        _write_library(tmp_path, monkeypatch, {"Quark": b"fake-png-bytes"})

        assert lookup("  QUARK  ") == b"fake-png-bytes"

    def test_a_missing_index_is_treated_as_an_empty_library(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            icon_library, "_INDEX_PATH", tmp_path / "does_not_exist.json"
        )
        icon_library._cache.cache_clear()

        assert lookup("Quark") is None

    def test_a_malformed_index_is_treated_as_empty(self, tmp_path, monkeypatch) -> None:
        path = tmp_path / "index.json"
        path.write_text("not json at all", encoding="utf-8")
        monkeypatch.setattr(icon_library, "_INDEX_PATH", path)
        icon_library._cache.cache_clear()

        assert lookup("Quark") is None

    def test_a_json_list_instead_of_an_object_is_treated_as_empty(
        self, tmp_path, monkeypatch
    ) -> None:
        path = tmp_path / "index.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setattr(icon_library, "_INDEX_PATH", path)
        icon_library._cache.cache_clear()

        assert lookup("Quark") is None


class TestShaMismatch:
    def test_a_file_whose_sha256_does_not_match_is_ignored_and_logged(
        self, tmp_path, monkeypatch, caplog: logging.LogCaptureFixture
    ) -> None:
        (tmp_path / "quark.png").write_bytes(b"tampered bytes")
        index = {
            "Quark": {
                "file": "quark.png",
                "sha256": hashlib.sha256(b"the original bytes").hexdigest(),
                "subject": None,
                "seed": None,
                "source": "generated:test-host",
                "exported_at": "2026-10-03T00:00:00+00:00",
            }
        }
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        monkeypatch.setattr(icon_library, "_INDEX_PATH", index_path)
        icon_library._cache.cache_clear()

        with caplog.at_level(logging.WARNING):
            result = lookup("Quark")

        assert result is None
        assert any("sha256" in r.getMessage() for r in caplog.records)

    def test_a_missing_file_is_ignored_and_logged(
        self, tmp_path, monkeypatch, caplog: logging.LogCaptureFixture
    ) -> None:
        index = {
            "Quark": {
                "file": "does_not_exist.png",
                "sha256": "whatever",
                "subject": None,
                "seed": None,
                "source": "generated:test-host",
                "exported_at": "2026-10-03T00:00:00+00:00",
            }
        }
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        monkeypatch.setattr(icon_library, "_INDEX_PATH", index_path)
        icon_library._cache.cache_clear()

        with caplog.at_level(logging.WARNING):
            result = lookup("Quark")

        assert result is None
        assert any("missing" in r.getMessage().lower() for r in caplog.records)

    def test_an_entry_missing_file_or_sha256_fields_is_ignored(
        self, tmp_path, monkeypatch
    ) -> None:
        index = {"Quark": {"subject": "a tub of cheese"}}
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        monkeypatch.setattr(icon_library, "_INDEX_PATH", index_path)
        icon_library._cache.cache_clear()

        assert lookup("Quark") is None

    def test_one_bad_entry_does_not_break_the_rest_of_the_library(
        self, tmp_path, monkeypatch
    ) -> None:
        (tmp_path / "leek.png").write_bytes(b"good leek bytes")
        index = {
            "Quark": {
                "file": "does_not_exist.png",
                "sha256": "whatever",
            },
            "Leek": {
                "file": "leek.png",
                "sha256": hashlib.sha256(b"good leek bytes").hexdigest(),
            },
        }
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        monkeypatch.setattr(icon_library, "_INDEX_PATH", index_path)
        icon_library._cache.cache_clear()

        assert lookup("Quark") is None
        assert lookup("Leek") == b"good leek bytes"


def _fake_png() -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


FAKE_PNG = _fake_png()


async def _product(
    db: AsyncSession,
    name: str = "Quark",
    *,
    icon_status: IconStatus | None = IconStatus.READY,
    icon_seed: int | None = 123,
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


class TestIsMarkable:
    def test_a_ready_generated_non_emoji_icon_is_markable(self) -> None:
        product = ProductMaster(
            icon_status=IconStatus.READY.value, icon_seed=1, emoji_match=None
        )
        assert icon_library.is_markable(product) is True

    def test_a_pending_icon_is_not_markable(self) -> None:
        product = ProductMaster(
            icon_status=IconStatus.PENDING.value, icon_seed=1, emoji_match=None
        )
        assert icon_library.is_markable(product) is False

    def test_a_library_icon_with_no_seed_is_not_markable(self) -> None:
        product = ProductMaster(
            icon_status=IconStatus.READY.value, icon_seed=None, emoji_match=None
        )
        assert icon_library.is_markable(product) is False

    def test_an_exact_emoji_win_is_not_markable(self) -> None:
        product = ProductMaster(
            icon_status=IconStatus.READY.value,
            icon_seed=1,
            emoji_match=EmojiMatch.EXACT.value,
        )
        assert icon_library.is_markable(product) is False

    def test_a_cook_emoji_win_is_not_markable(self) -> None:
        product = ProductMaster(
            icon_status=IconStatus.READY.value,
            icon_seed=1,
            emoji_match=EmojiMatch.COOK.value,
        )
        assert icon_library.is_markable(product) is False


class TestMarkAndUnmarkCanonical:
    async def test_marking_a_markable_product_sets_the_timestamp(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        marked = await icon_library.mark_canonical(seeded_db, product.id)

        assert marked is not None
        assert marked.icon_canonical_at is not None

    async def test_marking_a_pending_product_refuses(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, icon_status=IconStatus.PENDING)

        with pytest.raises(icon_library.IconNotMarkable):
            await icon_library.mark_canonical(seeded_db, product.id)

    async def test_marking_a_library_icon_refuses(
        self, seeded_db: AsyncSession
    ) -> None:
        """A library icon's `icon_seed` is NULL - it is already in the library, nothing
        to curate."""
        product = await _product(seeded_db, icon_seed=None)

        with pytest.raises(icon_library.IconNotMarkable):
            await icon_library.mark_canonical(seeded_db, product.id)

    async def test_marking_an_exact_emoji_product_refuses(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db, emoji_match=EmojiMatch.EXACT)

        with pytest.raises(icon_library.IconNotMarkable):
            await icon_library.mark_canonical(seeded_db, product.id)

    async def test_marking_an_unknown_product_is_none(
        self, seeded_db: AsyncSession
    ) -> None:
        assert await icon_library.mark_canonical(seeded_db, uuid4()) is None

    async def test_unmarking_clears_the_timestamp(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)
        await icon_library.mark_canonical(seeded_db, product.id)

        unmarked = await icon_library.unmark_canonical(seeded_db, product.id)

        assert unmarked is not None
        assert unmarked.icon_canonical_at is None

    async def test_unmarking_a_never_marked_product_is_a_no_op(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)

        unmarked = await icon_library.unmark_canonical(seeded_db, product.id)

        assert unmarked is not None
        assert unmarked.icon_canonical_at is None

    async def test_unmarking_an_unknown_product_is_none(
        self, seeded_db: AsyncSession
    ) -> None:
        assert await icon_library.unmark_canonical(seeded_db, uuid4()) is None


class TestBuildBundle:
    def test_it_zips_each_icon_and_an_index_fragment(self) -> None:
        quark = ProductMaster(
            canonical_name="Quark",
            icon_image=FAKE_PNG,
            icon_seed=42,
        )

        data = icon_library.build_bundle([quark], host="test-host:17300")
        archive = zipfile.ZipFile(BytesIO(data))

        names = archive.namelist()
        assert "icon_library/quark.png" in names
        assert "index.json" in names
        assert archive.read("icon_library/quark.png") == FAKE_PNG
        index = json.loads(archive.read("index.json"))
        entry = index["quark"]
        assert entry["file"] == "quark.png"
        assert entry["sha256"] == hashlib.sha256(FAKE_PNG).hexdigest()
        assert entry["seed"] == 42
        assert entry["source"] == "curated:test-host:17300"

    def test_it_round_trips_through_apply_icon_bundle_into_lookup(
        self, tmp_path, monkeypatch
    ) -> None:
        """The bundle this builds is exactly what `apply_icon_bundle.py` expects, and the
        library it produces is exactly what `icon_library.lookup` serves."""
        from scripts import apply_icon_bundle

        quark = ProductMaster(canonical_name="Quark", icon_image=FAKE_PNG, icon_seed=42)
        data = icon_library.build_bundle([quark], host="test-host:17300")
        bundle_path = tmp_path / "bundle.zip"
        bundle_path.write_bytes(data)
        library_dir = tmp_path / "lib"

        apply_icon_bundle.apply_bundle(
            bundle_path,
            library_dir=library_dir,
            contact_sheet_path=tmp_path / "contact_sheet.png",
        )

        monkeypatch.setattr(icon_library, "_INDEX_PATH", library_dir / "index.json")
        icon_library._cache.cache_clear()
        assert icon_library.lookup("Quark") == FAKE_PNG
