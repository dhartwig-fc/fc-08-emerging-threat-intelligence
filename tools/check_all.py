"""
Run every guard, the way the pre-commit hook and CI do.

Usage:
    python tools/check_all.py           # everything; needs the gitignored PDFs
    python tools/check_all.py --cold    # only guards proved to pass in a fresh clone
    python tools/check_all.py --list    # the table, no runs

Each guard's CLASS was measured by running it in a fresh clone (week 6.1), not read
from its source:
  cold             passes from a fresh clone
  needs-pdfs       re-finds quotes on data/advisories/*.pdf, which is gitignored
  needs-portfolio  reads the portfolio checkout (sub-project 2)
  needs-reviewed   reads data/reviewed/, the reviewer's additions, which is gitignored
--cold prints every other guard as NOT RUN, so a green CI run says what it did not cover.

The measurement disagreed with the plan's guess for three guards -- check_telemetry,
check_tool_surface (its default/static mode; --live is never run here) and
review.py --check -- all three passed cold. The measurement wins; they are classed
"cold" below.

evals/check_citations.py --all does not simply pass or fail: it diffs the current
citation-defect set against the frozen baseline in evals/known_citation_defects.json.
That baseline held 118 pre-existing defects (103 after the matcher's ARTEFACT tier, 91
after its ELLIPSIS tier) until the owner's citation repair of 2026-09-25
(evals/owner_decisions/citation_repair_2026-09-25.json) emptied it; 12 true quotes the
matcher cannot place are owner-attested. It needs the PDFs to compute that set,
so it is classed needs-pdfs even though its usual outcome, given the PDFs, is a clean
diff against the baseline rather than a raw pass. It also reads the owner's citation
attestations (evals/attested_citations.json) and refuses a stale, duplicated or
no-longer-needed entry; evals/check_attestations.py pins that logic cold.

The citation repair has two guards on purpose. evals/check_citation_repair.py replays
the evidence against the tracked data/records and data/records_merged and is cold.
tools/apply_citation_repair.py --check regenerates the merge from data/records plus the
reviewer's additions in data/reviewed/ (gitignored) and compares byte for byte, so it is
needs-reviewed and --cold prints it NOT RUN. Both classes were measured in a fresh
depth-1 clone: the replay passed; --check refused, because without the reviewer's
additions the merge does not match the evidence and writes nothing.

Every evals/check_*.py must be in GUARDS, and every GUARDS entry must exist: a new
guard cannot be silently left out, and a deleted one cannot linger as a name.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GUARDS = [
    # (name, argv after the interpreter, class) -- classes from the fresh-clone measurement
    ("check_digest_routing", ["evals/check_digest_routing.py"], "cold"),
    ("check_digest_batch", ["evals/check_digest_batch.py"], "cold"),
    ("check_emergent_threshold", ["evals/check_emergent_threshold.py"], "cold"),
    ("check_citation_match", ["evals/check_citation_match.py"], "cold"),
    ("check_attestations", ["evals/check_attestations.py"], "cold"),
    ("check_added_by", ["evals/check_added_by.py"], "cold"),
    ("check_actor_resolution", ["evals/check_actor_resolution.py"], "cold"),
    ("check_telemetry", ["evals/check_telemetry.py"], "cold"),
    ("check_tool_surface", ["evals/check_tool_surface.py"], "cold"),
    ("check_publish_boundary", ["evals/check_publish_boundary.py"], "cold"),
    ("check_walkthrough", ["evals/check_walkthrough.py"], "cold"),
    ("build_walkthrough --check", ["tools/build_walkthrough.py", "--check"], "cold"),
    # The batch is DATA (data/digests/CURRENT), so cutting a new batch never edits this list.
    ("build_digests --check (current batch)", ["tools/build_digests.py", "--current", "--check"], "cold"),
    ("build_actor_register --check", ["tools/build_actor_register.py", "--check"], "cold"),
    ("actor_resolution --check", ["evals/actor_resolution.py", "--check"], "cold"),
    ("review.py --check", ["tools/review.py", "--check"], "cold"),
    ("check_review_gate", ["evals/check_review_gate.py"], "needs-pdfs"),
    ("check_proposal_contract", ["evals/check_proposal_contract.py"], "needs-pdfs"),
    ("check_twin_pairs", ["evals/check_twin_pairs.py"], "needs-pdfs"),
    ("check_citations --all", ["evals/check_citations.py", "--all"], "needs-pdfs"),
    ("check_citation_repair", ["evals/check_citation_repair.py"], "cold"),
    ("apply_citation_repair --check", ["tools/apply_citation_repair.py", "--check"], "needs-reviewed"),
]
CLASSES = ("cold", "needs-pdfs", "needs-portfolio", "needs-reviewed")


def coverage_problems() -> list:
    listed = {Path(argv[0]).name for _, argv, _ in GUARDS if argv[0].startswith("evals/check_")}
    present = {p.name for p in (ROOT / "evals").glob("check_*.py")}
    out = ["%s is a guard but is not in check_all's list" % n for n in sorted(present - listed)]
    out += ["check_all lists %s, which does not exist" % n for n in sorted(listed - present)]
    out += ["%s has unknown class %r" % (n, c) for n, _, c in GUARDS if c not in CLASSES]
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Run every guard")
    ap.add_argument("--cold", action="store_true", help="only guards proved to pass in a fresh clone")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    problems = coverage_problems()
    for p in problems:
        print("FAIL  %s" % p)
    if args.list:
        for name, _, cls in GUARDS:
            print("%-16s %s" % (cls, name))
        return 1 if problems else 0

    failed, not_run = list(problems), []
    for name, cmd, cls in GUARDS:
        if args.cold and cls != "cold":
            not_run.append("NOT RUN (%s): %s" % (cls, name))
            continue
        r = subprocess.run([sys.executable] + cmd, cwd=ROOT, capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        print("%-4s %-30s %s" % ("ok" if r.returncode == 0 else "FAIL", name, tail[:90]))
        if r.returncode != 0:
            failed.append(name)
            # A guard that dies (a traceback, a refusal) says why on stderr, not in its last stdout line.
            for line in r.stderr.strip().splitlines()[-5:]:
                print("       %s" % line)
    for line in not_run:
        print(line)
    print("\n%s: %d run, %d not run, %d failed" % ("PASS" if not failed else "FAIL",
                                                  len(GUARDS) - len(not_run), len(not_run), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
