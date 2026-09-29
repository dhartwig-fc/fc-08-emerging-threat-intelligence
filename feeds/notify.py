"""
The one macOS notification at the end of a scheduled run (slice 2 C2, spec section 2).

The text is the report's own first two lines -- "# Friday run <id>: <STATUS>" and its one-sentence summary --
so the notification can never say more, or other, than the report. The words reach osascript as ARGUMENTS
(`on run argv`), never spliced into AppleScript source, so a title with a quote cannot become code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

OSASCRIPT = "/usr/bin/osascript"
SCRIPT = ("on run argv", "display notification (item 1 of argv) with title (item 2 of argv)", "end run")


def from_report(path: Path) -> tuple:
    lines = [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    head = lines[0].lstrip("# ") if lines else "Friday run: no report"
    status = head.rsplit(": ", 1)[-1]
    return "FC08 Friday run: %s" % status, (lines[1] if len(lines) > 1 else head)[:220]


def notify(title: str, message: str, run=subprocess.run) -> bool:
    argv = [OSASCRIPT]
    for line in SCRIPT:
        argv += ["-e", line]
    got = run(argv + [message, title], capture_output=True, text=True, timeout=30)
    return got.returncode == 0
