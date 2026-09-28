"""
The write allowlist: the one place a tool that changes anything may be permitted.

PLAN.md week 5: "Add a can_use_tool callback that denies any write tool not on
the allowlist. Prove it by trying." Measured 2026-09-24: while all four Knowledge
Centre tools sat in allowed_tools, a callback would NEVER have been consulted --
allowed_tools auto-approves a whole tool before the callback runs (SDK
CanUseToolShadowedWarning). As first specified, this item would have passed while
checking nothing.

So allowed_tools pre-approves ONLY the four read-only tools, and every other
MCP tool -- propose_link, and anything a future server exposes -- reaches this
callback. The CLI's own StructuredOutput tool does not: it is auto-allowed and
never consulted here (measured in the ADV-2026-0013 run). The callback allows a
tool on WRITE_ALLOWLIST, and only when the run's identity is complete; it denies
everything else, including a read-only tool that somehow reached it (reads are
pre-approved, never decided here).

A DENIED call fires no Post hook (probed 2026-09-24), so the callback records
that call's terminal telemetry event itself. Every decision it makes is an event.

ALLOWED IS NOT ACCEPTED. The callback allows propose_link by NAME; the server
still decides the proposal. A server refusal ("Rejected: ...") reaches telemetry
as REFUSED. A schema-level refusal does not: propose_link's input model rejects
out-of-bounds arguments (pydantic bounds, e.g. missing citations) before the
tool body runs, the call raises, and PostToolUseFailure records it as FAILURE.
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
    "knowledge_centre_resolve_actor",
))
PROPOSE_TOOL = "mcp__%s__knowledge_centre_propose_link" % SERVER_KEY
WRITE_ALLOWLIST = frozenset({PROPOSE_TOOL})

# Slice 2 B: the feeds orchestrator (agents/orchestrate_feeds.py), declared HERE because this is the
# one place a tool that changes anything may be permitted. Triage-only mode: read_page is the only
# read, pre-approved; list, fetch and triage each write into the run's inbox and reach the callback.
# feeds_extract joins the allowlist in sub-project C, not before -- a triage-only run cannot extract.
FEEDS_SERVER_KEY = "feeds"
FEEDS_READ_ONLY_TOOLS = ("mcp__%s__feeds_read_page" % FEEDS_SERVER_KEY,)
FEEDS_WRITE_ALLOWLIST = frozenset("mcp__%s__%s" % (FEEDS_SERVER_KEY, t)
                                  for t in ("feeds_list_new", "feeds_fetch", "feeds_triage"))
# Slice 2 C: a LIVE (full-mode) run may also queue a relevant item for extraction. An eval run may not:
# its allowlist above is unchanged, and its server does not list the tool.
FEEDS_FULL_WRITE_ALLOWLIST = FEEDS_WRITE_ALLOWLIST | {"mcp__%s__feeds_extract" % FEEDS_SERVER_KEY}

# The exact start of the SDK's advisory when these four are pre-approved.
SHADOWING_MESSAGE = "can_use_tool will not be invoked for: %s." % ", ".join(READ_ONLY_TOOLS)


def _record_denial(run, tool: str, tool_use_id, reason: str) -> dict:
    # The TERMINAL event for a denied call: no Post hook will fire for it.
    return telemetry.emit(run, telemetry.PERMISSION_DENIED, telemetry.DENIED, "%s denied: %s" % (tool, reason),
                          tool=tool, tool_use_id=tool_use_id, latency_ms=None, outcome=reason)


def permission_callback(run, allowlist=None, may="propose links"):
    """The can_use_tool callback for one run.

    `allowlist` defaults to WRITE_ALLOWLIST, read at CALL time (a guard swaps the module global);
    the feeds orchestrator passes FEEDS_WRITE_ALLOWLIST. `may` completes the denial message.
    """

    async def can_use_tool(tool_name, tool_input, context):
        tool_use_id = getattr(context, "tool_use_id", None)
        allowed = WRITE_ALLOWLIST if allowlist is None else allowlist
        if tool_name in allowed and all(run.env().values()):
            telemetry.emit(run, telemetry.PERMISSION_ALLOWED, telemetry.ALLOWED,
                           "%s allowed: on the write allowlist" % tool_name,
                           tool=tool_name, tool_use_id=tool_use_id, latency_ms=None, outcome="on the write allowlist")
            return PermissionResultAllow()
        reason = ("%s is not on the write allowlist" % tool_name if tool_name not in allowed
                  else "the run identity is incomplete")
        _record_denial(run, tool_name, tool_use_id, reason)
        return PermissionResultDeny(message="Denied: %s. This agent may only %s; "
                                            "it writes nothing else." % (reason, may))

    return can_use_tool


@contextlib.contextmanager
def expected_shadowing(read_only=None):
    """Silence ONLY the SDK advisory naming exactly the pre-approved read-only tools.

    They are pre-approved on purpose, so the advisory is expected on every run.
    Any other shadowing -- a different tool pre-approved -- still warns. `read_only`
    defaults to the four Knowledge Centre reads; the feeds orchestrator passes its own.
    """
    message = SHADOWING_MESSAGE if read_only is None else \
        "can_use_tool will not be invoked for: %s." % ", ".join(read_only)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning,
                                message=re.escape(message))
        yield
