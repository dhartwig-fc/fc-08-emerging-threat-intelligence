"""
Import fc-10's typology proposals (Stage565 S1) for the agents to read.

Usage:
    python tools/import_fc10_proposals.py <path/to/fc-10/indexes/typology_proposals.json>

One way, like tools/import_fc10_doctrine.py: fc-10 owns the proposals; this writes
data/typology_proposals.json with fc-10's commit and the sha256 of the file read. Deterministic, no
timestamp. S2 makes the agents search it; S1 only imports it.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "typology_proposals.json"
PROPOSAL_ID = re.compile(r"^TP-\d{4}-\d{3}$")


def _commit(path: Path) -> str:
    r = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def convert(path: Path) -> dict:
    raw = path.read_bytes()
    doc = json.loads(raw)
    proposals = sorted(doc["proposals"], key=lambda p: p["proposal_id"])
    bad = [p["proposal_id"] for p in proposals if not PROPOSAL_ID.match(p["proposal_id"])]
    if bad:
        raise SystemExit("not proposal ids: %s" % bad)
    return {
        "version": "fc10-%s" % _commit(path),
        "source": {"repository": "fc-10-intelligence-repository-layer", "file": "indexes/typology_proposals.json",
                   "sha256": hashlib.sha256(raw).hexdigest(), "proposal_count": len(proposals)},
        "note": "Governed export from fc-10's typology proposal ledger. Regenerate with "
                "tools/import_fc10_proposals.py; never hand-edit.",
        "proposals": proposals,
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
    print("Wrote %s: %d proposals from %s (%s)" % (OUT.name, out["source"]["proposal_count"], out["version"],
                                                  out["source"]["sha256"][:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
