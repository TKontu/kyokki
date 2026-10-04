"""Re-exports: the key is in `app.domain.product_names`, the queries in `app.crud.product_name`.

The key half of `docs/PRODUCT_RESOLUTION_SPEC.md`: a line resolves to a product through an
exact key, never through a similarity score. Kept as the public path its existing importers
use (round 2026-10-04-1 moved the code down so crud no longer imports a service).
"""

from app.crud.product_name import (
    CanonicalName,
    KnownName,
    UnknownName,
    forget_product_name,
    known_names,
    learn_product_name,
    names_for_product,
    product_for_name,
)
from app.domain.product_names import normalize_product_name

__all__ = [
    "CanonicalName",
    "KnownName",
    "UnknownName",
    "forget_product_name",
    "known_names",
    "learn_product_name",
    "names_for_product",
    "normalize_product_name",
    "product_for_name",
]
