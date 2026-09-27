"""
Pin the triage scorer (evals/score_feeds_triage.py): recall first, precision beside it, a band over repeats.

Usage:
    python evals/check_feeds_score.py
    python evals/check_feeds_score.py --mutate missing-excluded    # an unfinished relevant item leaves the denominator
    python evals/check_feeds_score.py --mutate swap                # recall and precision swapped
    python evals/check_feeds_score.py --mutate band-first          # the band is one repeat, not three
    python evals/check_feeds_score.py --mutate zero-as-one         # recall over no relevant items reads 1.0
    python evals/check_feeds_score.py --mutate draft-labels        # the owner's decisions are ignored
    python evals/check_feeds_score.py --mutate majority-dispute    # a dispute needs 2 of 3 repeats to disagree
    python evals/check_feeds_score.py --mutate unfinished-dispute  # a missing verdict counts as a dispute
    python evals/check_feeds_score.py --mutate decide-anything     # a decision on an undisputed item is accepted
    python evals/check_feeds_score.py --mutate spot-any-agreed     # the spot check samples agreed relevant items too

WHAT IT HOLDS, on a synthetic set whose every figure was computed by hand (ten items, three sources,
three repeats, four disputes, four owner decisions):
  the counts    tp, fn, fp, tn and the unfinished list of one repeat, and its recall and precision;
  unfinished    a relevant item with no verdict is a miss: it stays in recall's denominator;
  the band      min, max and mean over all three repeats, for recall and for precision;
  n/a           a ratio over an empty denominator is null, never 0 or 1;
  disputes      an item is disputed when ANY repeat's verdict differs from the draft, one of three is
                enough, and an item with no verdict is not disputed;
  decisions     the owner's decision replaces the draft; a decision on an undisputed item, a second
                decision, and an undecided dispute are each refused;
  spot check    the sample is drawn by hash, re-derivably, only from items the draft and every repeat
                called not_relevant (where an agreed error would cost recall), and must then be decided;
  determinism   the same inputs give the same bytes, whatever order the repeats arrive in.

COLD. No repeat, label or catalogue file is read: every input is built below.

NOT A VACUOUS PASS. Each --mutate rewrites the scorer's SOURCE in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCORER = ROOT / "evals" / "score_feeds_triage.py"
R, N = "relevant", "not_relevant"

MUTATIONS = {
    "missing-excluded": ("    rel = {k for k in keys if labels[k] == RELEVANT}\n",
                         "    rel = {k for k in keys if labels[k] == RELEVANT and k in verdicts}\n"),
    "swap": ('            "recall": _ratio(tp, len(rel)), "precision": _ratio(tp, len(kept))}',
             '            "recall": _ratio(tp, len(kept)), "precision": _ratio(tp, len(rel))}'),
    "band-first": ('    return {"min": min(got), "max": max(got),', '    return {"min": got[0], "max": got[0],'),
    "zero-as-one": ("    return round(num / den, 3) if den else None\n", "    return round(num / den, 3) if den else 1.0\n"),
    "draft-labels": ('    out.update({k: d["decision"] for k, d in decided.items()})\n', "    pass\n"),
    "majority-dispute": ("    return sorted(k for k in draft if any(k in r and r[k] != draft[k] for r in runs))\n",
                         "    return sorted(k for k in draft if sum(k in r and r[k] != draft[k] for r in runs) * 2 "
                         "> len(runs))\n"),
    "unfinished-dispute": ("    return sorted(k for k in draft if any(k in r and r[k] != draft[k] for r in runs))\n",
                           "    return sorted(k for k in draft if any(r.get(k) != draft[k] for r in runs))\n"),
    "decide-anything": ('        if d["key"] not in asked or d.get("kind") != asked[d["key"]]:\n', "        if False:\n"),
    "spot-any-agreed": ('    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT)\n',
                        '    agreed_not_relevant = sorted(k for k in draft if k not in keys)\n'),
}


def load_scorer(mutation) -> types.ModuleType:
    source = SCORER.read_text(encoding="utf-8")
    if mutation:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, SCORER))
        source = source.replace(old, new)
    module = types.ModuleType("score_feeds_triage_under_test")
    module.__file__ = str(SCORER)
    exec(compile(source, str(SCORER), "exec"), module.__dict__)
    return module


# Ten items: o = ofsi, f = fincen, a = ofac.
KEYS = ["o1", "o2", "o3", "o4", "f1", "f2", "f3", "a1", "a2", "a3"]
DRAFT = dict(zip(KEYS, [R, N, N, R, R, R, R, N, N, R]))
REP = {
    "rep1": dict(zip(KEYS, [R, N, R, N, R, R, R, N, N, R])),                  # o3 kept, o4 missed
    "rep2": {k: v for k, v in zip(KEYS, [R, N, N, R, R, R, None, R, R, R]) if v},  # f3 unfinished; a1, a2 kept
    "rep3": dict(DRAFT),                                                        # agrees with the draft
}
DECISIONS = [{"key": "o3", "kind": "dispute", "decision": R}, {"key": "o4", "kind": "dispute", "decision": R},
             {"key": "a1", "kind": "dispute", "decision": N}, {"key": "a2", "kind": "dispute", "decision": N}]


def fixtures():
    catalogue = {"items": [{"key": k, "source": {"o": "ofsi", "f": "fincen", "a": "ofac"}[k[0]], "title": k,
                            "url": "https://x/%s" % k, "published": "2026-09-01"} for k in KEYS]}
    labels = {"labels": {k: {"label": v, "reason": "draft"} for k, v in DRAFT.items()}}
    repeats = {r: {"verdicts": {k: {"verdict": v} for k, v in vs.items()},
                   "sessions": [{"terminal_check": {"calls": 3, "unterminated": [], "duplicated": []},
                                 "cost_usd": 0.5}]} for r, vs in REP.items()}
    return catalogue, labels, repeats


def checks(sc) -> list:
    out = []
    catalogue, labels, repeats = fixtures()
    disputes = sc.disputes_doc(catalogue, labels, repeats)

    def attempt(fn):
        try:
            return fn(), None
        except Exception as exc:  # a mutation that raises must not stop the guard
            return None, "%s: %s" % (type(exc).__name__, exc)

    keys = sorted(c["key"] for c in disputes["cards"])
    out.append((keys == ["a1", "a2", "o3", "o4"],
                "disputed: every item where ANY repeat's verdict differs from the draft; f3, with no verdict, is not",
                keys))

    score, err = attempt(lambda: sc.build(catalogue, labels, disputes, DECISIONS, repeats))
    ov = (score or {}).get("overall", {})
    rep2 = ov.get("per_repeat", {}).get("rep2", {})
    out.append((err is None and {k: rep2.get(k) for k in ("tp", "fn", "fp", "tn")} == {"tp": 5, "fn": 2, "fp": 2, "tn": 1}
                and rep2.get("unfinished") == ["f3"] and rep2.get("recall") == 0.714 and rep2.get("precision") == 0.714,
                "rep2's counts by hand: tp 5, fn 2 (o3, and unfinished f3), fp 2, tn 1; recall 0.714, precision 0.714",
                err or {k: rep2.get(k) for k in ("tp", "fn", "fp", "tn", "recall", "precision")}))
    rep1 = ov.get("per_repeat", {}).get("rep1", {})
    out.append((rep1.get("recall") == 0.857 and rep1.get("precision") == 1.0,
                "rep1: recall 0.857 (6 of 7 relevant kept), precision 1.0 (6 of 6 kept relevant)",
                {k: rep1.get(k) for k in ("recall", "precision")}))
    out.append((rep2.get("relevant") == 7, "an unfinished relevant item stays in recall's denominator (7, not 6)",
                rep2.get("relevant")))
    out.append((ov.get("recall") == {"min": 0.714, "max": 0.857, "mean": 0.809, "n": 3}
                and ov.get("precision") == {"min": 0.714, "max": 1.0, "mean": 0.905, "n": 3},
                "the band is min, max and mean over all three repeats", {"recall": ov.get("recall"),
                                                                         "precision": ov.get("precision")}))
    out.append(((score or {}).get("labels", {}).get("changed_by_owner") == ["o3"]
                and (score or {}).get("labels", {}).get("relevant") == 7,
                "the owner's decision replaces the draft: o3 becomes relevant, 7 relevant in all",
                (score or {}).get("labels")))
    per = (score or {}).get("per_source", {})
    sums = {k: sum(per.get(s, {}).get("per_repeat", {}).get("rep2", {}).get(k, 0) for s in ("ofsi", "fincen", "ofac"))
            for k in ("tp", "fn", "fp", "tn")}
    out.append((sums == {k: rep2.get(k) for k in ("tp", "fn", "fp", "tn")},
                "the three sources' counts sum to the overall counts", sums))
    out.append(((score or {}).get("false_negatives") == {"f3": ["rep2"], "o3": ["rep2", "rep3"], "o4": ["rep1"]},
                "every relevant item a repeat did not keep is listed with the repeats that missed it",
                (score or {}).get("false_negatives")))

    none_rel = sc.score_one({"x": N}, {"x": N}, ["x"])
    out.append((none_rel["recall"] is None and none_rel["precision"] is None,
                "recall over no relevant items, and precision over none kept, are null (n/a)", none_rel))

    refusals = []
    for bad in ([{"key": "o1", "kind": "dispute", "decision": R}] + DECISIONS,
                DECISIONS + [dict(DECISIONS[0])], DECISIONS[:3]):
        refusals.append(attempt(lambda: sc.final_labels(labels, disputes, bad))[1] is not None)
    out.append((refusals == [True, True, True],
                "a decision on an undisputed item, a second decision, and an undecided dispute are each refused",
                refusals))

    pool = ["k%02d" % i for i in range(20)]
    spot = sc.spot_sample(pool, 3)
    with_spot = sc.disputes_doc(catalogue, labels, repeats, spot_check=2)
    spot_cards = sorted(c["key"] for c in with_spot["cards"] if c["kind"] == "spot_check")
    need = attempt(lambda: sc.final_labels(labels, with_spot, DECISIONS))[1]
    out.append((len(spot) == 3 and set(spot) <= set(pool) and spot == sc.spot_sample(list(reversed(pool)), 3)
                and spot_cards == ["o2"] and need is not None,
                "the spot check samples by hash, re-derivably, only items all four called not_relevant (here o2 "
                "alone), and a sampled item must then be decided", {"pool sample": spot, "cards": spot_cards}))

    shuffled = {r: repeats[r] for r in ("rep3", "rep1", "rep2")}
    again, _ = attempt(lambda: sc.render(sc.build(catalogue, labels, disputes, DECISIONS, shuffled)))
    out.append((score is not None and again == sc.render(score), "the same inputs give the same bytes", ""))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage scorer")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    sc = load_scorer(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(sc):
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
