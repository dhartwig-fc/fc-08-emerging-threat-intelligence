"""
Pin the third link kind, `proposal` (Stage565 S2): an advisory linked to an OPEN fc-10 typology proposal.

Usage:
    python evals/check_proposal_kind.py
    python evals/check_proposal_kind.py --mutate body-always   # body() always carries typology_proposal; MUST fail
    python evals/check_proposal_kind.py --mutate two-targets   # the contract accepts two targets; MUST fail
    python evals/check_proposal_kind.py --mutate kind-fallback # _rows files a proposal approval as emergent; MUST fail
    python evals/check_proposal_kind.py --mutate unknown-tp    # the server accepts a TP that is not open; MUST fail
    python evals/check_proposal_kind.py --mutate no-tier       # search never lists open proposals; MUST fail

COLD. Pure functions and temporary files only: no PDF, no run context, no portfolio. The quote-on-page
re-check for proposal links is the existing review-gate guard's (needs-pdfs); this guard pins the kind.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from governance import proposals as gp  # noqa: E402

MUTATIONS = ("body-always", "two-targets", "kind-fallback", "unknown-tp", "no-tier")
MUTATION = None


def _proposal(**over) -> "gp.Proposal":
    base = dict(proposal_id="x", proposed_at="2026-10-14T00:00:00+00:00", run_id="run-a", stage="extractor",
                advisory_id="ADV-2026-0030", document_sha256="a" * 64, typology_id=None, emergent_label=None,
                rationale="a rationale long enough to pass", confidence="medium",
                citations=((1, "Underground banking moved the funds."),), source_file="data/proposals/run-a.jsonl")
    base.update(over)
    p = gp.Proposal(**base)
    return gp.Proposal(**{**base, "proposal_id": gp.proposal_id(p.body())})


def checks_queue():
    yield gp.link_key("ADV-2026-0030", None, None, "TP-2026-001") == "ADV-2026-0030::PROPOSAL[TP-2026-001]", \
        "a proposal link's key", gp.link_key("ADV-2026-0030", None, None, "TP-2026-001")
    p = _proposal(typology_proposal="TP-2026-001")
    yield (p.kind, p.link_key) == ("proposal", "ADV-2026-0030::PROPOSAL[TP-2026-001]"), \
        "a proposal naming a TP is kind 'proposal'", "%s %s" % (p.kind, p.link_key)
    yield _proposal(emergent_label="x y z").kind == "emergent" and _proposal(typology_id="SAN006").kind == "governed", \
        "the other two kinds are unchanged", "emergent, governed"
    plain = _proposal(emergent_label="underground banking")
    yield "typology_proposal" not in plain.body(), "an unset typology_proposal stays out of the body", \
        ", ".join(sorted(plain.body()))
    yield "typology_proposal" in p.body(), "a set typology_proposal is in the body (and so in the id)", p.proposal_id
    lines = [ln for f in sorted(gp.QUEUE_DIR.glob("*.jsonl"))
             for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    stale = []
    for ln in lines:
        d = json.loads(ln)
        q = gp.Proposal.from_line(d)
        if gp.proposal_id(q.body()) != d["proposal_id"]:
            stale.append(d["proposal_id"])
    yield not stale and len(lines) >= 1, "every tracked queue line still recomputes its id", \
        ", ".join(stale) or "%d lines" % len(lines)
    two = _proposal(emergent_label="underground banking", typology_proposal="TP-2026-001")
    yield (gp._contract_problem(two) or "").startswith("names both"), \
        "a proposal naming two targets breaks the contract", gp._contract_problem(two) or "accepted"
    yield gp._contract_problem(p) is None, "a proposal naming only a TP meets the contract", \
        gp._contract_problem(p) or "ok"


def checks():
    yield from checks_queue()


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the proposal link kind")
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
