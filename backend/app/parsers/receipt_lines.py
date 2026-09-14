"""Receipt lines that are never products, shared by the LLM prefilter and the heuristic parser.

Covers the formats in the ARCHITECTURE.md appendix (S-Group, K-Group, Lidl): separators,
totals, payment and VAT rows, discounts, fees, deposits and loyalty lines.
"""

import re

SKIP_LINE = re.compile(
    r"^(-{5,}|={5,}|VÄLISUMMA|YHTEENSÄ|BONUSTA|MAKSUTAPA|KORTTI\b|\*{4,}|Veloitus:|"
    r"Autentisointi:|Viite:|Aika:|ALV\b|ALV%|\d+,\d+\s*%|YHT\.|NORM\.|ALENNUS|TOIMITUSMAKSU|"
    r"VERKKOK\.PAKKAUS|PANTTI\s+YHT|Tolkkipantti|PANTTI\b|PLUSSA-ETU|PLUSSA-TASAERÄ|"
    r"KANTA-ASIAKAS|Lidl\s+Plus|KORTTIMAKSU|SÄÄSTÖT|.*säästö)",
    re.IGNORECASE,
)


def is_skip_line(line: str) -> bool:
    return bool(SKIP_LINE.match(line.strip()))
