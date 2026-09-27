"""Optional, country- or language-specific receipt profiles (Q27, amendment 2).

Receipts from any shop, country and language go through the same format-agnostic core: the
model numbers and accounts for every line. A profile is extra evidence for a country or
language whose receipt grammar we know. When one is registered for what the model detected,
reconciliation runs it on the same numbered lines, and any product line it finds that no
model product cites is sent to the one targeted retry. A profile never decides alone and
never replaces the core; the core imports profiles only through `profile_for`.

A numbered text is every line of the receipt with the number it was given in the model's
prompt, or None for a line the prompt left out, so a profile can still see (for example) a
total line the prompt dropped, while only ever citing numbered lines.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.parsers.heuristic import parse_receipt_blocks

NumberedText = Sequence[tuple[int | None, str]]


@dataclass(frozen=True)
class ProfileLine:
    """One product a profile read, with the numbered lines it came from."""

    line_numbers: tuple[int, ...]
    name: str
    quantity: float = 1.0
    weight_kg: float | None = None


class ReceiptProfile(Protocol):
    """A receipt grammar for one country or language."""

    @property
    def country(self) -> str | None: ...

    @property
    def language(self) -> str | None: ...

    def product_lines(self, numbered_text: NumberedText) -> list[ProfileLine]: ...


class FinnishProfile:
    """Finnish chains (S-Group, K-Group, Lidl Suomi): the MVP-R3b line parser."""

    country = "FI"
    language = "fi"

    def product_lines(self, numbered_text: NumberedText) -> list[ProfileLine]:
        return [
            ProfileLine(
                line_numbers=tuple(block.line_numbers),
                name=block.line.name,
                quantity=block.line.quantity,
                weight_kg=block.line.weight_kg,
            )
            for block in parse_receipt_blocks(numbered_text)
            if block.line_numbers
        ]


_PROFILES: tuple[ReceiptProfile, ...] = (FinnishProfile(),)


def profile_for(country: str | None, language: str | None) -> ReceiptProfile | None:
    """The profile for the detected country, else for the detected language, else None."""
    if country:
        for profile in _PROFILES:
            if profile.country and profile.country.casefold() == country.casefold():
                return profile
    if language:
        for profile in _PROFILES:
            if profile.language and profile.language.casefold() == language.casefold():
                return profile
    return None
