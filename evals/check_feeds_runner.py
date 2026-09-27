"""
Prove the triage repeat runner cannot re-spend a batch by accident (slice 2 B, Task 7).

Usage:
    python evals/check_feeds_runner.py
    python evals/check_feeds_runner.py --mutate error-dropped        # a failed attempt's record loses its error
    python evals/check_feeds_runner.py --mutate unrecorded-raise     # a session that raises kills the runner unrecorded
    python evals/check_feeds_runner.py --mutate retry-forever        # a repeated failure is re-run, and re-spent
    python evals/check_feeds_runner.py --mutate sdk-exempt           # a paid agent error result is exempt from the stop
    python evals/check_feeds_runner.py --mutate exact-match          # a bug whose text varies by id evades the stop
    python evals/check_feeds_runner.py --mutate cost-hidden          # the FAILED line hides what the attempt cost
    python evals/check_feeds_runner.py --mutate spend-hidden         # failed attempts' spend is left out of the totals
    python evals/check_feeds_runner.py --mutate forget-evidence      # a lost progress file re-runs a done batch
    python evals/check_feeds_runner.py --mutate no-lock              # two invocations of one repeat run at once
    python evals/check_feeds_runner.py --mutate pilot-reruns         # a second --pilot silently runs batch-2
    python evals/check_feeds_runner.py --mutate labels-unchecked     # the run starts on uncommitted labels
    python evals/check_feeds_runner.py --mutate unterminated-hidden  # the done line hides unterminated calls

WHAT IT HOLDS (evals/run_feeds_triage.py; the Task 4 review ruling and the Task 7 review):
  error recorded   a failed attempt keeps `error` "<Type>: <message>" and its kind: through the REAL
                   run_triage (its SDK loop patched to raise KeyError), through a session that raises
                   itself (recorded with its traceback, not a dead runner), and "sdk" for the SDK's
                   own errors and an agent error result;
  stops on repeat  the same failure twice in a row, OF ANY KIND -- a bug, an SDK error, a PAID agent
                   error result -- prints STOPPED and the next invocation starts NO session;
                   --after-fix buys exactly one more; two different failures do not stop it;
  normalised       a bug whose message varies by run id, tool-use id, path or number is still "the same";
  spend shown      the FAILED line prints the attempt's cost ("unknown" for a raise the runner caught),
                   and the WROTE total includes the failed attempts' spend;
  never twice      a lost progress file with the repeat's telemetry present REFUSES (the batch is named,
                   no session starts), while telemetry the progress file accounts for does not; a second
                   concurrent invocation is refused by the lock, which a finished one releases; a second
                   --pilot starts nothing;
  frozen inputs    preflight refuses labels.json or catalogue.json that is untracked or differs from HEAD
                   (asked of a throwaway git repository), and accepts them committed and unchanged;
  the done line    names the session's unterminated calls.

STUBS ONLY. No model, no network, no session. The runner's paths are redirected into a temporary
directory; the only real file it reads is the tracked catalogue (the batches) and labels (identity).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import secrets
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from agents import telemetry  # noqa: E402

telemetry.TELEMETRY_DIR = Path(tempfile.mkdtemp(prefix="fc08_runner_telemetry_"))  # never data/telemetry/
from agents import orchestrate_feeds as of  # noqa: E402
import run_feeds_triage as rf  # noqa: E402

MUTATIONS = ("error-dropped", "unrecorded-raise", "retry-forever", "sdk-exempt", "exact-match", "cost-hidden",
             "spend-hidden", "forget-evidence", "no-lock", "pilot-reruns", "labels-unchecked", "unterminated-hidden")
TODAY = date(2026, 10, 2)
KEY = "ofsi:0123456789abcdef"


def mutate(mutation) -> None:
    if mutation == "error-dropped":
        rf.failure_record = lambda summary: dict(summary, error_kind=rf.error_kind(str(summary["failure"])))
    if mutation == "unrecorded-raise":
        rf.attempt = lambda session, run: dict(asyncio.run(session(run)))  # the runner as first drafted
    if mutation == "retry-forever":
        rf.repeated_failure = lambda failed_attempts, batch: None
    if mutation == "sdk-exempt":  # the rule as first built: only a "code" error stops
        real = rf.repeated_failure
        rf.repeated_failure = lambda fa, batch: (None if any(a.get("error_kind") != "code"
                                                             for a in [a for a in fa if a.get("batch") == batch][-2:])
                                                 else real(fa, batch))
    if mutation == "exact-match":
        rf.normalise = lambda error: error
    if mutation == "cost-hidden":
        rf.failed_line = lambda name, run_id, summary, progress: (
            "FAILED  %s %s: %s\n  Nothing is lost; run the same command again." % (name, run_id, summary["failure"]))
    if mutation == "spend-hidden":
        rf.spend = lambda attempts: (0, 0)
    if mutation == "forget-evidence":
        rf.unaccounted = lambda rep, progress, plan: []
    if mutation == "no-lock":
        rf.repeat_lock = contextlib.contextmanager(lambda rep: (yield True))
    if mutation == "pilot-reruns":
        rf.pilot_done = lambda plan, progress: False
    if mutation == "labels-unchecked":
        rf._committed = lambda path: True
    if mutation == "unterminated-hidden":
        rf.done_line = lambda name, run_id, summary, keys: "done    %s %s  %d/%d triaged" % (
            name, run_id, len(summary["triaged"]), len(keys))


def counted(fn):
    async def session(run):
        session.calls += 1
        return await fn(run)
    session.calls = 0
    return session


def returns(failure, cost=0.01):
    async def session(run):
        return {"run_id": run.run_id, "failure": failure, "limit": None, "cost_usd": cost, "turns": 1}
    return session


def succeeds(cost=0.20, unterminated=3):
    async def session(run):
        return {"run_id": run.run_id, "failure": None, "limit": None, "cost_usd": cost, "turns": 9,
                "triaged": list(run.batch), "unfinished": [], "listed": list(run.batch), "never_listed": [],
                "tool_calls": {}, "duration_ms": 1, "stop_reason": "end_turn",
                "terminal_check": {"calls": 9, "duplicated": [], "unterminated": ["toolu_x"] * unterminated}}
    return session


def _quiet(fn, *args, **kwargs):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code = fn(*args, **kwargs)
        except Exception as exc:  # the runner died: nothing was recorded for this attempt
            code = "died: %s: %s" % (type(exc).__name__, exc)
    return code, out.getvalue()


def checks(mutation) -> list:
    mutate(mutation)
    tmp = Path(tempfile.mkdtemp(prefix="fc08_runner_"))
    # Every path the runner writes is redirected here; run() is driven past its preflight (which needs the
    # gitignored documents), and section 7 asks the real preflight directly.
    rf.REPEATS_DIR, rf.PROGRESS_DIR = tmp / "repeats", tmp / "repeats" / ".progress"
    real_preflight, rf.preflight = rf.preflight, (lambda rep, catalogue: [])
    plan = [("batch-1", [KEY])]
    fresh = lambda: {"sessions": {}, "failed_attempts": []}  # noqa: E731

    def invoke(session, progress, after_fix=False, pilot=True, the_plan=None):
        return _quiet(rf.run_plan, "rep1", the_plan or plan, progress, tmp / "progress.json", session, TODAY,
                      pilot=pilot, after_fix=after_fix)

    async def broken_query(**kwargs):  # the SDK loop raising a bug, not an SDK error
        raise KeyError("page")
        yield  # noqa: unreachable -- makes this an async generator, as query() is

    async def real_triage(run):
        return await of.run_triage(run, inbox_root=tmp / "inbox")

    async def raises(run):
        raise ValueError("boom in the runner's session")

    async def raises_varying(run):  # one bug, its text different every time
        raise FileNotFoundError("[Errno 2] %s: '/tmp/%s/%s/items.json' after %d ms" % (
            "toolu_" + secrets.token_hex(8), secrets.token_hex(4), run.run_id, secrets.randbelow(10 ** 6)))

    out = []
    real_query = of.query
    of.query = broken_query
    try:
        # 1. error recorded
        seen = {}
        for label, session in (("run_triage", real_triage), ("raised", raises),
                               ("sdk", returns("CLIConnectionError: not logged in")),
                               ("agent", returns("agent run failed: ['credit balance too low']"))):
            progress = fresh()
            code, _ = invoke(session, progress)
            a = progress["failed_attempts"][-1] if progress["failed_attempts"] else {}
            seen[label] = (code, a.get("error"), a.get("error_kind"),
                           "ValueError: boom" in a.get("traceback", ""))
        out.append((seen["run_triage"][:3] == (1, "KeyError: 'page'", "code")
                    and seen["raised"][:3] == (1, "ValueError: boom in the runner's session", "code") and seen["raised"][3]
                    and seen["sdk"][1:3] == ("CLIConnectionError: not logged in", "sdk") and seen["agent"][2] == "sdk",
                    "a failed attempt records its error's type and message (run_triage's and a raised session's, "
                    "with its traceback) and its kind", seen))

        # 2. stops on repeat, of any kind
        calls = {}
        for label, fn in (("bug", real_triage), ("sdk", returns("CLIConnectionError: not logged in")),
                          ("paid-agent-error", returns("agent run failed: ['error_during_execution']", cost=0.40))):
            progress, session = fresh(), counted(fn)
            outs = [invoke(session, progress)[1] for _ in range(3)]
            calls[label] = (session.calls, "STOPPED" in outs[1] and "STOPPED" in outs[2])
            if label == "bug":
                after = invoke(session, progress, after_fix=True)[1]
                again = invoke(session, progress)[1]
                calls["after-fix"] = (session.calls, "STOPPED" in after and "STOPPED" in again)
        two_bugs = fresh()
        differ = counted(returns("KeyError: 'a'"))
        invoke(differ, two_bugs)
        invoke(counted(returns("TypeError: b")), two_bugs)
        invoke(differ, two_bugs)
        calls["two-different"] = (differ.calls, False)
        out.append((calls == {"bug": (2, True), "after-fix": (3, True), "sdk": (2, True), "paid-agent-error": (2, True),
                              "two-different": (2, False)},
                    "the same failure twice in a row, of any kind (a bug, an SDK error, a paid agent error result), "
                    "STOPS: the next invocation starts no session; --after-fix buys one; different failures do not",
                    calls))

        # 3. normalised
        progress, session = fresh(), counted(raises_varying)
        outs = [invoke(session, progress)[1] for _ in range(3)]
        errors = [a.get("error") for a in progress["failed_attempts"]]
        out.append((session.calls == 2 and "STOPPED" in outs[2] and len(set(errors)) == 2,
                    "a bug whose message varies by run id, tool-use id, path and number is still the same failure",
                    {"sessions": session.calls, "distinct raw messages": len(set(errors))}))

        # 4. spend shown
        progress = fresh()
        failed_paid = invoke(returns("agent run failed: ['error_during_execution']", cost=0.40), progress)[1]
        failed_raise = invoke(raises, progress)[1]
        wrote = invoke(succeeds(cost=0.20), progress, pilot=False)[1]
        record = json.loads((rf.REPEATS_DIR / "rep1.json").read_text()) if (rf.REPEATS_DIR / "rep1.json").exists() else {}
        shown = {"paid FAILED names US$0.4000": "US$0.4000" in failed_paid.split("STOPPED")[0],
                 "raise FAILED says unknown": "cost unknown" in failed_raise,
                 "WROTE total US$0.60": "US$0.60 in total" in wrote,
                 "WROTE counts the unknown": "1 of unknown cost" in wrote,
                 "record keeps the failed costs": [a.get("cost_usd") for a in record.get("failed_attempts", [])]
                 == [0.40, None]}
        out.append((all(v is True for v in shown.values()),
                    "the FAILED line prints the attempt's cost (unknown for a raise), and the WROTE total includes "
                    "failed attempts", shown))

        # 5. never twice: lost progress, the lock, the second pilot
        tele = rf.REPEATS_DIR / "rep1" / "telemetry"
        tele.mkdir(parents=True, exist_ok=True)
        (tele / "feeds-2026-10-01-abc123.jsonl").write_text(json.dumps(
            {"stage": "FC08_TOOL_CALL", "payload": {"outcome": "Recorded: %s is relevant" % rf.batches(
                json.loads(rf.CATALOGUE.read_text()))[0][1][0]}}) + "\n")
        lost = counted(succeeds())
        code_lost, text_lost = _quiet(rf.run, "rep1", True, session=lost, today=TODAY)
        # the same telemetry, accounted for by a progress file whose batch-1 is done: not a refusal
        progress = dict(rf.identity(), repeat="rep1", failed_attempts=[],
                        sessions={"batch-1": {"run_id": "feeds-2026-10-01-abc123", "cost_usd": 0.2}})
        rf._save(rf.PROGRESS_DIR / "rep1.json", progress)
        kept = counted(succeeds())
        code_kept, text_kept = _quiet(rf.run, "rep1", True, session=kept, today=TODAY)
        never = {"lost progress: refused, no session": (code_lost, "REFUSED" in text_lost and "batch-1" in text_lost,
                                                        lost.calls),
                 "accounted: a second --pilot starts nothing": (code_kept, "already has a completed session"
                                                                in text_kept, kept.calls)}
        out.append((never == {"lost progress: refused, no session": (1, True, 0),
                              "accounted: a second --pilot starts nothing": (0, True, 0)},
                    "a lost progress file with the repeat's telemetry present REFUSES and names the batch; a second "
                    "--pilot starts nothing", never))

        holder = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.path.insert(0, %r); import run_feeds_triage as rf; "
             "from pathlib import Path; rf.PROGRESS_DIR = Path(%r)\nwith rf.repeat_lock('rep1') as held:\n"
             "    print('held' if held else 'not-held', flush=True); sys.stdin.read()"
             % (str(ROOT / "evals"), str(rf.PROGRESS_DIR))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT)
        held = holder.stdout.readline().strip()
        blocked = counted(succeeds())
        code_blocked, text_blocked = _quiet(rf.run, "rep1", False, session=blocked, today=TODAY)
        holder.stdin.close()
        holder.wait(timeout=30)
        with rf.repeat_lock("rep1") as after_exit:
            pass
        lock = {"holder": held, "second invocation": (code_blocked, "locked" in text_blocked, blocked.calls),
                "released on exit": after_exit}
        out.append((lock == {"holder": "held", "second invocation": (1, True, 0), "released on exit": True},
                    "a second concurrent invocation of a repeat is refused by the lock, and the lock is released "
                    "when its holder exits", lock))

        # 6. the done line
        line = invoke(succeeds(unterminated=3), fresh(), the_plan=[("batch-9", [KEY])])[1]
        out.append(("3 unterminated" in line, "the done line names the session's unterminated calls",
                    line.strip().splitlines()[0] if line.strip() else ""))
    finally:
        of.query = real_query

    # 7. frozen inputs: preflight asked of a throwaway git repository
    repo = Path(tempfile.mkdtemp(prefix="fc08_runner_repo_"))
    git = lambda *a: subprocess.run(["git", "-c", "user.name=guard", "-c", "user.email=guard@example.invalid",  # noqa: E731
                                     "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"] + list(a),
                                    cwd=repo, capture_output=True, check=True)
    git("init", "-q")
    (repo / "catalogue.json").write_text("{}\n")
    (repo / "labels.json").write_text("{}\n")
    saved = (rf.ROOT, rf.CATALOGUE, rf.LABELS, rf.REPEATS_DIR)
    rf.ROOT, rf.CATALOGUE, rf.LABELS, rf.REPEATS_DIR = repo, repo / "catalogue.json", repo / "labels.json", repo / "r"
    try:
        about = lambda: sorted(p.split(" ")[0] for p in real_preflight("rep1", {"items": []})  # noqa: E731
                               if "differs from HEAD" in p)
        frozen = {"untracked": about()}
        git("add", "catalogue.json", "labels.json")
        git("commit", "-q", "-m", "frozen")
        frozen["committed"] = about()
        (repo / "labels.json").write_text('{"edited": true}\n')
        frozen["labels edited"] = about()
    finally:
        rf.ROOT, rf.CATALOGUE, rf.LABELS, rf.REPEATS_DIR = saved
    out.append((frozen == {"untracked": ["catalogue.json", "labels.json"], "committed": [],
                           "labels edited": ["labels.json"]},
                "preflight refuses labels or catalogue untracked or differing from HEAD, and accepts them committed",
                frozen))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Prove the triage repeat runner cannot re-spend a batch by accident")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
