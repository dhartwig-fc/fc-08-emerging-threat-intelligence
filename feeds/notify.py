"""
The one macOS end-of-run notice for a scheduled Friday run (slice 2 C2, spec section 2).

MEASURED ON THE OWNER'S MAC: `osascript -e 'display notification ...'` is accepted (exit 0) and never shown --
there is no "Script Editor" entry in System Settings -> Notifications to grant, even after running it from
Script Editor directly, so there is nothing to permission. The owner's chosen replacement, `display alert ...
giving up after <seconds>`, was measured working: a detached call of exactly that shape put a real window on
screen. This module now posts an ALERT, not a notification, and nothing here falls back to `display
notification`.

The text is the report's own first two lines -- "# Friday run <id>: <STATUS>" and its one-sentence summary --
so the alert can never say more, or other, than the report. The words reach osascript as ARGUMENTS (`on run
argv`), never spliced into AppleScript source, so a title with a quote cannot become code. They are also
passed after a `--`, so a message that itself starts with `-` (e.g. "-e") is never read as an osascript
option (fix round 1, M-1 -- the same rule, now applied to `display alert`'s two argv slots instead of
`display notification`'s). Item 1 of argv is the alert's own heading (the run's status line, `title` below);
item 2 is its explanatory "message" text (the report's one-sentence summary, `message` below) -- the mapping
`display alert <heading> message <body>` expects, and the reverse of `display notification`'s
message-then-title order this module used before.

`display alert ... giving up after 86400` (24h) BLOCKS osascript itself until the owner clicks OK or the
timeout elapses, so it must never run in the foreground of a scheduled run: `notify()` starts osascript
DETACHED (`start_new_session=True`, all three standard streams to DEVNULL) and returns as soon as the process
has STARTED, never waiting on it. **What "posted" now means: osascript was launched without error.** That is
all this function can know -- it cannot see the window appear, cannot see it get clicked, and cannot see the
24-hour timeout expire unclicked. The `run=` injection seam is kept, renamed in spirit to a Popen-style
starter rather than a blocking `subprocess.run`-style caller (it is called with `start_new_session=True` and
no `capture_output`/`timeout`, since nothing here waits for output or exit status), so a guard can stub it
without ever spawning -- or blocking on -- a real alert.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

OSASCRIPT = "/usr/bin/osascript"
GIVE_UP_SECONDS = 86400  # 24h: the alert stays on screen until the owner clicks OK, or this elapses
SCRIPT = ("on run argv",
          "display alert (item 1 of argv) message (item 2 of argv) giving up after %d" % GIVE_UP_SECONDS,
          "end run")


def from_report(path: Path) -> tuple:
    lines = [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    head = lines[0].lstrip("# ") if lines else "Friday run: no report"
    status = head.rsplit(": ", 1)[-1]
    return "FC08 Friday run: %s" % status, (lines[1] if len(lines) > 1 else head)[:220]


def notify(title: str, message: str, run=subprocess.Popen) -> bool:
    """Start the alert window and return as soon as osascript has STARTED -- never waits for it to be seen,
    clicked or timed out. `run` is a Popen-style starter (default `subprocess.Popen`): called once, given the
    argv, and expected to return (or raise) immediately rather than block. Returns True iff starting it did
    not raise; False on any OSError (e.g. the osascript binary is missing), which is the only failure this
    function can observe."""
    argv = [OSASCRIPT]
    for line in SCRIPT:
        argv += ["-e", line]
    try:
        run(argv + ["--", title, message], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True
