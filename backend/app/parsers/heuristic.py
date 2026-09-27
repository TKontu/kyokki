"""Deterministic, store-agnostic receipt line parser (MVP-R3b).

Used when LLM extraction fails or finds nothing, so a receipt with readable text still reaches
review. It reads the grammar shared by Finnish receipts (ARCHITECTURE.md appendix):

    NAME PRICE [PRICE] [VAT code]        a product line
    3 KPL 1,88 €/KPL  |  2 x 2,89 EUR    quantity of the product above
    0,386 KG 3,89 €/KG | 0,436 kg x ...  weight of the product above

Discounts (negative prices), totals, fees, deposits and payment lines are skipped. Names stay
as printed; there are no generic names or categories without the model.

These are Finnish receipt formats. Besides the last-resort fallback, the parser is used only
as the `fi` receipt profile (`app.parsers.profiles`), which adds evidence to the
format-agnostic completeness check and never decides alone (Q27). Reading stops at the
first total, since what follows it is loyalty, payment and VAT; and a quantity or weight line
belongs only to a product directly above it, so the `1 KPL` under a skipped deposit line stays
with the deposit. Both rules hold for the fallback too: it runs only when the model has failed,
and a mid-receipt SUMMA ending it early is an accepted limit of that last resort (PR #131 F8).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.parsers.receipt_lines import is_skip_line
from app.services.store_chain import normalize_store_chain

_QUANTITY = re.compile(r"^(\d+)\s*(?:KPL|x)\s+\d+[,.]\d{2}", re.IGNORECASE)
_WEIGHT = re.compile(r"^(\d+[,.]\d{3})\s*kg\b", re.IGNORECASE)
_PRODUCT = re.compile(
    r"^(?P<name>.+?)\s+(?P<price>-?\d+[,.]\d{2})(?P<minus>-)?"
    r"(?:\s+-?\d+[,.]\d{2})?(?:\s+[A-C])?\s*(?:€|EUR)?$"
)
_PRICE_ANYWHERE = re.compile(r"\d+[,.]\d{2}(?!\d)")
_WORD = re.compile(r"[A-Za-zÅÄÖåäö]{2,}")
_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_HEADER_LINES = 8
# The first total ends the products; the footer's amounts are loyalty and payment (Q27)
_TOTAL = re.compile(r"^(YHTEENSÄ|YHTEENSA|SUMMA)\b", re.IGNORECASE)


def _normalise(line: str) -> str:
    return " ".join(line.replace("−", "-").replace("–", "-").split())


def _purchase_date(lines: list[str]) -> date | None:
    for line in lines:
        for day, month, year in _DATE.findall(line):
            try:
                return date(int(year), int(month), int(day))
            except ValueError:
                continue
    return None


def _store(lines: list[str]) -> str | None:
    header = lines[:_HEADER_LINES]
    for line in header:
        if normalize_store_chain(line) in ("s-group", "k-group", "lidl", "tokmanni"):
            return line
    for line in header:
        if (
            _WORD.search(line)
            and not _PRICE_ANYWHERE.search(line)
            and not _DATE.search(line)
        ):
            return line
    return None


def _product(line: str) -> str | None:
    """The product name if this is a product line with a positive price."""
    match = _PRODUCT.match(line)
    if not match:
        return None
    if match["price"].startswith("-") or match["minus"]:
        return None  # a discount
    name = match["name"].strip()
    first_token = name.split(" ", 1)[0]
    if (
        len(name) < 2
        or not _WORD.search(name)
        or first_token.replace(",", "").isdigit()
    ):
        return None
    return name


@dataclass
class ProductBlock:
    """One product line and the numbers of the lines it was read from."""

    line: ExtractedLine
    line_numbers: list[int] = field(default_factory=list)


def parse_receipt_blocks(
    numbered: Sequence[tuple[int | None, str]],
) -> list[ProductBlock]:
    """The product lines of a receipt, each with the numbers of its source lines.

    ``numbered`` is every line of the receipt with the number it was given in the model's
    prompt, or None for a line the prompt left out; a block only cites numbered lines.
    """
    blocks: list[ProductBlock] = []
    # The product a following KPL or KG line belongs to; a skipped line breaks the chain
    current: ProductBlock | None = None
    for number, raw in numbered:
        line = _normalise(raw)
        if not line:
            continue
        if _TOTAL.match(line):
            break
        if is_skip_line(line):
            current = None
            continue
        quantity = _QUANTITY.match(line)
        weight = None if quantity else _WEIGHT.match(line)
        if quantity or weight:
            if current is not None:
                if quantity:
                    current.line.quantity = float(quantity[1])
                elif weight:
                    current.line.weight_kg = float(weight[1].replace(",", "."))
                if number is not None:
                    current.line_numbers.append(number)
            continue
        name = _product(line)
        if name:
            current = ProductBlock(
                line=ExtractedLine(name=name),
                line_numbers=[number] if number is not None else [],
            )
            blocks.append(current)
    return blocks


def parse_receipt_text(text: str) -> ReceiptExtraction:
    lines = [_normalise(raw) for raw in text.splitlines()]
    lines = [line for line in lines if line]
    blocks = parse_receipt_blocks([(None, line) for line in lines])

    return ReceiptExtraction(
        method="heuristic",
        store_chain=_store(lines),
        purchase_date=_purchase_date(lines),
        lines=[block.line for block in blocks],
    )
