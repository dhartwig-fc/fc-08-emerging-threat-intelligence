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

A FAILURE NAMES ITS ERROR, AND A REPEATED BUG STOPS THE RUNNER (Task 4 review ruling). Each failed
attempt records `error` -- "<Type>: <message>", as run_triage returns it, or as the runner caught it
with its traceback when the session itself raised -- and `error_kind`: "sdk" for the SDK's own errors
and an agent error result (auth, credit, the CLI: fix the machine, run again), "code" for anything
else. A batch whose last two attempts failed with the SAME "code" error (the run id normalised out)
is a bug in the runner, the orchestrator or the tools, not a flake, and re-running it would spend
again for the same result: the runner prints STOPPED and refuses that batch until the bug is fixed
and it is run once with --after-fix, which permits exactly one more attempt. Guarded by
evals/check_feeds_orchestrator.py (error-recorded, stops-on-repeat).

MODEL RUNS. The only file in sub-project B that starts agent sessions. check_all never runs it.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import os
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


def preflight(rep: str, catalogue: dict) -> list:
    problems = []
    if (REPEATS_DIR / ("%s.json" % rep)).exists():
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
    """"sdk" when the SDK or the agent's own result failed (fix the machine, run again); "code" otherwise."""
    if error.startswith(AGENT_FAILED):
        return "sdk"
    return "sdk" if error.split(":", 1)[0].strip() in SDK_ERRORS else "code"


def attempt(session, run: of.FeedsRun) -> dict:
    """One session. run_triage records its own failures; if the session RAISES instead (a bug before or
    after the agent loop), the runner records it the same way, with the traceback, rather than dying
    with nothing written -- an unrecorded failure could be re-run without limit."""
    try:
        return dict(asyncio.run(session(run)))
    except Exception as exc:  # noqa: BLE001 -- recorded, then counted by repeated_code_error
        return {"run_id": run.run_id, "failure": "%s: %s" % (type(exc).__name__, exc), "raised_in": "runner",
                "traceback": traceback.format_exc(), "cost_usd": None, "turns": None, "limit": None}


def failure_record(summary: dict) -> dict:
    """The failure as kept under failed_attempts: the error's type and message, and its kind."""
    error = str(summary["failure"])
    return dict(summary, error=error, error_kind=error_kind(error))


def repeated_code_error(failed_attempts: list, batch: str) -> Optional[str]:
    """The error, when this batch's last two attempts failed with the same non-SDK error; else None."""
    tail = [a for a in failed_attempts if a.get("batch") == batch][-2:]
    if len(tail) < 2 or any(a.get("error_kind") != "code" for a in tail):
        return None
    same = [str(a.get("error", "")).replace(str(a.get("run_id")), "<run_id>") for a in tail]
    return same[1] if same[0] == same[1] else None


def _stopped(name: str, error: str) -> None:
    print("STOPPED %s failed twice in a row with the same non-SDK error:\n  %s\n"
          "  That is a bug in the runner, the orchestrator or the tools, not a flake: another attempt would\n"
          "  spend again for the same result. Fix the bug, then run once with --after-fix." % (name, error[:500]))


def run_plan(rep: str, plan: list, progress: dict, progress_path: Path, session, today: Optional[date],
             pilot: bool, after_fix: bool = False) -> int:
    if pilot and plan[0][0] in progress["sessions"]:
        # The pilot IS the first batch; run again, it would silently become batch-2's session.
        print("PILOT: %s already has a completed session; nothing run" % plan[0][0])
        return 0
    for name, keys in plan:
        if name in progress["sessions"]:
            continue
        stuck = repeated_code_error(progress["failed_attempts"], name)
        if stuck and not after_fix:
            _stopped(name, stuck)
            return 1
        after_fix = False  # --after-fix buys exactly one attempt
        run = of.FeedsRun(inbox.mint_run_id(today or date.today()), catalogue=CATALOGUE, batch=tuple(keys))
        summary = dict(attempt(session, run), batch=name, keys=keys)
        if summary["failure"]:
            progress["failed_attempts"].append(failure_record(summary))
            _save(progress_path, progress)
            stuck = repeated_code_error(progress["failed_attempts"], name)
            if stuck:
                _stopped(name, stuck)
                return 1
            print("FAILED  %s %s: %s\n  Nothing is lost; run the same command again to retry this batch."
                  % (name, run.run_id, summary["failure"]))
            return 1
        summary["verdicts"] = feeds_triage.load(run.run_id)
        progress["sessions"][name] = summary
        _save(progress_path, progress)
        print("done    %-9s %s  %d/%d triaged, %d unfinished, %s turns, US$%s" % (
            name, run.run_id, len(summary["triaged"]), len(keys), len(summary["unfinished"]), summary["turns"],
            summary["cost_usd"]))
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
    print("WROTE evals/feeds/repeats/%s.json: %d sessions, %d verdicts, US$%.2f" % (
        rep, len(sessions), len(verdicts), sum(s["cost_usd"] or 0 for s in sessions)))
    return 0


def run(rep: str, pilot: bool, session=of.run_triage, today: date = None, after_fix: bool = False) -> int:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    problems = preflight(rep, catalogue)
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems))
        return 1
    progress_path = PROGRESS_DIR / ("%s.json" % rep)
    progress = (json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists()
                else dict(identity(), repeat=rep, sessions={}, failed_attempts=[]))
    moved = sorted(k for k, v in identity().items() if progress.get(k) != v)
    if moved:
        print("REFUSED: %s was started under a different %s; see the plan (Task 7) for a changed arm"
              % (progress_path.relative_to(ROOT), ", ".join(moved)))
        return 1
    telemetry.TELEMETRY_DIR = REPEATS_DIR / rep / "telemetry"
    return run_plan(rep, batches(catalogue), progress, progress_path, session, today, pilot, after_fix)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Run triage-only repeats over the back-catalogue")
    ap.add_argument("--repeat", choices=REPEATS)
    ap.add_argument("--pilot", action="store_true", help="one session, then stop and project the cost")
    ap.add_argument("--plan", action="store_true", help="print the batches; start nothing")
    ap.add_argument("--after-fix", action="store_true",
                    help="one more attempt at a batch STOPPED for a repeated non-SDK error, once its bug is fixed")
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
