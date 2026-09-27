"""
Score the triage repeats against the labels: recall first, precision beside it, a band over the repeats.

Usage:
    python evals/score_feeds_triage.py                          # print the score; write nothing
    python evals/score_feeds_triage.py --write-disputes [--spot-check N]
                                                                # after the repeats: evals/feeds/disputes.json
    python evals/score_feeds_triage.py --check-disputes         # the committed disputes rebuild byte for byte
    python evals/score_feeds_triage.py --write                  # after the owner's decisions: evals/feeds/score.json
    python evals/score_feeds_triage.py --check                  # the committed score rebuilds byte for byte

THE LABEL of an item is Claude's draft (evals/feeds/labels.json, committed before the first repeat)
unless the owner decided it (evals/owner_decisions/feeds_triage_labels_*.json). The owner decides the
DISPUTES -- items where at least one repeat's verdict differs from the draft -- and the spot-check
sample, if disputes.json names one. The sample is drawn from the items the draft AND every repeat
called not_relevant: that is the only place an agreed error costs recall (a relevant publication all
four missed), and recall is the score that comes first. Every disputed or sampled item must be decided
exactly once, and nothing else may be: a decision on an item nobody disputed is refused. An item where
the draft and every repeat agree, and which was not sampled, is UNCHALLENGED, not confirmed.

THE SCORE, per repeat, over every scored catalogue item:
  kept       the items the repeat triaged relevant. An item with NO verdict is not kept: the run left
             it unfinished, and a relevant item left unfinished is a miss (spec section 1: whatever the
             agent skipped is reported as unfinished, never as success). Unfinished items are listed.
  recall     kept and relevant / relevant   -- first: a relevant publication missed is lost to the desk
  precision  kept and relevant / kept       -- beside it: an irrelevant one kept costs a reviewer a minute
  n/a        a ratio whose denominator is zero is null, never 0 or 1.
A band is the min, max and mean of a ratio over the repeats, overall and per source. Counts are exact
and ratios are rounded to 3 places; a band's mean is the mean of the three ratios as printed, so every
figure in score.json can be re-derived by hand from the counts beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.triage import NOT_RELEVANT, RELEVANT, VERDICTS  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
LABELS = EVAL_DIR / "labels.json"
REPEATS_DIR = EVAL_DIR / "repeats"
DISPUTES = EVAL_DIR / "disputes.json"
SCORE = EVAL_DIR / "score.json"
DECISIONS_DIR = ROOT / "evals" / "owner_decisions"
DECISIONS_GLOB = "feeds_triage_labels_*.json"
REPEATS = ("rep1", "rep2", "rep3")
SOURCES = ("ofsi", "fincen", "ofac")
SPOT_SEED = "fc08-slice2-triage-spot-check"


def render(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verdicts_of(repeat: dict) -> Dict[str, str]:
    return {k: v["verdict"] for k, v in repeat["verdicts"].items()}


def disputed(draft: Dict[str, str], runs: Sequence[Dict[str, str]]) -> List[str]:
    """Items where at least one repeat GAVE a verdict that differs from the draft. No verdict is no dispute."""
    return sorted(k for k in draft if any(k in r and r[k] != draft[k] for r in runs))


def spot_sample(agreed: Sequence[str], n: int, seed: str = SPOT_SEED) -> List[str]:
    """n agreed items, chosen by hash rather than by a random generator, so the sample re-derives."""
    ranked = sorted(agreed, key=lambda k: hashlib.sha256((seed + k).encode("utf-8")).hexdigest())
    return sorted(ranked[:n])


def disputes_doc(catalogue: dict, labels: dict, repeats: Dict[str, dict], spot_check: int = 0) -> dict:
    draft = {k: v["label"] for k, v in labels["labels"].items()}
    runs = [verdicts_of(repeats[r]) for r in REPEATS]
    keys = disputed(draft, runs)
    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT)
    by_key = {it["key"]: it for it in catalogue["items"]}

    def card(k: str, kind: str) -> dict:
        it = by_key[k]
        return {"key": k, "kind": kind, "source": it["source"], "title": it["title"], "url": it["url"],
                "published": it["published"], "draft": labels["labels"][k],
                "repeats": {r: repeats[r]["verdicts"].get(k) for r in REPEATS}}

    return {"schema": "fc08-triage-disputes/1", "labels_sha256": hashlib.sha256(render(labels).encode()).hexdigest(),
            "repeats": list(REPEATS), "spot_check": {"n": spot_check, "seed": SPOT_SEED},
            "cards": [card(k, "dispute") for k in keys] + [card(k, "spot_check")
                                                          for k in spot_sample(agreed_not_relevant, spot_check)]}


def final_labels(labels: dict, disputes: dict, decisions: Sequence[dict]) -> Dict[str, str]:
    """The draft, overridden by the owner's decision on each disputed or sampled item. Raises ValueError."""
    out = {k: v["label"] for k, v in labels["labels"].items()}
    asked = {c["key"]: c["kind"] for c in disputes["cards"]}
    decided: Dict[str, dict] = {}
    for d in decisions:
        if d["key"] not in asked or d.get("kind") != asked[d["key"]]:
            raise ValueError("%s was not put to the owner as a %s" % (d["key"], d.get("kind")))
        if d["key"] in decided:
            raise ValueError("%s is decided twice" % d["key"])
        if d["decision"] not in VERDICTS:
            raise ValueError("%s: decision %r is not one of %s" % (d["key"], d["decision"], VERDICTS))
        decided[d["key"]] = d
    undecided = sorted(set(asked) - set(decided))
    if undecided:
        raise ValueError("undecided: %s" % ", ".join(undecided))
    out.update({k: d["decision"] for k, d in decided.items()})
    return out


def _ratio(num: int, den: int) -> Optional[float]:
    return round(num / den, 3) if den else None


def score_one(verdicts: Dict[str, str], labels: Dict[str, str], keys: Sequence[str]) -> dict:
    kept = {k for k in keys if verdicts.get(k) == RELEVANT}
    rel = {k for k in keys if labels[k] == RELEVANT}
    tp, fn, fp = len(kept & rel), len(rel - kept), len(kept - rel)
    return {"items": len(keys), "relevant": len(rel), "kept": len(kept), "tp": tp, "fn": fn, "fp": fp,
            "tn": len(keys) - tp - fn - fp, "unfinished": sorted(k for k in keys if k not in verdicts),
            "recall": _ratio(tp, len(rel)), "precision": _ratio(tp, len(kept))}


def band(values: Sequence[Optional[float]]) -> Optional[dict]:
    got = [v for v in values if v is not None]
    if not got:
        return None
    return {"min": min(got), "max": max(got), "mean": round(sum(got) / len(got), 3), "n": len(got)}


def build(catalogue: dict, labels: dict, disputes: dict, decisions: Sequence[dict], repeats: Dict[str, dict],
          decision_files: Sequence[str] = ()) -> dict:
    final = final_labels(labels, disputes, decisions)
    keys = sorted(it["key"] for it in catalogue["items"])
    src = {it["key"]: it["source"] for it in catalogue["items"]}
    runs = {r: verdicts_of(repeats[r]) for r in REPEATS}

    def section(ks: List[str]) -> dict:
        per = {r: score_one(runs[r], final, ks) for r in REPEATS}
        return {"per_repeat": per, "recall": band([per[r]["recall"] for r in REPEATS]),
                "precision": band([per[r]["precision"] for r in REPEATS])}

    sessions = [s for r in REPEATS for s in repeats[r]["sessions"]]
    return {
        "schema": "fc08-triage-score/1",
        "inputs": {"catalogue_sha256": hashlib.sha256(render(catalogue).encode()).hexdigest(),
                   "labels_sha256": hashlib.sha256(render(labels).encode()).hexdigest(),
                   "decision_files": sorted(decision_files), "repeats": list(REPEATS)},
        "labels": {"items": len(keys), "relevant": sum(1 for k in keys if final[k] == RELEVANT),
                   "not_relevant": sum(1 for k in keys if final[k] == NOT_RELEVANT),
                   "owner_decided": len(decisions), "unchallenged": len(keys) - len(disputes["cards"]),
                   "changed_by_owner": sorted(d["key"] for d in decisions
                                              if d["decision"] != labels["labels"][d["key"]]["label"])},
        "overall": section(keys),
        "per_source": {s: section([k for k in keys if src[k] == s]) for s in SOURCES},
        "false_negatives": {k: [r for r in REPEATS if runs[r].get(k) != RELEVANT]
                            for k in keys if final[k] == RELEVANT and any(runs[r].get(k) != RELEVANT for r in REPEATS)},
        "unanimous": sum(1 for k in keys if len({runs[r].get(k) for r in REPEATS}) == 1),
        "sessions": {"count": len(sessions),
                     "terminal_check_clean": sum(1 for s in sessions if not s["terminal_check"]["unterminated"]
                                                 and not s["terminal_check"]["duplicated"]),
                     "cost_usd": round(sum(s.get("cost_usd") or 0 for s in sessions), 2)},
    }


def load_inputs() -> tuple:
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731
    repeats = {r: load(REPEATS_DIR / ("%s.json" % r)) for r in REPEATS}
    files = sorted(DECISIONS_DIR.glob(DECISIONS_GLOB))
    decisions = [d for f in files for d in load(f)["decisions"]]
    disputes = load(DISPUTES) if DISPUTES.exists() else None
    return load(CATALOGUE), load(LABELS), disputes, decisions, repeats, [str(f.relative_to(ROOT)) for f in files]


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Score the triage repeats")
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--write-disputes", "--check-disputes", "--write", "--check"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--spot-check", type=int, default=0, help="with --write-disputes: sample N agreed items")
    args = ap.parse_args(argv)
    catalogue, labels, disputes, decisions, repeats, files = load_inputs()
    if args.write_disputes or args.check_disputes:
        n = args.spot_check if args.write_disputes else (disputes or {}).get("spot_check", {}).get("n", 0)
        text = render(disputes_doc(catalogue, labels, repeats, n))
        if args.check_disputes:
            ok = DISPUTES.exists() and DISPUTES.read_text(encoding="utf-8") == text
            print("HOLDS: disputes.json rebuilds" if ok else "REFUSED: disputes.json does not rebuild")
            return 0 if ok else 1
        if DISPUTES.exists():
            print("REFUSED: %s exists; it is the question put to the owner and is never rewritten" % DISPUTES.name)
            return 1
        DISPUTES.write_text(text, encoding="utf-8")
        print("WROTE %s: %d card(s)" % (DISPUTES.relative_to(ROOT), len(json.loads(text)["cards"])))
        return 0
    if disputes is None:
        print("REFUSED: no disputes.json yet; run --write-disputes after the repeats")
        return 1
    try:
        text = render(build(catalogue, labels, disputes, decisions, repeats, files))
    except ValueError as exc:
        print("REFUSED: %s" % exc)
        return 1
    if args.check:
        ok = SCORE.exists() and SCORE.read_text(encoding="utf-8") == text
        print("HOLDS: score.json rebuilds from the committed repeats" if ok else "REFUSED: score.json does not rebuild")
        return 0 if ok else 1
    if args.write:
        SCORE.write_text(text, encoding="utf-8")
        print("WROTE %s" % SCORE.relative_to(ROOT))
    s = json.loads(text)
    for name, sec in [("overall", s["overall"])] + sorted(s["per_source"].items()):
        fmt = lambda b: "n/a" if b is None else "%.3f-%.3f (mean %.3f)" % (b["min"], b["max"], b["mean"])  # noqa: E731
        print("  %-8s recall %-26s precision %s" % (name, fmt(sec["recall"]), fmt(sec["precision"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
