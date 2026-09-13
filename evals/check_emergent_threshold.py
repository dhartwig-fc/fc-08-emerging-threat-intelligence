"""
Pin the emergent matching threshold, and pin the floor beneath it.

Usage:
    python evals/check_emergent_threshold.py
    python evals/check_emergent_threshold.py --mutate    # drop to 0.40; the merge check MUST fail

WHY. Emergent sat at 0.60 until 2026-09-13 on a justification that did not
belong to it. The docstring defended it with "0.50 collapses 2Rivers DMCC into
2Rivers PTE" -- a REAL pair, both companies in ADV-2026-0017's label, scoring
exactly 0.50 -- but they are ACTORS, matched under DEFAULT_ACTOR_THRESHOLD. The
emergent constant was being held up by an actor case. Conflating two thresholds
is how a number survives three weeks without ever being measured.

Measured on the full 20 (evals/traces/EMERGENT_AUDIT_2026-09-12.md), emergent
0.60 -> 0.50 credits 7 further matches, every one a genuine restatement, and
merges nothing. F1 0.208 -> 0.306, precision 0.441 -> 0.647.

WHAT THIS FILE PROTECTS. Not the number for its own sake -- the two facts that
justify it, so a future change has to argue with evidence rather than taste:

  1. At the chosen threshold, a known-DISTINCT pair does not merge.
  2. At 0.40 that same pair DOES merge, so the floor is real and not a hunch.
  3. The 2Rivers actors stay separate under the actor threshold, which is why
     that constant did not move.

NOT A VACUOUS PASS. --mutate lowers the threshold to the unsafe value and the
distinct-pair check must then fail. A guard never seen to fail is decoration.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("fc08_score", ROOT / "evals" / "score.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

# Different mechanisms, both from ADV-2026-0004's golden label. Gatekeeper
# complicity is a professional-enabler technique; interposing trusts is a
# structural concealment technique. They share legal vocabulary and nothing else.
DISTINCT = ("Professional Intermediary (TCSP/Legal/Accounting) Gatekeeper Complicity in Beneficial Ownership Concealment",
            "Trusts and legal arrangements interposed to separate legal from beneficial ownership")

# The same technique, restated. From ADV-2026-0008 and ADV-2026-0019.
SAME = [("Black Market Peso Exchange (BMPE) Trade-Based Settlement",
         "Black market peso exchange and three-way exchange exploiting capital controls"),
        ("Cryptocurrency Layering via Mixing Services, Chain-Hopping and DeFi",
         "Cryptocurrency laundering through mixers, chain hopping, privacy coins and DeFi")]

# Two different companies on the blue side of the shadow fleet network, both
# real actors in ADV-2026-0017's label.
ACTORS = ("2Rivers DMCC", "2Rivers PTE")

UNSAFE = 0.40


def score(a: str, b: str) -> float:
    return sc.containment(sc.tokens(a), sc.tokens(b))


def checks(threshold: float) -> list:
    out = []
    out.append((threshold == 0.50, "the emergent threshold is 0.50",
                "measured, not chosen: 0.60 refused 7 genuine restatements"))

    d = score(*DISTINCT)
    out.append((d < threshold, "a known-DISTINCT pair stays separate at %.2f" % threshold,
                "gatekeeper complicity vs interposed trusts scores %.2f" % d))

    out.append((d >= UNSAFE, "and that same pair MERGES at %.2f, so the floor is real" % UNSAFE,
                "%.2f >= %.2f -- 0.40 is not available, and this is why" % (d, UNSAFE)))

    for a, b in SAME:
        s = score(a, b)
        out.append((s >= threshold, "a genuine restatement matches: %s" % a[:44],
                    "scores %.2f" % s))

    act = score(*ACTORS)
    out.append((act < sc.DEFAULT_ACTOR_THRESHOLD,
                "the 2Rivers companies stay SEPARATE under the actor threshold",
                "scores %.2f against actor threshold %.2f -- two real companies, and the reason "
                "that constant did not move with the emergent one"
                % (act, sc.DEFAULT_ACTOR_THRESHOLD)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the emergent threshold")
    ap.add_argument("--mutate", action="store_true",
                    help="test at %.2f; the distinct-pair check MUST fail" % UNSAFE)
    args = ap.parse_args(argv)

    threshold = UNSAFE if args.mutate else sc.DEFAULT_EMERGENT_THRESHOLD
    if args.mutate:
        print("MUTATED: testing at %.2f. The distinct-pair check must fail, or this probe\n"
              "         proves nothing about where the floor is.\n" % UNSAFE)

    failures = 0
    for ok, label, detail in checks(threshold):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1

    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the merge at the unsafe threshold" if failures
                        else "NOTHING PROVED: it passed at the threshold it calls unsafe"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED",
                                   failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
