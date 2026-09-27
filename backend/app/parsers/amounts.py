"""Locale-neutral amounts and line shapes on a printed receipt (Q27).

Line accounting asks one question of every receipt line: does it carry an amount that has to
be accounted for? Receipts come from any shop, country and language, so the answer uses no
store, language or country words and no closed list of currencies, only the structure every
till prints: a line's amount stands at its end.

- Before the amount there may be a currency: any Unicode currency symbol (category Sc),
  optionally after up to two capitals (``$7.00``, ``R$ 12,90``).
- After it there may be up to two short markers: a space-separated token of 1-3 characters
  (a currency code or abbreviation such as ``EUR``, ``Kč``, ``Ft``; a tax letter or digit such
  as ``B``, ``FS``, ``1``; a symbol such as ``軽``) or 1-2 glued symbols (``※``, ``*``). A
  trailing token that this receipt uses as a unit in its own count or weight lines (``KPL``
  in ``3 KPL 1,88 €/KPL``) is a unit, not a currency: ``Tuote 2,49 KPL`` has no amount.
- Thousands may be grouped with ``.``, ``,``, ``'`` or a space (``1 234,56``).
- A date or a time before the number, a masked card number (``****0000``) or, on a receipt
  without cents, a spaced phone-like digit group (``TEL 000 0000``) is never an amount.
  A dotted time after a date anywhere on the line (``Kuitti 27.9.2026 klo 18.05``) is not
  either. ``clock_time`` marks the weaker case, a time after one short word (``KLO 11.49``),
  which reconciliation treats as an amount only when the sums say money is missing.
- The receipt decides the precision (``amount_style``): ``cents`` when a line ends in a
  two-decimal amount; ``mills`` when the model's total is printed with three decimals
  (``TOTAL 3.150``, KWD, BHD); otherwise ``whole`` (JPY, HUF, ISK), where whole numbers count.
  Outside ``mills`` a separator followed by exactly three digits is a thousands separator
  ("1,299" is 1299), except after a lone 0 ("0,913" is a weight).
"""

import re
import sys
import unicodedata
from collections.abc import Iterable
from typing import Literal

AmountStyle = Literal["cents", "mills", "whole"]


def _currency_symbols() -> str:
    """Every Unicode currency symbol, as the body of a regex character class."""
    symbols = (
        chr(c)
        for c in range(sys.maxunicode + 1)
        if unicodedata.category(chr(c)) == "Sc"
    )
    return "".join(re.escape(s) for s in symbols)


_CURRENCY = f"[{_currency_symbols()}]"
# Separators that group thousands: dot, comma, apostrophe, a space or a no-break space
_GROUP = "[.,'   ]"
# A number as tills print it: grouped thousands, or plain digits with a decimal part
_NUMBER = rf"\d{{1,3}}(?:{_GROUP}\d{{3}})+(?:[.,]\d{{1,3}})?|\d+(?:[.,]\d{{1,3}})?"
# What may follow the amount: a short space-separated token, or one or two glued symbols
_SUFFIX = r"(?:\s+(?P<token{n}>[^\s/]{{1,3}})|[^\s\w/.,:'\-]{{1,2}})"
_END_AMOUNT = re.compile(
    rf"(?<![\w.,:/'\-])(?P<sign>[-−])?(?:[A-Z]{{0,2}}{_CURRENCY}\s?)?"
    rf"(?P<number>{_NUMBER})(?P<minus>-)?"
    rf"{_SUFFIX.format(n=1)}?{_SUFFIX.format(n=2)}?\s*$"
)
_DATE = r"\d{1,4}[./-]\d{1,2}[./-]\d{2,4}"
# A date or time right before the amount means the "amount" is part of a timestamp
_DATE_OR_TIME_BEFORE = re.compile(rf"(?:{_DATE}|\d{{1,2}}:\d{{2}}(?::\d{{2}})?)\s*$")
_DATE_ANYWHERE = re.compile(_DATE)
# A clock time: hours 0-23, a dot or colon, minutes 00-59
_TIME = re.compile(r"^(?:[01]?\d|2[0-3])[.:][0-5]\d$")
# A masked card number right before the digits
_MASKED = re.compile(r"\*{2,}\s*$")
# On a receipt without cents: digits right before, as in a spaced phone number
_DIGIT_GROUP_BEFORE = re.compile(r"\d\s+$")
# Any number on a line, for the arithmetic of a count or weight line; not a percentage
_ANY_NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![.,]?\d)(?!\s*%)")
# A run of four or more letters in any script: something a name has and a detail line
# ("0,523 KG 1,99 €/KG", "2 x 1,49", "3 kom x 1,29") does not
_WORD = re.compile(r"[^\W\d_]{4,}")
# A count or weight line starts with a bare number: "2 x", "2x1,49", "0,913 KG". A name that
# starts with digits glued to letters ("7UP", "1,5L COLA") does not
_BARE_NUMBER_FIRST = re.compile(r"\s*\d+(?:[.,]\d+)?(?:\s|[x×X*@]|$)")
# The unit after a leading count or weight ("3 KPL", "0,913 KG") or after a slash ("€/KG")
_LEADING_UNIT = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*([^\W\d_]{2,5})\b")
_SLASH_UNIT = re.compile(r"/\s*([^\W\d_]{2,5})\b")


def _decimals(number: str, style: AmountStyle = "cents") -> int:
    """How many digits follow the decimal separator, 0 for a whole or grouped number."""
    match = re.search(r"[.,](\d+)$", number)
    if not match:
        return 0
    digits = match[1]
    if len(digits) == 3 and style != "mills" and not number.startswith(("0,", "0.")):
        return 0  # a thousands group: 1,299
    return len(digits)


def number_value(number: str, style: AmountStyle = "cents") -> float:
    """The value of a printed number, whatever its separators."""
    decimals = _decimals(number, style)
    if decimals:
        whole, fraction = number[: -decimals - 1], number[-decimals:]
    else:
        whole, fraction = number, ""
    whole = re.sub(r"[.,'\s]", "", whole)
    return float(f"{whole or 0}.{fraction or 0}")


def _end_amount(line: str) -> re.Match[str] | None:
    match = _END_AMOUNT.search(line)
    if match is None:
        return None
    before = line[: match.start()]
    if _DATE_OR_TIME_BEFORE.search(before) or _MASKED.search(before):
        return None
    if _TIME.match(match["number"]) and _DATE_ANYWHERE.search(before):
        return None  # "Kuitti 27.9.2026 klo 18.05"
    return match


def _counts(match: re.Match[str], line: str, style: AmountStyle) -> bool:
    number = match["number"]
    decimals = _decimals(number, style)
    if style == "cents":
        return decimals == 2
    if style == "mills":
        return decimals == 3
    if decimals == 2:
        return True
    digits = re.sub(r"\D", "", number)
    if _DIGIT_GROUP_BEFORE.search(line[: match.start()]):
        return False  # "TEL 000 0000"
    # a card, reference or register number is long or zero-padded; a price is neither
    return len(digits) <= 7 and not (digits.startswith("0") and len(digits) > 1)


def amount_style(lines: Iterable[str], total: float | None = None) -> AmountStyle:
    """This receipt's precision, decided by the receipt and the model's total, not a locale."""
    lines = list(lines)
    if total is not None:
        for line in lines:
            match = _end_amount(line)
            if match is None or not re.search(r"[.,]\d{3}$", match["number"]):
                continue
            if abs(number_value(match["number"], "mills") - abs(total)) < 0.0005:
                return "mills"
    for line in lines:
        match = _end_amount(line)
        if match is not None and _decimals(match["number"]) == 2:
            return "cents"
    return "whole"


def receipt_units(lines: Iterable[str]) -> set[str]:
    """The unit words this receipt prints in its own count and weight lines, casefolded."""
    units: set[str] = set()
    for line in lines:
        if leading := _LEADING_UNIT.match(line):
            units.add(leading[1].casefold())
        units.update(unit.casefold() for unit in _SLASH_UNIT.findall(line))
    return units


def _is_unit(match: re.Match[str], units: Iterable[str]) -> bool:
    tokens = [match["token1"], match["token2"]]
    known = set(units)
    return any(t is not None and t.isalpha() and t.casefold() in known for t in tokens)


def line_amount(
    line: str, style: AmountStyle = "cents", units: Iterable[str] = ()
) -> float | None:
    """The signed amount at the end of a line, or None when the line carries none."""
    match = _end_amount(line)
    if match is None or not _counts(match, line, style) or _is_unit(match, units):
        return None
    value = number_value(match["number"], style)
    return -value if match["sign"] or match["minus"] else value


def end_number(line: str) -> str | None:
    """The printed number at the end of a line, as a token, if the line ends in one."""
    match = _end_amount(line)
    return match["number"] if match else None


def clock_time(line: str) -> bool:
    """A clock time after one short word ("KLO 11.49", "Time 12.30").

    Structurally it is a price too ("KIWI 0.59"), so it is a weak amount: reconciliation
    counts it only when the sums miss a total the model listed.
    """
    match = _end_amount(line)
    if match is None or not _TIME.match(match["number"]):
        return False
    before = line[: match.start()].split()
    return len(before) == 1 and before[0].isalpha() and len(before[0]) <= 4


def strip_amount(line: str) -> str:
    """The line without its end amount and whatever follows it: what a name looks like."""
    match = _end_amount(line)
    text = line[: match.start()] if match else line
    return " ".join(text.split())


def is_detail(line: str) -> bool:
    """A count, weight or unit-price line rather than a name, by shape alone."""
    text = line.strip()
    return bool(_BARE_NUMBER_FIRST.match(text)) and not _WORD.search(text)


def continues_a_name(line: str) -> bool:
    """A line that starts in lower case continues the name printed above it."""
    return line.strip()[:1].islower()


def wraps_onto(first: str, second: str) -> bool:
    """Whether ``first`` (a line without an amount) is the first half of ``second``'s name.

    Either ``second`` starts in lower case, or both are printed in capitals, as an all-caps
    till wraps a long name. A line with digits or a colon (a card or header line) is never
    a name's first half.
    """
    head = first.strip()
    if not head or re.search(r"[\d:]", head) or not re.search(r"[^\W\d_]", head):
        return False
    if continues_a_name(second):
        return True
    letters = [c for c in head + strip_amount(second) if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


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
