"""Task progress per person, from the status column of docs/tasks/<person>/README.md.

A task is a table row whose first cell links to its spec (`| [A5](A5-…md) | … | ☑ … |`); its
status is the first mark in the last cell: ☑ done, ◐ half done, ☐ not started (also the default
for a row without a mark). Prints Discord markdown for the push notification.

Run: python3 scripts/task_progress.py [repo root]
"""

from __future__ import annotations

import sys
from pathlib import Path

WEIGHT = {"☑": 1.0, "◐": 0.5, "☐": 0.0}
BAR = 10


def person_progress(readme: Path) -> tuple[float, int]:
    """(done, total) for one person; done counts ◐ as half."""
    done, total = 0.0, 0
    for line in readme.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].startswith("[") or "](" not in cells[0]:
            continue
        total += 1
        status = cells[-1]
        done += next((WEIGHT[ch] for ch in status if ch in WEIGHT), 0.0)
    return done, total


def report(root: Path) -> str:
    lines: list[str] = []
    all_done, all_total = 0.0, 0
    for readme in sorted((root / "docs" / "tasks").glob("*/README.md")):
        done, total = person_progress(readme)
        if total == 0:
            continue
        all_done += done
        all_total += total
        lines.append(f"**{readme.parent.name.capitalize()}** {_line(done, total)}")
    lines.append(f"**Ogółem** {_line(all_done, all_total)}")
    return "\n".join(lines)


def _line(done: float, total: int) -> str:
    share = done / total if total else 0.0
    filled = round(share * BAR)
    return f"`{'█' * filled}{'░' * (BAR - filled)}` {done:g}/{total} · {share:.0%}"


if __name__ == "__main__":
    print(report(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()))
