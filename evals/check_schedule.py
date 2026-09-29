"""
Pin the Friday schedule, its launcher, its preflight and its one notification (slice 2 C2, spec section 5).

Usage:
    python evals/check_schedule.py
    python evals/check_schedule.py --mutate log-token        # friday_run.sh prints the token
    python evals/check_schedule.py --mutate keep-api-key     # friday_run.sh leaves ANTHROPIC_API_KEY set
    python evals/check_schedule.py --mutate double-notify    # friday_run.sh notifies on every run, not only when it must
    python evals/check_schedule.py --mutate wrong-day        # the plist fires on Mondays
    python evals/check_schedule.py --mutate token-in-plist   # the plist carries a token variable
    python evals/check_schedule.py --mutate any-auth         # the preflight accepts the interactive login
    python evals/check_schedule.py --mutate no-branch-check  # the preflight runs off main
    python evals/check_schedule.py --mutate no-back-pressure # the preflight ignores an unaccepted run
    python evals/check_schedule.py --mutate silent-refusal   # a refused scheduled run posts no notification
    python evals/check_schedule.py --mutate crash-exits-1    # a scheduled crash exits 1 (read as "already notified")
    python evals/check_schedule.py --mutate crash-notifies   # a scheduled crash ALSO notifies -- two notifications
    python evals/check_schedule.py --mutate export-token     # the token leaks into every later child, not just Python
    python evals/check_schedule.py --mutate ignore-auth-exit # auth_status trusts stdout even on a non-zero exit
    python evals/check_schedule.py --mutate xtrace-ux        # the launcher enables xtrace alongside -u

WHAT IT HOLDS:
  the plist     renders to a valid plist: label uk.fc08.friday-run; Fridays (Weekday 5) at 09:00; runs
                /bin/bash scripts/schedule/friday_run.sh of THIS checkout; logs under ~/Library/Logs; RunAtLoad
                false; no environment but PATH, and no token anywhere in it;
  schedule.py   install writes exactly the rendered plist and bootstraps gui/<uid>; refuses a second install;
                --dry-run writes nothing; uninstall boots out and removes it; a FAILED bootout is reported, not
                swallowed, and leaves the plist in place; status only reads;
  the launcher  run with stub security, python and osascript: the token reaches Python as
                CLAUDE_CODE_OAUTH_TOKEN and appears in NO output, notification, argument or the environment of
                any OTHER child process (not even a crash's own osascript call); ANTHROPIC_API_KEY is unset;
                the script never enables tracing, in any `set` flag combination; notify() passes `--` before
                the message and title, so a message starting with `-` cannot be read as an option;
  the contract  every scheduled exit code -- 0, the reserved "already notified" code, 1, 2, 3 -- yields exactly
                ONE notification in total, whichever side posts it (tools/friday_run.py's docstring has the
                full contract; this is fix round 1's I-1);
  the preflight off main, detached, a pending run under 14 days, and any auth but loggedIn "oauth_token"
                each refuse; a clean state passes; auth_status and on_main REFUSE -- never crash, never pass --
                on a non-zero exit, non-JSON output, `null`, a list, or a missing binary (fix round 1's I-3);
  one notice    friday_run --scheduled, refused, writes a REFUSED report and posts exactly one notification
                whose words are the report's first two lines; a crash inside the scheduled run posts NONE of
                its own; a notifier that itself fails to deliver is reported as a failure, not swallowed
                (fix round 1's I-2).

COLD. Temporary folders, temporary git repositories, stub commands. It never runs launchctl, never reads the
Keychain, never runs the claude CLI, and never writes ~/Library.

NOT A VACUOUS PASS. Each --mutate rewrites the script, the template or a module in memory or in a temporary
copy; at least one check must fail.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import inbox  # noqa: E402
from feeds import notify as real_notify  # noqa: E402 -- never mutated by this guard; imported directly

SCRIPT = ROOT / "scripts" / "schedule" / "friday_run.sh"
TEMPLATE = ROOT / "scripts" / "schedule" / "uk.fc08.friday-run.plist"
PREFLIGHT = ROOT / "feeds" / "preflight.py"
FRIDAY = ROOT / "tools" / "friday_run.py"
SCHEDULE = ROOT / "tools" / "schedule.py"
SENTINEL = "sk-ant-oat01-SENTINEL-never-print-me"
TEXT_MUTATIONS = {
    "log-token": (SCRIPT, 'if [ -z "$FC08_TOKEN" ]; then\n', 'echo "token $FC08_TOKEN"\nif [ -z "$FC08_TOKEN" ]; then\n'),
    "keep-api-key": (SCRIPT, "unset ANTHROPIC_API_KEY\n", ""),
    "double-notify": (SCRIPT, 'if [ "$code" -ne 0 ] && [ "$code" -ne "$NOTIFIED_EXIT" ]; then\n', "if true; then\n"),
    "wrong-day": (TEMPLATE, "<key>Weekday</key>\n        <integer>5</integer>", "<key>Weekday</key>\n        <integer>1</integer>"),
    "token-in-plist": (TEMPLATE, "        <key>PATH</key>\n", "        <key>CLAUDE_CODE_OAUTH_TOKEN</key>\n        <string>x</string>\n"
                                                          "        <key>PATH</key>\n"),
    "any-auth": (PREFLIGHT, "    if status.get(\"authMethod\") != TOKEN_METHOD:\n", "    if False:\n"),
    "no-branch-check": (PREFLIGHT, '    if got.returncode != 0 or branch != "main":\n', "    if False:\n"),
    "no-back-pressure": (PREFLIGHT, "    if waiting:\n", "    if False:\n"),
    "ignore-auth-exit": (PREFLIGHT, "    if got.returncode != 0:\n", "    if False:\n"),
    "silent-refusal": (FRIDAY, "    posted = (notifier or notify.notify)(*notify.from_report(path))\n",
                       "    posted = (notifier or notify.notify)(*notify.from_report(path)) if not reasons else True\n"),
    "crash-exits-1": (FRIDAY, "            return 3\n", "            return 1\n"),
    "crash-notifies": (FRIDAY, "            traceback.print_exc()\n",
                       "            traceback.print_exc()\n            (notifier or notify.notify)('FC08 Friday run: CRASHED', 'x')\n"),
    "export-token": (SCRIPT, '    CLAUDE_CODE_OAUTH_TOKEN="$FC08_TOKEN" "$PYTHON" tools/friday_run.py --scheduled\n',
                     '    export CLAUDE_CODE_OAUTH_TOKEN="$FC08_TOKEN"; "$PYTHON" tools/friday_run.py --scheduled\n'),
    "xtrace-ux": (SCRIPT, "set -u\n", "set -ux\n"),
}


def text(path: Path, mutation) -> str:
    source = path.read_text(encoding="utf-8")
    if mutation and TEXT_MUTATIONS[mutation][0] == path:
        old, new = TEXT_MUTATIONS[mutation][1:]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
        source = source.replace(old, new)
    return source


def module(name: str, path: Path, mutation):
    m = types.ModuleType(name)
    m.__file__ = str(path)
    sys.modules[name] = m
    exec(compile(text(path, mutation), str(path), "exec"), m.__dict__)
    return m


def stub(path: Path, body: str) -> Path:
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def launcher(tmp: Path, mutation, token: bool, exit_code: int) -> dict:
    """Run a copy of friday_run.sh in a fake repo with stub security, python and osascript. Both security and
    osascript also record whether they inherited CLAUDE_CODE_OAUTH_TOKEN, so a leak into EITHER (not just
    Python's own argv/output) is caught -- fix round 1, M-2."""
    repo = Path(tempfile.mkdtemp(dir=str(tmp), prefix="repo-%s-%d-" % (token, exit_code)))
    (repo / "scripts" / "schedule").mkdir(parents=True)
    script = repo / "scripts" / "schedule" / "friday_run.sh"
    script.write_text(text(SCRIPT, mutation), encoding="utf-8")
    seen, notes = repo / "python-saw.txt", repo / "notifications.txt"
    envcheck = '[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && echo "ENV-LEAK:$0" >> "%s" || true\n' % notes
    security = stub(repo / "security", envcheck +
                     'if [ "$STUB_HAS_TOKEN" = 1 ]; then echo "%s"; else exit 44; fi\n' % SENTINEL)
    python = stub(repo / "python", (
        '{ [ "${CLAUDE_CODE_OAUTH_TOKEN:-}" = "%s" ] && echo token=yes || echo token=no\n'
        '  [ -n "${ANTHROPIC_API_KEY:-}" ] && echo apikey=set || echo apikey=unset\n'
        '  echo "args=$*"; } > "%s"\nexit "$STUB_EXIT"\n') % (SENTINEL, seen))
    osa = stub(repo / "osascript", envcheck +
               'for a in "$@"; do printf "%%s|" "$a"; done >> "%s"; echo >> "%s"\n' % (notes, notes))
    env = dict(os.environ, FC08_SECURITY=str(security), FC08_PYTHON=str(python), FC08_OSASCRIPT=str(osa),
               STUB_HAS_TOKEN="1" if token else "0", STUB_EXIT=str(exit_code), ANTHROPIC_API_KEY="leak-me",
               USER=os.environ.get("USER", "owner"))
    got = subprocess.run(["/bin/bash", str(script)], cwd=str(tmp), env=env, capture_output=True, text=True, timeout=60)
    return {"code": got.returncode, "out": got.stdout + got.stderr,
            "saw": seen.read_text() if seen.exists() else "", "notes": notes.read_text() if notes.exists() else "",
            "script": script.read_text()}


def git(repo: Path, *args) -> None:
    subprocess.run(["git", "-c", "user.email=g@g", "-c", "user.name=guard", *args], cwd=str(repo), check=True,
                   capture_output=True)


def is_tracing_enabled(source: str) -> bool:
    """Any `set` invocation that turns xtrace (or verbose) ON, in any flag combination -- `set -x`, `set -eux`,
    `set -ux` -- not just a literal `set -x` line (fix round 1, M-3). `set +x` / `set +o xtrace` (defensive,
    turning it OFF) must NOT trip this."""
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if line.startswith("set -") and not line.startswith("set --"):
            flags = line[len("set -"):].split()[0] if len(line) > len("set -") else ""
            if "x" in flags:
                return True
        if "-o xtrace" in line or "-o verbose" in line:  # "+o xtrace" (disabling) does not contain this substring
            return True
        if line.startswith("printenv") or line == "env":
            return True
    return False


def checks(mutation) -> list:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # --- the plist, rendered from the (possibly mutated) template
        sched = module("schedule_under_test", SCHEDULE, mutation)
        tpl = tmp / "template.plist"
        tpl.write_text(text(TEMPLATE, mutation), encoding="utf-8")
        sched.TEMPLATE = tpl
        rendered = sched.render(Path("/Users/owner/fc08"), Path("/Users/owner"))
        d = plistlib.loads(rendered)
        out.append((d["Label"] == "uk.fc08.friday-run" and d["StartCalendarInterval"] == {"Weekday": 5, "Hour": 9, "Minute": 0}
                    and d["ProgramArguments"] == ["/bin/bash", "/Users/owner/fc08/scripts/schedule/friday_run.sh"]
                    and d["RunAtLoad"] is False and d["StandardOutPath"].startswith("/Users/owner/Library/Logs/"),
                    "the plist runs this checkout's friday_run.sh every Friday at 09:00, logging under ~/Library/Logs",
                    "%s %s" % (d.get("StartCalendarInterval"), d.get("ProgramArguments"))))
        def words(x):  # every key and string value in the parsed plist (the XML comment is not configuration)
            if isinstance(x, dict):
                return [w for k, v in x.items() for w in [k] + words(v)]
            return [w for v in x for w in words(v)] if isinstance(x, list) else [x] if isinstance(x, str) else []
        out.append((sorted(d.get("EnvironmentVariables", {})) == ["PATH"]
                    and not any("TOKEN" in w.upper() or "sk-ant" in w for w in words(d)),
                    "the plist carries no environment but PATH and no token",
                    sorted(d.get("EnvironmentVariables", {}))))

        # --- the scheduled-run module, loaded early so its reserved exit code is available to every section below
        fr = module("friday_under_test", FRIDAY, mutation)
        RESERVED = fr.SCHEDULED_NOTIFIED_EXIT

        # --- schedule.py against a temporary LaunchAgents folder and a stub launchctl
        calls = []
        fake = lambda argv, **kw: (calls.append(argv), types.SimpleNamespace(returncode=0, stdout="state = waiting", stderr=""))[1]  # noqa: E731
        agents = tmp / "LaunchAgents"
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            dry = sched.main(["install", "--dry-run"], agents=agents, run=fake, uid=501, home=Path("/Users/owner"))
            wrote_on_dry = sched.installed_path(agents).exists()
            first = sched.main(["install"], agents=agents, run=fake, uid=501, home=Path("/Users/owner"))
            same = sched.installed_path(agents).read_bytes() == sched.render(ROOT, Path("/Users/owner"))
            second = sched.main(["install"], agents=agents, run=fake, uid=501, home=Path("/Users/owner"))
            status = sched.main(["status"], agents=agents, run=fake, uid=501, home=Path("/Users/owner"))
            gone = sched.main(["uninstall"], agents=agents, run=fake, uid=501, home=Path("/Users/owner"))
        verbs = [c[1] for c in calls]
        out.append((dry == 0 and not wrote_on_dry and first == 0 and same and second == 1 and status == 0 and gone == 0
                    and not sched.installed_path(agents).exists() and verbs == ["bootstrap", "print", "bootout"]
                    and calls[0][2] == "gui/501",
                    "schedule.py: a dry run writes nothing; install writes the rendered plist and bootstraps gui/<uid>; "
                    "a second install refuses; status only reads; uninstall boots out and removes it", verbs))

        # --- schedule.py uninstall: a FAILED bootout is reported, not swallowed, and the plist stays (fix round 1, M-5)
        with contextlib.redirect_stdout(io.StringIO()):
            reinstalled = sched.main(["install"], agents=agents, run=fake, uid=502, home=Path("/Users/owner"))
        fail_bootout = lambda argv, **kw: types.SimpleNamespace(  # noqa: E731
            returncode=1, stdout="", stderr="No such process") if argv[1] == "bootout" else types.SimpleNamespace(
            returncode=0, stdout="", stderr="")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            failed = sched.main(["uninstall"], agents=agents, run=fail_bootout, uid=502, home=Path("/Users/owner"))
        out.append((reinstalled == 0 and failed == 1 and sched.installed_path(agents).exists()
                    and "REFUSED" in buf.getvalue() and "bootout" in buf.getvalue(),
                    "schedule.py uninstall reports a failed launchctl bootout instead of ignoring it, and leaves the "
                    "plist in place", buf.getvalue().strip()[:160]))
        with contextlib.redirect_stdout(io.StringIO()):
            sched.main(["uninstall"], agents=agents, run=fake, uid=502, home=Path("/Users/owner"))  # clean up

        # --- the launcher, with stubs. "none" (no token) now uses RESERVED: a real --refuse run notifies itself
        # and exits RESERVED, so this reproduces that path rather than an arbitrary stand-in exit code.
        ok = launcher(tmp, mutation, token=True, exit_code=0)
        crash = launcher(tmp, mutation, token=True, exit_code=3)
        none = launcher(tmp, mutation, token=False, exit_code=RESERVED)
        leaked = [n for n, r in (("ok", ok), ("crash", crash), ("none", none))
                  if SENTINEL in r["out"] or SENTINEL in r["notes"] or SENTINEL in r["saw"] or "ENV-LEAK" in r["notes"]]
        out.append((not leaked and "token=yes" in ok["saw"] and "token=no" in none["saw"],
                    "the token reaches Python as CLAUDE_CODE_OAUTH_TOKEN and appears in no output, notification, "
                    "argument or any OTHER child's environment", "leaked in %s; saw %r" % (leaked, ok["saw"][:40])))
        out.append(("apikey=unset" in ok["saw"] and "apikey=unset" in none["saw"],
                    "ANTHROPIC_API_KEY is unset before Python starts", ok["saw"].split("\n")[1:2]))
        out.append(("--refuse" in none["saw"] and "Keychain" in none["saw"] and none["code"] == RESERVED,
                    "with no token in the Keychain, Python is told to refuse, notifies itself and exits the "
                    "reserved code", none["saw"][-80:]))
        out.append((ok["notes"] == "" and none["notes"] == "" and crash["notes"].count("\n") == 1
                    and "CRASHED" in crash["notes"] and crash["code"] == 3,
                    "an acceptable or already-notified exit adds no notification of the script's own; a crash "
                    "posts exactly one", "ok %r | none %r | crash %r" % (ok["notes"][:30], none["notes"][:30], crash["notes"][:60])))
        out.append((is_tracing_enabled("set -x\ntrue\n") and is_tracing_enabled("set -eux\n")
                    and is_tracing_enabled("set -ux\n") and not is_tracing_enabled("set -u\n")
                    and not is_tracing_enabled("set +x\n") and not is_tracing_enabled("set +o xtrace +o verbose\n")
                    and not is_tracing_enabled(text(SCRIPT, mutation)),
                    "the launcher never enables tracing, in any `set` flag combination", ""))

        # --- fix round 1, I-1: every scheduled exit code yields exactly ONE notification in total. Python posts
        # its own for 0 (acceptable) and RESERVED (refused/failed) by contract; every other code means Python
        # posted nothing, so the shell must be the one that does.
        totals = {}
        for code in (0, RESERVED, 1, 2, 3):
            r = launcher(tmp, mutation, token=True, exit_code=code)
            shell_notified = r["notes"] != ""
            python_notified_by_contract = code in (0, RESERVED)
            totals[code] = int(shell_notified) + int(python_notified_by_contract)
        out.append((all(v == 1 for v in totals.values()),
                    "every scheduled exit code (0, reserved, 1, 2, 3) yields exactly one notification in total, "
                    "from whichever side is supposed to post it", totals))

        # --- notify() passes `--` before the message and title (fix round 1, M-1): a message of "-e" must not be
        # read as an osascript option.
        seen_argv = []
        real_notify.notify("some title", "-e", run=lambda argv, **kw: (
            seen_argv.append(argv), types.SimpleNamespace(returncode=0, stdout="", stderr=""))[1])
        out.append((seen_argv and seen_argv[-1][-3:] == ["--", "-e", "some title"],
                    "notify() passes -- before the message and title, so a message beginning with '-' is never "
                    "read as an option", seen_argv[-1][-4:] if seen_argv else None))

        # --- the preflight
        pf = module("feeds.preflight", PREFLIGHT, mutation)
        repo = tmp / "git-repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "f").write_text("x")
        git(repo, "add", "f")
        git(repo, "commit", "-qm", "one")
        on_main = pf.on_main(repo)
        git(repo, "checkout", "-q", "-b", "feature")
        off = pf.on_main(repo)
        git(repo, "checkout", "-q", "--detach")
        detached = pf.on_main(repo)
        out.append((on_main is None and bool(off) and bool(detached), "the preflight refuses a feature branch and a "
                    "detached HEAD, and passes main", "%s | %s" % (off, detached)))
        box = tmp / "inbox"
        today = date(2026, 10, 9)
        inbox.save("feeds-2026-10-02-ddd001", {"run_id": "feeds-2026-10-02-ddd001", "sources": {"ofac": {"items": [
            {"key": "ofac:%016x" % 1, "source": "ofac", "item_id": "x"}]}}}, box)
        inbox.save("feeds-2026-10-03-ddd002", {"run_id": "feeds-2026-10-03-ddd002", "eval": True, "sources": {
            "ofac": {"items": [{"key": "ofac:%016x" % 2, "source": "ofac", "item_id": "y"}]}}}, box)
        waiting = pf.back_pressure(box, today)
        clear = pf.back_pressure(box, date(2026, 10, 16))
        out.append((bool(waiting) and "feeds-2026-10-02-ddd001" in waiting and "ddd002" not in waiting and clear is None,
                    "a pending run under 14 days blocks the next run (an eval run never does); at 14 days it does not",
                    str(waiting)[:90]))
        cases = {"token": {"loggedIn": True, "authMethod": "oauth_token"}, "login": {"loggedIn": True, "authMethod": "claude.ai"},
                 "api": {"loggedIn": True, "authMethod": "api_key"}, "out": {"loggedIn": False, "authMethod": "oauth_token"},
                 "error": {"error": "OSError: no claude"}}
        verdict = {k: pf.auth(v) for k, v in cases.items()}
        out.append((verdict["token"] is None and all(verdict[k] for k in ("login", "api", "out", "error")),
                    "auth passes only loggedIn with authMethod oauth_token; the interactive login, an API key, logged "
                    "out, or no status each refuse", {k: bool(v) for k, v in verdict.items()}))

        # --- fix round 1, I-3: auth_status and on_main fail closed on a hostile or broken CLI, never crash, never pass
        def stub_run(rc, out_, exc=None, err="boom"):
            def run(argv, **kw):
                if exc:
                    raise exc
                return types.SimpleNamespace(returncode=rc, stdout=out_, stderr=err)
            return run
        auth_cases = {
            "good": (stub_run(0, json.dumps({"loggedIn": True, "authMethod": "oauth_token"})), False),
            "rc1-json-says-token": (stub_run(1, json.dumps({"loggedIn": True, "authMethod": "oauth_token"})), True),
            "rc1-empty": (stub_run(1, ""), True),
            "not-json": (stub_run(0, "Update available\n{}"), True),
            "missing-binary": (stub_run(0, "", FileNotFoundError(2, "No such file or directory", "claude")), True),
            "json-null": (stub_run(0, "null"), True),
            "json-list": (stub_run(0, "[]"), True),
        }
        auth_detail = {}
        auth_ok = True
        for name, (run_stub, should_refuse) in auth_cases.items():
            try:
                st = pf.auth_status(run_stub)
                verdict = pf.auth(st)
                crashed = False
            except Exception as exc:  # noqa: BLE001 -- a crash here IS the failure this check exists to catch
                verdict, crashed = None, True
            ok = (not crashed) and bool(verdict) == should_refuse
            auth_ok = auth_ok and ok
            auth_detail[name] = "crash" if crashed else bool(verdict)
        out.append((auth_ok, "auth_status refuses (never crashes, never passes) on a non-zero exit even with "
                    "well-formed JSON, on non-JSON output, on `null` or a list, and on a missing claude binary",
                    auth_detail))
        missing_git = None
        git_crashed = False
        try:
            missing_git = pf.on_main(Path("."), run=stub_run(0, "", FileNotFoundError(2, "No such file or directory", "git")))
        except Exception:  # noqa: BLE001
            git_crashed = True
        out.append((not git_crashed and bool(missing_git),
                    "on_main refuses rather than crashing when git itself is missing",
                    "crash" if git_crashed else missing_git))

        # --- fix round 1, I-2: the Python half of the one-notification contract
        notes = []
        good_notifier = lambda t, m: notes.append((t, m)) or True  # noqa: E731 -- list.append returns None

        with contextlib.redirect_stdout(io.StringIO()):
            code_refused = fr.main(["--scheduled"], root=tmp / "inbox-refused", today=date(2026, 10, 9),
                                   notifier=good_notifier, preflight_reasons=["the checkout is on 'feature', not main"])
        reports = list((tmp / "inbox-refused").glob("feeds-*/report.md"))
        head = reports[0].read_text().splitlines()[0] if reports else ""
        out.append((code_refused == RESERVED and len(notes) == 1 and notes[0][0] == "FC08 Friday run: REFUSED"
                    and "REFUSED" in head and "not main" in notes[0][1],
                    "a refused scheduled run writes a REFUSED report, posts exactly one notification from the "
                    "report's own first lines, and exits the reserved code", notes))

        notes2 = []
        failing_notifier2 = lambda t, m: notes2.append((t, m)) or False  # noqa: E731
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code_failed_notify = fr.main(["--scheduled"], root=tmp / "inbox-failnotify", today=date(2026, 10, 9),
                                         notifier=failing_notifier2, preflight_reasons=["the checkout is on 'feature', not main"])
        out.append((code_failed_notify not in (0, RESERVED) and len(notes2) == 1,
                    "when notify() itself returns False, --scheduled is called once, reports the failure, and "
                    "exits a non-reserved non-zero code so friday_run.sh notifies instead",
                    "code=%s notes=%s" % (code_failed_notify, notes2)))

        # A NATURAL crash, not a notifier that raises: write_refusal's _save does `path.parent.mkdir(...)`, which
        # raises NotADirectoryError when an ancestor of `root` is a plain file. This exercises main()'s except
        # block for real, and -- unlike a raising notifier -- stays safe to call again if a mutation makes that
        # except block ALSO notify (crash-notifies): the notifier here just appends and returns, it never re-raises.
        bad_root = tmp / "not-a-directory"
        bad_root.write_text("x", encoding="utf-8")
        notes3 = []
        crash_notifier = lambda t, m: notes3.append((t, m)) or True  # noqa: E731 -- only reached if a mutation makes the crash path notify
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code_crashed = fr.main(["--scheduled"], root=bad_root, today=date(2026, 10, 9),
                                   notifier=crash_notifier, preflight_reasons=["the checkout is on 'feature', not main"])
        out.append((code_crashed == 3 and len(notes3) == 0,
                    "a crash inside the scheduled run (write_refusal failing on a non-directory root) posts NO "
                    "notification of its own, and exits exactly the documented crash code (3, neither 0 nor "
                    "the reserved value, so friday_run.sh notifies instead)",
                    "code=%s notes=%s" % (code_crashed, notes3)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the Friday schedule, launcher and preflight")
    ap.add_argument("--mutate", choices=sorted(TEXT_MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:160]))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
