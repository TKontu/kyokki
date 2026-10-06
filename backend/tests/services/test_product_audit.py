"""CL8 L4: the read-only audit of products whose items came in through suspicious joins.

The production shape (docs/PRODUCT_IDENTITY_SPEC.md): one product, renamed "Karelian stew",
holds the stew line `KARJALANPAISTI` (joined by a model pick, `selected`) and the rice-pie
lines `VUOKSEN RIISIPIIRAKKA 15KPL` from two receipts (joined by alias).
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.services.product_audit import audit_product_joins

STEW = "KARJALANPAISTI"
RICE_PIE = "VUOKSEN RIISIPIIRAKKA 15KPL"


@pytest.fixture
async def db(seeded_db: AsyncSession) -> AsyncSession:
    return seeded_db


async def _product(db: AsyncSession, name: str) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="count",
        default_unit="pcs",
        default_quantity=Decimal("1"),
    )
    db.add(product)
    await db.flush()
    return product


def line(
    name: str,
    product: ProductMaster | None,
    *,
    source: str | None,
    generic: str,
    verified: bool = False,
    alias_source: str | None = None,
) -> dict[str, Any]:
    """A stored receipt line as `receipt_processing` writes it."""
    resolution: dict[str, Any] = {
        "product_id": str(product.id) if product else None,
        "source": source or "none",
        "verified": verified,
        "candidates": [],
    }
    if alias_source is not None:
        resolution["alias_source"] = alias_source
    return {
        "name": name,
        "generic_name": generic,
        "line_id": str(uuid4()),
        "product_id": str(product.id) if product else None,
        "product_name": str(product.canonical_name) if product else None,
        "match_source": source,
        "resolution": resolution,
    }


async def _receipt(
    db: AsyncSession,
    chain: str,
    purchased: date,
    stocked: list[tuple[dict[str, Any], ProductMaster]],
    *,
    status: str = "sealed",
) -> Receipt:
    """A confirmed receipt whose every line was stocked onto the given product."""
    receipt = Receipt(
        id=uuid4(),
        store_chain=chain,
        purchase_date=purchased,
        image_path="data/receipts/none.jpg",
        processing_status="confirmed",
        ocr_structured={"lines": [stored for stored, _ in stocked]},
    )
    db.add(receipt)
    await db.flush()
    for index, (stored, product) in enumerate(stocked):
        db.add(
            InventoryItem(
                product_master_id=product.id,
                receipt_id=receipt.id,
                receipt_line_index=index,
                receipt_line_text=stored["name"],
                initial_quantity=Decimal("1"),
                current_quantity=Decimal("1"),
                unit="pcs",
                status=status,
                purchase_date=purchased,
                expiry_date=purchased,
            )
        )
    await db.flush()
    return receipt


def _alias(
    product: ProductMaster,
    chain: str,
    receipt_name: str,
    *,
    verified: bool,
    source: str = "cook",
    count: int = 1,
) -> StoreProductAlias:
    return StoreProductAlias(
        product_master_id=product.id,
        store_chain=chain,
        receipt_name=receipt_name,
        source=source,
        manually_verified=verified,
        occurrence_count=count,
    )


async def _production_case(db: AsyncSession) -> ProductMaster:
    stew = await _product(db, "Karelian stew")
    db.add(_alias(stew, "s-group", RICE_PIE, verified=True, count=2))
    await _receipt(
        db,
        "s-group",
        date(2026, 9, 30),
        [
            (
                line(
                    RICE_PIE,
                    stew,
                    source="alias",
                    generic="Karelian pie",
                    verified=True,
                    alias_source="cook",
                ),
                stew,
            )
        ],
    )
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 6),
        [
            (line(STEW, stew, source="selected", generic="Karelian pie"), stew),
            (
                line(
                    RICE_PIE,
                    stew,
                    source="alias",
                    generic="Karelian pie",
                    verified=True,
                    alias_source="cook",
                ),
                stew,
            ),
        ],
    )
    return stew


def _flagged(report: Any, product: ProductMaster) -> Any:
    hits = [p for p in report.products if p.product_id == product.id]
    return hits[0] if hits else None


async def test_production_stew_and_rice_pies_are_flagged(db: AsyncSession) -> None:
    stew = await _production_case(db)

    report = await audit_product_joins(db)

    entry = _flagged(report, stew)
    assert entry is not None
    assert entry.product_name == "Karelian stew"
    groups = {g.label: g for g in entry.groups}
    assert set(groups) == {STEW, RICE_PIE}
    assert groups[STEW].match_sources == ["selected"]
    assert groups[STEW].store_chain == "s-group"
    assert groups[STEW].total_count == 1
    assert groups[RICE_PIE].match_sources == ["alias"]
    assert groups[RICE_PIE].total_count == 2
    assert groups[RICE_PIE].active_count == 2
    assert groups[RICE_PIE].first_seen == date(2026, 9, 30)
    assert groups[RICE_PIE].last_seen == date(2026, 10, 6)
    assert groups[RICE_PIE].generic_names == ["Karelian pie"]
    assert any("selected" in reason and STEW in reason for reason in entry.reasons)
    assert entry.min_similarity is not None
    assert 0.0 <= entry.min_similarity < 1.0


async def test_one_printed_name_is_not_flagged(db: AsyncSession) -> None:
    """Even a model pick, if every line printed the same, joined nothing different."""
    milk = await _product(db, "Milk")
    for day in (1, 2):
        await _receipt(
            db,
            "s-group",
            date(2026, 10, day),
            [(line("MAITO 1L", milk, source="selected", generic="Milk"), milk)],
        )

    report = await audit_product_joins(db)

    assert _flagged(report, milk) is None


async def test_verified_aliases_for_two_printed_names_are_not_flagged(
    db: AsyncSession,
) -> None:
    milk = await _product(db, "Milk")
    for printed in ("MAITO 1L", "VALIO MAITO 1L"):
        db.add(_alias(milk, "s-group", printed, verified=True))
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [
            (
                line("MAITO 1L", milk, source="alias", generic="Milk", verified=True),
                milk,
            ),
            (
                line(
                    "VALIO MAITO 1L",
                    milk,
                    source="alias",
                    generic="Milk",
                    verified=True,
                ),
                milk,
            ),
        ],
    )

    report = await audit_product_joins(db)

    assert _flagged(report, milk) is None


async def test_verified_aliases_plus_a_non_key_join_are_flagged(
    db: AsyncSession,
) -> None:
    milk = await _product(db, "Milk")
    for printed in ("MAITO 1L", "VALIO MAITO 1L"):
        db.add(_alias(milk, "s-group", printed, verified=True))
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [
            (
                line("MAITO 1L", milk, source="alias", generic="Milk", verified=True),
                milk,
            ),
            (
                line(
                    "VALIO MAITO 1L",
                    milk,
                    source="alias",
                    generic="Milk",
                    verified=True,
                ),
                milk,
            ),
            # P4: unresolved at read time, joined at confirm by the served generic name
            (line("KAURAJUOMA 1L", milk, source=None, generic="Milk"), milk),
        ],
    )

    report = await audit_product_joins(db)

    entry = _flagged(report, milk)
    assert entry is not None
    assert len(entry.groups) == 3
    assert any("KAURAJUOMA 1L" in reason for reason in entry.reasons)
    oat = next(g for g in entry.groups if g.label == "KAURAJUOMA 1L")
    assert oat.match_sources == ["none"]


async def test_unverified_alias_with_two_printed_names_is_flagged(
    db: AsyncSession,
) -> None:
    milk = await _product(db, "Milk")
    db.add(_alias(milk, "s-group", "MAITO 1L", verified=True))
    db.add(_alias(milk, "s-group", "MAITOJAUHE", verified=False, source="model"))
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [
            (
                line("MAITO 1L", milk, source="alias", generic="Milk", verified=True),
                milk,
            ),
            (
                line(
                    "MAITOJAUHE",
                    milk,
                    source="alias",
                    generic="Milk",
                    verified=False,
                    alias_source="model",
                ),
                milk,
            ),
        ],
    )

    report = await audit_product_joins(db)

    entry = _flagged(report, milk)
    assert entry is not None
    assert any("MAITOJAUHE" in reason for reason in entry.reasons)


async def test_cross_chain_alias_with_two_printed_names_is_flagged(
    db: AsyncSession,
) -> None:
    milk = await _product(db, "Milk")
    db.add(_alias(milk, "s-group", "MAITO 1L", verified=True))
    db.add(_alias(milk, "s-group", "VALIO MAITO", verified=True))
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [
            (
                line("MAITO 1L", milk, source="alias", generic="Milk", verified=True),
                milk,
            )
        ],
    )
    # The Lidl line resolved through the S-group alias: no Lidl alias exists for it.
    await _receipt(
        db,
        "lidl",
        date(2026, 10, 2),
        [
            (
                line(
                    "VALIO MAITO", milk, source="alias", generic="Milk", verified=True
                ),
                milk,
            )
        ],
    )

    report = await audit_product_joins(db)

    entry = _flagged(report, milk)
    assert entry is not None
    assert any("cross-chain" in reason for reason in entry.reasons)


async def test_generic_names_that_differ_are_flagged(db: AsyncSession) -> None:
    """One printed name, but the lines named the food differently."""
    pie = await _product(db, "Karelian pie")
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [(line(RICE_PIE, pie, source="selected", generic="Karelian pie"), pie)],
    )
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 2),
        [(line(RICE_PIE, pie, source="selected", generic="Karelian  PIE"), pie)],
    )
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 3),
        [(line(RICE_PIE, pie, source="selected", generic="Rice cake"), pie)],
    )

    report = await audit_product_joins(db)

    entry = _flagged(report, pie)
    assert entry is not None
    assert any("generic" in reason for reason in entry.reasons)
    assert entry.min_similarity is None  # one printed group: nothing to compare


async def test_generic_names_equal_after_normalisation_are_not_flagged(
    db: AsyncSession,
) -> None:
    pie = await _product(db, "Karelian pie")
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [(line(RICE_PIE, pie, source="alias", generic="Karelian pie"), pie)],
    )
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 2),
        [(line(RICE_PIE, pie, source="alias", generic=" karelian  PIE "), pie)],
    )

    report = await audit_product_joins(db)

    assert _flagged(report, pie) is None


async def test_flagged_products_rank_least_similar_first(db: AsyncSession) -> None:
    near = await _product(db, "Milk")
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 1),
        [
            (line("MAITO 1L", near, source="selected", generic="Milk"), near),
            (line("MAITO 1,5L", near, source="selected", generic="Milk"), near),
        ],
    )
    stew = await _production_case(db)

    report = await audit_product_joins(db)

    ids = [p.product_id for p in report.products]
    assert ids.index(stew.id) < ids.index(near.id)
    similarities = [p.min_similarity for p in report.products]
    assert similarities == sorted(similarities, key=lambda s: (s is None, s))


async def test_active_count_leaves_out_used_up_items(db: AsyncSession) -> None:
    stew = await _production_case(db)
    await _receipt(
        db,
        "s-group",
        date(2026, 10, 7),
        [(line(STEW, stew, source="selected", generic="Karelian pie"), stew)],
        status="empty",
    )

    report = await audit_product_joins(db)

    group = next(g for g in _flagged(report, stew).groups if g.label == STEW)
    assert group.total_count == 2
    assert group.active_count == 1


async def test_model_names_and_unverified_aliases_are_listed_with_counts(
    db: AsyncSession,
) -> None:
    stew = await _production_case(db)
    db.add(ProductName(product_master_id=stew.id, name="karelian pie", source="model"))
    db.add(ProductName(product_master_id=stew.id, name="karelian stew", source="cook"))
    db.add(
        _alias(stew, "lidl", "KARJ.PIIRAKKA", verified=False, source="model", count=4)
    )
    await db.flush()

    report = await audit_product_joins(db)

    names = {(n.name, n.product_id) for n in report.model_names}
    assert ("karelian pie", stew.id) in names
    assert all(n.name != "karelian stew" for n in report.model_names)
    model_name = next(n for n in report.model_names if n.name == "karelian pie")
    assert model_name.product_name == "Karelian stew"
    assert model_name.item_count == 3

    aliases = {a.receipt_name: a for a in report.unverified_aliases}
    assert set(aliases) == {"KARJ.PIIRAKKA"}
    alias = aliases["KARJ.PIIRAKKA"]
    assert alias.occurrence_count == 4
    assert alias.store_chain == "lidl"
    assert alias.source == "model"
    assert alias.product_id == stew.id
    assert alias.product_name == "Karelian stew"


async def test_items_without_a_receipt_line_are_ignored(db: AsyncSession) -> None:
    stew = await _production_case(db)
    db.add(
        InventoryItem(
            product_master_id=stew.id,
            initial_quantity=Decimal("1"),
            current_quantity=Decimal("1"),
            unit="pcs",
            status="sealed",
            purchase_date=date(2026, 10, 8),
            expiry_date=date(2026, 10, 8),
        )
    )
    await db.flush()

    report = await audit_product_joins(db)

    entry = _flagged(report, stew)
    assert sum(g.total_count for g in entry.groups) == 3
    assert isinstance(entry.product_id, UUID)
