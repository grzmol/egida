from collections.abc import Callable

import pytest

from control_layer.detectors.validators import (
    is_card,
    is_iban,
    is_nip,
    is_pesel,
    strip_separators,
)


def test_strip_separators() -> None:
    assert strip_separators("440514 01359") == "44051401359"
    assert strip_separators("123-456-32.18") == "1234563218"


@pytest.mark.parametrize(
    ("check", "valid", "invalid"),
    [
        (is_pesel, "44051401359", "44051401358"),
        (is_nip, "1234563218", "1234563219"),
        (is_iban, "PL61 1090 1014 0000 0712 1981 2874", "PL61 1090 1014 0000 0712 1981 2875"),
        (is_card, "4111111111111111", "4111111111111112"),
    ],
)
def test_checksums(check: Callable[[str], bool], valid: str, invalid: str) -> None:
    assert check(valid) is True
    assert check(invalid) is False


@pytest.mark.parametrize("check", [is_pesel, is_nip, is_iban, is_card])
@pytest.mark.parametrize("value", ["", "abc", "4111 1111", "١٢٣٤٥٦٧٨٩٠١"])
def test_malformed_input_is_false_without_exception(
    check: Callable[[str], bool], value: str
) -> None:
    assert check(value) is False
