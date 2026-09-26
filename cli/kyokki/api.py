"""HTTP to the Kyokki API, and its errors mapped to the CLI's exit codes."""

import sys
from dataclasses import dataclass
from typing import Any, Literal

import httpx

OK = 0
ERROR = 1
USAGE = 2
NOT_FOUND = 3
AMBIGUOUS = 4
INSUFFICIENT_STOCK = 5
CONFLICT = 6
AUTH = 7

EXIT_FOR_CODE = {
    "not_found": NOT_FOUND,
    "ambiguous": AMBIGUOUS,
    "insufficient_stock": INSUFFICIENT_STOCK,
    "conflict": CONFLICT,
    "invalid": USAGE,
    "auth": AUTH,
}

TIMEOUT_SECONDS = 15.0

# Transport failures that happen before any byte of the request left: nothing was sent.
NOTHING_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
    httpx.LocalProtocolError,
)


class CliError(Exception):
    """A failure to report: ``detail`` is what --json prints, the exit code what we return."""

    def __init__(self, exit_code: int, detail: Any, status: int | None = None) -> None:
        super().__init__(describe(detail))
        self.exit_code = exit_code
        self.detail = detail
        self.status = status

    @property
    def code(self) -> str | None:
        """The detail's ``code``, when the detail is an object."""
        return str(self.detail.get("code")) if isinstance(self.detail, dict) else None


def describe(detail: Any) -> str:
    """One line for a person: the message, or the 422's field errors."""
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("code") or detail)
    if isinstance(detail, list):
        parts = []
        for error in detail:
            if isinstance(error, dict):
                loc = ".".join(str(p) for p in error.get("loc", []) if p != "body")
                msg = str(error.get("msg", error))
                parts.append(f"{loc}: {msg}" if loc else msg)
            else:
                parts.append(str(error))
        return "; ".join(parts) or "invalid request"
    return str(detail)


def usage_error(message: str) -> CliError:
    return CliError(USAGE, {"code": "usage", "message": message})


def clean_token(raw: str | None) -> str | None:
    """The token without surrounding whitespace (a CRLF env file), or None if empty.

    A token that still holds a control or non-ASCII character cannot go in a header;
    it is refused as a usage error that never repeats it.
    """
    token = (raw or "").strip()
    if not token:
        return None
    if any(not 0x20 <= ord(ch) < 0x7F for ch in token):
        raise usage_error(
            "the token (--token or KYOKKI_TOKEN) contains control or non-ASCII "
            "characters; nothing was sent"
        )
    return token


def base_url(raw: str) -> str:
    """``raw`` without a trailing slash or ``/api``; a usage error if it is no URL."""
    if not raw:
        raise usage_error(
            "no Kyokki URL. Set KYOKKI_URL or pass --url, "
            "e.g. --url http://kyokki.lan:17300"
        )
    if not raw.startswith(("http://", "https://")):
        raise usage_error(f"the URL must start with http:// or https://, got {raw!r}")
    url = raw.rstrip("/")
    if url.endswith("/api"):
        url = url[: -len("/api")]
    try:
        host = httpx.URL(url).host
    except httpx.InvalidURL as exc:
        raise usage_error(f"not a valid URL: {raw!r} ({exc})") from None
    if not host:
        raise usage_error(f"the URL has no host: {raw!r}")
    return url


def exit_code_for(status: int, detail: Any) -> int:
    if status in (401, 403):
        return AUTH
    if status == 422:
        return USAGE
    if status >= 500:
        return ERROR
    if isinstance(detail, dict):
        return EXIT_FOR_CODE.get(str(detail.get("code")), ERROR)
    return ERROR


def error_from(response: httpx.Response) -> CliError:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("detail"), dict | list):
        detail: Any = body["detail"]
    else:
        text = response.text.strip()[:200] or response.reason_phrase
        if isinstance(body, dict) and isinstance(body.get("detail"), str):
            # A plain-string detail (handle_integrity_errors): the status says it all.
            detail = {"code": f"http_{response.status_code}", "message": body["detail"]}
            code = STRING_DETAIL_EXIT.get(response.status_code)
            if code is not None:
                return CliError(code, detail, response.status_code)
        else:
            detail = {"code": f"http_{response.status_code}", "message": text}
    return CliError(
        exit_code_for(response.status_code, detail), detail, response.status_code
    )


STRING_DETAIL_EXIT = {400: USAGE, 409: CONFLICT}

# What ``expect="text"`` accepts: the export's bodies, never an HTML login page.
TEXT_MEDIA_TYPES = ("text/plain", "text/markdown")


def bad_response(method: str, path: str, status: int, what: str) -> CliError:
    return CliError(
        ERROR,
        {
            "code": "bad_response",
            "message": f"{method} {path} answered {status} with {what}",
        },
        status,
    )


@dataclass
class Answer:
    status: int
    body: Any
    replayed: bool


class Api:
    def __init__(
        self,
        url: str,
        token: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
        verbose: bool = False,
    ) -> None:
        self.url = url
        headers = {"Accept": "application/json", "User-Agent": "kyokki-cli"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=self.url,
            headers=headers,
            transport=transport,
            timeout=TIMEOUT_SECONDS,
        )
        self._verbose = verbose

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
        idempotency_key: str | None = None,
        expect: type[list[Any]] | type[dict[str, Any]] | Literal["text"] | None = None,
    ) -> Answer:
        """One request. ``expect`` is the JSON type a success must carry, or
        ``"text"`` for a text/plain or text/markdown body, returned as a string."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        if expect == "text":
            headers["Accept"] = ", ".join(TEXT_MEDIA_TYPES)
        query = {k: v for k, v in (params or {}).items() if v is not None}
        if self._verbose:
            key = f" (Idempotency-Key {idempotency_key})" if idempotency_key else ""
            print(f"> {method} {self.url}{path}{key}", file=sys.stderr)
        try:
            response = self._client.request(
                method, path, params=query or None, json=body, headers=headers
            )
        except httpx.TransportError as exc:
            # Only the class name: the text of a header error quotes the header.
            raise self._transport_error(method, path, exc, idempotency_key) from None
        if self._verbose:
            print(f"< {response.status_code} {response.reason_phrase}", file=sys.stderr)
        if response.is_error:
            raise error_from(response)
        replayed = response.headers.get("Idempotent-Replayed", "").lower() == "true"
        if expect == "text":
            media_type = response.headers.get("Content-Type", "").split(";")[0]
            if media_type.strip().lower() not in TEXT_MEDIA_TYPES:
                raise bad_response(
                    method,
                    path,
                    response.status_code,
                    f"{media_type.strip() or 'no Content-Type'} where text was "
                    "expected",
                )
            return Answer(response.status_code, response.text, replayed)
        try:
            parsed = response.json() if response.content else None
        except ValueError:
            raise bad_response(
                method, path, response.status_code, "a body that is not JSON"
            ) from None
        if expect is not None and not isinstance(parsed, expect):
            raise bad_response(
                method,
                path,
                response.status_code,
                f"JSON that is not {'a list' if expect is list else 'an object'}",
            )
        return Answer(response.status_code, parsed, replayed)

    def _transport_error(
        self,
        method: str,
        path: str,
        exc: httpx.TransportError,
        idempotency_key: str | None,
    ) -> CliError:
        kind = type(exc).__name__
        if isinstance(exc, NOTHING_SENT):
            message = f"cannot reach {self.url} ({kind}); nothing was sent"
            return CliError(ERROR, {"code": "connection", "message": message})
        if idempotency_key:
            return CliError(
                ERROR,
                {
                    "code": "unknown_outcome",
                    "message": f"sent {method} {path} to {self.url} but got no answer "
                    f"({kind}); the change may have been applied. Retry with the "
                    f"same Idempotency-Key {idempotency_key} to replay it, not "
                    "repeat it",
                    "idempotency_key": idempotency_key,
                },
            )
        message = f"no answer from {self.url} ({kind})"
        return CliError(ERROR, {"code": "connection", "message": message})
