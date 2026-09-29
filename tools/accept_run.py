"""
Decide the items of one feeds run: the ONLY way a live result enters tracked data (spec section 2).

Usage:
    python tools/accept_run.py RUN_ID                     # show the report, ask accept/drop/defer per item, confirm
    python tools/accept_run.py RUN_ID --decisions FILE [--dry-run] [--override-reconciliation REASON]
    python tools/accept_run.py --pending                  # every run in the inbox and what it is waiting for
    python tools/accept_run.py --expire [RUN_ID]          # move pending runs 14+ days old to inbox/expired/
    python tools/accept_run.py --seed-catalogue [--dry-run]  # ONE-TIME: the back-catalogue's items, as drops

FILE is JSON, {"<item key>": "accept" | "drop" | "defer"}, one entry for EVERY item the run listed as new.
  accept  only an item the run EXTRACTED. It gets the advisory id its extraction was allocated (the id its
          record and every proposal already carry), a new entry in data/feeds/advisory_list.json (source, URL,
          sha256, date, the feed run) -- NOT evals/golden/advisory_list.json, the labelled corpus, which every
          digest batch pins by sha256 (measured 2026-09-28: one appended entry fails build_digests --check and
          check_digest_batch); the review gate reads both lists -- and its files are COPIED into tracked folders:
            the document      -> data/advisories/<adv-id>-<source>.<pdf|html>   (gitignored, as in slice 1)
            the record        -> data/feeds/records/<ADV-id>.json  (NOT data/records/: that folder is slice 1's
                                 pinned evidence -- check_citation_repair pins its file set and actor_resolution
                                 --check reads it; measured 2026-09-28, one planted record fails both)
            the queue         -> data/proposals/<extraction run id>.jsonl   (tools/review.py reads it there)
            the telemetry     -> data/telemetry/<extraction run id>.jsonl
  drop    any item. Recorded in the ledger, never listed again.
  defer   any item. NOT recorded: it is listed again next Friday (spec section 1: unfinished and budget-deferred
          items come back).
An item whose extraction FAILED (a crash included) or was DEFERRED FOR BUDGET cannot be accepted -- there is
no complete record to accept -- and is never lost: the decisions must name it, and the interactive default
for it is defer, never drop (default_decision). Dropping it takes an explicit "drop".
AN ALLOCATED ID NOTHING USED. An id is allocated when an extraction STARTS (owner decision 11), so an item
whose extraction failed after that -- the one in flight when a run crashed, say -- holds an id no record
carries. It is not accepted and the id is not reused: it stays in the run's advisory_ids.jsonl (copied to
data/feeds/runs/<run_id>/), and accepted.json names it under "allocated_not_accepted" -- as it does the id of
an extracted item a person deferred or dropped. A recorded gap. If the item returns next Friday and is
extracted, it gets a new id.
Once per run: the run's evidence -- items.json, triage.jsonl, the extraction files, run.json, report.md,
accepted.json and the orchestrator's telemetry -- is copied to data/feeds/runs/<run_id>/, so every ledger
decision is traceable to the verdict and reason behind it from a clone. The inbox copy is left whole.

TAKES THE FRIDAY RUN'S OWN LOCK (tools/friday_run.run_lock) across the plan+apply path -- --dry-run included
-- and is refused while a live Friday run holds it: reconciliation reads every run's allocations, and a live
run could still be making them, so a snapshot taken mid-write would miss allocations made after it. --pending
and --seed-catalogue never touch another run's allocations and stay unlocked.

THE LOCK IS ALSO HELD ACROSS THE INTERACTIVE PROMPT -- ask()'s per-item questions and the final "Apply: ...?
[y/N]" -- not just plan() and apply(). This is by design, not an oversight: the plan's snapshot of every
run's allocations must stay valid until apply() writes, and a person deciding interactively is still inside
that window. The consequence is real: a person who leaves the prompt open blocks the next Friday run for as
long as it stays open, with a LOCKED refusal, same as if `accept_run` were still computing. Decide from a
--decisions file for anything that must not wait on a person.

VALIDATES EVERYTHING FIRST, and refuses the whole run on any failure, writing nothing:
  - the run exists, is not an eval run, is not already accepted, and every listed item is decided exactly once;
  - the run's reconciliation (feeds/reconcile.py) is acceptable -- a FAILED or RECONCILIATION_FAILED run needs
    --override-reconciliation "<reason>", which is recorded -- and a REFUSED run has nothing to accept;
  - per accepted item: the record validates against schemas/advisory.py, names its allocated id and the pinned
    document's sha256, names only library typology ids, and every citation is found on the page it names in
    the pinned document (the shared matcher, PDF or HTML); every queue line passes the review gate's own
    re-check (governance/proposals.recheck) against the advisory-list entry about to be written; its
    extraction session completed with a clean terminal_check (or the override); nothing it would write exists;
  - an item already in the ledger (decided in an EARLIER run) is never a reason to refuse this one (owner
    ruling A, 2026-09-29, C2 Task 0 -- the old wording refused the WHOLE run, which deadlocked two runs
    listing the same item: neither could be accepted nor, under 14 days, expired). It is instead carried as
    already decided: never re-recorded, its ledger entry never touched, and named in accepted.json under
    "already_decided" as decided in the run that first saw it. A decision file that tries to ACCEPT such an
    item IS refused (copying a second record for an item the ledger already closed makes no sense); a drop or
    defer for it is ignored -- WITH A NOTE, not silently: the "ALREADY DECIDED" line (printed after RECORDED,
    and after a --dry-run alike) names this run's own overridden decision for it and the run that actually
    decided it, since it is not this run's decision to make.
Then writes, in this order: the copies, the live-feed advisory list (its entries and derived counts), the
ledger (accepted and dropped items only), and accepted.json in the run's inbox folder. A failure before the
ledger removes the copies AND the folders this call made and restores the advisory list byte for byte, so the
same acceptance can simply be retried. That includes a failure part-way through a copy: every target is
created exclusively ("xb", so nothing is ever overwritten even if it appeared after plan()) and registered
for rollback before its first byte. The owner commits; proposals then go through tools/review.py as in slice 1.

IF THE INBOX MARKER CANNOT BE WRITTEN (the last step, after the ledger), the acceptance IS recorded and is
not rolled back; the run just still reads as pending, so every retry is refused, and it blocks the next
Friday -- naming "already decided ... cannot re-accept it" for any item this run had itself accepted (now in
the ledger under this same run's id), and unconditionally by "<run>'s already exists; nothing is overwritten"
once data/feeds/runs/<run_id>/ was written on the failed attempt, so a drop-only run's retry is refused too,
just by the second reason rather than the first (owner ruling A, 2026-09-29, C2 Task 0). accept_run prints
"RECORDED, BUT NOT MARKED" and exits 2. The recovery is one copy:
    cp data/feeds/runs/<run_id>/accepted.json inbox/<run_id>/accepted.json
Exit codes: 0 recorded (or a dry run); 1 refused, nothing written; 2 recorded, but the marker needs that copy.

--expire moves a pending run of 14 days or more to inbox/expired/<run_id>/ and does not touch the ledger, so its
items return (feeds/runs.py). It takes the Friday run's own exclusive lock (tools/friday_run.run_lock) and is
refused while a run holds it: allocation reads every run's advisory_ids.jsonl, expired ones included, and a
folder moved mid-read could hide an allocated id from it. --seed-catalogue records every evals/feeds/catalogue.json item as a drop, run
"catalogue:<sha256[:12]>", refusing if any is already decided (owner decision 3, slice 2 C).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import extraction, inbox, ledger, reconcile, runs  # noqa: E402

DATA = ROOT / "data"
GOLDEN_LIST = ROOT / "evals" / "golden" / "advisory_list.json"
ADVISORY_LIST = DATA / "feeds" / "advisory_list.json"   # the live-feed list: this tool is its only writer
FEED_LIST_SCHEMA = "fc08-feed-advisories/1"
CATALOGUE = ROOT / "evals" / "feeds" / "catalogue.json"
DECISIONS = ("accept", "drop", "defer")
PUBLISHERS = {"fincen": "FinCEN (US Treasury)", "ofsi": "OFSI (HM Treasury)", "ofac": "OFAC (US Treasury)"}
OVERRIDE_MIN = 10
RUN_FILES = ("items.json", "triage.jsonl", extraction.REQUESTS, extraction.ALLOCATIONS, extraction.OUTCOMES,
             reconcile.RUN_JSON, "report.md")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def targets(adv: str, source: str, ext: str, xrun: str, data: Path) -> dict:
    return {"document": data / "advisories" / ("%s-%s.%s" % (adv.lower(), source, ext)),
            "record": data / "feeds" / "records" / ("%s.json" % adv),
            "queue": data / "proposals" / ("%s.jsonl" % xrun),
            "telemetry": data / "telemetry" / ("%s.jsonl" % xrun)}


class _Unreadable:
    """A quarantine-shaped reason for a queue line that cannot even be read."""

    def __init__(self, reason):
        self.reason = "unreadable queue line: %s" % reason


def _check_accepted(run_id, key, item, verdict, outcome, request, alloc, folder, data, alist_entries, override):
    """(the plan for one accepted item, problems). Nothing is written here."""
    from pydantic import ValidationError
    from schemas.advisory import AdvisoryRecord
    from schemas.citation_match import PageIndex
    from governance import proposals as gate
    sys.path.insert(0, str(ROOT / "evals"))
    from check_citations import check_record_citations
    problems = []
    if not outcome or outcome.get("status") != "extracted":
        return None, ["%s cannot be accepted: it was not extracted (%s)" % (key, (outcome or {}).get("status", "never queued"))]
    if verdict is None:
        return None, ["%s: extracted but has no triage verdict" % key]
    adv, xrun = outcome["advisory_id"], outcome["extraction_run_id"]
    doc = folder / request["document"]["path"]
    ext = doc.suffix.lstrip(".")
    t = targets(adv, item["source"], ext, xrun, data)
    if alloc != adv:
        problems.append("%s: the outcome names %s but the run allocated %s" % (key, adv, alloc))
    if adv in {a["advisory_id"] for a in alist_entries}:
        problems.append("%s: %s is already in the advisory list" % (key, adv))
    if not doc.exists() or _sha(doc) != request["document"]["sha256"]:
        return None, problems + ["%s: the pinned document is missing or changed" % key]
    for name, path in sorted(t.items()):
        if path.exists():
            problems.append("%s: %s already exists; nothing is overwritten" % (key, path))
    record_path = folder / outcome["record"]
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    try:
        record = AdvisoryRecord.model_validate(raw)
    except ValidationError as exc:
        return None, problems + ["%s: the record does not validate: %s" % (key, str(exc).splitlines()[0])]
    if record.advisory_id != adv or record.source.document_sha256 != request["document"]["sha256"]:
        problems.append("%s: the record names %s and document %s..., not %s and the pinned %s..." % (
            key, record.advisory_id, record.source.document_sha256[:12], adv, request["document"]["sha256"][:12]))
    known = gate._library_ids(gate.LIBRARY)
    unknown = sorted({x.typology_id for x in record.typologies if x.typology_id and x.typology_id not in known})
    if unknown:
        problems.append("%s: the record names typology ids the library does not hold: %s" % (key, unknown))
    index = PageIndex.from_document(doc)
    bad = [d for _, ok, d in check_record_citations(adv, raw, index) if not ok]
    if bad:
        problems.append("%s: %d citation(s) are not on the page they name, first: %s p%s (%s)" % (
            key, len(bad), bad[0]["section"], bad[0]["page"], bad[0]["kind"]))
    entry = {"advisory_id": adv, "file": t["document"].name, "publisher": PUBLISHERS[item["source"]],
             "source_type": item["source"], "title": item["title"], "published_on": item["published"],
             "published_on_precision": "day", "url": request["document"].get("url") or item["url"],
             "source_matrix_tier": "live feed", "sha256": request["document"]["sha256"],
             "bytes": doc.stat().st_size, "pages": len(index),
             "selection_rationale": "live feed run %s, item %s: triaged relevant: %s" % (run_id, key, verdict["reason"]),
             "feed": {"run_id": run_id, "key": key, "item_id": item["item_id"], "listed_url": item["url"],
                      "extraction_run_id": xrun}}
    queue = folder / inbox.PROPOSALS / ("%s.jsonl" % xrun)
    lines = [json.loads(l) for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()] if queue.exists() else []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "advisory_list.json").write_text(json.dumps({"advisories": [entry]}), encoding="utf-8")
        (tmp / "docs").mkdir()
        shutil.copyfile(doc, tmp / "docs" / entry["file"])
        try:
            props = [gate.Proposal.from_line(d, source_file=queue.name) for d in lines]
            clean, quarantined = gate.recheck(props, advisory_list=tmp / "advisory_list.json",
                                              advisories_dir=tmp / "docs", feed_list=None)
        except (KeyError, TypeError, ValueError) as exc:
            clean, quarantined = [], [_Unreadable(str(exc))]
    for q in quarantined:
        problems.append("%s: a proposal the review gate would quarantine: %s" % (key, q.reason[:160]))
    if any(p.run_id != xrun or p.advisory_id != adv for p in clean):
        problems.append("%s: a queue line names another run or advisory" % key)
    tel = folder / inbox.TELEMETRY / ("%s.jsonl" % xrun)
    s = reconcile.session(tel) if tel.exists() else None
    if s is None or not s["completed"]:
        problems.append("%s: the extraction session's telemetry is missing or never completed" % key)
    elif (s["unterminated"] or s["duplicated"]) and not override:
        problems.append("%s: the extraction session has %d unterminated / %d duplicated tool call(s); accepting it "
                        "needs --override-reconciliation" % (key, len(s["unterminated"]), len(s["duplicated"])))
    copies = {"document": (doc, t["document"]), "record": (record_path, t["record"]), "queue": (queue, t["queue"]),
              "telemetry": (tel, t["telemetry"])}
    return {"key": key, "advisory_id": adv, "entry": entry, "copies": copies, "proposals": len(lines)}, problems


def plan(run_id: str, decisions: dict, *, inbox_root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         data: Path = DATA, advisory_list: Path = ADVISORY_LIST, golden_list: Path = GOLDEN_LIST,
         override: str = None) -> dict:
    """Validate everything and return what to write. Raises ValueError, naming every problem, on any."""
    if not (inbox.run_dir(run_id, inbox_root) / inbox.ITEMS).exists():
        raise ValueError("run %s has no %s in the inbox" % (run_id, inbox.ITEMS))
    state = inbox.load(run_id, inbox_root)
    if state.get("eval"):
        raise ValueError("run %s is an eval run; eval runs never reach the ledger" % run_id)
    folder = inbox.run_dir(run_id, inbox_root)
    if (folder / runs.ACCEPTED).exists():
        raise ValueError("run %s was already accepted" % run_id)
    if not isinstance(decisions, dict):
        raise ValueError("the decisions file must be a JSON object of item key -> decision")
    listed = {it["key"]: it for it in inbox.items(state)}
    missing, extra = sorted(set(listed) - set(decisions)), sorted(set(decisions) - set(listed))
    if missing or extra:
        raise ValueError("the decisions must cover every listed item exactly: missing %s, not listed %s"
                         % (missing, extra))
    bad = sorted(k for k, v in decisions.items() if v not in DECISIONS)
    if bad:
        raise ValueError("these decisions are not accept, drop or defer: %s" % bad)
    if override is not None and len(override.strip()) < OVERRIDE_MIN:
        raise ValueError("an override needs a reason of at least %d characters" % OVERRIDE_MIN)
    rec = reconcile.reconcile_run(run_id, inbox_root)
    if rec["status"] == reconcile.REFUSED:
        raise ValueError("run %s was refused before any agent ran; there is nothing to accept" % run_id)
    if rec["status"] not in reconcile.ACCEPTABLE and not override:
        raise ValueError("run %s is %s (%s); accepting it needs --override-reconciliation \"<reason>\"" % (
            run_id, rec["status"], "; ".join(rec["problems"][:3]) or rec["failure"] or "no session"))
    seen = ledger.load(seen_path)
    # Owner ruling A (2026-09-29, C2 Task 0): an item already in the ledger -- decided in an earlier run --
    # is carried as such, not a reason to refuse this whole run (C1 final review I-3: two runs listing the
    # same item could otherwise deadlock, since neither could be accepted nor, under 14 days, expired).
    already_decided = {k: seen[(it["source"], it["item_id"])]["first_seen_run"]
                        for k, it in listed.items() if (it["source"], it["item_id"]) in seen}
    alist = (json.loads(Path(advisory_list).read_text(encoding="utf-8")) if Path(advisory_list).exists()
             else {"schema": FEED_LIST_SCHEMA, "advisories": []})
    golden = json.loads(Path(golden_list).read_text(encoding="utf-8"))["advisories"] if Path(golden_list).exists() else []
    verdicts = rec["verdicts"]
    requests = {r["key"]: r for r in extraction.load_requests(run_id, inbox_root)}
    outcomes = extraction.load_outcomes(run_id, inbox_root)
    allocations = extraction.load_allocations(run_id, inbox_root)
    # An already-decided item cannot be (re-)accepted: that would copy a second record for an item the ledger
    # already closed. A drop or defer for it is not a problem -- it is simply not this run's decision to make --
    # and is excluded below (never re-recorded, never rewritten); main() prints it as a note, not silently.
    problems = ["%s: already decided in %s; a decision file cannot re-accept it" % (k, already_decided[k])
                for k in sorted(already_decided) if decisions[k] == "accept"]
    accepted = []
    for key in sorted(k for k, v in decisions.items() if v == "accept" and k not in already_decided):
        got, why = _check_accepted(run_id, key, listed[key], verdicts.get(key), outcomes.get(key), requests.get(key),
                                   allocations.get(key), folder, Path(data), golden + alist["advisories"], override)
        problems += why
        if got:
            accepted.append(got)
    run_dest = Path(data) / "feeds" / "runs" / run_id
    if run_dest.exists():
        problems.append("%s already exists; nothing is overwritten" % run_dest)
    if problems:
        raise ValueError("; ".join(problems))
    entries = [{"source": listed[k]["source"], "item_id": listed[k]["item_id"], "decision": decisions[k]}
               for k in sorted(listed) if k not in already_decided and decisions[k] != "defer"]
    # Every id this run allocated that no accepted item carries: an extraction that failed after its id was
    # allocated (the one in flight when the run crashed, say), or an extracted item a person deferred or
    # dropped. Never reused; named, so the gap is explained.
    taken = {a["key"] for a in accepted}
    gaps = {k: v for k, v in sorted(allocations.items()) if k not in taken}
    return {"run_id": run_id, "accepted": accepted, "entries": entries, "status": rec["status"],
            "crash": rec["crash"], "problems": rec["problems"], "gaps": gaps, "already_decided": already_decided,
            "deferred": sorted(k for k, v in decisions.items() if v == "defer" and k not in already_decided),
            "run_dest": run_dest,
            "folder": folder, "alist": alist, "override": override}


def default_decision(outcome, verdict) -> str:
    """The interactive default for one item. Accept only what was extracted; drop only what triage called not
    relevant and nothing tried to extract; everything else is deferred, so it comes back next Friday."""
    status = (outcome or {}).get("status")
    if status == "extracted":
        return "accept"
    if status is None and verdict == "not_relevant":
        return "drop"
    return "defer"  # failed, deferred for budget, relevant but never queued, or unfinished


def default_decisions(run_id: str, inbox_root: Path = inbox.INBOX_ROOT) -> dict:
    rec = reconcile.reconcile_run(run_id, inbox_root)
    outcomes = extraction.load_outcomes(run_id, inbox_root)
    return {it["key"]: default_decision(outcomes.get(it["key"]), rec["verdicts"].get(it["key"], {}).get("verdict"))
            for it in inbox.items(inbox.load(run_id, inbox_root))}


def already_decided_note(already_decided: dict, decisions: dict) -> str:
    """The note M-3 asks for: an already-decided item's drop or defer is IGNORED, not silently -- this names
    this run's own (overridden) decision for it and the run that actually decided it. "" (falsy) when there
    is nothing to carry, so callers can just `if note: print(note)`. An "accept" never reaches here: plan()
    refuses the whole run first (an already-decided item cannot be re-accepted)."""
    if not already_decided:
        return ""
    return "ALREADY DECIDED (ignored, with a note): %d item(s) carried from an earlier run, untouched -- this " \
           "run's own decision for each is overridden: %s" % (
               len(already_decided), ", ".join(
                   "%s (this run said %r, decided in %s)" % (k, decisions.get(k), v)
                   for k, v in sorted(already_decided.items())))


def _mkdir(folder: Path, made: list) -> None:
    """mkdir -p that remembers every folder it CREATED, so a rollback removes exactly those and nothing that
    was already there. A folder left behind would block the retry (plan refuses an existing run folder)."""
    missing, f = [], Path(folder)
    while not f.exists():
        missing.append(f)
        f = f.parent
    for f in reversed(missing):
        f.mkdir()
        made.append(f)


def counts(advisories: list) -> dict:
    """The live-feed list's counts, DERIVED from its entries on every write, never edited by hand."""
    by_source: dict = {}
    for a in advisories:
        by_source[a["source_type"]] = by_source.get(a["source_type"], 0) + 1
    return {"advisories": len(advisories), "by_source_type": dict(sorted(by_source.items()))}


class MarkerNotWritten(Exception):
    """The acceptance IS recorded -- copies, advisory list and ledger all written -- but the inbox marker
    (inbox/<run_id>/accepted.json) is not. Nothing is rolled back: the ledger is the commit point."""


def _write_new(dst: Path, created: list, fill) -> None:
    """Create `dst` EXCLUSIVELY ("xb": never overwrite, re-proved at write time, not only by plan()), register it
    for rollback BEFORE a single byte is written, then fill it. A failure mid-write (disk full, an I/O error,
    Ctrl-C) leaves a truncated file the rollback knows about and removes, so a retry is never blocked by it."""
    with open(dst, "xb") as out:
        created.append(dst)
        fill(out)


def _copy_new(src: Path, dst: Path, created: list) -> None:
    def fill(out):
        with open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
    _write_new(dst, created, fill)


def apply(p: dict, today: date, *, inbox_root: Path, seen_path: Path, advisory_list: Path) -> None:
    """Write the plan. Any failure BEFORE the ledger is written removes every file and folder this call made and
    restores the advisory list byte for byte, then re-raises. A failure AFTER it (only the inbox marker is left)
    raises MarkerNotWritten, naming the one-copy recovery."""
    created, made = [], []
    original = Path(advisory_list).read_bytes() if Path(advisory_list).exists() else None
    try:
        for a in p["accepted"]:
            for src, dst in a["copies"].values():
                _mkdir(dst.parent, made)
                _copy_new(src, dst, created)
        dest = p["run_dest"]
        record = {"run_id": p["run_id"], "decided_on": today.isoformat(), "status": p["status"],
                  "override_reconciliation": p["override"],
                  "reconciliation": {"crash": p["crash"], "problems": p["problems"]},
                  "accepted": {a["key"]: a["advisory_id"] for a in p["accepted"]},
                  "dropped": sorted("%s:%s" % (e["source"], e["item_id"]) for e in p["entries"] if e["decision"] == "drop"),
                  "deferred": p["deferred"],
                  "already_decided": p["already_decided"],
                  "already_decided_note": "decided in an earlier run, named here by that run's id: never "
                                          "re-recorded and not a decision of this run (owner ruling A, 2026-09-29)",
                  "allocated_not_accepted": p["gaps"],
                  "allocated_not_accepted_note": "allocated when an extraction started and carried by no accepted "
                                                 "record: never reused (owner decision 11)"}
        _mkdir(dest, made)
        for name in RUN_FILES:
            if (p["folder"] / name).exists():
                _copy_new(p["folder"] / name, dest / name, created)
        orchestrator = p["folder"] / inbox.TELEMETRY / ("%s.jsonl" % p["run_id"])
        if orchestrator.exists():
            _mkdir(dest / "telemetry", made)
            _copy_new(orchestrator, dest / "telemetry" / orchestrator.name, created)
        body = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_new(dest / runs.ACCEPTED, created, lambda out: out.write(body))
        if p["accepted"]:
            advisories = p["alist"]["advisories"] + [a["entry"] for a in p["accepted"]]
            alist = dict(p["alist"], schema=FEED_LIST_SCHEMA, counts=counts(advisories), advisories=advisories)
            _mkdir(Path(advisory_list).parent, made)
            Path(advisory_list).write_text(json.dumps(alist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ledger.record_decisions(p["run_id"], today.isoformat(), p["entries"], path=seen_path)
    except BaseException:
        for path in reversed(created):
            if path.exists():
                path.unlink()
        if original is None:
            if Path(advisory_list).exists():
                Path(advisory_list).unlink()
        else:
            Path(advisory_list).write_bytes(original)
        for folder in reversed(made):
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        raise
    try:
        runs.mark_accepted(p["run_id"], record, inbox_root)
    except Exception as exc:  # after the ledger: nothing to roll back, and the owner must be told how to finish
        marker = inbox.run_dir(p["run_id"], inbox_root) / runs.ACCEPTED
        raise MarkerNotWritten(
            "the acceptance of run %s IS recorded (copies, advisory list and ledger written), but its inbox marker "
            "could not be written (%s: %s). Until it exists the run reads as pending and blocks the next Friday. "
            "Recover with one copy -- nothing else is needed:\n    cp %s %s"
            % (p["run_id"], type(exc).__name__, exc, dest / runs.ACCEPTED, marker)) from exc


def ask(run_id: str, inbox_root: Path, seen_path: Path = ledger.SEEN_PATH) -> dict:
    """The interactive form: the report, then one decision per item, with the evidence's default. An item
    already decided in an earlier run (owner ruling A, 2026-09-29) is shown as such and asked nothing about --
    its decisions.json entry is "defer", which plan() ignores for it (never re-recorded)."""
    folder = inbox.run_dir(run_id, inbox_root)
    report = folder / "report.md"
    print(report.read_text(encoding="utf-8") if report.exists() else "(no report.md)")
    rec = reconcile.reconcile_run(run_id, inbox_root)
    outcomes = extraction.load_outcomes(run_id, inbox_root)
    seen = ledger.load(seen_path)
    decisions = {}
    for it in inbox.items(inbox.load(run_id, inbox_root)):
        k = it["key"]
        seen_key = (it["source"], it["item_id"])
        if seen_key in seen:
            print("%s  %s\n   already decided in %s -- nothing asked" % (k, it["title"][:90], seen[seen_key]["first_seen_run"]))
            decisions[k] = "defer"
            continue
        v = rec["verdicts"].get(k, {}).get("verdict")
        default = default_decision(outcomes.get(k), v)
        answer = input("%s  %s\n   verdict %s, extraction %s  [a]ccept/[d]rop/de[f]er (default %s): " % (
            k, it["title"][:90], v, outcomes.get(k, {}).get("status", "-"), default)).strip().lower()
        decisions[k] = {"a": "accept", "d": "drop", "f": "defer", "": default}.get(answer[:1], answer)
    path = folder / "decisions.json"
    path.write_text(json.dumps(decisions, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("decisions written to %s" % path)
    return decisions


def seed_catalogue(today: date, seen_path: Path, catalogue: Path = CATALOGUE, dry_run: bool = False) -> int:
    raw = Path(catalogue).read_bytes()
    items = json.loads(raw)["items"]
    run_label = "catalogue:%s" % hashlib.sha256(raw).hexdigest()[:12]
    entries = [{"source": it["source"], "item_id": it["item_id"], "decision": "drop"} for it in items]
    seen = ledger.load(seen_path)
    already = sorted("%s:%s" % (e["source"], e["item_id"]) for e in entries if (e["source"], e["item_id"]) in seen)
    if already:
        print("REFUSED: %d catalogue item(s) are already decided, e.g. %s" % (len(already), already[0]))
        return 1
    if dry_run:
        print("DRY RUN: would record %d catalogue item(s) as drops under %s" % (len(entries), run_label))
        return 0
    ledger.record_decisions(run_label, today.isoformat(), entries, path=seen_path)
    print("RECORDED: %d catalogue item(s) as drops under %s in %s" % (len(entries), run_label, seen_path))
    return 0


def main(argv: list, *, inbox_root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         today: date = None, data: Path = DATA, advisory_list: Path = ADVISORY_LIST, golden_list: Path = GOLDEN_LIST,
         catalogue: Path = CATALOGUE) -> int:
    ap = argparse.ArgumentParser(description="Decide the items of one feeds run")
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--decisions", type=Path, help="JSON: item key -> accept | drop | defer")
    ap.add_argument("--dry-run", action="store_true", help="validate and say what would be written")
    ap.add_argument("--override-reconciliation", metavar="REASON", help="accept a FAILED or RECONCILIATION_FAILED run")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--expire", action="store_true")
    ap.add_argument("--seed-catalogue", action="store_true")
    args = ap.parse_args(argv)
    today = today or date.today()
    if args.seed_catalogue:
        return seed_catalogue(today, seen_path, catalogue, args.dry_run)
    if args.pending:
        for r in runs.run_ids(inbox_root):
            print("%-26s %s" % (r, runs.classify(r, inbox_root)))
        return 0
    if args.expire:
        from tools.friday_run import LOCK, run_lock  # the Friday run's OWN lock, never a second copy of it
        with run_lock(inbox_root) as held:
            if not held:
                print("REFUSED: a Friday run holds %s; expiring moves run folders that its advisory-id allocation "
                      "reads -- wait for it to finish" % (Path(inbox_root) / LOCK))
                return 1
            todo = [(args.run_id, None)] if args.run_id else runs.expirable(inbox_root, today)
            for r, _ in todo:
                try:
                    print("EXPIRED: %s -> %s" % (r, runs.expire(r, inbox_root, today)))
                except ValueError as exc:
                    print("REFUSED: %s" % exc)
                    return 1
        return 0
    if not args.run_id:
        ap.error("RUN_ID is required")
    from tools.friday_run import LOCK, run_lock  # the Friday run's OWN lock, never a second copy of it
    with run_lock(inbox_root) as held:
        if not held:
            print("REFUSED: a Friday run holds %s; accepting a run reads every run's allocations and would "
                  "snapshot them mid-write -- wait for it to finish" % (Path(inbox_root) / LOCK))
            return 1
        try:
            decisions = (json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions
                         else ask(args.run_id, inbox_root, seen_path))
            p = plan(args.run_id, decisions, inbox_root=inbox_root, seen_path=seen_path, data=data,
                     advisory_list=advisory_list, golden_list=golden_list, override=args.override_reconciliation)
        except (ValueError, OSError) as exc:
            print("REFUSED: %s" % exc)
            return 1
        what = "%d accepted (%s), %d dropped, %d deferred, %d already decided" % (
            len(p["accepted"]), ", ".join(a["advisory_id"] for a in p["accepted"]) or "-",
            sum(1 for e in p["entries"] if e["decision"] == "drop"), len(p["deferred"]), len(p["already_decided"]))
        note = already_decided_note(p["already_decided"], decisions)
        if args.dry_run:
            print("DRY RUN: would record %d decision(s) for run %s: %s" % (len(p["entries"]), args.run_id, what))
            if note:
                print(note)
            return 0
        if not args.decisions and input("Apply: %s? [y/N] " % what).strip().lower() != "y":
            print("NOTHING WRITTEN")
            return 1
        try:
            apply(p, today, inbox_root=inbox_root, seen_path=seen_path, advisory_list=advisory_list)
        except MarkerNotWritten as exc:
            print("RECORDED, BUT NOT MARKED: %s" % exc)
            return 2
        except (ValueError, OSError) as exc:
            print("REFUSED: %s -- every copy this call made was removed; nothing is recorded" % exc)
            return 1
        print("RECORDED: %d decision(s) for run %s in %s: %s. Commit, then review the proposals with "
              "tools/review.py." % (len(p["entries"]), args.run_id, seen_path, what))
        if note:
            print(note)
        if p["gaps"]:
            print("GAP: %d allocated advisory id(s) carried by no accepted record, never reused: %s" % (
                len(p["gaps"]), ", ".join("%s (%s)" % (v, k) for k, v in p["gaps"].items())))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
