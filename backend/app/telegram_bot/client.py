"""Thin Telegram Bot API client over httpx.

Every request URL contains the bot token, so errors are rebuilt from the method name and the
API's own description. Neither ``TelegramError`` nor a log line ever carries the URL.
"""

from typing import Any

import httpx

MAX_FILE_BYTES = 20 * 1024 * 1024  # Bot API download limit for getFile


class TelegramError(Exception):
    """A Bot API call failed. The message never contains the token."""


class TelegramClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.telegram.org",
        http: httpx.AsyncClient | None = None,
    ):
        self._token = token
        self._base = base_url.rstrip("/")
        # Long polls hold the connection open, so the read timeout sits above the poll timeout
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=90.0))

    def __repr__(self) -> str:
        return f"TelegramClient(base_url={self._base!r})"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base}/bot{self._token}/{method}"
        try:
            response = await self._http.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise TelegramError(
                f"Telegram {method} failed: {type(exc).__name__}"
            ) from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or not body.get("ok"):
            description = body.get("description") or f"HTTP {response.status_code}"
            raise TelegramError(f"Telegram {method} failed: {description}")
        return body.get("result")

    async def get_updates(
        self, offset: int | None, poll_seconds: int
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "offset": offset,
            "timeout": poll_seconds,
            "allowed_updates": ["message"],
        }
        return list(await self._call("getUpdates", payload) or [])

    async def send_message(self, chat_id: int, text: str) -> int:
        result = await self._call("sendMessage", {"chat_id": chat_id, "text": text})
        return int(result["message_id"])

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        await self._call(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": text},
        )

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return dict(await self._call("getFile", {"file_id": file_id}))

    async def download_file(self, file_path: str) -> bytes:
        url = f"{self._base}/file/bot{self._token}/{file_path}"
        try:
            response = await self._http.get(url)
        except httpx.HTTPError as exc:
            raise TelegramError(
                f"Telegram download failed: {type(exc).__name__}"
            ) from None
        if response.status_code != 200:
            raise TelegramError(
                f"Telegram download failed: HTTP {response.status_code}"
            )
        return response.content
