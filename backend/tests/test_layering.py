"""No crud module imports a service (A4): endpoint -> service -> crud -> model.

Two call sites used to break this - `update_inventory_item` and `move_many` in
`app/crud/inventory_item.py` each deferred an `import app.services.min_stock` inside
the function, to call `after_stock_decrease` directly once their own commit had
landed. Both now report which product their change lowered (a return value) and leave
the auto-add check itself to their callers - the `PATCH /inventory/{id}` and
`POST /inventory/discard` endpoints - exactly as `consume_inventory_item` already did.

This guards the regression with an AST check over every import in `app/crud`, so it
catches `import app.services.min_stock`, `from app.services import min_stock` and
`from app.services.min_stock import ...` alike, module-level or deferred inside a
function - not only a text grep for the one spelling this round happened to use.

Scoped to `app.services.min_stock` specifically, rather than every `app.services`
import: `app/crud/inventory_item.py` and `app/crud/product_master.py` already import a
few service-layer helpers (`item_status`, `units`, `product_names`, `storage`) that
predate this fix and are out of this assignment's scope (file ownership; A4's own task
list names only the two min-stock call sites as the violation to fix).
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CRUD_DIR = BACKEND_ROOT / "app" / "crud"


def _imported_service_modules(path: Path) -> set[str]:
    """Every dotted `app.services...` name this file imports, deferred or not."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.services"):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and (
            node.module and node.module.startswith("app.services")
        ):
            for alias in node.names:
                found.add(f"{node.module}.{alias.name}")
    return found


def test_no_crud_module_imports_the_min_stock_service() -> None:
    """The layering inversion A4 fixes: no file under `app/crud` may import
    `app.services.min_stock`, at module level or deferred inside a function."""
    offenders: dict[str, set[str]] = {}
    for path in sorted(CRUD_DIR.rglob("*.py")):
        hits = {
            name
            for name in _imported_service_modules(path)
            if name == "app.services.min_stock"
            or name.startswith("app.services.min_stock.")
        }
        if hits:
            offenders[str(path.relative_to(BACKEND_ROOT))] = hits

    assert offenders == {}, (
        "crud must not import the min_stock service (endpoint -> service -> crud -> "
        f"model): {offenders}"
    )


def test_inventory_item_crud_reports_instead_of_calling_the_service() -> None:
    """Direct regression guard for the exact two call sites this round fixed: neither
    `update_inventory_item` nor `move_many` mentions `min_stock` any more - they return
    which product lowered instead of calling the service to find out."""
    source = (CRUD_DIR / "inventory_item.py").read_text()
    assert "min_stock" not in source
