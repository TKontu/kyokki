# Icon spike (Q18): attribution

## OpenMoji (`openmoji/`)

All emoji designs in `openmoji/` are from **OpenMoji**, the open-source emoji and icon
project. License: **CC BY-SA 4.0** (full text in `openmoji/LICENSE.txt`,
<https://creativecommons.org/licenses/by-sa/4.0/>).

> All emojis designed by OpenMoji – the open-source emoji and icon project. License: CC BY-SA 4.0

- Source: <https://openmoji.org>, <https://github.com/hfg-gmuend/openmoji>, npm package
  `openmoji@17.0.0` (fetched from cdn.jsdelivr.net on 2026-09-26).
- Subset: the 144 icons of the `food-drink` group (without its `dishware` subgroup) and the
  food and drink extras of `extras-openmoji` / `extras-unicode`. Files are the colour SVGs,
  named by their hexcode.
- Changes: XML comments and whitespace between tags removed (`backend/scripts/icon_spike.py
  --route vendor`); the drawings themselves are unmodified.
- `openmoji/index.json` keeps each icon's emoji, annotation and tags from OpenMoji's
  `data/openmoji.json` (same licence).

Any adaptation of these icons must be shared under CC BY-SA 4.0, with this attribution.

## Contact sheets (`screenshots/`)

Raster renders (resvg) of the picked OpenMoji icons next to the generated ones, for the spike
write-up. The OpenMoji parts are OpenMoji designs, CC BY-SA 4.0, attributed as above.

## Generated icons (`generated/`)

Drawn by the model `c2.qwen3.8-27b` on the homelab gateway for this spike, then sanitised.
No third-party material.
