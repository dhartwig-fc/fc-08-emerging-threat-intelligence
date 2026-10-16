"""
NEXUS Track 2 · Threat Intelligence · Slice 1
Extraction agent: one advisory PDF in, one validated AdvisoryRecord out.

Usage:
    python agents/extract_advisory.py path/to/advisory.pdf --advisory-id ADV-2026-0001

Week 1 pasted the typology library into the prompt. Week 2 (2026-09-10) removed
it: the agent reaches the Knowledge Centre only through the MCP server in
mcp_server/, so a typology_id can only come from a tool result. That is
enforced three times, on purpose:
  1. the propose_link tool refuses an id the library does not contain;
  2. the prompt tells the agent to use the tools;
  3. `_refuse_unknown_ids` below raises if the returned record names an id the
     library does not hold, whatever the prompt said.
Only 1 and 3 are governance. 2 is advice.

2026-09-12: the advice changed, and this is the one prompt edit today with a
measured reason. "Prefer fewer, well-cited items over many weakly supported
ones" was suppressing assertions the golden set expects -- the agent cited that
rule back in its own extraction_notes as why it did not reproduce all fourteen
of ADV-2026-0016's numbered red flags. Replaced with the document-shape rule,
which was an owner decision taken on 2026-09-11 for LABELLERS (see
evals/golden/README.md) and never propagated here, so the label and the agent
were applying different rules to the same document and the scorer called the
difference "recall".

Evidence: SAN006 on ADV-2026-0016 was RETRIEVED by search, CONFIRMED with
get_typology, then dropped -- 0 of 7 runs under the old prompt, 3 of 3 under the
new one, with indicators rising 9.9 -> 13.3 of the document's 14 and zero new
false positives. Probe: evals/probe_prompt_variant.py.

2026-10-02 (slice 2 C2): the extractor checks its own quotes, in code. Every live Friday extraction to that
date was refused at acceptance (bd1185: ADV-2026-0021/0022; 10ce44: 0023..0025, 1/21, 1/19 and 26/46 quotes
off their page). OFAC SDN entries embed each name's original script -- "HAMEDANI, Mehnoosh Poursaraf
(Arabic: <script>), China; DOB 07 Mar 1984" -- and the extractor dropped the bracketed script or
mistranscribed a CJK character, so the quote was not verbatim; one quote was verbatim but cited p4 for text
on p5. Slice 1 learned that a prompt rule fails under tool load, so there are two code rules and one line of
advice:
  1. the tool knowledge_centre_check_quote(page, quote) asks the SAME rule accept_run refuses on
     (schemas/citation_match.PageIndex.locate) before the agent finishes;
  2. after the record is produced, extract() runs evals/check_citations.unplaced_citations -- the function
     tools/friday_run.py warns on and tools/accept_run.py refuses on, never a copy -- and if any citation is
     off its page the SAME session gets ONE repair turn naming each one (MAX_REPAIR_TURNS), the result is
     re-checked once, and whatever still fails is reported exactly as before (the runner's warning, then
     accept_run's refusal). The repair turn is in the same session, so the CLI's --max-budget-usd, which is
     the session's running total, bounds the first turn and the repair together: the US$1.00 extraction cap
     is not raised. The summary and RUN_COMPLETED record whether a repair turn ran and how many citations
     failed before and after it.
  3. one prompt line, advice only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.advisory import AdvisoryRecord  # noqa: E402
from agents.run_identity import RunIdentity  # noqa: E402
from schemas.citation_match import PageIndex, document_texts, file_sha256, quote_reply  # noqa: E402

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage,
)
from claude_agent_sdk import ClaudeSDKError  # noqa: E402

# One definition, shared with the permission callback's tool names.
from agents.permissions import READ_ONLY_TOOLS, SERVER_KEY, expected_shadowing, permission_callback  # noqa: E402
from agents import telemetry  # noqa: E402

SERVER_PATH = ROOT / "mcp_server" / "knowledge_centre_server.py"
LIBRARY_PATH = ROOT / "data" / "typologies.json"
KC_TOOLS = (
    "knowledge_centre_list_typologies",
    "knowledge_centre_get_typology",
    "knowledge_centre_search_typologies",
    "knowledge_centre_resolve_actor",
    "knowledge_centre_check_quote",
    "knowledge_centre_propose_link",
)

# Slice 2 C2 (owner ruling 2026-10-02): at most ONE repair turn per extraction, never a loop; the cost of that
# turn counts inside the extraction's own budget because it runs in the same session.
MAX_REPAIR_TURNS = 1
# The CLI counts max_turns PER user turn and options cannot change mid-session, so the repair turn would get a
# fresh allowance of its own. It is held to what is LEFT of the extraction's total instead (see
# _check_and_repair): no repair turn unless at least this many API rounds remain, and the turn is interrupted
# in code if it uses more than remain. Enough for a couple of check_quote calls and the corrected record.
REPAIR_MIN_TURNS = 4
# The repair turn names each failing citation; past this many it names the first ones and says how many more.
MAX_REPAIR_LINES = 60

# The qualified names the agent can call, recorded in RUN_STARTED (agents/telemetry.run_started).
AGENT_TOOLS = tuple("mcp__%s__%s" % (SERVER_KEY, name) for name in KC_TOOLS)

SYSTEM_PROMPT = """You are an intel extraction agent for a financial-crime threat-intelligence desk.
You read regulator and industry advisories and reduce them to a governed record.

Rules:
- Extract only what the document states. Never add typologies, actors or indicators from your own knowledge.
- Every typology, actor and indicator must carry at least one citation with page number and verbatim quote.
- Citation page is the n in the "=== PAGE n ===" marker above the text, never the number printed on the page. Put the printed number in printed_folio.
- Quote non-Latin script exactly as written, or choose a span that contains none (for example DOB, place of birth, address). Cite the page the text is actually on. Check each quote with knowledge_centre_check_quote before you finish.
- published_on_precision says how much of the date the document states. "December 2020" is 2020-12-01 with precision month.
- A class of actor the document describes (organised crime groups, professional money launderers) is actor_type category, not organisation.
- Whether an indicator is a typology depends on the shape of the document. In a narrative report, a red flag mentioned once in passing is not a typology: label what the report is about. In an indicator-list document (a red alert, a FATF risk-indicator paper, a FinCEN red-flag section) the indicators ARE the content -- each indicator, or each group of related indicators, may carry a typology, and a single bullet is sufficient evidence.
- Confidence carries the weight, not omission. One bullet supports a typology at low or medium; high needs the document to develop the technique.
- Jurisdictions are ISO 3166-1 alpha-2 codes.
- Put caveats for the human reviewer in extraction_notes.

The Knowledge Centre:
- You do not know the typology library. Look it up with the knowledge_centre_* tools.
- For each technique the document describes, call knowledge_centre_search_typologies with a phrase from the document. Confirm a candidate with knowledge_centre_get_typology before using it.
- A typology_id may only be one a tool returned. If the search reports no match, the typology is emergent: typology_id null, emergent true.
- A search result listed under "Open typology proposals" is a technique NEXUS is still defining, not a typology. If the advisory describes that technique, record it as emergent with the proposal's working name as its label, and call knowledge_centre_propose_link with typology_proposal set to the proposal id instead of emergent_label.
- A search result marked TWIN carries the same technique as another code in a different family. The declaration names the twin and the preferred family where one exists. knowledge_centre_propose_link REFUSES the link unless your rationale names that twin and says why this family fits the advisory. Do not judge by whether the two labels look alike: SAN006 and TBML010 are the same technique with the words reordered.
- When a result says its doctrine is authored as another id, prefer that id.
- For each named actor you record (a person, an organisation, a network, a vessel or a wallet; never a category), call knowledge_centre_resolve_actor with the name as the document gives it and the actor_type you record. Only a reply starting "Resolved:" is an identity: note it in extraction_notes as "name -> actor_id". Any other reply ("Unresolved:", "Ambiguous:", "Not resolvable:") is not an identity: an actor_id it lists is for a human to decide, so if you mention it, label it a suggestion or an ambiguity, and never treat it as the actor's identity.
- Before you finish, call knowledge_centre_propose_link once per typology in your record: with typology_id for a library match, with emergent_label for an emergent one. Pass the same citations as the record entry (page and verbatim quote); a quote that is not on the page it names is refused, and the refusal says where it is. Cite page numbers in the rationale.
"""

# The prompt this run was actually sent, recorded in RUN_STARTED (agents/telemetry.run_started) so a run
# can be tied to the prompt it ran under. Owner decision, 2026-09-29, before Task 9's first live dry run.
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def document_pages(path: Path) -> list:
    """The prompt's pages, "=== PAGE n ===" each: a PDF through pypdf exactly as before, a pinned HTML
    page (a live feed item, slice 2 C) through schemas/html_pages -- the pages propose_link and the
    review gate re-find every quote on, through the same schemas.citation_match.document_texts."""
    return ["=== PAGE %d ===\n%s" % (i, (text or "").strip()) for i, text in enumerate(document_texts(path), start=1)]


# The name agents/review_advisory.py imports; a PDF's pages are unchanged by the rename.
pdf_to_pages = document_pages


def sha256_of(path: Path) -> str:
    return file_sha256(path)


def build_prompt(advisory_id: str, path: Path, pages: list) -> str:
    return (
        "Advisory ID to use: %s\n"
        "Document SHA-256: %s\n"
        "Page count: %d\n\n"
        "Document text follows. Resolve typologies through the Knowledge Centre tools, then produce the AdvisoryRecord.\n\n%s"
        % (advisory_id, sha256_of(path), len(pages), "\n\n".join(pages))
    )


def library_ids() -> set:
    with open(LIBRARY_PATH, "r", encoding="utf-8") as fh:
        return {t["typology_id"] for t in json.load(fh)["typologies"]}


def _refuse_unknown_ids(record: AdvisoryRecord) -> None:
    """Governance in code: a record may not name an id the library does not hold."""
    known = library_ids()
    unknown = sorted({t.typology_id for t in record.typologies if t.typology_id and t.typology_id not in known})
    if unknown:
        raise ValueError("record names typology ids the library does not contain: %s" % ", ".join(unknown))


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def mcp_servers(run: RunIdentity) -> dict:
    return {
        SERVER_KEY: {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(SERVER_PATH)],
            # The run's identity reaches the server here and only here. The agent
            # cannot set or change it (week 5, agents/run_identity.py).
            "env": {"NEXUS_TYPOLOGY_PATH": str(LIBRARY_PATH), **run.env()},
        }
    }


def agent_options(model: str, max_budget_usd: float, max_turns: int, run: RunIdentity) -> ClaudeAgentOptions:
    """The agent's whole capability surface, in one place a guard can read.

    THE EXTRACTION AGENT HAS NO BUILT-IN TOOLS. `tools=[]` emits `--tools ""`
    (see the SDK's subprocess_cli.py), which removes the base set -- Bash, Write,
    Read, Edit, WebFetch, everything -- and leaves only the MCP tools supplied
    through `mcp_servers`.

    Why this is not what `allowed_tools` does, measured 2026-09-12. With
    `allowed_tools` naming only the four Knowledge Centre tools, the agent still
    HELD Bash and Write and used them: on ADV-2026-0002 it ran
    `echo -n "<sha256>" | wc -c` successfully and attempted to write
    /tmp/adv_record.json. `allowed_tools` governs whether a call PROMPTS, not
    whether the tool exists. The Write was refused by a hook on the operator's
    machine, which is not this pipeline's governance and would not exist in CI or
    on anyone else's clone.

    `setting_sources=[]` is the other half: the run must not inherit settings,
    hooks or permissions from the machine it happens to be on, or the contract
    differs per developer. It also stops the run depending on the hook that
    masked the defect above.

    An extraction agent that can write files and run shell commands is outside
    its own contract whether or not it chooses to use them. Guarded by
    `evals/check_tool_surface.py`, which proves both directions.

    Week 5 adds the other half. `allowed_tools` pre-approves only the
    read-only Knowledge Centre tools (the four lookups and, since 2026-10-02, check_quote); `can_use_tool` (agents/permissions.py)
    decides every other MCP tool against WRITE_ALLOWLIST -- the CLI's own
    StructuredOutput tool is auto-allowed and never reaches it (measured in the
    ADV-2026-0013 run); and the Post hooks
    (agents/telemetry.py) record one terminal event per call. Pre-approving a
    tool shadows the callback entirely -- which is why propose_link is NOT in
    allowed_tools.
    """
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        mcp_servers=mcp_servers(run),
        # The CLI would also load the server registered with `claude mcp add` for
        # this folder, giving the model two copies with different names and four
        # permission denials per run (measured 2026-09-10). Only the one passed in.
        strict_mcp_config=True,
        # Capability, not permission. See the docstring.
        tools=[],
        setting_sources=[],
        # Week 5: pre-approve ONLY the read-only tools, so every other tool --
        # propose_link and anything a server adds -- is decided by the callback.
        allowed_tools=list(READ_ONLY_TOOLS),
        can_use_tool=permission_callback(run),
        hooks=telemetry.tool_hooks(run),
        output_format={"type": "json_schema", "schema": AdvisoryRecord.model_json_schema()},
    )


async def extract(path: Path, advisory_id: str, model: str, max_budget_usd: float, max_turns: int,
                  run: RunIdentity = None) -> tuple:
    """`run` is passed by a feeds run (tools/friday_run.py), whose identity names the feeds run so the
    queue goes to its inbox; slice 1's command line leaves it None and gets a fresh identity as before.

    A passed run is checked against this call's OWN arguments before anything else -- no file read, no
    session -- because a runner passing a mismatched identity would show the agent one document while the
    Knowledge Centre server checks quotes against another: every proposal would then be refused or
    quarantined, a loud but confusing failure far from its real cause."""
    if run is not None:
        resolved = Path(path).resolve()
        if run.advisory_id != advisory_id or run.pdf_path != resolved:
            raise ValueError("the run identity %s (advisory %s, document %s) does not match this call's own "
                             "arguments (advisory %s, document %s)"
                             % (run.run_id, run.advisory_id, run.pdf_path, advisory_id, resolved))
    pages = document_pages(path)

    run = run or RunIdentity.new("extractor", advisory_id, path)
    options = agent_options(model, max_budget_usd, max_turns, run)

    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256=PROMPT_SHA256)
    structured = None
    failure: str | None = None
    seen = _Seen()
    result: ResultMessage | None = None
    quote_repair = {"checked": None, "failing_before": None, "failing_after": None, "repair_turns": 0,
                    "skipped": None, "error": None, "cost_after_first_usd": None,
                    "repair_allowance_turns": None, "interrupted": False}
    try:
        with expected_shadowing():
            # ONE session for the whole extraction: the first turn produces the record, and -- only when the
            # shared citation rule finds a quote off its page -- the same session gets one repair turn.
            # ClaudeSDKClient and not query(): query() closes the CLI's stdin after the first result, which
            # cannot carry a second turn while hooks and can_use_tool are installed (SDK, Query.wait_for_
            # result_and_end_input). The first turn is the same prompt and the same options as before.
            async with ClaudeSDKClient(options) as client:
                await client.query(build_prompt(advisory_id, path, pages))
                result = await _receive_turn(client, seen)
                if result is not None:
                    if result.is_error:
                        # Recorded, NOT raised here: raising inside a receive loop abandons the SDK's
                        # generator and its teardown masks the real error. Let the turn end, then raise.
                        failure = "Agent run failed: %s" % (result.errors or result.result)
                    else:
                        structured = result.structured_output
                if failure:
                    raise RuntimeError(failure)
                if structured is None:
                    raise RuntimeError("Agent returned no structured output (stop_reason=%s)"
                                       % (result.stop_reason if result else None))
                record = AdvisoryRecord.model_validate(structured)
                _refuse_unknown_ids(record)
                record, quote_repair, result = await _check_and_repair(
                    client, record, path, advisory_id, max_budget_usd, max_turns, result, seen, quote_repair)
    except Exception as exc:
        _terminate_calls(run, seen)
        telemetry.run_completed(run, telemetry.FAILURE, str(exc)[:300], result=result, validated=False,
                                terminal_check=telemetry.reconcile(run, seen.tool_use_ids), model_rounds=seen.rounds)
        raise
    _terminate_calls(run, seen)
    terminal_check = telemetry.reconcile(run, seen.tool_use_ids)
    telemetry.run_completed(run, telemetry.SUCCESS, "record validated", result=result, validated=True,
                            terminal_check=terminal_check, quote_repair=quote_repair, model_rounds=seen.rounds)

    summary = {
        "tool_calls": dict(seen.tool_calls),
        "unterminated": len(terminal_check["unterminated"]),
        "duplicated": len(terminal_check["duplicated"]),
        "turns": result.num_turns if result else None,
        "model_rounds": seen.rounds,
        "cost_usd": result.total_cost_usd if result else None,
        "duration_s": round(result.duration_ms / 1000, 1) if result else None,
        "permission_denials": len(result.permission_denials or []) if result else None,
        "run_id": run.run_id,
        "queue_path": _shown(run.queue_path),
        "telemetry_path": _shown(telemetry.telemetry_path(run)),
        "proposals_written": _count_lines(run.queue_path),
        "quote_repair": quote_repair,
    }
    return record, summary


def _shown(path: Path) -> str:
    """A path as the summary prints it: relative to the repository when it is inside it (always, for a real run),
    else as it is -- a guard that points the inbox and telemetry at a temporary folder must not crash here."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


class _Seen:
    """What a session's messages showed, across every turn of it: tool-call counts, every call's id (so
    RUN_COMPLETED can record whether each got exactly one terminal event, telemetry.reconcile, rather than
    assume it), and -- Slice 2 C -- the names and results a call the CLI answered with no hook needs its
    terminal event from."""

    def __init__(self) -> None:
        self.tool_calls: Counter = Counter()
        self.tool_use_ids: list = []
        self.names: dict = {}
        self.results: dict = {}
        self.interrupted = False
        # Distinct assistant messages over every turn: the API rounds, counted HERE because num_turns is the CLI's
        # own figure. Measured 2026-10-16: ADV-2026-0028 reported num_turns 63 against max_turns 60 on a success
        # with no repair turn, and nothing recorded could say whether the CLI counts turns differently or let the
        # cap pass. RUN_COMPLETED now carries both, with the result's subtype.
        self.rounds = 0


def _terminate_calls(run, seen: "_Seen") -> None:
    """Every call the session started ends with one terminal event: the CLI-answered ones, and -- if the runner
    interrupted a turn -- the ones it cut off (S-1)."""
    telemetry.record_unhooked(run, seen.names, seen.results)
    if seen.interrupted:
        telemetry.record_interrupted(run, seen.names, seen.results)


async def _receive_turn(client, seen: "_Seen", limit: int = None) -> "ResultMessage | None":
    """Read one turn of the session to its ResultMessage (returned; None if the session ended without one).
    Never raises on an error RESULT -- the caller decides what an error result means for its turn.

    `limit`: the most API rounds (distinct assistant messages) this turn may use. The first round past it
    interrupts the session once (seen.interrupted), and the turn is read on to the result the CLI then sends."""
    result = None
    rounds: set = set()
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            rounds.add(message.message_id or id(message))
            if limit is not None and len(rounds) > limit and not seen.interrupted:
                seen.interrupted = True
                await client.interrupt()
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    seen.tool_calls[block.name] += 1
                    seen.tool_use_ids.append(block.id)
                    seen.names[block.id] = block.name
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    text = block.content if isinstance(block.content, str) else " ".join(
                        str(c.get("text", "")) for c in block.content or [] if isinstance(c, dict))
                    seen.results[block.tool_use_id] = (bool(block.is_error), text)
        elif isinstance(message, ResultMessage):
            result = message
    seen.rounds += len(rounds)
    return result


def _unplaced(record: AdvisoryRecord, path: Path, advisory_id: str, index: PageIndex) -> tuple:
    """(citations checked, [failing citation with its quote]) by THE rule -- evals/check_citations.
    unplaced_citations, the function tools/friday_run.py warns on and tools/accept_run.py refuses on. Never a
    copy of it: imported at call time, so a guard can put a spy on it and see this call go through."""
    if str(ROOT / "evals") not in sys.path:
        sys.path.insert(0, str(ROOT / "evals"))
    from check_citations import unplaced_citations, with_quotes
    raw = json.loads(record.model_dump_json())  # the record exactly as it is written to the inbox
    checked, bad = unplaced_citations(advisory_id, raw, path, index=index)
    return checked, with_quotes(raw, bad)


def repair_prompt(index: PageIndex, failing: list, checked: int) -> str:
    """The one repair turn's message: each failing citation (section, item, cited page, and the shared rule's own
    answer -- wrong page, or where the quote stops agreeing with the page), then what to do about it."""
    lines = []
    for n, d in enumerate(failing[:MAX_REPAIR_LINES], start=1):
        quote = d.get("quote")
        shown = json.dumps(quote[:100] + ("..." if len(quote) > 100 else ""), ensure_ascii=False) if quote else "(not found)"
        lines.append("%d. %s %s, cites page %d, quote %s -- %s" % (
            n, d["section"], json.dumps(d["item"], ensure_ascii=False), d["page"], shown,
            quote_reply(index, d["page"], quote) if quote else "its quote could not be read back from the record"))
    if len(failing) > MAX_REPAIR_LINES:
        lines.append("... and %d more, found by the same rule: check every quote you cite." % (len(failing) - MAX_REPAIR_LINES))
    return (
        "Quote check, run by code on your record: %d of %d citations are not on the page they name.\n\n%s\n\n"
        "Correct each of these: quote the page text exactly as written -- non-Latin script included, or choose a span "
        "that contains none -- and cite the page the text is actually on. Check each corrected quote with "
        "knowledge_centre_check_quote before you finish. Leave every citation that is not listed, and every other "
        "field, exactly as it is, and do not call knowledge_centre_propose_link again: your proposals are already "
        "queued. Reply with the complete corrected record."
        % (len(failing), checked, "\n".join(lines)))


def _session_total(first: "ResultMessage | None", turn: "ResultMessage") -> "ResultMessage":
    """The result a two-turn session reports. Measured from the bundled CLI (2.1.259): total_cost_usd is the
    session's running total, but num_turns, permission_denials and duration are PER TURN -- so the closing
    figures are the first turn's plus the repair's (denials combined), and the cost is the later total."""
    if first is None:
        return turn
    return dataclasses.replace(
        turn,
        num_turns=(first.num_turns or 0) + (turn.num_turns or 0),
        duration_ms=(first.duration_ms or 0) + (turn.duration_ms or 0),
        duration_api_ms=(first.duration_api_ms or 0) + (turn.duration_api_ms or 0),
        permission_denials=list(first.permission_denials or []) + list(turn.permission_denials or []),
        total_cost_usd=turn.total_cost_usd if turn.total_cost_usd is not None else first.total_cost_usd)


async def _check_and_repair(client, record: AdvisoryRecord, path: Path, advisory_id: str, max_budget_usd: float,
                            max_turns: int, result: "ResultMessage | None", seen: "_Seen", note: dict) -> tuple:
    """(record, note, result): the record's citations against the pinned document by the shared rule, and --
    when any is off its page -- up to MAX_REPAIR_TURNS repair turn(s) in the SAME session, re-checking the
    corrected record after each. Anything still failing is left for the runner's warning and accept_run, exactly
    as before. The repair spends inside this session's budget: the CLI's --max-budget-usd is the session's
    running total (bundled CLI 2.1.259: it ends a turn with error_max_budget_usd once the session total reaches
    the budget, so one API call can overshoot, as in any single turn), and a first turn that has already spent
    it gets no repair turn at all (recorded in note["skipped"]). The TURN allowance is held in code the same
    way: the repair gets what is left of max_turns after the first turn (note["repair_allowance_turns"]), is
    skipped under REPAIR_MIN_TURNS, and is interrupted if it uses more (note["interrupted"]). The closing
    result is the whole session's (_session_total). A repair turn that errors, or returns a record that does
    not validate, keeps the original record (recorded in note["error"]): no failure of the repair turn or of
    the first check fails an extraction that had a valid record. (The re-check of a corrected, schema-valid
    record is not wrapped: every field it reads is required, so it cannot realistically raise.)"""
    note["cost_after_first_usd"] = result.total_cost_usd if result is not None else None
    try:
        index = PageIndex.from_document(path)
        note["checked"], bad = _unplaced(record, path, advisory_id, index)
    except Exception as exc:  # noqa: BLE001 -- the runner's own check reports a document that cannot be checked
        note["error"] = ("the quote check could not run: %s: %s" % (type(exc).__name__, exc))[:300]
        return record, note, result
    note["failing_before"] = note["failing_after"] = len(bad)
    for _ in range(MAX_REPAIR_TURNS):
        if not bad:
            break
        spent = result.total_cost_usd if result is not None else None
        if spent is not None and spent >= max_budget_usd:
            note["skipped"] = "the first turn spent US$%.2f of the US$%.2f budget" % (spent, max_budget_usd)
            break
        allowance = max_turns - ((result.num_turns or 0) if result is not None else 0)
        if allowance < REPAIR_MIN_TURNS:
            note["skipped"] = "the first turn used %s of the %s turn allowance" % (
                (result.num_turns if result is not None else 0), max_turns)
            break
        note["repair_turns"] += 1
        note["repair_allowance_turns"] = allowance
        try:
            await client.query(repair_prompt(index, bad, note["checked"]))
            turn = await _receive_turn(client, seen, limit=allowance)
        except Exception as exc:  # noqa: BLE001 -- the SDK raising mid-repair must not lose a valid record
            note["interrupted"] = seen.interrupted  # S-3: the interrupt may have been issued before it raised
            note["error"] = ("the repair turn raised %s: %s" % (type(exc).__name__, exc))[:300]
            break
        note["interrupted"] = seen.interrupted
        if turn is not None:
            result = _session_total(result, turn)  # cost: the running total; turns, denials, duration: summed
        if turn is None or turn.is_error or turn.structured_output is None:
            note["error"] = ("the repair turn returned no record (%s%s)" % (
                (turn.errors or turn.result or turn.subtype) if turn is not None else "no result",
                "; interrupted at its %d-turn allowance" % allowance if seen.interrupted else ""))[:300]
            break
        try:
            corrected = AdvisoryRecord.model_validate(turn.structured_output)
            _refuse_unknown_ids(corrected)
        except Exception as exc:  # noqa: BLE001 -- the original record stands
            note["error"] = ("the repair turn's record was refused: %s: %s" % (type(exc).__name__, exc))[:300]
            break
        record = corrected
        note["checked"], bad = _unplaced(record, path, advisory_id, index)
        note["failing_after"] = len(bad)
    return record, note, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a governed AdvisoryRecord from one PDF")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--advisory-id", required=True, help="Governed ID, for example ADV-2026-0001")
    parser.add_argument("--model", default="claude-sonnet-5", help="Model alias or ID")
    parser.add_argument("--out", type=Path, default=None, help="Where to write the JSON record")
    parser.add_argument("--max-budget-usd", type=float, default=5.0, help="Hard cost cap for the run")
    parser.add_argument("--max-turns", type=int, default=60, help="Turn cap; tool calls consume turns")
    args = parser.parse_args()

    if not args.pdf.exists():
        print("PDF not found: %s" % args.pdf, file=sys.stderr)
        return 2
    if not SERVER_PATH.exists():
        print("MCP server not found: %s" % SERVER_PATH, file=sys.stderr)
        return 2

    # FAIL ON THE EXIT CODE, NOT ON A GREP.
    #
    # This used to let the RuntimeError escape, so a failed run printed a Python
    # traceback. A batch loop filtering stdout for "Agent run failed" saw nothing
    # match -- the message is mid-traceback on stderr, not at the start of a line
    # -- and reported a bare FAILED that read like a soft error. Measured
    # 2026-09-11: five runs died on "Credit balance is too low", the loop exited 0,
    # and the scores were then compared as though the runs had happened. A null
    # result nearly became a finding.
    #
    # So: one line on stderr saying what happened, and a non-zero exit any caller
    # can test. Week 4's batch runner and any CI step get this for free.
    try:
        record, summary = asyncio.run(
            extract(args.pdf, args.advisory_id, args.model, args.max_budget_usd, args.max_turns))
    except (RuntimeError, ClaudeSDKError) as exc:
        # ClaudeSDKError too: the SDK raises ResultError from inside its own
        # receive loop before the ResultMessage reaches us, so catching only
        # RuntimeError let a credit-balance failure escape as a traceback.
        detail = str(exc)
        print("extraction FAILED for %s: %s" % (args.advisory_id, detail), file=sys.stderr)
        # These are recoverable and nothing to do with the advisory or the agent,
        # so say which, or a caller is left diagnosing the wrong thing.
        low = detail.lower()
        if "credit balance" in low or "quota" in low or "rate_limit" in low:
            print("  the account needs credit or has hit a limit; the run never reached the model.",
                  file=sys.stderr)
        elif "authenticate" in low or "oauth" in low or "api key" in low:
            print("  the claude CLI is not authenticated. Check `claude auth status`.", file=sys.stderr)
        return 1

    out = args.out or (ROOT / "data" / "records" / ("%s.json" % args.advisory_id))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    print("Wrote %s" % out)
    print("Typologies: %d (emergent: %d) | Actors: %d | Indicators: %d | Desks: %s" % (
        len(record.typologies),
        len(record.emergent_candidates),
        len(record.actors),
        len(record.indicators),
        ", ".join(d.value for d in record.suggested_desks),
    ))
    print("Telemetry: %s" % json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
