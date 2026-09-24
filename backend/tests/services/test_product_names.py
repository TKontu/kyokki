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
    CanonicalName,
    UnknownName,
    forget_product_name,
    known_names,
    learn_product_name,
    names_for_product,
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


async def _row(db: AsyncSession, key: str) -> ProductName:
    return (
        (await db.execute(select(ProductName).where(ProductName.name == key)))
        .scalars()
        .one()
    )


async def _count(db: AsyncSession, key: str) -> int:
    rows = (
        (await db.execute(select(ProductName).where(ProductName.name == key)))
        .scalars()
        .all()
    )
    return len(rows)


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    for category_id in ("meat", "dairy"):
        db_session.add(
            Category(
                id=category_id,
                display_name=category_id.title(),
                icon="*",
                default_shelf_life_days=5,
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

        assert {key: k.product.id for key, k in found.items()} == {
            "ground beef": beef.id,
            "milk": milk.id,
        }
        assert {k.source for k in found.values()} == {"canonical"}

    async def test_known_names_carry_their_source(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Resolution needs to tell the cook's word from a model's guess (H51)."""
        beef = await _product(db_session, "Ground beef")
        await learn_product_name(db_session, beef, "Beef mince", "cook")
        await learn_product_name(db_session, beef, "Minced beef", "model")
        await db_session.commit()

        found = await known_names(
            db_session, ["Ground beef", "Beef mince", "Minced beef"]
        )

        assert {key: k.source for key, k in found.items()} == {
            "ground beef": "canonical",
            "beef mince": "cook",
            "minced beef": "model",
        }

    async def test_a_product_without_a_name_row_is_known_by_its_canonical_name(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Open Food Facts enrichment writes straight to `product_master`."""
        product = ProductMaster(
            id=uuid4(),
            canonical_name="Feta",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=5,
            unit_type="weight",
            default_unit="g",
        )
        db_session.add(product)
        await db_session.commit()

        found = await known_names(db_session, ["feta"])

        assert found["feta"].product.id == product.id
        assert found["feta"].source == "canonical"

    async def test_the_cooks_lookup_can_skip_model_names(
        self, db_session: AsyncSession, categories
    ) -> None:
        """A cook typing "Ketchup" as a new product must not be handed the product a
        model once guessed for that word (H51)."""
        sauce = await _product(db_session, "Taco sauce")
        await learn_product_name(db_session, sauce, "Ketchup", "model")
        await learn_product_name(db_session, sauce, "Salsa", "cook")
        await db_session.commit()

        assert await product_for_name(db_session, "Ketchup", trust_model=False) is None
        salsa = await product_for_name(db_session, "Salsa", trust_model=False)
        assert salsa is not None and salsa.id == sauce.id
        own = await product_for_name(db_session, "Taco sauce", trust_model=False)
        assert own is not None and own.id == sauce.id
        # The default still honours a model synonym: that is what makes it useful.
        trusted = await product_for_name(db_session, "Ketchup")
        assert trusted is not None and trusted.id == sauce.id


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

    async def test_a_cook_or_canonical_claim_is_never_re_pointed(
        self, db_session: AsyncSession, categories
    ) -> None:
        """First claim wins among the cook's and canonical rows. A genuine clash is
        resolved by merge (spec §3.7), never by silently repointing a key the rest of
        the catalog depends on."""
        beef = await _product(db_session, "Ground beef")
        pork = await _product(db_session, "Ground pork")

        assert (
            await learn_product_name(db_session, pork, "Ground beef", "cook") is False
        )

        found = await product_for_name(db_session, "Ground beef")
        assert found is not None and found.id == beef.id

    async def test_a_cook_claim_is_not_re_pointed_by_a_model_learn(
        self, db_session: AsyncSession, categories
    ) -> None:
        ketchup = await _product(db_session, "Ketchup")
        sauce = await _product(db_session, "Taco sauce")
        await learn_product_name(db_session, ketchup, "Tomato ketchup", "cook")

        assert (
            await learn_product_name(db_session, sauce, "Tomato ketchup", "model")
            is False
        )

        found = await product_for_name(db_session, "Tomato ketchup")
        assert found is not None and found.id == ketchup.id

    async def test_a_model_claim_yields_to_the_cook(
        self, db_session: AsyncSession, categories
    ) -> None:
        """The reported case (Q13): "ketchup" guessed for Taco sauce once, and the
        cook's correction could never move it. Now it does."""
        sauce = await _product(db_session, "Taco sauce")
        ketchup = await _product(db_session, "Heinz")
        await learn_product_name(db_session, sauce, "Ketchup", "model")

        assert await learn_product_name(db_session, ketchup, "Ketchup", "cook") is True

        row = await _row(db_session, "ketchup")
        assert (row.product_master_id, row.source) == (ketchup.id, "cook")
        assert await _count(db_session, "ketchup") == 1

    async def test_a_model_claim_yields_to_a_canonical_name(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Creating a product called Ketchup must leave it resolvable by its own name,
        whatever a model once guessed for that word."""
        sauce = await _product(db_session, "Taco sauce")
        await learn_product_name(db_session, sauce, "Ketchup", "model")

        ketchup = await _product(db_session, "Ketchup")

        row = await _row(db_session, "ketchup")
        assert (row.product_master_id, row.source) == (ketchup.id, "canonical")
        found = await product_for_name(db_session, "Ketchup")
        assert found is not None and found.id == ketchup.id

    async def test_the_cook_confirming_a_model_synonym_upgrades_it(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Same product, stronger word: the row is upgraded, not duplicated. Returns
        False because no row was added - merge counts on that (H16)."""
        beef = await _product(db_session, "Ground beef")
        await learn_product_name(db_session, beef, "Minced beef", "model")

        assert (
            await learn_product_name(db_session, beef, "Minced beef", "cook") is False
        )

        row = await _row(db_session, "minced beef")
        assert (row.product_master_id, row.source) == (beef.id, "cook")
        assert await _count(db_session, "minced beef") == 1

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


class TestForgetting:
    """H52: the cook takes back a name the table learned."""

    async def test_its_own_name_is_listed_first(
        self, db_session: AsyncSession, categories: None
    ) -> None:
        product = await _product(db_session, "Taco sauce")
        await learn_product_name(db_session, product, "ketchup", "model")
        await learn_product_name(db_session, product, "abc salsa", "cook")

        names = await names_for_product(db_session, product.id)

        assert [(row.name, row.source) for row in names] == [
            ("taco sauce", "canonical"),
            ("abc salsa", "cook"),
            ("ketchup", "model"),
        ]

    async def test_a_forgotten_name_resolves_to_nothing(
        self, db_session: AsyncSession, categories: None
    ) -> None:
        product = await _product(db_session, "Taco sauce")
        await learn_product_name(db_session, product, "ketchup", "model")
        await db_session.commit()
        row = await _row(db_session, "ketchup")

        await forget_product_name(db_session, product.id, row.id)

        assert await product_for_name(db_session, "ketchup") is None

    async def test_the_canonical_name_stays(
        self, db_session: AsyncSession, categories: None
    ) -> None:
        product = await _product(db_session, "Taco sauce")
        row = await _row(db_session, "taco sauce")

        with pytest.raises(CanonicalName):
            await forget_product_name(db_session, product.id, row.id)

        assert await _count(db_session, "taco sauce") == 1

    async def test_another_products_name_is_unknown_here(
        self, db_session: AsyncSession, categories: None
    ) -> None:
        product = await _product(db_session, "Taco sauce")
        other = await _product(db_session, "Ketchup")
        await learn_product_name(db_session, other, "tomato ketchup", "cook")
        await db_session.commit()
        row = await _row(db_session, "tomato ketchup")

        with pytest.raises(UnknownName):
            await forget_product_name(db_session, product.id, row.id)

        assert await _count(db_session, "tomato ketchup") == 1
