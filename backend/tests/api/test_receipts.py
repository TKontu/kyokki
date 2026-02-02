"""Tests for Receipt API endpoints."""
import shutil
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app


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
    receipts_dir = Path("data/receipts")
    if receipts_dir.exists():
        shutil.rmtree(receipts_dir)
        receipts_dir.mkdir(parents=True, exist_ok=True)


class TestUploadReceipt:
    """Test POST /api/receipts/scan endpoint."""

    async def test_upload_receipt_image_success(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should successfully upload an image file."""
        # Create a fake image file
        file_content = b"fake image content"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
        data = {
            "store_chain": "S-Market",
            "purchase_date": "2024-01-05"
        }

        response = await client.post("/api/receipts/scan", files=files, data=data)

        assert response.status_code == 201
        receipt = response.json()
        assert "id" in receipt
        assert receipt["store_chain"] == "S-Market"
        assert receipt["purchase_date"] == "2024-01-05"
        assert receipt["processing_status"] == "uploaded"
        assert "image_path" in receipt
        assert receipt["items_extracted"] == 0
        assert receipt["items_matched"] == 0

    async def test_upload_receipt_pdf_success(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/scan should successfully upload a PDF file."""
        file_content = b"%PDF-1.4 fake pdf content"
        files = {"file": ("receipt.pdf", BytesIO(file_content), "application/pdf")}
        data = {
            "store_chain": "K-Citymarket",
            "purchase_date": "2024-01-04"
        }

        response = await client.post("/api/receipts/scan", files=files, data=data)

        assert response.status_code == 201
        receipt = response.json()
        assert receipt["store_chain"] == "K-Citymarket"
        assert receipt["processing_status"] == "uploaded"
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
        assert receipt["processing_status"] == "uploaded"

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
        file_path = Path(receipt["image_path"])
        assert file_path.exists()

        # Verify file content matches
        assert file_path.read_bytes() == file_content


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

        create_response = await client.post("/api/receipts/scan", files=files, data=data)
        receipt_id = create_response.json()["id"]

        # Now get it
        response = await client.get(f"/api/receipts/{receipt_id}")

        assert response.status_code == 200
        receipt = response.json()
        assert receipt["id"] == receipt_id
        assert receipt["store_chain"] == "Lidl"
        assert receipt["purchase_date"] == "2024-01-03"
        assert receipt["processing_status"] == "uploaded"

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

        response = await client.get("/api/receipts?status=uploaded")

        assert response.status_code == 200
        receipts = response.json()
        assert len(receipts) == 1
        assert receipts[0]["processing_status"] == "uploaded"

    async def test_list_receipts_filter_by_store(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """GET /api/receipts should support filtering by store_chain."""
        # Create receipts from different stores
        for store in ["S-Market", "K-Citymarket", "S-Market"]:
            file_content = f"fake image {store}".encode()
            files = {"file": (f"receipt_{store}.jpg", BytesIO(file_content), "image/jpeg")}
            data = {"store_chain": store}
            await client.post("/api/receipts/scan", files=files, data=data)

        response = await client.get("/api/receipts?store=S-Market")

        assert response.status_code == 200
        receipts = response.json()
        assert len(receipts) == 2
        assert all(r["store_chain"] == "S-Market" for r in receipts)


class TestProcessReceipt:
    """Test POST /api/receipts/{id}/process endpoint."""

    async def test_process_receipt_success(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/{id}/process should process receipt through OCR + LLM + matching."""
        from unittest.mock import patch, AsyncMock
        from app.parsers.base import ReceiptExtraction, ParsedProduct, StoreInfo

        # Create a receipt
        file_content = b"fake receipt image"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
        create_response = await client.post("/api/receipts/scan", files=files)
        receipt_id = create_response.json()["id"]

        # Mock OCR and LLM services
        mock_ocr_text = "S-MARKET\nVALIO MILK 1L  2.49\nTOTAL  2.49"
        mock_extraction = ReceiptExtraction(
            store=StoreInfo(name="S-Market", chain="s-group"),
            products=[
                ParsedProduct(name="Valio Milk 1L", quantity=1.0, price=2.49)
            ],
            confidence=0.95,
        )

        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=mock_ocr_text,
        ):
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                return_value=mock_extraction,
            ):
                response = await client.post(f"/api/receipts/{receipt_id}/process")

                assert response.status_code == 200
                result = response.json()
                assert result["success"] is True
                assert result["items_extracted"] == 1
                # items_matched may be 0 if no matching products in DB

    async def test_process_receipt_not_found(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/{id}/process should return 404 for non-existent receipt."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.post(f"/api/receipts/{fake_uuid}/process")

        assert response.status_code == 404

    async def test_process_receipt_updates_status(
        self, client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """POST /api/receipts/{id}/process should update receipt processing_status."""
        from unittest.mock import patch, AsyncMock
        from app.parsers.base import ReceiptExtraction, StoreInfo

        # Create a receipt
        file_content = b"fake receipt"
        files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
        create_response = await client.post("/api/receipts/scan", files=files)
        receipt_id = create_response.json()["id"]

        mock_extraction = ReceiptExtraction(
            store=StoreInfo(),
            products=[],
            confidence=0.9,
        )

        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value="text",
        ):
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                return_value=mock_extraction,
            ):
                await client.post(f"/api/receipts/{receipt_id}/process")

                # Check receipt status was updated
                get_response = await client.get(f"/api/receipts/{receipt_id}")
                assert get_response.status_code == 200
                receipt = get_response.json()
                assert receipt["processing_status"] == "completed"
                assert receipt["ocr_raw_text"] is not None
