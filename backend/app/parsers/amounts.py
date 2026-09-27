"""Locale-neutral amounts and line shapes on a printed receipt (Q27).

Line accounting asks one question of every receipt line: does it carry an amount that has to
be accounted for? Receipts come from any shop, country and language, so the answer uses no
store, language or country words, only the shape every till prints: a line's amount stands
at its end, optionally followed by a currency symbol or code, a tax letter or a marker.

- ``4,27``, ``2.49``, ``1.299,00``, ``1,299.00``, ``1'299.00``, ``-1,14``, ``1,14-``,
  ``$7.00``, ``73,07 EUR`` and ``2,98 B`` are amounts.
- ``K004 M000000/0000 11.49 26.9.2026`` ends in a date, ``18:05`` is a time and
  ``0,523 KG 1,99 €/KG`` ends in a unit: none of them is the line's amount.
- A receipt whose amounts carry no cents (JPY, HUF, ISK) prints ``1299`` or ``1,299``. Whole
  numbers count only on such a receipt, that is when no line on it ends in a two-decimal
  amount, so a phone number or a reference number on an ordinary receipt never does.

A separator followed by exactly three digits reads as a thousands separator ("1,299" is
1299), except after a lone 0 ("0,913" is a weight); a three-decimal currency would therefore
read a thousandfold too high, which only matters for the value, not for whether the line is
priced.
"""

import re
from collections.abc import Iterable
from typing import Literal

AmountStyle = Literal["cents", "whole"]

_CURRENCY = r"[€$£¥₩₹₽₺¢]"
# A number as tills print it: grouped thousands, or plain digits with a decimal part
_NUMBER = r"\d{1,3}(?:[.,']\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,3})?"
# Currency abbreviations printed after an amount (HUF, SEK/NOK/DKK, CZK, PLN, BGN)
_CURRENCY_WORD = r"(?:Ft|kr|Kč|zł|лв)\.?"
# What may follow a line's amount: a currency symbol, code or abbreviation, a tax letter,
# a marker
_SUFFIX = rf"(?:\s*(?:{_CURRENCY}|{_CURRENCY_WORD}|[A-Z]{{3}}\b|[A-Za-z]\b|\*|#))"
_END_AMOUNT = re.compile(
    rf"(?<![\w.,:/'-])(?P<sign>[-−])?(?:{_CURRENCY}\s?)?(?P<number>{_NUMBER})"
    rf"(?P<minus>-)?{_SUFFIX}{{0,2}}\s*$"
)
# A date or time right before the amount means the "amount" is part of a timestamp
_DATE_OR_TIME_BEFORE = re.compile(
    r"(?:\d{1,4}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}:\d{2}(?::\d{2})?)\s*$"
)
# Any number on a line, for the arithmetic of a count or weight line; not a percentage
_ANY_NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![.,]?\d)(?!\s*%)")
# A run of four or more letters in any script: something a name has and a detail line
# ("0,523 KG 1,99 €/KG", "2 x 1,49", "3 kom x 1,29") does not
_WORD = re.compile(r"[^\W\d_]{4,}")


def _decimals(number: str) -> int:
    """How many digits follow the decimal separator, 0 for a whole or grouped number."""
    match = re.search(r"[.,](\d+)$", number)
    if not match:
        return 0
    digits = match[1]
    if len(digits) == 3 and not number.startswith(("0,", "0.")):
        return 0  # a thousands group: 1,299
    return len(digits)


def number_value(number: str) -> float:
    """The value of a printed number, whatever its separators."""
    decimals = _decimals(number)
    if decimals:
        whole, fraction = number[: -decimals - 1], number[-decimals:]
    else:
        whole, fraction = number, ""
    whole = re.sub(r"[.,']", "", whole)
    return float(f"{whole or 0}.{fraction or 0}")


def _end_amount(line: str) -> re.Match[str] | None:
    match = _END_AMOUNT.search(line)
    if match is None or _DATE_OR_TIME_BEFORE.search(line[: match.start()]):
        return None
    return match


def _counts(match: re.Match[str], style: AmountStyle) -> bool:
    number = match["number"]
    decimals = _decimals(number)
    if style == "cents":
        return decimals == 2
    if decimals == 2:
        return True
    digits = re.sub(r"\D", "", number)
    # a card, reference or register number is long or zero-padded; a price is neither
    return len(digits) <= 7 and not (digits.startswith("0") and len(digits) > 1)


def amount_style(lines: Iterable[str]) -> AmountStyle:
    """Whether this receipt prints cents; decided by the receipt, not by a locale."""
    for line in lines:
        match = _end_amount(line)
        if match is not None and _decimals(match["number"]) == 2:
            return "cents"
    return "whole"


def line_amount(line: str, style: AmountStyle = "cents") -> float | None:
    """The signed amount at the end of a line, or None when the line carries none."""
    match = _end_amount(line)
    if match is None or not _counts(match, style):
        return None
    value = number_value(match["number"])
    return -value if match["sign"] or match["minus"] else value


def strip_amount(line: str) -> str:
    """The line without its end amount and whatever follows it: what a name looks like."""
    match = _end_amount(line)
    text = line[: match.start()] if match else line
    return " ".join(text.split())


def is_detail(line: str) -> bool:
    """A count, weight or unit-price line rather than a name, by shape alone."""
    text = line.strip()
    return text[:1].isdigit() and not _WORD.search(text)


def continues_a_name(line: str) -> bool:
    """A line that starts in lower case continues the name printed above it."""
    return line.strip()[:1].islower()


def _tolerance(total: float) -> float:
    return max(0.011, abs(total) * 0.005)


def _factors(line: str) -> list[tuple[str, float]]:
    return [(m[1], number_value(m[1])) for m in _ANY_NUMBER.finditer(line)]


def explaining_pair(line: str, total: float | None) -> tuple[str, str] | None:
    """The two printed numbers on a count or weight line whose product is ``total``.

    "2 x 1,49" explains 2,98 and "0,913 KG 25,00 €/KG" explains 22,83, in any currency or
    language: the arithmetic proves the line belongs to that line total, where adjacency
    alone does not.
    """
    if total is None or total <= 0:
        return None
    factors = _factors(line)
    for i, (first, a) in enumerate(factors):
        for second, b in factors[i + 1 :]:
            if a > 0 and b > 0 and abs(a * b - total) <= _tolerance(total):
                return first, second
    return None


def detail_count(line: str, total: float | None) -> int | None:
    """The piece count a count line gives for ``total`` ("2 x 1,49" for 2,98), if any."""
    pair = explaining_pair(line, total)
    if pair is None:
        return None
    for token in pair:
        if token.isdigit() and int(token) >= 1:
            return int(token)
    return None
