"""
Pin fc-08's import of fc-10's typology proposals (Stage565 S1).

Usage:
    python evals/check_proposals_import.py
    python evals/check_proposals_import.py --mutate bad-id             # a malformed proposal id; MUST fail
    python evals/check_proposals_import.py --mutate no-quotes          # evidence with no quote; MUST fail
    python evals/check_proposals_import.py --mutate count-drift        # source.proposal_count disagrees; MUST fail
    python evals/check_proposals_import.py --mutate not-deterministic  # output depends on export order; MUST fail

COLD. Checks the committed data/typology_proposals.json and convert() over a synthetic export in a
temporary directory. Whether the import is CURRENT against fc-10's export is checked from fc-10's
side (tests/typology_proposals/test_fc08_import_is_current.py, warm), because a guard here would need
an fc-10 checkout that CI does not have (plan ruling R5).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_fc10_proposals as imp  # noqa: E402

MUTATIONS = ("bad-id", "no-quotes", "count-drift", "not-deterministic")
MUTATION = None
ID = re.compile(r"^TP-\d{4}-\d{3}$")


def _synthetic() -> dict:
    ev = {"advisory_id": "ADV-2026-0003", "publisher": "FATF", "quotes": ["Underground banking is one tool."]}
    return {"schema_version": "1.0", "head": {"event_count": 2, "event_hash": "a" * 64}, "proposals": [
        {"proposal_id": "TP-2026-002", "working_name": "b", "family": "tbml", "stage": "open", "summary": "b",
         "evidence": [ev]},
        {"proposal_id": "TP-2026-001", "working_name": "a", "family": "sanctions", "stage": "corroborating",
         "summary": "a", "evidence": [ev, dict(ev, advisory_id="ADV-2026-0011")]}]}


def problems(doc: dict) -> list:
    out = []
    ids = [p["proposal_id"] for p in doc.get("proposals", [])]
    out += ["malformed id %s" % i for i in ids if not ID.match(i)]
    if len(ids) != len(set(ids)):
        out.append("duplicate proposal ids")
    for p in doc.get("proposals", []):
        if not p.get("evidence") or any(not e.get("quotes") for e in p["evidence"]):
            out.append("%s carries evidence with no quote" % p["proposal_id"])
    if doc.get("source", {}).get("proposal_count") != len(ids):
        out.append("source.proposal_count %s != %d proposals" % (doc.get("source", {}).get("proposal_count"), len(ids)))
    if not re.fullmatch(r"[0-9a-f]{64}", doc.get("source", {}).get("sha256", "")):
        out.append("source.sha256 missing")
    return out


def checks():
    committed = json.loads(imp.OUT.read_text(encoding="utf-8"))
    yield problems(committed) == [], "the committed import is well formed", "%d proposals" % len(committed["proposals"])
    with tempfile.TemporaryDirectory() as d:
        src = _synthetic()
        if MUTATION == "bad-id":
            src["proposals"][0]["proposal_id"] = "TP-26-2"
        if MUTATION == "no-quotes":
            src["proposals"][0]["evidence"][0]["quotes"] = []
        a, b = Path(d) / "a.json", Path(d) / "b.json"
        a.write_text(json.dumps(src), encoding="utf-8")
        flipped = copy.deepcopy(src)
        flipped["proposals"].reverse()
        b.write_text(json.dumps(flipped), encoding="utf-8")
        try:
            out = imp.convert(a)
        except SystemExit as exc:
            yield False, "convert accepts a well-formed export", str(exc)
            return
        if MUTATION == "count-drift":
            out["source"]["proposal_count"] += 1
        found = problems(out)
        yield found == [] and out["source"]["proposal_count"] == 2, "convert produces a well-formed import", \
            "; ".join(found) or "2 proposals"
        other = imp.convert(b)
        if MUTATION == "not-deterministic":
            other["proposals"].reverse()
        yield out["proposals"] == other["proposals"], "convert is independent of export order", \
            ", ".join(p["proposal_id"] for p in out["proposals"])


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the typology proposals import")
    ap.add_argument("--mutate", choices=MUTATIONS)
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect" if failures else "NOTHING PROVED"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
