"""Which products may hold items that were joined to them wrongly (CL8 L4). Read-only.

A wrong join happens when a receipt line lands on an existing product without an exact key
(`docs/PRODUCT_IDENTITY_SPEC.md`, paths P1-P9). In production, "Karelian stew" holds the stew
line `KARJALANPAISTI` (a model pick) and the rice-pie lines `VUOKSEN RIISIPIIRAKKA 15KPL`.
This module lists such products for the cook to review and split; it decides nothing and
writes nothing - every query here is a SELECT, and nothing is added, flushed or committed.

A product is flagged when:
  (i) its receipt-born items came in under two or more printed names (grouped by chain and
      normalised printed text) and any group joined without an exact key: a model pick
      (`selected`), no match at read time but a product at confirm (`none`, the P4 suspect),
      an unverified or model alias, or an alias learned at another chain; or
  (ii) the lines' generic names differ beyond normalisation.
Flagged products are ranked by the lowest similarity between their printed groups, least
alike first. The similarity only orders the list.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from typing import Any, cast
from uuid import UUID

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.product_names import normalize_product_name
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import NameSource, ProductName
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.schemas.inventory_item import InventoryStatus
from app.schemas.product_audit import (
    AuditedProduct,
    AuditModelName,
    AuditPrintedGroup,
    AuditUnverifiedAlias,
    ProductJoinAudit,
)
from app.services.matching_service import normalize_receipt_name

USED_UP = {InventoryStatus.EMPTY.value, InventoryStatus.DISCARDED.value}
# A stored line with no `match_source` resolved to nothing at read time.
NO_MATCH = "none"
# An item whose receipt line can no longer be found: how it joined is unknown.
UNKNOWN = "unknown"


@dataclass
class _Group:
    chain: str | None
    label: str
    sources: set[str] = field(default_factory=set)
    generic_names: dict[str, str] = field(default_factory=dict)  # normalised -> as read
    suspicions: set[str] = field(default_factory=set)
    active: int = 0
    total: int = 0
    first: date | None = None
    last: date | None = None

    def add_date(self, seen: date | None) -> None:
        if seen is None:
            return
        self.first = seen if self.first is None else min(self.first, seen)
        self.last = seen if self.last is None else max(self.last, seen)


@dataclass
class _Product:
    name: str
    groups: dict[tuple[str | None, str], _Group] = field(default_factory=dict)


def _stored_lines(receipt: Receipt) -> list[Any]:
    structured = receipt.ocr_structured
    if not isinstance(structured, dict):
        return []
    lines = structured.get("lines")
    if not isinstance(lines, list):
        lines = structured.get("items")
    return lines if isinstance(lines, list) else []


def _line_for(item: InventoryItem, lines: list[Any]) -> dict[str, Any] | None:
    """The stored line the item was confirmed from, if it still reads as the same line."""
    index = cast("int | None", item.receipt_line_index)
    if index is None or not 0 <= index < len(lines):
        return None
    line = lines[index]
    if not isinstance(line, dict) or not line.get("name"):
        return None
    text = cast("str | None", item.receipt_line_text)
    if text and normalize_receipt_name(text) != normalize_receipt_name(
        str(line["name"])
    ):
        return None  # the receipt was re-read since; this position is another line
    return line


def _line_verified(line: dict[str, Any]) -> bool:
    if line.get("verified"):
        return True
    resolution = line.get("resolution")
    return isinstance(resolution, dict) and bool(resolution.get("verified"))


def _alias_source(line: dict[str, Any]) -> str | None:
    resolution = line.get("resolution")
    if isinstance(resolution, dict) and resolution.get("alias_source"):
        return str(resolution["alias_source"])
    return None


def _suspicions(
    line: dict[str, Any] | None,
    source: str,
    chain: str | None,
    label: str,
    product_id: UUID,
    aliases: dict[tuple[str, str], StoreProductAlias],
    alias_chains: dict[tuple[str, UUID], set[str]],
) -> set[str]:
    """Why this item's join was not an exact key, if it was not."""
    if source == "selected":
        return {"picked by the model (selected)"}
    if source == NO_MATCH:
        return {"no match when read, joined at confirm (P4 suspect)"}
    if source != "alias" or line is None:
        return set()

    found: set[str] = set()
    here = aliases.get((chain or "", label))
    here_is_ours = here is not None and here.product_master_id == product_id
    elsewhere = alias_chains.get((label, product_id), set()) - {chain or ""}
    if not here_is_ours and elsewhere:
        found.add(f"cross-chain alias (learned at {', '.join(sorted(elsewhere))})")
    verified = _line_verified(line) or (
        here_is_ours and bool(cast(Any, here).manually_verified)
    )
    if not verified:
        found.add(
            "model alias" if _alias_source(line) == "model" else "unverified alias"
        )
    return found


def _min_similarity(labels: list[str]) -> float | None:
    if len(labels) < 2:
        return None
    return round(
        min(fuzz.ratio(a, b) / 100 for a, b in combinations(labels, 2)),
        3,
    )


async def _receipt_items(
    db: AsyncSession,
) -> list[tuple[InventoryItem, Receipt, str]]:
    rows = await db.execute(
        select(InventoryItem, Receipt, ProductMaster.canonical_name)
        .join(Receipt, InventoryItem.receipt_id == Receipt.id)
        .join(ProductMaster, InventoryItem.product_master_id == ProductMaster.id)
        .order_by(InventoryItem.created_at, InventoryItem.id)
    )
    return [(item, receipt, str(name)) for item, receipt, name in rows.all()]


async def _flagged_products(
    db: AsyncSession, aliases: list[StoreProductAlias]
) -> list[AuditedProduct]:
    by_key = {
        (str(alias.store_chain), str(alias.receipt_name)): alias for alias in aliases
    }
    alias_chains: dict[tuple[str, UUID], set[str]] = defaultdict(set)
    for alias in aliases:
        alias_chains[
            (str(alias.receipt_name), cast(UUID, alias.product_master_id))
        ].add(str(alias.store_chain))

    products: dict[UUID, _Product] = {}
    for item, receipt, product_name in await _receipt_items(db):
        lines = _stored_lines(receipt)
        line = _line_for(item, lines)
        printed = (
            str(line["name"]) if line else cast("str | None", item.receipt_line_text)
        )
        label = normalize_receipt_name(printed or "")
        if not label:
            continue  # confirmed before items recorded their line (Q26)

        product_id = cast(UUID, item.product_master_id)
        chain = cast("str | None", receipt.store_chain)
        product = products.setdefault(product_id, _Product(name=product_name))
        group = product.groups.setdefault((chain, label), _Group(chain, label))

        source = UNKNOWN
        if line is not None:
            source = str(line.get("match_source") or NO_MATCH)
            generic = line.get("generic_name")
            if isinstance(generic, str) and normalize_product_name(generic):
                group.generic_names.setdefault(normalize_product_name(generic), generic)
        group.sources.add(source)
        group.suspicions |= _suspicions(
            line, source, chain, label, product_id, by_key, alias_chains
        )
        group.total += 1
        if str(item.status) not in USED_UP:
            group.active += 1
        created = cast("Any", item.created_at)
        group.add_date(
            cast("date | None", item.purchase_date)
            or cast("date | None", receipt.purchase_date)
            or (created.date() if created is not None else None)
        )

    flagged: list[AuditedProduct] = []
    for product_id, product in products.items():
        groups = sorted(
            product.groups.values(),
            key=lambda g: (g.first or date.max, g.label, g.chain or ""),
        )
        reasons: list[str] = []
        if len(groups) >= 2:
            for group in groups:
                for why in sorted(group.suspicions):
                    reasons.append(
                        f"{group.label} ({group.chain or 'no chain'}): {why}"
                    )
        generics: dict[str, str] = {}
        for group in groups:
            for key, as_read in group.generic_names.items():
                generics.setdefault(key, as_read)
        if len(generics) >= 2:
            reasons.append(
                f"generic names differ: {', '.join(sorted(generics.values()))}"
            )
        if not reasons:
            continue
        flagged.append(
            AuditedProduct(
                product_id=product_id,
                product_name=product.name,
                groups=[
                    AuditPrintedGroup(
                        label=g.label,
                        store_chain=g.chain,
                        match_sources=sorted(g.sources),
                        generic_names=sorted(g.generic_names.values()),
                        active_count=g.active,
                        total_count=g.total,
                        first_seen=g.first,
                        last_seen=g.last,
                    )
                    for g in groups
                ],
                reasons=reasons,
                min_similarity=_min_similarity([g.label for g in groups]),
            )
        )

    flagged.sort(
        key=lambda p: (
            p.min_similarity is None,
            p.min_similarity or 0.0,
            p.product_name,
        )
    )
    return flagged


async def _model_names(db: AsyncSession) -> list[AuditModelName]:
    item_counts = (
        select(
            InventoryItem.product_master_id.label("product_id"),
            func.count(InventoryItem.id).label("item_count"),
        )
        .group_by(InventoryItem.product_master_id)
        .subquery()
    )
    rows = await db.execute(
        select(ProductName, ProductMaster.canonical_name, item_counts.c.item_count)
        .join(ProductMaster, ProductName.product_master_id == ProductMaster.id)
        .outerjoin(item_counts, item_counts.c.product_id == ProductMaster.id)
        .where(ProductName.source == NameSource.MODEL.value)
        .order_by(ProductMaster.canonical_name, ProductName.name)
    )
    return [
        AuditModelName(
            id=cast(UUID, name.id),
            name=str(name.name),
            product_id=cast(UUID, name.product_master_id),
            product_name=str(product_name),
            item_count=int(items or 0),
            created_at=cast("Any", name.created_at),
        )
        for name, product_name, items in rows.all()
    ]


async def _aliases(db: AsyncSession) -> list[tuple[StoreProductAlias, str]]:
    rows = await db.execute(
        select(StoreProductAlias, ProductMaster.canonical_name)
        .join(ProductMaster, StoreProductAlias.product_master_id == ProductMaster.id)
        .order_by(
            StoreProductAlias.occurrence_count.desc(),
            StoreProductAlias.store_chain,
            StoreProductAlias.receipt_name,
        )
    )
    return [(alias, str(name)) for alias, name in rows.all()]


async def audit_product_joins(db: AsyncSession) -> ProductJoinAudit:
    """Every product whose items may have been joined wrongly, plus the unconfirmed keys.

    Read-only: only SELECTs run on `db`; the caller's session is left as it was found.
    """
    aliases = await _aliases(db)
    return ProductJoinAudit(
        products=await _flagged_products(db, [alias for alias, _ in aliases]),
        model_names=await _model_names(db),
        unverified_aliases=[
            AuditUnverifiedAlias(
                id=cast(UUID, alias.id),
                store_chain=str(alias.store_chain),
                receipt_name=str(alias.receipt_name),
                product_id=cast(UUID, alias.product_master_id),
                product_name=product_name,
                source=str(alias.source),
                occurrence_count=int(alias.occurrence_count or 0),
                last_seen=cast("Any", alias.last_seen),
            )
            for alias, product_name in aliases
            if not alias.manually_verified
        ],
    )
