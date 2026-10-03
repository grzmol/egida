"""Shared text normalization for deterministic detectors (C06).

Matching runs on `views(text)`: the normalized text plus decoded variants
(base64 segments, ROT13). Views are for matching only; spans for redaction
must be computed on the original text.
"""

import base64
import binascii
import codecs
import re
import unicodedata

# ponytail: hand-picked Cyrillic/Greek look-alikes only; full UTS #39 confusables
# table if attackers start using other scripts.
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
        "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
        "һ": "h", "ӏ": "l", "ԛ": "q", "ԝ": "w", "ɡ": "g",
        "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p",
        "τ": "t", "υ": "u", "χ": "x",
        "ł": "l",
    }
)  # fmt: skip

_B64_TOKEN = re.compile(r"[A-Za-z0-9+/_-]+={0,2}")
_WORD = re.compile(r"\w+")
_WHITESPACE = re.compile(r"\s+")
_MIN_PRINTABLE = 0.9


def normalize(text: str) -> str:
    """Fold text to a canonical form for phrase matching.

    NFKC (fullwidth, ligatures), drop format characters (zero-width, bidi,
    tag characters U+E0000), casefold, map look-alike letters to Latin,
    strip diacritics (so "pomiń" matches "pomin"), collapse whitespace runs
    (a run containing a newline becomes one newline, so line starts survive).
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = text.casefold().translate(_CONFUSABLES)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return _WHITESPACE.sub(lambda m: "\n" if "\n" in m.group() else " ", text).strip()


def decoded_segments(text: str, min_len: int = 16, max_segments: int = 5) -> list[str]:
    """Printable UTF-8 strings hidden in base64/base64url tokens of `min_len`+ characters.

    Binary payloads (images, archives) fail UTF-8 or the printable ratio and are skipped.
    At most `max_segments` results, so a flood of tokens cannot multiply the scan work.
    """
    decoded: list[str] = []
    for m in _B64_TOKEN.finditer(text):
        token = m.group()
        if len(token) < min_len:
            continue
        padded = token.rstrip("=") + "=" * (-len(token.rstrip("=")) % 4)
        try:
            raw = base64.b64decode(padded.replace("-", "+").replace("_", "/"), validate=True)
            candidate = raw.decode("utf-8")
        except (binascii.Error, ValueError):
            continue
        printable = sum(c.isprintable() or c.isspace() for c in candidate)
        if candidate and printable / len(candidate) >= _MIN_PRINTABLE:
            decoded.append(candidate)
            if len(decoded) == max_segments:
                break
    return decoded


def mixed_script_words(text: str) -> int:
    """Number of words mixing Latin and Cyrillic letters (homoglyph attack signal).

    Greek is left out on purpose: "β-carotene" or "μs" are legitimate.
    """
    count = 0
    for word in _WORD.findall(text):
        latin = any("a" <= c.lower() <= "z" for c in word)
        cyrillic = any("\u0400" <= c <= "\u04ff" for c in word)
        count += latin and cyrillic
    return count


def views(text: str) -> list[str]:
    """Normalized text plus normalized decoded variants (base64 segments, ROT13)."""
    variants = [text, codecs.encode(text, "rot13"), *decoded_segments(text)]
    return [normalize(v) for v in variants]
