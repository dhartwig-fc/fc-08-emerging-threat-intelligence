"""
Pin tools/measure_slice2.py: the read-only measurement of the live Friday runs (slice 2 D).

Usage:
    python evals/check_measure_slice2.py
    python evals/check_measure_slice2.py --mutate keep-refused   # a refused run is measured as a run
    python evals/check_measure_slice2.py --mutate sum-rates      # the resolution rate is the mean of per-run rates, not resolved / calls

WHAT IT HOLDS: on three synthetic run directories (a scheduled Friday run, a manual Wednesday run, a refused
run) the totals are exact; the refused run is excluded; the manual run is kept and flagged scheduled false;
the triage band is read from evals/feeds/score.json and not recomputed; at least 2 runs are measured; and
measuring never writes into the inbox.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import measure_slice2  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "measure"
SCORE = ROOT / "evals" / "feeds" / "score.json"


def _tree(p: Path) -> dict:
    return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob("*")) if f.is_file()}


def checks() -> list:
    before = _tree(FIXTURE)
    m = measure_slice2.measure(FIXTURE)
    by = {r["run_id"]: r for r in m["runs"]}
    live, manual = by.get("feeds-2026-01-02-aaaaaa"), by.get("feeds-2026-01-07-bbbbbb")
    t = m["totals"]
    score = json.loads(SCORE.read_text(encoding="utf-8"))["overall"]
    b = m["band"]
    return [
        (len(m["runs"]) >= 2, "non-vacuity: at least 2 runs are measured", len(m["runs"])),
        (t["runs"] == 2 and "feeds-2026-01-09-cccccc" not in by, "the refused run is excluded", sorted(by)),
        (bool(live and manual) and live["scheduled"] is True and manual["scheduled"] is False
         and manual["weekday"] == "Wednesday", "the manual run is kept and flagged scheduled false",
         {k: (v["scheduled"], v["weekday"]) for k, v in by.items()}),
        (t["cost_mean_usd"] == 1.5 and t["cost_max_usd"] == 2.0, "cost per run is run.json's spent_usd (mean 1.5, max 2.0)",
         (t["cost_mean_usd"], t["cost_max_usd"])),
        (t["resolution_rate"] == 0.2 and (live["resolver_calls"], live["resolved"], manual["resolver_calls"], manual["resolved"]) == (10, 1, 5, 2),
         "resolution rate is resolved / calls summed over runs: 3 of 15 = 0.2 (not the mean of 0.1 and 0.4)",
         (t["resolution_rate"], live["resolver_calls"], manual["resolver_calls"])),
        (t["items_by_source"] == {"ofsi": 3, "fincen": 0, "ofac": 4}, "items per source are the new items",
         t["items_by_source"]),
        ((live["triage_kept"], live["triage_total"], manual["triage_kept"], manual["triage_total"]) == (1, 3, 2, 4)
         and t["triage_kept_ratio"] == [3, 7], "live triage is reported as observed kept of total",
         (t["triage_kept_ratio"], live["triage_kept"], manual["triage_kept"])),
        (b == {"recall_min": score["recall"]["min"], "recall_mean": score["recall"]["mean"], "recall_max": score["recall"]["max"],
               "precision_min": score["precision"]["min"], "precision_mean": score["precision"]["mean"],
               "precision_max": score["precision"]["max"]}, "the band is read from score.json", b),
        (_tree(FIXTURE) == before, "measuring writes nothing into the inbox", "tree unchanged"),
    ]


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the slice 2 measurement tool")
    ap.add_argument("--mutate", choices=["keep-refused", "sum-rates"], help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    measure_slice2._MUTATE = args.mutate
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
