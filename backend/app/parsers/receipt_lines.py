"""Receipt lines that are never products, for the heuristic parser and the `fi` receipt profile.

Covers the formats in the ARCHITECTURE.md appendix (S-Group, K-Group, Lidl): separators,
totals, payment and VAT rows, discounts, fees, deposits and loyalty lines.

The `säästö` ("saving") skip is anchored to the loyalty/discount forms themselves -
line-start (``Säästöt 0,94``) or a standalone ``-säästö...`` discount entry
(``Lidl Plus -säästösi -0,37``) - never to the word appearing anywhere on the line, so a real
product such as ``OMENA SÄÄSTÖPAKKAUS 4,99`` is not mistaken for one (H27).
"""

import re

SKIP_LINE = re.compile(
    r"^(-{5,}|={5,}|VÄLISUMMA|YHTEENSÄ|BONUSTA|MAKSUTAPA|KORTTI\b|\*{4,}|Veloitus:|"
    r"Autentisointi:|Viite:|Aika:|ALV\b|ALV%|\d+,\d+\s*%|YHT\.|NORM\.|ALENNUS|TOIMITUSMAKSU|"
    r"VERKKOK\.PAKKAUS|PANTTI\s+YHT|Tolkkipantti|PANTTI\b|PLUSSA-ETU|PLUSSA-TASAERÄ|"
    r"KANTA-ASIAKAS|Lidl\s+Plus|KORTTIMAKSU|SÄÄSTÖT|.*-säästö)",
    re.IGNORECASE,
)


def is_skip_line(line: str) -> bool:
    return bool(SKIP_LINE.match(line.strip()))
