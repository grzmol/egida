"""Helpers shared by span-based detectors (PII, secrets)."""

from egida.core.models import Category, Finding, Span

Hit = tuple[str, str, float, int, int]  # target, label, score, start, end
EVIDENCE_MAX = 200


def mask(value: str) -> str:
    """Keep two characters at each end, so evidence never carries the raw value."""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def span_finding(
    control_id: str,
    category: Category,
    hits: list[Hit],
    tags: tuple[str, ...],
    evidence: list[str],
) -> list[Finding]:
    """One finding per control: all spans, score = strongest hit."""
    if not hits:
        return []
    return [
        Finding(
            control_id=control_id,
            category=category,
            score=max(score for _, _, score, _, _ in hits),
            spans=tuple(Span(target, start, end, label) for target, label, _, start, end in hits),
            evidence="; ".join(evidence)[:EVIDENCE_MAX],
            tags=tags,
        )
    ]
