"""The one place a name becomes a product id for writing (CL8, `docs/PRODUCT_IDENTITY_SPEC.md`).

Operator, 2026-10-06: "Get rid of fuzzy matching." Line ``KARJALANPAISTI`` got the generic
name "Karelian pie", selection picked the pie product, and confirm stocked the stew on it.
From here on a name joins an existing product only on an exact key:

- K1 a cook-verified alias at **this** chain for the normalised printed name;
- K2 a ``canonical`` or ``cook`` product name equal to the normalised printed name;
- K3 a ``cook`` product name equal to the normalised generic name;
- K4 an explicit product id the cook picked (the caller's, not decided here).

Everything else is at most a suggestion the cook has to accept, in this precedence:
``unverified_alias`` (this chain), ``other_chain_alias``, ``model_name``, ``selected`` (the
model's pick from a shortlist, made by `ProductResolution`), ``generic_name`` (the Q37 hit:
the generic name equals a catalog name that is not the cook's word).

Receipt resolution (`decide_line` through `ReceiptIdentity`), confirm, quick add and the
agents' stock add (`decide_name`) all come through here; `tests/test_layering.py` keeps
the name lookups (`product_for_name`, `known_names`) from being used anywhere else that
writes a join.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product_name import KnownName, known_names, product_for_name
from app.domain.product_names import normalize_product_name
from app.models.product_master import ProductMaster
from app.models.store_product_alias import StoreProductAlias
from app.services.matching_service import normalize_receipt_name

# Confirm stores aliases for a receipt with no chain under this key; reading uses the same.
UNKNOWN_CHAIN = "unknown"

KeySource = Literal["alias", "name"]
SuggestionReason = Literal[
    "unverified_alias", "other_chain_alias", "model_name", "selected", "generic_name"
]
# `inventory_item.join_source`: how an item came to be on its product (CHECK in alembic).
JoinSource = Literal[
    "created",
    "alias",
    "name",
    "cook_pick",
    "accepted_suggestion",
    "quick_add",
    "agent",
    "merge",
    "split",
    "legacy",
]
JOIN_SOURCES: tuple[str, ...] = (
    "created",
    "alias",
    "name",
    "cook_pick",
    "accepted_suggestion",
    "quick_add",
    "agent",
    "merge",
    "split",
    "legacy",
)


@dataclass(frozen=True)
class KeyJoin:
    """An exact key: the line or name is this product without asking."""

    product: ProductMaster
    source: KeySource
    key: str
    # Where the alias came from (K1 only), so confirm keeps its provenance.
    alias_source: str | None = None


@dataclass(frozen=True)
class Suggestion:
    """A product offered for the cook to accept; never joined by default."""

    product: ProductMaster
    reason: SuggestionReason
    # Only for `other_chain_alias`: the chain the alias was learned at.
    store_chain: str | None = None

    def as_dict(self) -> dict[str, Any]:
        blob: dict[str, Any] = {
            "product_id": str(self.product.id),
            "product_name": str(self.product.canonical_name),
            "reason": self.reason,
        }
        if self.store_chain is not None:
            blob["store_chain"] = self.store_chain
        return blob


def selected(product: ProductMaster) -> Suggestion:
    """The model's pick from a shortlist: a suggestion, never a product."""
    return Suggestion(product=product, reason="selected")


def _chain_key(chain: str | None) -> str:
    return chain or UNKNOWN_CHAIN


class ReceiptIdentity:
    """Keys and suggestions for one receipt's lines, loaded in three queries."""

    def __init__(
        self,
        chain: str | None,
        aliases: dict[str, list[StoreProductAlias]],
        products: dict[UUID, ProductMaster],
        names: dict[str, KnownName],
    ):
        self.chain = _chain_key(chain)
        self._aliases = aliases
        self._products = products
        self._names = names

    @classmethod
    async def load(
        cls,
        db: AsyncSession,
        lines: Iterable[tuple[str, str | None]],
        chain: str | None,
    ) -> "ReceiptIdentity":
        """``lines`` is ``(printed, generic)`` per line."""
        pairs = list(lines)
        keys = {normalize_receipt_name(printed) for printed, _ in pairs}
        keys.discard("")
        aliases: dict[str, list[StoreProductAlias]] = {}
        products: dict[UUID, ProductMaster] = {}
        if keys:
            rows = (
                (
                    await db.execute(
                        select(StoreProductAlias).where(
                            StoreProductAlias.receipt_name.in_(keys)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for alias in rows:
                aliases.setdefault(str(alias.receipt_name), []).append(alias)
            ids = {alias.product_master_id for alias in rows}
            if ids:
                products = {
                    product.id: product
                    for product in (
                        await db.execute(
                            select(ProductMaster).where(ProductMaster.id.in_(ids))
                        )
                    )
                    .scalars()
                    .all()
                }
        names = await known_names(db, [part for pair in pairs for part in pair if part])
        return cls(chain, aliases, products, names)

    def _best(self, aliases: Sequence[StoreProductAlias]) -> StoreProductAlias | None:
        """Verified first, then how often, then how recent; only with a product."""
        usable = [a for a in aliases if a.product_master_id in self._products]
        if not usable:
            return None
        return max(
            usable,
            key=lambda a: (
                1 if a.manually_verified else 0,
                int(a.occurrence_count or 0),
                a.last_seen,
            ),
        )

    def decide_line(
        self, printed: str, generic: str | None
    ) -> KeyJoin | Suggestion | None:
        """A key join, else the strongest suggestion, else nothing.

        ``selected`` is not decided here (it needs the model); it outranks only
        ``generic_name``, which `ProductResolution` therefore still sends to selection.
        """
        printed_key = normalize_receipt_name(printed)
        aliases = self._aliases.get(printed_key, [])
        here = self._best([a for a in aliases if str(a.store_chain) == self.chain])
        elsewhere = self._best([a for a in aliases if str(a.store_chain) != self.chain])

        # K1
        if here is not None and here.manually_verified:
            return KeyJoin(
                product=self._products[here.product_master_id],  # type: ignore[index]
                source="alias",
                key=printed_key,
                alias_source=str(here.source or "cook"),
            )

        printed_name = normalize_product_name(printed)
        named_printed = self._names.get(printed_name) if printed_name else None
        # K2
        if named_printed is not None and named_printed.source != "model":
            return KeyJoin(
                product=named_printed.product, source="name", key=printed_name
            )

        generic_name = normalize_product_name(generic)
        named_generic = self._names.get(generic_name) if generic_name else None
        # K3
        if named_generic is not None and named_generic.source == "cook":
            return KeyJoin(
                product=named_generic.product, source="name", key=generic_name
            )

        if here is not None:
            return Suggestion(
                product=self._products[here.product_master_id],  # type: ignore[index]
                reason="unverified_alias",
            )
        if elsewhere is not None:
            return Suggestion(
                product=self._products[elsewhere.product_master_id],  # type: ignore[index]
                reason="other_chain_alias",
                store_chain=str(elsewhere.store_chain),
            )
        if named_printed is not None:
            return Suggestion(product=named_printed.product, reason="model_name")
        if named_generic is not None:
            return Suggestion(product=named_generic.product, reason="generic_name")
        return None


async def decide_line(
    db: AsyncSession, printed: str, generic: str | None, chain: str | None
) -> KeyJoin | Suggestion | None:
    """`ReceiptIdentity.decide_line` for one line."""
    identity = await ReceiptIdentity.load(db, [(printed, generic)], chain)
    return identity.decide_line(printed, generic)


async def decide_name(db: AsyncSession, name: str | None) -> KeyJoin | None:
    """A typed name's key: a ``canonical`` or ``cook`` product name, never a model one.

    For quick add, the agents' stock add and confirm's ``name``. A name the model taught
    neither joins nor blocks.
    """
    key = normalize_product_name(name)
    if not key:
        return None
    product = await product_for_name(db, key, trust_model=False)
    if product is None:
        return None
    return KeyJoin(product=product, source="name", key=key)


__all__ = [
    "JOIN_SOURCES",
    "JoinSource",
    "KeyJoin",
    "ReceiptIdentity",
    "Suggestion",
    "SuggestionReason",
    "UNKNOWN_CHAIN",
    "decide_line",
    "decide_name",
    "selected",
]
