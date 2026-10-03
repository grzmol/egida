"""Checksum validators for PII numbers. Thin layer over python-stdnum (LGPL-2.1+).

We never write checksum code ourselves. All functions return False on malformed input.
"""

import re

from stdnum import iban, luhn
from stdnum.pl import nip, pesel

_SEPARATORS = re.compile(r"[\s.-]")


def strip_separators(value: str) -> str:
    return _SEPARATORS.sub("", value)


def is_pesel(digits: str) -> bool:
    return bool(pesel.is_valid(digits))


def is_nip(digits: str) -> bool:
    return bool(nip.is_valid(digits))


def is_iban(value: str) -> bool:
    return bool(iban.is_valid(value))


def is_card(digits: str) -> bool:
    return digits.isdigit() and 13 <= len(digits) <= 19 and bool(luhn.is_valid(digits))
