"""C06: prompt-injection heuristics (EN/PL) on normalized text views.

Patterns run on `normalize.views()` output: lowercase, no diacritics, Latin
look-alikes folded, base64/ROT13 decoded. They are deliberately narrow; the
false-positive traps from docs/research/11-brainstorm-red-team.md §2 must pass.
"""

import re
from typing import ClassVar

import anyio
from pydantic import BaseModel, ConfigDict, field_validator

from control_layer.core.models import Category, Finding
from control_layer.core.ports import ScanContext
from control_layer.core.texts import iter_texts
from control_layer.detectors.common import EVIDENCE_MAX
from control_layer.detectors.normalize import mixed_script_words, views

_EN_ADJ = r"(previous|prior|above|earlier|preceding|system|initial|original|your|all)"
_EN_NOUN = r"(instructions?|prompts?|rules|directives|guidelines|guardrails)"
_PL_ADJ = (
    r"(poprzednie|wczesniejsze|powyzsze|wszystkie|dotychczasowe|systemowe|"
    r"twoje|swoje|swoich|twoich)"
)
_PL_NOUN = (
    r"(instrukcje|instrukcji|polecenia|polecen|zasady|zasad|reguly|regul|"
    r"wytyczne|wytycznych|prompty?)"
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rx))
    for name, rx in (
        (
            "ignore_instructions",
            rf"\b(ignore|disregard|forget|override|bypass)\s+((all|any|the|of|my|these)\s+)*"
            rf"{_EN_ADJ}\s+(\w+\s+)?{_EN_NOUN}\b",
        ),
        (
            "reveal_system_prompt",
            r"\b(print|reveal|show|repeat|output|display|leak|dump|give|tell)\s+(me\s+|us\s+)?"
            r"(your|the)\s+(\w+\s+)?(system\s+prompt|(initial|hidden|original|secret)\s+"
            r"(instructions|prompt))\b",
        ),
        (
            "persona_override",
            r"\b(you are now|from now on you are|pretend (to be|you are)|act as)\b.{0,40}"
            r"\b(dan|jailbroken|unrestricted|unfiltered|uncensored|without (any )?"
            r"(restrictions|filters|rules|limits))\b",
        ),
        (
            "no_restrictions",
            r"\b(pretend|imagine|act as if|assume)\b.{0,30}\b(you have|there are) no "
            r"(restrictions|rules|limits|filters|guidelines|guardrails)\b",
        ),
        (
            "forget_rules",
            r"\b(forget|ignore|disregard)\s+((all|the|your|any)\s+)+(rules|instructions|guidelines)"
            r"\s+(you (were|have been) given|above|so far)\b",
        ),
        (
            "obey_only_me",
            r"\b(obey|listen to|follow) only (me|my (instructions|orders|commands))\b",
        ),
        (
            "ignore_authority",
            r"\b(ignore|disregard|forget)\s+(what|everything|anything)\s+(the\s+)?"
            r"(developer|system|admin|operator|you (were|have been) told)",
        ),
        (
            "policy_revoked",
            r"\b(system override|(safety|security) (policy|rules|filters|guidelines) "
            r"(is|are|has been|have been) (revoked|disabled|lifted|removed))\b",
        ),
        ("do_anything_now", r"\bdo anything now\b"),
        ("mode_switch", r"\b(enable|activate|enter)\w*\s+(developer|dan|god|jailbreak)\s+mode\b"),
        (
            "fake_role_header",
            r"(^|[\n\[(])\s*(system|admin|developer)\s*(message|override|note)?\s*[\]:)]\s*"
            r"(ignore|disregard|send|forward|email|exfiltrate|reveal|upload)\b",
        ),
        (
            "pl_ignore_instructions",
            rf"\b(zignoruj|ignoruj|pomin|zapomnij|olej|nie zwazaj na)\s+(\w+\s+){{0,2}}"
            rf"{_PL_ADJ}\s+(\w+\s+)?{_PL_NOUN}\b",
        ),
        (
            "pl_reveal_system_prompt",
            r"\b(podaj|pokaz|wypisz|powtorz|ujawnij|wyswietl|zdradz)\s+(mi\s+)?(\w+\s+)?"
            r"(prompt\w*\s+systemow\w*|systemow\w*\s+prompt\w*|instrukcj\w*\s+systemow\w*|"
            r"systemow\w*\s+instrukcj\w*)",
        ),
        (
            "pl_persona_override",
            r"\b(jestes teraz|od teraz jestes|udawaj, ze jestes|udawaj ze jestes)\b.{0,40}"
            r"\b(dan|bez ograniczen|bez cenzury|bez filtrow|nieograniczon\w*)",
        ),
        (
            "pl_no_restrictions",
            r"\b(udawaj|wyobraz sobie|zaloz)\b.{0,30}\bnie (masz|obowiazuja cie|ma) (zadnych )?"
            r"(ograniczen|zasad|regul|filtrow|wytycznych)",
        ),
        (
            "pl_disobey",
            rf"\bnie (stosuj sie do|sluchaj|przestrzegaj)\s+(\w+\s+)?{_PL_NOUN}\b",
        ),
    )
)


def find_injection(
    text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...] = PATTERNS
) -> list[str]:
    """Matched pattern names, suffixed with the view they matched in ("x/base64", "x/rot13")."""
    hits: list[str] = []
    for kind, view in views(text):
        for name, pattern in patterns:
            label = name if kind == "text" else f"{name}/{kind}"
            if label not in hits and pattern.search(view):
                hits.append(label)
    return hits


TAGS = ("owasp.llm01-2025", "asi.asi01", "atlas.AML.T0051")
MIXED_SCRIPT_SCORE = 0.6
_NAMES = frozenset(name for name, _ in PATTERNS)


class InjectionParams(BaseModel):
    """`extra_patterns` run on normalized text: lowercase, no diacritics (`ł` -> `l`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    extra_patterns: tuple[str, ...] = ()
    disabled_patterns: tuple[str, ...] = ()

    @field_validator("extra_patterns")
    @classmethod
    def _compiles(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for rx in patterns:
            try:
                re.compile(rx)
            except re.error as e:
                raise ValueError(f"extra_patterns {rx!r}: {e}") from e
        return patterns

    @field_validator("disabled_patterns")
    @classmethod
    def _known(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(names) - _NAMES
        if unknown:
            raise ValueError(f"unknown patterns: {sorted(unknown)}")
        return names


def _scan(control_id: str, texts: list[tuple[str, str]], params: InjectionParams) -> list[Finding]:
    patterns = tuple(p for p in PATTERNS if p[0] not in params.disabled_patterns)
    patterns += tuple((f"extra_{i}", re.compile(rx)) for i, rx in enumerate(params.extra_patterns))
    score = 0.0
    evidence: list[str] = []
    for target, text in texts:
        labels = find_injection(text, patterns)
        if labels:
            score = 1.0
            evidence.append(f"{','.join(labels)}@{target}")
        elif mixed_script_words(text) >= 2:
            score = max(score, MIXED_SCRIPT_SCORE)
            evidence.append(f"mixed_script@{target}")
    if not evidence:
        return []
    return [
        Finding(
            control_id=control_id,
            category=Category.INJECTION,
            score=score,
            evidence="; ".join(evidence)[:EVIDENCE_MAX],
            tags=TAGS,
        )
    ]


class InjectionHeuristics:
    kind: ClassVar[str] = "injection_heuristics"
    Params: ClassVar[type[BaseModel]] = InjectionParams

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        if not isinstance(ctx.params, InjectionParams):
            raise TypeError(f"expected InjectionParams, got {type(ctx.params).__name__}")
        texts = list(iter_texts(ctx.interaction, ctx.side))
        return await anyio.to_thread.run_sync(
            _scan, ctx.control_id, texts, ctx.params, abandon_on_cancel=True
        )
