"""Q26 (item provenance) and Q28 (receipt audit): API endpoints.

``GET /api/inventory/{item_id}/source`` (Q26) and ``GET /api/receipts/{id}/file``,
``GET /api/receipts/{id}/audit`` (Q28).
"""

import shutil
from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import anyio
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.services.generic_products import build_inventory_item

PURCHASED = date(2026, 9, 26)


@pytest.fixture
async def test_db(db_session: AsyncSession):
    """Test database session with dependency override; cleans up receipt files after."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield db_session
    app.dependency_overrides.clear()

    receipts_dir = anyio.Path("data/receipts")
    if await receipts_dir.exists():
        shutil.rmtree(str(receipts_dir))
        await receipts_dir.mkdir(parents=True, exist_ok=True)


@pytest.fixture
async def sample_category(test_db: AsyncSession) -> Category:
    category = Category(
        id="dairy",
        display_name="Dairy",
        icon="🥛",
        default_shelf_life_days=7,
        sort_order=1,
    )
    test_db.add(category)
    await test_db.commit()
    await test_db.refresh(category)
    return category


@pytest.fixture
async def sample_product(
    test_db: AsyncSession, sample_category: Category
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Valio Whole Milk 1L",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
        default_quantity=Decimal("1000"),
    )
    test_db.add(product)
    await test_db.commit()
    await test_db.refresh(product)
    return product


async def _receipt(test_db: AsyncSession, **fields) -> Receipt:
    fields.setdefault("processing_status", "completed")
    fields.setdefault("items_extracted", 0)
    fields.setdefault("items_matched", 0)
    fields.setdefault("image_path", f"data/receipts/{uuid4()}.jpg")
    receipt = Receipt(id=uuid4(), **fields)
    test_db.add(receipt)
    await test_db.commit()
    await test_db.refresh(receipt)
    return receipt


class TestItemSource:
    """GET /api/inventory/{item_id}/source (Q26)."""

    async def test_unknown_item_is_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.get(f"/api/inventory/{uuid4()}/source")
        assert response.status_code == 404

    async def test_hand_added_item_has_no_source(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_product: ProductMaster,
    ):
        item = build_inventory_item(
            sample_product, quantity=Decimal("1"), purchase_date=PURCHASED
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.get(f"/api/inventory/{item.id}/source")

        assert response.status_code == 200
        assert response.json() is None

    async def test_item_with_a_line_names_its_receipt(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_product: ProductMaster,
    ):
        receipt = await _receipt(
            test_db,
            store_chain="s-group",
            purchase_date=PURCHASED,
            processing_status="confirmed",
        )
        item = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        item.receipt_line_index = 1
        item.receipt_line_text = "KOKKIKARTANO KERMAINEN LOHIKEITTO"
        test_db.add(item)
        await test_db.commit()

        response = await client.get(f"/api/inventory/{item.id}/source")

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "receipt_id": str(receipt.id),
            "store_chain": "s-group",
            "purchase_date": "2026-09-26",
            "line_text": "KOKKIKARTANO KERMAINEN LOHIKEITTO",
            "line_index": 1,
        }

    async def test_legacy_item_names_the_receipt_without_a_line(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_product: ProductMaster,
    ):
        receipt = await _receipt(test_db, processing_status="confirmed")
        item = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.get(f"/api/inventory/{item.id}/source")

        assert response.status_code == 200
        body = response.json()
        assert body["receipt_id"] == str(receipt.id)
        assert body["line_index"] is None
        assert body["line_text"] is None


class TestReceiptAudit:
    """GET /api/receipts/{id}/audit (Q28)."""

    async def test_unknown_receipt_is_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.get(f"/api/receipts/{uuid4()}/audit")
        assert response.status_code == 404

    async def test_file_content_type_matches_the_stored_file(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        files = {"file": ("receipt.jpg", BytesIO(b"\xff\xd8\xff"), "image/jpeg")}
        upload = await client.post("/api/receipts/scan", files=files)
        receipt_id = upload.json()["id"]

        response = await client.get(f"/api/receipts/{receipt_id}/audit")

        assert response.status_code == 200
        assert response.json()["file_content_type"] == "image/jpeg"

    async def test_pending_receipt_shows_lines_awaiting_confirm(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        receipt = await _receipt(
            test_db,
            store_chain="s-group",
            purchase_date=PURCHASED,
            ocr_raw_text="VALIO MAITO 1L 1,49\n",
            ocr_structured={
                "lines": [{"name": "VALIO MAITO 1L", "price": 1.49}],
                "raw_completion": '{"lines":[]}',
            },
        )

        response = await client.get(f"/api/receipts/{receipt.id}/audit")

        assert response.status_code == 200
        body = response.json()
        assert body["processing_status"] == "completed"
        assert body["ocr_raw_text"] == "VALIO MAITO 1L 1,49\n"
        assert body["model_raw_answer"] == '{"lines":[]}'
        # The fixture's file was never actually written to disk
        assert body["file_content_type"] is None
        assert body["lines"] == [
            {
                "index": 0,
                "name": "VALIO MAITO 1L",
                "price": 1.49,
                "outcome": "pending",
                "items": [],
            }
        ]
        assert body["unlinked_items"] == []

    async def test_confirmed_receipt_shows_each_lines_outcome(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_product: ProductMaster,
    ):
        receipt = await _receipt(
            test_db,
            processing_status="confirmed",
            ocr_structured={
                "lines": [
                    {"name": "VALIO MAITO 1L", "price": 1.49},
                    {"name": "MUOVIKASSI", "price": 0.10, "non_food": True},
                    {"name": "PIRKKA HERNEET", "price": 0.99},
                ]
            },
        )
        stocked = build_inventory_item(
            sample_product,
            quantity=Decimal("1"),
            purchase_date=PURCHASED,
            receipt_id=receipt.id,
        )
        stocked.receipt_line_index = 0
        stocked.receipt_line_text = "VALIO MAITO 1L"
        test_db.add(stocked)
        await test_db.commit()

        response = await client.get(f"/api/receipts/{receipt.id}/audit")

        assert response.status_code == 200
        body = response.json()
        outcomes = {line["index"]: line["outcome"] for line in body["lines"]}
        assert outcomes == {0: "stocked", 1: "household", 2: "skipped"}
        stocked_line = next(line for line in body["lines"] if line["index"] == 0)
        assert stocked_line["items"] == [
            {
                "id": str(stocked.id),
                "product_id": str(sample_product.id),
                "product_name": sample_product.canonical_name,
            }
        ]

    async def test_a_line_marked_household_in_this_confirm_reads_household(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """A never-seen household line folded away via `non_food_indexes` used to read
        `skipped`: only the non-food *memory* recorded it, nothing said so on this
        receipt. Goes through the real confirm endpoint, then the audit endpoint.
        """
        receipt = await _receipt(
            test_db,
            processing_status="completed",
            ocr_structured={"lines": [{"name": "MUOVIKASSI", "price": 0.10}]},
        )

        confirm = await client.post(
            f"/api/receipts/{receipt.id}/confirm",
            json={"items": [], "non_food_indexes": [0]},
        )
        assert confirm.status_code == 200, confirm.text

        response = await client.get(f"/api/receipts/{receipt.id}/audit")

        assert response.status_code == 200
        assert response.json()["lines"] == [
            {
                "index": 0,
                "name": "MUOVIKASSI",
                "price": 0.10,
                "outcome": "household",
                "items": [],
            }
        ]

    async def test_the_household_mark_is_actually_written_to_the_row(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Mutating `ocr_structured` in place is invisible to SQLAlchemy without
        `flag_modified`; without it the row would look unchanged once reloaded from the
        database, even though the in-process object still shows the mutation.
        """
        receipt = await _receipt(
            test_db,
            processing_status="completed",
            ocr_structured={"lines": [{"name": "MUOVIKASSI", "price": 0.10}]},
        )

        confirm = await client.post(
            f"/api/receipts/{receipt.id}/confirm",
            json={"items": [], "non_food_indexes": [0]},
        )
        assert confirm.status_code == 200, confirm.text

        await test_db.refresh(receipt)
        assert receipt.ocr_structured["lines"][0]["confirmed_non_food"] is True


class TestReceiptFile:
    """GET /api/receipts/{id}/file (Q28). Must not become a path-traversal or arbitrary read."""

    async def test_unknown_receipt_is_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.get(f"/api/receipts/{uuid4()}/file")
        assert response.status_code == 404

    async def test_serves_the_uploaded_file(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        content = b"\xff\xd8\xff fake jpeg bytes"
        files = {"file": ("receipt.jpg", BytesIO(content), "image/jpeg")}
        upload = await client.post("/api/receipts/scan", files=files)
        receipt_id = upload.json()["id"]

        response = await client.get(f"/api/receipts/{receipt_id}/file")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert "inline" in response.headers["content-disposition"]
        assert response.headers["cache-control"].startswith("private")
        assert response.content == content

    async def test_a_missing_file_is_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        receipt = await _receipt(test_db, image_path="data/receipts/does-not-exist.jpg")

        response = await client.get(f"/api/receipts/{receipt.id}/file")

        assert response.status_code == 404

    async def test_a_path_outside_the_upload_dir_is_refused(
        self, client: AsyncClient, test_db: AsyncSession, tmp_path
    ):
        outside = tmp_path / "secret.txt"
        outside.write_text("not a receipt")
        receipt = await _receipt(test_db, image_path=str(outside))

        response = await client.get(f"/api/receipts/{receipt.id}/file")

        assert response.status_code == 404

    async def test_a_traversal_path_is_refused(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        receipt = await _receipt(test_db, image_path="data/receipts/../../etc/hostname")

        response = await client.get(f"/api/receipts/{receipt.id}/file")

        assert response.status_code == 404
