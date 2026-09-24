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
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.advisory import AdvisoryRecord  # noqa: E402
from agents.run_identity import RunIdentity  # noqa: E402
from schemas.citation_match import file_sha256  # noqa: E402

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, query  # noqa: E402
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
    "knowledge_centre_propose_link",
)

SYSTEM_PROMPT = """You are an intel extraction agent for a financial-crime threat-intelligence desk.
You read regulator and industry advisories and reduce them to a governed record.

Rules:
- Extract only what the document states. Never add typologies, actors or indicators from your own knowledge.
- Every typology, actor and indicator must carry at least one citation with page number and verbatim quote.
- Citation page is the n in the "=== PAGE n ===" marker above the text, never the number printed on the page. Put the printed number in printed_folio.
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
- A search result marked TWIN carries the same technique as another code in a different family. The declaration names the twin and the preferred family where one exists. knowledge_centre_propose_link REFUSES the link unless your rationale names that twin and says why this family fits the advisory. Do not judge by whether the two labels look alike: SAN006 and TBML010 are the same technique with the words reordered.
- When a result says its doctrine is authored as another id, prefer that id.
- Before you finish, call knowledge_centre_propose_link once per typology in your record: with typology_id for a library match, with emergent_label for an emergent one. Pass the same citations as the record entry (page and verbatim quote); a quote that is not on the page it names is refused, and the refusal says where it is. Cite page numbers in the rationale.
"""


def pdf_to_pages(path: Path) -> list:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append("=== PAGE %d ===\n%s" % (i, text.strip()))
    return pages


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

    Week 5 adds the other half. `allowed_tools` pre-approves only the three
    read-only Knowledge Centre tools; `can_use_tool` (agents/permissions.py)
    decides every other tool against WRITE_ALLOWLIST; and the Post hooks
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


async def extract(path: Path, advisory_id: str, model: str, max_budget_usd: float, max_turns: int) -> tuple:
    pages = pdf_to_pages(path)

    run = RunIdentity.new("extractor", advisory_id, path)
    options = agent_options(model, max_budget_usd, max_turns, run)

    telemetry.run_started(run, model, max_budget_usd, max_turns)
    structured = None
    failure: str | None = None
    tool_calls: Counter = Counter()
    # Every call's id, so RUN_COMPLETED can record whether each one got exactly
    # one terminal event (telemetry.reconcile) rather than assume it.
    tool_use_ids: list = []
    result: ResultMessage | None = None
    try:
        with expected_shadowing():
            async for message in query(prompt=build_prompt(advisory_id, path, pages), options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls[block.name] += 1
                            tool_use_ids.append(block.id)
                elif isinstance(message, ResultMessage):
                    result = message
                    if message.is_error:
                        # Recorded, NOT raised here: raising inside `async for`
                        # abandons the SDK's generator and its teardown masks the
                        # real error. Let the loop end, then raise.
                        failure = "Agent run failed: %s" % (message.errors or message.result)
                    else:
                        structured = message.structured_output

        if failure:
            raise RuntimeError(failure)
        if structured is None:
            raise RuntimeError("Agent returned no structured output (stop_reason=%s)"
                               % (result.stop_reason if result else None))
        record = AdvisoryRecord.model_validate(structured)
        _refuse_unknown_ids(record)
    except Exception as exc:
        telemetry.run_completed(run, telemetry.FAILURE, str(exc)[:300], result=result, validated=False,
                                terminal_check=telemetry.reconcile(run, tool_use_ids))
        raise
    terminal_check = telemetry.reconcile(run, tool_use_ids)
    telemetry.run_completed(run, telemetry.SUCCESS, "record validated", result=result, validated=True,
                            terminal_check=terminal_check)

    summary = {
        "tool_calls": dict(tool_calls),
        "unterminated": len(terminal_check["unterminated"]),
        "duplicated": len(terminal_check["duplicated"]),
        "turns": result.num_turns if result else None,
        "cost_usd": result.total_cost_usd if result else None,
        "duration_s": round(result.duration_ms / 1000, 1) if result else None,
        "permission_denials": len(result.permission_denials or []) if result else None,
        "run_id": run.run_id,
        "queue_path": str(run.queue_path.relative_to(ROOT)),
        "telemetry_path": str(telemetry.telemetry_path(run).relative_to(ROOT)),
        "proposals_written": _count_lines(run.queue_path),
    }
    return record, summary


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
        record, telemetry = asyncio.run(
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
    print("Telemetry: %s" % json.dumps(telemetry, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
