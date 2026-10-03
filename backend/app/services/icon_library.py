"""The repo-shipped icon library (operator ask 2026-10-03): reviewed PNGs keyed by a
product's canonical name, exported from good icons a deployment already generated.

Today every deployment must render its own icons on a GPU through ComfyUI
(`services/product_icons.py`), and the good ones exist only in that deployment's own
database. This library closes that gap: a product whose name matches a library entry
gets its icon instantly - no GPU, and it works with `COMFYUI_BASE_URL` empty, in any
deployment. See `docs/icon_library/README.md` for what the library is and how an entry
gets into it (`scripts/export_icon_library.py`, reviewed by the operator in the PR before
it ever merges - a contact sheet is part of that review, not this module's job).

Looked up by `app.services.product_names.normalize_product_name`, the same key
`app.services.icon_subjects.subject_for` uses: casefolded, whitespace collapsed.
Synonyms are not used here - a display name or a model-taught alias is not identity,
only the product's own canonical name is, exactly as `icon_subjects` already treats it.

Read once and cached (`app/resources/icon_library/index.json` plus the PNGs beside it).
Each entry's `sha256` is checked against its file at load time: a mismatch (a corrupted
file, or one edited by hand without updating the index) is logged at WARNING and ignored
rather than served - a tile must never show an unreviewed image.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from app.core.logging import get_logger
from app.services.product_names import normalize_product_name

logger = get_logger(__name__)

_DIR = Path(__file__).resolve().parent.parent / "resources" / "icon_library"
_INDEX_PATH = _DIR / "index.json"


@lru_cache(maxsize=1)
def _cache() -> dict[str, bytes]:
    try:
        raw = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    cache: dict[str, bytes] = {}
    base_dir = _INDEX_PATH.parent
    for name, entry in raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        file_name = entry.get("file")
        expected_sha = entry.get("sha256")
        if not isinstance(file_name, str) or not isinstance(expected_sha, str):
            logger.warning(
                "Icon library entry is missing file or sha256; ignoring it",
                extra={"product": name},
            )
            continue
        path = base_dir / file_name
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            logger.warning(
                "Icon library entry's file is missing; ignoring it",
                extra={"product": name, "file": file_name},
            )
            continue
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha:
            logger.warning(
                "Icon library entry's sha256 does not match its file; ignoring it",
                extra={"product": name, "file": file_name},
            )
            continue
        cache[normalize_product_name(name)] = data
    return cache


def lookup(name: str) -> bytes | None:
    """The library's PNG for this normalised product name, or None.

    Never raises on a missing or malformed library - an empty one (nothing exported
    yet, or a corrupted index) simply answers None for everything, same as a missing
    `icon_subjects.json` answers no cached subject.
    """
    return _cache().get(normalize_product_name(name))
