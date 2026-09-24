"""
Pin the review gate: what reaches a human, and what a decision can and cannot do.

Usage:
    python evals/check_review_gate.py
    python evals/check_review_gate.py --mutate quarantine   # re-check disabled; tampered proposal MUST surface
    python evals/check_review_gate.py --mutate overturn     # decided links reopen; overturn MUST go through
    python evals/check_review_gate.py --mutate evidence     # new quotes ignored; new evidence MUST stay hidden
    python evals/check_review_gate.py --mutate contract     # contract re-checks off; tampered lines MUST pass

Builds a throwaway queue from REAL quotes in the ADV-2026-0002 golden label, plus
one tampered proposal and one legacy line, and drives governance/ against it.
Nothing here touches data/proposals/, the decision log or the approvals files.

NEEDS the ADV-2026-0002 PDF in data/advisories/ (gitignored). Without it this
exits 2 and says so.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import proposals as gp  # noqa: E402
from governance import decisions as gd  # noqa: E402
from schemas.citation_match import MISSING, PageIndex  # noqa: E402
from schemas.proposal_contract import QUOTE_MAX, proposal_id  # noqa: E402

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


def _line(run_id: str, typology_id, emergent_label, page: int, quote: str) -> dict:
    """A queue line as the server writes it: its proposal_id recomputes, since the gate re-asserts that."""
    d = {"schema": "proposal/2", "proposed_at": "2026-09-24T12:00:00+00:00",
         "run_id": run_id, "stage": "extractor", "advisory_id": ADVISORY, "document_sha256": SHA,
         "typology_id": typology_id, "emergent_label": emergent_label,
         "rationale": "Guard fixture rationale for %s." % (typology_id or emergent_label),
         "confidence": "medium", "citations": [{"page": page, "quote": quote}]}
    return {"proposal_id": proposal_id(d), **d}


def build_fixture() -> dict:
    """Write the throwaway queue. Returns the witness keys the checks refer to."""
    cites = _gold_citations()
    a_tid, a_page, a_quote = cites[0]
    # A different typology for the tampered proposal, so quarantine is visible per link.
    t_tid = next(t for t, _, _ in cites if t != a_tid)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    rows_1 = [
        _line("run-one", a_tid, None, a_page, a_quote),
        _line("run-one", None, "Guard  Witness emergent technique", a_page, a_quote),
        _line("run-one", t_tid, None, a_page, a_quote + " FABRICATED BY THE GUARD"),
        {"advisory_id": ADVISORY, "typology_id": a_tid, "status": "pending_review"},  # legacy shape
    ]
    rows_2 = [_line("run-two", a_tid, None, a_page, a_quote)]  # same link, same quote, second run
    (QUEUE_DIR / "run-one.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_1), encoding="utf-8")
    (QUEUE_DIR / "run-two.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_2), encoding="utf-8")
    new_quote = next((p, q) for t, p, q in cites if (p, q) != (a_page, a_quote))
    return {"a_key": gp.link_key(ADVISORY, a_tid, None), "t_key": gp.link_key(ADVISORY, t_tid, None),
            "e_key": gp.link_key(ADVISORY, None, "guard witness emergent technique"),
            "a_tid": a_tid, "new_quote": new_quote, "t_id": rows_1[2]["proposal_id"],
            "e_id": rows_1[1]["proposal_id"], "cite": (a_page, a_quote), "cites": cites}


def queue_checks(w: dict) -> list:
    out = []
    proposals, skipped = gp.load_queue(QUEUE_DIR)
    out.append((len(proposals) == 4 and len(skipped) == 1,
                "load_queue reads proposal/2 lines and REPORTS the legacy line it skips",
                "%d proposals, skipped: %s" % (len(proposals), skipped)))
    clean, quarantined = gp.recheck(proposals)
    out.append(([q.proposal.proposal_id for q in quarantined] == [w["t_id"]],
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


def contract_checks(w: dict) -> list:
    """Each tampered copy of a clean line, in its OWN queue dir, must quarantine with its own reason.

    The final week-5 review measured six hand-tampered copies of a real line
    passing the re-check clean: the gate verified quotes and nothing else. One
    dir per witness so a witness can never lean on another's quarantine, and the
    shared fixture's counts above are untouched.
    """
    out = []
    page, quote = w["cite"]
    base = _line("run-c", w["a_tid"], None, page, quote)

    def sealed(**changes) -> dict:
        """The clean line with `changes`, and a proposal_id that recomputes -- so only the change is wrong."""
        d = {k: v for k, v in base.items() if k != "proposal_id"}
        d.update(changes)
        return {"proposal_id": proposal_id(d), **d}

    def cite(q: str, pg: int = page) -> list:
        return [{"page": pg, "quote": q}]

    index = PageIndex.from_pdf(PDF)
    off_page = next((pg, q) for _, pg, q in w["cites"]
                    if not index.locate(pg + 1, q).ok and index.locate(pg + 1, q).found_on)
    witnesses = [
        ("clean", sealed(), None),
        ("empty quote", sealed(citations=cite("")), "characters after strip"),
        ("quote 'the'", sealed(citations=cite("the")), "characters after strip"),
        ("quote padded to length", sealed(citations=cite("   the    ")), "characters after strip"),
        ("quote over QUOTE_MAX", sealed(citations=cite("x" * (QUOTE_MAX + 1))), "characters after strip"),
        ("neither typology nor emergent", sealed(typology_id=None, emergent_label=None), "names neither"),
        ("empty strings are absent", sealed(typology_id="", emergent_label=""), "names neither"),
        ("both typology and emergent", sealed(emergent_label="Guard witness label"), "names both"),
        ("stage not in STAGES", sealed(stage="whoever"), "is not one of"),
        ("run_id is not the file stem", sealed(run_id="run-elsewhere"), "does not match its queue file"),
        ("rationale edited, old id kept", {**base, "rationale": base["rationale"] + " Edited by hand."},
         "does not recompute"),
        ("quote on another page", sealed(citations=cite(off_page[1], off_page[0] + 1)),
         "quote not on page %d (it appears on page" % (off_page[0] + 1)),
        ("quote not in the document", sealed(citations=cite(quote + " FABRICATED BY THE GUARD")),
         "quote not in the document"),
    ]
    for n, (name, line, expect) in enumerate(witnesses):
        qdir = WORK / "contract" / ("w%02d" % n)
        qdir.mkdir(parents=True)
        (qdir / "run-c.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        proposals, skipped = gp.load_queue(qdir)
        clean, quarantined = gp.recheck(proposals)
        reason = quarantined[0].reason if quarantined else ""
        if expect is None:
            ok = len(proposals) == 1 and len(clean) == 1 and not quarantined and not skipped
            label = "an untampered line in the same style passes clean (the witnesses below are not vacuous)"
        else:
            ok = len(proposals) == 1 and not clean and len(quarantined) == 1 and expect in reason
            label = "%s: QUARANTINED with its own reason" % name
        out.append((ok, label, reason[:110] or "clean %d, skipped %s" % (len(clean), skipped)))
    hit = PageIndex(["some page text"]).locate(1, "   ")
    out.append((hit.status == MISSING, "PageIndex.locate: an empty quote is MISSING, not an exact match",
                hit.status))
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
    third.write_text(json.dumps(_line("run-three", w["a_tid"], None, page, quote)) + "\n",
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


def cli_checks(w: dict) -> list:
    out = []
    cli = WORK / "cli"
    cli.mkdir(exist_ok=True)
    paths = ["--queue-dir", str(QUEUE_DIR), "--log", str(cli / "log.jsonl"),
             "--approved-links", str(cli / "links.json"), "--approved-emergent", str(cli / "emergent.json")]

    def run(*args, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "tools" / "review.py"), *args, *paths],
                              input=stdin, capture_output=True, text=True, cwd=ROOT)

    r = run("--list")
    out.append((r.returncode == 0 and w["a_key"] in r.stdout and "quarantined links: 1" in r.stdout
                and "skipped lines: 1" in r.stdout,
                "--list shows open links, the quarantined link and the skipped line", r.stdout[-200:]))

    # Controller ruling (Task 5 review): a quarantined proposal whose link ALSO
    # has a clean proposal must still be listed with its reason -- it currently
    # appears nowhere, because quarantined_links() only reports links with NO
    # clean proposal at all.
    page, quote = w["cite"]
    mixed = QUEUE_DIR / "run-mixed.jsonl"
    a9 = _line("run-mixed", w["a_tid"], None, page, quote + " TAMPERED")
    mixed.write_text(json.dumps(a9) + "\n", encoding="utf-8")
    r = run("--list")
    out.append((r.returncode == 0 and a9["proposal_id"] in r.stdout and "quote not in the document" in r.stdout,
                "--list names a quarantined proposal even when its link has a clean one", r.stdout[-200:]))
    mixed.unlink()

    decisions = cli / "decisions.txt"
    decisions.write_text("FC08 review decisions\n%s %s: approve -- from a pasted list\n"
                         % (ADVISORY, w["a_tid"]), encoding="utf-8")
    r = run("--decisions", str(decisions))
    links = json.loads((cli / "links.json").read_text(encoding="utf-8"))["approved"] \
        if (cli / "links.json").exists() else []
    out.append((r.returncode == 0 and [x["link_key"] for x in links] == [w["a_key"]],
                "--decisions applies a pasted list and rebuilds the approvals", (r.stdout + r.stderr)[-160:]))

    r = run("--decisions", str(decisions))
    out.append((r.returncode != 0 and "change of mind" in (r.stdout + r.stderr),
                "the same list again is REFUSED, exit non-zero", (r.stdout + r.stderr)[-120:]))

    r = run("--check")
    out.append((r.returncode == 0, "--check passes on files the CLI wrote", r.stdout[-100:]))
    (cli / "links.json").write_text("{}\n", encoding="utf-8")
    r = run("--check")
    out.append((r.returncode != 0, "--check FAILS on a hand-edited approvals file", r.stdout[-100:]))

    # Interactive: the only open link left in THIS log is the emergent one (A is
    # approved above, T is quarantined), so the first card is the emergent link.
    r = run(stdin="r\nno mechanism on the page\nq\n")
    log_file = cli / "log.jsonl"
    log = [json.loads(x) for x in log_file.read_text(encoding="utf-8").splitlines()] if log_file.exists() else []
    out.append((r.returncode == 0 and bool(log) and log[-1]["link_key"] == w["e_key"]
                and log[-1]["decision"] == "reject" and log[-1]["note"] == "no mechanism on the page",
                "interactive mode records a decision with its note through the same writer",
                (r.stdout + r.stderr)[-160:]))

    writers = []
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith((".venv/", "evals/")) or rel == "governance/decisions.py":
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        if "approved_links.json" in text or "approved_emergent.json" in text:
            writers.append(rel)
    out.append((writers == [], "NOTHING outside governance/decisions.py names the approvals files",
                "found in: %s" % writers if writers else "only the gate"))
    return out


def _review(*args, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "tools" / "review.py"), *args],
                          input=stdin, capture_output=True, text=True, cwd=ROOT)


def log_checks(w: dict) -> list:
    """--check proves the log holds ONLY decisions the gate made, and the deciding modes cannot be pointed
    at a stray queue while writing the real log.

    The final week-5 review hand-wrote a log line approving ADV-2026-0001::TBML001
    with proposal_ids [] and rebuilt the approvals from it: --check passed,
    because it only asked whether the approvals match the log. Each witness here
    rebuilds its approvals FROM its own log, so check_approved is satisfied and
    only the new log check can catch it.
    """
    out = []
    proposals, _ = gp.load_queue(QUEUE_DIR)
    clean, quarantined = gp.recheck(proposals)
    links = gp.group(clean)
    q_links = gp.quarantined_links(quarantined, links)
    a = links[w["a_key"]]

    def forged(**changes) -> str:
        d = gd.Decision(decided_at="2026-09-24T15:00:00+00:00", link_key=w["a_key"], kind="governed",
                        advisory_id=ADVISORY, typology_id=w["a_tid"], emergent_label=None, decision="approve",
                        note="hand-written", proposal_ids=a.proposal_ids, run_ids=a.run_ids,
                        quotes_seen_sha256=tuple(sorted(a.quote_hashes())))
        return gd.Decision(**{**d.__dict__, **changes}).to_line() + "\n"

    witnesses = [
        ("a decision the gate made", None, None),
        ("a hand-written line with EMPTY proposal_ids",
         forged(link_key="ADV-2026-0001::TBML001", advisory_id="ADV-2026-0001", typology_id="TBML001",
                proposal_ids=()), "no proposal_ids"),
        ("a line citing a proposal_id that does not exist",
         forged(proposal_ids=("0000000000000000",)), "not in the queue"),
        ("a line citing a real proposal of a DIFFERENT link",
         forged(proposal_ids=(w["e_id"],)), "is for %s" % w["e_key"]),
        ("a MALFORMED log line", "{not json\n", "line 1 of the log is malformed"),
    ]
    for n, (name, text, expect) in enumerate(witnesses):
        d = WORK / "logcheck" / ("w%02d" % n)
        d.mkdir(parents=True)
        log, lk, em = d / "log.jsonl", d / "links.json", d / "emergent.json"
        if text is None:
            gd.apply([(w["a_key"], "approve", "made by the gate")], links, q_links, log_path=log,
                     now="2026-09-24T15:00:00+00:00")
        else:
            log.write_text(text, encoding="utf-8")
        try:
            gd.write_approved(gd.load_log(log), lk, em)
        except Exception:  # a malformed log cannot be rebuilt from: no approvals files, so none to disagree
            pass
        r = _review("--check", "--queue-dir", str(QUEUE_DIR), "--log", str(log),
                    "--approved-links", str(lk), "--approved-emergent", str(em))
        said = r.stdout + r.stderr
        if expect is None:
            ok, label = r.returncode == 0, "--check passes a log the gate wrote (the witnesses below are not vacuous)"
        else:
            ok = r.returncode == 1 and expect in said and "Traceback" not in said
            label = "--check FAILS on %s, with the reason and no traceback" % name
        out.append((ok, label, said.strip().replace("\n", " | ")[-150:]))

    # Deciding modes refuse a split override. The requests name an UNKNOWN link,
    # so even with the refusal gone apply() refuses before writing: this check can
    # never write the real log. It also asserts the real log is untouched.
    real = [(p, p.read_bytes() if p.exists() else None) for p in (gd.LOG, gd.APPROVED_LINKS, gd.APPROVED_EMERGENT)]
    stray = WORK / "stray_decisions.txt"
    stray.write_text("%s NOPE999: approve -- must never reach the real log\n" % ADVISORY, encoding="utf-8")
    for name, args, stdin in (
        ("--decisions with --queue-dir but not --log", ("--decisions", str(stray), "--queue-dir", str(QUEUE_DIR)), ""),
        ("interactive with --queue-dir but not --log", ("--queue-dir", str(QUEUE_DIR)), "q\n"),
        ("--decisions with --log but not --queue-dir",
         ("--decisions", str(stray), "--log", str(WORK / "stray_log.jsonl")), ""),
    ):
        r = _review(*args, stdin=stdin)
        said = r.stdout + r.stderr
        out.append((r.returncode != 0 and "--queue-dir and --log" in said,
                    "a deciding mode REFUSES %s" % name, said.strip()[-120:]))
    after = [(p, p.read_bytes() if p.exists() else None) for p, _ in real]
    out.append((after == real, "the real decision log and approvals files are untouched by this guard",
                ", ".join(p.name for p, b in real if b is not None) or "none exist"))
    return out


def all_checks() -> list:
    w = build_fixture()
    return queue_checks(w) + contract_checks(w) + decision_checks(w) + cli_checks(w) + log_checks(w)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the review gate")
    ap.add_argument("--mutate", choices=("quarantine", "overturn", "evidence", "contract"),
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
    elif args.mutate == "contract":
        gp._contract_problem = lambda proposal: None
        print("MUTATED: the review-time contract re-checks are removed; only the quote check is left.\n")

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
