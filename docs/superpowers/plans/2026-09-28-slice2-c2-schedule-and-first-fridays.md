# Slice 2 C2: The Schedule, the Preflight, and the First Live Fridays Implementation Plan

> **Approved by the owner on 2026-09-28: "accept all recommendations".** Every decision in "For the owner" is taken as recommended (decisions 1-11). Drafted and verified in a scratch clone of `main` at `2375fd8`; re-check each edit's anchor before running it if `main` has moved.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Every STOP is a hard stop. Every OWNER STEP is run by the owner in their own Terminal, never by an agent:** the token, `launchctl`, and anything that reads the Keychain.

## For the owner

### Decisions this plan needed from you (taken 2026-09-28: all as recommended) (C1's decisions 1 to 11 are in the C1 plan; these are the ones C2 turns on)

1. **The long-lived token (C1's decision 6).** **Recommended: login Keychain, service `uk.fc08.claude-oauth-token`, account `$USER`,** read at run time by `scripts/schedule/friday_run.sh` into the Python run's environment as `CLAUDE_CODE_OAUTH_TOKEN`, and nowhere else.
   - It is never in the repository, the plist or the log; the guard proves it with a sentinel token and stub commands.
   - You create it (`claude setup-token`) and store it (`security add-generic-password ... -w`, which prompts for the value) by hand in Task 4.
   - Claude never creates, reads, prints or enters it.
   - Residual, stated rather than hidden: the `claude` CLI hands its environment to the MCP servers it starts, so the token is in those child processes' environments for the run's duration. It is not written anywhere.
2. **Installing launchd (C1's decision 7).** **Recommended: you run `tools/schedule.py install` yourself (Task 6),** after one rehearsal and one real run by hand. `install` writes `~/Library/LaunchAgents/uk.fc08.friday-run.plist` and runs `launchctl bootstrap gui/<uid>`; `uninstall` reverses both. An agent runs `status` at most, which only reads.
3. **The first run through the launcher, before launchd (Task 5).** **Recommended: two by hand.**
   - A zero-cost rehearsal on a branch, which the preflight refuses. It proves the Keychain read, the refusal report and the one notification, and it is where macOS asks you once to "Always Allow" `security` to read the item.
   - Then one real run on `main`: up to US$5.

   The alternative is to let the first launchd Friday be the first run through the launcher, and debug a missed notification a week later.
4. **What the preflight accepts as auth.** It requires `claude auth status --json` to say `loggedIn: true` and `authMethod: "oauth_token"`. **That string was read from the installed CLI's code (2.1.269), not observed with a token.** Task 4 has you confirm it: the command prints the method and never the token. If it prints something else, `TOKEN_METHOD` changes, with its guard, before Task 5.

### Measured for this draft (2026-09-28)

- macOS 14.8.9 (23J631). `~/Library/LaunchAgents` exists, holding 6 entries, none for fc08. **Nothing was created there, and `launchctl` was never run.**
- `claude --version`: 2.1.269. `claude auth status`: `authMethod: "claude.ai"` (the interactive login, which expires), `loggedIn: true`, subscription `max`. `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` are unset in this shell. So today the scheduled preflight would refuse, correctly, until Task 4.
- The installed CLI's own code maps a token read from the environment to `authMethod: "oauth_token"`. It also carries a warning that a `CLAUDE_CODE_OAUTH_TOKEN` "has no refresh token ... and has likely expired" when it fails. The long-lived token does expire; the preflight and the FAILED report are where you will see it.
- `plutil -lint` on the template: OK. `bash -n` on the launcher: OK.

### Verification done for this draft

- Every code block below was run in the scratch clone on top of C1:
  - `check_schedule`: 12 checks `HELD`, and its 9 named mutations each detected;
  - `tools/check_all.py --cold` on C1 plus C2: 33 run, 0 failed besides the C1 republish obligation (resolved by C1 Task 6);
  - `check_friday_run` and `check_accept_run` still `HELD` after the `--scheduled` edits.
- The C2 edits and files were re-applied mechanically on top of a mechanically reproduced C1 and matched the tested files byte for byte.
- **The launcher was run for real, with stubs:**
  - stub `security`, `python` and `osascript`, with a sentinel token that appeared in no output, notification or argument;
  - `ANTHROPIC_API_KEY=leak-me` set on entry and unset by the time Python started;
  - a crash (exit 3) posted exactly one notification;
  - a normal exit posted none of the script's own.
- **Not verified:**
  - the real `security` read and its first-use prompt;
  - a real `osascript` notification (macOS may ask to allow notifications for Script Editor / osascript);
  - `launchctl bootstrap`;
  - the `oauth_token` method string;
  - any model run.

  Tasks 4 to 7 are where each is seen for the first time, by you.

### What I think is wrong or unworkable in the spec (C2's part)

1. **The auth preflight can only read the CLI's local status.** A revoked or expired token may still report `loggedIn`. The first model call then fails, and the run is FAILED, with a loud report and a notification. A live ping would itself be a model call; this plan does not add one.
2. **"launchd running weekly" has conditions launchd imposes:**
   - a LaunchAgent runs only while you are logged in;
   - a Mac asleep at 09:00 runs the job when it wakes;
   - a Mac powered off skips that Friday.

   A skipped Friday leaves no report, because nothing ran. The absence of a Friday notification is the only signal.
3. **"One macOS notification at the end."** Python posts it: the report's own first two lines, refusals included. The shell posts one only when Python never got that far (exit 2 or more). A run that hangs posts nothing until it ends; the SDK's turn and budget caps bound it.
4. **Back-pressure makes the manual runs and the schedule interact.** A run left pending blocks every scheduled run for 14 days from its date. So C1's dry run, and C2 Task 5's run, must be decided (accepted, or all dropped or deferred) before the first launchd Friday, or that Friday is REFUSED, loudly and harmlessly.

### Expected spend (C2)

- **Task 5's real run by hand:** capped at US$5, expected US$2 to US$3.50.
- **Task 7, the first launchd Friday:** capped at US$5, expected US$2 to US$3.50.
- The rehearsal (Task 5 Step 1): US$0; the preflight refuses before any agent.
- **C2 in all: at most US$10, expected US$4 to US$7.** C1 and C2 together: at most US$15, expected US$6 to US$10.5. Notional on the subscription token.

---

**Goal:**
- The scheduled half of the spec's section 5:
  - `tools/friday_run.py --scheduled`, with the preflight (on `main`, back-pressure, auth) and one notification;
  - `scripts/schedule/friday_run.sh`, which reads the token from the Keychain;
  - the plist template, and `tools/schedule.py install|uninstall|status`.
- Then the first live Fridays and the first accepted run, each an explicit STOP.

**Architecture:**
- **The launcher.** launchd starts `friday_run.sh`. It unsets `ANTHROPIC_API_KEY`, reads the token from the Keychain, and runs `tools/friday_run.py --scheduled` with the token in that command's environment.
- **The preflight.** `feeds/preflight.py` returns the refusals: the branch, a pending run under 14 days old (`feeds/runs.py`, eval runs excluded), and the CLI's own auth summary. A refusal goes through C1's `write_refusal`, so it is a run folder with a REFUSED report like any other.
- **The notification.** `feeds/notify.py` posts one, from the report's own first two lines, passing the words to `osascript` as arguments rather than as AppleScript source.
- **`schedule.py` renders and installs.** It renders the tracked template with this checkout's path, and installs or removes it only when the owner runs it.

**Tech Stack:** as C1, plus `/bin/bash` 3.2, `/usr/bin/security`, `/usr/bin/osascript` and `/bin/launchctl` (all macOS built-ins, all stubbed in the guard).

**Spec:** sections 2 (the notification) and 5 (the schedule, auth), section 6's week 5, and definition-of-done items 4, 6 and 7.

## Global Constraints

C1's Global Constraints hold. In addition:
- Commit messages start `Slice 2 C2:`.
- **No agent runs `launchctl`, `security`, `claude setup-token`, `schedule.py install` or `schedule.py uninstall`, or `friday_run.sh`.** Those are OWNER STEPS. An agent may run `tools/schedule.py status` (read-only) and every guard.
- The token is never:
  - written to a file, the plist, the log or a report;
  - echoed, or put on a command line;
  - asked for in chat.

  If the owner pastes it in chat by mistake, tell them to revoke it and mint a new one.
- The guard runs the launcher only as a COPY in a temporary folder, with stub commands. It never touches `~/Library` or the Keychain.

## Rulings made while writing this plan

1. **The token in the Keychain.** Service `uk.fc08.claude-oauth-token`, account `$USER`, read by `security find-generic-password -w` at run time.
2. **A refusal the shell finds** (no token) reaches Python as `--refuse "<reason>"`. Python writes the report and posts the notification, so every refusal looks the same.
3. **The preflight's three checks, in a fixed order:**
   - branch `main` exactly (`git rev-parse --abbrev-ref HEAD`; a detached HEAD reads `HEAD` and refuses);
   - `feeds.runs.blocking()`;
   - `loggedIn` with `authMethod == "oauth_token"`.

   All three are reported together, not the first alone.
4. **A crash exits 3 without notifying.** The shell notifies for any exit of 2 or more, so exactly one notification reaches you either way.
5. **The plist:**
   - `StartCalendarInterval` Weekday 5, Hour 9, Minute 0 (local time);
   - `RunAtLoad` false;
   - `EnvironmentVariables` holds only `PATH` (`~/.local/bin` first, where the `claude` CLI is installed);
   - the log goes to `~/Library/Logs/uk.fc08.friday-run.log`, outside the repository.

   The template carries `__REPO__` and `__HOME__`, rendered at install.
6. **`install` refuses when a plist is already installed** (uninstall first), so a schedule is never silently replaced.

## File map

| File | Task | Responsibility |
|---|---|---|
| `feeds/preflight.py` | 1 | on main, back-pressure, auth |
| `feeds/notify.py` | 1 | one notification from the report's first lines |
| `tools/friday_run.py` | 1 | `--scheduled`, `--refuse` |
| `scripts/schedule/friday_run.sh` | 1 | the launcher: the Keychain, the environment, the crash notification |
| `scripts/schedule/uk.fc08.friday-run.plist` | 1 | the tracked template |
| `tools/schedule.py` | 1 | install, uninstall, status |
| `evals/check_schedule.py` | 1 | NEW guard, 9 mutations |
| `tools/check_all.py` | 1 | registration |
| `CLAUDE.md` | 2 | the record, and the owner's runbook |

---

### Task 0: an item already decided in an earlier run does not refuse its whole run (C1 final review I-3; owner ruling A, 2026-09-29)

**Why first.** Task 1 wires back-pressure to `runs.blocking`. Today, `tools/accept_run.plan()` refuses a WHOLE run if any item it lists is already in the ledger (`accept_run.py`, the `already decided in an earlier run` raise). Deferring that item does not help, and `--expire` refuses anything under 14 days. So when two runs list the same item and the older is accepted, the newer run can be neither accepted nor expired, and it blocks every Friday until day 14. C1's final review reproduced this. Owner ruling (option A): **an item already in the ledger counts as decided in its earlier run, and the rest of the run is decided as normal.**

**Files:** `tools/accept_run.py` (`plan`, `apply`, `ask`, the RECORDED line), `evals/check_accept_run.py`, CLAUDE.md's C1 `accept_run` row.

- [ ] **Step 1: The failing guard case.** Build it in `check_accept_run` from the review's reproduction:
  - runs A (2026-10-02) and B (2026-10-09) both list item X, and B also lists a new item Y;
  - accept A with X dropped;
  - then accept B.

  The case asserts all of the following:
  1. B is RECORDED;
  2. Y's decision is in the ledger;
  3. X's ledger entry is byte-identical to A's (its `first_seen_run`, `decision` and `decided_on` are unchanged);
  4. B's `accepted.json` names X as "decided in A", not as a decision of B's;
  5. `runs.blocking` no longer lists B.

  Run it and watch it fail on the current raise.
- [ ] **Step 2: Implement.**
  - **In `plan()`,** partition the listed items. Items already in the ledger are carried as `already_decided: {key: <first_seen_run>}`; everything else goes through the usual per-item rules.
  - **An item already decided,** whatever the decision file says for it:
    - is never re-recorded, and the ledger is never rewritten for it;
    - a decision file that tries to ACCEPT it is refused, naming the earlier run, because an accept would copy a second record for an item the ledger already closed;
    - a drop or defer for it is ignored, with a note.
  - **If every listed item is already decided,** the run is still recorded as accepted, with 0 new decisions, so it stops blocking.
  - **`ask()`** shows those items as "already decided in <run>" and asks nothing about them.
  - **The RECORDED line** counts them separately.
- [ ] **Step 3: Mutations.**
  - `whole-run-refusal`: restore the old raise. The Step 1 case must go red.
  - `redecide-seen`: let an already-decided item be re-recorded. The byte-identical-entry assertion must go red.

  Run each one on its own, with its own `PYTHONPYCACHEPREFIX`.
- [ ] **Step 4: Full check.**
  - Run `check_accept_run` plain, then `tools/check_all.py --cold`.
  - Update CLAUDE.md's `accept_run` row and the `check_accept_run` mutation list.
- [ ] **Step 5: Commit.**
  ```bash
  git add tools/accept_run.py evals/check_accept_run.py CLAUDE.md
  git commit -m "Slice 2 C2: an item already decided in an earlier run is carried, not refused -- two overlapping runs can both be accepted (owner ruling A)"
  ```

### Task 1: the scheduled run: preflight, notification, launcher, plist and `schedule.py`

**Files:**
- Create: `feeds/preflight.py`, `feeds/notify.py`, `scripts/schedule/friday_run.sh` (mode 755), `scripts/schedule/uk.fc08.friday-run.plist`, `tools/schedule.py`, `evals/check_schedule.py`
- Modify: `tools/friday_run.py`, `tools/check_all.py`

**Interfaces:**
- `feeds.preflight`:
  - `on_main(repo, run)`, `back_pressure(root, today)`, `auth_status(run)`, `auth(status)`;
  - `reasons(repo, root, today, run, status) -> [str]`;
  - `TOKEN_METHOD = "oauth_token"`.
- `feeds.notify`: `from_report(path) -> (title, message)`, `notify(title, message, run)`.
- `tools.friday_run.main(..., preflight_reasons=, notifier=)`, with `--scheduled` and `--refuse REASON`.
- `tools.schedule.main(argv, agents, run, uid, home)`, `render(repo, home)`, `LABEL = "uk.fc08.friday-run"`.

- [ ] **Step 1: Write the guard first**

Create `evals/check_schedule.py`:

```python
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
```

- [ ] **Step 2: Create the preflight and the notification**

`feeds/preflight.py`:

```python
"""
The scheduled run's preflight (slice 2 C2, spec section 5): three refusals, each written up as a run report
with a notification by tools/friday_run.py --scheduled, and none of them spends anything.

  on main       the checkout is on branch `main` (a detached HEAD or a feature branch refuses): a Friday run
                reads the committed ledger, prompts and guards, and must read the governed ones;
  back-pressure a pending run under 14 days old is still in the inbox (feeds/runs.py; eval runs never count);
  auth          `claude auth status --json` says loggedIn with authMethod "oauth_token", the long-lived
                subscription token (`claude setup-token`). "claude.ai" is the interactive login, which expires
                (CLAUDE.md, Auth); "api_key" means ANTHROPIC_API_KEY, which bills pay-as-you-go.
The expected method string was READ from the installed CLI (2.1.269), not observed with a token: its status
code maps a token from the environment to "oauth_token". C2 Task 5 has the owner confirm it by hand.
The token itself is never read here: only the CLI's own summary of it.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import List, Optional

from feeds import inbox, runs

TOKEN_METHOD = "oauth_token"


def on_main(repo: Path, run=subprocess.run) -> Optional[str]:
    got = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), capture_output=True, text=True)
    branch = (got.stdout or "").strip()
    if got.returncode != 0 or branch != "main":
        return "the checkout is on %r, not main" % (branch or got.stderr.strip()[:80])
    return None


def back_pressure(root: Path = inbox.INBOX_ROOT, today: date = None) -> Optional[str]:
    waiting = runs.blocking(root, today)
    if waiting:
        return ("an unaccepted run is still in the inbox: %s -- accept it (tools/accept_run.py) or, from 14 days, "
                "expire it (tools/accept_run.py --expire)" % ", ".join("%s (%d days)" % (r, a) for r, a in waiting))
    return None


def auth_status(run=subprocess.run) -> dict:
    """The CLI's own JSON summary; {"error": ...} when it cannot be had. Only the fields named are kept."""
    try:
        got = run(["claude", "auth", "status", "--json"], capture_output=True, text=True, timeout=60)
        data = json.loads(got.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}
    return {k: data.get(k) for k in ("loggedIn", "authMethod")}


def auth(status: dict) -> Optional[str]:
    if status.get("error"):
        return "the auth preflight could not run `claude auth status`: %s" % status["error"]
    if status.get("loggedIn") is not True:
        return "the claude CLI is not logged in: the long-lived token is missing, revoked or expired"
    if status.get("authMethod") != TOKEN_METHOD:
        return ("the claude CLI authenticates by %r, not the long-lived subscription token (%r)"
                % (status.get("authMethod"), TOKEN_METHOD))
    return None


def reasons(repo: Path, root: Path = inbox.INBOX_ROOT, today: date = None, run=subprocess.run,
            status: dict = None) -> List[str]:
    found = [on_main(repo, run), back_pressure(root, today), auth(status if status is not None else auth_status(run))]
    return [r for r in found if r]
```

`feeds/notify.py`:

```python
"""
The one macOS notification at the end of a scheduled run (slice 2 C2, spec section 2).

The text is the report's own first two lines -- "# Friday run <id>: <STATUS>" and its one-sentence summary --
so the notification can never say more, or other, than the report. The words reach osascript as ARGUMENTS
(`on run argv`), never spliced into AppleScript source, so a title with a quote cannot become code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

OSASCRIPT = "/usr/bin/osascript"
SCRIPT = ("on run argv", "display notification (item 1 of argv) with title (item 2 of argv)", "end run")


def from_report(path: Path) -> tuple:
    lines = [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    head = lines[0].lstrip("# ") if lines else "Friday run: no report"
    status = head.rsplit(": ", 1)[-1]
    return "FC08 Friday run: %s" % status, (lines[1] if len(lines) > 1 else head)[:220]


def notify(title: str, message: str, run=subprocess.run) -> bool:
    argv = [OSASCRIPT]
    for line in SCRIPT:
        argv += ["-e", line]
    got = run(argv + [message, title], capture_output=True, text=True, timeout=30)
    return got.returncode == 0
```

- [ ] **Step 3: `tools/friday_run.py --scheduled`**

In `tools/friday_run.py` (edit `c2-friday-doc`), replace:

```python
Sub-project C2 adds the scheduled preflight (on main, back-pressure, auth) through the same refusal path.
```

with:

```python
With --scheduled (C2; scripts/schedule/friday_run.sh passes it) it also refuses, through the same path, when
feeds/preflight.py finds the checkout off main, an unaccepted run under 14 days old, or auth that is not the
long-lived token -- and whatever friday_run.sh itself refused (--refuse REASON, e.g. no token in the Keychain).
Then it posts ONE notification, the report's first two lines (feeds/notify.py). A crash in scheduled mode exits 3
without notifying, and friday_run.sh posts the one notification instead.
```

In `tools/friday_run.py` (edit `c2-friday-import`), replace:

```python
from feeds import extraction, inbox, reconcile, report  # noqa: E402
```

with:

```python
from feeds import extraction, inbox, notify, preflight, reconcile, report  # noqa: E402
```

In `tools/friday_run.py` (edit `c2-friday-main`), replace:

```python
def main(argv: list, root: Path = inbox.INBOX_ROOT, today: date = None, extra_refusals=None) -> int:
    ap = argparse.ArgumentParser(description="One Friday feeds run")
    ap.add_argument("--plan", action="store_true", help="print the budget and caps; start nothing")
    args = ap.parse_args(argv)
```

with:

```python
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
        except Exception:  # noqa: BLE001 -- friday_run.sh posts the one notification for a crash
            import traceback
            traceback.print_exc()
            return 3
```

In `tools/friday_run.py` (edit `c2-friday-scheduled`), replace:

```python
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

with:

```python
def _scheduled(args, root, today, extra_refusals, preflight_reasons, notifier) -> int:
    run = of.FeedsRun(inbox.mint_run_id(today or date.today()))
    telemetry.TELEMETRY_DIR = inbox.run_dir(run.run_id, root) / inbox.TELEMETRY
    found = preflight.reasons(ROOT, root, today) if preflight_reasons is None else list(preflight_reasons)
    reasons = refusals() + list(extra_refusals or []) + list(args.refuse) + found
    rec = write_refusal(run.run_id, reasons, root) if reasons else asyncio.run(friday(run, root=root))
    path = inbox.run_dir(run.run_id, root) / report.REPORT
    (notifier or notify.notify)(*notify.from_report(path))
    print("%s: %s -- %s" % (run.run_id, rec["status"], path))
    return 0 if rec["status"] in reconcile.ACCEPTABLE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```


- [ ] **Step 4: The launcher, the template, and `schedule.py`**

`scripts/schedule/friday_run.sh` (then `chmod 755 scripts/schedule/friday_run.sh`):

```bash
#!/bin/bash
# FC08 Friday run, started by launchd (scripts/schedule/uk.fc08.friday-run.plist, installed by the OWNER with
# tools/schedule.py install). Bash 3.2: no arrays of pairs, no mapfile.
#
# THE TOKEN. The long-lived subscription token (`claude setup-token`, run by the owner) lives in the login
# Keychain under service uk.fc08.claude-oauth-token. This script reads it into ONE variable and hands it to the
# Python run as CLAUDE_CODE_OAUTH_TOKEN in that command's environment only. It is never written to a file,
# never printed, never on a command line, never in the plist or the log. Nothing here enables `set -x`.
# ANTHROPIC_API_KEY is unset first: it takes precedence over the token and bills pay-as-you-go (CLAUDE.md, Auth).
#
# ONE NOTIFICATION. tools/friday_run.py --scheduled posts it (the report's first two lines), refusals included.
# This script posts one only when Python never got that far: exit 2 or more (a crash, a missing interpreter).
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE="${FC08_KEYCHAIN_SERVICE:-uk.fc08.claude-oauth-token}"
SECURITY="${FC08_SECURITY:-/usr/bin/security}"
OSASCRIPT="${FC08_OSASCRIPT:-/usr/bin/osascript}"
PYTHON="${FC08_PYTHON:-$REPO/.venv/bin/python}"

notify() {
    "$OSASCRIPT" -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' \
        -e 'end run' "$1" "FC08 Friday run: CRASHED" >/dev/null 2>&1 || true
}

cd "$REPO" || { notify "The repository is not at $REPO."; exit 2; }
unset ANTHROPIC_API_KEY
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) friday_run.sh start in $REPO"

FC08_TOKEN="$("$SECURITY" find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null)"
if [ -z "$FC08_TOKEN" ]; then
    "$PYTHON" tools/friday_run.py --scheduled --refuse "no long-lived token in the login Keychain (service $SERVICE)"
    code=$?
else
    CLAUDE_CODE_OAUTH_TOKEN="$FC08_TOKEN" "$PYTHON" tools/friday_run.py --scheduled
    code=$?
fi
FC08_TOKEN=""
unset FC08_TOKEN
if [ "$code" -ge 2 ]; then
    notify "The run did not finish (exit $code). See ~/Library/Logs/uk.fc08.friday-run.log"
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) friday_run.sh end, exit $code"
exit "$code"
```

`scripts/schedule/uk.fc08.friday-run.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- FC08 Friday run: every Friday at 09:00 local time. A TEMPLATE: tools/schedule.py install renders
     __REPO__ and __HOME__ and writes the result to ~/Library/LaunchAgents/. It carries no token and no
     environment beyond PATH; friday_run.sh reads the token from the Keychain at run time. -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>uk.fc08.friday-run</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>__REPO__/scripts/schedule/friday_run.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>5</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>__HOME__/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>__HOME__/Library/Logs/uk.fc08.friday-run.log</string>
    <key>StandardErrorPath</key>
    <string>__HOME__/Library/Logs/uk.fc08.friday-run.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

`tools/schedule.py`:

```python
"""
Install, remove or inspect the Friday schedule (slice 2 C2, spec section 5). NOTHING INSTALLS ITSELF.

Usage:
    python tools/schedule.py status               # read-only: installed? loaded? matches the template?
    python tools/schedule.py install [--dry-run]  # OWNER ONLY: render the plist into ~/Library/LaunchAgents, bootstrap
    python tools/schedule.py uninstall [--dry-run]  # OWNER ONLY: bootout, and remove the rendered plist

install and uninstall change persistent user configuration (launchd), so they are run by the owner by hand;
an agent runs `status` at most. The template is scripts/schedule/uk.fc08.friday-run.plist: __REPO__ becomes this
checkout, __HOME__ the home folder. launchctl is `bootstrap gui/<uid> <plist>` and `bootout gui/<uid>/<label>`.
install refuses when a plist is already installed (uninstall first), so a schedule is never silently replaced.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "uk.fc08.friday-run"
TEMPLATE = ROOT / "scripts" / "schedule" / ("%s.plist" % LABEL)
AGENTS = Path.home() / "Library" / "LaunchAgents"
LAUNCHCTL = "/bin/launchctl"


def render(repo: Path = ROOT, home: Path = Path.home()) -> bytes:
    text = TEMPLATE.read_text(encoding="utf-8").replace("__REPO__", str(repo)).replace("__HOME__", str(home))
    plistlib.loads(text.encode("utf-8"))  # refuses a template that does not parse
    return text.encode("utf-8")


def installed_path(agents: Path = AGENTS) -> Path:
    return Path(agents) / ("%s.plist" % LABEL)


def main(argv: list, agents: Path = AGENTS, run=subprocess.run, uid: int = None, home: Path = None) -> int:
    ap = argparse.ArgumentParser(description="Manage the Friday launchd schedule")
    ap.add_argument("action", choices=("install", "uninstall", "status"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    uid = os.getuid() if uid is None else uid
    target = installed_path(agents)
    want = render(ROOT, home or Path.home())
    if args.action == "status":
        on_disk = target.read_bytes() if target.exists() else None
        got = run([LAUNCHCTL, "print", "gui/%d/%s" % (uid, LABEL)], capture_output=True, text=True)
        print("installed: %s" % ("no" if on_disk is None else target))
        print("matches the template: %s" % ("-" if on_disk is None else on_disk == want))
        print("loaded in launchd: %s" % ("yes" if got.returncode == 0 else "no"))
        for line in (got.stdout or "").splitlines():
            if line.strip().startswith(("state =", "last exit code =", "runs =")):
                print("  %s" % line.strip())
        return 0
    if args.action == "install":
        if target.exists():
            print("REFUSED: %s is already installed; run uninstall first" % target)
            return 1
        if args.dry_run:
            print("DRY RUN: would write %s (%d bytes) and run %s bootstrap gui/%d %s"
                  % (target, len(want), LAUNCHCTL, uid, target))
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(want)
        got = run([LAUNCHCTL, "bootstrap", "gui/%d" % uid, str(target)], capture_output=True, text=True)
        if got.returncode != 0:
            target.unlink()
            print("REFUSED: launchctl bootstrap failed (%s); nothing is installed" % (got.stderr or "").strip()[:200])
            return 1
        print("INSTALLED: %s, every Friday at 09:00. Check with: python tools/schedule.py status" % target)
        return 0
    if not target.exists():
        print("NOTHING TO DO: %s is not installed" % target)
        return 0
    if args.dry_run:
        print("DRY RUN: would run %s bootout gui/%d/%s and remove %s" % (LAUNCHCTL, uid, LABEL, target))
        return 0
    run([LAUNCHCTL, "bootout", "gui/%d/%s" % (uid, LABEL)], capture_output=True, text=True)
    target.unlink()
    print("UNINSTALLED: %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Register the guard**

In `tools/check_all.py` (edit `c2-check-all`), replace:

```python
    ("check_accept_run", ["evals/check_accept_run.py"], "cold"),
```

with:

```python
    ("check_accept_run", ["evals/check_accept_run.py"], "cold"),
    ("check_schedule", ["evals/check_schedule.py"], "cold"),
```


- [ ] **Step 6: Run it, each mutation, and C1's two runner guards**

```bash
bash -n scripts/schedule/friday_run.sh && plutil -lint scripts/schedule/uk.fc08.friday-run.plist
.venv/bin/python evals/check_schedule.py
for m in log-token keep-api-key double-notify wrong-day token-in-plist any-auth no-branch-check no-back-pressure silent-refusal; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_schedule.py --mutate $m | tail -1
done
.venv/bin/python evals/check_friday_run.py | tail -1 && .venv/bin/python evals/check_accept_run.py | tail -1
.venv/bin/python tools/schedule.py status
ls ~/Library/LaunchAgents | grep -c fc08
```

Expected:
- `check_schedule`: `HELD (0 failures)`, 12 checks, and nine mutations detected;
- both C1 runner guards `HELD`;
- `status` prints `installed: no` and `loaded in launchd: no`;
- the last line prints `0`: nothing is installed.

- [ ] **Step 7: Commit**

```bash
git add feeds/preflight.py feeds/notify.py tools/friday_run.py scripts/schedule/friday_run.sh scripts/schedule/uk.fc08.friday-run.plist tools/schedule.py evals/check_schedule.py tools/check_all.py
git commit -m "Slice 2 C2: the scheduled run -- preflight, one notification, the Keychain launcher, the plist and schedule.py (nothing installs itself)"
```

---

### Task 2: CLAUDE.md, with the owner's runbook

- [ ] **Step 1: Add the C2 entry after C1's**

````markdown
## Slice 2: the schedule (sub-project C2, built <DATE>)

| File | What it holds |
|---|---|
| `scripts/schedule/friday_run.sh` | launchd's command: unsets ANTHROPIC_API_KEY, reads the token from the login Keychain (service uk.fc08.claude-oauth-token) into ONE command's environment, runs `tools/friday_run.py --scheduled`; notifies itself only on a crash (exit >= 2). Never traces, never prints the token |
| `scripts/schedule/uk.fc08.friday-run.plist` | the TEMPLATE: Fridays 09:00 local, RunAtLoad false, PATH only, log ~/Library/Logs/uk.fc08.friday-run.log |
| `tools/schedule.py` | install / uninstall are OWNER steps (they change launchd); status only reads |
| `feeds/preflight.py` | refuses off main, with an unaccepted run under 14 days (eval runs never count), or with auth other than loggedIn + authMethod "oauth_token" |
| `feeds/notify.py` | ONE notification per run: the report's first two lines, passed to osascript as arguments |

**Owner runbook.** Token: `claude setup-token`, then `security add-generic-password -a "$USER" -s uk.fc08.claude-oauth-token -w` (it prompts). Rotate: `security delete-generic-password -a "$USER" -s uk.fc08.claude-oauth-token`, then add again. Schedule: `.venv/bin/python tools/schedule.py install|uninstall|status`. A REFUSED Friday is harmless: read its report, fix the cause (accept or expire the pending run; switch to main; renew the token), and the next Friday runs.
````

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md && git commit -m "Slice 2 C2: CLAUDE.md -- the schedule and the owner's runbook"
```

---

### Task 3: STOP: C1 and C2 on `main`

The scheduled run refuses anything but `main`.
- The owner merges C1 and C2 and pushes, on their word.
- The pre-commit hook and CI (`tools/check_all.py --cold`) must pass.
- Report the merge commit.

---

### Task 4: OWNER STEP: the long-lived token, in the Keychain

Run by the owner in their own Terminal. Claude gives these lines and never runs them.

```bash
claude setup-token
# copy the token it prints, then store it; -w with no value makes security PROMPT for it (no shell history):
security add-generic-password -a "$USER" -s uk.fc08.claude-oauth-token -w
# confirm the METHOD the CLI reports with it -- this prints two words, never the token:
CLAUDE_CODE_OAUTH_TOKEN="$(security find-generic-password -a "$USER" -s uk.fc08.claude-oauth-token -w)" \
  claude auth status --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("loggedIn"), d.get("authMethod"))'
```

- [ ] The owner reports the last line.
  - **`True oauth_token`**: go on.
  - **Anything else**: STOP. `feeds/preflight.TOKEN_METHOD` changes to the observed value, with its guard, before Task 5.

  Never paste the token into chat.

---

### Task 5: OWNER STEP: two runs through the launcher, by hand

- [ ] **Step 1: The zero-cost rehearsal, on a branch.** The preflight refuses "not main" before any agent runs.

  ```bash
  git switch -c schedule-rehearsal
  bash scripts/schedule/friday_run.sh; echo "exit $?"
  git switch main && git branch -D schedule-rehearsal
  ```

  Expected:
  - macOS asks once whether `security` may read the item: choose **Always Allow**;
  - one notification, "FC08 Friday run: REFUSED";
  - `exit 1`;
  - a new `inbox/feeds-.../report.md` naming the branch.

  If no notification appears, allow notifications for Script Editor in System Settings, Notifications, and repeat. That run is `nothing_to_decide` and blocks nothing.
- [ ] **Step 2: Preconditions for the real run**
  - C1's dry-run run is decided (`.venv/bin/python tools/accept_run.py --pending` shows no `pending` run under 14 days old);
  - the checkout is on `main`;
  - `.venv/bin/python tools/check_all.py` passes.
- [ ] **Step 3: STOP: the owner's go. Cost: capped at US$5, expected US$2 to US$3.50.**
- [ ] **Step 4: The real run:** `bash scripts/schedule/friday_run.sh; echo "exit $?"`. Report exactly as C1 Task 9 Step 4, plus:
  - the notification's words;
  - the log's two lines in `~/Library/Logs/uk.fc08.friday-run.log`. When run by hand the log is your Terminal; launchd writes the file.
- [ ] **Step 5: STOP: the owner decides this run's items** (`tools/accept_run.py <run_id>`), or deliberately leaves it pending. Back-pressure then refuses the next Friday.

---

### Task 6: OWNER STEP: install the schedule

```bash
.venv/bin/python tools/schedule.py install --dry-run
.venv/bin/python tools/schedule.py install
.venv/bin/python tools/schedule.py status
```

Expected:
- the dry run writes nothing;
- `INSTALLED: ~/Library/LaunchAgents/uk.fc08.friday-run.plist, every Friday at 09:00`;
- `status` shows `installed`, `matches the template: True`, and `loaded in launchd: yes`.

Undo at any time: `.venv/bin/python tools/schedule.py uninstall`.

---

### Task 7: STOP: the first launchd Friday

**Cost: capped at US$5, expected US$2 to US$3.50.** Nothing to run: launchd starts it at 09:00 local time, if the Mac is on, awake or waking, and you are logged in.

- [ ] Afterwards, report:
  - the notification;
  - `tools/schedule.py status`: `last exit code`;
  - the log;
  - the report, as in C1 Task 9 Step 4.

  If there was no notification and no new inbox folder, launchd did not run it (asleep, powered off, logged out). Say so. Do not start it by hand in its place without the owner.

---

### Task 8: STOP: the first accepted run, through `review.py`

- [ ] **Step 1:** The owner runs `.venv/bin/python tools/accept_run.py <run_id>`:
  - the report is shown;
  - one decision per item: accept, drop or defer;
  - one confirmation.

  Claude renders the cards and recommends; the owner decides.
- [ ] **Step 2: Check and commit exactly what it wrote**

```bash
git status --short     # expect: data/feeds/seen.json, data/feeds/advisory_list.json, data/feeds/records/, data/proposals/, data/telemetry/, data/feeds/runs/<run_id>/
.venv/bin/python tools/check_all.py | tail -1
git add data/feeds data/proposals data/telemetry
git commit -m "Slice 2 C2: accept run <run_id> -- <n> accepted (<ADV ids>), <m> dropped, <k> deferred"
```

`check_walkthrough` prints its INFO line: live data has moved past the snapshot. **No republish is owed**, because the page is pinned to its snapshot.

- [ ] **Step 3: The proposals through the gate, as in slice 1:** `.venv/bin/python tools/review.py`. Claude shows the cards and recommends; the owner confirms each in chat. Only then is `--decisions` run. Commit the decision log and the rebuilt approvals.

---

### Task 9: what C leaves for D

Report, with the numbers:
- live `terminal_check`s so far: every session in every run's reconciliation table. Definition-of-done item 4 needs at least 3;
- the largest single run's cost against US$5, and each extraction's against US$1.00. Name any overshoot;
- the resolution rate per run: resolver calls and resolved per extraction, and record actors resolvable;
- items per source.

D (week 6) takes two more Fridays, the measurement note, the release audit and the tag.

---

## Definition of done for sub-project C2

- **Spec DoD 6 (Tasks 1 and 4 to 7).**
  - launchd runs weekly on Fridays, installed by the owner.
  - The auth preflight refuses anything but the long-lived token.
  - One notification per run.
  - Back-pressure refuses while a run under 14 days old is pending.
  - "No run exceeding US$5" is MEASURED per run in the report, not assumed; see C1's note on the overshoot.
- **Spec DoD 4 (Tasks 5 and 7, with C1 Task 9).** At least three live `terminal_check`s. Each run's orchestrator and extraction sessions each carry one.
- **Spec DoD 7 (Task 8).** At least one accepted live run whose proposals went through `tools/review.py`.
- **One new cold guard, `check_schedule`, 9 mutations.** No agent installs or reads anything persistent.
