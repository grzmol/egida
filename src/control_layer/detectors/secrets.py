"""C05: credential finder. Patterns follow gitleaks rules (MIT, config/gitleaks.toml).

Returns spans on the original text.
"""

import re

# ponytail: no entropy rule — it flags commit SHAs and UUIDs; add as a separate
# redact-only control if needed (docs/research/02-detektory-i-modele.md §5).
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(rx))
    for label, rx in (
        ("aws_access_key", r"\b(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16}\b"),
        ("github_token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{82})\b"),
        (
            "private_key",
            r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\s\S]*?"
            r"(?:-----END[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----|\Z)",
        ),
        ("jwt", r"\bey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        ("connection_string", r"\b[a-z][a-z0-9+.-]{1,20}://[^\s:/@]+:[^\s/@]+@\S+"),
        ("slack_token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
        ("openai_key", r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"),
        ("stripe_key", r"\b[rs]k_live_[A-Za-z0-9]{20,}"),
        ("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    )
)


def find_secrets(text: str) -> list[tuple[str, int, int]]:
    """(label, start, end) for each credential in `text`, sorted by position."""
    hits = [(label, m.start(), m.end()) for label, p in _PATTERNS for m in p.finditer(text)]
    return sorted(hits, key=lambda h: h[1])
