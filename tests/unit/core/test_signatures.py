"""Signature feed (A5): schema, regex guard, rule self-tests, engine, scoped texts, cases."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import pickle
from typing import Any

import pytest

from control_layer.core.errors import FeedError, SignatureLimitError
from control_layer.core.models import Interaction, Message, Side, ToolCall, ToolDef
from control_layer.core.policy import build_policy
from control_layer.core.ports import FeedSnapshot
from control_layer.core.signatures import (
    SignatureParams,
    compile_feed,
    match_unit_text,
    scan_feed,
    signature_cases,
)
from control_layer.core.texts import ScopedText, iter_scoped_texts, iter_texts

PICKLE_P4_SYSTEM = "gASVHQAAAAAAAACMBXBvc2l4lIwGc3lzdGVtlJOUjAJpZJSFlFKULg=="  # posix.system("id")
PICKLE_P0_SYSTEM = "Y29zCnN5c3RlbQooUydpZCcKdFIu"  # protocol 0 os.system, no \x80 magic
PICKLE_P4_TRUNCATED = "gASVHQAAAAAAAACMBXBvc2l4lIwGc3lzdGVtlJOUjA=="


def _rule(rid: str = "SIG-0100", **overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": rid,
        "title": "test rule",
        "status": "stable",
        "severity": "high",
        "action": "block",
        "scope": ["input"],
        "decode": "none",
        "matchers": {"word": {"contains_any": ["attack"]}},
        "condition": "any",
        "tests": {"positive": ["an attack"], "negative": ["benign"]},
    }
    rule.update(overrides)
    return rule


def _feed(*rules: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    feed: dict[str, Any] = {
        "feed_version": "1.0.0",
        "generated_at": "2026-10-03T20:00:00Z",
        "source": "test",
        "rules": list(rules) or [_rule()],
    }
    feed.update(overrides)
    return feed


def _errors(raw: dict[str, Any]) -> list[str]:
    with pytest.raises(FeedError) as info:
        compile_feed(raw)
    return info.value.errors


def _compiled(**overrides: Any) -> Any:
    return compile_feed(_feed(_rule(**overrides))).rules[0]


def _items(
    text: str, scope: Any = "input", target: str = "messages[0].content"
) -> list[ScopedText]:
    return [ScopedText(scope, target, text, redactable=True)]


# --- schema ---------------------------------------------------------------------------


def test_minimal_feed_compiles() -> None:
    feed = compile_feed(_feed())
    assert feed.document.feed_version == "1.0.0"
    assert [r.rule.id for r in feed.rules] == ["SIG-0100"]


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        (_feed(_rule(), _rule()), "duplicate rule id: SIG-0100"),
        (_feed(_rule("SIG-1")), "rules.0.id"),
        (_feed(_rule(author="me")), "rules.0.author"),
        (_feed(_rule(matchers={"m": {"regex": "a", "flags": "i"}})), "flags"),
        (_feed(_rule(matchers={"m": {}})), "exactly one matcher field"),
        (_feed(_rule(matchers={"m": {"regex": "a", "contains_any": ["b"]}})), "exactly one"),
        (_feed(_rule(matchers={"m": {"prefix_hex": "abc"}})), "prefix_hex"),
        (_feed(_rule(matchers={"m": {"prefix_hex": "zz"}})), "prefix_hex"),
        (_feed(feed_version="1.0"), "feed_version"),
        (_feed(_rule(tests={"positive": ["an attack"], "negative": []})), "tests.negative"),
        (_feed(_rule(scope=["input", "input"])), "duplicate scope"),
    ],
    ids=[
        "duplicate-id",
        "bad-id",
        "unknown-rule-field",
        "unknown-matcher-field",
        "empty-matcher",
        "two-matcher-fields",
        "odd-hex",
        "non-hex",
        "short-version",
        "no-negative-test",
        "duplicate-scope",
    ],
)
def test_schema_rejects(raw: dict[str, Any], fragment: str) -> None:
    assert any(fragment in e for e in _errors(raw))


def test_sha256_must_match_the_rules() -> None:
    raw = _feed()
    canonical = json.dumps(raw["rules"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    good = hashlib.sha256(canonical.encode()).hexdigest()
    assert compile_feed({**raw, "sha256": good}).document.sha256 == good
    assert _errors({**raw, "sha256": "0" * 64}) == ["sha256: does not match rules"]


def test_validation_errors_never_echo_rule_tests() -> None:
    raw = _feed(_rule(severity="extreme", tests={"positive": ["SECRET-PAYLOAD"], "negative": []}))
    assert "SECRET-PAYLOAD" not in "; ".join(_errors(raw))


# --- regex guard and self-tests ------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "reason"),
    [
        ("(a+)+", "nested quantifier"),
        (r"(\w+\s?)*", "nested quantifier"),
        # security review: forms the old text-based guard missed
        ("((a+))+$", "nested quantifier"),
        ("(a|aa)+$", "nested quantifier"),
        ("(a?){30}a{30}", "nested quantifier"),
        (r"(\w{2,3})+", "nested quantifier"),
        (r"(a)\1", "backreference"),
        ("a" * 257, "longer than 256"),
        ("[", "invalid regex"),
    ],
)
def test_regex_guard_rejects_with_matcher_path(pattern: str, reason: str) -> None:
    errors = _errors(_feed(_rule(matchers={"call": {"regex": pattern}})))
    assert errors == [f"rules[0].matchers.call.regex: {errors[0].split(': ', 1)[1]}"]
    assert reason in errors[0]


@pytest.mark.parametrize(
    "pattern",
    [r"(?:\d{3}){2}", r"(?:ab)+", r"(ba|z|da)?sh\b", r"[a-z]+\s*=", r"(\.\w+)?\s+/dev/"],
)
def test_regex_guard_accepts_unambiguous_repeats(pattern: str) -> None:
    """Fixed counts, single-path bodies and optional groups (max 1) backtrack linearly."""
    errors = _errors(_feed(_rule(matchers={"call": {"regex": pattern}})))
    assert not [e for e in errors if ".regex:" in e]


def test_regex_guard_collects_every_error() -> None:
    raw = _feed(_rule(matchers={"a": {"regex": "(a+)+"}, "b": {"regex": "["}}))
    assert len(_errors(raw)) == 2


def test_rule_failing_its_own_tests_is_rejected_with_its_id() -> None:
    misses = _feed(_rule(tests={"positive": ["nothing here"], "negative": ["benign"]}))
    assert _errors(misses) == [
        "rules[SIG-0100].tests.positive[0]: rule does not match its own example"
    ]
    hits_benign = _feed(_rule(tests={"positive": ["an attack"], "negative": ["attack!"]}))
    assert _errors(hits_benign) == [
        "rules[SIG-0100].tests.negative[0]: rule matches its own example"
    ]


# --- engine -----------------------------------------------------------------------------


def _pickle_rule() -> Any:
    return _compiled(
        decode="base64",
        matchers={"magic": {"prefix_hex": "80"}, "call": {"contains_any": ["system"]}},
        condition="all",
        tests={"positive": [PICKLE_P4_SYSTEM], "negative": ["aGVsbG8gd29ybGQ="]},
    )


def test_condition_all_needs_every_matcher_in_the_same_base64_blob() -> None:
    rule = _pickle_rule()
    magic_only = base64.b64encode(b"\x80\x04 harmless data").decode()
    word_only = base64.b64encode(b"call system later").decode()
    assert match_unit_text(rule, f"{magic_only} and {word_only}") is False
    assert match_unit_text(rule, f"x {PICKLE_P4_SYSTEM} y") is True


def test_urlsafe_base64_without_padding_is_decoded() -> None:
    urlsafe = "gAT7__4gc3lzdGVtIGNhbGw"  # b"\x80\x04\xfb\xff\xfe system call", urlsafe, unpadded
    assert base64.urlsafe_b64decode(urlsafe + "=").startswith(b"\x80")
    assert match_unit_text(_pickle_rule(), urlsafe) is True


def test_more_than_64_base64_candidates_is_a_limit_error_not_a_silent_cut() -> None:
    text = " ".join(base64.b64encode(f"benign blob {i:04d}".encode()).decode() for i in range(65))
    with pytest.raises(SignatureLimitError, match="64"):
        match_unit_text(_pickle_rule(), text)


def test_png_data_uri_does_not_look_like_pickle() -> None:
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()
    assert match_unit_text(_pickle_rule(), f"data:image/png;base64,{png}") is False


def test_url_decoding() -> None:
    rule = _compiled(
        decode="url",
        matchers={"trav": {"regex": r"\.\./"}},
        tests={"positive": ["%2E%2E%2Fetc"], "negative": ["etc"]},
    )
    assert match_unit_text(rule, "file=%2E%2E%2Fetc%2Fpasswd") is True


def _globals_rule() -> Any:
    return _compiled(
        decode="base64",
        matchers={"g": {"pickle_globals": ["os.system", "posix.system", "builtins.eval"]}},
        tests={"positive": [PICKLE_P0_SYSTEM], "negative": ["aGVsbG8gd29ybGQ="]},
    )


@pytest.mark.parametrize("payload", [PICKLE_P0_SYSTEM, PICKLE_P4_SYSTEM, PICKLE_P4_TRUNCATED])
def test_pickle_globals_found_in_protocol_0_4_and_truncated_streams(payload: str) -> None:
    assert match_unit_text(_globals_rule(), payload) is True


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _only_rule(pattern: str, attack: bytes) -> Any:
    """A rule with one pickle_globals pattern; compiling it proves `attack` matches."""
    return _compiled(
        decode="base64",
        matchers={"g": {"pickle_globals": [pattern]}},
        tests={"positive": [_b64(attack)], "negative": ["aGVsbG8gd29ybGQ="]},
    )


# STACK_GLOBAL takes ("os", "system"); "builtins", "len" are pushed and popped as decoys.
PICKLE_DECOY = b"\x8c\x02os\x8c\x06system\x8c\x08builtins\x8c\x03len00\x93\x8c\x02id\x85R."
# Same import with the operands stored in the memo first and fetched with BINGET.
PICKLE_MEMO = (
    b"\x80\x04\x8c\x02os\x94\x8c\x06system\x94\x8c\x08builtins\x8c\x03len00"
    b"h\x00h\x01\x93\x8c\x02id\x85R."
)
PICKLE_P0_POPEN = b"cos\npopen\n(S'id'\ntR."


@pytest.mark.parametrize("raw", [PICKLE_DECOY, PICKLE_MEMO], ids=["decoy", "memo"])
def test_stack_global_operands_come_from_the_stack_not_the_last_strings(raw: bytes) -> None:
    assert match_unit_text(_only_rule("os.system", raw), _b64(raw)) is True
    decoy_rule = _only_rule("builtins.len", pickle.dumps(len, protocol=4))
    assert match_unit_text(decoy_rule, _b64(raw)) is False


def test_protocol_0_popen_global_is_reported() -> None:
    rule = _only_rule("os.popen", PICKLE_P0_POPEN)
    assert match_unit_text(rule, _b64(PICKLE_P0_POPEN)) is True


def test_stack_global_with_a_non_literal_operand_is_unresolved() -> None:
    # module name is BININT1 (not a string literal): the scanner cannot know what is imported
    raw = b"\x80\x04K\x01\x8c\x06system\x93."
    rule = _only_rule("[?].[?]", raw)
    assert match_unit_text(rule, _b64(raw)) is True
    assert match_unit_text(rule, PICKLE_P4_SYSTEM) is False


@pytest.mark.parametrize("protocol", [0, 2, 4, 5])
@pytest.mark.parametrize("value", [{"a": 1, "b": [1, 2]}, [1, "os", "system", (2, 3)], 7])
def test_benign_pickles_import_nothing(protocol: int, value: object) -> None:
    rule = _only_rule("*", PICKLE_DECOY)
    assert match_unit_text(rule, _b64(pickle.dumps(value, protocol=protocol))) is False


def test_pickle_globals_benign_and_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("the engine must never unpickle")

    monkeypatch.setattr(pickle, "loads", forbidden)
    monkeypatch.setattr(pickle, "load", forbidden)
    benign = base64.b64encode(pickle.dumps({"a": 1}, protocol=4)).decode()
    garbage = base64.b64encode(b"\xff\xfe\x00garbage-bytes-here").decode()
    assert match_unit_text(_globals_rule(), benign) is False
    assert match_unit_text(_globals_rule(), garbage) is False
    for raw in (PICKLE_DECOY, PICKLE_MEMO, PICKLE_P0_POPEN):  # would run `id` if unpickled
        assert match_unit_text(_only_rule("*", raw), _b64(raw)) is True


def _rm_rule() -> Any:
    return _compiled(
        scope=["tool_call.args"],
        matchers={"rm": {"regex": r"\brm\s+-rf\s+/(?=[\s\"]|$)"}},
        tests={"positive": ["rm -rf /"], "negative": ["rm -rf ./build"]},
    )


def test_json_escapes_in_tool_arguments_do_not_hide_a_command() -> None:
    feed = compile_feed(_feed(_rule(**{**_rm_rule().rule.model_dump(mode="json")})))
    escaped = '{"cmd": "\\u0072m -rf /"}'
    hits = scan_feed(
        feed,
        _items(escaped, "tool_call.args", "messages[1].tool_calls[0].arguments"),
        rule_action="block",
        disabled=frozenset(),
    )
    assert [h.rule.id for h in hits] == ["SIG-0100"]


def test_more_than_1000_json_leaves_is_a_limit_error() -> None:
    feed = compile_feed(_feed(_rm_rule().rule.model_dump(mode="json")))
    args = json.dumps({f"k{i}": "v" for i in range(600)})
    with pytest.raises(SignatureLimitError, match="1000"):
        scan_feed(feed, _items(args, "tool_call.args"), rule_action="block", disabled=frozenset())


def test_texts_over_200k_characters_are_a_limit_error() -> None:
    feed = compile_feed(_feed())
    with pytest.raises(SignatureLimitError):
        scan_feed(feed, _items("a" * 200_001), rule_action="block", disabled=frozenset())


def test_spans_are_exact_on_redactable_text_and_absent_on_read_only_text() -> None:
    feed = compile_feed(_feed(_rule(scope=["input", "model_ref", "tool_definition"])))
    items = [
        ScopedText("input", "messages[0].content", "an attack here", True),
        ScopedText("model_ref", "model", "attack-model", False),
        ScopedText("tool_definition", "tools[0].parameters_json", '{"attack": 1}', False),
    ]
    (hit,) = scan_feed(feed, items, rule_action="block", disabled=frozenset())
    assert hit.targets == ("messages[0].content", "model", "tools[0].parameters_json")
    assert [(s.target, s.start, s.end, s.label) for s in hit.spans] == [
        ("messages[0].content", 3, 9, "SIG-0100")
    ]


def test_scan_skips_deprecated_disabled_and_other_action_rules() -> None:
    feed = compile_feed(
        _feed(
            _rule("SIG-0101"),
            _rule("SIG-0102", status="deprecated"),
            _rule("SIG-0103", action="redact"),
            _rule("SIG-0104"),
        )
    )
    hits = scan_feed(
        feed, _items("an attack"), rule_action="block", disabled=frozenset({"SIG-0104"})
    )
    assert [h.rule.id for h in hits] == ["SIG-0101"]
    redact = scan_feed(feed, _items("an attack"), rule_action="redact", disabled=frozenset())
    assert [h.rule.id for h in redact] == ["SIG-0103"]


# --- scoped texts ---------------------------------------------------------------------------


def test_iter_scoped_texts_classifies_every_input_text() -> None:
    interaction = Interaction(
        request_id="r",
        agent_id="a",
        model="m",
        messages=(
            Message("system", "s"),
            Message("user", "u"),
            Message("assistant", "", tool_calls=(ToolCall("c", "t", '{"x": 1}'),)),
            Message("tool", "result", tool_call_id="c"),
        ),
        tools=(ToolDef("t", "desc", '{"type": "object"}'),),
    )
    got = [(s.scope, s.target, s.redactable) for s in iter_scoped_texts(interaction, Side.INPUT)]
    assert got == [
        ("input", "messages[0].content", True),
        ("input", "messages[1].content", True),
        ("input", "messages[2].content", True),
        ("tool_call.args", "messages[2].tool_calls[0].arguments", True),
        ("tool_result", "messages[3].content", True),
        ("tool_definition", "tools[0].description", True),
        ("tool_definition", "tools[0].parameters_json", True),
        ("model_ref", "model", False),
    ]
    redactable = [s.target for s in iter_scoped_texts(interaction, Side.INPUT) if s.redactable]
    assert redactable == [t for t, _ in iter_texts(interaction, Side.INPUT)]

    with_output = Interaction(
        request_id="r",
        agent_id="a",
        model="m",
        messages=(Message("user", "u"),),
        output=Message("assistant", "o", tool_calls=(ToolCall("c", "t", "{}"),)),
    )
    out = [(s.scope, s.target) for s in iter_scoped_texts(with_output, Side.OUTPUT)]
    assert out == [
        ("output", "output.content"),
        ("tool_call.args", "output.tool_calls[0].arguments"),
    ]


# --- selftest cases ------------------------------------------------------------------------


def _snapshot(*rules: dict[str, Any]) -> FeedSnapshot:
    return FeedSnapshot(compile_feed(_feed(*rules)), "1.0.0", "a" * 64, 0.0, "test")


def _policy(policy_dict: dict[str, Any], controls: list[dict[str, Any]]) -> Any:
    policy_dict = copy.deepcopy(policy_dict)
    policy_dict["controls"] = controls
    return build_policy(policy_dict, {"signature": SignatureParams})


SIGNATURES = {"id": "sigs", "kind": "signature", "sides": ["input", "output"], "action": "block"}


def test_cases_map_rule_tests_to_attack_and_benign_probes(policy_dict: dict[str, Any]) -> None:
    snapshot = _snapshot(
        _rule("SIG-0101"),
        _rule("SIG-0102", scope=["output", "tool_call.args"]),
        _rule("SIG-0103", scope=["model_ref", "output"]),
        _rule("SIG-0104", scope=["tool_definition"]),
    )
    body = signature_cases(snapshot, _policy(policy_dict, [SIGNATURES]), "demo-agent")
    cases = {c["id"]: c for c in body["cases"]}
    attack = cases["sig-sig-0101-atk-0"]
    assert attack["polarity"] == "negative"
    assert attack["expect"] == {"decision": "block", "control_id": "sigs", "tag": "sig.SIG-0101"}
    assert attack["request"]["messages"] == [{"role": "user", "content": "an attack"}]
    assert cases["sig-sig-0101-ok-0"]["expect"] == {"absent_tag": "sig.SIG-0101"}
    args = cases["sig-sig-0102-atk-0"]["request"]["messages"][1]["tool_calls"][0]
    assert json.loads(args["function"]["arguments"]) == {"input": "an attack"}
    assert body["skipped"] == [
        {"rule_id": "SIG-0103", "reason": "no scope reachable over HTTP: ['model_ref', 'output']"}
    ]
    names = [t["function"]["name"] for c in body["cases"] for t in c["request"].get("tools", [])]
    assert len(names) == len(set(names)) == 4


def test_no_signature_control_skips_every_rule(policy_dict: dict[str, Any]) -> None:
    body = signature_cases(_snapshot(_rule()), _policy(policy_dict, []), "demo-agent")
    assert body["cases"] == []
    assert [s["rule_id"] for s in body["skipped"]] == ["SIG-0100"]


def test_line_wrapped_base64_payload_is_rejoined() -> None:
    """MIME / base64.encodebytes wrap at 76 characters; a wrapped pickle must still match."""
    wrapped = (
        PICKLE_P4_SYSTEM[:20] + "\n" + PICKLE_P4_SYSTEM[20:40] + "\r\n  " + PICKLE_P4_SYSTEM[40:]
    )
    assert match_unit_text(_pickle_rule(), wrapped) is True
    assert match_unit_text(_globals_rule(), wrapped) is True
    assert match_unit_text(_pickle_rule(), "aGVsbG8gd29y\nbGQgaGVsbG8gd29ybGQ=") is False
