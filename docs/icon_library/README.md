# The icon library

Operator request (2026-10-03): "migrate the generated icons to the actual repo as
canonical symbols." Today every deployment must render its own product icons on a GPU
through ComfyUI (`backend/app/services/product_icons.py`), and the good ones exist only
in that deployment's own database. The icon library is a repo-shipped folder of reviewed
PNGs, keyed by product name, that any deployment can use instantly - no GPU, and it works
with `COMFYUI_BASE_URL` empty.

## What it is

- `backend/app/resources/icon_library/<slug>.png` - one reviewed icon per product.
- `backend/app/resources/icon_library/index.json` - maps the product's normalised
  canonical name (casefolded, whitespace collapsed - the same key
  `app.services.icon_subjects` uses) to:
  ```json
  {
    "file": "quark.png",
    "sha256": "<the file's own hash>",
    "subject": "a tub of smooth white soft cheese with a spoon in it",
    "seed": 123456789,
    "source": "generated:192.168.0.136:17300",
    "exported_at": "2026-10-03T12:00:00+00:00"
  }
  ```
- `backend/app/services/icon_library.py` - the loader: reads the index once, checks each
  file's `sha256` against it (a mismatch is ignored and logged at WARNING, never served),
  and caches the result. `lookup(name)` is the only thing callers use.

A library entry is matched by a product's **canonical name only** - never a display name,
a receipt alias, or a model-taught synonym. Those are not identity; the canonical name is.

## Precedence

Cook or exact emoji wins the tile first, same as always
(`frontend/lib/productIcon.ts`). After that:

1. **The library.** A gap product (no emoji win) whose name matches a library entry gets
   that icon, with no ComfyUI call, the moment it is scheduled - on create, and on a
   rename (`services/product_icons.py`'s `draw_icons`, before it even looks at whether
   `COMFYUI_BASE_URL` is set).
2. **A generated icon already in place is never overwritten automatically.** Once a
   product has actually been rendered (`icon_seed` is not NULL - no migration needed,
   that NULL-ness is the marker), the library leaves it alone.
3. **Cleared stays cleared.** A product the cook chose to show with the category emoji
   (`icon_status: cleared`) is not given a library icon behind their back.
4. **Regenerate always renders.** The cook asking for a fresh image bypasses the library
   entirely, even for a product the library would otherwise cover - that is what asking
   for a new one means.

`backend/scripts/backfill_icons.py` applies the same precedence for existing products:
a library pass runs first (`--dry-run` reports "would apply from library" separately from
"would generate"), and `--library-only` applies only what the library covers, with no
ComfyUI involved at all.

## Export

`backend/scripts/export_icon_library.py` pulls good icons out of a deployment's database,
through its own API - **GET only**, it never mutates the deployment:

```bash
python -m scripts.export_icon_library --api http://192.168.0.136:17300 --all-ready --dry-run
python -m scripts.export_icon_library --api http://192.168.0.136:17300 --all-ready
python -m scripts.export_icon_library --api http://192.168.0.136:17300 --names "Quark,Leek"
python -m scripts.export_icon_library --api http://192.168.0.136:17300 --all-ready --replace
```

It picks food products whose icon is `ready`, not an emoji win, and actually generated
(`icon_seed` not null) - a `ready` icon is never shown for a non-food product in the first
place, so nothing extra needs checking there. Without `--replace`, a name already in the
library is skipped. Each eligible product's icon is downloaded
(`GET /api/products/{id}/icon.png`), written as `<slug>.png`, and added to `index.json`
with its subject (from the API if it ever returns one, otherwise the operator's own brief
or the cached Q18 visual subject) and seed. `source` records which deployment it came
from (`generated:<host>`).

A real (non-dry-run) export that wrote at least one icon also writes a **contact
sheet**, `docs/icon_library/contact_sheet.png` - a grid of every icon just exported, its
product name underneath.

## Curation (in the app)

Operator ruling (2026-10-03): "The generated -> canonical should be a feature of the
'develop' production build I use. ... during use more [icons] are generated and some are
re-generated and after that updated canonical [icons] can be submitted to the repo." This
is the other way an icon reaches the library - from the cook's own use of the app, not a
one-off export run - and it needs no API access to a remote deployment: it runs on the
build the cook already has open.

1. Set `ICON_CURATION_ENABLED=true` on the develop build (`.env.example`; false
   everywhere else). The product sheet then shows a **Keep as canonical** toggle on any
   product whose icon is a ready, actually-generated image with no emoji win - an exact
   or cook emoji, a pending or failed render, or a library icon already applied here are
   never markable, since there is nothing of the cook's own to curate on any of them. A
   fresh render (Regenerate, or a rename's own) or a clear drops the mark in the same
   write that changes the image - a mark is only ever about the image actually showing.
2. Use the app as usual. More icons get generated and some get regenerated; mark the
   good ones as they come up.
3. Open Settings' "Canonical icons" section (shown only when curation is enabled): it
   lists every marked product and has **Download bundle**
   (`GET /api/icon-library/bundle.zip`) - every marked icon as `icon_library/<slug>.png`
   plus an `index.json` fragment in the library's exact entry format
   (`source: "curated:<host>"`).
4. In a checkout of this repo, apply the downloaded bundle:
   ```bash
   python -m scripts.apply_icon_bundle bundle.zip --dry-run
   python -m scripts.apply_icon_bundle bundle.zip
   ```
   This checks each entry's `sha256` against its image before ever writing it, merges it
   into `app/resources/icon_library/` under the library's own normalised-name keys
   (an entry already there is left alone unless `--replace` is given, the same as the
   export script), and regenerates `docs/icon_library/contact_sheet.png`.
5. Open a PR with the result - the same review step as an export (below): look at the
   contact sheet, drop anything wrong, merge.

## Review

The export's PR **is** the operator's approval step:

1. Open the contact sheet and look at every icon on it.
2. For any icon that is wrong, delete its `<slug>.png` file and its `index.json` entry
   from the diff before merging - nothing else needs to change.
3. Merge once satisfied.

## Apply

Once merged, every deployment already has the new entries built in - nothing to run. For
a deployment with existing gap products that predate the library entry (or that never had
`COMFYUI_BASE_URL` configured), run the backfill's library pass:

```bash
python -m scripts.backfill_icons --library-only
```

This needs no ComfyUI and touches only products the library actually covers; anything
left over is reported as skipped, same as any other gap product with no match.
