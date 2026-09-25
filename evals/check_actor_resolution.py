"""
Pin actor identity: exact matches resolve, similar names only suggest, the builder never
guesses between two parties, and a category never resolves.

Usage:
    python evals/check_actor_resolution.py
    python evals/check_actor_resolution.py --mutate containment    # suggestions resolve; MUST fail
    python evals/check_actor_resolution.py --mutate ambiguous      # builder merges into the first match; MUST fail
    python evals/check_actor_resolution.py --mutate same-advisory  # builder merges within one advisory; MUST fail
    python evals/check_actor_resolution.py --mutate category       # a category may resolve; MUST fail
    python evals/check_actor_resolution.py --mutate positional     # ids counted by position; MUST fail

WHY. Measured 2026-09-25 against the extractor's records: of five actors a containment
rule at 0.60 would have resolved, four were wrong -- "Iran" and "Islamic Republic of Iran"
to Islamic Republic of Iran Shipping Lines, "Syria" to the Iran-Syria oil procurement
network, "Company X" to National Iranian Oil Company.

OFFLINE. The REAL labels and records; the register is rebuilt in memory so the builder
mutations take effect. No model, no PDF.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals.actor_resolution import load_records, report  # noqa: E402
from schemas.actor_match import resolve  # noqa: E402
from tools.build_actor_register import build_register, load_labels  # noqa: E402

FLAGS = {"resolve": {}, "build": {}}
WITNESS = "Guard Witness Trading LLC"


def checks() -> list:
    out = []
    entries, candidates = build_register(load_labels(), **FLAGS["build"])
    by_name = {e["name"]: e for e in entries}

    merged = [e for e in entries if len({n["advisory_id"] for n in e["named_in"]}) > 1]
    out.append((len(merged) >= 1, "at least one real cross-advisory merge exists (not vacuous)",
                "; ".join("%s %s" % (e["name"], [n["advisory_id"] for n in e["named_in"]]) for e in merged)))

    got = resolve(["Iran"], "jurisdiction", entries, **FLAGS["resolve"])
    out.append((got["status"] != "resolved",
                '"Iran" does NOT resolve (containment would name Islamic Republic of Iran Shipping Lines)', str(got)))
    got = resolve(["Syria"], "jurisdiction", entries, **FLAGS["resolve"])
    out.append((got["status"] != "resolved", '"Syria" does NOT resolve', str(got)))

    got = resolve(["Milandr"], "organisation", entries, **FLAGS["resolve"])
    out.append((got["status"] == "resolved" and got["name"] == "AO PKK Milandr",
                "an exact ALIAS resolves: Milandr -> AO PKK Milandr (not vacuous)", str(got)))

    irgc = by_name.get("Islamic Revolutionary Guard Corps", {})
    out.append(([n["advisory_id"] for n in irgc.get("named_in", [])] == ["ADV-2026-0010"],
                "the IRGC entry holds ADV-2026-0010 only: 0012's conflated IRGC-Qods Force was not merged into it",
                str(irgc.get("named_in"))))
    amb = [c for c in candidates if c["reason"] == "ambiguous" and c["advisory_id"] == "ADV-2026-0012"]
    out.append((len(amb) == 1, "the candidates list ADV-2026-0012's IRGC-Qods Force as ambiguous", str(amb)))
    got = resolve(["IRGC"], "organisation", entries, **FLAGS["resolve"])
    out.append((got["status"] == "ambiguous", '"IRGC" is AMBIGUOUS while the 0012 label conflates two parties',
                str(got)))

    witness = [{"advisory_id": "ADV-9999-0001", "actors": [
        {"name": "Alpha Trading LLC", "actor_type": "organisation", "aliases": ["Alpha"]},
        {"name": "Alpha Shipping LLC", "actor_type": "organisation", "aliases": ["Alpha"]}]}]
    w_entries, w_cand = build_register(witness, **FLAGS["build"])
    out.append((len(w_entries) == 2 and any(c["reason"] == "same advisory" for c in w_cand),
                "two actors of ONE advisory sharing an alias stay two entries, listed 'same advisory'",
                "%d entries, reasons %s" % (len(w_entries), sorted({c["reason"] for c in w_cand}))))

    got = resolve(["AO PKK Milandr"], "category", entries, **FLAGS["resolve"])
    out.append((got["status"] == "category", "a category never resolves, even on an exact name", str(got)))

    # The 105/55 figure in the plan's narration was a pre-plan measurement that (unlike
    # RECORD_NAME's `^ADV-\d{4}-\d{4}\.json$`) also swept up ADV-2026-0001's two superseded
    # schema-variant siblings (ADV-2026-0001.schema-1.0.0.json, .week1-schema-1.1.0.json),
    # effectively counting that one advisory three times. Measured directly against
    # evals.actor_resolution.load_records() (which applies RECORD_NAME correctly): 102
    # named, 52 categories. Adjusted here per the plan's own rule for a false assumption
    # -- fix the CHECK, never the rules -- and recorded in the task report.
    rep = report(load_records(), entries, **FLAGS["resolve"])
    out.append((rep["named"] == 102 and rep["categories"] == 52 and rep["resolved"] > 0,
                "the measurement reads 102 named actors and 52 categories, and resolves some",
                "named %d, categories %d, resolved %d" % (rep["named"], rep["categories"], rep["resolved"])))
    wrong = [s["name"] for s in rep["suggestions"] if s["name"] in ("Iran", "Syria", "Company X")]
    out.append((len(wrong) >= 1, "known wrong containment matches appear as SUGGESTIONS, not resolutions", str(wrong)))

    # Order-independence witness (controller ruling, Task 4 review, carried into Task 6).
    # ADV-9001 names "Acme Corp" (alias "Acme"); ADV-9002 names "Acme" (alias "Acme
    # Holdings") and merges into it via the shared "acme" key; ADV-9003 names TWO actors,
    # "Other Co" (alias "Acme Holdings") and "Acme Holdings" itself, which must be blocked
    # from each other AND from reaching "Acme Corp" transitively through the shared
    # "Acme Holdings" key -- and blocked the same way regardless of which of the two is
    # labelled first within ADV-9003.
    order_x_y = [
        {"advisory_id": "ADV-9001", "actors": [
            {"name": "Acme Corp", "actor_type": "organisation", "aliases": ["Acme"]}]},
        {"advisory_id": "ADV-9002", "actors": [
            {"name": "Acme", "actor_type": "organisation", "aliases": ["Acme Holdings"]}]},
        {"advisory_id": "ADV-9003", "actors": [
            {"name": "Other Co", "actor_type": "organisation", "aliases": ["Acme Holdings"]},
            {"name": "Acme Holdings", "actor_type": "organisation", "aliases": []}]},
    ]
    order_y_x = [order_x_y[0], order_x_y[1],
                 {"advisory_id": "ADV-9003", "actors": list(reversed(order_x_y[2]["actors"]))}]

    def _acme_corp_is_clean(labels) -> tuple:
        o_entries, o_cand = build_register(labels, **FLAGS["build"])
        acme_corp = next((e for e in o_entries if e["name"] == "Acme Corp"), None)
        if acme_corp is None:
            return False, "no 'Acme Corp' entry"
        named_other_co = any(n["name_as_labelled"] == "Other Co" for n in acme_corp["named_in"])
        alias_other_co = "Other Co" in acme_corp["aliases"]
        same_advisory_9003 = any(c["reason"] == "same advisory" and c["advisory_id"] == "ADV-9003"
                                  for c in o_cand)
        ok = (not named_other_co) and (not alias_other_co) and same_advisory_9003
        return ok, ("named_in=%s aliases=%s same-advisory-9003=%s"
                     % ([n["name_as_labelled"] for n in acme_corp["named_in"]], acme_corp["aliases"],
                        same_advisory_9003))

    ok_xy, detail_xy = _acme_corp_is_clean(order_x_y)
    ok_yx, detail_yx = _acme_corp_is_clean(order_y_x)
    out.append((ok_xy and ok_yx,
                "same-advisory is order-independent: 'Other Co' never merges into Acme Corp, in either label order",
                "[Other Co, Acme Holdings]: %s | [Acme Holdings, Other Co]: %s" % (detail_xy, detail_yx)))

    # Stable ids (final review F1). Insert an actor at the START of the first label: a
    # positional counter renumbers every later entry; a content id leaves them alone.
    labels = load_labels()
    inserted = copy.deepcopy(labels)
    inserted[0].setdefault("actors", []).insert(0, {"name": WITNESS, "actor_type": "organisation", "aliases": []})
    before = {(e["actor_id"], e["name"]) for e in entries}
    i_entries, _ = build_register(inserted, **FLAGS["build"])
    after = {(e["actor_id"], e["name"]) for e in i_entries if e["name"] != WITNESS}
    moved = sorted(before - after)
    out.append((len(i_entries) == len(entries) + 1 and after == before,
                "inserting an actor into an early advisory leaves every other id unchanged",
                "witness in %s; %d of %d original (id, name) pairs changed%s"
                % (inserted[0]["advisory_id"], len(moved), len(before), (", e.g. %s" % (moved[:2],)) if moved else "")))

    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin actor identity")
    ap.add_argument("--mutate", choices=("containment", "ambiguous", "same-advisory", "category", "positional"))
    args = ap.parse_args(argv)
    if args.mutate == "containment":
        FLAGS["resolve"] = {"suggestions_resolve": True}
    elif args.mutate == "category":
        FLAGS["resolve"] = {"allow_category": True}
    elif args.mutate == "ambiguous":
        FLAGS["build"] = {"merge_ambiguous": True}
    elif args.mutate == "same-advisory":
        FLAGS["build"] = {"merge_same_advisory": True}
    elif args.mutate == "positional":
        FLAGS["build"] = {"positional_ids": True}
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
