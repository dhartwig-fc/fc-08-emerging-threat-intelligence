"""
Pin the review gate: what reaches a human, and what a decision can and cannot do.

Usage:
    python evals/check_review_gate.py
    python evals/check_review_gate.py --mutate quarantine   # re-check disabled; tampered proposal MUST surface
    python evals/check_review_gate.py --mutate overturn     # decided links reopen; overturn MUST go through
    python evals/check_review_gate.py --mutate evidence     # new quotes ignored; new evidence MUST stay hidden

Builds a throwaway queue from REAL quotes in the ADV-2026-0002 golden label, plus
one tampered proposal and one legacy line, and drives governance/ against it.
Nothing here touches data/proposals/, the decision log or the approvals files.

NEEDS the ADV-2026-0002 PDF in data/advisories/ (gitignored). Without it this
exits 2 and says so.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import proposals as gp  # noqa: E402

ADVISORY = "ADV-2026-0002"
_LIST = {a["advisory_id"]: a for a in json.loads(gp.ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
PDF = gp.ADVISORIES_DIR / Path(_LIST[ADVISORY]["file"]).name
SHA = _LIST[ADVISORY]["sha256"]
WORK = Path(tempfile.mkdtemp(prefix="fc08_gate_"))
QUEUE_DIR = WORK / "proposals"


def _gold_citations() -> list:
    """(typology_id, page, quote) for every citation in the golden label, in order."""
    g = json.loads((ROOT / "evals" / "golden" / ("%s.json" % ADVISORY)).read_text(encoding="utf-8"))
    return [(t["typology_id"], c["page"], c["quote"]) for t in g["typologies"] if t.get("typology_id")
            for c in t["citations"]]


def _line(run_id: str, pid: str, typology_id, emergent_label, page: int, quote: str) -> dict:
    return {"schema": "proposal/2", "proposal_id": pid, "proposed_at": "2026-09-24T12:00:00+00:00",
            "run_id": run_id, "stage": "extractor", "advisory_id": ADVISORY, "document_sha256": SHA,
            "typology_id": typology_id, "emergent_label": emergent_label,
            "rationale": "Guard fixture rationale for %s." % (typology_id or emergent_label),
            "confidence": "medium", "citations": [{"page": page, "quote": quote}]}


def build_fixture() -> dict:
    """Write the throwaway queue. Returns the witness keys the checks refer to."""
    cites = _gold_citations()
    a_tid, a_page, a_quote = cites[0]
    # A different typology for the tampered proposal, so quarantine is visible per link.
    t_tid = next(t for t, _, _ in cites if t != a_tid)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    rows_1 = [
        _line("run-one", "p-a1", a_tid, None, a_page, a_quote),
        _line("run-one", "p-e1", None, "Guard  Witness emergent technique", a_page, a_quote),
        _line("run-one", "p-t1", t_tid, None, a_page, a_quote + " FABRICATED BY THE GUARD"),
        {"advisory_id": ADVISORY, "typology_id": a_tid, "status": "pending_review"},  # legacy shape
    ]
    rows_2 = [_line("run-two", "p-a2", a_tid, None, a_page, a_quote)]  # same link, same quote, second run
    (QUEUE_DIR / "run-one.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_1), encoding="utf-8")
    (QUEUE_DIR / "run-two.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_2), encoding="utf-8")
    new_quote = next((p, q) for t, p, q in cites if (p, q) != (a_page, a_quote))
    return {"a_key": gp.link_key(ADVISORY, a_tid, None), "t_key": gp.link_key(ADVISORY, t_tid, None),
            "e_key": gp.link_key(ADVISORY, None, "guard witness emergent technique"),
            "a_tid": a_tid, "new_quote": new_quote}


def queue_checks(w: dict) -> list:
    out = []
    proposals, skipped = gp.load_queue(QUEUE_DIR)
    out.append((len(proposals) == 4 and len(skipped) == 1,
                "load_queue reads proposal/2 lines and REPORTS the legacy line it skips",
                "%d proposals, skipped: %s" % (len(proposals), skipped)))
    clean, quarantined = gp.recheck(proposals)
    out.append(([q.proposal.proposal_id for q in quarantined] == ["p-t1"],
                "re-check QUARANTINES exactly the tampered proposal",
                "; ".join("%s: %s" % (q.proposal.proposal_id, q.reason) for q in quarantined) or "none"))
    out.append((any("page" in q.reason for q in quarantined),
                "the quarantine reason names the page", quarantined[0].reason if quarantined else "none"))
    links = gp.group(clean)
    out.append((sorted(links) == sorted([w["a_key"], w["e_key"]]),
                "clean proposals group into one link per advisory+typology or emergent label",
                str(sorted(links))))
    a = links.get(w["a_key"])
    out.append((a is not None and a.run_ids == ("run-one", "run-two") and len(a.quotes()) == 1
                and a.quotes()[0][2] == 2,
                "a link collects every run; the repeated quote is shown ONCE with a count of 2",
                "runs %s, quotes %s" % (a.run_ids, a.quotes()) if a else "missing"))
    out.append((links.get(w["e_key"]) is not None and links[w["e_key"]].kind == "emergent",
                "emergent labels are matched case- and space-insensitively and kept as emergent",
                str(sorted(links))[:120]))
    q_links = gp.quarantined_links(quarantined, links)
    out.append((list(q_links) == [w["t_key"]],
                "a link with NO clean proposal is reported as quarantined, not presented",
                str(q_links)))
    return out


def all_checks() -> list:
    w = build_fixture()
    return queue_checks(w)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the review gate")
    ap.add_argument("--mutate", choices=("quarantine", "overturn", "evidence"),
                    help="remove one gate rule; the checks that depend on it MUST fail")
    args = ap.parse_args(argv)

    if not PDF.exists():
        print("CANNOT RUN: %s is not on this machine (data/advisories/ is gitignored).\n"
              "Nothing was checked; this is not a pass." % PDF.relative_to(ROOT))
        return 2

    if args.mutate == "quarantine":
        gp.recheck = lambda proposals, *a, **k: (list(proposals), [])
        print("MUTATED: the review-time re-check is removed.\n")

    failures = 0
    for ok, label, detail in all_checks():
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
