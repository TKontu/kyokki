"""The repo-shipped icon library (operator ask 2026-10-03): a loader over
`app/resources/icon_library/index.json` plus the PNGs beside it.

Read once and cached, exactly like `app.services.icon_subjects`; a sha256 mismatch or a
missing file is logged at WARNING and ignored rather than served.
"""

from __future__ import annotations

import hashlib
import json
import logging

import app.services.icon_library as icon_library
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
