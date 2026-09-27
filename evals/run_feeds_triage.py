"""
Run the triage-only orchestrator over the back-catalogue: one repeat is one session per batch.

Usage:
    python evals/run_feeds_triage.py --repeat rep1 --pilot   # ONE session (the first batch), then stop
    python evals/run_feeds_triage.py --repeat rep1           # every batch not yet done; resumes after a failure
    python evals/run_feeds_triage.py --repeat rep1 --after-fix  # one more attempt at a STOPPED batch
    python evals/run_feeds_triage.py --plan                  # print the batches; no session, no model

A REPEAT. The catalogue's scored items, the three sources interleaved (ofsi, fincen, ofac, ofsi, ...)
in catalogue order and cut into batches of at most feeds.triage.MAX_PER_RUN (10) -- batch-1 to batch-6
for 59 or 60 items -- one orchestrator session (agents/orchestrate_feeds.py) in eval mode per batch.
Interleaved, because a Friday run's new items arrive mixed: a session of ten OFAC designations would
measure a situation production never presents. The batches are the same in every repeat. When every
batch has a completed session the repeat is written to evals/feeds/repeats/<rep>.json, TRACKED, and
each session's telemetry is under evals/feeds/repeats/<rep>/telemetry/, TRACKED. Until then progress
is kept in evals/feeds/repeats/.progress/<rep>.json (gitignored), so a failed session is re-run alone.

REFUSES TO START when:
  - the repeat's record already exists (evidence is never overwritten);
  - ANTHROPIC_API_KEY is set: it takes precedence over the subscription token (CLAUDE.md, Auth);
  - catalogue.json or labels.json is untracked or differs from HEAD: the draft labels are frozen
    before the first repeat, and the record names both by sha256;
  - a catalogue document is missing, or its bytes do not hash to the catalogue's sha256;
  - the progress file was started under a different prompt, model, budget, catalogue or labels.

A session whose agent FAILED (is_error, or the SDK raised) does not advance the progress: it is kept
under failed_attempts and the command is simply run again. A session that ran and left items
unfinished DID complete: skipping is triage behaviour, and it is measured, never retried away.

A FAILURE NAMES ITS ERROR AND ITS COST, AND A REPEATED FAILURE STOPS THE RUNNER (Task 4 review
ruling; Task 7 review, fix round 1). Each failed attempt records `error` -- "<Type>: <message>", as
run_triage returns it, or as the runner caught it with its traceback when the session itself raised --
`error_kind` ("sdk" for the SDK's own errors and an agent error result, "code" otherwise; recorded for
the reader, it decides nothing) and `cost_usd` where it is known. The FAILED line prints that cost.
A batch is STOPPED (Task 7 review, fix round 2) when
  - its newest failure matches ANY earlier failure of the batch since the last --after-fix -- not only
    the one before it, so alternating failures A, B, A stop at the third -- of ANY kind: an agent error
    result arrives after paid turns and its prefix cannot tell a machine problem from a bug; or
  - it has failed MAX_FAILED_ATTEMPTS (3) times since the last --after-fix, whatever the errors.
"Matches" compares errors after normalise() strips run ids, tool-use ids, addresses, paths and numbers.
A STOPPED batch is refused until the cause is fixed and the command is run once with --after-fix,
which permits exactly one more attempt. That attempt tests the fix, so it is compared with every
earlier failure of the batch: failing the old way stops it again at once; failing a new way opens a
fresh window, capped at 3 like the first.

AND IT NEVER RUNS A BATCH TWICE BY ACCIDENT:
  - one invocation per repeat at a time: an exclusive lock on .progress/<rep>.lock, released on exit;
  - a session's telemetry the progress file does not account for -- the progress file was lost, or a
    run died before saving -- REFUSES the run: those batches were done or attempted and are never
    re-run blind; the message names the batch and the run id;
  - a second --pilot refuses rather than silently becoming batch-2's session.
Guarded by evals/check_feeds_runner.py, which drives this file with stub sessions and never a model.

MODEL RUNS. The only file in sub-project B that starts agent sessions. check_all never runs it.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import claude_agent_sdk  # noqa: E402
from agents import orchestrate_feeds as of, telemetry  # noqa: E402
from feeds import inbox, triage as feeds_triage  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
LABELS = EVAL_DIR / "labels.json"
DOCS = EVAL_DIR / "docs"
REPEATS_DIR = EVAL_DIR / "repeats"
PROGRESS_DIR = REPEATS_DIR / ".progress"
SCHEMA = "fc08-triage-repeat/1"
REPEATS = ("rep1", "rep2", "rep3")
SOURCES = ("ofsi", "fincen", "ofac")
# The SDK's own exception classes, read from the SDK rather than listed, so a new one is "sdk" too.
SDK_ERRORS = frozenset(n for n in dir(claude_agent_sdk) if isinstance(getattr(claude_agent_sdk, n), type)
                       and issubclass(getattr(claude_agent_sdk, n), claude_agent_sdk.ClaudeSDKError))
AGENT_FAILED = "agent run failed:"  # run_triage's prefix for an error ResultMessage from the agent
MAX_FAILED_ATTEMPTS = 3  # per batch, since the last --after-fix, whatever the errors


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def batches(catalogue: dict) -> list:
    per = [[it["key"] for it in catalogue["items"] if it["source"] == s] for s in SOURCES]
    mixed = [k for row in itertools.zip_longest(*per) for k in row if k]
    size = feeds_triage.MAX_PER_RUN
    return [("batch-%d" % (n + 1), mixed[i:i + size]) for n, i in enumerate(range(0, len(mixed), size))]


def identity() -> dict:
    return {"prompt_sha256": of.PROMPT_SHA256, "model": of.MODEL, "max_budget_usd": of.MAX_BUDGET_USD,
            "max_turns": of.MAX_TURNS, "catalogue_sha256": _sha(CATALOGUE), "labels_draft_sha256": _sha(LABELS)}


def _committed(path: Path) -> bool:
    rel = str(Path(path).relative_to(ROOT))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=ROOT).returncode == 0
    return tracked and clean


def record_written(rep: str) -> bool:
    """The repeat's record exists: it is written once and never overwritten."""
    return (REPEATS_DIR / ("%s.json" % rep)).exists()


def preflight(rep: str, catalogue: dict) -> list:
    problems = []
    if record_written(rep):
        problems.append("%s.json exists; a repeat is never overwritten" % rep)
    if os.environ.get("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY is set; unset it so the run uses the subscription token")
    for path in (CATALOGUE, LABELS):
        if not path.exists() or not _committed(path):
            problems.append("%s is missing, untracked or differs from HEAD; commit it first" % path.relative_to(ROOT))
    for it in catalogue["items"]:
        doc = DOCS / ("%s.%s" % (it["document"]["sha256"], it["document"]["ext"]))
        if not doc.exists() or _sha(doc) != it["document"]["sha256"]:
            problems.append("the catalogue copy for %s is missing or changed (%s)" % (it["key"], doc.name))
    return problems


def _save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def error_kind(error: str) -> str:
    """"sdk" when the SDK or the agent's own result failed, "code" otherwise. Recorded for the reader of
    failed_attempts; the stop rule does not consult it (an agent error result can be either)."""
    if error.startswith(AGENT_FAILED):
        return "sdk"
    return "sdk" if error.split(":", 1)[0].strip() in SDK_ERRORS else "code"


_VARYING = (
    (re.compile(r"feeds-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}"), "<run>"),
    (re.compile(r"toolu_[A-Za-z0-9]+"), "<tool_use>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"(?:[A-Za-z]:)?(?:[\w.~-]*/)+[\w.~-]*"), "<path>"),
    (re.compile(r"\b[0-9a-f]{16,}\b"), "<hex>"),
    (re.compile(r"\d+(?:\.\d+)?"), "<n>"),
)


def normalise(error: str) -> str:
    """The error with what varies between two attempts of one bug stripped: run ids, tool-use ids,
    addresses, paths, long hex and numbers. The type and the words are what must repeat."""
    for pattern, token in _VARYING:
        error = pattern.sub(token, error)
    return error


def attempt(session, run: of.FeedsRun) -> dict:
    """One session. run_triage records its own failures; if the session RAISES instead (a bug before or
    after the agent loop), the runner records it the same way, with the traceback, rather than dying
    with nothing written -- an unrecorded failure could be re-run without limit. Its cost is unknown:
    the result that carried it did not reach the runner."""
    try:
        return dict(asyncio.run(session(run)))
    except Exception as exc:  # noqa: BLE001 -- recorded, then counted by stop_reason
        return {"run_id": run.run_id, "failure": "%s: %s" % (type(exc).__name__, exc), "raised_in": "runner",
                "traceback": traceback.format_exc(), "cost_usd": None, "turns": None, "limit": None}


def failure_record(summary: dict) -> dict:
    """The failure as kept under failed_attempts: the error's type and message, and its kind."""
    error = str(summary["failure"])
    return dict(summary, error=error, error_kind=error_kind(error))


def _window(failed_attempts: list, batch: str) -> tuple:
    """(this batch's failed attempts, the ones since the last --after-fix, inclusive of that attempt)."""
    mine = [a for a in failed_attempts if a.get("batch") == batch]
    fixes = [i for i, a in enumerate(mine) if a.get("after_fix")]
    return mine, mine[fixes[-1]:] if fixes else mine


def repeated_failure(failed_attempts: list, batch: str) -> Optional[str]:
    """The newest error, when it matches ANY earlier failure of this batch since the last --after-fix (an
    --after-fix attempt is compared with every earlier failure: it tests the fix); else None."""
    mine, window = _window(failed_attempts, batch)
    if not mine:
        return None
    newest = mine[-1]
    earlier = mine[:-1] if newest.get("after_fix") else window[:-1]
    key = normalise(str(newest.get("error", "")))
    return newest.get("error") if key and any(normalise(str(a.get("error", ""))) == key for a in earlier) else None


def at_cap(failed_attempts: list, batch: str) -> bool:
    """MAX_FAILED_ATTEMPTS failures of this batch since the last --after-fix, whatever the errors."""
    return len(_window(failed_attempts, batch)[1]) >= MAX_FAILED_ATTEMPTS


def stop_reason(failed_attempts: list, batch: str) -> Optional[str]:
    same = repeated_failure(failed_attempts, batch)
    if same:
        return "failed again with an error it has failed with before:\n  %s" % str(same)[:500]
    if at_cap(failed_attempts, batch):
        return ("has failed %d times since the last --after-fix, with different errors (the newest: %s)"
                % (MAX_FAILED_ATTEMPTS, str(_window(failed_attempts, batch)[1][-1].get("error"))[:300]))
    return None


def spend(attempts: list) -> tuple:
    """(known US$, how many attempts' cost is unknown)."""
    return (sum(a.get("cost_usd") or 0 for a in attempts), sum(1 for a in attempts if a.get("cost_usd") is None))


def _usd(cost) -> str:
    return "unknown (no result reached the runner)" if cost is None else "US$%.4f" % cost


def _rel(path: Path) -> str:
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def done_line(name: str, run_id: str, summary: dict, keys: list) -> str:
    return "done    %-9s %s  %d/%d triaged, %d unfinished, %d unterminated, %s turns, US$%s" % (
        name, run_id, len(summary["triaged"]), len(keys), len(summary["unfinished"]),
        len((summary.get("terminal_check") or {}).get("unterminated") or []), summary["turns"], summary["cost_usd"])


def _stopped(name: str, reason: str, progress: dict) -> None:
    known, unknown = spend([a for a in progress["failed_attempts"] if a.get("batch") == name])
    print("STOPPED %s %s\n"
          "  Its failed attempts have cost US$%.4f%s. Another attempt would spend again without a decision.\n"
          "  Fix the cause (a bug, or the machine: auth, credit, the CLI), then run once with --after-fix."
          % (name, reason, known, " (and %d of unknown cost)" % unknown if unknown else ""))


def failed_line(name: str, run_id: str, summary: dict, progress: dict) -> str:
    known, unknown = spend(progress["failed_attempts"])
    return ("FAILED  %s %s: %s\n  This attempt cost %s. Failed attempts on this repeat so far: US$%.4f%s.\n"
            "  The batch is not done; run the same command again to retry it. A failure seen before, or a\n"
            "  third failure of this batch, STOPS."
            % (name, run_id, summary["failure"], _usd(summary.get("cost_usd")), known,
               " (and %d of unknown cost)" % unknown if unknown else ""))


def pilot_done(plan: list, progress: dict) -> bool:
    """The pilot IS the first batch; run again, it would silently become batch-2's session."""
    return plan[0][0] in progress["sessions"]


def run_plan(rep: str, plan: list, progress: dict, progress_path: Path, session, today: Optional[date],
             pilot: bool, after_fix: bool = False) -> int:
    if pilot and pilot_done(plan, progress):
        print("PILOT: %s already has a completed session; nothing run" % plan[0][0])
        return 0
    for name, keys in plan:
        if name in progress["sessions"]:
            continue
        stuck = stop_reason(progress["failed_attempts"], name)
        if stuck and not after_fix:
            _stopped(name, stuck, progress)
            return 1
        fixing = bool(stuck)  # the flag was spent on a STOPPED batch: this attempt opens a new window
        after_fix = False  # --after-fix buys exactly one attempt
        run = of.FeedsRun(inbox.mint_run_id(today or date.today()), catalogue=CATALOGUE, batch=tuple(keys))
        summary = dict(attempt(session, run), batch=name, keys=keys)
        if summary["failure"]:
            progress["failed_attempts"].append(dict(failure_record(summary), after_fix=fixing))
            _save(progress_path, progress)
            stuck = stop_reason(progress["failed_attempts"], name)
            if stuck:
                print("FAILED  %s %s: this attempt cost %s." % (name, run.run_id, _usd(summary.get("cost_usd"))))
                _stopped(name, stuck, progress)
                return 1
            print(failed_line(name, run.run_id, summary, progress))
            return 1
        summary["verdicts"] = feeds_triage.load(run.run_id)
        progress["sessions"][name] = summary
        _save(progress_path, progress)
        print(done_line(name, run.run_id, summary, keys))
        if pilot:
            print("PILOT: stopped after one session. Projected for three repeats of %d sessions: US$%.2f"
                  % (len(plan), (summary["cost_usd"] or 0) * len(plan) * len(REPEATS)))
            return 0
    sessions = [progress["sessions"][name] for name, _ in plan]
    verdicts = {k: {f: v[f] for f in ("verdict", "reason", "quote", "found_on", "match", "run_id", "decided_at")}
                for s in sessions for k, v in s["verdicts"].items()}
    record = dict(identity(), schema=SCHEMA, repeat=rep, verdicts=verdicts,
                  failed_attempts=progress["failed_attempts"],
                  sessions=[{f: s[f] for f in s if f != "verdicts"} for s in sessions])
    _save(REPEATS_DIR / ("%s.json" % rep), record)
    done_usd = sum(s["cost_usd"] or 0 for s in sessions)
    failed_usd, unknown = spend(progress["failed_attempts"])
    print("WROTE evals/feeds/repeats/%s.json: %d sessions, %d verdicts, US$%.2f in total: US$%.2f in sessions, "
          "US$%.2f in %d failed attempt%s%s" % (
              rep, len(sessions), len(verdicts), done_usd + failed_usd, done_usd, failed_usd,
              len(progress["failed_attempts"]), "" if len(progress["failed_attempts"]) == 1 else "s",
              " (%d of unknown cost)" % unknown if unknown else ""))
    return 0


def unaccounted(rep: str, progress: Optional[dict], plan: list) -> list:
    """Session telemetry under the repeat that the progress file does not name: evidence of a session
    this runner cannot account for. Each is named with the batch its item keys belong to."""
    folder = REPEATS_DIR / rep / "telemetry"
    known = set()
    if progress is not None:
        known = ({s.get("run_id") for s in progress["sessions"].values()}
                 | {a.get("run_id") for a in progress["failed_attempts"]})
    batch_of = {k: name for name, keys in plan for k in keys}
    out = []
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else ():
        if path.stem in known:
            continue
        keys = set(re.findall(r"(?:ofsi|fincen|ofac):[0-9a-f]{16}", path.read_text(encoding="utf-8")))
        out.append("%s (%s)" % (path.stem, ", ".join(sorted({batch_of[k] for k in keys if k in batch_of}))
                                or "no batch named"))
    return out


@contextlib.contextmanager
def repeat_lock(rep: str):
    """One invocation per repeat at a time. flock is released by the kernel when the process exits, so
    a crash cannot leave a stale lock. Yields False when another invocation holds it."""
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(PROGRESS_DIR / ("%s.lock" % rep)), os.O_CREAT | os.O_RDWR, 0o644)
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


def run(rep: str, pilot: bool, session=of.run_triage, today: date = None, after_fix: bool = False) -> int:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    problems = preflight(rep, catalogue)
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems))
        return 1
    with repeat_lock(rep) as held:
        if not held:
            print("REFUSED: another invocation is running %s (%s is locked); two would run the same batch twice"
                  % (rep, _rel(PROGRESS_DIR / ("%s.lock" % rep))))
            return 1
        if record_written(rep):  # again, inside the lock: an invocation that held it may have just written it
            print("REFUSED: %s exists; a repeat is never overwritten" % _rel(REPEATS_DIR / ("%s.json" % rep)))
            return 1
        plan = batches(catalogue)
        progress_path = PROGRESS_DIR / ("%s.json" % rep)
        existing = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else None
        orphans = unaccounted(rep, existing, plan)
        if orphans:
            print("REFUSED: %s's telemetry holds session%s %s that %s does not account for.\n"
                  "  Those batches were done or attempted and are never re-run blind. Restore the progress\n"
                  "  file, or, having read the telemetry, move it aside (mv, never delete) and run again."
                  % (rep, "" if len(orphans) == 1 else "s", "; ".join(orphans),
                     _rel(progress_path) if existing is not None else "no progress file (it is missing)"))
            return 1
        progress = existing if existing is not None else dict(identity(), repeat=rep, sessions={}, failed_attempts=[])
        moved = sorted(k for k, v in identity().items() if progress.get(k) != v)
        if moved:
            print("REFUSED: %s was started under a different %s; see the plan (Task 7) for a changed arm"
                  % (_rel(progress_path), ", ".join(moved)))
            return 1
        telemetry.TELEMETRY_DIR = REPEATS_DIR / rep / "telemetry"
        return run_plan(rep, plan, progress, progress_path, session, today, pilot, after_fix)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Run triage-only repeats over the back-catalogue")
    ap.add_argument("--repeat", choices=REPEATS)
    ap.add_argument("--pilot", action="store_true", help="one session, then stop and project the cost")
    ap.add_argument("--plan", action="store_true", help="print the batches; start nothing")
    ap.add_argument("--after-fix", action="store_true",
                    help="one more attempt at a batch STOPPED for a repeated failure, once its cause is fixed")
    args = ap.parse_args(argv)
    if args.plan:
        for name, keys in batches(json.loads(CATALOGUE.read_text(encoding="utf-8"))):
            print("  %-9s %2d items" % (name, len(keys)))
        return 0
    if not args.repeat:
        ap.error("--repeat is required unless --plan")
    return run(args.repeat, args.pilot, after_fix=args.after_fix)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
