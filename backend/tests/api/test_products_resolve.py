"""AG2: resolve a name to a product, and teach a product a new name."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.services import product_lookup


@pytest.fixture(autouse=True)
def broadcast():
    with patch(
        "app.api.endpoints.products.broadcast_product_update", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
async def own_sessions(db_engine, committed_db_session: AsyncSession):
    """Every request gets a session of its own on its own connection, committing for real.

    The savepoint ``db_session`` runs everything on one connection, so a second writer
    racing the request cannot be staged in it. ``committed_db_session`` truncates after.
    """
    from app.db.seed_categories import seed_categories
    from app.db.session import get_db
    from app.main import app

    await seed_categories(committed_db_session)
    await committed_db_session.commit()
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield committed_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


def _id(obj):
    """The row's id without loading it: a rolled-back session has expired every object."""
    return inspect(obj).identity[0]


async def _product(
    db: AsyncSession, name: str, *, category: str = "dairy"
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
    )
    db.add(product)
    db.add(
        ProductName(
            product_master_id=product.id, name=name.casefold(), source="canonical"
        )
    )
    await db.commit()
    return product


async def _names(db: AsyncSession, key: str) -> list[ProductName]:
    rows = await db.execute(select(ProductName).where(ProductName.name == key))
    return list(rows.scalars().all())


class TestResolve:
    async def test_is_not_taken_for_a_product_id(
        self, client: AsyncClient, seeded_db
    ) -> None:
        response = await client.get("/api/products/resolve", params={"name": "milk"})

        assert response.status_code == 200, response.text

    async def test_an_exact_name_is_a_match(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")

        body = (
            await client.get("/api/products/resolve", params={"name": "  MILK "})
        ).json()

        assert body["match"] == {
            "product_id": str(_id(milk)),
            "name": "Milk",
            "source": "canonical",
        }
        assert body["suggestion"] is None

    async def test_a_learned_name_says_whose_word_it_was(
        self, client: AsyncClient, seeded_db
    ) -> None:
        mince = await _product(seeded_db, "Ground beef", category="meat")
        seeded_db.add(
            ProductName(product_master_id=_id(mince), name="jauheliha", source="cook")
        )
        await seeded_db.commit()

        body = (
            await client.get("/api/products/resolve", params={"name": "Jauheliha"})
        ).json()

        assert body["match"]["product_id"] == str(_id(mince))
        assert body["match"]["source"] == "cook"

    async def test_a_near_miss_offers_candidates_and_a_suggestion(
        self, client: AsyncClient, seeded_db
    ) -> None:
        oat = await _product(seeded_db, "Oat milk")

        body = (
            await client.get("/api/products/resolve", params={"name": "Milk"})
        ).json()

        assert body["match"] is None
        assert [c["product_id"] for c in body["candidates"]] == [str(_id(oat))]
        assert body["candidates"][0]["name"] == "Oat milk"
        assert body["candidates"][0]["source"] == "canonical"
        assert 0 < body["candidates"][0]["score"] <= 1
        assert body["suggestion"] == "milk"

    async def test_nothing_at_all(self, client: AsyncClient, seeded_db) -> None:
        body = (
            await client.get("/api/products/resolve", params={"name": "Zyxxy  Thing"})
        ).json()

        assert body == {"match": None, "candidates": [], "suggestion": "zyxxy thing"}

    async def test_a_name_is_required(self, client: AsyncClient, seeded_db) -> None:
        response = await client.get("/api/products/resolve")

        assert response.status_code == 422


class TestTeachAName:
    async def test_learns_a_cook_name(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        mince = await _product(seeded_db, "Ground beef", category="meat")

        response = await client.post(
            f"/api/products/{_id(mince)}/names", json={"name": " Jauheliha "}
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["name"], body["source"], body["removable"]) == (
            "jauheliha",
            "cook",
            True,
        )
        (row,) = await _names(seeded_db, "jauheliha")
        assert row.product_master_id == _id(mince)
        broadcast.assert_awaited_once()

    async def test_its_own_name_without_a_name_row_is_200_unchanged(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        # Written straight to product_master, as Open Food Facts enrichment does
        oats = ProductMaster(
            id=uuid4(),
            canonical_name="Oat milk",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="dl",
        )
        seeded_db.add(oats)
        await seeded_db.commit()

        response = await client.post(
            f"/api/products/{_id(oats)}/names", json={"name": "OAT  milk"}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["name"], body["source"], body["removable"]) == (
            "oat milk",
            "canonical",
            False,
        )
        broadcast.assert_not_awaited()

    async def test_a_name_it_already_has_is_200_unchanged(
        self, client: AsyncClient, seeded_db
    ) -> None:
        mince = await _product(seeded_db, "Ground beef", category="meat")
        url = f"/api/products/{_id(mince)}/names"
        first = await client.post(url, json={"name": "jauheliha"})

        again = await client.post(url, json={"name": "JAUHELIHA"})

        assert again.status_code == 200
        assert again.json() == first.json()
        assert len(await _names(seeded_db, "jauheliha")) == 1

    async def test_another_products_name_is_a_conflict(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        cream = await _product(seeded_db, "Cream")

        response = await client.post(
            f"/api/products/{_id(cream)}/names", json={"name": "milk"}
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "conflict"
        assert "Milk" in detail["message"]
        (row,) = await _names(seeded_db, "milk")
        assert row.product_master_id == _id(milk)

    async def test_an_unknown_product(self, client: AsyncClient, seeded_db) -> None:
        response = await client.post(
            f"/api/products/{uuid4()}/names", json={"name": "anything"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    async def test_a_blank_name_is_a_422(self, client: AsyncClient, seeded_db) -> None:
        milk = await _product(seeded_db, "Milk")

        response = await client.post(
            f"/api/products/{_id(milk)}/names", json={"name": "   "}
        )

        assert response.status_code == 422

    async def test_a_repeated_key_replays(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        mince = await _product(seeded_db, "Ground beef", category="meat")
        url = f"/api/products/{_id(mince)}/names"
        headers = {"Idempotency-Key": "name-1"}

        first = await client.post(url, json={"name": "jauheliha"}, headers=headers)
        second = await client.post(url, json={"name": "jauheliha"}, headers=headers)
        other = await client.post(url, json={"name": "hakkliha"}, headers=headers)

        assert (first.status_code, second.status_code) == (201, 201)
        assert second.json() == first.json()
        assert other.status_code == 409
        assert other.json()["detail"]["code"] == "conflict"
        assert broadcast.await_count == 1
        count = await seeded_db.execute(
            select(func.count())
            .select_from(ProductName)
            .where(ProductName.product_master_id == _id(mince))
        )
        assert count.scalar_one() == 2

    async def test_the_existing_names_routes_still_work(
        self, client: AsyncClient, seeded_db
    ) -> None:
        mince = await _product(seeded_db, "Ground beef", category="meat")
        await client.post(
            f"/api/products/{_id(mince)}/names", json={"name": "jauheliha"}
        )

        listed = (await client.get(f"/api/products/{_id(mince)}/names")).json()
        learned = next(n for n in listed["names"] if n["name"] == "jauheliha")
        deleted = await client.delete(
            f"/api/products/{_id(mince)}/names/{learned['id']}"
        )

        assert deleted.status_code == 204
        assert await _names(seeded_db, "jauheliha") == []


class TestTeachRace:
    @pytest.mark.parametrize("lands", ["during_its_write", "before_its_write"], ids=str)
    async def test_the_same_name_taught_elsewhere_meanwhile_is_a_conflict(
        self,
        client: AsyncClient,
        own_sessions: AsyncSession,
        db_engine,
        broadcast,
        lands: str,
    ) -> None:
        """Another request teaches the name to Milk between this one's check and write.

        Landing during the write is a unique violation on insert; landing before it,
        `learn_product_name` sees the other product's row and leaves it alone.
        """
        milk_id = _id(await _product(own_sessions, "Milk"))
        cream_id = _id(await _product(own_sessions, "Cream"))
        other_writer = async_sessionmaker(db_engine, class_=AsyncSession)
        real_learn = product_lookup.learn_product_name
        commits: list[asyncio.Task] = []

        async def racing_learn(db, product, name, source="model"):
            if not commits:
                other = other_writer()
                other.add(
                    ProductName(product_master_id=milk_id, name=name, source="cook")
                )
                await other.flush()  # not committed: this request cannot see it yet

                async def commit_soon() -> None:
                    await asyncio.sleep(0.2)
                    await other.commit()
                    await other.close()

                commits.append(asyncio.create_task(commit_soon()))
                if lands == "before_its_write":
                    await commits[0]
            return await real_learn(db, product, name, source=source)

        with patch("app.services.product_lookup.learn_product_name", new=racing_learn):
            response = await client.post(
                f"/api/products/{cream_id}/names", json={"name": "Moo"}
            )
        await asyncio.gather(*commits)

        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "conflict"
        assert detail["product_id"] == str(milk_id)
        (row,) = await _names(own_sessions, "moo")
        assert row.product_master_id == milk_id
        broadcast.assert_not_awaited()
