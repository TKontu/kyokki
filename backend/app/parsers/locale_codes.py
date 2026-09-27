"""Normalise the language and country codes a model answers (Q27).

The prompt asks for ISO 639-1 and ISO 3166-1 alpha-2, but a model may answer "FIN", "fin" or
"fi-FI". These are standard code tables, not receipt formats: a three-letter code maps to its
two-letter form where the mapping is one-to-one, a locale such as "fi-FI" gives its language
or its country part, and anything else is unknown (None), so no profile runs on a guess.
"""

import re

# ISO 639-2/T and 639-2/B codes to ISO 639-1
_LANGUAGES_3_TO_2 = {
    "ara": "ar",
    "bos": "bs",
    "bul": "bg",
    "cat": "ca",
    "ces": "cs",
    "chi": "zh",
    "cze": "cs",
    "dan": "da",
    "deu": "de",
    "dut": "nl",
    "ell": "el",
    "eng": "en",
    "est": "et",
    "fin": "fi",
    "fra": "fr",
    "fre": "fr",
    "ger": "de",
    "gre": "el",
    "heb": "he",
    "hin": "hi",
    "hrv": "hr",
    "hun": "hu",
    "ice": "is",
    "isl": "is",
    "ita": "it",
    "jpn": "ja",
    "kor": "ko",
    "lav": "lv",
    "lit": "lt",
    "nld": "nl",
    "nob": "nb",
    "nno": "nn",
    "nor": "no",
    "pol": "pl",
    "por": "pt",
    "ron": "ro",
    "rum": "ro",
    "rus": "ru",
    "slk": "sk",
    "slo": "sk",
    "slv": "sl",
    "spa": "es",
    "srp": "sr",
    "swe": "sv",
    "tha": "th",
    "tur": "tr",
    "ukr": "uk",
    "vie": "vi",
    "zho": "zh",
}

# ISO 3166-1 alpha-3 to alpha-2
_COUNTRIES_3_TO_2 = {
    "AUS": "AU",
    "AUT": "AT",
    "BEL": "BE",
    "BGR": "BG",
    "BIH": "BA",
    "BRA": "BR",
    "CAN": "CA",
    "CHE": "CH",
    "CHN": "CN",
    "CYP": "CY",
    "CZE": "CZ",
    "DEU": "DE",
    "DNK": "DK",
    "ESP": "ES",
    "EST": "EE",
    "FIN": "FI",
    "FRA": "FR",
    "GBR": "GB",
    "GRC": "GR",
    "HRV": "HR",
    "HUN": "HU",
    "IND": "IN",
    "IRL": "IE",
    "ISL": "IS",
    "ISR": "IL",
    "ITA": "IT",
    "JPN": "JP",
    "KOR": "KR",
    "LTU": "LT",
    "LUX": "LU",
    "LVA": "LV",
    "MEX": "MX",
    "MLT": "MT",
    "NLD": "NL",
    "NOR": "NO",
    "NZL": "NZ",
    "POL": "PL",
    "PRT": "PT",
    "ROU": "RO",
    "RUS": "RU",
    "SRB": "RS",
    "SVK": "SK",
    "SVN": "SI",
    "SWE": "SE",
    "THA": "TH",
    "TUR": "TR",
    "UKR": "UA",
    "USA": "US",
    "VNM": "VN",
    "ZAF": "ZA",
}

# "fi", "FIN", or a locale "fi-FI" / "fi_FI"
_CODE = re.compile(r"^([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2,3}))?$")


def _parts(value: object) -> tuple[str, str | None] | None:
    if not isinstance(value, str):
        return None
    match = _CODE.match(value.strip())
    if not match:
        return None
    return match[1], match[2]


def language_code(value: object) -> str | None:
    """ISO 639-1 for an answered language code or locale; None when unknown."""
    parts = _parts(value)
    if parts is None:
        return None
    code = parts[0].casefold()
    if len(code) == 3:
        return _LANGUAGES_3_TO_2.get(code)
    return code


def country_code(value: object) -> str | None:
    """ISO 3166-1 alpha-2 for an answered country code or locale; None when unknown."""
    parts = _parts(value)
    if parts is None:
        return None
    code = (parts[1] if parts[1] is not None else parts[0]).upper()
    if len(code) == 3:
        return _COUNTRIES_3_TO_2.get(code)
    return code
