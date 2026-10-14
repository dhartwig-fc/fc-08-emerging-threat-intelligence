#!/usr/bin/env python3
"""Digests show open typology proposals (Stage565 S4, spec §7.3, plan R22-R24): on the desk of the proposal's
family (General intelligence when the family has no desk), with no heading when there are none; and a batch
pins the proposals import only when it holds one, so every committed batch rebuilds byte for byte.
Usage: .venv/bin/python evals/check_digest_proposals.py [--mutate LABEL]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import digest as dg  # noqa: E402
from governance.routing import ROUTING, load_routing  # noqa: E402

MUTATIONS = ("wrong-desk", "always-heading", "unpinned")
MUTATION = None
SAN = {"proposal_id": "TP-2026-001", "working_name": "Underground banking via ABP", "family": "sanctions",
       "stage": "corroborating", "summary": "", "evidence": [{"advisory_id": "ADV-2026-0003", "publisher": "FATF",
                                                               "quotes": ["q"], "citations": [{"page": 4, "quote": "q"}]}]}
CRYPTO = dict(SAN, proposal_id="TP-2026-002", working_name="Mixer laundering", family="crypto")


def _desk(desk, proposals):
    return dg.render_desk(desk, "b", [], 0, {}, load_routing(ROUTING), {}, {}, {}, open_proposals=proposals)


def checks():
    routing = load_routing(ROUTING)
    san = _desk("sanctions_desk", [SAN])
    yield dg.OPEN_PROPOSALS_HEADING in san and "TP-2026-001" in san and "Not a typology yet" in san, \
        "an open proposal is listed on its family's desk, marked as not a typology yet", ""
    yield "TP-2026-001" not in _desk("trade_desk", [SAN]), "it is not listed on another family's desk", ""
    yield dg.OPEN_PROPOSALS_HEADING in san and san.index(dg.OPEN_PROPOSALS_HEADING) < san.index(dg.NO_ADVISORIES), \
        "a desk with no advisories still shows its open proposals", ""
    yield "TP-2026-002" in _desk("general_intel", [CRYPTO]) and "TP-2026-002" not in _desk("sanctions_desk", [CRYPTO]), \
        "a proposal whose family has no desk goes to General intelligence (R23)", ""
    yield all(dg.OPEN_PROPOSALS_HEADING not in _desk(d, []) for d in routing["desk_titles"]), \
        "with no open proposals no desk gains the heading", ""

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        imp = d / "typology_proposals.json"
        imp.write_text(json.dumps({"proposals": []}), encoding="utf-8")

        def run(*args):
            return subprocess.run([sys.executable, str(ROOT / "tools" / "build_digests.py"), *args,
                                   "--out-dir", str(d / "digests"), "--typology-proposals", str(imp)],
                                  capture_output=True, text=True, cwd=ROOT)
        r = run("--batch-id", "empty-import")
        mpath = d / "digests" / "empty-import" / "manifest.json"
        man = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {"missing": True}
        yield r.returncode == 0 and "typology_proposals" not in man and "missing" not in man, \
            "a batch built with an empty import pins nothing new (its manifest is the old shape)", r.stderr[-160:]
        imp.write_text(json.dumps({"proposals": [SAN]}), encoding="utf-8")
        r = run("--batch-id", "empty-import", "--check")
        yield r.returncode == 0, "a batch built with an empty import rebuilds unchanged after a proposal is imported", \
            r.stdout[-160:]
        r = run("--batch-id", "with-proposal", *(["--_mutate", "unpinned"] if MUTATION == "unpinned" else []))
        mpath = d / "digests" / "with-proposal" / "manifest.json"
        man = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
        spath = d / "digests" / "with-proposal" / "sanctions_desk.md"
        san_md = spath.read_text(encoding="utf-8") if spath.exists() else ""
        yield "typology_proposals" in man and "TP-2026-001" in san_md, \
            "a batch built with a proposal pins the import and lists it", sorted(man)
        yield run("--batch-id", "with-proposal", "--check").returncode == 0, "and its --check matches", ""
        imp.write_text(json.dumps({"proposals": [SAN, CRYPTO]}), encoding="utf-8")
        r = run("--batch-id", "with-proposal", "--check")
        yield r.returncode == 1 and "inputs moved" in r.stdout and "typology_proposals.json" in r.stdout, \
            "a moved import reads as INPUTS MOVED, naming it", r.stdout[-160:]


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the digests' open typology proposals")
    ap.add_argument("--mutate", choices=MUTATIONS)
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if MUTATION == "wrong-desk":
        dg.proposals_for = lambda desk, open_proposals, routing: sorted(open_proposals, key=lambda p: p["proposal_id"])
    elif MUTATION == "always-heading":
        dg.proposals_for = lambda desk, open_proposals, routing: [dict(SAN, proposal_id="TP-0000-000")]
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
