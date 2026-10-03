"""C04: PII finder (EN/PL) with checksum validation.

Returns spans on the original text. Numbers are accepted only with a valid
checksum (PESEL, IBAN mod 97, card Luhn), so look-alike order or invoice
numbers pass. Checksums come from python-stdnum, not hand-written code.
"""

import re
from collections.abc import Callable

from stdnum import iban, luhn
from stdnum.pl import pesel

_SEPARATORS = re.compile(r"[ -]")


def _digits(match: str) -> str:
    return _SEPARATORS.sub("", match)


def _valid_card(match: str) -> bool:
    number = _digits(match)
    return 13 <= len(number) <= 19 and luhn.is_valid(number)


# Order matters: earlier patterns win on overlapping spans (an IBAN is not also a card).
_PATTERNS: tuple[tuple[str, re.Pattern[str], Callable[[str], bool] | None], ...] = (
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
        lambda m: bool(iban.is_valid(m)),
    ),
    (
        "iban",  # Polish NRB: IBAN without the "PL" prefix
        re.compile(r"(?<![\d-])\d{2}(?: ?\d{4}){6}(?![\d-])"),
        lambda m: bool(iban.is_valid("PL" + _digits(m))),
    ),
    ("card", re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"), _valid_card),
    (
        "pesel",
        re.compile(r"(?<![\d-])\d{6}[ -]?\d{5}(?![\d-])"),
        lambda m: bool(pesel.is_valid(_digits(m))),
    ),
    (
        "phone",
        re.compile(
            r"(?<![\w+])(?:\+\d{2,3}[ -]?)?\d{3}[ -]\d{3}[ -]\d{3}(?!\d)|\+\d{2,3}\d{9}(?!\d)"
        ),
        None,
    ),
    ("email", re.compile(r"\b[\w.%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), None),
)


def find_pii(text: str) -> list[tuple[str, int, int]]:
    """(label, start, end) for each PII item in `text`, sorted by position."""
    hits: list[tuple[str, int, int]] = []
    for label, pattern, is_valid in _PATTERNS:
        for m in pattern.finditer(text):
            overlaps = any(m.start() < end and start < m.end() for _, start, end in hits)
            if not overlaps and (is_valid is None or is_valid(m.group())):
                hits.append((label, m.start(), m.end()))
    return sorted(hits, key=lambda h: h[1])
