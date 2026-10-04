"""pi's look for Egida: palette, colour modes, text width helpers and the shield logo.

The palette is pi's `dark` theme (okhsl values in pi's `dark.json`) converted to sRGB and to
xterm-256 indices with pi's own colour code (pi-tui `colors.ts`), so Egida paints what pi paints.
Styles close their own layer (fg 39, bg 49, bold 22, inverse 27): compose styled segments side by
side and never nest one `fg` inside another, or the outer colour ends early.
"""

from __future__ import annotations

import os
import re
import textwrap
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

__all__ = [
    "LOGO_COLORS",
    "PALETTE",
    "ColorMode",
    "Style",
    "Token",
    "char_width",
    "clip",
    "detect_color_mode",
    "logo_lines",
    "pad",
    "supports_logo",
    "truncate",
    "visible_width",
    "wrap",
]

Token = Literal[
    "accent",
    "border",
    "border_muted",
    "success",
    "error",
    "warning",
    "muted",
    "dim",
    "text",
    "selected_bg",
    "pending_bg",
    "success_bg",
    "error_bg",
]

# (sRGB hex, xterm-256 index); pi theme token in the comment where the name differs.
PALETTE: Final[Mapping[Token, tuple[str, int]]] = {
    "accent": ("#a798d7", 140),
    "border": ("#5fa8cc", 74),
    "border_muted": ("#768186", 102),  # borderMuted
    "success": ("#68b78d", 72),
    "error": ("#ea7f81", 174),
    "warning": ("#cd9a22", 172),
    "muted": ("#9da5a9", 145),
    "dim": ("#7e888e", 102),
    "text": ("#dee0e1", 254),
    "selected_bg": ("#213b49", 23),  # selectedBg
    "pending_bg": ("#34383a", 237),  # toolPendingBg
    "success_bg": ("#254131", 23),  # toolSuccessBg
    "error_bg": ("#5b282a", 52),  # toolErrorBg
}

# The shield: pi's logo blue (lit left half, plain right half) and pi's logo yellow for the band,
# which stands for the proxy between agents and models.
LOGO_COLORS: Final[Mapping[str, tuple[str, int]]] = {
    "L": ("#7caac6", 110),
    "B": ("#4f8eb3", 67),
    "Y": ("#eab65d", 179),
}
_SHIELD: Final = (  # 6×6 pixels, two pixel rows per text row (half blocks); "." is empty
    "LLLBBB",
    "LLLBBB",
    "YYYYYY",
    "LLLBBB",
    ".LLBB.",
    "..LB..",
)


class ColorMode(Enum):
    TRUECOLOR = "truecolor"
    PALETTE256 = "256"
    NONE = "none"


def detect_color_mode(env: Mapping[str, str] | None = None) -> ColorMode:
    """NO_COLOR (set, non-empty) wins; COLORTERM=truecolor|24bit means 24-bit; else xterm-256."""
    env = os.environ if env is None else env
    if env.get("NO_COLOR"):
        return ColorMode.NONE
    if env.get("COLORTERM", "").lower() in {"truecolor", "24bit"}:
        return ColorMode.TRUECOLOR
    return ColorMode.PALETTE256


@dataclass(frozen=True, slots=True)
class Style:
    mode: ColorMode

    def fg(self, token: Token, text: str) -> str:
        return self.paint(PALETTE[token], text)

    def bg(self, token: Token, text: str) -> str:
        return self.paint(PALETTE[token], text, background=True)

    def paint(self, color: tuple[str, int], text: str, *, background: bool = False) -> str:
        if self.mode is ColorMode.NONE or not text:
            return text
        layer = 48 if background else 38
        hex_, index = color
        if self.mode is ColorMode.TRUECOLOR:
            r, g, b = (int(hex_[i : i + 2], 16) for i in (1, 3, 5))
            start = f"\x1b[{layer};2;{r};{g};{b}m"
        else:
            start = f"\x1b[{layer};5;{index}m"
        return f"{start}{text}\x1b[{49 if background else 39}m"

    def bold(self, text: str) -> str:
        return f"\x1b[1m{text}\x1b[22m" if text else text

    def inverse(self, text: str) -> str:
        return f"\x1b[7m{text}\x1b[27m" if text else text


_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\ufe0e\ufe0f")


def char_width(ch: str) -> int:
    """Terminal columns of one character: 0 for combining marks, 2 for wide East Asian forms."""
    if ch in _ZERO_WIDTH or unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def visible_width(text: str) -> int:
    """Columns `text` occupies; SGR escape sequences take none."""
    return sum(char_width(ch) for ch in _ESCAPE.sub("", text))


def clip(text: str, width: int) -> str:
    """Cut `text` to `width` columns. Escape sequences are kept, also after the cut, so styles
    opened before the cut are still closed."""
    out: list[str] = []
    used = 0
    full = False
    i = 0
    while i < len(text):
        match = _ESCAPE.match(text, i)
        if match:
            out.append(match.group())
            i = match.end()
            continue
        ch = text[i]
        i += 1
        if full:
            continue
        w = char_width(ch)
        if used + w > width:
            full = True
            continue
        out.append(ch)
        used += w
    return "".join(out)


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Plain text shortened to at most `width` columns, ending with `ellipsis` when cut."""
    if visible_width(text) <= width:
        return text
    room = width - visible_width(ellipsis)
    if room <= 0:
        return clip(ellipsis, max(width, 0))
    return clip(text, room) + ellipsis


def pad(text: str, width: int) -> str:
    """`text` (escapes allowed) clipped and right-padded with spaces to exactly `width` columns."""
    clipped = clip(text, width)
    return clipped + " " * max(0, width - visible_width(clipped))


def wrap(text: str, width: int) -> list[str]:
    """Plain text wrapped at word boundaries; long words are split. Empty text gives []."""
    lines: list[str] = []
    for paragraph in text.splitlines():
        lines += textwrap.wrap(paragraph, max(width, 1), break_on_hyphens=False) or [""]
    return lines if text.strip() else []


def logo_lines(style: Style) -> list[str]:
    """The shield as three text rows of six columns (upper/lower half blocks)."""
    rows: list[str] = []
    for top, bottom in zip(_SHIELD[0::2], _SHIELD[1::2], strict=True):
        cells: list[str] = []
        for upper, lower in zip(top, bottom, strict=True):
            if upper == "." and lower == ".":
                cells.append(" ")
            elif upper == lower:
                cells.append(style.paint(LOGO_COLORS[upper], "█"))
            elif lower == ".":
                cells.append(style.paint(LOGO_COLORS[upper], "▀"))
            elif upper == ".":
                cells.append(style.paint(LOGO_COLORS[lower], "▄"))
            else:
                half = style.paint(LOGO_COLORS[upper], "▀")
                cells.append(style.paint(LOGO_COLORS[lower], half, background=True))
        rows.append("".join(cells))
    return rows


def supports_logo(env: Mapping[str, str] | None = None) -> bool:
    """Apple Terminal draws gaps between rows of half blocks (pi shows a wordmark there too)."""
    env = os.environ if env is None else env
    return env.get("TERM_PROGRAM") != "Apple_Terminal"
