"""
Pin the public-page boundary: a page leaving this repository must not name local
paths, internal files, or people's addresses.

Usage:
    python evals/check_publish_boundary.py
    python evals/check_publish_boundary.py --mutate no-paths      # absolute/home paths pass; MUST fail
    python evals/check_publish_boundary.py --mutate no-internal   # internal names pass; MUST fail
    python evals/check_publish_boundary.py --mutate no-email      # addresses pass; MUST fail

WHY. fc-10 shipped pages across the public boundary for weeks with the check run
only when a human remembered (its CLAUDE.md, 2026-09-10). This is fc-08's own
check -- importing fc-10's would make a public repository depend on a sibling.

OFFLINE. Synthetic strings only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402

CLEAN = "<p>ADV-2026-0013 was approved on 2026-09-24; see github.com/example/repo/blob/main/evals/traces/X.md</p>"
PASS_CASES = [
    ("legitimate URL with data/ in path", "https://www.example.gov/sanctions/data/downloads/sdn.xml"),
    ("prose mentioning metadata/provenance fields", "governed metadata/provenance fields"),
]
REFUSE_CASES = [
    ("an absolute macOS path", "<p>built at /Users/someone/fc-08/site</p>", "/Users/"),
    ("a home-relative path", "<p>see ~/fc-08-emerging-threat-intelligence</p>", "~/"),
    ("a Windows drive path", "<p>C:\\work\\fc08</p>", "C:\\"),
    ("a queue file", "<p>adv-2026-0013-extractor-f617bd3b00.jsonl</p>", ".jsonl"),
    ("the decision log's filename", "<p>%s</p>" % gd.LOG.name, gd.LOG.name),
    ("an approvals file's filename", "<p>%s</p>" % gd.APPROVED_LINKS.name, gd.APPROVED_LINKS.name),
    ("a repo-relative data/ path", "<p>data/desk_routing.json</p>", "data/"),
    ("the SDD workspace", "<p>.superpowers/sdd</p>", ".superpowers"),
    ("the virtualenv", "<p>.venv/bin/python</p>", ".venv"),
    ("an email address", "<p>contact someone@example.com</p>", "someone@example.com"),
    ("a percent-encoded path", "<p>href=\"/r?u=%2FUsers%2Fsomeone%2Ffc-08\"</p>", "/Users/"),
    ("the approved-emergent filename", "<p>%s</p>" % gd.APPROVED_EMERGENT.name, gd.APPROVED_EMERGENT.name),
]


def checks() -> list:
    out = [(pb.violations(CLEAN) == [], "a clean page passes (a GitHub URL and ids are not violations)",
            str(pb.violations(CLEAN)))]
    for label, text in PASS_CASES:
        got = pb.violations(text)
        out.append((got == [], "allowed: %s" % label, str(got)))
    for label, text, token in REFUSE_CASES:
        got = pb.violations(text)
        out.append((any(token in v for v in got), "refused: %s" % label, str(got)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the publish boundary")
    ap.add_argument("--mutate", choices=("no-paths", "no-internal", "no-email"))
    args = ap.parse_args(argv)
    if args.mutate == "no-paths":
        pb._PATH_PATTERNS = ()
    elif args.mutate == "no-internal":
        pb.FORBIDDEN_LITERALS = ()
        pb._INTERNAL_PATTERNS = ()
    elif args.mutate == "no-email":
        pb._EMAIL = None
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
