"""
How many of the extractor's named actors resolve to the governed register.

Usage:
    python evals/actor_resolution.py            # print the summary and write evals/actor_resolution.json
    python evals/actor_resolution.py --check    # fail if the committed report differs from a fresh one

The register is built from the golden LABELS; this reads the EXTRACTOR's records
(data/records/), so the measurement is not circular. Categories are counted apart and
never in the denominator: a class of actor cannot name a party. Suggestions are listed
so a reader can see what a similarity rule WOULD have claimed -- measured 2026-09-25,
mostly wrongly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.actor_match import resolve, variants_of  # noqa: E402
from tools.build_actor_register import load_register  # noqa: E402

RECORDS = ROOT / "data" / "records"
REPORT = ROOT / "evals" / "actor_resolution.json"
RECORD_NAME = re.compile(r"^ADV-\d{4}-\d{4}\.json$")


def load_records(records_dir: Path = RECORDS) -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(records_dir.iterdir())
            if RECORD_NAME.match(p.name)]


def report(records, register, **flags) -> dict:
    out = {"named": 0, "resolved": 0, "ambiguous": 0, "unresolved": 0, "unresolved_with_suggestions": 0,
           "categories": 0, "per_advisory": {}, "ambiguous_actors": [], "suggestions": []}
    for rec in sorted(records, key=lambda r: r["advisory_id"]):
        aid = rec["advisory_id"]
        per = out["per_advisory"].setdefault(aid, {"named": 0, "resolved": 0})
        for a in rec.get("actors", []):
            got = resolve(variants_of(a), a.get("actor_type"), register, **flags)
            if got["status"] == "category":
                out["categories"] += 1
                continue
            out["named"] += 1
            per["named"] += 1
            if got["status"] == "resolved":
                out["resolved"] += 1
                per["resolved"] += 1
            elif got["status"] == "ambiguous":
                out["ambiguous"] += 1
                out["ambiguous_actors"].append({"advisory_id": aid, "name": a["name"],
                                                "entries": [e["actor_id"] for e in got["entries"]]})
            else:
                out["unresolved"] += 1
                if got["suggestions"]:
                    out["unresolved_with_suggestions"] += 1
                    out["suggestions"].append({"advisory_id": aid, "name": a["name"],
                                               "suggestions": got["suggestions"]})
    return out


def _text(rep: dict) -> str:
    return json.dumps(rep, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Actor resolution over the extractor's records")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    rep = report(load_records(), load_register())
    if args.check:
        same = REPORT.exists() and REPORT.read_text(encoding="utf-8") == _text(rep)
        print("actor resolution matches the committed report" if same
              else "FAIL  actor resolution differs from the committed report")
        return 0 if same else 1
    REPORT.write_text(_text(rep), encoding="utf-8")
    print("named actors resolved: %d / %d (ambiguous %d, unresolved %d, of which %d have suggestions); "
          "categories %d, not counted" % (rep["resolved"], rep["named"], rep["ambiguous"], rep["unresolved"],
                                          rep["unresolved_with_suggestions"], rep["categories"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
