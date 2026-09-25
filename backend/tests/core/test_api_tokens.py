"""Agent access tokens (AG1): the ``name:scope:sha256hex`` config format and CLI."""

import hashlib
import re

import pytest

from app.core.api_tokens import (
    ApiToken,
    ApiTokenConfigError,
    hash_secret,
    main,
    parse_token_entries,
)

HASH_A = hashlib.sha256(b"secret-a").hexdigest()
HASH_B = hashlib.sha256(b"secret-b").hexdigest()


class TestParse:
    def test_valid_list(self) -> None:
        tokens = parse_token_entries([f"ipad:write:{HASH_A}", f"hermes:read:{HASH_B}"])
        assert tokens == [
            ApiToken(name="ipad", scope="write", sha256=HASH_A),
            ApiToken(name="hermes", scope="read", sha256=HASH_B),
        ]

    def test_empty_list(self) -> None:
        assert parse_token_entries([]) == []

    def test_whitespace_around_fields_is_ignored(self) -> None:
        (token,) = parse_token_entries([f"  ipad : write : {HASH_A} "])
        assert token == ApiToken(name="ipad", scope="write", sha256=HASH_A)

    def test_uppercase_hash_is_normalised(self) -> None:
        (token,) = parse_token_entries([f"ipad:write:{HASH_A.upper()}"])
        assert token.sha256 == HASH_A

    @pytest.mark.parametrize(
        ("entry", "expected_in_message"),
        [
            (f"ipad:{HASH_A}", "'ipad'"),
            (f"ipad:write:extra:{HASH_A}", "'ipad'"),
            (f"ipad:admin:{HASH_A}", "'ipad'"),
            ("ipad:write:abc123", "'ipad'"),
            (f"ipad:write:{'g' * 64}", "'ipad'"),
            (f":write:{HASH_A}", "entry 1"),
        ],
        ids=[
            "too-few-fields",
            "too-many-fields",
            "unknown-scope",
            "short-hash",
            "non-hex-hash",
            "empty-name",
        ],
    )
    def test_malformed_entry_names_it_without_the_hash(
        self, entry: str, expected_in_message: str
    ) -> None:
        with pytest.raises(ApiTokenConfigError) as exc:
            parse_token_entries([entry])
        message = str(exc.value)
        assert expected_in_message in message
        assert HASH_A not in message
        assert "abc123" not in message

    def test_entry_without_separators_is_named_by_position(self) -> None:
        """A bare value may be a pasted secret; it must not be echoed back."""
        with pytest.raises(ApiTokenConfigError) as exc:
            parse_token_entries([f"ok:read:{HASH_B}", "my-raw-secret"])
        assert "entry 2" in str(exc.value)
        assert "my-raw-secret" not in str(exc.value)

    def test_duplicate_name(self) -> None:
        with pytest.raises(ApiTokenConfigError) as exc:
            parse_token_entries([f"ipad:write:{HASH_A}", f"ipad:read:{HASH_B}"])
        assert "'ipad'" in str(exc.value)
        assert HASH_A not in str(exc.value)
        assert HASH_B not in str(exc.value)


class TestScopes:
    def test_write_implies_read(self) -> None:
        token = ApiToken(name="t", scope="write", sha256=HASH_A)
        assert token.scopes == ("read", "write")
        assert token.allows("read")
        assert token.allows("write")

    def test_read_is_read_only(self) -> None:
        token = ApiToken(name="t", scope="read", sha256=HASH_A)
        assert token.scopes == ("read",)
        assert token.allows("read")
        assert not token.allows("write")

    def test_matches_uses_the_hash(self) -> None:
        token = ApiToken(name="t", scope="read", sha256=HASH_A)
        assert token.matches(HASH_A)
        assert not token.matches(HASH_B)


class TestCli:
    def test_hash_prints_the_sha256(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["hash", "secret-a"]) == 0
        assert capsys.readouterr().out.strip() == HASH_A

    def test_new_prints_a_secret_and_its_entry(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["new", "hermes", "write"]) == 0
        out = capsys.readouterr().out
        secret = re.search(r"^secret: (\S+)$", out, re.MULTILINE)
        entry = re.search(r"^entry: (\S+)$", out, re.MULTILINE)
        assert secret and entry
        # token_urlsafe(32) is 43 characters
        assert len(secret.group(1)) >= 43
        assert entry.group(1) == f"hermes:write:{hash_secret(secret.group(1))}"
        # The printed entry is itself valid config
        (token,) = parse_token_entries([entry.group(1)])
        assert token.name == "hermes"

    def test_new_gives_a_different_secret_each_time(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["new", "a", "read"])
        first = capsys.readouterr().out
        main(["new", "a", "read"])
        assert capsys.readouterr().out != first

    def test_new_rejects_an_unknown_scope(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["new", "hermes", "admin"])
        assert exc.value.code != 0

    def test_new_rejects_a_name_with_a_separator(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["new", "a:b", "read"]) != 0
        assert "secret:" not in capsys.readouterr().out
