"""
One Friday run (spec sections 1 and 2): the orchestrator session, then extraction IN CODE within the budget,
then reconciliation in code, then inbox/<run_id>/report.md -- on every run, refused and failed included.

Usage:
    python tools/friday_run.py           # one live run now (sub-project C1: the manual dry runs)
    python tools/friday_run.py --plan    # print the budget and the caps; start nothing, spend nothing

THE BUDGET (agents/orchestrate_feeds.py, pinned by evals/check_feeds_orchestrator.py). The orchestrator
session is capped at MAX_BUDGET_USD. Then each queued item, in the order the agent queued it: an extraction
starts only if the spend so far plus EXTRACTION_BUDGET_USD stays within RUN_CEILING_USD; otherwise the item
is DEFERRED FOR BUDGET (no advisory id is allocated, and accept_run defers it to next Friday). Each
extraction is slice 1's agents/extract_advisory.extract, unchanged in its gate, propose_link, citations and
telemetry, with its OWN run identity naming this feeds run, so its queue and telemetry land in this run's
inbox. A cost that never arrived (the SDK raised before its result) is counted at the session's cap. At
most extraction.MAX_PER_RUN requests are extracted: request() refuses a fourth, and friday() re-checks it.

friday() points telemetry.TELEMETRY_DIR at inbox/<run_id>/telemetry/ for the run and restores it after, so
every session's telemetry lands in the run whoever calls it. Whatever raises inside the run -- the session,
an allocation, an extraction -- run.json and report.md are still written: the run is FAILED, and run.json's
"crash" names the exception.

WRITES only inbox/<run_id>/ (gitignored): run.json, advisory_ids.jsonl, extraction_runs.jsonl, records/,
proposals/, telemetry/, report.md. Nothing tracked changes; tools/accept_run.py is the only way in.

REFUSES before any agent runs, with a refusal report (refusal.json + report.md) and exit 1, when:
  ANTHROPIC_API_KEY is set (it takes precedence over the subscription token: CLAUDE.md, Auth);
  FEEDS_CATALOGUE or FEEDS_CATALOGUE_BATCH is set (an eval catalogue in the shell; B carry-forward);
  another Friday run holds the inbox's lock (inbox/.friday.lock).

ONE FRIDAY RUN AT A TIME. friday() holds an exclusive flock on <inbox root>/.friday.lock across the session,
every advisory-id allocation and every extraction, and refuses when it cannot take it. Allocation
(feeds/extraction.py) reads every run's ids and then appends; its re-check narrows that window but cannot
close it, and back-pressure (feeds.runs.blocking) cannot either -- two runs started together both see no
pending run. The lock closes it, and it is taken in friday() rather than main() so every caller passes
through it. flock is released by the kernel when the process exits: a crash leaves no stale lock.
With --scheduled (C2; scripts/schedule/friday_run.sh passes it) it also refuses, through the same path, when
feeds/preflight.py finds the checkout off main, a checkout that is not the marked schedule clone
(<git-dir>/fc08-schedule-clone, re-review R-1), an unaccepted run under 14 days old, or auth that is not the
long-lived token -- and whatever friday_run.sh itself refused (--refuse REASON, e.g. no token in the Keychain).
Then it posts ONE notification, the report's first two lines (feeds/notify.py).

THE EXIT-CODE CONTRACT WITH friday_run.sh (fix round 1, I-1/I-2): every exit path posts exactly one
notification, and the exit code is how the two sides agree on who posted it.
  0                     the run was ACCEPTABLE and Python's own notification was posted;
  SCHEDULED_NOTIFIED_EXIT (10)  the run was REFUSED/FAILED and Python's own notification was posted;
  anything else (1, 2, 3, ...)  Python posted NOTHING -- friday_run.sh must post the one notification itself.
1 means notify() itself returned False (logged, not raised); 2 is argparse's own exit for a bad flag; 3 is a
crash caught below, which deliberately posts nothing itself (friday_run.sh's notify() covers it); an
import-time failure before main() ever runs also exits 1, from the interpreter, and is covered the same way.
The shell side matches on the EXACT reserved code, not on a `>= N` threshold -- 10 is not "less bad" than 3,
it is the one value that means "already handled".

_scheduled orders its own last three steps so nothing that can raise runs between a successful notify() and
the return: the status is computed and printed BEFORE notify() is called, and the return value is computed
from state read before notify() ran, so posting the notification is the last thing that can fail (fix round
2, N-1). The one residual this cannot reach is outside this function's control -- an interpreter-shutdown
stdout flush failure (exit 120), or notify.notify's own subprocess call raising AFTER osascript has already
displayed the notification -- named here rather than claimed fixed, because it isn't fixable from inside
_scheduled.

EXIT 0 for COMPLETE, NOTHING_NEW and UNFINISHED (a person decides the rest); 1 for REFUSED, FAILED and
RECONCILIATION_FAILED -- this is the PLAIN (non-scheduled) run's own exit code, separate from the
--scheduled contract above: a plain refusal exits 1, a *scheduled* one exits SCHEDULED_NOTIFIED_EXIT (10).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agents import orchestrate_feeds as of, telemetry  # noqa: E402
from feeds import extraction, inbox, notify, preflight, reconcile, report  # noqa: E402
from feeds.runs import run_date  # noqa: E402

# Every list an advisory id may already be in: the golden corpus and the accepted live-feed advisories. Every id
# any run ALLOCATED is also read, from the inbox and from accepted runs' tracked copies (extraction.TRACKED_RUNS);
# friday(tracked_runs=...) points a guard at a temporary one.
ADVISORY_LISTS = (ROOT / "evals" / "golden" / "advisory_list.json", ROOT / "data" / "feeds" / "advisory_list.json")
EVAL_VARIABLES = ("FEEDS_CATALOGUE", "FEEDS_CATALOGUE_BATCH")
LOCK = ".friday.lock"
LOCKED = ("another Friday run holds %s; two runs at once could allocate the same advisory id -- wait for it "
          "to finish")
# The one reserved --scheduled exit code: "Python already posted the one notification for a run that was not
# acceptable". scripts/schedule/friday_run.sh checks for this EXACT value (fix round 1, I-1); see the exit-code
# contract in the module docstring above.
SCHEDULED_NOTIFIED_EXIT = 10


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def counted(cost: Optional[float], cap: float) -> float:
    """What a session counts against the ceiling: its reported cost, or its cap when none arrived."""
    return cap if cost is None else cost


def may_start(spent: float) -> bool:
    """Spec section 1: an extraction starts only if the spend so far plus its budget stays within the ceiling."""
    return spent + of.EXTRACTION_BUDGET_USD <= of.RUN_CEILING_USD + 1e-9


def _save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


async def extract_one(run: of.FeedsRun, request: dict, advisory_id: str, root: Path) -> dict:
    """Slice 1's extraction on the pinned document, with its own identity; the outcome, never an exception."""
    from agents import extract_advisory
    from agents.run_identity import RunIdentity
    folder = inbox.run_dir(run.run_id, root)
    doc = folder / request["document"]["path"]
    out = {"key": request["key"], "advisory_id": advisory_id, "extraction_run_id": None, "document_sha256": None,
           "started_at": _now(), "status": None, "error": None, "record": None, "cost_usd": None}
    try:
        ident = RunIdentity.new("extractor", advisory_id, doc, feeds_run=run.run_id, inbox_root=root)
    except Exception as exc:  # a document that cannot be hashed is this extraction's failure, not the run's
        out.update(status="failed", error=("%s: %s" % (type(exc).__name__, exc))[:500], cost_usd=0.0)
        return out
    out.update(extraction_run_id=ident.run_id, document_sha256=ident.pdf_sha256)
    try:
        record, _ = await extract_advisory.extract(doc, advisory_id, of.MODEL, of.EXTRACTION_BUDGET_USD,
                                                   of.EXTRACTION_MAX_TURNS, run=ident)
        rel = "%s/%s.json" % (inbox.RECORDS, advisory_id)
        inbox.write_file(run.run_id, rel, record.model_dump_json(indent=2).encode("utf-8"), root)
        out.update(status="extracted", record=rel)
    except Exception as exc:  # recorded: an extraction that fails is reported, never raised past the run
        out.update(status="failed", error=("%s: %s" % (type(exc).__name__, exc))[:500])
    out["cost_usd"] = reconcile.session_cost(telemetry.telemetry_path(ident))
    return out


@contextlib.contextmanager
def run_lock(root: Path = inbox.INBOX_ROOT):
    """The inbox's exclusive Friday lock, never waited for: yields True when held, False when another
    process (or another open of it in this one) holds it. Released on exit, and by the kernel on a crash."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(root / LOCK), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


async def friday(run: of.FeedsRun, session=None, extractor=None, root: Path = inbox.INBOX_ROOT,
                 advisory_list=ADVISORY_LISTS, tracked_runs: Path = extraction.TRACKED_RUNS) -> dict:
    """The whole run under the inbox's lock; a run that cannot take it is REFUSED before its session."""
    if session is None and Path(root).resolve() != Path(inbox.INBOX_ROOT).resolve():
        # The live feeds server writes inbox.INBOX_ROOT and nothing else: a session there, read from here,
        # would reconcile a folder the agent never wrote. Another root is for stub sessions only.
        raise ValueError("the live session writes %s; a run over %s needs its own session" % (inbox.INBOX_ROOT, root))
    with run_lock(root) as held:
        if not held:
            return write_refusal(run.run_id, [LOCKED % (Path(root) / LOCK)], root)
        return await _locked_friday(run, session or of.run_session, extractor or extract_one, root, advisory_list,
                                    tracked_runs)


async def _locked_friday(run: of.FeedsRun, session, extractor, root: Path, advisory_list,
                         tracked_runs: Path = extraction.TRACKED_RUNS) -> dict:
    """The run itself. Whatever raises in here, run.json and report.md are still written (spec section 2: a
    report on EVERY run), the run is FAILED and the report names the exception."""
    started = _now()
    summary: dict = {}
    crash: Optional[str] = None
    spent = of.MAX_BUDGET_USD  # the session counts at its cap until its cost arrives
    previous_dir = telemetry.TELEMETRY_DIR
    # Every session this run starts -- the orchestrator and each extraction -- writes its telemetry into the
    # run's own folder, whoever called friday(): never data/telemetry/, which reconcile_run does not read.
    telemetry.TELEMETRY_DIR = inbox.run_dir(run.run_id, root) / inbox.TELEMETRY
    try:
        summary = await session(run)
        spent = counted(summary.get("cost_usd"), of.MAX_BUDGET_USD)
        if summary.get("failure") is None:
            for position, req in enumerate(extraction.load_requests(run.run_id, root)):
                if position >= extraction.MAX_PER_RUN:
                    # request() refuses a fourth; this is defence in depth, and reconcile_run reports the line.
                    outcome = {"key": req["key"], "status": "failed", "cost_usd": 0.0,
                               "error": "request %d of a run that extracts at most %d; not extracted" % (
                                   position + 1, extraction.MAX_PER_RUN)}
                elif req.get("error") or not req.get("document"):
                    outcome = {"key": req["key"], "status": "failed", "error": req.get("error") or "no document",
                               "cost_usd": 0.0}
                elif not may_start(spent):
                    outcome = {"key": req["key"], "status": "deferred_budget", "cost_usd": 0.0,
                               "error": "US$%.2f spent; US$%.2f more would pass the US$%.2f ceiling" % (
                                   spent, of.EXTRACTION_BUDGET_USD, of.RUN_CEILING_USD)}
                else:
                    advisory_id = extraction.allocate_advisory_id(run.run_id, req["key"], run_date(run.run_id).year,
                                                                  advisory_list, root, tracked_runs)
                    spent += of.EXTRACTION_BUDGET_USD  # counted at its cap while it runs, in case it raises
                    outcome = await extractor(run, req, advisory_id, root)
                    spent += counted(outcome.get("cost_usd"), of.EXTRACTION_BUDGET_USD) - of.EXTRACTION_BUDGET_USD
                extraction.append_outcome(run.run_id, outcome, root)
    except Exception as exc:  # a report on EVERY run: a crashed one is FAILED and says why
        crash = ("the run raised %s: %s" % (type(exc).__name__, exc))[:500]
    finally:
        telemetry.TELEMETRY_DIR = previous_dir
    unrecorded = None
    if crash is not None and summary.get("failure") is None:
        unrecorded = record_crash(run.run_id, "the run crashed before this item was extracted (%s)" % (
            crash[len("the run raised "):]), root)
    _save(inbox.run_dir(run.run_id, root) / reconcile.RUN_JSON,
          {"run_id": run.run_id, "started_at": started, "ended_at": _now(),
           "failure": summary.get("failure") or crash, "crash": crash, "unrecorded": unrecorded,
           "limit": summary.get("limit"), "orchestrator_cost_usd": summary.get("cost_usd"), "spent_usd": round(spent, 6),
           "ceiling_usd": of.RUN_CEILING_USD, "prompt_sha256": of.FULL_PROMPT_SHA256, "model": of.MODEL})
    report.write(run.run_id, root)
    return reconcile.reconcile_run(run.run_id, root)


def record_crash(run_id: str, reason: str, root: Path) -> Optional[str]:
    """After a crash, give every queued request that has no outcome yet -- the one in flight and every one not
    reached -- a FAILED outcome naming the crash, so each is reported unfinished and returns next Friday.
    Allocates nothing: an id the in-flight item already held stays allocated (never reused) and is named on
    its outcome. A request that already has an outcome (the crash came after its append) is left alone.
    Returns None, or why recording failed; the caller puts that in run.json and reconcile_run reports it."""
    try:
        allocations = extraction.load_allocations(run_id, root)
        done = extraction.load_outcomes(run_id, root)
        for req in extraction.load_requests(run_id, root):
            if req["key"] in done:
                continue
            started = req["key"] in allocations  # it held an id, so it started: its cost is unknown, not zero
            extraction.append_outcome(run_id, {"key": req["key"], "status": "failed",
                                               "cost_usd": None if started else 0.0,
                                               "advisory_id": allocations.get(req["key"]), "error": reason}, root)
    except Exception as exc:  # recording must not crash the crash path: the report is still written
        return ("%s: %s" % (type(exc).__name__, exc))[:500]
    return None


def write_refusal(run_id: str, reasons: list, root: Path = inbox.INBOX_ROOT) -> dict:
    """A refused run still gets a folder, refusal.json and report.md -- and never lists, fetches or spends."""
    _save(inbox.run_dir(run_id, root) / reconcile.REFUSAL, {"run_id": run_id, "refused_at": _now(), "reasons": reasons})
    report.write(run_id, root)
    return reconcile.reconcile_run(run_id, root)


def refusals(env=None) -> list:
    env = os.environ if env is None else env
    out = []
    if env.get("ANTHROPIC_API_KEY"):
        out.append("ANTHROPIC_API_KEY is set; it takes precedence over the subscription token -- unset it")
    for name in EVAL_VARIABLES:
        if env.get(name):
            out.append("%s is set in the environment; a Friday run is never an eval run -- unset it" % name)
    return out


def main(argv: list, root: Path = inbox.INBOX_ROOT, today: date = None, extra_refusals=None,
         preflight_reasons=None, notifier=None) -> int:
    ap = argparse.ArgumentParser(description="One Friday feeds run")
    ap.add_argument("--plan", action="store_true", help="print the budget and caps; start nothing")
    ap.add_argument("--scheduled", action="store_true", help="launchd: run the preflight, then post one notification")
    ap.add_argument("--refuse", action="append", default=[], metavar="REASON",
                    help="a refusal friday_run.sh found before Python started (repeatable)")
    args = ap.parse_args(argv)
    if args.scheduled:
        try:
            return _scheduled(args, root, today, extra_refusals, preflight_reasons, notifier)
        except Exception:  # noqa: BLE001 -- posts NO notification of its own; friday_run.sh posts the one instead
            import traceback
            traceback.print_exc()
            return 3
    if args.plan:
        print("orchestrator: US$%.2f, %d turns; extraction: US$%.2f, %d turns each, at most %d; ceiling US$%.2f"
              % (of.MAX_BUDGET_USD, of.MAX_TURNS, of.EXTRACTION_BUDGET_USD, of.EXTRACTION_MAX_TURNS,
                 extraction.MAX_PER_RUN, of.RUN_CEILING_USD))
        return 0
    run = of.FeedsRun(inbox.mint_run_id(today or date.today()))
    reasons = refusals() + list(extra_refusals or [])
    rec = write_refusal(run.run_id, reasons, root) if reasons else asyncio.run(friday(run, root=root))
    print("%s: %s -- %s" % (run.run_id, rec["status"], inbox.run_dir(run.run_id, root) / report.REPORT))
    return 0 if rec["status"] in reconcile.ACCEPTABLE else 1


def _scheduled(args, root, today, extra_refusals, preflight_reasons, notifier) -> int:
    run = of.FeedsRun(inbox.mint_run_id(today or date.today()))
    telemetry.TELEMETRY_DIR = inbox.run_dir(run.run_id, root) / inbox.TELEMETRY
    found = preflight.reasons(ROOT, root, today) if preflight_reasons is None else list(preflight_reasons)
    reasons = refusals() + list(extra_refusals or []) + list(args.refuse) + found
    rec = write_refusal(run.run_id, reasons, root) if reasons else asyncio.run(friday(run, root=root))
    path = inbox.run_dir(run.run_id, root) / report.REPORT
    # Fix round 2, N-1: everything that can raise -- including this print -- runs BEFORE notify() is called, and
    # `acceptable` is a plain bool computed before it too. Once notify() has returned True, nothing remains that
    # can raise and turn one posted notification into two (Python's own plus the shell's fallback).
    acceptable = rec["status"] in reconcile.ACCEPTABLE
    print("%s: %s -- %s" % (run.run_id, rec["status"], path))
    posted = (notifier or notify.notify)(*notify.from_report(path))
    if not posted:
        print("NOTIFICATION FAILED: friday_run.sh will post the one notification instead", file=sys.stderr)
        return 1
    return 0 if acceptable else SCHEDULED_NOTIFIED_EXIT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
