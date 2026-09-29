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
    python evals/check_schedule.py --mutate keep-inherited-token  # an inherited CLAUDE_CODE_OAUTH_TOKEN is not unset
    python evals/check_schedule.py --mutate seam-no-preflight     # --scheduled never consults preflight.reasons()
    python evals/check_schedule.py --mutate reasons-drop-auth     # preflight.reasons() drops the auth check
    python evals/check_schedule.py --mutate scheduled-no-env-refusals  # --scheduled drops C1's refusals() (API key)
    python evals/check_schedule.py --mutate auth-on-path          # auth_status runs the PATH claude, not the SDK's
    python evals/check_schedule.py --mutate cli-on-path           # cli_path() answers PATH's claude, not the SDK's
    python evals/check_schedule.py --mutate user-unset            # the launcher's Keychain account needs USER set

WHAT IT HOLDS:
  the plist     renders to a valid plist: label uk.fc08.friday-run; Fridays (Weekday 5) at 09:00; runs
                /bin/bash scripts/schedule/friday_run.sh of THIS checkout; logs under ~/Library/Logs; RunAtLoad
                false; no environment but PATH, and no token anywhere in it;
  schedule.py   install writes exactly the rendered plist and bootstraps gui/<uid>; refuses a second install;
                --dry-run writes nothing; uninstall boots out and removes it; a FAILED bootout is reported, not
                swallowed, and leaves the plist in place; status only reads;
  the launcher  run with stub security, python and osascript, and hermetic to the CALLING shell's own
                environment (the guard never leaks its own real CLAUDE_CODE_OAUTH_TOKEN into any stub, and an
                inherited dummy token in the shell that runs friday_run.sh is unset before the Keychain read,
                fix round 2's N-2): the token reaches Python as CLAUDE_CODE_OAUTH_TOKEN and appears in NO
                output, notification, argument or the environment of any OTHER child process (not even a
                crash's own osascript call); ANTHROPIC_API_KEY is unset; the script never enables tracing, in
                any `set`/`shopt` flag combination and at any position on the line (fix round 2's N-3); notify()
                passes `--` before the message and title, so a message starting with `-` cannot be read as an
                option;
  the contract  every scheduled exit code -- 0, the reserved "already notified" code, 1, 2, 3 -- yields exactly
                ONE notification in total, whichever side posts it (tools/friday_run.py's docstring has the
                full contract; this is fix round 1's I-1), including when a stdout write raises AFTER the
                notification has already posted (fix round 2's N-1: nothing that can raise runs between a
                successful notify() and the return);
  the preflight off main, detached, a pending run under 14 days, and any auth but loggedIn "oauth_token"
                each refuse; a clean state passes; auth_status and on_main REFUSE -- never crash, never pass --
                on a non-zero exit, non-JSON output, `null`, a list, or a missing binary (fix round 1's I-3);
  the seam      (final review, I-1) friday_run --scheduled with NO injected reasons runs the REAL
                preflight.reasons() -- its git and claude calls stubbed through its own `run=` seam, and the agent
                session replaced by a stub that can never spend -- exactly once: a clean state reaches the session;
                wrong auth, an ANTHROPIC_API_KEY or FEEDS_CATALOGUE in the environment (C1's refusals()), and all
                three preflight checks at once each refuse, with the reasons in the fixed order;
  which claude  (final review, I-2) preflight.cli_path() is the binary the Agent SDK would start for BOTH agents'
                real options (the bundled CLI when the SDK ships one), and auth_status runs exactly that binary;
                a claude that cannot be resolved at all refuses (N-1, below);
  one notice    friday_run --scheduled, refused, writes a REFUSED report and posts exactly one notification
                whose words are the report's first two lines; a crash inside the scheduled run posts NONE of
                its own; a notifier that itself fails to deliver is reported as a failure, not swallowed
                (fix round 1's I-2).

COLD. Temporary folders, temporary git repositories, stub commands. It never runs launchctl, never reads the
Keychain, never runs the claude CLI, and never writes ~/Library.

COLD WITH RESPECT TO THE CLAUDE CLI TOO (final re-review, N-1). Every check that stubs the preflight's `run=` also
stubs `preflight.cli_path` (`stubbed_cli`), so none of them needs the Agent SDK to RESOLVE a CLI. Exactly ONE
check asks the SDK's real resolver: "preflight.cli_path() is the claude binary the Agent SDK would start". Where
no CLI resolves (a runner whose SDK wheel ships no bundled CLI and has no claude anywhere), that one check
reports SKIP with the reason -- it is not counted as a pass, and the last line says how many were skipped. It
SKIPS only when the SDK's own resolver raises CLINotFoundError AND cli_path() raises it too; the preflight
answering a path the SDK cannot resolve is a FAIL, and so is any other exception (the private `_find_cli` gone
after an SDK upgrade is loud, never a skip).

NOT A VACUOUS PASS. Each --mutate rewrites the script, the template or a module in memory or in a temporary
copy; at least one check must fail.
"""

from __future__ import annotations

import argparse
import contextlib
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
# What the stubbed checks are told the SDK would start. Never executed: every `run=` that receives it is a stub.
STUB_CLI = "/guard-stub/claude_agent_sdk/_bundled/claude"
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
    "keep-inherited-token": (SCRIPT, "unset CLAUDE_CODE_OAUTH_TOKEN\n", ""),
    # final review I-1: the three one-line regressions that disconnected the seam with every check green
    "seam-no-preflight": (FRIDAY,
                          "    found = preflight.reasons(ROOT, root, today) if preflight_reasons is None else list(preflight_reasons)\n",
                          "    found = [] if preflight_reasons is None else list(preflight_reasons)\n"),
    "reasons-drop-auth": (PREFLIGHT,
                          "    found = [on_main(repo, run), back_pressure(root, today), auth(status if status is not None else auth_status(run))]\n",
                          "    found = [on_main(repo, run), back_pressure(root, today)]\n"),
    "scheduled-no-env-refusals": (FRIDAY,
                                  "    reasons = refusals() + list(extra_refusals or []) + list(args.refuse) + found\n",
                                  "    reasons = list(extra_refusals or []) + list(args.refuse) + found\n"),
    # final review I-2: the preflight checks a different claude from the one that spends
    "auth-on-path": (PREFLIGHT, "        cli = cli_path()\n", '        cli = "claude"\n'),
    "cli-on-path": (PREFLIGHT, "    return transport._find_cli()\n", '    return __import__("shutil").which("claude")\n'),
    # final review M-3: an unset USER under `set -u`
    "user-unset": (SCRIPT, 'ACCOUNT="${USER:-$(id -un)}"\n', 'ACCOUNT="$USER"\n'),
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


def launcher(tmp: Path, mutation, token: bool, exit_code: int, inherited_token: str = None,
             unset_user: bool = False) -> dict:
    """Run a copy of friday_run.sh in a fake repo with stub security, python and osascript. Both security and
    osascript also record whether they inherited CLAUDE_CODE_OAUTH_TOKEN, so a leak into EITHER (not just
    Python's own argv/output) is caught -- fix round 1, M-2.

    Hermetic to the CALLING process's own environment (fix round 2, N-2): `dict(os.environ, ...)` used to carry
    a REAL CLAUDE_CODE_OAUTH_TOKEN straight through into every stub if the person -- or CI -- running this guard
    had one exported (e.g. after `claude setup-token`), turning every ENV-LEAK check red for a reason that has
    nothing to do with the script. It is popped here unconditionally. `inherited_token`, when given, puts a
    caller-chosen value back -- simulating an operator's shell that itself exported one -- so a test can prove
    friday_run.sh unsets it before the Keychain read rather than merely that the FIXTURE doesn't leak its own.
    `unset_user` runs it with USER removed from the environment (final review, M-3); `security` records its own
    arguments, so the Keychain account it was asked for can be read back.
    """
    repo = Path(tempfile.mkdtemp(dir=str(tmp), prefix="repo-%s-%d-" % (token, exit_code)))
    (repo / "scripts" / "schedule").mkdir(parents=True)
    script = repo / "scripts" / "schedule" / "friday_run.sh"
    script.write_text(text(SCRIPT, mutation), encoding="utf-8")
    seen, notes, sec_args = repo / "python-saw.txt", repo / "notifications.txt", repo / "security-args.txt"
    envcheck = '[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && echo "ENV-LEAK:$0" >> "%s" || true\n' % notes
    security = stub(repo / "security", envcheck + 'printf "%%s|" "$@" > "%s"\n' % sec_args +
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
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    if unset_user:
        env.pop("USER", None)
    if inherited_token is not None:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = inherited_token
    got = subprocess.run(["/bin/bash", str(script)], cwd=str(tmp), env=env, capture_output=True, text=True, timeout=60)
    return {"code": got.returncode, "out": got.stdout + got.stderr,
            "saw": seen.read_text() if seen.exists() else "", "notes": notes.read_text() if notes.exists() else "",
            "script": script.read_text(), "security_args": sec_args.read_text() if sec_args.exists() else ""}


@contextlib.contextmanager
def stubbed_cli(pf, resolve=None):
    """Replace the module-under-test's cli_path for the checks that already stub `run=` (final re-review, N-1), so
    they hold whether or not a claude CLI resolves on this machine. auth_status looks cli_path up in its module's
    globals at call time, so this reaches it. `resolve` substitutes a different resolver (e.g. one that raises)."""
    real = pf.cli_path
    pf.cli_path = resolve or (lambda: STUB_CLI)
    try:
        yield
    finally:
        pf.cli_path = real


def git(repo: Path, *args) -> None:
    subprocess.run(["git", "-c", "user.email=g@g", "-c", "user.name=guard", *args], cwd=str(repo), check=True,
                   capture_output=True)


def is_tracing_enabled(source: str) -> bool:
    """Any `set` or `shopt` invocation that turns xtrace (or verbose) ON, anywhere on a line and in any flag
    combination -- `set -x`, `set -eux`, `set -u -x`, `true; set -x`, `shopt -so xtrace`, `set -o xtrace` -- not
    just a literal `set -x` line, and not just a line's FIRST flag word (fix round 1, M-3; fix round 2, N-3:
    `set -u -x` used to read only "-u", the first word, and pass). `set +x` / `set +o xtrace` / a `shopt` call
    that only NAMES xtrace without `-s`/`-o` enabling it must NOT trip this."""
    for raw in source.splitlines():
        line = raw.split("#", 1)[0]  # drop a trailing comment
        for stmt in line.split(";"):  # `true; set -x` -- a `set`/`shopt` need not open the line
            words = stmt.split()
            if not words or words[0] not in ("set", "shopt"):
                continue
            cmd, rest = words[0], words[1:]
            joined = " ".join(rest)
            if "-o xtrace" in joined or "-o verbose" in joined:  # "+o ..." (disabling) has no "-o" substring
                return True
            if cmd == "shopt" and "xtrace" in joined and "-u" not in rest[:1]:
                return True  # `shopt -so xtrace` / `shopt -s xtrace`; `shopt -u xtrace` (disabling) is exempt
            for word in rest:
                if word.startswith("-") and not word.startswith("--") and "x" in word[1:]:
                    return True
        if line.strip().startswith("printenv") or line.strip() == "env":
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
        # NO CHECK EVER STARTS AN AGENT SESSION, whatever a mutation disconnects. The scheduled path's session is
        # replaced here, before any check calls it, by a stub that records the call and writes an ordinary
        # refusal instead -- so a regression that lets a run through is SEEN (the stub was reached) and spends
        # nothing. `_scheduled` looks `friday` up in the module's globals at call time, so this reaches it.
        sessions = []

        async def no_session(run, root=inbox.INBOX_ROOT, **kw):
            sessions.append(run.run_id)
            return fr.write_refusal(run.run_id, ["GUARD STUB: the agent session would have started here"], root)
        fr.friday = no_session

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
                    and is_tracing_enabled("set -ux\n") and is_tracing_enabled("set -u -x\n")
                    and is_tracing_enabled("set -e -x\n") and is_tracing_enabled("true; set -x\n")
                    and is_tracing_enabled("shopt -so xtrace\n") and is_tracing_enabled("set -o xtrace\n")
                    and not is_tracing_enabled("set -u\n") and not is_tracing_enabled("set +x\n")
                    and not is_tracing_enabled("set +o xtrace +o verbose\n")
                    and not is_tracing_enabled(text(SCRIPT, mutation)),
                    "the launcher never enables tracing, in any `set`/`shopt` flag combination or position on "
                    "the line (fix round 2, N-3: `set -u -x` and `true; set -x` are now caught, not just a "
                    "line's first flag word)", ""))

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

        # --- fix round 2, N-2: an operator's shell that ALREADY exported a (different, dummy) CLAUDE_CODE_OAUTH_TOKEN
        # must not leak it anywhere -- friday_run.sh unsets it before reading the Keychain, so only the Keychain's
        # own sentinel ever reaches Python, and the dummy reaches no child at all (not even security or osascript).
        DUMMY_TOKEN = "dummy-inherited-from-the-operators-own-shell"
        inherited = launcher(tmp, mutation, token=True, exit_code=0, inherited_token=DUMMY_TOKEN)
        out.append((DUMMY_TOKEN not in inherited["out"] and DUMMY_TOKEN not in inherited["saw"]
                    and DUMMY_TOKEN not in inherited["notes"] and "ENV-LEAK" not in inherited["notes"]
                    and "token=yes" in inherited["saw"] and SENTINEL not in inherited["notes"],
                    "an inherited CLAUDE_CODE_OAUTH_TOKEN in the operator's own shell is unset before the "
                    "Keychain is read; only the Keychain's own token reaches Python, and the inherited dummy "
                    "reaches no child at all", "saw=%r notes=%r" % (inherited["saw"][:60], inherited["notes"][:60])))

        # --- final review M-3: with USER unset, `set -u` must not kill the Keychain read. The account falls back to
        # `id -un`, so the token is still read -- rather than the run REFUSING with a misleading "no token".
        me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
        nouser = launcher(tmp, mutation, token=True, exit_code=0, unset_user=True)
        out.append(("-a|%s|" % me in nouser["security_args"] and "token=yes" in nouser["saw"] and nouser["code"] == 0
                    and SENTINEL not in nouser["out"] + nouser["notes"],
                    "with USER unset, the launcher still reads the Keychain under the owner's account (id -un) and "
                    "hands the token to Python, instead of refusing with a misleading 'no token'",
                    "code=%s security=%r saw=%r" % (nouser["code"], nouser["security_args"][:60], nouser["saw"][:40])))

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
            # N-1: the resolver itself raising -- here stubbed, so this holds on a machine with no CLI too
            "no-cli-resolves": (stub_run(0, json.dumps({"loggedIn": True, "authMethod": "oauth_token"})), True),
        }
        from claude_agent_sdk import CLINotFoundError

        def unresolvable():
            raise CLINotFoundError("guard stub: no claude CLI resolves")
        auth_detail = {}
        auth_ok = True
        for name, (run_stub, should_refuse) in auth_cases.items():
            try:
                with stubbed_cli(pf, unresolvable if name == "no-cli-resolves" else None):
                    st = pf.auth_status(run_stub)
                verdict = pf.auth(st)
                crashed = False
            except Exception as exc:  # noqa: BLE001 -- a crash here IS the failure this check exists to catch
                verdict, crashed = None, True
            ok = (not crashed) and bool(verdict) == should_refuse
            auth_ok = auth_ok and ok
            auth_detail[name] = "crash" if crashed else bool(verdict)
        out.append((auth_ok, "auth_status refuses (never crashes, never passes) on a non-zero exit even with "
                    "well-formed JSON, on non-JSON output, on `null` or a list, on a missing claude binary, and when no "
                    "claude CLI resolves at all",
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

        # --- final review I-2: the preflight checks the claude the Agent SDK would START, not PATH's. The SDK's own
        # resolution is computed here from BOTH agents' real options, the way connect() does it
        # (claude_agent_sdk/_internal/transport/subprocess_cli.py:792-793: an options.cli_path wins, else
        # _find_cli()), so an agent that later pins a different cli_path turns this red too.
        import claude_agent_sdk
        from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
        from agents.extract_advisory import agent_options as extract_options
        from agents.run_identity import RunIdentity

        def sdk_would_start(options):
            t = SubprocessCLITransport(prompt="", options=options)
            return t._cli_path if t._cli_path is not None else t._find_cli()
        probe = RunIdentity(run_id="probe-check-schedule", stage="extractor", advisory_id="ADV-2026-0001",
                            pdf_path=ROOT / "data" / "advisories" / "fatf-tbml-2020.pdf", pdf_sha256="0" * 64)
        # THE ONE CHECK AGAINST THE REAL RESOLVER (final re-review, N-1). Where no CLI resolves, it SKIPS -- only if
        # the preflight agrees none resolves -- and a skip is reported as such, never counted as a pass.
        try:
            want = sorted({sdk_would_start(fr.of.agent_options(fr.of.FeedsRun("feeds-2026-10-09-ccc001"))),
                           sdk_would_start(extract_options("claude-sonnet-5", 1.0, 3, probe))})
        except Exception as exc:  # noqa: BLE001 -- judged below: CLINotFoundError may skip, anything else fails
            want = exc
        try:
            got_cli = pf.cli_path()
        except Exception as exc:  # noqa: BLE001
            got_cli = exc
        bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
        label = ("preflight.cli_path() is the claude binary the Agent SDK would start for both the orchestrator's "
                 "and the extractor's real options -- the bundled CLI when the SDK ships one, not PATH's")
        if isinstance(want, CLINotFoundError):
            agree = isinstance(got_cli, CLINotFoundError)
            out.append((None if agree else False, label,
                        ("SKIPPED: no claude CLI resolves on this machine (the SDK raised CLINotFoundError for both "
                         "agents' options, and so did preflight.cli_path()), so WHICH binary would spend cannot be "
                         "compared here; auth_status refuses in that state (the 'no-cli-resolves' case above)")
                        if agree else "sdk=CLINotFoundError preflight=%r -- the preflight answers a CLI the SDK "
                                      "cannot start" % (got_cli,)))
        else:
            same = isinstance(want, list) and want == [got_cli]
            out.append((same and (not bundled.is_file() or got_cli == str(bundled)), label,
                        "sdk=%s preflight=%s" % (want if isinstance(want, list) else repr(want),
                                                 got_cli if isinstance(got_cli, str) else repr(got_cli))))
        auth_argv = []
        with stubbed_cli(pf):
            pf.auth_status(run=lambda argv, **kw: (auth_argv.append(list(argv)), types.SimpleNamespace(
                returncode=0, stdout=json.dumps({"loggedIn": True, "authMethod": "oauth_token"}), stderr=""))[1])
        out.append((auth_argv == [[STUB_CLI, "auth", "status", "--json"]],
                    "auth_status runs `<cli_path()> auth status --json`: the CLI that spends, not the first "
                    "`claude` on PATH (cli_path stubbed, so this holds with no CLI on the machine)", auth_argv))

        # --- final review I-1: the seam --scheduled -> preflight.reasons(). Every check above that drives
        # --scheduled injects its reasons by hand; these inject NOTHING, so the REAL preflight.reasons() (the
        # module under test, mutations included) runs. Its own `run=` seam is stubbed -- no real git or claude
        # ever runs -- and a wrapper counts the calls. The session is the no_session stub installed above.
        fr.preflight = pf
        real_reasons = pf.reasons
        seam = {"calls": 0, "branch": "main", "auth": {"loggedIn": True, "authMethod": "oauth_token"}}

        def seam_run(argv, **kw):
            if argv[0] == "git":
                return types.SimpleNamespace(returncode=0, stdout=seam["branch"] + "\n", stderr="")
            if list(argv[1:]) == ["auth", "status", "--json"]:
                return types.SimpleNamespace(returncode=0, stdout=json.dumps(seam["auth"]), stderr="")
            raise AssertionError("the preflight ran something unexpected: %r" % (argv,))

        def recording_reasons(*a, **kw):
            seam["calls"] += 1
            kw["run"] = seam_run  # forced: whatever a caller passes, no real subprocess runs in this guard
            return real_reasons(*a, **kw)
        pf.reasons = recording_reasons
        env_names = ("ANTHROPIC_API_KEY",) + tuple(fr.EVAL_VARIABLES)

        def scheduled(label, branch="main", auth=None, env=None, pending=False):
            seam["branch"], seam["auth"] = branch, auth or {"loggedIn": True, "authMethod": "oauth_token"}
            box = tmp / ("inbox-seam-" + label)
            box.mkdir()
            if pending:
                inbox.save("feeds-2026-10-02-eee001", {"run_id": "feeds-2026-10-02-eee001", "sources": {"ofac": {
                    "items": [{"key": "ofac:%016x" % 3, "source": "ofac", "item_id": "z"}]}}}, box)
            calls, ran, posted = seam["calls"], len(sessions), []
            saved = {n: os.environ.pop(n, None) for n in env_names}  # the guard's own shell must not decide this
            os.environ.update(env or {})
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = fr.main(["--scheduled"], root=box, today=date(2026, 10, 9),
                                   notifier=lambda t, m: posted.append((t, m)) or True)
            finally:
                for n in env_names:
                    os.environ.pop(n, None)
                    if saved[n] is not None:
                        os.environ[n] = saved[n]
            this = sorted(p for p in box.glob("feeds-2026-10-09-*/" + fr.reconcile.REFUSAL))
            return {"code": code, "reasons_calls": seam["calls"] - calls, "session": len(sessions) - ran,
                    "notes": len(posted), "reasons": json.loads(this[0].read_text())["reasons"] if this else []}
        try:
            with stubbed_cli(pf):  # N-1: the seam's `run=` is stubbed, so its CLI resolution is too
                clean = scheduled("clean")
                wrong_auth = scheduled("auth", auth={"loggedIn": True, "authMethod": "claude.ai"})
                api_env = scheduled("env", env={"ANTHROPIC_API_KEY": "guard-dummy", "FEEDS_CATALOGUE": "guard-dummy"})
                everything = scheduled("all", branch="feature", pending=True,
                                       auth={"loggedIn": True, "authMethod": "claude.ai"})
        finally:
            pf.reasons = real_reasons
        out.append((clean["reasons_calls"] == 1 and clean["session"] == 1
                    and clean["reasons"] == ["GUARD STUB: the agent session would have started here"],
                    "--scheduled with no injected reasons calls the real preflight.reasons() once, and a clean "
                    "state (main, nothing pending, oauth_token, clean environment) goes on to the session", clean))
        out.append((wrong_auth["reasons_calls"] == 1 and wrong_auth["session"] == 0 and wrong_auth["code"] == RESERVED
                    and wrong_auth["notes"] == 1 and any("'claude.ai'" in r and "long-lived" in r
                                                         for r in wrong_auth["reasons"]),
                    "on the scheduled path, auth that is not the long-lived token refuses through preflight.reasons(): "
                    "no session, one notification, the reserved exit", wrong_auth))
        out.append((api_env["reasons_calls"] == 1 and api_env["session"] == 0 and api_env["code"] == RESERVED
                    and any("ANTHROPIC_API_KEY" in r for r in api_env["reasons"])
                    and any("FEEDS_CATALOGUE" in r for r in api_env["reasons"]),
                    "on the scheduled path, C1's refusals() still applies: an ANTHROPIC_API_KEY or FEEDS_CATALOGUE "
                    "in the environment refuses before any session", api_env))
        order = [next((i for i, r in enumerate(everything["reasons"]) if needle in r), -1)
                 for needle in ("not main", "unaccepted run", "'claude.ai'")]
        out.append((everything["session"] == 0 and -1 not in order and order == sorted(order),
                    "off main, with a pending run and the wrong auth, the scheduled path reports all three preflight "
                    "refusals together, in the fixed order branch, back-pressure, auth", everything["reasons"]))

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

        # --- fix round 2, N-1: a stdout write that raises AFTER the notification was posted must still leave the
        # TOTAL notification count at exactly one. `boom` arms itself the instant the notifier is called, so any
        # write to stdout from that point on (e.g. a regressed print between notify() and the return) raises --
        # simulating the same shape as an interpreter-shutdown flush failure, without needing a real subprocess.
        class ExplodeAfterArmed:
            armed = False
            def write(self, s):  # noqa: D102
                if self.armed:
                    raise OSError(28, "No space left on device")
                return len(s)
            def flush(self):  # noqa: D102
                if self.armed:
                    raise OSError(28, "No space left on device")
        boom = ExplodeAfterArmed()
        notes4 = []
        def arm_then_record(t, m):
            notes4.append((t, m))
            boom.armed = True
            return True
        with contextlib.redirect_stdout(boom), contextlib.redirect_stderr(io.StringIO()):
            code_post_notify = fr.main(["--scheduled"], root=tmp / "inbox-postnotify", today=date(2026, 10, 9),
                                       notifier=arm_then_record, preflight_reasons=["the checkout is on 'feature', not main"])
        total_after_notify = len(notes4) + (0 if code_post_notify in (0, RESERVED) else 1)
        out.append((total_after_notify == 1,
                    "a stdout write that raises AFTER the notification was posted still yields exactly one "
                    "notification in total: nothing that can raise runs between a successful notify() and the "
                    "return (fix round 2, N-1)",
                    "code=%s notes=%s total=%s" % (code_post_notify, notes4, total_after_notify)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the Friday schedule, launcher and preflight")
    ap.add_argument("--mutate", choices=sorted(TEXT_MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = skipped = 0
    for ok, label, detail in checks(args.mutate):
        if ok is None:  # N-1: a SKIP is neither a pass nor a failure, and says why in full
            print("  SKIP %s\n         %s" % (label, detail))
            skipped += 1
            continue
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:160]))
        failures += 0 if ok else 1
    skip_note = ", %d skipped" % skipped if skipped else ""
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed%s)" % (failures, "" if failures == 1 else "s",
                                                                                 skip_note)
                        if failures else "NOTHING PROVED: every check passed with the rule broken%s" % skip_note))
        return 0 if failures else 1
    print("\n%s (%d failure%s%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s",
                                     skip_note))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
