"""The raw terminal Egida draws on: raw mode, alternate screen, key input, differential redraw.

POSIX only (termios). Every change made on enter (tty attributes, alternate screen, hidden
cursor, bracketed paste, SIGTERM handler) is undone on exit, also when the body raised.
"""

from __future__ import annotations

import codecs
import contextlib
import os
import re
import select
import signal
import sys
import termios
import tty
from collections.abc import Sequence
from types import FrameType
from typing import Final, TextIO

from control_layer.egida.keys import PASTE_END, PASTE_START, Key, decode
from control_layer.egida.theme import clip

__all__ = ["Terminal"]

_ENTER: Final = "\x1b[?1049h\x1b[?25l\x1b[?2004h\x1b[H\x1b[2J"
_LEAVE: Final = "\x1b[?2004l\x1b[?25h\x1b[?1049l"
_SYNC_START: Final = "\x1b[?2026h"
_SYNC_END: Final = "\x1b[?2026l"
_DEFAULT_SIZE: Final = (80, 24)
_READ_CHUNK: Final = 4096
_ESCAPE_WAIT: Final = 0.03  # rest of an escape sequence split across reads
_PASTE_WAIT: Final = 1.0  # silence that ends an unterminated bracketed paste
# A chunk ending here may be the start of a longer sequence: ESC, ESC ESC, ESC O, ESC [ 1;5…
_UNFINISHED: Final = re.compile(r"\x1b(?:\x1b?\[[0-9;?]*|O|\x1b)?\Z")


def _terminate(signum: int, frame: FrameType | None) -> None:
    raise SystemExit(128 + signum)


class Terminal:
    """Context manager owning the controlling terminal while Egida runs."""

    def __init__(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        self._stdin = sys.stdin if stdin is None else stdin
        self._stdout = sys.stdout if stdout is None else stdout
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._cleanup: contextlib.ExitStack | None = None
        self._frame: list[str] = []
        self._frame_size: tuple[int, int] | None = None

    def __enter__(self) -> Terminal:
        fd = self._stdin.fileno()
        with contextlib.ExitStack() as stack:
            previous = signal.getsignal(signal.SIGTERM)
            stack.callback(
                signal.signal, signal.SIGTERM, signal.SIG_DFL if previous is None else previous
            )
            signal.signal(signal.SIGTERM, _terminate)
            stack.callback(termios.tcsetattr, fd, termios.TCSADRAIN, termios.tcgetattr(fd))
            tty.setraw(fd)
            stack.callback(self._write, _LEAVE)
            self._write(_ENTER)
            self._frame, self._frame_size = [], None
            self._decoder.reset()
            self._cleanup = stack.pop_all()
        return self

    def __exit__(self, *exc: object) -> None:
        cleanup, self._cleanup = self._cleanup, None
        if cleanup is not None:
            cleanup.close()

    def size(self) -> tuple[int, int]:
        """(columns, rows) of the terminal; (80, 24) when it can't be asked."""
        try:
            columns, rows = os.get_terminal_size(self._stdout.fileno())
        except (OSError, ValueError):  # io.UnsupportedOperation is both
            return _DEFAULT_SIZE
        return (columns, rows) if columns > 0 and rows > 0 else _DEFAULT_SIZE

    def read_keys(self, timeout: float) -> list[Key]:
        """Keys typed within `timeout` seconds ([] if none). A chunk that stops inside an escape
        sequence, a UTF-8 character or a bracketed paste waits briefly for the rest.
        EOFError when stdin is closed."""
        fd = self._stdin.fileno()
        if not _readable(fd, timeout):
            return []
        data = self._read(fd)
        while True:
            if data.rfind(PASTE_START) > data.rfind(PASTE_END):
                wait = _PASTE_WAIT
            elif _UNFINISHED.search(data) or self._decoder.getstate()[0]:
                wait = _ESCAPE_WAIT
            else:
                break
            if not _readable(fd, wait):
                break
            data += self._read(fd)
        return decode(data)

    def draw(self, lines: Sequence[str]) -> None:
        """Show `lines` from the top row: only rows that changed since the last frame are
        rewritten, rows no longer used are cleared, a size change repaints everything."""
        size = self.size()
        width, height = size
        out: list[str] = []
        if size != self._frame_size:
            out.append("\x1b[H\x1b[2J")
            self._frame, self._frame_size = [], size
        frame = list(lines[:height])
        previous = self._frame
        for row, line in enumerate(frame):
            if row < len(previous) and previous[row] == line:
                continue
            out.append(f"\x1b[{row + 1};1H\x1b[2K{clip(line, width)}\x1b[0m")
        out.extend(f"\x1b[{row + 1};1H\x1b[2K" for row in range(len(frame), len(previous)))
        self._frame = frame
        if out:
            self._write(_SYNC_START + "".join(out) + _SYNC_END)

    def _read(self, fd: int) -> str:
        chunk = os.read(fd, _READ_CHUNK)
        if not chunk:
            raise EOFError("Terminal input closed")
        return self._decoder.decode(chunk)

    def _write(self, text: str) -> None:
        self._stdout.write(text)
        self._stdout.flush()


def _readable(fd: int, timeout: float) -> bool:
    ready, _, _ = select.select([fd], [], [], max(timeout, 0.0))
    return bool(ready)
