"""
Measure the Knowledge Centre search tool against REAL advisory language.

Usage:
    python evals/search_recall.py               # headline numbers
    python evals/search_recall.py --verbose     # every case the tool fails
    python evals/search_recall.py --threshold 0.15

WHY THIS EXISTS, and why `search_probes.py` was not enough.

`search_probes.py` holds twelve phrases with expected answers and passes 12 of
12. I wrote those phrases. Measured 2026-09-11 against the first baseline, the
tool behaves very differently on sentences written by FATF, OFAC and the NCA:
of thirty typologies the extraction agent MISSED, the tool would have surfaced
only thirteen in its top five when handed the golden label's own evidence. The
other seventeen it could not return at all, eight of them with nothing above
the score floor.

So roughly half the agent's recall gap is this tool, not the agent. A probe set
written by the same hand that wrote the scorer is too easy, in the same way a
guard that has never been seen to fail is decoration.

THE CORPUS IS THE GOLDEN SET. Every (citation quote -> governed typology_id)
pair in `evals/golden/` is a case where a human-reviewed label says: this
sentence, from a real advisory, evidences this typology. That is exactly the
question the tool is asked at runtime, so it is the honest test.

WHAT A FAILURE HERE MEANS. The agent cannot label a typology the tool will not
return, because governance forbids naming an id no tool produced. Every miss
below is a ceiling on extraction recall that no prompt change can lift.

NOT A VACUOUS PASS. The run fails if fewer than 50 cases are found, because a
recall figure over a handful of quotes says nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server import knowledge_centre_server as kc  # noqa: E402

MIN_CASES = 50


def corpus() -> list:
    """(advisory_id, typology_id, quote) for every governed citation in the golden set."""
    cases = []
    for path in sorted((ROOT / "evals" / "golden").glob("ADV-*.json")):
        label = json.loads(path.read_text(encoding="utf-8"))
        for t in label.get("typologies", []):
            tid = t.get("typology_id")
            if not tid:
                continue
            for c in t.get("citations", []):
                cases.append((label["advisory_id"], tid, c["quote"]))
    return cases


def rank_of(tid: str, quote: str, threshold: float) -> tuple:
    """(rank of tid among returned results, number returned). rank is None if absent."""
    ranked = kc.rank_typologies(quote)
    above = [r["typology_id"] for score, r in ranked if score >= threshold]
    rank = above.index(tid) + 1 if tid in above else None
    return rank, len(above)


def _family(tid: str) -> str:
    for prefix in ("TBML", "SAN", "CMI", "PAT", "FND", "BA", "CM"):
        if tid.startswith(prefix):
            return prefix
    return "?"


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Search recall against real advisory language")
    ap.add_argument("--threshold", type=float, default=kc.SEARCH_SCORE_FLOOR)
    ap.add_argument("--verbose", action="store_true", help="list every case the tool fails")
    args = ap.parse_args(argv)

    cases = corpus()
    if len(cases) < MIN_CASES:
        print("only %d cases found in evals/golden/ (need %d). A recall figure over a handful of "
              "quotes says nothing." % (len(cases), MIN_CASES), file=sys.stderr)
        return 1

    at1 = at3 = at5 = absent = empty_result = 0
    failures = []
    by_family: Counter = Counter()
    fam_total: Counter = Counter()

    for aid, tid, quote in cases:
        rank, returned = rank_of(tid, quote, args.threshold)
        fam = _family(tid)
        fam_total[fam] += 1
        if rank and rank <= 5:
            at5 += 1
            by_family[fam] += 1
            if rank <= 3:
                at3 += 1
            if rank == 1:
                at1 += 1
        else:
            absent += 1
            if returned == 0:
                empty_result += 1
            failures.append((aid, tid, rank, returned, quote))

    n = len(cases)
    print("corpus: %d governed citations across %d golden labels" % (n, len({c[0] for c in cases})))
    print("threshold: %.2f\n" % args.threshold)
    print("  hit at rank 1      %4d   %.3f" % (at1, at1 / n))
    print("  hit in top 3       %4d   %.3f" % (at3, at3 / n))
    print("  hit in top 5       %4d   %.3f" % (at5, at5 / n))
    print("  never returned     %4d   %.3f   (of which %d returned NOTHING above the floor)"
          % (absent, absent / n, empty_result))

    print("\n  top-5 recall by family")
    for fam in sorted(fam_total):
        print("    %-5s %3d of %3d   %.3f" % (fam, by_family[fam], fam_total[fam], by_family[fam] / fam_total[fam]))

    if args.verbose and failures:
        print("\n  cases the tool cannot serve (%d):" % len(failures))
        for aid, tid, rank, returned, quote in failures:
            where = ("rank %d" % rank) if rank else ("nothing above floor" if returned == 0
                                                     else "%d returned, not it" % returned)
            print("    %s %-9s %-22s %s" % (aid[-4:], tid, where, quote[:66]))

    print("\nEvery miss is a ceiling on extraction recall: governance forbids the agent naming an id "
          "no tool returned.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
