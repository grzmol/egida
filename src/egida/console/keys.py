"""Key events decoded from raw terminal input (xterm sequences, bracketed paste).

Names: up down left right home end pageup pagedown insert delete enter escape tab shift+tab
backspace, modified arrows/keys as `shift+up`, `alt+down`, `ctrl+left` (xterm modifier parameter
or an ESC prefix for alt), control characters as `ctrl+a`…`ctrl+z`, `alt+<char>`, one printable
character as `char` (space included) and a bracketed paste as `paste` with line breaks removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = ["PASTE_END", "PASTE_START", "Key", "decode"]

PASTE_START: Final = "\x1b[200~"
PASTE_END: Final = "\x1b[201~"

_CSI: Final = re.compile(r"\x1b\[([0-9;]*)([~A-Za-z])")
_LETTER_KEYS: Final = {
    "A": "up",
    "B": "down",
    "C": "right",
    "D": "left",
    "H": "home",
    "F": "end",
    "Z": "shift+tab",
}
_TILDE_KEYS: Final = {
    "1": "home",
    "2": "insert",
    "3": "delete",
    "4": "end",
    "5": "pageup",
    "6": "pagedown",
    "7": "home",
    "8": "end",
}
# xterm modifier parameter: 1 + (shift 1, alt 2, ctrl 4, meta 8)
_MODIFIERS: Final = {"2": "shift+", "3": "alt+", "5": "ctrl+", "9": "alt+"}
_SS3_KEYS: Final = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}


@dataclass(frozen=True, slots=True)
class Key:
    name: str
    text: str = ""  # the character for `char`, the pasted text for `paste`


def decode(data: str) -> list[Key]:
    """Split a complete chunk of terminal input into keys. A trailing lone ESC is the Escape key;
    unknown or truncated escape sequences are dropped."""
    keys: list[Key] = []
    i = 0
    while i < len(data):
        if data.startswith(PASTE_START, i):
            end = data.find(PASTE_END, i + len(PASTE_START))
            stop = len(data) if end < 0 else end
            body = data[i + len(PASTE_START) : stop]
            keys.append(Key("paste", "".join(body.splitlines())))
            i = stop + len(PASTE_END) if end >= 0 else stop
            continue
        ch = data[i]
        if ch == "\x1b":
            key, i = _escape(data, i)
            if key is not None:
                keys.append(key)
            continue
        keys.append(_plain(ch))
        i += 1
    return keys


def _escape(data: str, i: int) -> tuple[Key | None, int]:
    """Decode the escape sequence at data[i] == ESC; returns the key (None if unknown) and the
    index after the sequence."""
    rest = data[i + 1 : i + 2]
    if not rest:
        return Key("escape"), i + 1
    if rest == "[":
        return _csi(data, i, alt=False)
    if rest == "O" and i + 2 < len(data):
        name = _SS3_KEYS.get(data[i + 2])
        return (Key(name) if name else None), i + 3
    if rest == "\x1b" and data.startswith("[", i + 2):  # ESC ESC [ A: option+arrow as meta
        return _csi(data, i + 1, alt=True)
    if rest.isprintable():
        return Key(f"alt+{rest}"), i + 2
    return Key("escape"), i + 1


def _csi(data: str, i: int, *, alt: bool) -> tuple[Key | None, int]:
    match = _CSI.match(data, i)
    if match is None:  # truncated sequence: drop what is left of it
        return None, len(data)
    params, final = match.groups()
    parts = params.split(";")
    base = _TILDE_KEYS.get(parts[0]) if final == "~" else _LETTER_KEYS.get(final)
    if base is None:
        return None, match.end()
    modifier = _MODIFIERS.get(parts[1], "") if len(parts) > 1 else ""
    if alt and not modifier:
        modifier = "alt+"
    if base == "shift+tab":
        modifier = ""
    return Key(modifier + base), match.end()


def _plain(ch: str) -> Key:
    if ch in "\r\n":
        return Key("enter")
    if ch == "\t":
        return Key("tab")
    if ch in "\x7f\x08":
        return Key("backspace")
    code = ord(ch)
    if code < 32:
        return Key(f"ctrl+{chr(code + 96)}")
    return Key("char", ch)
