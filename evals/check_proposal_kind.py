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


from governance import decisions as gd  # noqa: E402
import review  # noqa: E402  (tools/review.py)


def _decision(kind, **over):
    base = dict(decided_at="2026-10-14T00:00:00+00:00", link_key="k", kind=kind, advisory_id="ADV-2026-0030",
                typology_id=None, emergent_label=None, decision="approve", note="n", proposal_ids=("p",),
                run_ids=("r",), quotes_seen_sha256=("q",))
    base.update(over)
    return gd.Decision(**base)


def checks_decisions():
    old = {"decided_at": "2026-10-11T09:10:52+00:00", "link_key": "ADV-2026-0026::SAN006", "kind": "governed",
           "advisory_id": "ADV-2026-0026", "typology_id": "SAN006", "emergent_label": None, "decision": "approve",
           "note": "n", "proposal_ids": ["p"], "run_ids": ["r"], "quotes_seen_sha256": ["q"]}
    d = gd.Decision.from_line(old)
    yield d.typology_proposal is None and "typology_proposal" not in json.loads(d.to_line()), \
        "a pre-S2 decision line reads and re-serialises unchanged", d.link_key
    prop = _decision("proposal", link_key="ADV-2026-0030::PROPOSAL[TP-2026-001]", typology_proposal="TP-2026-001")
    emer = _decision("emergent", link_key="ADV-2026-0031::EMERGENT[x]", emergent_label="x")
    links_t, emergent_t, proposals_t = gd.rebuild([prop, emer])
    rows = json.loads(proposals_t)["approved"]
    yield [r.get("typology_proposal") for r in rows] == ["TP-2026-001"], \
        "a proposal approval lands in the proposals file", proposals_t.strip()[:80]
    yield "TP-2026-001" not in emergent_t and "EMERGENT[x]" not in proposals_t, \
        "emergent and proposal approvals never cross files", "separate"
    parsed = review.parse_decisions("ADV-2026-0030 PROPOSAL[tp-2026-001]: approve -- same channel")
    yield parsed == [("ADV-2026-0030::PROPOSAL[TP-2026-001]", "approve", "same channel")], \
        "a pasted PROPOSAL decision line parses to the gate's key", repr(parsed)


from mcp_server import knowledge_centre_server as kc_server  # noqa: E402  (reload keeps this object)


def _kc(proposals_path: Path):
    os.environ["NEXUS_TYPOLOGY_PROPOSALS_PATH"] = str(proposals_path)
    import importlib
    from mcp_server import knowledge_centre_server as kc
    return importlib.reload(kc)


def checks_server():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "typology_proposals.json"
        path.write_text(json.dumps({"proposals": [{
            "proposal_id": "TP-2026-001", "working_name": "Underground banking via alternative banking platforms",
            "family": "sanctions", "stage": "corroborating", "summary": "Underground banking; ABP",
            "evidence": [{"advisory_id": "ADV-2026-0003", "publisher": "FATF",
                          "quotes": ["Underground banking is one tool often used by professional money launderers."]}]}]}),
            encoding="utf-8")
        kc = _kc(path)
        if MUTATION == "unknown-tp":
            kc_server._open_proposals = lambda: [{"proposal_id": "TP-2026-009", "family": "sanctions",
                                           "working_name": "x", "evidence": []}] + json.loads(path.read_text())["proposals"]
        if MUTATION == "no-tier":
            kc_server._proposal_records = lambda: []
        P = kc.ProposeLinkInput
        args = dict(advisory_id="ADV-2026-0030", rationale="a rationale long enough to pass", confidence="medium",
                    citations=[{"page": 1, "quote": "Underground banking moved the funds."}])
        yield kc._refuse_target(P(typology_proposal="TP-2026-001", **args)) is None, \
            "an open proposal is an acceptable target", "TP-2026-001"
        r = kc._refuse_target(P(typology_proposal="TP-2026-009", **args))
        yield bool(r) and "not an open typology proposal" in r, "a TP that is not open is refused", r or "accepted"
        r = kc._refuse_target(P(typology_proposal="TP-2026-001", emergent_label="x y z", **args))
        yield bool(r) and "exactly one" in r, "two targets are refused", r or "accepted"
        text = kc._with_proposals("No match above the floor (0.25). Treat as a possible emergent typology and "
                                  "propose it with emergent_label.", "underground banking platform")
        yield "TP-2026-001" in text and "typology_proposal" in text, \
            "a matching open proposal is listed, with how to link it", text[:90]
        path.write_text(json.dumps({"proposals": []}), encoding="utf-8")
        kc = _kc(path)
        if MUTATION == "unknown-tp":
            kc_server._open_proposals = lambda: [{"proposal_id": "TP-2026-009", "family": "sanctions",
                                           "working_name": "x", "evidence": []}] + json.loads(path.read_text())["proposals"]
        if MUTATION == "no-tier":
            kc_server._proposal_records = lambda: []
        base = "No match above the floor (0.25). Treat as a possible emergent typology and propose it with emergent_label."
        yield kc._with_proposals(base, "underground banking platform") == base, \
            "with no open proposals the governed answer is unchanged (never an unimported TP)", "unchanged"
    os.environ.pop("NEXUS_TYPOLOGY_PROPOSALS_PATH", None)


def checks():
    yield from checks_queue()
    yield from checks_decisions()
    yield from checks_server()


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the proposal link kind")
    ap.add_argument("--mutate", choices=MUTATIONS)
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if MUTATION == "body-always":
        real = gp.Proposal.body
        gp.Proposal.body = lambda self: {**real(self), "typology_proposal": self.typology_proposal}
    elif MUTATION == "two-targets":
        gp._contract_problem = lambda p: None
    elif MUTATION == "kind-fallback":
        gd._TARGET["proposal"] = "emergent_label"
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
