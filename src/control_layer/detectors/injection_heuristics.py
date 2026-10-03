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
_EN_NOUN = r"(instructions?|prompts?|rules|directives|directions|guidelines|guardrails)"
# Polish: stems cover every case ending ("poprzednich instrukcjach", "wytycznych").
_PL_ADJ = (
    r"(poprzedni\w*|wczesniejsz\w*|powyzsz\w*|wszystki\w*|dotychczasow\w*|systemow\w*|"
    r"twoj\w*|twoi\w*|swoj\w*|swoi\w*)"
)
_PL_NOUN = (
    r"(instrukcj\w*|polecen\w*|zasad\w*|regul\w*|wytyczn\w*|prompt\w*|ograniczen\w*|"
    r"filtr\w*|zabezpieczen\w*)"
)
_PL_REVEAL = r"(podaj\w*|pokaz\w*|wypisz\w*|powtorz\w*|ujawni\w*|wyswietl\w*|zdradz\w*)"
_PL_HIDDEN = r"(tajn\w*|ukryt\w*|sekretn\w*|systemow\w*|bazow\w*|poczatkow\w*)"
_PL_IGNORE = r"(zignoruj|ignoruj|pomin|zapomnij( o)?|olej|nie zwazaj na|nie zwracaj uwagi na)"
_BENIGN_OBJECT = r"(message|messages|typos?|email|e-mail|question|answer|reply|post|comment)"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rx))
    for name, rx in (
        (
            "ignore_instructions",
            rf"\b(ignore|disregard|forget|bypass)\s+((all|any|the|of|my|these)\s+)*"
            rf"{_EN_ADJ}\s+(\w+\s+)?{_EN_NOUN}\b",
        ),
        (
            "ignore_everything_before",
            rf"\b(ignore|disregard|forget)\s+(all\s+|everything\s+|anything\s+)?"
            rf"(previous|prior|above|earlier|preceding)\b(?!\s+(\w+\s+)?{_BENIGN_OBJECT})",
        ),
        (
            "reveal_system_prompt",
            r"\b(print|reveal|show|repeat|output|display|leak|dump|give|tell)\s+(me\s+|us\s+)?"
            r"((your|the)\s+(\w+\s+)?system\s+prompt|your\s+(\w+\s+)?"
            r"(initial|hidden|original|secret|system)\s+(instructions|prompt))\b",
        ),
        (
            "ask_system_prompt",
            r"\bwhat (is|are|were) your (\w+\s+)?(system prompt|(initial|original|hidden|secret|"
            r"system) instructions)\b",
        ),
        ("repeat_above", r"\brepeat (the |all )?(words|text|everything|lines) above\b"),
        (
            "persona_override",
            r"\b(you are now|from now on you are|pretend (to be|you are)|act as)\b.{0,40}"
            r"\b(jailbroken|unrestricted|unfiltered|uncensored|without (any )?"
            r"(restrictions|filters|rules|limits))\b",
        ),
        ("you_are_dan", r"\byou are (now )?dan\b"),
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
        (
            "mode_switch",
            r"\b((you are|you're) (now )?in|switch (yourself )?(in)?to|enable your)\s+"
            r"(developer|dan|god|jailbreak|unrestricted)\s+mode\b|\b(dan|jailbreak) mode\b",
        ),
        (
            "fake_role_header",
            r"(^|[\n\[(])\s*system\s*(message|override|note)?\s*[\]:)]\s*"
            r"(ignore|disregard|send|forward|exfiltrate|reveal)\b",
        ),
        (
            "pl_ignore_instructions",
            rf"\b{_PL_IGNORE}\s+(\w+\s+){{0,2}}{_PL_ADJ}\s+(\w+\s+)?{_PL_NOUN}",
        ),
        (
            "pl_ignore_instructions_after",
            rf"\b{_PL_IGNORE}\s+(wszystki\w*\s+)?{_PL_NOUN}\s+(powyzej|wyzej|wczesniej|systemow\w*)",
        ),
        (
            "pl_reveal_system_prompt",
            rf"\b{_PL_REVEAL}\s+(mi\s+)?(\w+\s+)?"
            r"(prompt\w*\s+systemow\w*|systemow\w*\s+prompt\w*|instrukcj\w*\s+systemow\w*|"
            r"systemow\w*\s+instrukcj\w*)",
        ),
        (
            "pl_reveal_own_instructions",
            r"\b(podaj|pokaz|wypisz|powtorz|ujawnij|wyswietl|zdradz)\s+(mi\s+)?(swoj\w*|twoj\w*)\s+"
            r"(instrukcj\w*|polecen\w*|wytyczn\w*|prompt\w*)",
        ),
        (
            "pl_persona_override",
            r"\b(jestes teraz|od teraz jestes|udawaj, ze jestes|udawaj ze jestes)\b.{0,40}"
            r"\b(bez ograniczen|bez cenzury|bez filtrow|nieograniczon\w*)",
        ),
        (
            "pl_no_restrictions",
            r"\b(udawaj|wyobraz sobie|zaloz)\b.{0,100}\bnie (masz|obowiazuja cie|ma) (zadnych )?"
            r"(ograniczen|zasad|regul|filtrow|wytycznych)",
        ),
        (
            "pl_reveal_hidden",
            rf"\b{_PL_REVEAL}\s+(\w+\s+){{0,2}}({_PL_HIDDEN}\s+"
            rf"(instrukcj\w*|prompt\w*|klucz\w*|hasl\w*|token\w*)|(instrukcj\w*|prompt\w*)\s+{_PL_HIDDEN})",
        ),
        (
            "pl_ignore_object",  # only the unambiguous verbs: "pomin zasady formatowania" is benign
            r"\b(zignoruj|ignoruj|olej)\s+(\w+\s+){0,2}(instrukcj\w*|polecen\w*|wytyczn\w*|"
            r"prompt\w*|ograniczen\w*|zabezpieczen\w*)",
        ),
        (
            "pl_bypass_safety",
            r"\b(pomin\w*|zignor\w*|ignor\w*|wylacz\w*|obejs\w*|obejdz\w*)\s+(\w+\s+)?"
            r"(regul\w*|zasad\w*|filtr\w*|zabezpieczen\w*|ograniczen\w*)\s+bezpieczenstw\w*",
        ),
        (
            "pl_mode_switch",
            r"\btryb\w*\s+(\w+\s+)?bez\s+(zadnych\s+)?(filtrow|ograniczen|cenzury|zasad|"
            r"zabezpieczen)",
        ),
        (
            "grandma_exploit",
            r"\b(babci\w*|babcia|dziadek|dziadk\w*|grandma|grandmother|grandpa)\b.{0,100}"
            r"\b(prompt\w* systemow\w*|system prompt|instrukcj\w* systemow\w*|klucz\w* api|"
            r"api keys?|hasl\w*|password)",
        ),
        (
            "role_reset",
            r"(#{2,}|={3,}|-{3,})\s*(koniec|end of)\s+(kontekstu|context|instrukcji|instructions|"
            r"user input)|\b(nowa rola|new role)\s*:",
        ),
        (
            "decode_and_execute",
            r"\b(zdekoduj|odkoduj|odwroc|decode|reverse)\b.{0,40}\b(wykonaj|wykonac|execute|"
            r"follow|obey|zastosuj)\b",
        ),
        (
            "pl_disobey",
            rf"\bnie (stosuj sie do|sluchaj|przestrzegaj)\s+(\w+\s+)?{_PL_NOUN}",
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
