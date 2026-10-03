import time

import pytest
from pydantic import ValidationError

from control_layer.core.models import Category, Interaction, Message, Side, ToolCall
from control_layer.core.ports import ScanContext
from control_layer.detectors.pii import PiiDetector, PiiParams, find_pii


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


def test_params_reject_bad_regex_and_unknown_entity() -> None:
    with pytest.raises(ValidationError):
        PiiParams(extra_patterns={"badge": "("})
    with pytest.raises(ValidationError):
        PiiParams.model_validate({"entities": ["pesel", "ssn"]})


@pytest.mark.anyio
async def test_detector_spans_cover_every_input_text() -> None:
    interaction = Interaction(
        request_id="req_1",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=(
            Message(role="system", content="Support bot."),
            Message(role="user", content="Mój PESEL to 44051401359."),
            Message(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="c1", name="lookup", arguments='{"email": "a@b.pl"}'),),
            ),
        ),
    )
    ctx = ScanContext(
        interaction, Side.INPUT, "pii", PiiParams(extra_patterns={"badge": r"B-\d{4}"})
    )
    [finding] = await PiiDetector().scan(ctx)
    assert finding.category == Category.PII
    assert finding.score == 1.0
    assert [(s.target, s.label, s.start, s.end) for s in finding.spans] == [
        ("messages[1].content", "pesel", 13, 24),
        ("messages[2].tool_calls[0].arguments", "email", 11, 17),
    ]
    assert "44051401359" not in finding.evidence
    assert "pesel 44*******59@messages[1].content" in finding.evidence


@pytest.mark.anyio
async def test_detector_finds_nothing_in_clean_output() -> None:
    interaction = Interaction(
        request_id="req_2",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=(Message(role="user", content="PESEL 44051401359"),),
        output=Message(role="assistant", content="Nie mogę pomóc z danymi osobowymi."),
    )
    ctx = ScanContext(interaction, Side.OUTPUT, "pii", PiiParams())
    assert await PiiDetector().scan(ctx) == []


@pytest.mark.parametrize("unit", ["a.", "a-", "a+", "a@b.co ", "601 234 567 "])
def test_adversarial_input_scans_in_linear_time(unit: str) -> None:
    text = unit * (100_000 // len(unit))
    started = time.perf_counter()
    find_pii(text)
    assert time.perf_counter() - started < 0.5


def test_params_reject_empty_match_and_entity_clash() -> None:
    with pytest.raises(ValidationError):
        PiiParams(extra_patterns={"badge": r"\d*"})
    with pytest.raises(ValidationError):
        PiiParams(extra_patterns={"email": r"x@y"})
