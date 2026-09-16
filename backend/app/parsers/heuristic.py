"""Deterministic, store-agnostic receipt line parser (MVP-R3b).

Used when LLM extraction fails or finds nothing, so a receipt with readable text still reaches
review. It reads the grammar shared by Finnish receipts (ARCHITECTURE.md appendix):

    NAME PRICE [PRICE] [VAT code]        a product line
    3 KPL 1,88 €/KPL  |  2 x 2,89 EUR    quantity of the product above
    0,386 KG 3,89 €/KG | 0,436 kg x ...  weight of the product above

Discounts (negative prices), totals, fees, deposits and payment lines are skipped. Names stay as
printed; there are no generic names or categories without the model.
"""

import re
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


def parse_receipt_text(text: str) -> ReceiptExtraction:
    lines = [_normalise(raw) for raw in text.splitlines()]
    lines = [line for line in lines if line]

    products: list[ExtractedLine] = []
    for line in lines:
        if is_skip_line(line):
            continue
        if quantity := _QUANTITY.match(line):
            if products:
                products[-1].quantity = float(quantity[1])
            continue
        if weight := _WEIGHT.match(line):
            if products:
                products[-1].weight_kg = float(weight[1].replace(",", "."))
            continue
        name = _product(line)
        if name:
            products.append(ExtractedLine(name=name))

    return ReceiptExtraction(
        method="heuristic",
        store_chain=_store(lines),
        purchase_date=_purchase_date(lines),
        lines=products,
    )
