"""Terminal: differential drawing, key reading on a pseudo-terminal, state restored on exit."""

from __future__ import annotations

import io
import os
import pty
import re
import signal
import termios
import threading
from collections.abc import Iterator
from typing import TextIO

import pytest

from control_layer.egida.keys import PASTE_END, PASTE_START, Key
from control_layer.egida.term import Terminal

_ROW_UPDATE = re.compile(r"\x1b\[(\d+);1H\x1b\[2K")


def _drawer(size: tuple[int, int] = (40, 10)) -> tuple[Terminal, io.StringIO]:
    out = io.StringIO()
    term = Terminal(stdin=io.StringIO(), stdout=out)
    term.size = lambda: size  # type: ignore[method-assign]
    return term, out


def _updated_rows(text: str) -> list[int]:
    return [int(row) for row in _ROW_UPDATE.findall(text)]


def _take(out: io.StringIO) -> str:
    text = out.getvalue()
    out.seek(0)
    out.truncate()
    return text


def test_draw_same_frame_twice_writes_nothing_the_second_time() -> None:
    term, out = _drawer()
    term.draw(["a", "b", "c"])
    assert _updated_rows(_take(out)) == [1, 2, 3]
    term.draw(["a", "b", "c"])
    assert out.getvalue() == ""


def test_draw_rewrites_only_changed_rows_and_clears_unused_ones() -> None:
    term, out = _drawer()
    term.draw(["a", "b", "c", "d"])
    _take(out)
    term.draw(["a", "B"])
    text = _take(out)
    assert _updated_rows(text) == [2, 3, 4]
    assert "B" in text and "a" not in text
    assert text.startswith("\x1b[?2026h") and text.endswith("\x1b[?2026l")


def test_draw_clips_to_width_and_height() -> None:
    term, out = _drawer((5, 2))
    term.draw(["0123456789", "x", "beyond the last row"])
    text = _take(out)
    assert "01234" in text and "5" not in text
    assert "beyond" not in text


def test_draw_repaints_everything_after_a_resize() -> None:
    size = [(40, 10)]
    out = io.StringIO()
    term = Terminal(stdin=io.StringIO(), stdout=out)
    term.size = lambda: size[0]  # type: ignore[method-assign]
    term.draw(["a", "b"])
    _take(out)
    size[0] = (60, 10)
    term.draw(["a", "b"])
    text = _take(out)
    assert "\x1b[2J" in text
    assert _updated_rows(text) == [1, 2]


def test_size_falls_back_without_a_terminal() -> None:
    assert Terminal(stdin=io.StringIO(), stdout=io.StringIO()).size() == (80, 24)


@pytest.fixture
def tty_pair() -> Iterator[tuple[int, TextIO]]:
    master, slave = pty.openpty()
    stdin = os.fdopen(slave, "r")
    try:
        yield master, stdin
    finally:
        stdin.close()
        os.close(master)


def _send_later(fd: int, data: bytes, delay: float) -> threading.Timer:
    timer = threading.Timer(delay, os.write, (fd, data))
    timer.start()
    return timer


def _modes(fd: int) -> list[object]:
    """tty attributes without PENDIN, which the kernel sets by itself on mode switches."""
    attrs: list[object] = termios.tcgetattr(fd)
    lflag = attrs[3]
    assert isinstance(lflag, int)
    attrs[3] = lflag & ~getattr(termios, "PENDIN", 0)
    return attrs


def test_enter_and_exit_restore_tty_screen_and_sigterm(tty_pair: tuple[int, TextIO]) -> None:
    _, stdin = tty_pair
    before = _modes(stdin.fileno())
    handler = signal.getsignal(signal.SIGTERM)
    out = io.StringIO()
    with pytest.raises(RuntimeError), Terminal(stdin=stdin, stdout=out):
        assert _modes(stdin.fileno()) != before
        assert signal.getsignal(signal.SIGTERM) is not handler
        raise RuntimeError("body failed")
    assert _modes(stdin.fileno()) == before
    assert signal.getsignal(signal.SIGTERM) is handler
    text = out.getvalue()
    assert text.index("\x1b[?1049h") < text.index("\x1b[?1049l")
    assert "\x1b[?25h" in text and "\x1b[?2004l" in text


def test_sigterm_becomes_system_exit(tty_pair: tuple[int, TextIO]) -> None:
    _, stdin = tty_pair
    with pytest.raises(SystemExit), Terminal(stdin=stdin, stdout=io.StringIO()):
        os.kill(os.getpid(), signal.SIGTERM)
        threading.Event().wait(1.0)


def test_read_keys_times_out_with_nothing_typed(tty_pair: tuple[int, TextIO]) -> None:
    _, stdin = tty_pair
    with Terminal(stdin=stdin, stdout=io.StringIO()) as term:
        assert term.read_keys(0.01) == []


def test_read_keys_completes_split_escape_and_utf8(tty_pair: tuple[int, TextIO]) -> None:
    master, stdin = tty_pair
    with Terminal(stdin=stdin, stdout=io.StringIO()) as term:
        os.write(master, b"\x1b[")
        timer = _send_later(master, b"A", 0.01)
        assert term.read_keys(1.0) == [Key("up")]
        timer.join()
        os.write(master, "ł".encode()[:1])
        timer = _send_later(master, "ł".encode()[1:], 0.01)
        assert term.read_keys(1.0) == [Key("char", "ł")]
        timer.join()


def test_read_keys_lone_escape_is_the_escape_key(tty_pair: tuple[int, TextIO]) -> None:
    master, stdin = tty_pair
    with Terminal(stdin=stdin, stdout=io.StringIO()) as term:
        os.write(master, b"\x1b")
        assert term.read_keys(1.0) == [Key("escape")]


def test_read_keys_waits_for_the_paste_end(tty_pair: tuple[int, TextIO]) -> None:
    master, stdin = tty_pair
    with Terminal(stdin=stdin, stdout=io.StringIO()) as term:
        os.write(master, (PASTE_START + "abc").encode())
        timer = _send_later(master, ("def" + PASTE_END).encode(), 0.2)
        keys = term.read_keys(1.0)
        timer.join()
    assert keys == [Key("paste", "abcdef")]
