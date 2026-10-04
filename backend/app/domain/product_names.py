"""The product-name lookup key, the pure half of `app.services.product_names`.

A line resolves to a product through an exact key, never through a similarity score
(`docs/PRODUCT_RESOLUTION_SPEC.md`). This module owns the key format; the queries on the
`product_name` table live in `app.crud.product_name`.
"""


def normalize_product_name(name: str | None) -> str:
    """The lookup key: casefolded, whitespace collapsed.

    Deliberately gentler than `normalize_receipt_name`, which also strips a trailing
    price because it keys *printed* names. These are catalog names.
    """
    return " ".join((name or "").split()).casefold()
