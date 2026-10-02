"""Q18 subjects: cached visual descriptions for the generated-icon gap.

SDXL draws the *word*, not the food (`docs/spikes/Q18_icon_styles.md`,
`docs/spikes/q18_g2_live/README.md`): "Fish fingers" reads as a whole fish, "Karelian
pasty" reads as a pie wedge, "Quark" is unknown. For most gap products
(`app.services.icon_briefs` has the operator's own words for the four it was asked
about), the fix is a short *visual* description - shape, colour, packaging, how it is
served - instead of the bare product name, so the model has something to draw other
than the word itself.

That description is asked of the LLM gateway once per product
(`scripts/propose_icon_subjects.py`, reviewed by the operator before it is applied) and
cached here, in `app/resources/icon_subjects.json`, so a render never waits on a live LLM
call. This module only reads that file; nothing here ever calls the gateway.

Looked up the same way `icon_briefs.brief_for` is: casefolded, whitespace collapsed
(`app.services.product_names.normalize_product_name`), so "fish fingers" and " Fish
Fingers " are the same entry. `app.services.product_icons.icon_subject` is the only
caller, and the operator's own brief always wins over this cache there.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.services.product_names import normalize_product_name

_PATH = Path(__file__).resolve().parent.parent / "resources" / "icon_subjects.json"


@lru_cache(maxsize=1)
def _cache() -> dict[str, str]:
    try:
        raw = json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        normalize_product_name(name): text
        for name, text in raw.items()
        if isinstance(text, str) and text.strip()
    }


def subject_for(generic_name: str) -> str | None:
    """The cached visual description for this gap product, if the LLM was ever asked."""
    return _cache().get(normalize_product_name(generic_name))
