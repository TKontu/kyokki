"""Re-keying chain keys an OCR misread invented (Q37 follow-up).

Before the fuzzy pass, a misread Lidl header became its own one-off slug (``lidi-suomi-ky``)
instead of ``lidl``. `plan()` reports what every distinct stored chain key would become today,
and how (`exact` or `fuzzy`); `apply()` rewrites only the keys named explicitly and merges any
(chain, printed name) collision.
"""

from uuid import uuid4

import pytest
from scripts.rekey_store_chains import apply, plan
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.non_food_name import NonFoodName
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias


async def _product(db: AsyncSession, name: str = "Maito") -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="l",
    )
    db.add(product)
    await db.flush()
    return product


async def _receipt(db: AsyncSession, chain: str | None) -> Receipt:
    receipt = Receipt(id=uuid4(), store_chain=chain, image_path="/tmp/x.jpg")
    db.add(receipt)
    await db.flush()
    return receipt


def _alias(
    product_id,
    chain: str,
    name: str,
    *,
    occurrence_count: int = 1,
    manually_verified: bool = False,
) -> StoreProductAlias:
    return StoreProductAlias(
        id=uuid4(),
        product_master_id=product_id,
        store_chain=chain,
        receipt_name=name,
        source="cook",
        confidence_score=1.0,
        manually_verified=manually_verified,
        occurrence_count=occurrence_count,
    )


class TestPlan:
    async def test_misread_lidl_slug_maps_to_lidl(
        self, seeded_db: AsyncSession
    ) -> None:
        await _receipt(seeded_db, "lidi-suomi-ky")
        await seeded_db.commit()

        rows = await plan(seeded_db)

        (row,) = [r for r in rows if r.old_key == "lidi-suomi-ky"]
        assert row.new_key == "lidl"
        assert row.changed
        assert row.receipt_count == 1

    async def test_misread_slug_is_marked_fuzzy_not_suspicious(
        self, seeded_db: AsyncSession
    ) -> None:
        """A genuine OCR fix: the fuzzy pass found `LIDI` one edit from `LIDL`."""
        await _receipt(seeded_db, "lidi-suomi-ky")
        await seeded_db.commit()

        rows = await plan(seeded_db)

        (row,) = [r for r in rows if r.old_key == "lidi-suomi-ky"]
        assert row.rule == "fuzzy"
        assert row.token == "LIDI"
        assert not row.suspicious

    async def test_a_word_that_exactly_contains_a_pattern_is_suspicious(
        self, seeded_db: AsyncSession
    ) -> None:
        """F2: a flea market's "sale" is not an OCR-misread S-ryhmä receipt.

        `kirpputori-sale` (a charity-shop slug) contains the literal word `SALE`, an
        s-group pattern. That is an *exact* match, not a fuzzy one - unexpected for an
        already-stored key - so it must be flagged `suspicious` rather than treated the
        same as a genuine fix.
        """
        await _receipt(seeded_db, "kirpputori-sale")
        await seeded_db.commit()

        rows = await plan(seeded_db)

        (row,) = [r for r in rows if r.old_key == "kirpputori-sale"]
        assert row.new_key == "s-group"
        assert row.changed
        assert row.rule == "exact"
        assert row.suspicious

    async def test_a_known_chain_key_is_unchanged(
        self, seeded_db: AsyncSession
    ) -> None:
        await _receipt(seeded_db, "s-group")
        await seeded_db.commit()

        rows = await plan(seeded_db)

        (row,) = [r for r in rows if r.old_key == "s-group"]
        assert row.new_key == "s-group"
        assert not row.changed
        assert not row.suspicious

    async def test_a_genuinely_unknown_store_is_unchanged(
        self, seeded_db: AsyncSession
    ) -> None:
        await _receipt(seeded_db, "ruohonjuuri-kamppi")
        await seeded_db.commit()

        rows = await plan(seeded_db)

        (row,) = [r for r in rows if r.old_key == "ruohonjuuri-kamppi"]
        assert not row.changed
        assert row.rule is None

    async def test_counts_every_table(self, seeded_db: AsyncSession) -> None:
        product = await _product(seeded_db)
        await _receipt(seeded_db, "lidi-suomi-ky")
        seeded_db.add(_alias(product.id, "lidi-suomi-ky", "KARTANON KALKKUNALEIKE"))
        seeded_db.add(
            NonFoodName(id=uuid4(), store_chain="lidi-suomi-ky", receipt_name="PUSSI")
        )
        await seeded_db.commit()

        rows = await plan(seeded_db)

        (row,) = [r for r in rows if r.old_key == "lidi-suomi-ky"]
        assert (row.receipt_count, row.alias_count, row.non_food_count) == (1, 1, 1)


class TestApply:
    async def test_rewrites_receipt_and_alias(self, seeded_db: AsyncSession) -> None:
        product = await _product(seeded_db)
        await _receipt(seeded_db, "lidi-suomi-ky")
        seeded_db.add(_alias(product.id, "lidi-suomi-ky", "KARTANON KALKKUNALEIKE"))
        await seeded_db.commit()

        rows = await plan(seeded_db)
        touched = await apply(seeded_db, rows, ["lidi-suomi-ky"])

        assert touched == 2
        receipt = (await seeded_db.execute(Receipt.__table__.select())).first()
        assert receipt.store_chain == "lidl"
        alias = (await seeded_db.execute(StoreProductAlias.__table__.select())).first()
        assert alias.store_chain == "lidl"

    async def test_unnamed_changed_keys_are_left_alone(
        self, seeded_db: AsyncSession
    ) -> None:
        """F2: only the keys named in `--apply` move, even if others also changed."""
        await _receipt(seeded_db, "lidi-suomi-ky")
        await _receipt(seeded_db, "kirpputori-sale")
        await seeded_db.commit()

        rows = await plan(seeded_db)
        touched = await apply(seeded_db, rows, ["lidi-suomi-ky"])

        assert touched == 1
        chains = {
            row.store_chain
            for row in (await seeded_db.execute(Receipt.__table__.select())).all()
        }
        assert chains == {"lidl", "kirpputori-sale"}

    async def test_suspicious_key_is_not_rekeyed_unless_named_explicitly(
        self, seeded_db: AsyncSession
    ) -> None:
        await _receipt(seeded_db, "kirpputori-sale")
        await seeded_db.commit()

        rows = await plan(seeded_db)
        (row,) = [r for r in rows if r.old_key == "kirpputori-sale"]
        assert row.suspicious  # sanity: this is the case the test is about

        touched = await apply(seeded_db, rows, [])

        assert touched == 0
        receipt = (await seeded_db.execute(Receipt.__table__.select())).first()
        assert receipt.store_chain == "kirpputori-sale"

    async def test_apply_refuses_a_key_not_in_the_plan(
        self, seeded_db: AsyncSession
    ) -> None:
        await _receipt(seeded_db, "lidi-suomi-ky")
        await seeded_db.commit()
        rows = await plan(seeded_db)

        with pytest.raises(ValueError, match="not-a-real-key"):
            await apply(seeded_db, rows, ["not-a-real-key"])

        # Nothing was written: the whole call refused, not a partial apply.
        receipt = (await seeded_db.execute(Receipt.__table__.select())).first()
        assert receipt.store_chain == "lidi-suomi-ky"

    async def test_apply_refuses_an_unchanged_key(
        self, seeded_db: AsyncSession
    ) -> None:
        """There is no "apply everything" mode: naming a key still requires it to be due a
        change, so a typo'd-but-real key (e.g. an already-correct one) is refused too."""
        await _receipt(seeded_db, "s-group")
        await seeded_db.commit()
        rows = await plan(seeded_db)

        with pytest.raises(ValueError, match="s-group"):
            await apply(seeded_db, rows, ["s-group"])

    async def test_colliding_aliases_merge_keeping_higher_count_and_verified(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)
        # Same printed name, once under the misread slug (low count, unverified) and
        # once already under the real chain key (higher count, verified) - the merge
        # must keep the already-verified, higher-count row.
        seeded_db.add(
            _alias(
                product.id,
                "lidi-suomi-ky",
                "KARTANON KALKKUNALEIKE",
                occurrence_count=1,
                manually_verified=False,
            )
        )
        seeded_db.add(
            _alias(
                product.id,
                "lidl",
                "KARTANON KALKKUNALEIKE",
                occurrence_count=5,
                manually_verified=True,
            )
        )
        await seeded_db.commit()

        rows = await plan(seeded_db)
        await apply(seeded_db, rows, ["lidi-suomi-ky"])

        remaining = (
            (await seeded_db.execute(StoreProductAlias.__table__.select()))
            .mappings()
            .all()
        )
        assert len(remaining) == 1
        survivor = remaining[0]
        assert survivor["store_chain"] == "lidl"
        assert survivor["occurrence_count"] == 5
        assert survivor["manually_verified"] is True

    async def test_colliding_aliases_merge_verified_from_the_lower_count_side(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)
        # The higher-count row is the one filed under the old, misread key this time;
        # the verified flag from the other side must still survive the merge.
        seeded_db.add(
            _alias(
                product.id,
                "lidi-suomi-ky",
                "KARTANON KALKKUNALEIKE",
                occurrence_count=9,
                manually_verified=False,
            )
        )
        seeded_db.add(
            _alias(
                product.id,
                "lidl",
                "KARTANON KALKKUNALEIKE",
                occurrence_count=2,
                manually_verified=True,
            )
        )
        await seeded_db.commit()

        rows = await plan(seeded_db)
        await apply(seeded_db, rows, ["lidi-suomi-ky"])

        remaining = (
            (await seeded_db.execute(StoreProductAlias.__table__.select()))
            .mappings()
            .all()
        )
        assert len(remaining) == 1
        survivor = remaining[0]
        assert survivor["store_chain"] == "lidl"
        assert survivor["occurrence_count"] == 9
        assert survivor["manually_verified"] is True

    async def test_non_colliding_alias_just_moves(
        self, seeded_db: AsyncSession
    ) -> None:
        product = await _product(seeded_db)
        seeded_db.add(_alias(product.id, "lidi-suomi-ky", "MAITO 1L"))
        await seeded_db.commit()

        rows = await plan(seeded_db)
        await apply(seeded_db, rows, ["lidi-suomi-ky"])

        remaining = (
            (await seeded_db.execute(StoreProductAlias.__table__.select()))
            .mappings()
            .all()
        )
        assert len(remaining) == 1
        assert remaining[0]["store_chain"] == "lidl"

    async def test_dry_run_default_writes_nothing(
        self, seeded_db: AsyncSession
    ) -> None:
        """`plan()` alone (what a dry run does) must not touch any row."""
        await _receipt(seeded_db, "lidi-suomi-ky")
        await seeded_db.commit()

        await plan(seeded_db)

        receipt = (await seeded_db.execute(Receipt.__table__.select())).first()
        assert receipt.store_chain == "lidi-suomi-ky"
