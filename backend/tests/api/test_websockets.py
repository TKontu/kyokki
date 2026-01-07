"""Tests for WebSocket real-time updates endpoint."""
import pytest
import json
from fastapi.testclient import TestClient

from app.main import app
from app.services.websockets import manager


class TestWebSocketConnection:
    """Test WebSocket connection lifecycle."""

    def test_websocket_connect_disconnect(self):
        """Test WebSocket can connect and disconnect."""
        # Clear any existing connections
        manager.active_connections.clear()

        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                # Connection should be established
                assert websocket is not None

                # Manager should have one connection
                assert len(manager.active_connections) == 1

            # After context exits, connection should be removed
            assert len(manager.active_connections) == 0

    def test_multiple_websocket_connections(self):
        """Test multiple WebSocket connections can be established."""
        # Clear any existing connections
        manager.active_connections.clear()

        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as ws1:
                assert len(manager.active_connections) == 1

                with client.websocket_connect("/api/ws") as ws2:
                    assert len(manager.active_connections) == 2

            # After context exits, connections should be removed
            assert len(manager.active_connections) == 0


class TestWebSocketMessageFormat:
    """Test WebSocket message formats."""

    def test_receipt_status_message_structure(self):
        """Test receipt status messages have correct structure."""
        from app.services.broadcast_helpers import _build_message
        from uuid import uuid4

        receipt_id = uuid4()
        message = _build_message(
            message_type="receipt_status",
            entity_id=receipt_id,
            data={
                "receipt_id": receipt_id,
                "status": "completed",
                "items_extracted": 5,
                "items_matched": 3,
                "error": None
            }
        )

        assert message["type"] == "receipt_status"
        assert message["entity_id"] == str(receipt_id)
        assert "timestamp" in message
        assert message["data"]["status"] == "completed"
        assert message["data"]["items_extracted"] == 5
        assert message["data"]["items_matched"] == 3

    def test_inventory_update_message_structure(self):
        """Test inventory update messages have correct structure."""
        from app.services.broadcast_helpers import _build_message
        from uuid import uuid4
        from decimal import Decimal

        item_id = uuid4()
        message = _build_message(
            message_type="inventory_update",
            entity_id=item_id,
            data={
                "inventory_item_id": item_id,
                "action": "consumed",
                "current_quantity": Decimal("750.00"),
                "status": "opened",
                "product_name": "Milk 1L"
            }
        )

        assert message["type"] == "inventory_update"
        assert message["entity_id"] == str(item_id)
        assert "timestamp" in message
        assert message["data"]["action"] == "consumed"
        assert message["data"]["current_quantity"] == "750.00"
        assert message["data"]["status"] == "opened"
        assert message["data"]["product_name"] == "Milk 1L"

    def test_value_serialization(self):
        """Test that UUIDs and Decimals are serialized correctly."""
        from app.services.broadcast_helpers import _serialize_value
        from uuid import uuid4
        from decimal import Decimal
        from datetime import datetime, timezone

        test_uuid = uuid4()
        test_decimal = Decimal("123.45")
        test_datetime = datetime.now(timezone.utc)

        assert _serialize_value(test_uuid) == str(test_uuid)
        assert _serialize_value(test_decimal) == str(test_decimal)
        assert isinstance(_serialize_value(test_datetime), str)
        assert _serialize_value("string") == "string"
        assert _serialize_value(42) == 42


class TestConnectionManagerBroadcast:
    """Test ConnectionManager broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_to_disconnected_client_removes_it(self):
        """Test that broadcast removes disconnected clients."""
        from app.services.websockets import ConnectionManager
        from unittest.mock import AsyncMock, MagicMock

        # Create a fresh manager for this test
        test_manager = ConnectionManager()

        # Create mock websockets
        mock_ws1 = MagicMock()
        mock_ws1.send_text = AsyncMock()  # Working connection
        mock_ws2 = MagicMock()
        mock_ws2.send_text = AsyncMock(side_effect=Exception("Connection closed"))  # Broken connection

        # Add both to manager
        test_manager.active_connections = [mock_ws1, mock_ws2]

        # Broadcast a message
        await test_manager.broadcast("test message")

        # Only the working connection should remain
        assert len(test_manager.active_connections) == 1
        assert test_manager.active_connections[0] == mock_ws1

    @pytest.mark.asyncio
    async def test_broadcast_json(self):
        """Test that broadcast_json sends proper JSON."""
        from app.services.websockets import ConnectionManager
        from unittest.mock import AsyncMock, MagicMock

        test_manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        test_manager.active_connections = [mock_ws]

        test_data = {"type": "test", "data": "value"}
        await test_manager.broadcast_json(test_data)

        # Verify send_text was called with JSON string
        mock_ws.send_text.assert_called_once()
        call_arg = mock_ws.send_text.call_args[0][0]
        assert json.loads(call_arg) == test_data
