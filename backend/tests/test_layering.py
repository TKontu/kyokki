"""The layering rule, checked on imports: endpoint -> service -> crud -> model.

- **No crud module imports a service.** `app/crud` is data access; `app/services` builds
  on it. A crud module reaching back up into a service inverts the layering and invites an
  import cycle.
- **`app/domain` imports no layer above the models.** It holds the pure rules - unit
  arithmetic (`units`), the item status machine (`item_status`), the category -> storage map
  (`storage`) and the product-name lookup key (`product_names`) - that both crud and the
  services need. Keeping it free of `app.services`, `app.crud` and `app.api` is what lets
  crud depend on it without depending on a service.

History: #167 removed the last `app.services.min_stock` calls from
`app/crud/inventory_item.py` and guarded only that module. Round 2026-10-04-1 (A2) moved
the remaining helpers crud imported (`item_status`, `units`, `product_names`, `storage`)
into `app/domain`, and the `product_name` table queries into `app/crud/product_name.py`,
so the guard now covers every `app.services` import. It left re-exports of those four
modules in `app/services` for their other importers; round 2026-10-04-2 moved every
importer to the real homes and deleted them, and a guard here keeps them deleted.

The check walks every import in the AST, so it catches `import app.services.x`,
`from app.services import x` and `from app.services.x import y` alike, at module level or
deferred inside a function - not only one textual spelling.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CRUD_DIR = BACKEND_ROOT / "app" / "crud"
DOMAIN_DIR = BACKEND_ROOT / "app" / "domain"


def _imported_modules(path: Path) -> set[str]:
    """Every dotted module (or `module.name`) this file imports, deferred or not."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                found.add(f"{node.module}.{alias.name}")
    return found


def _offenders(directory: Path, forbidden: tuple[str, ...]) -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for path in sorted(directory.rglob("*.py")):
        hits = {
            name
            for name in _imported_modules(path)
            if any(name == root or name.startswith(f"{root}.") for root in forbidden)
        }
        if hits:
            offenders[str(path.relative_to(BACKEND_ROOT))] = hits
    return offenders


def test_no_crud_module_imports_a_service() -> None:
    """No file under `app/crud` may import anything from `app.services`."""
    offenders = _offenders(CRUD_DIR, ("app.services",))
    assert offenders == {}, (
        "crud must not import from app.services (endpoint -> service -> crud -> "
        f"model): {offenders}"
    )


def test_domain_imports_no_service_crud_or_api() -> None:
    """`app/domain` exists and imports nothing from services, crud or api."""
    assert (DOMAIN_DIR / "__init__.py").is_file()
    offenders = _offenders(DOMAIN_DIR, ("app.services", "app.crud", "app.api"))
    assert offenders == {}, (
        f"app/domain must not import app.services, app.crud or app.api: {offenders}"
    )


REMOVED_SHIMS = ("units", "item_status", "storage", "product_names")


def test_the_removed_service_shims_stay_removed() -> None:
    """The `app.services` re-exports of the domain modules are gone, and nothing
    under `app/`, `scripts/` or `tests/` imports them: each name is imported from
    `app.domain.<module>` or `app.crud.product_name`, where it really lives."""
    restored = [
        name
        for name in REMOVED_SHIMS
        if (BACKEND_ROOT / "app" / "services" / f"{name}.py").exists()
    ]
    assert restored == [], f"app/services shims came back: {restored}"

    forbidden = tuple(f"app.services.{name}" for name in REMOVED_SHIMS)
    offenders: dict[str, set[str]] = {}
    for directory in ("app", "scripts", "tests"):
        offenders.update(_offenders(BACKEND_ROOT / directory, forbidden))
    assert offenders == {}, (
        f"import these from app.domain or app.crud.product_name instead: {offenders}"
    )


def test_inventory_item_crud_reports_instead_of_calling_the_service() -> None:
    """Regression guard for #167: neither `update_inventory_item` nor `move_many`
    mentions `min_stock` - they return which product lowered instead of calling the
    service to find out."""
    source = (CRUD_DIR / "inventory_item.py").read_text()
    assert "min_stock" not in source
