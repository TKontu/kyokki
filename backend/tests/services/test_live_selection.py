"""The reported pairs (Q14) put to the real model. Deselected by default (pytest.ini).

    pytest tests/services/test_live_selection.py -m requires_vllm -v

The deterministic half of H53 - that the right product is on the shortlist - is pinned in
`test_product_resolution.py` against the same fixture. This half asks whether the model,
given that shortlist, picks it, and says null when the right product is not in the catalog.
It calls `product_selection.select_products` directly, so the autouse patch on the
resolver's import does not apply.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.product_selection import SelectionLine, select_products

CASES = json.loads(
    (
        Path(__file__).parent.parent / "fixtures" / "resolution" / "reported_pairs.json"
    ).read_text(encoding="utf-8")
)["cases"]


@pytest.mark.requires_vllm
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
async def test_the_model_picks_the_same_thing_or_nothing(case) -> None:
    ids = {name: str(uuid4()) for name, _ in case["catalog"]}
    line = SelectionLine(
        line_id="l1",
        printed=case["printed"],
        generic=case["generic"],
        category=case["category"],
        candidate_ids=tuple(ids.values()),
        candidate_names=tuple(ids),
    )

    chosen = await select_products([line])

    picked = next((n for n, i in ids.items() if str(chosen.get("l1")) == i), None)
    assert picked == case["answer"]
