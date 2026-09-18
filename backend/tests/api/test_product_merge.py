"""Tests for POST /api/products/{id}/merge (H16, spec §3.7).

Merge is the repair for a duplicate catalog entry, and the safe answer to
"I cannot delete this product": DELETE refuses with 409 while anything still
refers to the row, and those references are exactly what a merge moves.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product_master import references_to_product
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_name import ProductName
from app.models.shopping_list_item import ShoppingListItem
from app.models.store_product_alias import StoreProductAlias
from app.services.product_names import normalize_product_name, product_for_name

PRODUCT = {
    "category": "dairy",
    "storage_type": "refrigerator",
    "default_shelf_life_days": 7,
    "unit_type": "volume",
    "default_unit": "dl",
}


async def make_product(client: AsyncClient, name: str) -> dict:
    """A product created the way the cook creates one, canonical name row and all."""
    response = await client.post(
        "/api/products", json={**PRODUCT, "canonical_name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_inventory_item(db: AsyncSession, product_id: UUID) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product_id,
        initial_quantity=Decimal("1000"),
        current_quantity=Decimal("750"),
        unit="dl",
        status="sealed",
        expiry_date=date.today() + timedelta(days=7),
    )
    db.add(item)
    await db.commit()
    return item


async def count_referencing(db: AsyncSession, model, product_id: UUID) -> int:
    total = await db.scalar(
        select(func.count())
        .select_from(model)
        .where(model.product_master_id == product_id)
    )
    return int(total or 0)


@pytest.fixture
async def duplicates(client: AsyncClient, seeded_db: AsyncSession) -> tuple[dict, dict]:
    """The catalog mistake this endpoint exists for: one product entered twice."""
    source = await make_product(client, "Minced Beef")
    target = await make_product(client, "Ground Beef")
    return source, target


class TestMergeMovesEveryReference:
    """A merge moves what a delete refuses to destroy."""

    async def test_every_referencing_table_points_at_the_target(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates
        source_id, target_id = UUID(source["id"]), UUID(target["id"])

        item = await add_inventory_item(seeded_db, source_id)
        seeded_db.add_all(
            [
                StoreProductAlias(
                    id=uuid4(),
                    product_master_id=source_id,
                    store_chain="s-market",
                    receipt_name="ATRIA JAUHELIHA",
                ),
                ProductName(
                    id=uuid4(),
                    product_master_id=source_id,
                    name="beef mince",
                    source="model",
                ),
                ShoppingListItem(
                    id=uuid4(),
                    product_master_id=source_id,
                    name="Minced Beef",
                    quantity=Decimal("1"),
                    unit="pcs",
                ),
                ConsumptionLog(
                    id=uuid4(),
                    inventory_item_id=item.id,
                    product_master_id=source_id,
                    action="use_partial",
                    quantity_consumed=Decimal("250"),
                ),
            ]
        )
        await seeded_db.commit()

        response = await client.post(
            f"/api/products/{source_id}/merge", json={"target_id": str(target_id)}
        )

        assert response.status_code == 200, response.text
        for model in (
            InventoryItem,
            StoreProductAlias,
            ShoppingListItem,
            ConsumptionLog,
        ):
            assert await count_referencing(seeded_db, model, target_id) == 1, model
        # "beef mince" plus the source's canonical name, on top of the target's own.
        assert await count_referencing(seeded_db, ProductName, target_id) == 3

    async def test_the_response_counts_what_moved(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates
        await add_inventory_item(seeded_db, UUID(source["id"]))

        response = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        body = response.json()
        assert body["source_id"] == source["id"]
        assert body["source_name"] == "Minced Beef"
        assert body["target"]["id"] == target["id"]
        assert body["moved"]["inventory_item"] == 1
        assert body["moved"]["product_name"] == 1

    async def test_the_source_is_gone(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates

        await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        assert (await client.get(f"/api/products/{source['id']}")).status_code == 404
        assert (await client.get(f"/api/products/{target['id']}")).status_code == 200

    async def test_no_orphan_rows_are_left_behind(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        """The spec's acceptance criterion for a merge."""
        source, target = duplicates
        source_id = UUID(source["id"])
        item = await add_inventory_item(seeded_db, source_id)
        seeded_db.add_all(
            [
                StoreProductAlias(
                    id=uuid4(),
                    product_master_id=source_id,
                    store_chain="prisma",
                    receipt_name="JAUHELIHA 400G",
                ),
                ShoppingListItem(
                    id=uuid4(),
                    product_master_id=source_id,
                    name="Minced Beef",
                    quantity=Decimal("1"),
                    unit="pcs",
                ),
                ConsumptionLog(
                    id=uuid4(),
                    inventory_item_id=item.id,
                    product_master_id=source_id,
                    action="use_full",
                    quantity_consumed=Decimal("750"),
                ),
            ]
        )
        await seeded_db.commit()

        await client.post(
            f"/api/products/{source_id}/merge", json={"target_id": target["id"]}
        )

        assert await references_to_product(seeded_db, source_id) == {}
        assert await count_referencing(seeded_db, ProductName, source_id) == 0


class TestTheMergedNameKeepsResolving:
    """A cook who types the old name must still land on the surviving product."""

    async def test_the_source_canonical_name_resolves_to_the_target(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates

        await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        resolved = await product_for_name(seeded_db, "Minced Beef")
        assert resolved is not None
        assert str(resolved.id) == target["id"]

    async def test_the_merged_name_is_the_cooks_own_synonym(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        """A merge is an act of the cook, not a guess by the model."""
        source, target = duplicates

        await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        row = (
            (
                await seeded_db.execute(
                    select(ProductName).where(
                        ProductName.name == normalize_product_name("Minced Beef")
                    )
                )
            )
            .scalars()
            .one()
        )
        assert str(row.product_master_id) == target["id"]
        assert row.source == "cook"

    async def test_the_target_keeps_its_own_canonical_name(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates

        await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        resolved = await product_for_name(seeded_db, "Ground Beef")
        assert resolved is not None
        assert str(resolved.id) == target["id"]


class TestMergeIsRefused:
    """The two refusals happen before anything moves."""

    async def test_merging_a_product_into_itself_is_a_400(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, _ = duplicates

        response = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": source["id"]}
        )

        assert response.status_code == 400
        assert (await client.get(f"/api/products/{source['id']}")).status_code == 200

    async def test_an_unknown_source_is_a_404(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        _, target = duplicates

        response = await client.post(
            f"/api/products/{uuid4()}/merge", json={"target_id": target["id"]}
        )

        assert response.status_code == 404

    async def test_an_unknown_target_is_a_404(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, _ = duplicates
        missing = uuid4()

        response = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": str(missing)}
        )

        assert response.status_code == 404
        assert str(missing) in response.json()["detail"]
        assert (await client.get(f"/api/products/{source['id']}")).status_code == 200


class TestCollidingRows:
    """Both products can already know the same name; one row has to go."""

    async def test_a_name_the_target_already_claims_is_dropped_not_crashed(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        """`product_name` is UNIQUE (name), so the duplicate cannot simply move.

        The state is reachable because not every product gets a name row: Open
        Food Facts enrichment writes straight to `product_master`. Such a product
        can be merged away while the target already lists its name as a synonym.
        """
        source, target = duplicates
        key = normalize_product_name("Minced Beef")
        await seeded_db.execute(delete(ProductName).where(ProductName.name == key))
        seeded_db.add(
            ProductName(
                id=uuid4(),
                product_master_id=UUID(target["id"]),
                name=key,
                source="model",
            )
        )
        await seeded_db.commit()

        response = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        assert response.status_code == 200, response.text
        assert response.json()["dropped"]["product_name"] == 1
        rows = (
            (
                await seeded_db.execute(
                    select(ProductName).where(ProductName.name == key)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert str(rows[0].product_master_id) == target["id"]
        resolved = await product_for_name(seeded_db, "Minced Beef")
        assert resolved is not None and str(resolved.id) == target["id"]

    async def test_an_alias_both_products_know_keeps_exactly_one(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        """A duplicate printed name collapses instead of failing the merge.

        `uq_store_product_alias_chain_name` (H14) normally makes this state
        impossible, which is exactly why a merge must not depend on it: the repair
        for a broken catalog cannot be the operation that dies on broken data. The
        constraint is dropped inside this test's transaction - rolled back with
        everything else - so the collapse itself can be exercised.
        """
        source, target = duplicates
        await seeded_db.execute(
            text(
                "ALTER TABLE store_product_alias "
                "DROP CONSTRAINT IF EXISTS uq_store_product_alias_chain_name"
            )
        )
        seeded_db.add_all(
            [
                StoreProductAlias(
                    id=uuid4(),
                    product_master_id=UUID(source["id"]),
                    store_chain="s-market",
                    receipt_name="ATRIA JAUHELIHA",
                    source="cook",
                    occurrence_count=3,
                    manually_verified=True,
                    confidence_score=0.9,
                    last_seen=datetime(2026, 9, 1, tzinfo=UTC),
                ),
                StoreProductAlias(
                    id=uuid4(),
                    product_master_id=UUID(target["id"]),
                    store_chain="s-market",
                    receipt_name="ATRIA JAUHELIHA",
                    source="model",
                    occurrence_count=2,
                    manually_verified=False,
                    confidence_score=0.4,
                    last_seen=datetime(2026, 8, 1, tzinfo=UTC),
                ),
            ]
        )
        await seeded_db.commit()

        response = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        assert response.status_code == 200, response.text
        assert response.json()["dropped"]["store_product_alias"] == 1
        aliases = (
            (
                await seeded_db.execute(
                    select(StoreProductAlias).where(
                        StoreProductAlias.receipt_name == "ATRIA JAUHELIHA"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(aliases) == 1
        surviving = aliases[0]
        assert str(surviving.product_master_id) == target["id"]
        # The cook's word and the evidence behind it outlive the duplicate row.
        assert surviving.manually_verified is True
        assert surviving.source == "cook"
        assert surviving.occurrence_count == 5

    async def test_an_alias_for_another_chain_still_moves(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates
        for chain, product in (("s-market", source), ("prisma", target)):
            seeded_db.add(
                StoreProductAlias(
                    id=uuid4(),
                    product_master_id=UUID(product["id"]),
                    store_chain=chain,
                    receipt_name="ATRIA JAUHELIHA",
                )
            )
        await seeded_db.commit()

        response = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        assert response.json()["dropped"]["store_product_alias"] == 0
        assert (
            await count_referencing(seeded_db, StoreProductAlias, UUID(target["id"]))
            == 2
        )


class TestMergeBroadcasts:
    """A mutating endpoint tells the iPad what changed (CLAUDE.md)."""

    async def test_the_moved_inventory_items_are_broadcast(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates
        item = await add_inventory_item(seeded_db, UUID(source["id"]))

        with patch(
            "app.api.endpoints.products.broadcast_inventory_update",
            new_callable=AsyncMock,
        ) as broadcast:
            await client.post(
                f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
            )

        broadcast.assert_awaited_once()
        kwargs = broadcast.await_args.kwargs
        assert kwargs["inventory_item_id"] == item.id
        assert kwargs["action"] == "updated"
        # The item now belongs to the surviving product, and says so.
        assert kwargs["product_name"] == "Ground Beef"

    async def test_nothing_is_broadcast_when_no_stock_moved(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates

        with patch(
            "app.api.endpoints.products.broadcast_inventory_update",
            new_callable=AsyncMock,
        ) as broadcast:
            await client.post(
                f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
            )

        broadcast.assert_not_awaited()


class TestMergeUnblocksDelete:
    """The relationship H16 exists for: 409 on delete, merge, gone."""

    async def test_a_product_that_cannot_be_deleted_can_be_merged(
        self, client: AsyncClient, seeded_db: AsyncSession, duplicates
    ) -> None:
        source, target = duplicates
        await add_inventory_item(seeded_db, UUID(source["id"]))

        refused = await client.delete(f"/api/products/{source['id']}")
        merged = await client.post(
            f"/api/products/{source['id']}/merge", json={"target_id": target["id"]}
        )

        assert refused.status_code == 409
        assert merged.status_code == 200
        assert (await client.get(f"/api/products/{source['id']}")).status_code == 404
