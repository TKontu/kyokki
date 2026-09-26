"""Agent access tokens (AG1).

``KYOKKI_API_TOKENS`` holds comma-separated ``name:scope:sha256hex`` entries. Only the
SHA-256 of each secret lives in configuration; the secret itself is handed to the
client once, when it is generated::

    python -m app.core.api_tokens new hermes write   # prints a secret and its entry
    python -m app.core.api_tokens hash SECRET        # prints the hash of a secret

``write`` implies ``read``. Error messages name an entry by its name (or position),
never by its hash.
"""

import argparse
import hashlib
import hmac
import re
import secrets
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Scope = Literal["read", "write"]
SCOPES: tuple[Scope, ...] = ("read", "write")

_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ApiTokenConfigError(Exception):
    """A malformed ``KYOKKI_API_TOKENS`` entry.

    Deliberately not a ``ValueError``: pydantic would wrap that in a ValidationError
    whose text repeats the whole input value, hashes included.
    """


@dataclass(frozen=True)
class ApiToken:
    name: str
    scope: Scope
    sha256: str

    @property
    def scopes(self) -> tuple[Scope, ...]:
        return SCOPES if self.scope == "write" else ("read",)

    def allows(self, needed: Scope) -> bool:
        return needed in self.scopes

    def matches(self, presented_sha256: str) -> bool:
        return hmac.compare_digest(self.sha256, presented_sha256)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def parse_token_entries(entries: Sequence[str]) -> list[ApiToken]:
    tokens: list[ApiToken] = []
    seen: set[str] = set()
    for position, raw in enumerate(entries, start=1):
        fields = [part.strip() for part in raw.split(":")]
        # With no separator at all the value may be a pasted secret, and with the fields
        # out of order the first one may be the hash: name either by position.
        named = len(fields) > 1 and fields[0] and not _HASH_RE.match(fields[0])
        label = f"'{fields[0]}'" if named else f"entry {position}"
        if len(fields) != 3:
            raise ApiTokenConfigError(
                f"KYOKKI_API_TOKENS {label}: expected name:scope:sha256hex"
            )
        name, scope, digest = fields
        if not name:
            raise ApiTokenConfigError(f"KYOKKI_API_TOKENS {label}: empty name")
        if scope not in SCOPES:
            raise ApiTokenConfigError(
                f"KYOKKI_API_TOKENS {label}: scope must be 'read' or 'write'"
            )
        if not _HASH_RE.match(digest):
            raise ApiTokenConfigError(
                f"KYOKKI_API_TOKENS {label}: hash must be 64 hex characters"
            )
        if name in seen:
            raise ApiTokenConfigError(f"KYOKKI_API_TOKENS {label}: duplicate name")
        seen.add(name)
        tokens.append(ApiToken(name=name, scope=scope, sha256=digest.lower()))
    return tokens


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.core.api_tokens",
        description="Generate or hash Kyokki API access tokens.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="print a fresh secret and its config entry")
    new.add_argument("name")
    new.add_argument("scope", choices=SCOPES)
    hash_cmd = sub.add_parser("hash", help="print the SHA-256 of a secret")
    hash_cmd.add_argument("secret")
    args = parser.parse_args(argv)

    if args.command == "hash":
        print(hash_secret(args.secret))
        return 0

    name = args.name.strip()
    if not name or ":" in name or "," in name:
        print("name must be non-empty without ':' or ','", file=sys.stderr)
        return 2
    secret = secrets.token_urlsafe(32)
    print(f"secret: {secret}")
    print(f"entry: {name}:{args.scope}:{hash_secret(secret)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
