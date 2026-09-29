"""
Install, remove or inspect the Friday schedule (slice 2 C2, spec section 5). NOTHING INSTALLS ITSELF.

Usage:
    python tools/schedule.py status               # read-only: installed? loaded? matches the template?
    python tools/schedule.py install [--dry-run]  # OWNER ONLY: render the plist into ~/Library/LaunchAgents, bootstrap
    python tools/schedule.py uninstall [--dry-run]  # OWNER ONLY: bootout, and remove the rendered plist

install and uninstall change persistent user configuration (launchd), so they are run by the owner by hand;
an agent runs `status` at most. The template is scripts/schedule/uk.fc08.friday-run.plist: __REPO__ becomes this
checkout, __HOME__ the home folder. launchctl is `bootstrap gui/<uid> <plist>` and `bootout gui/<uid>/<label>`.
install refuses when a plist is already installed (uninstall first), so a schedule is never silently replaced.
uninstall reports a failed bootout rather than ignoring it: the plist is left in place so a later `status`
still shows it installed, instead of falsely reading "not installed" while the job is still loaded (fix
round 1, M-5).
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "uk.fc08.friday-run"
TEMPLATE = ROOT / "scripts" / "schedule" / ("%s.plist" % LABEL)
AGENTS = Path.home() / "Library" / "LaunchAgents"
LAUNCHCTL = "/bin/launchctl"


def render(repo: Path = ROOT, home: Path = Path.home()) -> bytes:
    text = TEMPLATE.read_text(encoding="utf-8").replace("__REPO__", str(repo)).replace("__HOME__", str(home))
    plistlib.loads(text.encode("utf-8"))  # refuses a template that does not parse
    return text.encode("utf-8")


def installed_path(agents: Path = AGENTS) -> Path:
    return Path(agents) / ("%s.plist" % LABEL)


def main(argv: list, agents: Path = AGENTS, run=subprocess.run, uid: int = None, home: Path = None) -> int:
    ap = argparse.ArgumentParser(description="Manage the Friday launchd schedule")
    ap.add_argument("action", choices=("install", "uninstall", "status"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    uid = os.getuid() if uid is None else uid
    target = installed_path(agents)
    want = render(ROOT, home or Path.home())
    if args.action == "status":
        on_disk = target.read_bytes() if target.exists() else None
        got = run([LAUNCHCTL, "print", "gui/%d/%s" % (uid, LABEL)], capture_output=True, text=True)
        print("installed: %s" % ("no" if on_disk is None else target))
        print("matches the template: %s" % ("-" if on_disk is None else on_disk == want))
        print("loaded in launchd: %s" % ("yes" if got.returncode == 0 else "no"))
        for line in (got.stdout or "").splitlines():
            if line.strip().startswith(("state =", "last exit code =", "runs =")):
                print("  %s" % line.strip())
        return 0
    if args.action == "install":
        if target.exists():
            print("REFUSED: %s is already installed; run uninstall first" % target)
            return 1
        if args.dry_run:
            print("DRY RUN: would write %s (%d bytes) and run %s bootstrap gui/%d %s"
                  % (target, len(want), LAUNCHCTL, uid, target))
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(want)
        got = run([LAUNCHCTL, "bootstrap", "gui/%d" % uid, str(target)], capture_output=True, text=True)
        if got.returncode != 0:
            target.unlink()
            print("REFUSED: launchctl bootstrap failed (%s); nothing is installed" % (got.stderr or "").strip()[:200])
            return 1
        print("INSTALLED: %s, every Friday at 09:00. Check with: python tools/schedule.py status" % target)
        return 0
    if not target.exists():
        print("NOTHING TO DO: %s is not installed" % target)
        return 0
    if args.dry_run:
        print("DRY RUN: would run %s bootout gui/%d/%s and remove %s" % (LAUNCHCTL, uid, LABEL, target))
        return 0
    got = run([LAUNCHCTL, "bootout", "gui/%d/%s" % (uid, LABEL)], capture_output=True, text=True)
    if got.returncode != 0:
        print("REFUSED: launchctl bootout failed (%s); the plist is left in place -- it may still be loaded, "
              "check with: python tools/schedule.py status" % (got.stderr or "").strip()[:200])
        return 1
    target.unlink()
    print("UNINSTALLED: %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
