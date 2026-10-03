import pytest

from control_layer.detectors.pii import find_pii


@pytest.mark.parametrize(
    ("text", "label", "value"),
    [
        ("Mój PESEL to 44051401359, sprawdź.", "pesel", "44051401359"),
        ("PESEL: 440514 01359", "pesel", "440514 01359"),
        ("Konto PL61 1090 1014 0000 0712 1981 2874.", "iban", "PL61 1090 1014 0000 0712 1981 2874"),
        ("Przelew na 61 1090 1014 0000 0712 1981 2874", "iban", "61 1090 1014 0000 0712 1981 2874"),
        ("Card 4111-1111-1111-1111 exp 12/29", "card", "4111-1111-1111-1111"),
        ("Pisz na jan.kowalski@example.com", "email", "jan.kowalski@example.com"),
        ("Zadzwoń: +48 601 234 567", "phone", "+48 601 234 567"),
        ("Tel. 601-234-567", "phone", "601-234-567"),
        ("NIP 123-456-32-18", "nip", "123-456-32-18"),
    ],
)
def test_pii_found_with_span_on_original_text(text: str, label: str, value: str) -> None:
    hits = find_pii(text)
    assert [(h[0], text[h[1] : h[2]]) for h in hits] == [(label, value)]


@pytest.mark.parametrize(
    "text",
    [
        "faktura 44051401358",  # bad PESEL checksum
        "zamówienie 4111111111111112",  # bad Luhn
        "Jak walidować PESEL w Pythonie?",
        "Spotkanie 2026-10-03 o 12:30, sala 101",
        "Konto PL61 1090 1014 0000 0712 1981 2875",  # bad mod 97
        "NIP 123-456-32-19",  # bad NIP checksum
    ],
)
def test_pii_look_alikes_pass(text: str) -> None:
    assert find_pii(text) == []


def test_entities_filter() -> None:
    text = "jan@example.com, PESEL 44051401359"
    assert [h[0] for h in find_pii(text, frozenset({"pesel"}))] == ["pesel"]
