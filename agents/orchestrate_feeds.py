"""
The feeds orchestrator: one orchestrating agent whose tools carry the invariants (spec sections 1 and 4).

TWO MODES, chosen by the run, never by the agent:
  triage-only (EVAL)  a FeedsRun with a catalogue and a batch -- evals/run_feeds_triage.py (slice 2 B). Four
                      tools: feeds_list_new, feeds_fetch, feeds_read_page, feeds_triage. The server started
                      in eval mode does not even list feeds_extract.
  full (LIVE)         a FeedsRun with neither -- tools/friday_run.py (slice 2 C). The four, plus
                      feeds_extract, which QUEUES a relevant item: the extraction itself runs in code after
                      the session, within the run's budget (tools/friday_run.py). The agent never extracts.
Both: `tools=[]` emits `--tools ""`, `setting_sources=[]` ignores the operator's settings and hooks,
`strict_mcp_config` loads only the server passed here, feeds_read_page is the only pre-approved tool, and
every tool that writes reaches agents/permissions.py's callback, which allows the mode's allowlist only.
A LIVE server is started with FEEDS_CATALOGUE and FEEDS_CATALOGUE_BATCH set EMPTY, so a value exported in
the operator's shell cannot turn a Friday run into an eval run (B's carry-forward). Guarded by
evals/check_feeds_orchestrator.py.

Telemetry is slice 1's, plus one rule (slice 2 C): a tool call the CLI answered before any hook could run
-- measured in B's pilot transcript: three feeds_triage calls whose input "could not be parsed as JSON",
each answered by a tool_result with is_error and no hook event -- gets its ONE terminal event from the
transcript (telemetry.record_unhooked, `source: transcript`). terminal_check then reads what the hooks and
the transcript together recorded; a call with neither is still unterminated.

After the agent stops, IN CODE, feeds.triage.reconcile() lists every listed or expected item without a
verdict as unfinished. A session is `validated` only when it failed nothing and left nothing unfinished.
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
    AssistantMessage, ClaudeAgentOptions, ResultError, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage,
    query,
)

from agents import telemetry  # noqa: E402
from agents.permissions import (  # noqa: E402
    FEEDS_FULL_WRITE_ALLOWLIST, FEEDS_READ_ONLY_TOOLS, FEEDS_SERVER_KEY, FEEDS_WRITE_ALLOWLIST, expected_shadowing,
    permission_callback,
)
from feeds import extraction as feeds_extraction, inbox, triage as feeds_triage  # noqa: E402

SERVER_PATH = ROOT / "mcp_server" / "feeds_server.py"
TRIAGE_TOOLS = ("feeds_list_new", "feeds_fetch", "feeds_read_page", "feeds_triage")
FULL_TOOLS = TRIAGE_TOOLS + ("feeds_extract",)
AGENT_TOOLS = tuple("mcp__%s__%s" % (FEEDS_SERVER_KEY, t) for t in TRIAGE_TOOLS)
FULL_AGENT_TOOLS = tuple("mcp__%s__%s" % (FEEDS_SERVER_KEY, t) for t in FULL_TOOLS)
MODEL = "claude-sonnet-5"
# Per orchestrator session. PINNED by evals/check_feeds_orchestrator.py since slice 2 C (B's carry-forward:
# they were unguarded). B measured US$0.12-0.33 for a 10-item triage session; the cap leaves room for the
# extraction requests and for one turn's overshoot inside the run's ceiling below.
MAX_BUDGET_USD = 1.50
MAX_TURNS = 80
# THE FRIDAY RUN'S BUDGET (spec section 1, owner decisions 2026-09-26), in the one place a guard reads it.
RUN_CEILING_USD = 5.00        # the whole run: orchestrator session plus every extraction
EXTRACTION_BUDGET_USD = 1.00  # each extraction's own max_budget_usd
EXTRACTION_MAX_TURNS = 60     # slice 1's extractor default
# A session stopped by its own turn or budget cap COMPLETED: what it left is unfinished, and measured.
# Anything else that ends a run in error (auth, credit, the CLI) is a failure.
LIMIT_SUBTYPES = ("error_max_turns", "error_max_budget_usd")
# A live server must never inherit an eval catalogue from the operator's shell (B carry-forward 1).
LIVE_SERVER_BLANKS = {"FEEDS_CATALOGUE": "", "FEEDS_CATALOGUE_BATCH": ""}
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

# Appended, never interleaved: the triage instructions a live run follows are byte-for-byte the ones B's
# band measured (PROMPT_SHA256), and the extraction request is one step after them.
EXTRACTION_SECTION = """Before your final message, queue extraction. This run extracts at most 3 items; the extraction runs after you finish, in code, and you do not see it.
- Call feeds_extract once for each relevant item worth extracting, the most substantive first: a publication that sets out methods, red flags or a case in its own text before a notice that only points to one. At most 3; the tool refuses a fourth, and a relevant item left over returns next run.
- feeds_extract refuses an item not triaged relevant. It may fetch the publication's own PDF, linked from the page you read. If it replies "Failed:", name the item in your final message.
- In your final message, mark each queued item "queued"."""

FULL_PROMPT = TRIAGE_PROMPT + "\n\n" + EXTRACTION_SECTION
PROMPT_SHA256 = hashlib.sha256(TRIAGE_PROMPT.encode("utf-8")).hexdigest()
FULL_PROMPT_SHA256 = hashlib.sha256(FULL_PROMPT.encode("utf-8")).hexdigest()


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

    @property
    def live(self) -> bool:
        """A live run is FULL mode: triage and extraction requests. An eval run is triage-only."""
        return self.catalogue is None

    def env(self) -> dict:
        """The run's identity, as the permission callback checks it: every value set."""
        env = {"FEEDS_RUN_ID": self.run_id}
        if self.catalogue is not None:
            env.update(FEEDS_CATALOGUE=str(Path(self.catalogue).resolve()), FEEDS_CATALOGUE_BATCH=",".join(self.batch))
        return env

    def server_env(self) -> dict:
        """What the feeds server is started with: the identity, and in live mode the eval variables BLANKED."""
        return dict(self.env(), **LIVE_SERVER_BLANKS) if self.live else self.env()


def agent_options(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                  max_turns: int = MAX_TURNS) -> ClaudeAgentOptions:
    """The orchestrator's whole capability surface, in one place a guard can read."""
    return ClaudeAgentOptions(
        system_prompt=FULL_PROMPT if run.live else TRIAGE_PROMPT,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        mcp_servers={FEEDS_SERVER_KEY: {"type": "stdio", "command": sys.executable, "args": [str(SERVER_PATH)],
                                        "env": run.server_env()}},
        strict_mcp_config=True,
        tools=[],
        setting_sources=[],
        allowed_tools=list(FEEDS_READ_ONLY_TOOLS),
        can_use_tool=permission_callback(
            run, allowlist=FEEDS_FULL_WRITE_ALLOWLIST if run.live else FEEDS_WRITE_ALLOWLIST,
            may="list, fetch, read and triage feed items%s" % (", and queue relevant ones for extraction"
                                                               if run.live else "")),
        hooks=telemetry.tool_hooks(run),
    )


def _prompt(run: FeedsRun) -> str:
    if run.live:
        return "Run %s. Triage every new item from ofsi, fincen and ofac, then queue extraction." % run.run_id
    return "Run %s. Triage every new item from ofsi, fincen and ofac." % run.run_id


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(str(c.get("text", "")) for c in content or [] if isinstance(c, dict))


async def run_session(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                      max_turns: int = MAX_TURNS, inbox_root: Path = inbox.INBOX_ROOT) -> dict:
    """One orchestrator session, in the run's mode. Returns its summary; never raises for an agent-side
    failure, which is recorded (`failure`) so the caller decides."""
    telemetry.run_started(run, model, max_budget_usd, max_turns, FULL_AGENT_TOOLS if run.live else AGENT_TOOLS,
                          prompt_sha256=FULL_PROMPT_SHA256 if run.live else PROMPT_SHA256)
    tool_calls: Counter = Counter()
    calls: dict = {}    # tool_use_id -> tool name, every call the agent made, in order
    results: dict = {}  # tool_use_id -> (is_error, text), every tool_result the transcript carried
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
                            calls[block.id] = block.name
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            results[block.tool_use_id] = (bool(block.is_error), _result_text(block.content))
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
    from_transcript = telemetry.record_unhooked(run, calls, results)
    terminal_check = telemetry.reconcile(run, list(calls))
    items = feeds_triage.reconcile(run.run_id, run.batch, inbox_root)
    queued = [r["key"] for r in feeds_extraction.load_requests(run.run_id, inbox_root)] if run.live else []
    validated = failure is None and not items["unfinished"]
    telemetry.run_completed(run, telemetry.FAILURE if failure else telemetry.SUCCESS,
                            (failure or limit or "%s session ended" % ("orchestrator" if run.live else "triage"))[:300],
                            result=result, validated=validated, terminal_check=terminal_check, limit=limit,
                            unfinished=items["unfinished"], queued=queued,
                            terminated_from_transcript=[e["payload"]["tool_use_id"] for e in from_transcript])
    return {"run_id": run.run_id, "failure": failure, "limit": limit, "tool_calls": dict(tool_calls),
            "turns": getattr(result, "num_turns", None), "cost_usd": getattr(result, "total_cost_usd", None),
            "duration_ms": getattr(result, "duration_ms", None), "stop_reason": getattr(result, "stop_reason", None),
            "terminal_check": terminal_check, "listed": items["listed"], "triaged": items["triaged"],
            "unfinished": items["unfinished"], "never_listed": items["never_listed"], "queued": queued,
            "validated": validated}


# B's name: evals/run_feeds_triage.py and its guard call run_triage for an eval session.
run_triage = run_session
