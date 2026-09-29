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
