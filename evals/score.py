"""
NEXUS Track 2 · Threat Intelligence · Slice 1
Week 3: score predicted AdvisoryRecords against the golden set.

Usage:
    python evals/score.py                          # score data/records/ against evals/golden/
    python evals/score.py --predicted data/records --verbose
    python evals/score.py --json evals/score_report.json
    python evals/score.py --predicted evals/golden  # self-score: must be 1.000 everywhere

Four fields are scored, each with its own matching rule:

  typologies   governed ids, EXACT. An id is an identifier; near enough is wrong.
  emergent     labels with no id, TOKEN OVERLAP (owner decision 2026-09-11).
               The golden set names the same technique three different ways
               ("Black Market Peso Exchange" / "...and money brokering of drug
               proceeds" / "...and three-way exchange exploiting capital
               controls"), so exact-string scoring would report a defect that
               lives in the labels rather than the agent. Containment over the
               shorter token set, not Jaccard, because the same concept is
               described at very different lengths.
  actors       alias-aware: exact match on any normalised name-or-alias pair,
               else token containment. Aliases matter — a record naming "PMLs"
               and a label naming "Professional Money Launderers" share no
               tokens but are the same actor.
  jurisdictions ISO alpha-2, exact.

Matching is greedy one-to-one and deterministic: candidate pairs are sorted by
score then by text, so one golden item can absorb only one prediction and the
result does not depend on dict ordering.

WHY 0.60 AND NOT SOMETHING ELSE. Measured 2026-09-11 by rewording every one of
the golden set's 106 emergent labels (keep two thirds of the content words, add
a qualifier) and scoring the result:

    threshold   1.00    0.80    0.60    0.50
    emergent F1 0.000   0.057   0.934   0.991

0.50 scores higher on paraphrases and is still wrong: "2Rivers DMCC" against
"2Rivers PTE" is exactly 0.50, and those are two different companies on the
same network. 0.60 is the floor that recovers a rewording without collapsing
two entities into one. Note that threshold 1.00 here means full containment of
the shorter token set, which is stricter than string equality in one direction
and looser in the other; it is not an "exact match" mode.

WHAT THIS SCORER WILL NOT DO. It will not report a score for a field where
nothing was found on either side: zero against zero is "n/a", never 1.000. A
metric that can pass by finding nothing is the failure mode this repository
keeps rediscovering.

VERIFIED BOTH WAYS before it was trusted (the 429D ordering rule: prove the
instrument reaches a pass on real data first). Scoring the golden set against
itself gives 1.000 on all four fields over 214 governed ids, 106 emergent
labels, 159 actors and 292 jurisdictions. Scoring a deliberately corrupted copy
— one governed id dropped and one planted, one emergent label replaced with
nonsense, one actor removed, one spurious jurisdiction added per advisory —
moves every field in the right direction and no others. An empty prediction
directory exits 1 rather than reporting a perfect score.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.actor_match import containment, norm, tokens  # noqa: E402,F401  (re-exported: sc.norm etc.)

# EMERGENT 0.50, ACTORS 0.60, and the two are not interchangeable.
#
# Emergent was 0.60 until 2026-09-13. The full-set audit
# (evals/traces/EMERGENT_AUDIT_2026-09-12.md) measured what that cost: of 19
# false positives, 10 were genuine paraphrases the threshold refused to credit.
# Lowering it to 0.50 credits 7 of them and merges nothing -- every gained match
# was read pair by pair against its citations:
#
#   0.60 -> 0.50 gains 7, all genuine restatements. Examples:
#     "Black Market Peso Exchange (BMPE) Trade-Based Settlement"
#       <-> "Black market peso exchange and three-way exchange exploiting capital controls"
#     "Cryptocurrency Layering via Mixing Services, Chain-Hopping and DeFi"
#       <-> "Cryptocurrency laundering through mixers, chain hopping, privacy coins and DeFi"
#
# 0.40 IS THE FLOOR AND IT IS REAL, not hypothetical. It merges this pair on
# ADV-2026-0004 at 0.43, and they are different mechanisms:
#     "Professional Intermediary (TCSP/Legal/Accounting) Gatekeeper Complicity"
#       <-> "Trusts and legal arrangements interposed to separate legal from beneficial ownership"
#
# THE ACTOR THRESHOLD STAYS AT 0.60, and the reason is the 2Rivers pair below.
# "2Rivers DMCC" and "2Rivers PTE" are two different companies, both real actors
# in ADV-2026-0017's label, and they score exactly 0.50 -- so an actor threshold
# of 0.50 would score them as one. That example was previously quoted as the
# justification for the EMERGENT threshold; it is a real case, but it is an
# ACTOR case, and conflating the two constants is what kept emergent at 0.60 for
# no measured reason. Change one without the other.
#
# Guarded by evals/check_emergent_threshold.py, mutation-verified.
DEFAULT_EMERGENT_THRESHOLD = 0.50
DEFAULT_ACTOR_THRESHOLD = 0.60


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def governed_ids(record: dict) -> list:
    return sorted({t["typology_id"] for t in record.get("typologies", []) if t.get("typology_id")})


def emergent_labels(record: dict) -> list:
    return [t["label"] for t in record.get("typologies", []) if not t.get("typology_id")]


def actor_variants(record: dict) -> list:
    """One entry per actor: every spelling it answers to."""
    out = []
    for a in record.get("actors", []):
        names = [a.get("name", "")] + list(a.get("aliases") or [])
        out.append({"display": a.get("name", ""), "variants": [n for n in names if n]})
    return out


def jurisdictions(record: dict) -> list:
    return sorted({j.upper() for j in record.get("jurisdictions", [])})


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_exact(gold: list, pred: list) -> tuple:
    """Set matching for identifiers. Returns (pairs, unmatched_gold, unmatched_pred)."""
    g, p = list(gold), list(pred)
    pairs = [(x, x) for x in g if x in p]
    matched = {x for x, _ in pairs}
    return pairs, [x for x in g if x not in matched], [x for x in p if x not in matched]


def match_by_score(gold: list, pred: list, score_fn, threshold: float) -> tuple:
    """Greedy one-to-one matching above a threshold. Deterministic."""
    candidates = []
    for gi, gv in enumerate(gold):
        for pi, pv in enumerate(pred):
            s = score_fn(gv, pv)
            if s >= threshold:
                candidates.append((s, str(gv), str(pv), gi, pi))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_g, used_p, pairs = set(), set(), []
    for s, _, _, gi, pi in candidates:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gold[gi], pred[pi], round(s, 3)))
    return (pairs,
            [g for i, g in enumerate(gold) if i not in used_g],
            [p for i, p in enumerate(pred) if i not in used_p])


def emergent_score(a: str, b: str) -> float:
    return 1.0 if norm(a) == norm(b) else containment(tokens(a), tokens(b))


def actor_score(a: dict, b: dict) -> float:
    """Best score over every pair of spellings. Exact on any alias wins outright."""
    best = 0.0
    for av in a["variants"]:
        for bv in b["variants"]:
            if norm(av) and norm(av) == norm(bv):
                return 1.0
            best = max(best, containment(tokens(av), tokens(bv)))
    return best


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class Tally:
    __slots__ = ("tp", "fp", "fn")

    def __init__(self):
        self.tp = self.fp = self.fn = 0

    def add(self, tp: int, fp: int, fn: int) -> None:
        self.tp += tp
        self.fp += fp
        self.fn += fn

    @property
    def seen(self) -> int:
        return self.tp + self.fp + self.fn

    def prf(self) -> tuple:
        """(precision, recall, f1) or (None, None, None) when there was nothing to score."""
        if self.seen == 0:
            return (None, None, None)
        p = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0
        r = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0
        f = (2 * p * r / (p + r)) if (p + r) else 0.0
        return (p, r, f)


FIELDS = ("typologies", "emergent", "actors", "jurisdictions")


def score_pair(gold: dict, pred: dict, emergent_threshold: float, actor_threshold: float) -> dict:
    out = {}

    pairs, miss_g, miss_p = match_exact(governed_ids(gold), governed_ids(pred))
    out["typologies"] = {"tp": len(pairs), "fn": len(miss_g), "fp": len(miss_p),
                         "missed": miss_g, "spurious": miss_p, "matched": [g for g, _ in pairs]}

    pairs, miss_g, miss_p = match_by_score(emergent_labels(gold), emergent_labels(pred),
                                           emergent_score, emergent_threshold)
    out["emergent"] = {"tp": len(pairs), "fn": len(miss_g), "fp": len(miss_p),
                       "missed": miss_g, "spurious": miss_p,
                       "matched": [{"gold": g, "predicted": p, "score": s} for g, p, s in pairs]}

    pairs, miss_g, miss_p = match_by_score(actor_variants(gold), actor_variants(pred),
                                           actor_score, actor_threshold)
    out["actors"] = {"tp": len(pairs), "fn": len(miss_g), "fp": len(miss_p),
                     "missed": [g["display"] for g in miss_g], "spurious": [p["display"] for p in miss_p],
                     "matched": [{"gold": g["display"], "predicted": p["display"], "score": s}
                                 for g, p, s in pairs]}

    pairs, miss_g, miss_p = match_exact(jurisdictions(gold), jurisdictions(pred))
    out["jurisdictions"] = {"tp": len(pairs), "fn": len(miss_g), "fp": len(miss_p),
                            "missed": miss_g, "spurious": miss_p, "matched": [g for g, _ in pairs]}
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def pct(x) -> str:
    return "  n/a " if x is None else "%.3f" % x


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Score predicted AdvisoryRecords against the golden set")
    ap.add_argument("--golden", type=Path, default=ROOT / "evals" / "golden")
    ap.add_argument("--predicted", type=Path, default=ROOT / "data" / "records")
    ap.add_argument("--emergent-threshold", type=float, default=DEFAULT_EMERGENT_THRESHOLD)
    ap.add_argument("--actor-threshold", type=float, default=DEFAULT_ACTOR_THRESHOLD)
    ap.add_argument("--verbose", action="store_true", help="per-advisory detail and what was missed")
    ap.add_argument("--json", type=Path, default=None, help="write the full report here")
    args = ap.parse_args(argv)

    golden = {}
    for p in sorted(args.golden.glob("ADV-*.json")):
        try:
            golden[_load(p)["advisory_id"]] = _load(p)
        except (KeyError, json.JSONDecodeError) as exc:
            print("skipping unreadable golden label %s: %s" % (p.name, exc), file=sys.stderr)
    if not golden:
        print("No golden labels found in %s. Nothing to score against." % args.golden, file=sys.stderr)
        return 1

    predicted = {}
    if args.predicted.is_dir():
        for p in sorted(args.predicted.glob("ADV-*.json")):
            # Only the current record per advisory; sidecars such as
            # ADV-2026-0001.week1-schema-1.1.0.json are history, not predictions.
            if not re.fullmatch(r"ADV-\d{4}-\d{4}", p.stem):
                continue
            try:
                predicted[_load(p)["advisory_id"]] = _load(p)
            except (KeyError, json.JSONDecodeError) as exc:
                print("skipping unreadable predicted record %s: %s" % (p.name, exc), file=sys.stderr)

    scored_ids = sorted(set(golden) & set(predicted))
    unpredicted = sorted(set(golden) - set(predicted))
    unlabelled = sorted(set(predicted) - set(golden))

    print("golden labels: %d | predicted records: %d | scored: %d"
          % (len(golden), len(predicted), len(scored_ids)))
    if unpredicted:
        print("NOT SCORED, no predicted record (%d): %s" % (len(unpredicted), ", ".join(unpredicted)))
    if unlabelled:
        print("ignored, predicted but not in the golden set (%d): %s" % (len(unlabelled), ", ".join(unlabelled)))
    if not scored_ids:
        print("\nNothing was scored. A scorer with no pairs reports no number, not a perfect one.", file=sys.stderr)
        return 1
    print("emergent matching: token containment >= %.2f | actor matching: alias-aware, >= %.2f"
          % (args.emergent_threshold, args.actor_threshold))

    totals = {f: Tally() for f in FIELDS}
    per_advisory = {}
    for aid in scored_ids:
        detail = score_pair(golden[aid], predicted[aid], args.emergent_threshold, args.actor_threshold)
        per_advisory[aid] = detail
        for f in FIELDS:
            totals[f].add(detail[f]["tp"], detail[f]["fp"], detail[f]["fn"])

    print()
    print("%-14s %7s %7s %7s   %9s %7s %7s" % ("field", "TP", "FP", "FN", "precision", "recall", "F1"))
    print("-" * 66)
    for f in FIELDS:
        t = totals[f]
        p, r, f1 = t.prf()
        note = "   (nothing to score)" if t.seen == 0 else ""
        print("%-14s %7d %7d %7d   %9s %7s %7s%s" % (f, t.tp, t.fp, t.fn, pct(p), pct(r), pct(f1), note))

    if args.verbose:
        for aid in scored_ids:
            print("\n=== %s" % aid)
            for f in FIELDS:
                d = per_advisory[aid][f]
                print("  %-13s tp=%-3d fp=%-3d fn=%-3d" % (f, d["tp"], d["fp"], d["fn"]))
                if d["missed"]:
                    print("      missed:   %s" % ", ".join(str(m)[:70] for m in d["missed"]))
                if d["spurious"]:
                    print("      spurious: %s" % ", ".join(str(s)[:70] for s in d["spurious"]))
                if f in ("emergent", "actors"):
                    for m in d["matched"]:
                        if m["score"] < 1.0:
                            print("      fuzzy %.2f: %s  ~  %s" % (m["score"], str(m["gold"])[:45], str(m["predicted"])[:45]))

    if args.json:
        report = {
            "golden_dir": str(args.golden), "predicted_dir": str(args.predicted),
            "emergent_threshold": args.emergent_threshold, "actor_threshold": args.actor_threshold,
            "scored": scored_ids, "not_scored_no_prediction": unpredicted, "ignored_no_golden": unlabelled,
            "totals": {f: dict(tp=totals[f].tp, fp=totals[f].fp, fn=totals[f].fn,
                               precision=totals[f].prf()[0], recall=totals[f].prf()[1], f1=totals[f].prf()[2])
                       for f in FIELDS},
            "per_advisory": per_advisory,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nwrote %s" % args.json)

    if len(scored_ids) < len(golden):
        print("\nPartial run: %d of %d golden labels had a predicted record. These numbers describe "
              "that subset only." % (len(scored_ids), len(golden)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
