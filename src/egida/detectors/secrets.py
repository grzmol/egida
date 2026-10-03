"""C05: credentials in text. Rules follow gitleaks (MIT, config/gitleaks.toml), rewritten by hand.

Spans are on the original text. Entropy hits score below the default threshold, so they
show up in the audit without blocking, unless the policy lowers the threshold.
"""

import math
import re
from collections import Counter
from typing import ClassVar

import anyio
from pydantic import BaseModel, ConfigDict, Field, field_validator

from egida.core.models import Category, Finding
from egida.core.ports import ScanContext
from egida.core.texts import iter_texts
from egida.detectors.common import Hit, span_finding

RULES: tuple[tuple[str, float, re.Pattern[str]], ...] = tuple(
    (label, score, re.compile(rx))
    for label, score, rx in (
        ("aws_access_key", 1.0, r"\b(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16}\b"),
        ("github_token", 1.0, r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{82})\b"),
        (
            "private_key",
            1.0,
            r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\s\S]*?"
            r"(?:-----END[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----|\Z)",
        ),
        (
            "jwt",
            0.9,
            r"(?<![A-Za-z0-9_-])ey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        ),
        ("slack_token", 1.0, r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
        ("conn_string", 0.9, r"\b[a-z][a-z0-9+.-]{1,20}://[^\s:/@]+:[^\s/@]+@\S+"),
        ("openai_key", 1.0, r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"),
        ("stripe_key", 1.0, r"\b[rs]k_live_[A-Za-z0-9]{20,}"),
        ("google_api_key", 1.0, r"\bAIza[0-9A-Za-z_-]{35}\b"),
        ("gitlab_token", 1.0, r"\bglpat-[A-Za-z0-9_-]{20}\b"),
        ("npm_token", 1.0, r"\bnpm_[A-Za-z0-9]{36}\b"),
        ("sendgrid_key", 1.0, r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b"),
        (
            "aws_secret_key",
            1.0,
            r"(?i)(?<![a-z0-9])aws_?secret(_access)?_?key\b\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}",
        ),
        ("bearer_token", 0.9, r"(?i)\bauthorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
        (
            "keyed_secret",
            0.8,
            r"(?i)(?<![a-z0-9])(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"
            r"\b\s*[:=]\s*['\"]?[^\s'\"]{8,}",
        ),
    )
)
ENTROPY_SCORE = 0.6
LABELS = tuple(label for label, _, _ in RULES) + ("high_entropy",)
TAGS = ("owasp.llm02-2025", "asi.asi03", "atlas.AML.T0055")
_TOKEN = re.compile(r"[A-Za-z0-9+/=_-]+")


def shannon_entropy(value: str) -> float:
    n = len(value)
    return -sum(c / n * math.log2(c / n) for c in Counter(value).values()) if n else 0.0


def find_secrets(
    text: str,
    rules: tuple[str, ...] = LABELS,
    entropy_threshold: float = 4.5,
    entropy_min_len: int = 32,
) -> list[tuple[str, float, int, int]]:
    """(label, score, start, end) for each credential in `text`, sorted by position."""
    hits = [
        (label, score, m.start(), m.end())
        for label, score, pattern in RULES
        if label in rules
        for m in pattern.finditer(text)
    ]
    if "high_entropy" in rules:
        taken = bytearray(len(text))
        for _, _, start, end in hits:
            taken[start:end] = b"\x01" * (end - start)
        for m in _TOKEN.finditer(text):
            start, end = m.span()
            if (
                end - start >= entropy_min_len
                and not any(taken[start:end])
                and shannon_entropy(m.group()) > entropy_threshold
            ):
                hits.append(("high_entropy", ENTROPY_SCORE, start, end))
    return sorted(hits, key=lambda h: h[2])


class SecretsParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rules: tuple[str, ...] = LABELS
    entropy_threshold: float = Field(default=4.5, gt=0)
    entropy_min_len: int = Field(default=32, ge=8)

    @field_validator("rules")
    @classmethod
    def _known_rules(cls, rules: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(rules) - set(LABELS)
        if unknown:
            raise ValueError(f"unknown secret rules: {sorted(unknown)}")
        return rules


def _scan(control_id: str, texts: list[tuple[str, str]], params: SecretsParams) -> list[Finding]:
    hits: list[Hit] = []
    for target, text in texts:
        found = find_secrets(text, params.rules, params.entropy_threshold, params.entropy_min_len)
        hits += [(target, label, score, start, end) for label, score, start, end in found]
    # Entropy-only hits are a separate, weaker finding: the policy threshold decides them on
    # their own, so a real key in the same message does not drag them into redaction.
    findings: list[Finding] = []
    for group in (
        [h for h in hits if h[1] != "high_entropy"],
        [h for h in hits if h[1] == "high_entropy"],
    ):
        evidence = [f"{label}@{target}" for target, label, *_ in group]
        findings += span_finding(control_id, Category.SECRET, group, TAGS, evidence)
    return findings


class SecretsDetector:
    kind: ClassVar[str] = "secrets"
    Params: ClassVar[type[BaseModel]] = SecretsParams

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        if not isinstance(ctx.params, SecretsParams):
            raise TypeError(f"expected SecretsParams, got {type(ctx.params).__name__}")
        texts = list(iter_texts(ctx.interaction, ctx.side))
        return await anyio.to_thread.run_sync(
            _scan, ctx.control_id, texts, ctx.params, abandon_on_cancel=True
        )
