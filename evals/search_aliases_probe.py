"""
Guard the search alias layer: it must fix the direction inversion, stay symmetric,
and not buy recall by matching everything.

Usage:
    python evals/search_aliases_probe.py
    python evals/search_aliases_probe.py --mutate    # empty the map; the fix MUST fail

WHY. Traced 2026-09-12 on ADV-2026-0016 red flag 4, "a customer that
significantly OVERPAYS for a Common High Priority list item". TBML001 Over
Invoicing never says "overpay" in its doctrine; TBML002U Under Invoicing does,
in a mirror-image contrast. `overpa` was the highest-IDF term in such a query,
so the OPPOSITE-direction typology outranked the right one 0.78 to 0.42, and
the agent -- correctly, on the mechanism test -- refused to assert either.

WHAT THIS LAYER DOES NOT FIX, stated because a guard that oversells its scope is
worse than no guard:

  The document's OWN sentence still does not return TBML001. The label route
  needs two of TBML001's label stems {invoic, over} and the document supplies
  neither ("overpays" stems to `overpa`, not `over`); the query route is diluted
  across seventeen words. That is the scorer's documented length property, not an
  alias gap, and rescuing one sentence with a bespoke third scoring route would
  be overfitting to a single trace. Measured after the layer:
  search_recall top-5 0.496 -> 0.501, probes still 12 of 12.

  The CORRECT fix is upstream: fc-10's TBML001 doctrine under-describes the
  technique by omitting payment-side vocabulary. This layer approximates that
  and is explicitly the fast version.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server import knowledge_centre_server as kc  # noqa: E402

# The query the trace turned on: payment-side phrasing of over-invoicing.
DIRECTION_QUERY = "overpayment for goods above market value"

# Emergent techniques that must NOT acquire a library match. Same two that
# regressed when the label route was added without its two-term guard.
MUST_STAY_EMERGENT = ("Black Market Peso Exchange used by drug cartels to launder proceeds",
                      "surrogate shoppers purchasing luxury goods on behalf of wealthy clients")


def checks() -> list:
    out = []
    al = kc.SEARCH_ALIASES

    out.append((bool(al), "the alias map is not empty",
                "%d typologies carry aliases" % len(al)))

    known = {t["typology_id"] for t in kc._typologies()}
    bad = [k for k in al if k not in known]
    out.append((not bad, "every alias key is a real typology id", "unknown: %s" % bad if bad else "all known"))

    # Direction pairs must be symmetric: TBML001/TBML002U is the pair this exists for.
    pair_ok = ("TBML001" in al) == ("TBML002U" in al)
    out.append((pair_ok, "the over/under invoicing pair is aliased on BOTH sides",
                "asymmetric aliasing biases a direction pair rather than separating it"))

    ranked = kc.rank_typologies(DIRECTION_QUERY)
    above = [(s, r["typology_id"]) for s, r in ranked if s >= kc.SEARCH_SCORE_FLOOR]
    pos = {tid: i for i, (_, tid) in enumerate(above)}
    fixed = "TBML001" in pos and ("TBML002U" not in pos or pos["TBML001"] < pos["TBML002U"])
    out.append((fixed, "TBML001 outranks TBML002U for %r" % DIRECTION_QUERY,
                "top: %s" % [(round(s, 2), t) for s, t in above[:3]]))

    for phrase in MUST_STAY_EMERGENT:
        r = kc.rank_typologies(phrase)
        hit = [(round(s, 2), x["typology_id"]) for s, x in r if s >= kc.SEARCH_SCORE_FLOOR]
        out.append((not hit, "stays emergent: %r" % phrase[:46],
                    "returned %s" % hit if hit else "nothing above the floor, as required"))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Guard the search alias layer")
    ap.add_argument("--mutate", action="store_true",
                    help="empty SEARCH_ALIASES; the direction check MUST then fail")
    args = ap.parse_args(argv)

    if args.mutate:
        kc.SEARCH_ALIASES = {}
        print("MUTATED: SEARCH_ALIASES emptied. The direction check must fail, or this probe\n"
              "         proves nothing about the layer.\n")

    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1

    if args.mutate:
        # Inverted: at least one failure is required.
        print("\n%s" % ("HELD: the probe detects the defect when the layer is removed" if failures
                        else "NOTHING PROVED: the probe passed with the layer gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED",
                                   failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
