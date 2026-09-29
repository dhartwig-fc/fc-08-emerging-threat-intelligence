"""
The scheduled run's preflight (slice 2 C2, spec section 5): four refusals, each written up as a run report
with a notification by tools/friday_run.py --scheduled, and none of them spends anything. All that apply are
reported together, in the fixed order below.

  on main       the checkout is on branch `main` (a detached HEAD or a feature branch refuses): a Friday run
                reads the committed ledger, prompts and guards, and must read the governed ones;
  the clone     the checkout carries the schedule-clone marker, <git-dir>/fc08-schedule-clone (owner decision,
                2026-09-29; re-review R-1): the schedule runs only from its own clone, ~/fc-08-schedule, never
                from the development checkout. The marker lives INSIDE the git directory, so git can never
                track, commit, push or clone it: a fresh clone of anything lacks it until the owner creates it
                (CLAUDE.md, "The schedule clone", the create-once block). tools/schedule.py install refuses
                without it too;
  back-pressure a pending run under 14 days old is still in the inbox (feeds/runs.py; eval runs never count);
  auth          `<cli_path()> auth status --json` -- the SDK's own CLI, see WHICH claude below -- says loggedIn
                with authMethod "oauth_token", the long-lived subscription token (`claude setup-token`).
                "claude.ai" is the interactive login, which expires (CLAUDE.md, Auth); "api_key" means
                ANTHROPIC_API_KEY, which bills pay-as-you-go.
The expected method string was READ from the PATH CLI's code (2.1.269), not observed with a token, and not
read from the SDK's bundled CLI at all. C2 Task 4 has the owner confirm it by hand, against cli_path().
The token itself is never read here: only the CLI's own summary of it.

WHICH claude (final-review fix, I-2). `auth_status` runs the binary the Agent SDK would start for the Friday
sessions -- `cli_path()`, which asks the SDK's own resolver -- NOT whatever `claude` is first on PATH. The two
differ on this Mac: the SDK starts its BUNDLED CLI (in .venv, moving only when the SDK is upgraded), while PATH
finds the self-updating native install. The preflight exists to check the CLI that spends, so it checks that
one. Which binary the agents run is deliberately NOT changed: B's and C1's measurements were made on the
bundled CLI.

Fix round 1 (I-3): both subprocess calls fail closed rather than crashing or passing. `on_main` catches a
missing `git` binary. `auth_status` reads the exit code before trusting the output (a non-zero exit refuses
even if the stdout claims "oauth_token"), and refuses -- naming the actual problem -- on non-JSON output, on
`null` or `[]` (valid JSON that is not an object), and on a missing `claude` binary.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import List, Optional

from feeds import inbox, runs

TOKEN_METHOD = "oauth_token"
CLONE_MARKER = "fc08-schedule-clone"
CLONE_STEP = ('create it only in the schedule clone, with CLAUDE.md\'s "The schedule clone" create-once block: '
              'touch "$(git rev-parse --git-dir)/%s"' % CLONE_MARKER)


def on_main(repo: Path, run=subprocess.run) -> Optional[str]:
    try:
        got = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), capture_output=True, text=True)
    except OSError as exc:
        return "the preflight could not run git: %s" % exc
    branch = (got.stdout or "").strip()
    if got.returncode != 0 or branch != "main":
        return "the checkout is on %r, not main" % (branch or got.stderr.strip()[:80])
    return None


def clone_marker(repo: Path, run=subprocess.run) -> Path:
    """<git-dir>/fc08-schedule-clone for the checkout at `repo`. RAISES when git cannot say where its git
    directory is; schedule_clone turns that into a refusal."""
    got = run(["git", "rev-parse", "--git-dir"], cwd=str(repo), capture_output=True, text=True)
    git_dir = (got.stdout or "").strip()
    if got.returncode != 0 or not git_dir:
        raise RuntimeError("`git rev-parse --git-dir` exited %d: %s" % (got.returncode, (got.stderr or "").strip()[:80]))
    return Path(repo) / git_dir / CLONE_MARKER  # --git-dir may answer relative to repo; an absolute one wins the join


def schedule_clone(repo: Path, run=subprocess.run) -> Optional[str]:
    """None when this checkout is the marked schedule clone; otherwise why not (never raises)."""
    try:
        marker = clone_marker(repo, run)
    except (OSError, RuntimeError) as exc:
        return "the preflight could not find this checkout's git directory to look for the schedule-clone marker: %s" % exc
    if not marker.is_file():
        return ("this checkout is not the schedule clone: %s is missing -- the schedule runs only from its own clone "
                "(~/fc-08-schedule), never from the development checkout; %s" % (marker, CLONE_STEP))
    return None


def back_pressure(root: Path = inbox.INBOX_ROOT, today: date = None) -> Optional[str]:
    waiting = runs.blocking(root, today)
    if waiting:
        return ("an unaccepted run is still in the inbox: %s -- accept it (tools/accept_run.py) or, from 14 days, "
                "expire it (tools/accept_run.py --expire)" % ", ".join("%s (%d days)" % (r, a) for r, a in waiting))
    return None


def cli_path() -> str:
    """The claude binary the Agent SDK would start for a Friday session: the one that spends.

    Asks the SDK directly rather than mirroring it. claude_agent_sdk 0.2.152,
    claude_agent_sdk/_internal/transport/subprocess_cli.py: `connect()` (lines 792-793) sets
    `self._cli_path = self._find_cli()` whenever ClaudeAgentOptions.cli_path is None -- as it is in both
    agents/orchestrate_feeds.agent_options and agents/extract_advisory.agent_options -- and `_find_cli()`
    (line 247) returns the BUNDLED CLI first (`_find_bundled_cli`, line 333: <package>/_bundled/claude), then
    `shutil.which("claude")`, then a fixed list of home locations. `_find_cli` ignores every other option, so a
    default ClaudeAgentOptions resolves exactly as the agents' own do (evals/check_schedule.py checks that
    against both agents' real options). PRIVATE SDK API, as evals/check_tool_surface.py already uses: if a
    future SDK renames it, this RAISES -- and auth_status turns that into a refusal -- rather than guessing.
    """
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
    transport = SubprocessCLITransport(prompt="", options=ClaudeAgentOptions())
    if not hasattr(transport, "_find_cli"):
        raise RuntimeError("the Agent SDK no longer exposes SubprocessCLITransport._find_cli; the preflight "
                           "cannot tell which claude binary the sessions will start")
    return transport._find_cli()


def auth_status(run=subprocess.run) -> dict:
    """The CLI's own JSON summary; {"error": ...} when it cannot be had. Only the fields named are kept.

    The exit code is checked BEFORE the output is trusted: a non-zero exit refuses even when stdout happens
    to contain a well-formed {"loggedIn": true, "authMethod": "oauth_token"} (fix round 1, I-3). Output that
    parses to something other than a JSON object -- not JSON at all, or valid JSON that is `null` or a list --
    also refuses, naming the actual problem, instead of crashing with AttributeError on the missing `.get`.
    """
    try:
        cli = cli_path()
    except Exception as exc:  # noqa: BLE001 -- CLINotFoundError, or the SDK's resolver gone: refuse, never guess
        return {"error": "could not resolve the claude CLI the Agent SDK would start: %s: %s"
                % (type(exc).__name__, exc)}
    try:
        got = run([cli, "auth", "status", "--json"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}
    if got.returncode != 0:
        return {"error": "`%s auth status --json` exited %d: %s"
                % (cli, got.returncode, (got.stderr or got.stdout or "").strip()[:200])}
    try:
        data = json.loads(got.stdout or "")
    except ValueError as exc:
        return {"error": "`%s auth status --json` printed no valid JSON: %s" % (cli, exc)}
    if not isinstance(data, dict):
        return {"error": "`%s auth status --json` printed a JSON %s, not an object" % (cli, type(data).__name__)}
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
    found = [on_main(repo, run), schedule_clone(repo, run), back_pressure(root, today),
             auth(status if status is not None else auth_status(run))]
    return [r for r in found if r]
