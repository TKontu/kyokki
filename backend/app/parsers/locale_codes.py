"""Normalise the language and country codes a model answers (Q27).

The prompt asks for ISO 639-1 and ISO 3166-1 alpha-2, but a model may answer "FIN", "fin" or
"fi-FI". These are standard code tables, not receipt formats: a three-letter code maps to its
two-letter form where the mapping is one-to-one, a locale such as "fi-FI" gives its language
or its country part, and anything else is unknown (None), so no profile runs on a guess.
A two-letter code must be a real ISO 639-1 or ISO 3166-1 code (pycountry's tables when it is
installed, else the embedded ones below); "UK" is read as GB (PR #131 F17).
"""

import importlib
import re
from types import ModuleType


def _pycountry() -> ModuleType | None:
    """The full ISO tables when pycountry is installed; not a dependency."""
    try:
        return importlib.import_module("pycountry")
    except ImportError:
        return None


pycountry = _pycountry()

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


def _codes(text: str) -> frozenset[str]:
    return frozenset(text.split())


# ISO 639-1: every two-letter language code
_LANGUAGES_2 = _codes(
    """
    aa ab ae af ak am an ar as av ay az ba be bg bi bm bn bo br bs ca ce ch co cr cs cu
    cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he
    hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko
    kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd
    ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se
    sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty
    ug uk ur uz ve vi vo wa wo xh yi yo za zh zu
    """
)

# ISO 3166-1 alpha-2: every officially assigned country code (as in tzdata's iso3166.tab)
_COUNTRIES_2 = _codes(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN
    BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
    DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL
    GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM
    JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME
    MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP
    NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD
    SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
    TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """
)
# The one alias every model answers: the United Kingdom is GB in ISO 3166-1
_COUNTRY_ALIASES = {"UK": "GB"}

# "fi", "FIN", or a locale "fi-FI" / "fi_FI"
_CODE = re.compile(r"^([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2,3}))?$")


def _parts(value: object) -> tuple[str, str | None] | None:
    if not isinstance(value, str):
        return None
    match = _CODE.match(value.strip())
    if not match:
        return None
    return match[1], match[2]


def _known_language(code: str) -> bool:
    if pycountry is not None:
        return pycountry.languages.get(alpha_2=code) is not None
    return code in _LANGUAGES_2


def _known_country(code: str) -> bool:
    if pycountry is not None:
        return pycountry.countries.get(alpha_2=code) is not None
    return code in _COUNTRIES_2


def language_code(value: object) -> str | None:
    """ISO 639-1 for an answered language code or locale; None when unknown."""
    parts = _parts(value)
    if parts is None:
        return None
    code = parts[0].casefold()
    if len(code) == 3:
        return _LANGUAGES_3_TO_2.get(code)
    return code if _known_language(code) else None


def country_code(value: object) -> str | None:
    """ISO 3166-1 alpha-2 for an answered country code or locale; None when unknown."""
    parts = _parts(value)
    if parts is None:
        return None
    code = (parts[1] if parts[1] is not None else parts[0]).upper()
    if len(code) == 3:
        return _COUNTRIES_3_TO_2.get(code)
    code = _COUNTRY_ALIASES.get(code, code)
    return code if _known_country(code) else None
