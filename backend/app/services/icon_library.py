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

The second half of this module (operator ask 2026-10-03, folded in) is icon *curation*:
on a develop build (`ICON_CURATION_ENABLED`), the cook marks a good generated icon
canonical on the product sheet, and `GET /api/icon-library/bundle.zip` zips every marked
icon into the library's own entry format - the bundle `scripts/apply_icon_bundle.py`
merges into the library above, ready for a PR. "The generated -> canonical should be a
feature of the 'develop' production build I use. ... during use more [icons] are
generated and some are re-generated and after that updated canonical [icons] can be
submitted to the repo."
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.models.product_master import EmojiMatch, IconStatus, ProductMaster
from app.services.icon_briefs import brief_for
from app.services.icon_subjects import subject_for
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


def library_count() -> int:
    """How many products the repo's icon library covers, for `GET /icon-library/status`."""
    return len(_cache())


# --- icon curation (operator ask 2026-10-03) -------------------------------------------------


def slug_for(name: str) -> str:
    """A filesystem-safe key for a product's PNG, from its normalised name.

    Shared between `scripts/export_icon_library.py` and `build_bundle` below - the two
    places that ever invent a library filename from a product name - so they can never
    drift into picking different ones for the same product.
    """
    text = normalize_product_name(name)
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "icon"


def index_entry(
    name: str,
    image: bytes,
    *,
    source: str,
    seed: int | None,
    subject: str | None,
    exported_at: datetime | None = None,
) -> dict[str, Any]:
    """One `index.json` entry, in the library's exact shape (see the module docstring's
    example). Shared by `scripts/export_icon_library.py` and `build_bundle` below, so an
    export and a curated bundle can never disagree on what an entry looks like.
    """
    return {
        "file": f"{slug_for(name)}.png",
        "sha256": hashlib.sha256(image).hexdigest(),
        "subject": subject,
        "seed": seed,
        "source": source,
        "exported_at": (exported_at or datetime.now(UTC)).isoformat(),
    }


def is_markable(product: ProductMaster) -> bool:
    """Whether "Keep as canonical" may be set on this product's current icon.

    Only an actually-rendered, currently-showing image qualifies: `icon_status` is
    `ready` (not pending, failed or cleared), `icon_seed` is not NULL (a render, not a
    library icon already applied here - a library icon is already in the library, nothing
    to curate), and no emoji wins the tile (an exact or cook emoji means the generated
    image could never show in the first place, same rule Regenerate already refuses on).
    """
    return bool(
        product.icon_status == IconStatus.READY
        and product.icon_seed is not None
        and product.emoji_match not in (EmojiMatch.EXACT, EmojiMatch.COOK)
    )


class IconNotMarkable(Exception):
    """ "Keep as canonical" was asked for a product whose icon cannot be marked - see
    `is_markable`."""


async def mark_canonical(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Mark this product's current icon canonical. None: no such product.

    Raises:
        IconNotMarkable: the icon is not a ready, actually-generated image with no
            emoji win (`is_markable`).
    """
    product = await crud_product.get_product(db, product_id)
    if product is None:
        return None
    if not is_markable(product):
        raise IconNotMarkable(
            "Only a ready, generated icon with no emoji win can be marked canonical"
        )
    await crud_product.mark_icon_canonical(db, product)
    return product


async def unmark_canonical(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Undo a mark. None: no such product. A no-op, not an error, if never marked."""
    product = await crud_product.get_product(db, product_id)
    if product is None:
        return None
    await crud_product.unmark_icon_canonical(db, product)
    return product


def build_bundle(products: list[ProductMaster], *, host: str) -> bytes:
    """Zip every marked product's icon as `icon_library/<slug>.png`, plus an `index.json`
    fragment in the library's exact entry format - what `scripts/apply_icon_bundle.py`
    merges into the repo's own library and index. `host` names this deployment
    (`source: "curated:<host>"`), the same shape `scripts/export_icon_library.py` uses
    for `generated:<host>`.

    Each product must carry its image (`crud.product_master.canonical_icons` undefers
    it) - this never touches the database itself.
    """
    index: dict[str, Any] = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for product in products:
            name = str(product.canonical_name)
            image = bytes(product.icon_image)
            seed = int(product.icon_seed) if product.icon_seed is not None else None
            entry = index_entry(
                name,
                image,
                source=f"curated:{host}",
                seed=seed,
                subject=brief_for(name) or subject_for(name),
            )
            archive.writestr(f"icon_library/{entry['file']}", image)
            index[normalize_product_name(name)] = entry
        archive.writestr(
            "index.json",
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    return buffer.getvalue()
