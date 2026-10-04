"""A pre-existing circular import (round 2026-09-30-1).

The category -> storage map (then in `services/storage.py`, now `app.domain.storage`)
imports `app.schemas.inventory_item` (`StorageLocation`), and `app.schemas.category`
imports the map (`StorageType`, `storage_type_for_category`). `app.schemas` (the package
`__init__`) imports `app.schemas.category` before `app.schemas.inventory_item`, so
importing either module *first*, in a fresh interpreter, used to fail with an ImportError
cycle - which is exactly what happened running the storage tests alone. Once something
else has already imported `app.schemas` in full (as the rest of the suite does via
fixtures), the cycle is masked, so this needs a fresh subprocess to catch.

`app.main` and `app.worker.receipt_worker` are the two production entry points that import
`app.schemas` (directly or by importing the routers/services that do), so they are the ones
a regression through them would actually have to pass - the two narrower modules above
could stay fixed in isolation while a production entry point still failed.

Round 2026-10-04-1 moved the storage, units and item-status code into `app.domain`, and the
`product_name` queries into `app.crud.product_name`, so those modules are each imported
first in a fresh interpreter too. `app.domain.storage` keeps the lazy `StorageLocation`
resolution described above. Round 2026-10-04-2 deleted the `app/services` re-exports that
round left behind, so they are no longer listed (`tests/test_layering.py` keeps them out).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module",
    [
        "app.domain.units",
        "app.domain.item_status",
        "app.domain.storage",
        "app.domain.product_names",
        "app.crud.product_name",
        "app.schemas.category",
        "app.main",
        "app.worker.receipt_worker",
    ],
)
def test_imports_cleanly_in_a_fresh_interpreter(module: str) -> None:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{BACKEND_ROOT}{os.pathsep}{existing}" if existing else str(BACKEND_ROOT)
    )

    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
