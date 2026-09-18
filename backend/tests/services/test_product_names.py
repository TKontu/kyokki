"""Names as keys (H11, `docs/PRODUCT_RESOLUTION_SPEC.md` §3.1).

Fuzzy similarity cannot see synonyms: "Minced beef" scores 64 against "Ground beef", so
the old matcher left it unmatched and the cook re-created the product every week. A name
that means a product is stored, not guessed at.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.services.product_names import (
    known_names,
    learn_product_name,
    normalize_product_name,
    product_for_name,
)


async def _product(
    db: AsyncSession, name: str, category: str = "meat"
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=5,
        unit_type="weight",
        default_unit="g",
    )
    db.add(product)
    await db.flush()
    await learn_product_name(db, product, name, "canonical")
    await db.commit()
    return product


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    for category_id in ("meat", "dairy"):
        db_session.add(
            Category(
                id=category_id,
                display_name=category_id.title(),
                icon="*",
                default_shelf_life_days=5,
                meal_contexts=[],
                sort_order=1,
            )
        )
    await db_session.commit()


class TestNormalise:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Ground beef", "ground beef"),
            ("  GROUND   BEEF ", "ground beef"),
            ("Ground\tbeef", "ground beef"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_the_key_is_casefolded_and_collapsed(self, raw, expected) -> None:
        assert normalize_product_name(raw) == expected

    def test_a_trailing_price_is_kept(self) -> None:
        """Unlike `normalize_receipt_name`, which keys printed lines: a catalog name is
        not a receipt line and should not be silently truncated."""
        assert normalize_product_name("Beef 4,27") == "beef 4,27"


class TestLookup:
    async def test_the_canonical_name_resolves(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Ground beef")

        found = await product_for_name(db_session, "Ground beef")

        assert found is not None and found.id == product.id

    async def test_lookup_ignores_case_and_spacing(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Ground beef")

        found = await product_for_name(db_session, "  gRoUnd   BEEF  ")

        assert found is not None and found.id == product.id

    async def test_a_synonym_resolves_to_the_same_product(
        self, db_session: AsyncSession, categories
    ) -> None:
        """The case fuzzy matching could never reach."""
        product = await _product(db_session, "Ground beef")
        await learn_product_name(db_session, product, "Minced beef", "model")

        found = await product_for_name(db_session, "minced beef")

        assert found is not None and found.id == product.id

    async def test_an_unknown_name_resolves_to_nothing(
        self, db_session: AsyncSession, categories
    ) -> None:
        await _product(db_session, "Apple")

        assert await product_for_name(db_session, "Pineapple") is None

    async def test_a_substring_is_not_a_match(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Sour cream is not Cream; this is the whole point of keys over scores."""
        await _product(db_session, "Cream", "dairy")

        assert await product_for_name(db_session, "Sour cream") is None

    async def test_an_empty_name_resolves_to_nothing(
        self, db_session: AsyncSession, categories
    ) -> None:
        assert await product_for_name(db_session, "   ") is None

    async def test_many_names_resolve_in_one_call(
        self, db_session: AsyncSession, categories
    ) -> None:
        beef = await _product(db_session, "Ground beef")
        milk = await _product(db_session, "Milk", "dairy")

        found = await known_names(db_session, ["Ground beef", "MILK", "Nothing"])

        assert {key: p.id for key, p in found.items()} == {
            "ground beef": beef.id,
            "milk": milk.id,
        }


class TestLearning:
    async def test_learning_a_new_name_adds_a_row(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Ground beef")

        assert (
            await learn_product_name(db_session, product, "Beef mince", "cook") is True
        )

        rows = (await db_session.execute(select(ProductName))).scalars().all()
        assert sorted(r.name for r in rows) == ["beef mince", "ground beef"]

    async def test_the_source_is_recorded(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Ground beef")
        await learn_product_name(db_session, product, "Beef mince", "cook")

        row = (
            (
                await db_session.execute(
                    select(ProductName).where(ProductName.name == "beef mince")
                )
            )
            .scalars()
            .one()
        )
        assert row.source == "cook"

    async def test_relearning_the_same_name_is_a_no_op(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Confirm calls this on every line, so it must be cheap and idempotent."""
        product = await _product(db_session, "Ground beef")

        assert await learn_product_name(db_session, product, "ground beef") is False

        rows = (await db_session.execute(select(ProductName))).scalars().all()
        assert len(rows) == 1

    async def test_a_name_another_product_already_claims_is_left_alone(
        self, db_session: AsyncSession, categories
    ) -> None:
        """First claim wins. A genuine clash is resolved by merge (spec §3.7), never by
        silently repointing a key the rest of the catalog depends on."""
        beef = await _product(db_session, "Ground beef")
        pork = await _product(db_session, "Ground pork")

        assert (
            await learn_product_name(db_session, pork, "Ground beef", "cook") is False
        )

        found = await product_for_name(db_session, "Ground beef")
        assert found is not None and found.id == beef.id

    async def test_an_empty_name_teaches_nothing(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Ground beef")

        assert await learn_product_name(db_session, product, "  ") is False

    async def test_names_go_when_the_product_goes(
        self, db_session: AsyncSession, categories
    ) -> None:
        """ondelete=CASCADE: a name has no meaning without its product."""
        product = await _product(db_session, "Ground beef")
        await learn_product_name(db_session, product, "Minced beef", "model")

        await db_session.delete(product)
        await db_session.commit()

        assert (await db_session.execute(select(ProductName))).scalars().all() == []
