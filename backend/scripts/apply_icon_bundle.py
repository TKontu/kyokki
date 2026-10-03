"""Merge a curated icon bundle into the repo's icon library, ready for a PR.

Operator ruling (2026-10-03): "The generated -> canonical should be a feature of the
'develop' production build I use. ... during use more [icons] are generated and some are
re-generated and after that updated canonical [icons] can be submitted to the repo." On a
develop build (`ICON_CURATION_ENABLED`), the cook marks a good generated icon canonical on
the product sheet; Settings lists every marked product and downloads them as one bundle
(`GET /api/icon-library/bundle.zip`, `app.services.icon_library.build_bundle`). This script
is the repo side of that hand-off: it unzips the bundle's `icon_library/<slug>.png` files
and its `index.json` fragment, checks each entry's `sha256` against the bundle's own image
bytes (never trusts the zip blindly - a corrupted download must not silently poison the
library), and merges it into `app/resources/icon_library/` under the same normalised-name
keys the library already uses.

An entry already in the library is left alone unless `--replace` is given, the same
semantics `scripts/export_icon_library.py` uses - and for the same reason: a name clash is
worth a human looking at, not a silent overwrite. A real (non-dry-run) merge that actually
changed the library also regenerates `docs/icon_library/contact_sheet.png`, reusing
`export_icon_library`'s own writer rather than a second copy of it - the review step
described in `docs/icon_library/README.md` is the same whichever way an icon arrived.

    python -m scripts.apply_icon_bundle bundle.zip --dry-run
    python -m scripts.apply_icon_bundle bundle.zip
    python -m scripts.apply_icon_bundle bundle.zip --replace
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.export_icon_library import (
    CONTACT_SHEET_PATH,
    LIBRARY_DIR,
    _contact_sheet,
    load_index,
    save_index,
)


@dataclass
class ApplyResult:
    """What one merge found and did, for the CLI to print and the tests to assert on."""

    lines: list[str] = field(default_factory=list)
    eligible: int = 0
    applied: int = 0
    replaced: int = 0
    skipped_existing: int = 0
    skipped_bad_sha256: int = 0


def apply_bundle(
    bundle_path: Path,
    *,
    library_dir: Path = LIBRARY_DIR,
    index_path: Path | None = None,
    contact_sheet_path: Path = CONTACT_SHEET_PATH,
    replace: bool = False,
    dry_run: bool = False,
) -> ApplyResult:
    """Unzip `bundle_path` and merge it into the library. Writes nothing under `dry_run`.

    Never raises on a malformed bundle (no `index.json`, a non-object index, a missing
    image, a sha256 mismatch) - each such entry is reported in `result.lines` and skipped,
    same as a malformed `index.json` entry is at load time (`services/icon_library.py`).
    """
    if index_path is None:
        index_path = library_dir / "index.json"
    result = ApplyResult()
    applied_images: list[tuple[str, bytes]] = []
    index = load_index(index_path)

    with zipfile.ZipFile(bundle_path) as archive:
        try:
            raw_index = archive.read("index.json")
        except KeyError:
            result.lines.append("bundle has no index.json; nothing to apply")
            return result
        try:
            bundle_index: Any = json.loads(raw_index)
        except json.JSONDecodeError:
            result.lines.append(
                "bundle's index.json is not valid JSON; nothing to apply"
            )
            return result
        if not isinstance(bundle_index, dict):
            result.lines.append(
                "bundle's index.json is not an object; nothing to apply"
            )
            return result

        for key, entry in bundle_index.items():
            if not isinstance(key, str) or not isinstance(entry, dict):
                continue
            file_name = entry.get("file")
            expected_sha = entry.get("sha256")
            if not isinstance(file_name, str) or not isinstance(expected_sha, str):
                result.lines.append(f"skip (malformed entry)  {key}")
                continue
            result.eligible += 1
            try:
                image = archive.read(f"icon_library/{file_name}")
            except KeyError:
                result.lines.append(f"skip (missing image in bundle)  {key}")
                continue
            actual_sha = hashlib.sha256(image).hexdigest()
            if actual_sha != expected_sha:
                result.skipped_bad_sha256 += 1
                result.lines.append(f"skip (sha256 does not match)  {key}")
                continue

            already_in_library = key in index
            if already_in_library and not replace:
                result.skipped_existing += 1
                result.lines.append(f"skip (already in library)  {key}")
                continue
            if dry_run:
                result.lines.append(
                    f"would {'replace' if already_in_library else 'apply'}  {key}"
                )
                continue

            library_dir.mkdir(parents=True, exist_ok=True)
            (library_dir / file_name).write_bytes(image)
            index[key] = entry
            applied_images.append((key, image))
            if already_in_library:
                result.replaced += 1
                result.lines.append(f"replaced  {key}")
            else:
                result.applied += 1
                result.lines.append(f"applied  {key}")

    if not dry_run and applied_images:
        save_index(index, index_path)
        _contact_sheet(
            sorted(applied_images, key=lambda item: item[0]), contact_sheet_path
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument("bundle", help="path to the downloaded bundle.zip")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="overwrite a library entry that already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be applied; write nothing",
    )
    args = parser.parse_args(argv)

    result = apply_bundle(Path(args.bundle), replace=args.replace, dry_run=args.dry_run)
    for line in result.lines:
        print(f"  {line}")
    print(
        f"{result.eligible} eligible, {result.applied} applied, "
        f"{result.replaced} replaced, {result.skipped_existing} already in the library, "
        f"{result.skipped_bad_sha256} with a bad sha256"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
