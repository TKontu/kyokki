"""Thin Telegram Bot API client over httpx."""

import json

import httpx
import pytest

from app.telegram_bot.client import TelegramClient, TelegramError

TOKEN = "123456:TEST-token-must-not-leak"
BASE = "https://telegram.test"


def _client(handler) -> TelegramClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TelegramClient(token=TOKEN, base_url=BASE, http=http)


async def test_get_updates_sends_offset_and_timeout():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})

    updates = await _client(handler).get_updates(offset=7, poll_seconds=50)

    assert updates == [{"update_id": 7}]
    assert seen["url"] == f"{BASE}/bot{TOKEN}/getUpdates"
    assert seen["body"] == {
        "offset": 7,
        "timeout": 50,
        "allowed_updates": ["message"],
    }


async def test_send_and_edit_message():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(
            (request.url.path.rsplit("/", 1)[-1], json.loads(request.content))
        )
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    client = _client(handler)
    message_id = await client.send_message(chat_id=5, text="hello")
    await client.edit_message_text(chat_id=5, message_id=message_id, text="done")

    assert message_id == 42
    assert bodies == [
        ("sendMessage", {"chat_id": 5, "text": "hello"}),
        ("editMessageText", {"chat_id": 5, "message_id": 42, "text": "done"}),
    ]


async def test_get_file_and_download():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {"file_path": "documents/f.pdf", "file_size": 3},
                },
            )
        assert str(request.url) == f"{BASE}/file/bot{TOKEN}/documents/f.pdf"
        return httpx.Response(200, content=b"PDF")

    client = _client(handler)
    info = await client.get_file("file-1")
    content = await client.download_file(info["file_path"])

    assert info["file_path"] == "documents/f.pdf"
    assert content == b"PDF"


async def test_api_error_raises_without_the_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
        )

    with pytest.raises(TelegramError) as caught:
        await _client(handler).send_message(chat_id=5, text="x")

    assert "Unauthorized" in str(caught.value)
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)


async def test_transport_error_raises_without_the_token():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    with pytest.raises(TelegramError) as caught:
        await _client(handler).get_updates(offset=None, poll_seconds=1)

    assert TOKEN not in str(caught.value)
