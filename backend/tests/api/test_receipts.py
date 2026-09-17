"""Tests for Receipt API endpoints."""

import shutil
from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import UUID

import anyio
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.worker.receipt_worker import run_once


@pytest.fixture
async def test_db(db_session: AsyncSession):
    """Provide a test database session with dependency override and cleanup test receipts."""

    # Override the dependency to use test database session
    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    yield db_session

    # Clean up
    app.dependency_overrides.clear()

    # Clean up test receipt files
    receipts_dir = anyio.Path("data/receipts")
    if await receipts_dir.exists():
        shutil.rmtree(str(receipts_dir))
        await receipts_dir.mkdir(parents=True, exist_ok=True)


class TestUploadReceipt:
    """Test POST /api/receipts/scan endpoint."""

    async def test_upload_receipt_image_success(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should successfully upload an image file."""
        # Create a fake image file
        file_content = b"fake image content"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
        data = {"store_chain": "S-Market", "purchase_date": "2024-01-05"}

        response = await client.post("/api/receipts/scan", files=files, data=data)

        assert response.status_code == 201
        receipt = response.json()
        assert "id" in receipt
        assert receipt["store_chain"] == "S-Market"
        assert receipt["purchase_date"] == "2024-01-05"
        assert receipt["processing_status"] == "queued"
        assert "image_path" in receipt
        assert receipt["items_extracted"] == 0
        assert receipt["items_matched"] == 0

    async def test_upload_receipt_pdf_success(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should successfully upload a PDF file."""
        file_content = b"%PDF-1.4 fake pdf content"
        files = {"file": ("receipt.pdf", BytesIO(file_content), "application/pdf")}
        data = {"store_chain": "K-Citymarket", "purchase_date": "2024-01-04"}

        response = await client.post("/api/receipts/scan", files=files, data=data)

        assert response.status_code == 201
        receipt = response.json()
        assert receipt["store_chain"] == "K-Citymarket"
        assert receipt["processing_status"] == "queued"
        assert receipt["image_path"].endswith(".pdf")

    async def test_upload_receipt_without_metadata(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should work without optional metadata."""
        file_content = b"fake image content"
        files = {"file": ("receipt.png", BytesIO(file_content), "image/png")}

        response = await client.post("/api/receipts/scan", files=files)

        assert response.status_code == 201
        receipt = response.json()
        assert receipt["store_chain"] is None
        assert receipt["purchase_date"] is None
        assert receipt["processing_status"] == "queued"

    async def test_upload_receipt_no_file(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should return 422 when no file is provided."""
        response = await client.post("/api/receipts/scan")

        assert response.status_code == 422

    async def test_upload_receipt_invalid_file_type(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should reject invalid file types."""
        file_content = b"fake text file"
        files = {"file": ("receipt.txt", BytesIO(file_content), "text/plain")}

        response = await client.post("/api/receipts/scan", files=files)

        assert response.status_code == 400
        assert "detail" in response.json()
        assert "file type" in response.json()["detail"].lower()

    async def test_upload_receipt_stores_file(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should save the file to disk."""
        file_content = b"fake image content for storage test"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}

        response = await client.post("/api/receipts/scan", files=files)

        assert response.status_code == 201
        receipt = response.json()

        # Verify file path exists
        file_path = anyio.Path(receipt["image_path"])
        assert await file_path.exists()

        # Verify file content matches
        assert await file_path.read_bytes() == file_content


class TestGetReceipt:
    """Test GET /api/receipts/{id} endpoint."""

    async def test_get_receipt_by_id(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts/{id} should return specific receipt."""
        # First create a receipt
        file_content = b"fake image"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
        data = {"store_chain": "Lidl", "purchase_date": "2024-01-03"}

        create_response = await client.post(
            "/api/receipts/scan", files=files, data=data
        )
        receipt_id = create_response.json()["id"]

        # Now get it
        response = await client.get(f"/api/receipts/{receipt_id}")

        assert response.status_code == 200
        receipt = response.json()
        assert receipt["id"] == receipt_id
        assert receipt["store_chain"] == "Lidl"
        assert receipt["purchase_date"] == "2024-01-03"
        assert receipt["processing_status"] == "queued"

    async def test_get_receipt_not_found(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts/{id} should return 404 for non-existent receipt."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/receipts/{fake_uuid}")

        assert response.status_code == 404
        assert "detail" in response.json()

    async def test_get_receipt_invalid_uuid(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts/{id} should return 422 for invalid UUID."""
        response = await client.get("/api/receipts/not-a-uuid")

        assert response.status_code == 422


class TestListReceipts:
    """Test GET /api/receipts endpoint."""

    async def test_list_receipts_empty(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts should return empty list when no receipts exist."""
        response = await client.get("/api/receipts")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_list_receipts_returns_all_receipts(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts should return all receipts."""
        # Create multiple receipts
        for i in range(3):
            file_content = f"fake image {i}".encode()
            files = {"file": (f"receipt{i}.jpg", BytesIO(file_content), "image/jpeg")}
            data = {"store_chain": f"Store{i}"}
            await client.post("/api/receipts/scan", files=files, data=data)

        response = await client.get("/api/receipts")

        assert response.status_code == 200
        receipts = response.json()
        assert len(receipts) == 3
        assert all("id" in r for r in receipts)
        assert all("store_chain" in r for r in receipts)

    async def test_list_receipts_sorted_by_created_at(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts should return receipts sorted by created_at descending."""
        # Create receipts
        for i in range(3):
            file_content = f"fake image {i}".encode()
            files = {"file": (f"receipt{i}.jpg", BytesIO(file_content), "image/jpeg")}
            await client.post("/api/receipts/scan", files=files)

        response = await client.get("/api/receipts")

        assert response.status_code == 200
        receipts = response.json()

        # Most recent should be first (descending order)
        created_dates = [r["created_at"] for r in receipts]
        assert created_dates == sorted(created_dates, reverse=True)

    async def test_list_receipts_filter_by_status(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts should support filtering by processing_status."""
        # Create a receipt
        file_content = b"fake image"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
        await client.post("/api/receipts/scan", files=files)

        response = await client.get("/api/receipts?status=queued")

        assert response.status_code == 200
        receipts = response.json()
        assert len(receipts) == 1
        assert receipts[0]["processing_status"] == "queued"

    async def test_list_receipts_filter_by_store(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts should support filtering by store_chain."""
        # Create receipts from different stores
        # Distinct bytes per upload: identical files are rejected as duplicates (MVP-T1)
        for n, store in enumerate(["S-Market", "K-Citymarket", "S-Market"]):
            file_content = f"fake image {store} {n}".encode()
            files = {
                "file": (f"receipt_{store}.jpg", BytesIO(file_content), "image/jpeg")
            }
            data = {"store_chain": store}
            await client.post("/api/receipts/scan", files=files, data=data)

        response = await client.get("/api/receipts?store=S-Market")

        assert response.status_code == 200
        receipts = response.json()
        assert len(receipts) == 2
        assert all(r["store_chain"] == "S-Market" for r in receipts)


class TestProcessReceipt:
    """MVP-R3: uploads are queued; the worker reads them; /process only re-queues."""

    async def _upload(
        self, client: AsyncClient, content: bytes = b"fake receipt"
    ) -> str:
        files = {"file": ("receipt.jpg", BytesIO(content), "image/jpeg")}
        return (await client.post("/api/receipts/scan", files=files)).json()["id"]

    async def _set_status(
        self, db: AsyncSession, receipt_id: str, status: str, **fields
    ):
        from app.models.receipt import Receipt

        receipt = await db.get(Receipt, UUID(receipt_id))
        receipt.processing_status = status
        for name, value in fields.items():
            setattr(receipt, name, value)
        await db.commit()

    async def test_queued_upload_is_read_by_the_worker(
        self, client: AsyncClient, test_db: AsyncSession, session_factory
    ) -> None:
        receipt_id = await self._upload(client)
        extraction = ReceiptExtraction(
            method="text",
            store_chain="S-MARKET",
            lines=[ExtractedLine(name="Valio Milk 1L", quantity=1.0)],
        )

        with (
            patch(
                "app.services.receipt_processing.extract_text_from_receipt",
                new_callable=AsyncMock,
                return_value="S-MARKET\nVALIO MILK 1L  2.49\nTOTAL  2.49",
            ),
            patch(
                "app.services.receipt_processing.extract_from_text",
                new_callable=AsyncMock,
                return_value=extraction,
            ),
        ):
            assert await run_once(session_factory) is True

        receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
        assert receipt["processing_status"] == "completed"
        assert receipt["items_extracted"] == 1
        assert receipt["ocr_raw_text"] is not None
        assert receipt["error"] is None
        assert receipt["processing_started_at"] is not None

    async def test_process_never_runs_the_pipeline(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        receipt_id = await self._upload(client)
        await self._set_status(test_db, receipt_id, "failed", error="LLM timed out")

        with patch(
            "app.services.receipt_processing.ReceiptProcessingService.process_receipt",
            side_effect=AssertionError("pipeline ran inside the request"),
        ):
            response = await client.post(f"/api/receipts/{receipt_id}/process")

        assert response.status_code == 202
        body = response.json()
        assert body["processing_status"] == "queued"
        assert body["error"] is None
        assert body["queued_at"] is not None

    async def test_legacy_uploaded_receipt_can_be_queued(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        receipt_id = await self._upload(client)
        await self._set_status(test_db, receipt_id, "uploaded", queued_at=None)

        response = await client.post(f"/api/receipts/{receipt_id}/process")

        assert response.status_code == 202
        assert response.json()["processing_status"] == "queued"

    @pytest.mark.parametrize(
        ("status", "message"),
        [
            ("queued", "already queued or processing"),
            ("processing", "already queued or processing"),
            ("completed", "already read"),
            ("confirmed", "already read"),
        ],
    )
    async def test_process_conflicts(
        self, client: AsyncClient, test_db: AsyncSession, status: str, message: str
    ) -> None:
        receipt_id = await self._upload(client)
        fields = (
            {"processing_started_at": datetime.now(UTC)}
            if status == "processing"
            else {}
        )
        await self._set_status(test_db, receipt_id, status, **fields)

        response = await client.post(f"/api/receipts/{receipt_id}/process")

        assert response.status_code == 409
        assert message in response.json()["detail"]

    async def test_heuristic_receipt_reports_its_method_and_can_be_reread(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """MVP-R3b: a receipt read by the fallback parser can be queued for the model again."""
        receipt_id = await self._upload(client)
        await self._set_status(
            test_db,
            receipt_id,
            "completed",
            ocr_structured={
                "method": "heuristic",
                "fallback_reason": "Model unavailable: timed out",
                "lines": [{"name": "MAITO", "quantity": 1}],
            },
        )

        body = (await client.get(f"/api/receipts/{receipt_id}")).json()
        assert body["extraction_method"] == "heuristic"
        assert body["fallback_reason"] == "Model unavailable: timed out"
        assert [item["name"] for item in body["items"]] == ["MAITO"]

        retry = await client.post(f"/api/receipts/{receipt_id}/process")
        assert retry.status_code == 202
        assert retry.json()["processing_status"] == "queued"

    @pytest.mark.parametrize(
        ("status", "method"),
        [("completed", "text"), ("confirmed", "heuristic")],
    )
    async def test_only_unconfirmed_heuristic_receipts_can_be_reread(
        self, client: AsyncClient, test_db: AsyncSession, status: str, method: str
    ) -> None:
        receipt_id = await self._upload(client)
        await self._set_status(
            test_db, receipt_id, status, ocr_structured={"method": method, "lines": []}
        )

        response = await client.post(f"/api/receipts/{receipt_id}/process")

        assert response.status_code == 409
        assert "already read" in response.json()["detail"]

    async def test_process_receipt_not_found(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.post(f"/api/receipts/{fake_uuid}/process")

        assert response.status_code == 404

    async def test_stale_processing_reads_as_failed_and_can_be_retried(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        receipt_id = await self._upload(client)
        await self._set_status(
            test_db,
            receipt_id,
            "processing",
            processing_started_at=datetime.now(UTC) - timedelta(minutes=11),
        )

        receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
        assert receipt["processing_status"] == "failed"
        assert "did not finish" in receipt["error"]

        listed = (await client.get("/api/receipts")).json()
        assert listed[0]["processing_status"] == "failed"

        retry = await client.post(f"/api/receipts/{receipt_id}/process")
        assert retry.status_code == 202


class TestReceiptItems:
    """MVP-R1b: GET /api/receipts/{id} exposes typed, matched items."""

    async def _catalog(self, db: AsyncSession):
        from uuid import uuid4

        from app.models.category import Category
        from app.models.product_master import ProductMaster

        for cid, name in [
            ("dairy", "Dairy & Eggs"),
            ("produce", "Vegetables"),
            ("frozen", "Frozen"),
        ]:
            db.add(
                Category(
                    id=cid,
                    display_name=name,
                    icon=None,
                    default_shelf_life_days=7,
                    meal_contexts=[],
                    sort_order=1,
                )
            )
        await db.flush()
        # Stored as pantry on purpose: a matched item's location follows the product
        product = ProductMaster(
            id=uuid4(),
            canonical_name="BARISTA KAURAJUOMA",
            category="dairy",
            storage_type="pantry",
            default_shelf_life_days=90,
            unit_type="count",
            default_unit="pcs",
        )
        db.add(product)
        await db.commit()
        return product

    async def test_processed_receipt_returns_items(
        self, client: AsyncClient, test_db: AsyncSession, session_factory
    ) -> None:
        from unittest.mock import AsyncMock, patch

        from app.parsers.base import ExtractedLine, ReceiptExtraction

        product = await self._catalog(test_db)
        files = {"file": ("receipt.pdf", BytesIO(b"%PDF fake"), "application/pdf")}
        receipt_id = (await client.post("/api/receipts/scan", files=files)).json()["id"]

        extraction = ReceiptExtraction(
            method="text",
            store_chain="Prisma ruoan verkkokauppa",
            lines=[
                ExtractedLine(
                    name="BARISTA KAURAJUOMA",
                    generic_name="Oat drink",
                    quantity=3,
                    category="dairy",
                ),
                ExtractedLine(
                    name="PUNASIPULI", quantity=1, weight_kg=0.33, category="produce"
                ),
                ExtractedLine(name="PAKASTEHERNE", quantity=1, category="frozen"),
                ExtractedLine(name="SIENILIINA", quantity=2, category=None),
            ],
        )
        with (
            patch(
                "app.services.receipt_processing.extract_text_from_receipt",
                new_callable=AsyncMock,
                return_value="text",
            ),
            patch(
                "app.services.receipt_processing.extract_from_text",
                new_callable=AsyncMock,
                return_value=extraction,
            ),
        ):
            await run_once(session_factory)

        body = (await client.get(f"/api/receipts/{receipt_id}")).json()

        assert body["processing_status"] == "completed"
        assert body["store_chain"] == "s-group"
        assert body["extraction_method"] == "text"
        oat, onion, peas, cloth = body["items"]

        assert oat == {
            "index": 0,
            "name": "BARISTA KAURAJUOMA",
            "generic_name": "Oat drink",
            "quantity": 3.0,
            "unit": "pcs",
            "product_id": str(product.id),
            "product_name": "BARISTA KAURAJUOMA",
            "match_score": 100.0,
            "match_confidence": "exact",
            "match_source": "exact",
            "suggested_category": "dairy",
            "piece_grams": None,
            "shelf_life_days": None,
            "printed_quantity": None,
            "printed_unit": None,
            "storage_type": "pantry",
            "location": "pantry",
        }
        # No piece weight was read, so a weighed line stays in grams
        assert (onion["quantity"], onion["unit"]) == (330.0, "g")
        assert onion["product_id"] is None
        assert (onion["storage_type"], onion["location"]) == (
            "refrigerator",
            "main_fridge",
        )
        assert (peas["storage_type"], peas["location"]) == ("freezer", "freezer")
        assert cloth["suggested_category"] is None
        assert (cloth["quantity"], cloth["unit"], cloth["location"]) == (
            2.0,
            "pcs",
            "main_fridge",
        )
        assert [item["index"] for item in body["items"]] == [0, 1, 2, 3]

    async def test_unprocessed_receipt_has_no_items(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        files = {"file": ("receipt.jpg", BytesIO(b"img"), "image/jpeg")}
        body = (await client.post("/api/receipts/scan", files=files)).json()

        assert body["items"] == []
        assert body["extraction_method"] is None

    async def test_unknown_status_filter_is_rejected(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await client.get("/api/receipts?status=pending")
        assert response.status_code == 422


class TestDuplicateUploads:
    """MVP-T1: the same file uploaded twice returns the existing receipt."""

    async def test_second_upload_of_the_same_file_is_409_with_existing_id(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        content = b"%PDF-1.4 order 1089366829"
        first = await client.post(
            "/api/receipts/scan",
            files={"file": ("order.pdf", BytesIO(content), "application/pdf")},
        )
        second = await client.post(
            "/api/receipts/scan",
            files={"file": ("order-copy.pdf", BytesIO(content), "application/pdf")},
        )

        assert first.status_code == 201
        assert first.json()["content_sha256"]
        assert second.status_code == 409
        assert second.json()["detail"] == {
            "message": "Receipt already uploaded",
            "receipt_id": first.json()["id"],
        }


class TestReceiptsListPayload:
    """MVP-R8: the list is polled from the iPad, so it stays small and pageable."""

    async def _upload(self, client: AsyncClient, n: int) -> None:
        files = {
            "file": (f"r{n}.jpg", BytesIO(f"fake image {n}".encode()), "image/jpeg")
        }
        await client.post("/api/receipts/scan", files=files)

    async def test_list_leaves_out_the_ocr_payload(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """Full OCR text and items are tens of kilobytes each; the list must not carry them."""
        await self._upload(client, 0)

        listed = (await client.get("/api/receipts")).json()

        assert len(listed) == 1
        summary = listed[0]
        for heavy in ("ocr_raw_text", "ocr_structured", "items"):
            assert heavy not in summary
        # What the list page actually renders is still there
        for field in (
            "id",
            "store_chain",
            "purchase_date",
            "processing_status",
            "error",
            "items_extracted",
            "items_matched",
            "extraction_method",
            "created_at",
        ):
            assert field in summary

    async def test_detail_still_carries_the_full_payload(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """The review page needs the items; only the list was slimmed."""
        await self._upload(client, 0)
        receipt_id = (await client.get("/api/receipts")).json()[0]["id"]

        detail = (await client.get(f"/api/receipts/{receipt_id}")).json()

        assert "items" in detail
        assert "ocr_raw_text" in detail

    async def test_limit_and_offset_page_through_newest_first(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        for n in range(3):
            await self._upload(client, n)

        everything = (await client.get("/api/receipts")).json()
        first = (await client.get("/api/receipts?limit=2")).json()
        rest = (await client.get("/api/receipts?limit=2&offset=2")).json()

        assert [r["id"] for r in first] == [r["id"] for r in everything[:2]]
        assert [r["id"] for r in rest] == [r["id"] for r in everything[2:]]

    @pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
    async def test_rejects_an_out_of_range_page(
        self, client: AsyncClient, test_db: AsyncSession, query: str
    ) -> None:
        """An unbounded list would ship every receipt ever read."""
        response = await client.get(f"/api/receipts?{query}")

        assert response.status_code == 422


class TestWeighedProduceBecomesPieces:
    """Q2: a shop sells apples by the kilo; the review screen should offer them as apples."""

    async def _receipt(self, client: AsyncClient, session_factory, lines) -> dict:
        files = {"file": ("apples.pdf", BytesIO(b"%PDF apples"), "application/pdf")}
        receipt_id = (await client.post("/api/receipts/scan", files=files)).json()["id"]
        extraction = ReceiptExtraction(
            method="text", store_chain="S-Market", lines=lines
        )
        with (
            patch(
                "app.services.receipt_processing.extract_text_from_receipt",
                new_callable=AsyncMock,
                return_value="text",
            ),
            patch(
                "app.services.receipt_processing.extract_from_text",
                new_callable=AsyncMock,
                return_value=extraction,
            ),
        ):
            await run_once(session_factory)
        return (await client.get(f"/api/receipts/{receipt_id}")).json()

    async def test_a_weighed_line_with_a_piece_weight_is_offered_as_pieces(
        self, client: AsyncClient, test_db: AsyncSession, session_factory
    ) -> None:
        body = await self._receipt(
            client,
            session_factory,
            [
                ExtractedLine(
                    name="KG OMENA GOLDEN",
                    generic_name="Apple",
                    quantity=1,
                    weight_kg=1.072,
                    category="produce",
                    piece_grams=125,
                    shelf_life_days=21,
                )
            ],
        )

        (apple,) = body["items"]
        assert (apple["quantity"], apple["unit"]) == (9.0, "pcs")
        # and what the receipt actually said is still there to show and to override
        assert (apple["printed_quantity"], apple["printed_unit"]) == (1072.0, "g")
        assert apple["piece_grams"] == 125
        assert apple["shelf_life_days"] == 21

    async def test_without_a_piece_weight_the_line_stays_in_grams(
        self, client: AsyncClient, test_db: AsyncSession, session_factory
    ) -> None:
        body = await self._receipt(
            client,
            session_factory,
            [
                ExtractedLine(
                    name="NAUDAN JAUHELIHA",
                    generic_name="Ground beef",
                    quantity=1,
                    weight_kg=0.4,
                    category="meat",
                )
            ],
        )

        (mince,) = body["items"]
        assert (mince["quantity"], mince["unit"]) == (400.0, "g")
        assert mince["printed_quantity"] is None
