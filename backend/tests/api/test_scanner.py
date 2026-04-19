"""Tests for Scanner API endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.db.session import get_db
from app.main import app
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.off_service import OffApiError, OffProductNotFoundError


@pytest.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    """Database session with seeded categories and app dependency override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    await seed_categories(db_session)
    await db_session.commit()
    yield db_session
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    """Mock Redis client with common scanner key operations."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.keys = AsyncMock(return_value=[])
    return redis


@pytest.fixture
def off_enriched_data():
    """Sample OFF enrichment response."""
    return {
        "canonical_name": "Valio Whole Milk 1L",
        "category": "dairy",
        "off_product_id": "5901234123457",
        "off_data": {"product_name": "Whole Milk", "brands": "Valio"},
    }


class TestScanBarcodeAdd:
    """Tests for POST /api/scanner/scan in add mode."""

    async def test_scan_new_product_from_off_returns_201(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        mock_redis: AsyncMock,
        off_enriched_data: dict,
    ) -> None:
        """Scanning an unknown barcode creates product from OFF and returns 201."""
        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.scanner_service.enrich_product_from_off",
                return_value=off_enriched_data,
            ),
            patch(
                "app.services.broadcast_helpers.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "5901234123457", "mode": "add"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "product_created_and_added"
        assert data["product"]["canonical_name"] == "Valio Whole Milk 1L"
        assert data["inventory_item"] is not None
        assert "Added" in data["message"]

    async def test_scan_existing_product_returns_200(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        sample_product: ProductMaster,
        mock_redis: AsyncMock,
    ) -> None:
        """Scanning a known barcode adds to inventory and returns 200."""
        # Give sample product a barcode
        sample_product.off_product_id = "1234567890123"
        await seeded_db.commit()

        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.broadcast_helpers.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "1234567890123", "mode": "add"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "inventory_added"
        assert data["product"]["canonical_name"] == "Test Milk 1L"

    async def test_scan_product_not_found_returns_404(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        mock_redis: AsyncMock,
    ) -> None:
        """Scanning an unknown barcode not in OFF returns 404."""
        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.scanner_service.enrich_product_from_off",
                side_effect=OffProductNotFoundError("0000000000000"),
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "0000000000000", "mode": "add"},
            )

        assert response.status_code == 404

    async def test_scan_off_unavailable_returns_503(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        mock_redis: AsyncMock,
    ) -> None:
        """When OFF is down and product not local, returns 503."""
        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.scanner_service.enrich_product_from_off",
                side_effect=OffApiError("Service unavailable"),
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "9999999999999", "mode": "add"},
            )

        assert response.status_code == 503

    async def test_scan_empty_barcode_returns_400(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
    ) -> None:
        """Empty barcode returns 400."""
        response = await client.post(
            "/api/scanner/scan",
            json={"barcode": "  ", "mode": "add"},
        )
        assert response.status_code == 400

    async def test_scan_invalid_mode_returns_400(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
    ) -> None:
        """Invalid mode returns 400."""
        response = await client.post(
            "/api/scanner/scan",
            json={"barcode": "1234567890123", "mode": "invalid_mode"},
        )
        assert response.status_code == 400

    async def test_scan_uses_redis_mode_when_no_mode_in_request(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        sample_product: ProductMaster,
        mock_redis: AsyncMock,
    ) -> None:
        """Mode falls back to Redis global mode when not in request."""
        sample_product.off_product_id = "1111111111111"
        await seeded_db.commit()

        # Redis returns "add" as global mode
        mock_redis.get = AsyncMock(return_value=b"add")

        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.broadcast_helpers.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "1111111111111"},
            )

        assert response.status_code == 200
        assert response.json()["action"] == "inventory_added"


class TestScanBarcodeConsume:
    """Tests for POST /api/scanner/scan in consume mode."""

    async def test_scan_consume_reduces_inventory(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        sample_product: ProductMaster,
        mock_redis: AsyncMock,
    ) -> None:
        """Scanning in consume mode reduces inventory quantity."""
        from datetime import date, timedelta

        sample_product.off_product_id = "2222222222222"
        await seeded_db.commit()

        # Create inventory item
        inv = InventoryItem(
            id=uuid4(),
            product_master_id=sample_product.id,
            initial_quantity=Decimal("1000"),
            current_quantity=Decimal("1000"),
            unit="ml",
            status="sealed",
            expiry_date=date.today() + timedelta(days=7),
        )
        seeded_db.add(inv)
        await seeded_db.commit()

        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.broadcast_helpers.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "2222222222222", "mode": "consume", "quantity": "250"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "inventory_consumed"
        assert data["inventory_item"]["current_quantity"] == "750"

    async def test_scan_consume_no_inventory_returns_404(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        sample_product: ProductMaster,
        mock_redis: AsyncMock,
    ) -> None:
        """Consuming a product with no active inventory returns 404."""
        sample_product.off_product_id = "3333333333333"
        await seeded_db.commit()

        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "3333333333333", "mode": "consume"},
            )

        assert response.status_code == 404
        assert "inventory" in response.json()["detail"].lower()

    async def test_scan_consume_unknown_product_returns_404(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        mock_redis: AsyncMock,
    ) -> None:
        """Consuming an unknown product returns 404."""
        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "4444444444444", "mode": "consume"},
            )

        assert response.status_code == 404


class TestScanBarcodeLookup:
    """Tests for POST /api/scanner/scan in lookup mode."""

    async def test_lookup_local_product(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        sample_product: ProductMaster,
        mock_redis: AsyncMock,
    ) -> None:
        """Lookup returns product info without creating inventory."""
        sample_product.off_product_id = "5555555555555"
        await seeded_db.commit()

        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "5555555555555", "mode": "lookup"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "lookup"
        assert data["inventory_item"] is None

    async def test_lookup_from_off_when_not_local(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        mock_redis: AsyncMock,
    ) -> None:
        """Lookup fetches from OFF without writing to DB."""
        off_product_data = {"product": {"product_name": "Remote Product"}, "status": 1}

        with (
            patch(
                "app.services.scanner_service.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.services.scanner_service.fetch_product_from_off",
                return_value=off_product_data,
            ),
        ):
            response = await client.post(
                "/api/scanner/scan",
                json={"barcode": "6666666666666", "mode": "lookup"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "lookup"
        assert data["product"]["canonical_name"] == "Remote Product"
        assert data["inventory_item"] is None


class TestScannerMode:
    """Tests for GET/POST /api/scanner/mode."""

    async def test_get_mode_returns_default_add(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """Default mode is 'add' when Redis has no value."""
        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.get("/api/scanner/mode")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "add"
        assert data["is_global"] is True

    async def test_get_mode_per_station(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """Per-station mode is returned when set."""
        mock_redis.get = AsyncMock(return_value=b"consume")

        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.get(
                "/api/scanner/mode", params={"station_id": "kitchen-pi"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "consume"
        assert data["is_global"] is False
        assert data["station_id"] == "kitchen-pi"

    async def test_get_mode_falls_back_to_global(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """When station has no mode, falls back to global."""

        # Station key returns None, global key returns "lookup"
        async def mock_get(key: str):
            if "kitchen-pi" in key:
                return None
            return b"lookup"

        mock_redis.get = mock_get

        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.get(
                "/api/scanner/mode", params={"station_id": "kitchen-pi"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "lookup"
        assert data["is_global"] is True

    async def test_set_global_mode(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """Setting global mode stores in Redis and returns confirmation."""
        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.post("/api/scanner/mode", json={"mode": "consume"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "consume"
        assert data["station_id"] is None
        mock_redis.set.assert_called_once()

    async def test_set_per_station_mode(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """Setting per-station mode stores station-specific key."""
        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.post(
                "/api/scanner/mode",
                json={"mode": "consume", "station_id": "pantry-pi"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["station_id"] == "pantry-pi"
        # Verify station-specific key was used
        call_args = mock_redis.set.call_args[0]
        assert "pantry-pi" in call_args[0]

    async def test_set_invalid_mode_returns_400(self, client: AsyncClient) -> None:
        """Invalid mode value returns 400."""
        response = await client.post("/api/scanner/mode", json={"mode": "dance"})
        assert response.status_code == 400


class TestScannerStations:
    """Tests for GET /api/scanner/stations."""

    async def test_empty_stations(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """Returns empty list when no stations active."""
        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.get("/api/scanner/stations")

        assert response.status_code == 200
        data = response.json()
        assert data["stations"] == []
        assert data["total_stations"] == 0
        assert data["online_stations"] == 0

    async def test_stations_listed_after_scan(
        self, client: AsyncClient, mock_redis: AsyncMock
    ) -> None:
        """Station appears in list after a scan is recorded."""
        mock_redis.keys = AsyncMock(return_value=[b"scanner:station:kitchen-pi:online"])

        async def mock_get(key: str):
            key_str = key if isinstance(key, str) else key.decode()
            if "last_scan" in key_str:
                return b"2026-04-19T10:00:00+00:00"
            if "scan_count" in key_str:
                return b"5"
            if "online" in key_str:
                return b"true"
            if "mode" in key_str:
                return b"add"
            return None

        mock_redis.get = mock_get

        with patch(
            "app.services.scanner_service.get_redis_client",
            return_value=mock_redis,
        ):
            response = await client.get("/api/scanner/stations")

        assert response.status_code == 200
        data = response.json()
        assert data["total_stations"] == 1
        assert data["online_stations"] == 1
        station = data["stations"][0]
        assert station["station_id"] == "kitchen-pi"
        assert station["mode"] == "add"
        assert station["scan_count"] == 5
        assert station["online"] is True
