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
from governance import decisions as gd  # noqa: E402

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


def decision_checks(w: dict) -> list:
    out = []
    log = WORK / "review_decisions.jsonl"
    links_path, emergent_path = WORK / "approved_links.json", WORK / "approved_emergent.json"
    proposals, _ = gp.load_queue(QUEUE_DIR)
    clean, quarantined = gp.recheck(proposals)
    links = gp.group(clean)
    q_links = gp.quarantined_links(quarantined, links)

    def refused(requests) -> str:
        """The refusal message, or '' if apply accepted. Flags a refusal that wrote anyway."""
        before = log.read_text(encoding="utf-8") if log.exists() else ""
        try:
            gd.apply(requests, links, q_links, log_path=log, now="2026-09-24T13:00:00+00:00")
        except gd.GateRefusal as exc:
            after = log.read_text(encoding="utf-8") if log.exists() else ""
            return str(exc) if before == after else "REFUSED BUT WROTE: %s" % exc
        return ""

    a_link = links.get(w["a_key"])
    out.append((a_link is not None and gd.state(a_link, None) == gd.OPEN, "an undecided link is OPEN", ""))

    made = gd.apply([(w["a_key"], "approve", "fixture approve"), (w["e_key"], "reject", "")],
                    links, q_links, log_path=log, now="2026-09-24T13:00:00+00:00")
    rows = gd.load_log(log)
    out.append((len(made) == 2 and len(rows) == 2 and rows[0].run_ids == ("run-one", "run-two")
                and rows[0].advisory_id == ADVISORY and rows[0].typology_id == w["a_tid"],
                "apply appends one line per decision, carrying runs, advisory and typology",
                "%d lines" % len(rows)))

    gd.write_approved(gd.load_log(log), links_path, emergent_path)
    approved = json.loads(links_path.read_text(encoding="utf-8"))["approved"]
    emergent = json.loads(emergent_path.read_text(encoding="utf-8"))["approved"]
    out.append(([r["link_key"] for r in approved] == [w["a_key"]] and emergent == [],
                "approvals are rebuilt from the log; a REJECTED emergent is in neither file",
                "links %s, emergent %s" % ([r["link_key"] for r in approved], emergent)))

    msg = refused([(w["a_key"], "reject", "change of mind")])
    out.append(("change of mind" in msg and "REFUSED BUT WROTE" not in msg,
                "overturning a decided link is REFUSED and writes nothing", msg[:120]))

    msg = refused([(w["t_key"], "approve", "")])
    out.append(("quarantined" in msg, "a quarantined link cannot be approved", msg[:120]))

    msg = refused([("ADV-2026-0002::NOPE999", "approve", "")])
    out.append(("no reviewable link" in msg, "an unknown link is refused", msg[:120]))

    lines_before = len(gd.load_log(log))
    msg = refused([(w["e_key"], "approve", ""), (w["e_key"], "approve", "")])
    out.append(("twice" in msg and len(gd.load_log(log)) == lines_before,
                "a link decided twice in one list is refused, and NOTHING from that list is written",
                msg[:120]))

    # New evidence: a third run proposes the approved link with a quote not seen before.
    page, quote = w["new_quote"]
    third = QUEUE_DIR / "run-three.jsonl"
    third.write_text(json.dumps(_line("run-three", "p-a3", w["a_tid"], None, page, quote)) + "\n",
                     encoding="utf-8")
    clean3, quarantined3 = gp.recheck(gp.load_queue(QUEUE_DIR)[0])
    links3 = gp.group(clean3)
    prior = gd.latest(gd.load_log(log))
    now_state = gd.state(links3[w["a_key"]], prior.get(w["a_key"]))
    out.append((now_state == gd.NEW_EVIDENCE,
                "a decided link RETURNS when a later run brings a quote not seen before", now_state))
    try:
        gd.apply([(w["a_key"], "reject", "new evidence changes it")], links3,
                 gp.quarantined_links(quarantined3, links3), log_path=log, now="2026-09-24T14:00:00+00:00")
    except gd.GateRefusal as exc:
        out.append((False, "deciding new evidence is accepted", str(exc)[:120]))
    rows = gd.load_log(log)
    out.append((len(rows) == 3 and rows[0].decision == "approve" and rows[-1].decision == "reject",
                "deciding new evidence APPENDS a line; the earlier line is untouched",
                [r.decision for r in rows]))
    third.unlink()

    gd.write_approved(gd.load_log(log), links_path, emergent_path)
    out.append((gd.check_approved(gd.load_log(log), links_path, emergent_path) == [],
                "check_approved passes on files rebuilt from the log", ""))
    links_path.write_text(links_path.read_text(encoding="utf-8").replace("[]", '[{"hand": "edit"}]'),
                          encoding="utf-8")
    problems = gd.check_approved(gd.load_log(log), links_path, emergent_path)
    out.append((bool(problems), "a HAND-EDITED approvals file is caught", "; ".join(problems)[:120]))
    out.append((gd.rebuild(gd.load_log(log)) == gd.rebuild(gd.load_log(log)), "rebuild is deterministic", ""))
    return out


def all_checks() -> list:
    w = build_fixture()
    return queue_checks(w) + decision_checks(w)


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
    elif args.mutate == "overturn":
        gd.state = lambda link, prior: gd.OPEN
        print("MUTATED: every link reads as OPEN, so a decided link can be overturned.\n")
    elif args.mutate == "evidence":
        gp.Link.quote_hashes = lambda self: frozenset()
        print("MUTATED: a link's quotes are ignored when deciding whether it has new evidence.\n")

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
