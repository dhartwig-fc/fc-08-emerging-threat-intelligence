"""
The feeds orchestrator, TRIAGE-ONLY mode (slice 2 sub-project B; spec sections 1 and 4).

One session is one orchestrating agent whose tools carry the invariants. In triage-only mode it has
four tools from mcp_server/feeds_server.py and nothing else:
  feeds_list_new, feeds_fetch   see and pin new items (sub-project A)
  feeds_read_page               read a pinned document's pages (B; the only read, pre-approved)
  feeds_triage                  one verdict per item, the quote found in the pinned document (B)
There is no extraction tool, no Knowledge Centre, and no built-in tool: `tools=[]` emits
`--tools ""`, `setting_sources=[]` ignores the operator's settings and hooks, `strict_mcp_config`
loads only the server passed here, and every tool that writes reaches agents/permissions.py's
callback, which allows FEEDS_WRITE_ALLOWLIST only. Guarded by evals/check_feeds_orchestrator.py.

Telemetry is slice 1's, unchanged: RUN_STARTED names the tools, the Post hooks and the callback leave
one terminal event per tool call, and RUN_COMPLETED carries telemetry.reconcile() as terminal_check.
After the agent stops, IN CODE, feeds.triage.reconcile() lists every listed or expected item without
a verdict as unfinished: whatever the agent skipped is reported, never read as success.

Sub-project B runs this only on the back-catalogue (evals/run_feeds_triage.py passes a catalogue and
a batch). The live Friday run, extraction, the budget ceiling across a run and the report are
sub-project C, which extends this module.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage, ClaudeAgentOptions, ResultError, ResultMessage, ToolUseBlock, query,
)

from agents import telemetry  # noqa: E402
from agents.permissions import (  # noqa: E402
    FEEDS_READ_ONLY_TOOLS, FEEDS_SERVER_KEY, FEEDS_WRITE_ALLOWLIST, expected_shadowing, permission_callback,
)
from feeds import inbox, triage as feeds_triage  # noqa: E402

SERVER_PATH = ROOT / "mcp_server" / "feeds_server.py"
TRIAGE_TOOLS = ("feeds_list_new", "feeds_fetch", "feeds_read_page", "feeds_triage")
AGENT_TOOLS = tuple("mcp__%s__%s" % (FEEDS_SERVER_KEY, t) for t in TRIAGE_TOOLS)
MODEL = "claude-sonnet-5"
# Per session. A session triages at most feeds.triage.MAX_PER_RUN (10) items.
MAX_BUDGET_USD = 1.50
MAX_TURNS = 80
# A session stopped by its own turn or budget cap COMPLETED: what it left is unfinished, and measured.
# Anything else that ends a run in error (auth, credit, the CLI) is a failure, and the batch is re-run.
LIMIT_SUBTYPES = ("error_max_turns", "error_max_budget_usd")

TRIAGE_PROMPT = """You are the triage stage of a financial-crime threat-intelligence desk's weekly feed run.
For each new publication you decide one thing: is it worth extracting? You do not extract.

Relevant: the publication describes methods, red flags or cases of financial crime that a typology could hold -- a money-laundering, fraud, sanctions-evasion, terrorist-financing, proliferation-financing or corruption technique; indicators an analyst could screen for; or an enforcement, penalty or settlement case that says what was done.
Not relevant: a bare designation or delisting list, a licence or general licence, a notice of a regulatory, procedural or website change, an event listing, or guidance that restates obligations without describing a method, red flag or case.
When in doubt, keep it: mark it relevant. A relevant publication missed here is lost to the desk; an irrelevant one kept costs a reviewer a minute.

How to work:
1. Call feeds_list_new once each for ofsi, fincen and ofac.
2. For every item listed, call feeds_fetch, then read the document with feeds_read_page. Start at page 1 and read on while the question is not settled.
3. Call feeds_triage exactly once per item: verdict relevant or not_relevant; a reason of at most 300 characters; one verbatim quote, copied from the pages feeds_read_page returned, that supports the verdict.
4. Triage every item. If an item cannot be fetched or read, do not guess a verdict: say so in your final message.
5. Finish with one line per item: key, verdict.

Tool replies that start "Rejected:" are refusals; read the reason and correct the call (a quote the tool cannot find must be copied again, exactly). You only ever pass keys the tools gave you, never a URL."""

PROMPT_SHA256 = hashlib.sha256(TRIAGE_PROMPT.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeedsRun:
    """Who a feeds session is, told to the MCP server by the runner, never by the agent."""

    run_id: str
    catalogue: Optional[Path] = None   # eval mode: evals/feeds/catalogue.json
    batch: Tuple[str, ...] = ()        # eval mode: the keys this session triages
    stage: str = "orchestrator"
    advisory_id: Optional[str] = None  # telemetry's payload field; a feeds session spans many items
    pdf_sha256: Optional[str] = None   # likewise: each document is pinned in the inbox, not here

    def __post_init__(self) -> None:
        if not inbox.RUN_ID.fullmatch(self.run_id):
            raise ValueError("run id %r is not feeds-YYYY-MM-DD-xxxxxx" % self.run_id)
        if (self.catalogue is None) != (not self.batch):
            raise ValueError("eval mode needs both a catalogue and a batch, and live mode neither")
        if len(self.batch) > feeds_triage.MAX_PER_RUN:
            raise ValueError("a session triages at most %d items; the batch has %d" % (feeds_triage.MAX_PER_RUN,
                                                                                        len(self.batch)))

    def env(self) -> dict:
        env = {"FEEDS_RUN_ID": self.run_id}
        if self.catalogue is not None:
            env.update(FEEDS_CATALOGUE=str(Path(self.catalogue).resolve()), FEEDS_CATALOGUE_BATCH=",".join(self.batch))
        return env


def agent_options(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                  max_turns: int = MAX_TURNS) -> ClaudeAgentOptions:
    """The triage agent's whole capability surface, in one place a guard can read."""
    return ClaudeAgentOptions(
        system_prompt=TRIAGE_PROMPT,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        mcp_servers={FEEDS_SERVER_KEY: {"type": "stdio", "command": sys.executable, "args": [str(SERVER_PATH)],
                                        "env": run.env()}},
        strict_mcp_config=True,
        tools=[],
        setting_sources=[],
        allowed_tools=list(FEEDS_READ_ONLY_TOOLS),
        can_use_tool=permission_callback(run, allowlist=FEEDS_WRITE_ALLOWLIST, may="list, fetch, read and "
                                         "triage feed items"),
        hooks=telemetry.tool_hooks(run),
    )


def _prompt(run: FeedsRun) -> str:
    return "Run %s. Triage every new item from ofsi, fincen and ofac." % run.run_id


async def run_triage(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                     max_turns: int = MAX_TURNS, inbox_root: Path = inbox.INBOX_ROOT) -> dict:
    """One triage-only session. Returns its summary; never raises for an agent-side failure, which
    is recorded (`failure`) so the caller decides. The summary is what a repeat record keeps."""
    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS)
    tool_calls: Counter = Counter()
    tool_use_ids: list = []
    result: Optional[ResultMessage] = None
    failure: Optional[str] = None
    limit: Optional[str] = None
    try:
        with expected_shadowing(FEEDS_READ_ONLY_TOOLS):
            async for message in query(prompt=_prompt(run), options=agent_options(run, model, max_budget_usd,
                                                                                  max_turns)):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls[block.name] += 1
                            tool_use_ids.append(block.id)
                elif isinstance(message, ResultMessage):
                    result = message
                    if message.is_error and message.subtype in LIMIT_SUBTYPES:
                        limit = message.subtype
                    elif message.is_error:
                        # Recorded, not raised inside the loop (see agents/extract_advisory.py).
                        failure = "agent run failed: %s" % (message.errors or message.result)
    except ResultError as exc:  # the CLI exits non-zero after an error result; the SDK raises this
        if exc.subtype in LIMIT_SUBTYPES:
            limit = exc.subtype
        else:
            failure = failure or "%s: %s" % (type(exc).__name__, exc)
    except Exception as exc:  # the SDK raises its own errors (auth, credit) from inside the loop
        failure = "%s: %s" % (type(exc).__name__, exc)
    terminal_check = telemetry.reconcile(run, tool_use_ids)
    items = feeds_triage.reconcile(run.run_id, run.batch, inbox_root)
    telemetry.run_completed(run, telemetry.FAILURE if failure else telemetry.SUCCESS,
                            (failure or limit or "triage session ended")[:300], result=result,
                            validated=failure is None, terminal_check=terminal_check, limit=limit,
                            unfinished=items["unfinished"])
    return {"run_id": run.run_id, "failure": failure, "limit": limit, "tool_calls": dict(tool_calls),
            "turns": getattr(result, "num_turns", None), "cost_usd": getattr(result, "total_cost_usd", None),
            "duration_ms": getattr(result, "duration_ms", None), "stop_reason": getattr(result, "stop_reason", None),
            "terminal_check": terminal_check, "listed": items["listed"], "triaged": items["triaged"],
            "unfinished": items["unfinished"], "never_listed": items["never_listed"]}
