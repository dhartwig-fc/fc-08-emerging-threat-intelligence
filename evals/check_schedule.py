"""
Pin the Friday schedule, its launcher, its preflight and its one notification (slice 2 C2, spec section 5).

Usage:
    python evals/check_schedule.py
    python evals/check_schedule.py --mutate log-token        # friday_run.sh prints the token
    python evals/check_schedule.py --mutate keep-api-key     # friday_run.sh leaves ANTHROPIC_API_KEY set
    python evals/check_schedule.py --mutate double-notify    # friday_run.sh notifies on every run, not only a crash
    python evals/check_schedule.py --mutate wrong-day        # the plist fires on Mondays
    python evals/check_schedule.py --mutate token-in-plist   # the plist carries a token variable
    python evals/check_schedule.py --mutate any-auth         # the preflight accepts the interactive login
    python evals/check_schedule.py --mutate no-branch-check  # the preflight runs off main
    python evals/check_schedule.py --mutate no-back-pressure # the preflight ignores an unaccepted run
    python evals/check_schedule.py --mutate silent-refusal   # a refused scheduled run posts no notification

WHAT IT HOLDS:
  the plist     renders to a valid plist: label uk.fc08.friday-run; Fridays (Weekday 5) at 09:00; runs
                /bin/bash scripts/schedule/friday_run.sh of THIS checkout; logs under ~/Library/Logs; RunAtLoad
                false; no environment but PATH, and no token anywhere in it;
  schedule.py   install writes exactly the rendered plist and bootstraps gui/<uid>; refuses a second install;
                --dry-run writes nothing; uninstall boots out and removes it; status only reads;
  the launcher  run with stub security, python and osascript: the token reaches Python as
                CLAUDE_CODE_OAUTH_TOKEN and appears in NO output, notification or argument; ANTHROPIC_API_KEY is
                unset; no token -> Python is told to refuse; a normal exit posts no second notification; a
                crash (exit 3) posts exactly one; the script never enables tracing;
  the preflight off main, detached, a pending run under 14 days, and any auth but loggedIn "oauth_token"
                each refuse; a clean state passes;
  one notice    friday_run --scheduled, refused, writes a REFUSED report and posts exactly one notification
                whose words are the report's first two lines.

COLD. Temporary folders, temporary git repositories, stub commands. It never runs launchctl, never reads the
Keychain, never runs the claude CLI, and never writes ~/Library.

NOT A VACUOUS PASS. Each --mutate rewrites the script, the template or a module in memory or in a temporary
copy; at least one check must fail.
"""

from __future__ import annotations

import argparse
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

SCRIPT = ROOT / "scripts" / "schedule" / "friday_run.sh"
TEMPLATE = ROOT / "scripts" / "schedule" / "uk.fc08.friday-run.plist"
PREFLIGHT = ROOT / "feeds" / "preflight.py"
FRIDAY = ROOT / "tools" / "friday_run.py"
SCHEDULE = ROOT / "tools" / "schedule.py"
SENTINEL = "sk-ant-oat01-SENTINEL-never-print-me"
TEXT_MUTATIONS = {
    "log-token": (SCRIPT, 'if [ -z "$FC08_TOKEN" ]; then\n', 'echo "token $FC08_TOKEN"\nif [ -z "$FC08_TOKEN" ]; then\n'),
    "keep-api-key": (SCRIPT, "unset ANTHROPIC_API_KEY\n", ""),
    "double-notify": (SCRIPT, 'if [ "$code" -ge 2 ]; then\n', 'if [ "$code" -ge 0 ]; then\n'),
    "wrong-day": (TEMPLATE, "<key>Weekday</key>\n        <integer>5</integer>", "<key>Weekday</key>\n        <integer>1</integer>"),
    "token-in-plist": (TEMPLATE, "        <key>PATH</key>\n", "        <key>CLAUDE_CODE_OAUTH_TOKEN</key>\n        <string>x</string>\n"
                                                          "        <key>PATH</key>\n"),
    "any-auth": (PREFLIGHT, "    if status.get(\"authMethod\") != TOKEN_METHOD:\n", "    if False:\n"),
    "no-branch-check": (PREFLIGHT, '    if got.returncode != 0 or branch != "main":\n', "    if False:\n"),
    "no-back-pressure": (PREFLIGHT, "    if waiting:\n", "    if False:\n"),
    "silent-refusal": (FRIDAY, "    (notifier or notify.notify)(*notify.from_report(path))\n",
                       "    if not reasons:\n        (notifier or notify.notify)(*notify.from_report(path))\n"),
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
    """Run a copy of friday_run.sh in a fake repo with stub security, python and osascript."""
    repo = tmp / ("repo-%s-%d" % (token, exit_code))
    (repo / "scripts" / "schedule").mkdir(parents=True)
    script = repo / "scripts" / "schedule" / "friday_run.sh"
    script.write_text(text(SCRIPT, mutation), encoding="utf-8")
    seen, notes = repo / "python-saw.txt", repo / "notifications.txt"
    security = stub(repo / "security", 'if [ "$STUB_HAS_TOKEN" = 1 ]; then echo "%s"; else exit 44; fi\n' % SENTINEL)
    python = stub(repo / "python", (
        '{ [ "${CLAUDE_CODE_OAUTH_TOKEN:-}" = "%s" ] && echo token=yes || echo token=no\n'
        '  [ -n "${ANTHROPIC_API_KEY:-}" ] && echo apikey=set || echo apikey=unset\n'
        '  echo "args=$*"; } > "%s"\nexit "$STUB_EXIT"\n') % (SENTINEL, seen))
    osa = stub(repo / "osascript", 'for a in "$@"; do printf "%%s|" "$a"; done >> "%s"; echo >> "%s"\n' % (notes, notes))
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


def checks(mutation) -> list:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # --- the plist, rendered from the (possibly mutated) template
        sched = module("schedule_under_test", SCHEDULE, None)
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

        # --- the launcher, with stubs
        ok = launcher(tmp, mutation, token=True, exit_code=0)
        crash = launcher(tmp, mutation, token=True, exit_code=3)
        none = launcher(tmp, mutation, token=False, exit_code=1)
        leaked = [n for n, r in (("ok", ok), ("crash", crash), ("none", none))
                  if SENTINEL in r["out"] or SENTINEL in r["notes"] or SENTINEL in r["saw"]]
        out.append((not leaked and "token=yes" in ok["saw"] and "token=no" in none["saw"],
                    "the token reaches Python as CLAUDE_CODE_OAUTH_TOKEN and appears in no output, notification or "
                    "argument", "leaked in %s; saw %r" % (leaked, ok["saw"][:40])))
        out.append(("apikey=unset" in ok["saw"] and "apikey=unset" in none["saw"],
                    "ANTHROPIC_API_KEY is unset before Python starts", ok["saw"].split("\n")[1:2]))
        out.append(("--refuse" in none["saw"] and "Keychain" in none["saw"] and none["code"] == 1,
                    "with no token in the Keychain, Python is told to refuse (and reports it)", none["saw"][-80:]))
        out.append((ok["notes"] == "" and none["notes"] == "" and crash["notes"].count("\n") == 1
                    and "CRASHED" in crash["notes"] and crash["code"] == 3,
                    "a normal or refused exit adds no notification of the script's own; a crash posts exactly one",
                    "ok %r | crash %r" % (ok["notes"][:30], crash["notes"][:60])))
        body = [l.strip() for l in SCRIPT.read_text().splitlines() if not l.strip().startswith("#")]
        out.append((not any(l.startswith("set -x") or "set -o xtrace" in l or l.startswith("printenv") or l == "env"
                            for l in body),
                    "the launcher never enables tracing or dumps its environment", ""))

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

        # --- one notification for a refused scheduled run
        fr = module("friday_under_test", FRIDAY, mutation)
        notes = []
        with contextlib.redirect_stdout(io.StringIO()):
            code = fr.main(["--scheduled"], root=tmp / "inbox2", today=date(2026, 10, 9), notifier=lambda t, m: notes.append((t, m)),
                           preflight_reasons=["the checkout is on 'feature', not main"])
        reports = list((tmp / "inbox2").glob("feeds-*/report.md"))
        head = reports[0].read_text().splitlines()[0] if reports else ""
        out.append((code == 1 and len(notes) == 1 and notes[0][0] == "FC08 Friday run: REFUSED" and "REFUSED" in head
                    and "not main" in notes[0][1],
                    "a refused scheduled run writes a REFUSED report and posts exactly one notification, from the "
                    "report's own first lines", notes))
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
