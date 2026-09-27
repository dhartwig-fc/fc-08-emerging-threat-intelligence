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
    python evals/check_feeds_score.py --mutate edited-repeat       # a committed repeat's verdict edited in memory
    python evals/check_feeds_score.py --mutate edited-labels       # a draft label edited after the repeats ran
    python evals/check_feeds_score.py --mutate unfinished-in-stratum  # an item a repeat left unfinished re-enters the stratum
    python evals/check_feeds_score.py --mutate sample-sorted       # the spot sample is sorted(agreed), not hash-ranked

WHAT IT HOLDS, on a synthetic set whose every figure was computed by hand (ten items, three sources,
three repeats, four disputes, four owner decisions):
  the counts    tp, fn, fp, tn and the unfinished list of one repeat, and its recall and precision;
  unfinished    a relevant item with no verdict is a miss: it stays in recall's denominator; an item
                every repeat left unfinished is not "unanimous" either;
  the band      min, max and mean over all three repeats, for recall and for precision;
  n/a           a ratio over an empty denominator is null, never 0 or 1;
  disputes      an item is disputed when ANY repeat's verdict differs from the draft, one of three is
                enough, and an item with no verdict is not disputed;
  decisions     the owner's decision replaces the draft; a decision on an undisputed item, a second
                decision, an undecided dispute, and a decision missing its own 'decision' key are each
                refused with REFUSED text, never a bare traceback;
  spot check    the sample is drawn by hash, re-derivably, only from items the draft AND EVERY repeat
                explicitly called not_relevant -- a repeat that dropped or left the item unfinished is
                excluded, not counted as agreement (ruling 10) -- and must then be decided; the CONCRETE
                sample is pinned here against an independently re-derived hash ranking, not just its size;
  provenance    the *_sha256 fields carry whatever the caller passes in (the real file hash, in the CLI);
                nothing here silently re-derives its own hash from the parsed object;
  sources       a catalogue item whose source is not in SOURCES is refused, so a per-source sum can
                never silently fall short of the overall figure;
  determinism   the same inputs give the same bytes on a second call.

AND ON THE COMMITTED EVIDENCE (added in Task 9, with the files it reads):
  reproducible  evals/feeds/score.json is exactly what the scorer builds from the committed catalogue,
                draft labels, three repeats and owner decisions, and disputes.json exactly what was put
                to the owner -- so the committed band cannot drift from the records behind it;
  one arm       the three repeats share one prompt, model, budget and turn cap, name the committed
                catalogue by sha256, and name the draft labels as they are NOW (drafted before the
                repeats and unchanged since);
  coverage      each repeat's sessions cover every scored item exactly once, and every verdict carries
                its verified quote and the pages it was found on;
  decisions     each decision file is dated in its name and its body, each decision timestamped.

COLD. The synthetic checks read nothing; the committed checks read tracked files only.

NOT A VACUOUS PASS. Each --mutate rewrites the scorer's SOURCE in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCORER = ROOT / "evals" / "score_feeds_triage.py"
R, N = "relevant", "not_relevant"
# Independently derived, not imported from the scorer under test: the guard must pin the concrete
# spot-check sample against its OWN hash ranking, not the module's.
SPOT_SEED = "fc08-slice2-triage-spot-check"

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
    "decide-anything": ('        if key not in asked or d.get("kind") != asked[key]:\n', "        if False:\n"),
    "spot-any-agreed": ('    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT\n'
                        '                                  and all(r.get(k) == NOT_RELEVANT for r in runs))\n',
                        '    agreed_not_relevant = sorted(k for k in draft if k not in keys)\n'),
    "unfinished-in-stratum": ('    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT\n'
                              '                                  and all(r.get(k) == NOT_RELEVANT for r in runs))\n',
                              '    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT)\n'),
    "sample-sorted": ('    ranked = sorted(agreed, key=lambda k: hashlib.sha256((seed + k).encode("utf-8")).hexdigest())\n',
                      "    ranked = sorted(agreed)\n"),
}
DATA_MUTATIONS = ("edited-repeat", "edited-labels")  # applied to the loaded evidence, not to the scorer


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


def _one_item_fixture(key: str, source: str, label: str, repeat_verdicts: dict) -> tuple:
    """A single catalogue item, its label, and named repeats' verdicts for it (a repeat absent from
    repeat_verdicts left it unfinished). No sessions, since sessions play no part in these checks."""
    catalogue = {"items": [{"key": key, "source": source, "title": key, "url": "https://x/%s" % key,
                            "published": "2026-09-01"}]}
    labels = {"labels": {key: {"label": label, "reason": "draft"}}}
    repeats = {r: {"verdicts": ({key: {"verdict": repeat_verdicts[r]}} if r in repeat_verdicts else {}),
                   "sessions": []} for r in ("rep1", "rep2", "rep3")}
    return catalogue, labels, repeats


def unfinished_stratum_fixture() -> tuple:
    """u1: draft not_relevant, rep1 and rep3 agree, rep2 never triaged it (dropped/unfinished)."""
    return _one_item_fixture("u1", "ofsi", N, {"rep1": N, "rep3": N})


def unanimous_unfinished_fixture() -> tuple:
    """z1: draft not_relevant, no repeat gave it any verdict at all."""
    return _one_item_fixture("z1", "ofsi", N, {})


def bad_source_fixture() -> tuple:
    """q1: a catalogue source outside SOURCES."""
    return _one_item_fixture("q1", "unknownsrc", N, {})


def hash_sample_fixture() -> tuple:
    """Four agreed not_relevant items across two sources, chosen so hash order and sorted(agreed) diverge
    (checked below), for pinning the spot sample against an independently re-derived hash ranking."""
    keys = ["ofsi:z9", "ofsi:z1", "fincen:m5", "fincen:m2"]
    catalogue = {"items": [{"key": k, "source": k.split(":")[0], "title": k, "url": "https://x/%s" % k,
                            "published": "2026-09-01"} for k in keys]}
    labels = {"labels": {k: {"label": N, "reason": "draft"} for k in keys}}
    repeats = {r: {"verdicts": {k: {"verdict": N} for k in keys}, "sessions": []}
               for r in ("rep1", "rep2", "rep3")}
    return catalogue, labels, repeats, keys


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
                and spot_cards == ["o2"] and with_spot["spot_check"]["n"] == 2
                and with_spot["spot_check"]["drawn"] == 1 and need is not None,
                "the spot check samples by hash, re-derivably, only items all four called not_relevant (here o2 "
                "alone), and a sampled item must then be decided; drawn (1) differs from requested n (2)",
                {"pool sample": spot, "cards": spot_cards, "spot_check": with_spot["spot_check"]}))

    # Ruling 10: an item a repeat left unfinished is excluded from the stratum even when the draft and
    # every OTHER repeat call it not_relevant, and the drawn count reflects what the stratum actually held.
    u_cat, u_labels, u_repeats = unfinished_stratum_fixture()
    u_disputes = sc.disputes_doc(u_cat, u_labels, u_repeats, spot_check=1)
    u_spot = sorted(c["key"] for c in u_disputes["cards"] if c["kind"] == "spot_check")
    out.append((u_spot == [] and u_disputes["spot_check"]["n"] == 1 and u_disputes["spot_check"]["drawn"] == 0,
                "an item a repeat left unfinished is excluded from the spot-check stratum, even though the "
                "draft and every OTHER repeat call it not_relevant; drawn (0) differs from requested n (1)",
                {"cards": u_spot, "spot_check": u_disputes["spot_check"]}))

    # The concrete sample is pinned against a hash ranking computed independently here, not just its size.
    h_cat, h_labels, h_repeats, h_keys = hash_sample_fixture()
    h_disputes = sc.disputes_doc(h_cat, h_labels, h_repeats, spot_check=2)
    h_spot = sorted(c["key"] for c in h_disputes["cards"] if c["kind"] == "spot_check")
    hash_ranked = sorted(h_keys, key=lambda k: hashlib.sha256((SPOT_SEED + k).encode("utf-8")).hexdigest())
    expected_sample, sorted_would_give = sorted(hash_ranked[:2]), sorted(h_keys)[:2]
    out.append((h_spot == expected_sample and expected_sample != sorted_would_give,
                "the spot check draws the CONCRETE hash-ranked sample -- re-derived independently here, not "
                "copied from the scorer -- and for these four keys across two sources that differs from "
                "sorted(agreed), which would draw the whole sample from one source",
                {"got": h_spot, "expected (hash)": expected_sample, "sorted(agreed) would give": sorted_would_give}))

    neg_err = attempt(lambda: sc.spot_sample(["x"], -1))[1]
    out.append((neg_err is not None, "a negative spot-check sample size is refused", neg_err))

    # An item every repeat left unfinished is not unanimous: {None} is not agreement.
    uni_cat, uni_labels, uni_repeats = unanimous_unfinished_fixture()
    uni_disputes = sc.disputes_doc(uni_cat, uni_labels, uni_repeats)
    uni_score, uni_err = attempt(lambda: sc.build(uni_cat, uni_labels, uni_disputes, [], uni_repeats))
    out.append((uni_err is None and (uni_score or {}).get("unanimous") == 0,
                "an item every repeat left unfinished is not counted as unanimous",
                uni_err or (uni_score or {}).get("unanimous")))

    # A catalogue source outside SOURCES is refused, so per-source sums can never silently fall short.
    bad_cat, bad_labels, bad_repeats = bad_source_fixture()
    bad_disputes = sc.disputes_doc(bad_cat, bad_labels, bad_repeats)
    bad_source_err = attempt(lambda: sc.build(bad_cat, bad_labels, bad_disputes, [], bad_repeats))[1]
    out.append((bad_source_err is not None,
                "a catalogue item whose source is not in SOURCES is refused", bad_source_err))

    # *_sha256 fields carry exactly what the caller passes (the real file hash, in the CLI) -- nothing
    # here silently re-derives its own hash from the parsed object, so there is one rule and no dead helper.
    prov_score, prov_err = attempt(lambda: sc.build(catalogue, labels, disputes, DECISIONS, repeats,
                                                     catalogue_sha256="cafebabe", labels_sha256="deadbeef"))
    prov_inputs = (prov_score or {}).get("inputs", {})
    out.append((prov_err is None and prov_inputs.get("catalogue_sha256") == "cafebabe"
                and prov_inputs.get("labels_sha256") == "deadbeef",
                "the score's *_sha256 fields carry exactly what the caller passes, never a re-derived hash",
                prov_inputs))
    disp_with_hash = sc.disputes_doc(catalogue, labels, repeats, labels_sha256="feedface")
    out.append((disp_with_hash.get("labels_sha256") == "feedface",
                "disputes_doc's labels_sha256 also carries exactly what the caller passes", disp_with_hash.get("labels_sha256")))

    # A decision missing its own 'decision' key, or a catalogue item with no matching label, is refused
    # with REFUSED text -- never a bare KeyError traceback.
    missing_field_err = attempt(lambda: sc.final_labels(labels, disputes, [{"key": "o3", "kind": "dispute"}]))[1]
    out.append((missing_field_err is not None and not missing_field_err.startswith("KeyError"),
                "a decision missing its own 'decision' key is refused with a clear message, not a bare KeyError",
                missing_field_err))
    orphan_cat = {"items": catalogue["items"] + [{"key": "zzz9", "source": "ofsi", "title": "zzz9",
                                                  "url": "https://x/zzz9", "published": "2026-09-01"}]}
    mismatch_err = attempt(lambda: sc.build(orphan_cat, labels, disputes, DECISIONS, repeats))[1]
    out.append((mismatch_err is not None and not mismatch_err.startswith("KeyError"),
                "a catalogue item with no matching label is refused with a clear message, not a bare KeyError",
                mismatch_err))

    # Determinism: render(build(...)) reproduces byte for byte on a second call with identical inputs.
    # An input-reordering variant of this check (shuffling the `repeats` dict's key order) was removed:
    # build() reads repeats only through the fixed REPEATS tuple, and every list-derived key is sorted()
    # before use, so no caller-supplied ordering can ever reach the output -- reordering inputs here could
    # never fail. A genuine loss of a sorted() call would already break one of the numeric checks above.
    again, _ = attempt(lambda: sc.render(sc.build(catalogue, labels, disputes, DECISIONS, repeats)))
    out.append((score is not None and again == sc.render(score), "the same inputs give the same bytes on a second call", ""))
    return out


def committed_checks(sc, mutation) -> list:
    """The committed evidence: the band and the disputes rebuild, and the repeats are one arm."""
    import json
    import re
    out = []
    catalogue, labels, disputes, decisions, repeats, files = sc.load_inputs()
    if mutation == "edited-repeat":
        key = sorted(repeats["rep1"]["verdicts"])[0]
        v = repeats["rep1"]["verdicts"][key]
        v["verdict"] = sc.NOT_RELEVANT if v["verdict"] == sc.RELEVANT else sc.RELEVANT
    if mutation == "edited-labels":
        labels["labels"][sorted(labels["labels"])[0]]["reason"] += " (edited after the repeats)"
    # score.json and disputes.json each carry the real file hashes (as the CLI computes them with
    # sha256_file); the rebuild must supply the same hashes or a byte-for-byte comparison could never
    # hold even on unmutated evidence. Computed here, once, from the (possibly mutated) loaded objects.
    cat_sha = hashlib.sha256(sc.CATALOGUE.read_bytes()).hexdigest()
    lab_sha = hashlib.sha256(sc.render(labels).encode("utf-8")).hexdigest()
    try:
        text, err = sc.render(sc.build(catalogue, labels, disputes, decisions, repeats, files,
                                       catalogue_sha256=cat_sha, labels_sha256=lab_sha)), None
    except Exception as exc:
        text, err = None, "%s: %s" % (type(exc).__name__, exc)
    out.append((text is not None and sc.SCORE.read_text(encoding="utf-8") == text,
                "the committed score.json is exactly what the scorer builds from the committed evidence",
                err or "score.json %s" % ("matches" if text == sc.SCORE.read_text(encoding="utf-8") else "DIFFERS")))
    rebuilt = sc.render(sc.disputes_doc(catalogue, labels, repeats, disputes["spot_check"]["n"], labels_sha256=lab_sha))
    out.append((sc.DISPUTES.read_text(encoding="utf-8") == rebuilt,
                "disputes.json is exactly the question the evidence poses (%d cards)" % len(disputes["cards"]), ""))
    arm = {r: tuple(repeats[r].get(k) for k in ("prompt_sha256", "model", "max_budget_usd", "max_turns"))
           for r in sc.REPEATS}
    out.append((len(set(arm.values())) == 1 and all(repeats[r].get("schema") == "fc08-triage-repeat/1"
                                                    and repeats[r].get("repeat") == r
                                                    and repeats[r].get("catalogue_sha256") == cat_sha
                                                    and repeats[r].get("labels_draft_sha256") == lab_sha
                                                    for r in sc.REPEATS),
                "the three repeats are one arm over the committed catalogue and the unchanged draft labels",
                {r: repeats[r].get("labels_draft_sha256", "")[:12] for r in sc.REPEATS}))
    keys = sorted(it["key"] for it in catalogue["items"])
    covered = {r: sorted(k for s in repeats[r]["sessions"] for k in s["keys"]) for r in sc.REPEATS}
    quoted = all(v.get("quote") and v.get("found_on") and set(v) >= {"verdict", "reason", "run_id"}
                 and k in keys for r in sc.REPEATS for k, v in repeats[r]["verdicts"].items())
    out.append((all(c == keys for c in covered.values()) and quoted,
                "each repeat's sessions cover every scored item exactly once; every verdict carries its quote",
                {r: len(c) for r, c in covered.items()}))
    dated = all(re.fullmatch(r"evals/owner_decisions/feeds_triage_labels_(\d{4}-\d{2}-\d{2})\.json", f)
                and json.loads((sc.ROOT / f).read_text(encoding="utf-8"))["date"] == f[-15:-5] for f in files)
    out.append((files and dated and all(d.get("decided_at") for d in decisions),
                "each owner decision file is dated in its name and body, and each decision is timestamped", files))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage scorer")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS) + list(DATA_MUTATIONS),
                    help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    sc = load_scorer(args.mutate if args.mutate in MUTATIONS else None)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(sc) + committed_checks(sc, args.mutate):
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
