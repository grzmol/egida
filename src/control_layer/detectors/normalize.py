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

# Unicode category Cf (format: zero-width, bidi, tag characters); test pins it to unicodedata.
_FORMAT_CHARS = re.compile(
    "[\u00ad\u0600-\u0605\u061c\u06dd\u070f\u0890\u0891\u08e2\u180e\u200b-\u200f"
    "\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb\U000110bd\U000110cd"
    "\U00013430-\U0001343f\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0001"
    "\U000e0020-\U000e007f\u180b-\u180d\ufe00-\ufe0f\u3164\u115f\u1160\uffa0\u2800\U000e0100-\U000e01ef]"
)
_COMBINING = re.compile("[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]")
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
    text = _FORMAT_CHARS.sub("", text).casefold().translate(_CONFUSABLES)
    text = _COMBINING.sub("", unicodedata.normalize("NFKD", text))
    return _WHITESPACE.sub(lambda m: "\n" if "\n" in m.group() else " ", text).strip()


def decoded_segments(text: str, min_len: int = 16, max_segments: int = 50) -> list[str]:
    """Printable UTF-8 strings hidden in base64/base64url tokens of `min_len`+ characters.

    Binary payloads (images, archives) fail UTF-8 or the printable ratio and are skipped.
    At most `max_segments` candidate tokens are examined, so a flood of tokens cannot
    multiply the scan work; padding with benign tokens cannot push an attack out of the cap.
    """
    decoded: list[str] = []
    examined = 0
    for m in _B64_TOKEN.finditer(text):
        token = m.group()
        if len(token) < min_len:
            continue
        examined += 1
        if examined > max_segments:
            break
        padded = token.rstrip("=") + "=" * (-len(token.rstrip("=")) % 4)
        try:
            raw = base64.b64decode(padded.replace("-", "+").replace("_", "/"), validate=True)
            candidate = raw.decode("utf-8")
        except (binascii.Error, ValueError):
            continue
        printable = sum(c.isprintable() or c.isspace() for c in candidate)
        if candidate and printable / len(candidate) >= _MIN_PRINTABLE:
            decoded.append(candidate)
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


def views(text: str) -> list[tuple[str, str]]:
    """(kind, normalized text) for the text itself, its ROT13 and each decoded base64 segment."""
    variants = [("text", text), ("rot13", codecs.encode(text, "rot13"))]
    variants += [("base64", segment) for segment in decoded_segments(text)]
    return [(kind, normalize(v)) for kind, v in variants]
