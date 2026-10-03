from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from control_layer.core.policy import AgentSpec, ControlSpec, Defaults
from control_layer.core.signatures import SIGNATURE_KIND, SignatureParams
from control_layer.detectors import REGISTRY
from control_layer.detectors.canary import CanaryDetector
from control_layer.detectors.egress import EgressDetector, EgressParams
from control_layer.detectors.harmful_content import HarmfulContentDetector
from control_layer.detectors.injection_heuristics import InjectionHeuristics, InjectionParams
from control_layer.detectors.pii import PiiDetector, PiiParams
from control_layer.detectors.prompt_guard import PromptGuardDetector
from control_layer.detectors.secrets import LABELS, SecretsDetector, SecretsParams
from control_layer.egida.schema import (
    HELP,
    SECTION_MODELS,
    FieldSpec,
    check,
    detector_params,
    feed_rules,
    fields,
    help_for,
    parse_input,
)

FEED = Path(__file__).parents[3] / "signatures" / "feed.yaml"


def spec(model: type[BaseModel], name: str) -> FieldSpec:
    return next(s for s in fields(model) if s.name == name)


def test_detector_params_cover_every_registered_kind_and_signature() -> None:
    params = detector_params()

    assert set(params) == set(REGISTRY) | {SIGNATURE_KIND}
    classes = (
        PiiDetector,
        SecretsDetector,
        InjectionHeuristics,
        PromptGuardDetector,
        EgressDetector,
        HarmfulContentDetector,
        CanaryDetector,
    )
    assert {cls.kind: cls.Params for cls in classes} | {SIGNATURE_KIND: SignatureParams} == params


def test_fields_keep_declaration_order_and_skip() -> None:
    names = [s.name for s in fields(ControlSpec, skip={"params"})]

    assert names == list(ControlSpec.model_fields)[:-1]
    assert "params" not in names


def test_core_fields_are_classified() -> None:
    action = spec(ControlSpec, "action")
    assert (action.kind, action.choices, action.required) == (
        "choice",
        ("allow", "redact", "block"),
        True,
    )
    sides = spec(ControlSpec, "sides")
    assert (sides.kind, sides.choices) == ("multi", ("input", "output"))
    on_error = spec(ControlSpec, "on_error")
    assert (on_error.kind, on_error.choices, on_error.optional, on_error.default) == (
        "choice",
        ("block", "allow"),
        True,
        None,
    )
    timeout = spec(ControlSpec, "timeout_ms")
    assert (timeout.kind, timeout.optional) == ("int", True)
    assert spec(ControlSpec, "params").kind == "raw"
    assert spec(ControlSpec, "enabled").kind == "bool"
    assert spec(ControlSpec, "threshold").kind == "float"
    tools = spec(AgentSpec, "allowed_tools")
    assert (tools.kind, tools.choices, tools.default, tools.required) == ("list", (), [], False)
    assert spec(AgentSpec, "budget").kind == "text"


def test_detector_param_fields_are_classified() -> None:
    entities = spec(PiiParams, "entities")
    assert entities.kind == "multi"
    assert entities.default == ["email", "phone", "pesel", "nip", "iban", "card"]
    assert set(entities.default) <= set(entities.choices)
    assert spec(PiiParams, "extra_patterns").kind == "map"
    rules = spec(SecretsParams, "rules")
    assert (rules.kind, rules.choices, rules.default) == ("list", LABELS, list(LABELS))
    links = spec(EgressParams, "links")
    assert (links.kind, links.choices) == ("choice", ("with_data", "all"))
    assert links.default == "with_data"


@pytest.mark.parametrize(
    ("model", "name", "value"),
    [
        (ControlSpec, "threshold", 1.5),
        (ControlSpec, "timeout_ms", 0),
        (ControlSpec, "sides", []),
        (ControlSpec, "action", "deny"),
        (AgentSpec, "key_sha256", "xyz"),
        (Defaults, "on_error", "ignore"),
    ],
)
def test_check_rejects_values_outside_the_field_type(
    model: type[BaseModel], name: str, value: object
) -> None:
    with pytest.raises(ValueError, match=r"\S"):
        check(spec(model, name), value)


def test_check_returns_plain_normalized_values() -> None:
    assert check(spec(ControlSpec, "threshold"), 1) == 1.0
    assert check(spec(ControlSpec, "timeout_ms"), None) is None
    assert check(spec(ControlSpec, "sides"), ("output",)) == ["output"]
    assert check(spec(ControlSpec, "action"), "redact") == "redact"
    assert check(spec(AgentSpec, "key_sha256"), "a" * 64) == "a" * 64


def test_check_message_is_pydantic_readable() -> None:
    with pytest.raises(ValueError, match=r"^Input should be less than or equal to 1$"):
        check(spec(ControlSpec, "threshold"), 1.5)


def test_check_applies_model_field_validators() -> None:
    with pytest.raises(ValueError, match="extra_patterns"):
        check(spec(InjectionParams, "extra_patterns"), ["(unclosed"])
    with pytest.raises(ValueError, match="empty string"):
        check(spec(PiiParams, "extra_patterns"), {"ticket": "x*"})
    with pytest.raises(ValueError, match="unknown secret rules"):
        check(spec(SecretsParams, "rules"), ["nope"])
    assert check(spec(EgressParams, "allowed_domains"), ["Bank.Example."]) == ["bank.example"]


def test_parse_input_converts_text_by_kind() -> None:
    assert parse_input(spec(ControlSpec, "timeout_ms"), " 300 ") == 300
    assert parse_input(spec(ControlSpec, "timeout_ms"), "  ") is None
    assert parse_input(spec(ControlSpec, "threshold"), "0.25") == 0.25
    assert parse_input(spec(AgentSpec, "budget"), "  small ") == "small"
    assert parse_input(spec(ControlSpec, "params"), "{rule_action: redact}") == {
        "rule_action": "redact"
    }


@pytest.mark.parametrize(
    ("model", "name", "text", "message"),
    [
        (ControlSpec, "timeout_ms", "abc", "whole number"),
        (Defaults, "timeout_ms", "", "whole number"),
        (ControlSpec, "threshold", "high", "number"),
        (AgentSpec, "budget", "   ", "required"),
        (ControlSpec, "threshold", "2", "less than or equal to 1"),
        (ControlSpec, "params", "{a: [", "YAML"),
        (ControlSpec, "params", "42", "dictionary"),
    ],
)
def test_parse_input_rejects_bad_text(
    model: type[BaseModel], name: str, text: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_input(spec(model, name), text)


def test_help_covers_every_core_policy_field() -> None:
    expected = {
        f"{section}.{name}"
        for section, model in SECTION_MODELS.items()
        for name in model.model_fields
    }

    assert set(HELP) == expected | {"policy.version"}
    assert all(text.strip() and "\n" not in text for text in HELP.values())


def test_help_for_generates_detector_param_help() -> None:
    assert help_for("controls", spec(ControlSpec, "action")) == HELP["controls.action"]
    entities = help_for("params", spec(PiiParams, "entities"))
    assert "email, phone, pesel, nip, iban, card" in entities
    assert "8" in help_for("params", spec(SecretsParams, "entropy_min_len"))


def test_feed_rules_reads_rule_ids_in_file_order() -> None:
    rules = feed_rules(FEED)

    assert rules
    assert all(rule_id.startswith("SIG-") and title for rule_id, title in rules)
    assert [rule_id for rule_id, _ in rules] == sorted(
        (rule_id for rule_id, _ in rules), key=FEED.read_text().index
    )


def test_feed_rules_is_empty_for_missing_or_invalid_files(tmp_path: Path) -> None:
    broken = tmp_path / "feed.yaml"
    broken.write_text("rules: [")
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("feed_version: x\n")

    assert feed_rules(tmp_path / "missing.yaml") == []
    assert feed_rules(broken) == []
    assert feed_rules(invalid) == []
