"""
Import fc-10's advisory impact export (Stage566 K4b) for the scan page to show.

Usage:
    python tools/import_fc10_impact.py <path/to/fc-10/indexes/advisory_impact.json>

One way, like tools/import_fc10_proposals.py: fc-10 owns the ledger; this writes data/advisory_impact.json with
fc-10's commit and the sha256 of the file read. Deterministic, no timestamp. It does not re-verify the ledger's
hash chain -- that is fc-10's guarantee, checked where the log lives.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "advisory_impact.json"
RR_ID = re.compile(r"^RR-\d+$")


def _commit(path: Path) -> str:
    r = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def convert(path: Path) -> dict:
    raw = path.read_bytes()
    doc = json.loads(raw)
    typologies = {}
    for code in sorted(doc["typologies"]):
        entry = doc["typologies"][code]
        typologies[code] = {
            "corroborations": sorted(entry.get("corroborations") or [], key=lambda c: c["advisory_id"]),
            "rereviews": entry.get("rereviews") or [],
        }
    bad = sorted(r["id"] for t in typologies.values() for r in t["rereviews"] if not RR_ID.match(r["id"]))
    if bad:
        raise SystemExit("not re-review ids: %s" % bad)
    orphans = sorted(code for code, t in typologies.items() if t["rereviews"] and not t["corroborations"])
    if orphans:
        raise SystemExit("re-reviews with no corroboration: %s" % orphans)
    for t in typologies.values():
        t["rereviews"] = sorted(t["rereviews"], key=lambda r: int(r["id"][3:]))
    return {
        "version": "fc10-%s" % _commit(path),
        "source": {"repository": "fc-10-intelligence-repository-layer", "file": "indexes/advisory_impact.json",
                   "sha256": hashlib.sha256(raw).hexdigest(), "event_count": doc["head"]["event_count"]},
        "note": "Governed export from fc-10's advisory impact ledger. Regenerate with tools/import_fc10_impact.py; "
                "never hand-edit.",
        "typologies": typologies,
    }


def main(argv: list) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    path = Path(argv[0]).resolve()
    if not path.exists():
        print("not found: %s" % path, file=sys.stderr)
        return 2
    out = convert(path)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    ts = out["typologies"].values()
    print("Wrote advisory_impact.json: %d typologies, %d corroborations, %d re-reviews from %s (%s)"
          % (len(out["typologies"]), sum(len(t["corroborations"]) for t in ts),
             sum(len(t["rereviews"]) for t in ts), out["version"], out["source"]["sha256"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
