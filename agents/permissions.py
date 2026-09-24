"""
The write allowlist: the one place a tool that changes anything may be permitted.

PLAN.md week 5: "Add a can_use_tool callback that denies any write tool not on
the allowlist. Prove it by trying." Measured 2026-09-24: while all four Knowledge
Centre tools sat in allowed_tools, a callback would NEVER have been consulted --
allowed_tools auto-approves a whole tool before the callback runs (SDK
CanUseToolShadowedWarning). As first specified, this item would have passed while
checking nothing.

So allowed_tools pre-approves ONLY the three read-only tools, and every other
tool -- propose_link, and anything a future server exposes -- reaches this
callback. It allows a tool on WRITE_ALLOWLIST, and only when the run's identity
is complete; it denies everything else, including a read-only tool that somehow
reached it (reads are pre-approved, never decided here).

A DENIED call fires no Post hook (probed 2026-09-24), so the callback records
that call's terminal telemetry event itself. Every decision it makes is an event.
"""

from __future__ import annotations

import contextlib
import re
import warnings

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from claude_agent_sdk.types import CanUseToolShadowedWarning

from agents import telemetry

SERVER_KEY = "knowledge_centre"
READ_ONLY_TOOLS = tuple("mcp__%s__%s" % (SERVER_KEY, t) for t in (
    "knowledge_centre_list_typologies",
    "knowledge_centre_get_typology",
    "knowledge_centre_search_typologies",
))
PROPOSE_TOOL = "mcp__%s__knowledge_centre_propose_link" % SERVER_KEY
WRITE_ALLOWLIST = frozenset({PROPOSE_TOOL})

# The exact start of the SDK's advisory when these three are pre-approved.
SHADOWING_MESSAGE = "can_use_tool will not be invoked for: %s." % ", ".join(READ_ONLY_TOOLS)


def _record_denial(run, tool: str, tool_use_id, reason: str) -> dict:
    # The TERMINAL event for a denied call: no Post hook will fire for it.
    return telemetry.emit(run, telemetry.PERMISSION_DENIED, telemetry.DENIED, "%s denied: %s" % (tool, reason),
                          tool=tool, tool_use_id=tool_use_id, latency_ms=None, outcome=reason)


def permission_callback(run):
    """The can_use_tool callback for one run."""

    async def can_use_tool(tool_name, tool_input, context):
        tool_use_id = getattr(context, "tool_use_id", None)
        if tool_name in WRITE_ALLOWLIST and all(run.env().values()):
            telemetry.emit(run, telemetry.PERMISSION_ALLOWED, telemetry.ALLOWED,
                           "%s allowed: on the write allowlist" % tool_name,
                           tool=tool_name, tool_use_id=tool_use_id)
            return PermissionResultAllow()
        reason = ("%s is not on the write allowlist" % tool_name if tool_name not in WRITE_ALLOWLIST
                  else "the run identity is incomplete")
        _record_denial(run, tool_name, tool_use_id, reason)
        return PermissionResultDeny(message="Denied: %s. This agent may only propose links; "
                                            "it writes nothing else." % reason)

    return can_use_tool


@contextlib.contextmanager
def expected_shadowing():
    """Silence ONLY the SDK advisory naming exactly the three read-only tools.

    They are pre-approved on purpose, so the advisory is expected on every run.
    Any other shadowing -- a different tool pre-approved -- still warns.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning,
                                message=re.escape(SHADOWING_MESSAGE))
        yield
