"""
Pin fc-08's import of fc-10's advisory impact export (Stage566 K4b).

Usage:
    python evals/check_impact_import.py
    python evals/check_impact_import.py --mutate bad-rr-id          # a malformed re-review id; MUST fail
    python evals/check_impact_import.py --mutate orphan-rereview    # a re-review with no corroboration; MUST fail
    python evals/check_impact_import.py --mutate hash-drift         # source.sha256 is not a sha256; MUST fail
    python evals/check_impact_import.py --mutate not-deterministic  # output depends on export order; MUST fail
    python evals/check_impact_import.py --mutate drop-flags         # the import loses fc-10's flags; MUST fail
    python evals/check_impact_import.py --mutate orphan-flag        # a flag with no corroboration; MUST fail

COLD. Checks the committed data/advisory_impact.json and convert() over a synthetic export in a temporary
directory. Whether the import is CURRENT against fc-10's export is checked from fc-10's side
(tests/advisory_impact/test_fc08_impact_import_is_current.py, warm), because a guard here would need an fc-10
checkout that CI does not have -- the same split as the proposals import.
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
import import_fc10_impact as imp  # noqa: E402

MUTATIONS = ("bad-rr-id", "orphan-rereview", "hash-drift", "not-deterministic", "drop-flags", "orphan-flag")
FLG = re.compile(r"^FLG-\d+$")
MUTATION = None
RR = re.compile(r"^RR-\d+$")


def _corr(adv, publisher="OFAC"):
    return {"advisory_id": adv, "publisher": publisher, "published_on": "2026-10-01",
            "decided_at": "2026-10-02T09:00:00+00:00", "absorbed_at": "2026-10-15T17:30:00",
            "quotes": [{"page": 1, "quote": "A designated party owns the trading company."}]}


def _rr(rid, typology, status="open"):
    return {"id": rid, "case_id": "%s-X001" % typology, "subject": "Example Trading Ltd", "status": status,
            "outcome": "unchanged" if status == "closed" else "", "raised_at": "2026-10-15T17:30:00",
            "closed_at": "2026-10-20T09:00:00" if status == "closed" else ""}


def _synthetic() -> dict:
    return {"schema_version": "1.0", "head": {"event_count": 5, "event_hash": "b" * 64}, "typologies": {
        "SAN006": {"corroborations": [_corr("ADV-2026-0026")], "rereviews": [_rr("RR-2", "SAN006", "closed")]},
        "SAN001": {"corroborations": [_corr("ADV-2026-0013", "OFSI")], "rereviews": [_rr("RR-1", "SAN001")]}}}


def _flag(fid, status="approved"):
    return {"id": fid, "text": "Company incorporated shortly before its owner was designated",
            "advisory_id": "ADV-2026-0026", "quote": "A trading party owned by a designated person.", "page": 2,
            "status": status, "in_doctrine_commit": "c" * 40 if status == "in_doctrine" else ""}


def problems(doc: dict) -> list:
    out = []
    for typ, entry in doc.get("typologies", {}).items():
        fids = [f["id"] for f in entry.get("flags", [])]
        out += ["%s: malformed flag id %s" % (typ, i) for i in fids if not FLG.match(i)]
        if fids and not entry.get("corroborations"):
            out.append("%s: flags with no corroboration" % typ)
        ids = [r["id"] for r in entry.get("rereviews", [])]
        out += ["%s: malformed re-review id %s" % (typ, i) for i in ids if not RR.match(i)]
        if ids and not entry.get("corroborations"):
            out.append("%s: re-reviews with no corroboration" % typ)
        out += ["%s: %s carries no quote" % (typ, c.get("advisory_id")) for c in entry.get("corroborations", [])
                if not c.get("quotes")]
    src = doc.get("source", {})
    if not re.fullmatch(r"[0-9a-f]{64}", src.get("sha256", "")):
        out.append("source.sha256 missing")
    if not isinstance(src.get("event_count"), int):
        out.append("source.event_count is not an int")
    return out


def _reversed(src: dict) -> dict:
    flipped = copy.deepcopy(src)
    flipped["typologies"] = dict(reversed(list(flipped["typologies"].items())))
    for entry in flipped["typologies"].values():
        entry["corroborations"].reverse()
        entry["rereviews"].reverse()
    return flipped


def checks():
    committed = json.loads(imp.OUT.read_text(encoding="utf-8"))
    yield (problems(committed) == [] and bool(committed.get("typologies"))), "the committed import is well formed", \
        "%d typologies" % len(committed.get("typologies", {}))
    with tempfile.TemporaryDirectory() as d:
        src = _synthetic()
        src["typologies"]["SAN006"]["rereviews"].append(_rr("RR-3", "SAN006"))   # RR-2 then RR-3, plus SAN001's RR-1
        src["typologies"]["SAN006"]["rereviews"].reverse()                      # listed RR-3, RR-2
        src["typologies"]["SAN006"]["flags"] = [_flag("FLG-2", "in_doctrine"), _flag("FLG-1")]   # listed out of order
        if MUTATION == "bad-rr-id":
            src["typologies"]["SAN001"]["rereviews"][0]["id"] = "RR-x"
        a, b = Path(d) / "a.json", Path(d) / "b.json"
        a.write_text(json.dumps(src), encoding="utf-8")
        b.write_text(json.dumps(_reversed(src)), encoding="utf-8")
        try:
            out = imp.convert(a)
        except SystemExit as exc:
            yield False, "convert accepts a well-formed export", str(exc)
            return
        if MUTATION == "orphan-rereview":
            out["typologies"]["SAN001"]["corroborations"] = []
        if MUTATION == "hash-drift":
            out["source"]["sha256"] = "x"
        if MUTATION == "drop-flags":
            out["typologies"]["SAN006"].pop("flags", None)
        if MUTATION == "orphan-flag":
            out["typologies"]["SAN001"]["corroborations"] = []
            out["typologies"]["SAN001"]["flags"] = [_flag("FLG-3")]
        found = problems(out)
        yield found == [] and out["source"]["event_count"] == 5, "convert produces a well-formed import", \
            "; ".join(found) or "2 typologies, event_count 5"
        ids = [r["id"] for r in out["typologies"]["SAN006"]["rereviews"]]
        yield ids == ["RR-2", "RR-3"], "convert sorts re-reviews by number", ", ".join(ids)
        flags = out["typologies"]["SAN006"].get("flags", [])
        yield [(f["id"], f["status"]) for f in flags] == [("FLG-1", "approved"), ("FLG-2", "in_doctrine")], \
            "convert carries fc-10's flags unchanged, sorted by number", [f["id"] for f in flags]
        yield "flags" not in out["typologies"]["SAN001"], "a typology with no flag gets no flags key", ""
        other = imp.convert(b)
        if MUTATION == "not-deterministic":
            other["typologies"]["SAN006"]["rereviews"].reverse()
        yield out["typologies"] == other["typologies"], "convert is independent of export order", \
            ", ".join(sorted(out["typologies"]))
        orphan = copy.deepcopy(src)
        orphan["typologies"]["SAN001"]["corroborations"] = []
        c = Path(d) / "c.json"
        c.write_text(json.dumps(orphan), encoding="utf-8")
        try:
            imp.convert(c)
            refused = ""
        except SystemExit as exc:
            refused = str(exc)
        yield "SAN001" in refused, "convert refuses an orphan re-review", refused or "accepted it"
        orphan = copy.deepcopy(src)
        orphan["typologies"]["SAN001"] = {"corroborations": [], "rereviews": [], "flags": [_flag("FLG-9")]}
        c.write_text(json.dumps(orphan), encoding="utf-8")
        try:
            imp.convert(c)
            refused = ""
        except SystemExit as exc:
            refused = str(exc)
        yield "SAN001" in refused, "convert refuses a flag with no corroboration", refused or "accepted it"


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the advisory impact import")
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
