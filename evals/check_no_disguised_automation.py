"""
Refuse disguised browser automation anywhere in the tracked tree (spec 2026-10-31 §2).

Usage:
    python evals/check_no_disguised_automation.py
    python evals/check_no_disguised_automation.py --mutate plant   # a tracked tool that switches AutomationControlled off

WHY. tools/fetch_fatf_via_chrome.js (2026-09-10 to 2026-10-31) launched Chrome with AutomationControlled off and
navigator.webdriver hidden, to pass fatf-gafi.org's bot check. fc-08 does not get past bot checks: FATF arrives
through tools/intake_document.py, from a file the owner downloaded. This keeps that retirement from being undone.

WHAT IT HOLDS: no tracked file outside ALLOWED (this guard, and the spec and plan that record the retirement)
carries any signature (the two Chrome switches, or a stealth library), and at least 200 tracked text files were
read -- a scan of nothing passes nothing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNATURES = (re.compile(r"AutomationControlled"),
              re.compile(r"""navigator\s*,\s*['"]webdriver['"]|navigator\.webdriver\s*="""),
              re.compile(r"puppeteer-extra-plugin-stealth|undetected[_-]chromedriver|playwright[_-]stealth"))
ALLOWED = {"evals/check_no_disguised_automation.py",
           "docs/superpowers/specs/2026-10-31-wolfsberg-swept-fatf-by-hand-design.md",
           "docs/superpowers/plans/2026-10-31-wolfsberg-swept-fatf-by-hand.md"}
PLANT = ("tools/planted.js", "chromium.launch({ args: ['--disable-blink-features=AutomationControlled'] })")
MIN_FILES = 200


def tracked() -> list:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def checks(mutation) -> list:
    files = []
    for rel in tracked():
        try:
            files.append((rel, (ROOT / rel).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
    if mutation == "plant":
        files.append(PLANT)
    hits = sorted(rel for rel, text in files if rel not in ALLOWED and any(s.search(text) for s in SIGNATURES))
    return [(len(files) >= MIN_FILES, "the scan read the tracked tree", "%d text files" % len(files)),
            (not hits, "no tracked file disguises browser automation", hits)]


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--mutate", choices=["plant"])
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s" % ("HOLDS" if not failures else "FAILED: %d" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
