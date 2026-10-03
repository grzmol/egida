"""C04: PII finder (EN/PL) with checksum validation.

Returns spans on the original text. Numbers are accepted only with a valid
checksum (PESEL, NIP, IBAN mod 97, card Luhn), so look-alike order or invoice
numbers pass.
"""

import re
from collections.abc import Callable

from control_layer.detectors.validators import (
    is_card,
    is_iban,
    is_nip,
    is_pesel,
    strip_separators,
)

# Order matters: earlier patterns win on overlapping spans (an IBAN is not also a card).
PATTERNS: tuple[tuple[str, re.Pattern[str], Callable[[str], bool] | None], ...] = (
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
        is_iban,
    ),
    (
        "iban",  # Polish NRB: IBAN without the "PL" prefix
        re.compile(r"(?<![\d-])\d{2}(?: ?\d{4}){6}(?![\d-])"),
        lambda m: is_iban("PL" + strip_separators(m)),
    ),
    (
        "card",
        re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"),
        lambda m: is_card(strip_separators(m)),
    ),
    (
        "nip",
        re.compile(r"(?<![\d-])\d{3}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?![\d-])"),
        lambda m: is_nip(strip_separators(m)),
    ),
    (
        "pesel",
        re.compile(r"(?<![\d-])\d{6}[ -]?\d{5}(?![\d-])"),
        lambda m: is_pesel(strip_separators(m)),
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
ENTITIES = frozenset(label for label, _, _ in PATTERNS)


def find_pii(text: str, entities: frozenset[str] = ENTITIES) -> list[tuple[str, int, int]]:
    """(label, start, end) for each PII item of the given entity types, sorted by position."""
    hits: list[tuple[str, int, int]] = []
    for label, pattern, is_valid in PATTERNS:
        if label not in entities:
            continue
        for m in pattern.finditer(text):
            overlaps = any(m.start() < end and start < m.end() for _, start, end in hits)
            if not overlaps and (is_valid is None or is_valid(m.group())):
                hits.append((label, m.start(), m.end()))
    return sorted(hits, key=lambda h: h[1])
