"""Signature feed of known attacks (R4, C10, C11, C18; research 04 §5).

Pure logic: the feed schema (Pydantic), load-time checks (regex guard, every rule passes its own
tests), the matching engine and the selftest cases derived from the rules' tests. The file
adapter (adapters/feed_file.py) reads YAML; SignatureDetector runs scan_feed per request.

Never unpickles: pickle payloads are inspected with pickletools.genops only.
"""

from __future__ import annotations

import base64
import binascii
import fnmatch
import hashlib
import json
import pickletools
import re
import urllib.parse
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from control_layer.core.errors import FeedError, SignatureLimitError
from control_layer.core.models import Side, Span
from control_layer.core.policy import Policy
from control_layer.core.texts import Scope, ScopedText

if TYPE_CHECKING:
    from control_layer.core.ports import FeedSnapshot

__all__ = [
    "SEVERITY_SCORE",
    "SIGNATURE_KIND",
    "CompiledFeed",
    "CompiledRule",
    "FeedDocument",
    "RuleHit",
    "SignatureParams",
    "SignatureRule",
    "compile_feed",
    "match_unit_text",
    "scan_feed",
    "signature_cases",
]

SIGNATURE_KIND: Final = "signature"
Severity = Literal["low", "medium", "high", "critical"]
SEVERITY_SCORE: Final[dict[str, float]] = {
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "critical": 1.0,
}

MAX_TEXT_CHARS: Final = 200_000
MAX_JSON_LEAVES: Final = 1000
MAX_BASE64_CANDIDATES: Final = 64
MAX_DECODED_BYTES: Final = 1 << 20
MAX_PATTERN_CHARS: Final = 256

_BASE64_CANDIDATE = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{16,}={0,2}")
_BACKREFERENCE = re.compile(r"\\[1-9]|\(\?P=")
_NESTED_QUANTIFIER = re.compile(
    r"\((?:[^()\\]|\\.)*(?:[+*]|\{\d*,\d*\})(?:[^()\\]|\\.)*\)(?:[+*]|\{\d*,\d*\})"
)
_PICKLE_STRINGS = frozenset(
    {
        "SHORT_BINUNICODE",
        "BINUNICODE",
        "BINUNICODE8",
        "UNICODE",
        "STRING",
        "BINSTRING",
        "SHORT_BINSTRING",
    }
)
_PROBE_SCOPES: Final[tuple[Scope, ...]] = (
    "input",
    "tool_result",
    "tool_call.args",
    "tool_definition",
)

Text200 = Annotated[str, Field(min_length=1, max_length=200)]
TestText = Annotated[str, Field(max_length=4096)]


# --- schema -------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Matcher(_Strict):
    """Exactly one field set."""

    regex: str | None = None  # re.search; flags inline only, e.g. (?i)
    contains_any: tuple[Text200, ...] | None = Field(default=None, min_length=1, max_length=100)
    prefix_hex: str | None = Field(default=None, pattern=r"^(?:[0-9a-fA-F]{2}){1,32}$")
    pickle_globals: tuple[Text200, ...] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _exactly_one(self) -> Matcher:
        set_fields = [name for name in type(self).model_fields if getattr(self, name) is not None]
        if len(set_fields) != 1:
            raise ValueError(f"exactly one matcher field required, got {set_fields or 'none'}")
        return self


class RuleTests(_Strict):
    positive: tuple[TestText, ...] = Field(min_length=1)  # the rule MUST match each
    negative: tuple[TestText, ...] = Field(min_length=1)  # the rule MUST NOT match any


class SignatureRule(_Strict):
    id: str = Field(pattern=r"^SIG-\d{4}$")
    title: Text200
    status: Literal["experimental", "stable", "deprecated"]
    severity: Severity
    action: Literal["block", "redact"]
    scope: tuple[Scope, ...] = Field(min_length=1)
    decode: Literal["none", "base64", "url"] = "none"
    matchers: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")], Matcher] = Field(
        min_length=1, max_length=8
    )
    condition: Literal["any", "all"]
    tags: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    tests: RuleTests

    @field_validator("scope")
    @classmethod
    def _unique_scope(cls, scope: tuple[Scope, ...]) -> tuple[Scope, ...]:
        if len(set(scope)) != len(scope):
            raise ValueError("duplicate scope")
        return scope


class FeedDocument(_Strict):
    feed_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    generated_at: datetime
    source: Text200
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rules: tuple[SignatureRule, ...] = Field(min_length=1, max_length=500)

    @field_validator("rules")
    @classmethod
    def _unique_ids(cls, rules: tuple[SignatureRule, ...]) -> tuple[SignatureRule, ...]:
        counts = Counter(r.id for r in rules)
        duplicates = sorted(rid for rid, n in counts.items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate rule id: {', '.join(duplicates)}")
        return rules


class SignatureParams(_Strict):
    """Params of a `kind: signature` control."""

    rule_action: Literal["block", "redact"] = "block"  # which rules (by rule.action) it runs
    disabled_rules: tuple[str, ...] = ()  # policy override (04 §5); unknown ids are ignored


# --- compiled form ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompiledRule:
    rule: SignatureRule
    matchers: tuple[tuple[str, Matcher, re.Pattern[str] | None], ...]


@dataclass(frozen=True, slots=True)
class CompiledFeed:
    document: FeedDocument
    rules: tuple[CompiledRule, ...]


@dataclass(frozen=True, slots=True)
class RuleHit:
    rule: SignatureRule
    scope: Scope
    targets: tuple[str, ...]
    spans: tuple[Span, ...]


def compile_feed(raw: Mapping[str, object]) -> CompiledFeed:
    """Validate and compile a parsed feed. FeedError lists every problem as 'path: reason'.
    Order: schema → sha256 → regex guard and re.compile → each rule against its own tests."""
    try:
        document = FeedDocument.model_validate(raw)
    except ValidationError as exc:
        # no input_value: rule tests may contain attack payloads
        raise FeedError(
            [".".join(str(p) for p in e["loc"]) + f": {e['msg']}" for e in exc.errors()]
        ) from exc
    if document.sha256 is not None:
        canonical = json.dumps(
            raw["rules"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if hashlib.sha256(canonical.encode()).hexdigest() != document.sha256:
            raise FeedError(["sha256: does not match rules"])

    errors: list[str] = []
    compiled: list[CompiledRule] = []
    for i, rule in enumerate(document.rules):
        matchers: list[tuple[str, Matcher, re.Pattern[str] | None]] = []
        for name, matcher in rule.matchers.items():
            pattern = None
            if matcher.regex is not None:
                path = f"rules[{i}].matchers.{name}.regex"
                problem = _regex_problem(matcher.regex)
                if problem:
                    errors.append(f"{path}: {problem}")
                    continue
                try:
                    pattern = re.compile(matcher.regex)
                except re.error as exc:
                    errors.append(f"{path}: invalid regex: {exc}")
                    continue
            matchers.append((name, matcher, pattern))
        compiled.append(CompiledRule(rule, tuple(matchers)))
    if errors:
        raise FeedError(errors)

    for item in compiled:
        rid = item.rule.id
        for kind, texts, expected in (
            ("positive", item.rule.tests.positive, True),
            ("negative", item.rule.tests.negative, False),
        ):
            for j, text in enumerate(texts):
                try:
                    matched = match_unit_text(item, text)
                except SignatureLimitError as exc:
                    errors.append(f"rules[{rid}].tests.{kind}[{j}]: {exc}")
                    continue
                if matched != expected:
                    verb = "does not match" if expected else "matches"
                    errors.append(f"rules[{rid}].tests.{kind}[{j}]: rule {verb} its own example")
    if errors:
        raise FeedError(errors)
    return CompiledFeed(document, tuple(compiled))


def _regex_problem(pattern: str) -> str | None:
    """Static guard (Python re has no timeout): reject patterns prone to heavy backtracking."""
    if len(pattern) > MAX_PATTERN_CHARS:
        return f"longer than {MAX_PATTERN_CHARS} characters"
    if _BACKREFERENCE.search(pattern):
        return "backreference"
    if _NESTED_QUANTIFIER.search(pattern):
        return "nested quantifier"
    return None


# --- engine -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    raw: bytes
    origin: tuple[int, int] | None  # position in the scanned text; None = matcher positions apply


def match_unit_text(rule: CompiledRule, text: str) -> bool:
    """Whether the rule matches this text alone (no JSON leaves): used for the rules' own tests."""
    _check_length(text)
    return any(
        _match_unit(rule, unit) is not None for unit in _decoded(rule.rule.decode, text, None)
    )


def scan_feed(
    feed: CompiledFeed,
    items: Sequence[ScopedText],
    *,
    rule_action: str,
    disabled: frozenset[str],
) -> list[RuleHit]:
    """One hit per matching rule with all its targets and spans (spans only on redactable texts)."""
    for item in items:
        _check_length(item.text)
    hits: list[RuleHit] = []
    for compiled in feed.rules:
        rule = compiled.rule
        if rule.status == "deprecated" or rule.action != rule_action or rule.id in disabled:
            continue
        scopes: list[Scope] = []
        targets: list[str] = []
        spans: list[Span] = []
        for item in items:
            if item.scope not in rule.scope:
                continue
            found = _match_item(compiled, item)
            if found is None:
                continue
            scopes.append(item.scope)
            targets.append(item.target)
            if item.redactable:
                spans += [Span(item.target, start, end, rule.id) for start, end in found]
        if targets:
            hits.append(RuleHit(rule, scopes[0], tuple(targets), tuple(spans)))
    return hits


def _check_length(text: str) -> None:
    if len(text) > MAX_TEXT_CHARS:
        raise SignatureLimitError(f"text of {len(text)} characters exceeds {MAX_TEXT_CHARS}")


def _match_item(rule: CompiledRule, item: ScopedText) -> list[tuple[int, int]] | None:
    """Spans (in item.text) of the units the rule matches, or None when nothing matches."""
    found: list[tuple[int, int]] = []
    for base, whole in _base_units(item):
        for unit in _decoded(rule.rule.decode, base, None if whole else (0, len(item.text))):
            spans = _match_unit(rule, unit)
            if spans is not None:
                found += [unit.origin] if unit.origin else spans
    return found or None


def _base_units(item: ScopedText) -> Iterator[tuple[str, bool]]:
    """(text, is_the_scanned_text): the text itself, plus JSON keys and string leaves of tool
    arguments and parameter schemas (a JSON escape like \\u0072m must not hide `rm`)."""
    yield item.text, True
    if item.scope != "tool_call.args" and not item.target.endswith(".parameters_json"):
        return
    try:
        data = json.loads(item.text)
    except json.JSONDecodeError:
        return
    leaves: list[str] = []
    stack: list[object] = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                leaves.append(key)
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            leaves.append(node)
        if len(leaves) > MAX_JSON_LEAVES:
            raise SignatureLimitError(f"more than {MAX_JSON_LEAVES} JSON keys and strings")
    for leaf in leaves:
        yield leaf, False


def _decoded(decode: str, text: str, origin: tuple[int, int] | None) -> Iterator[_Unit]:
    if decode == "none":
        yield _Unit(text, text.encode("utf-8"), origin)
        return
    if decode == "url":
        plain = urllib.parse.unquote(text, errors="replace")
        yield _Unit(plain, plain.encode("utf-8"), origin or (0, len(text)))
        return
    candidates = list(_BASE64_CANDIDATE.finditer(text))
    if len(candidates) > MAX_BASE64_CANDIDATES:
        raise SignatureLimitError(f"more than {MAX_BASE64_CANDIDATES} base64 candidates")
    total = 0
    for m in candidates:
        blob = m.group().replace("-", "+").replace("_", "/")
        blob += "=" * (-len(blob) % 4)
        try:
            raw = base64.b64decode(blob, validate=True)
        except binascii.Error:
            continue
        total += len(raw)
        if total > MAX_DECODED_BYTES:
            raise SignatureLimitError(f"more than {MAX_DECODED_BYTES} decoded base64 bytes")
        yield _Unit(raw.decode("latin-1"), raw, origin or m.span())


def _match_unit(rule: CompiledRule, unit: _Unit) -> list[tuple[int, int]] | None:
    results = [_match_one(matcher, pattern, unit) for _, matcher, pattern in rule.matchers]
    hits = [r for r in results if r is not None]
    matched = len(hits) == len(results) if rule.rule.condition == "all" else bool(hits)
    return hits if matched else None


def _match_one(
    matcher: Matcher, pattern: re.Pattern[str] | None, unit: _Unit
) -> tuple[int, int] | None:
    if pattern is not None:
        m = pattern.search(unit.text)
        return m.span() if m else None
    if matcher.contains_any is not None:
        for needle in matcher.contains_any:
            index = unit.text.find(needle)
            if index >= 0:
                return index, index + len(needle)
        return None
    if matcher.prefix_hex is not None:
        prefix = bytes.fromhex(matcher.prefix_hex)
        return (0, min(len(prefix), len(unit.text))) if unit.raw.startswith(prefix) else None
    if matcher.pickle_globals is None:  # unreachable: the schema sets exactly one field
        raise ValueError("matcher without a field")
    for found in _pickle_globals(unit.raw):
        if any(fnmatch.fnmatchcase(found, p) for p in matcher.pickle_globals):
            return 0, len(unit.text)
    return None


def _pickle_globals(raw: bytes) -> list[str]:
    """'module.name' of GLOBAL / STACK_GLOBAL imports, read with pickletools (never unpickled).
    A truncated or corrupt stream keeps what was collected before the error."""
    found: list[str] = []
    strings: list[str] = []
    try:
        for opcode, arg, _ in pickletools.genops(raw):
            if opcode.name == "GLOBAL" and isinstance(arg, str):
                found.append(arg.replace(" ", ".", 1))
            elif opcode.name in _PICKLE_STRINGS:
                strings.append(arg.decode("latin-1") if isinstance(arg, bytes) else str(arg))
            elif opcode.name == "STACK_GLOBAL" and len(strings) >= 2:
                found.append(f"{strings[-2]}.{strings[-1]}")
    except ValueError:
        pass
    return found


# --- selftest cases -----------------------------------------------------------------


def signature_cases(snapshot: FeedSnapshot, policy: Policy, agent_id: str) -> dict[str, object]:
    """The feed rules' own tests as live selftest cases (R4 + R6): attack examples must be
    caught by the policy's signature control, benign examples must not carry the rule's tag."""
    agent = policy.agents[agent_id]
    version = snapshot.version
    cases: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    for compiled in snapshot.feed.rules:
        rule = compiled.rule
        if rule.status == "deprecated":
            continue
        control = next(
            (
                c
                for c in policy.controls
                if c.enabled
                and c.kind == SIGNATURE_KIND
                and Side.INPUT in c.sides
                and isinstance(c.params, SignatureParams)
                and c.params.rule_action == rule.action
            ),
            None,
        )
        scope = next((s for s in rule.scope if s in _PROBE_SCOPES), None)
        if control is None:
            reason = f"no enabled control kind={SIGNATURE_KIND} with rule_action={rule.action}"
            skipped.append({"rule_id": rule.id, "reason": reason})
            continue
        if scope is None:
            skipped.append(
                {"rule_id": rule.id, "reason": f"no scope reachable over HTTP: {list(rule.scope)}"}
            )
            continue
        for kind, texts in (("atk", rule.tests.positive), ("ok", rule.tests.negative)):
            for i, text in enumerate(texts):
                tool = f"sig_probe_{rule.id.lower().replace('-', '_')}_{kind}_{i}"
                expect: dict[str, object] = (
                    {
                        "decision": control.action.value,
                        "control_id": control.id,
                        "tag": f"sig.{rule.id}",
                    }
                    if kind == "atk"
                    else {"absent_tag": f"sig.{rule.id}"}
                )
                cases.append(
                    {
                        "id": f"sig-{rule.id.lower()}-{kind}-{i}",
                        "rule_id": rule.id,
                        "scope": scope,
                        "source": f"feed:{version}",
                        "control": control.id,
                        "polarity": "negative" if kind == "atk" else "positive",
                        "agent": agent_id,
                        "request": {"model": agent.allowed_models[0], **_probe(scope, text, tool)},
                        "expect": expect,
                    }
                )
    return {"feed_version": version, "agent": agent_id, "cases": cases, "skipped": skipped}


def _probe(scope: Scope, text: str, tool: str) -> dict[str, object]:
    if scope == "input":
        return {"messages": [{"role": "user", "content": text}]}
    if scope == "tool_definition":
        return {
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool,
                        "description": text,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        }
    arguments = (
        json.dumps({"input": text}, ensure_ascii=False) if scope == "tool_call.args" else "{}"
    )
    result = "ok" if scope == "tool_call.args" else text
    call = {
        "id": "call_sig",
        "type": "function",
        "function": {"name": tool, "arguments": arguments},
    }
    return {
        "messages": [
            {"role": "user", "content": "Use the tool."},
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "call_sig", "content": result},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool,
                    "description": "Selftest probe tool.",
                    "parameters": {"type": "object", "properties": {"input": {"type": "string"}}},
                },
            }
        ],
    }
