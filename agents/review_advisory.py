"""
NEXUS Track 2 · Threat Intelligence · Slice 1
Week 4: the ADDITIVE reviewer. A second pass that asks what the document
evidences that the extraction missed.

Usage:
    python agents/review_advisory.py data/advisories/<file>.pdf \
        --record data/records/ADV-2026-0016.json

WHY THIS EXISTS, AND WHY IT IS NOT THE REVIEWER PLAN.md SPECIFIED.

PLAN.md week 4 says the reviewer "must reject any fact whose quote is not found
verbatim in the page text". `evals/check_citations.py` already does exactly that,
mechanically, and all 624 citations in the golden set pass it. Building that
reviewer would duplicate a passing guard.

The measured defect is the other one: A QUOTE THAT EXISTS IS NOT A QUOTE THAT
SUPPORTS. Location is proven; evidence is not. And the measured shape of the gap
is recall, not precision -- 0.357 against precision 0.889.

Every governance mechanism built in weeks 1-3 SUBTRACTS. `tools=[]` removes
capability, `propose_link` refuses an unjustified twin, the search floor refuses
a weak match, `_refuse_unknown_ids` raises. Measured 2026-09-13: a refusal
suppresses but does not redirect -- told it could not justify a twin choice, the
agent dropped the claim rather than reconsidering which twin fits. Subtractive
mechanisms are why precision is the strong number. Nothing built so far ADDS.

So this reviewer adds, under a justification burden:
  - it is told what the extraction already claimed, and may not repeat it;
  - it is pointed at indicator sections, where the 2026-09-13 shape count found
    the misses concentrate (ADV-2026-0016 7 of 7, 0015 7 of 8, 0009 5 of 6,
    0004 12 of 17 -- against eight documents at exactly zero);
  - every addition must quote the doctrine's own words and say how the
    document's evidence matches THAT mechanism, not merely share its vocabulary;
  - anything it cannot justify that way, it must not propose.

GOVERNANCE IS INHERITED, NOT REDECLARED. The options come from
`extract_advisory.agent_options` with only the prompt and the output schema
replaced, so the reviewer has the same surface as the extractor: no built-in
tools, no inherited settings, the four Knowledge Centre tools and nothing else.
A second entry point that rebuilt its own options would be a second place for
the tool surface to drift, and the 2026-09-12 finding was that the surface had
already drifted once without anyone noticing.

IT DOES NOT WRITE THE RECORD. Additions go to their own file. The schema has no
provenance field and `extra="forbid"`, so marking a reviewer-added typology
needs a version bump -- and the contract does not change for something unproven.
The separate file is better provenance in the meantime: what the extractor said
and what the reviewer added stay distinguishable, which a merged record loses.

ACCEPTANCE, from PLAN.md and unchanged: keep this only if it beats the week-3
baseline. Amended once, on this week's evidence: "beats" means BANDS. Three
repeats either side, or it is an anecdote with a decimal point.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.advisory import Citation, Confidence, TypologyFamily  # noqa: E402
from agents.extract_advisory import agent_options, library_ids, pdf_to_pages  # noqa: E402

from claude_agent_sdk import AssistantMessage, ClaudeSDKError, ResultMessage, ToolUseBlock, query  # noqa: E402


class ProposedAddition(BaseModel):
    """One typology the extraction missed, with the justification that earns it."""

    model_config = ConfigDict(extra="forbid")

    family: TypologyFamily
    typology_id: Optional[str] = Field(None, pattern=r"^[A-Z]{2,6}\d{3}[A-Z]?$")
    label: str = Field(..., min_length=3, max_length=120)
    emergent: bool = False
    confidence: Confidence
    citations: List[Citation] = Field(..., min_length=1)
    doctrine_justification: str = Field(
        ...,
        min_length=40,
        max_length=1200,
        description="Quote the doctrine's own words for the mechanism, then say how this "
                    "document's evidence matches THAT mechanism. Shared vocabulary is not a match.",
    )
    where_found: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="Which part of the document, e.g. 'red flag 7, page 4' or 'case study, page 12'.",
    )


class ReviewAdditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advisory_id: str = Field(..., pattern=r"^ADV-\d{4}-\d{4}$")
    additions: List[ProposedAddition] = Field(default_factory=list)
    reviewer_notes: str = Field("", max_length=4000)


REVIEWER_PROMPT = """You are a second-pass reviewer on a financial-crime threat-intelligence desk.

An extraction agent has already read this advisory and produced a record. Your job is NOT to check its work. Your job is to find what it MISSED, and to earn every addition.

What you are looking for:
- Techniques the document evidences that the existing record does not claim.
- Indicator lists are content, not context. A red alert's numbered red flags, a FATF risk-indicator paper's bullets, a FinCEN red-flag section: each indicator, or each group of related indicators, may carry a typology, and a single bullet is sufficient evidence.
- Read the whole document, but spend most of your attention on indicator and red-flag sections. That is where misses concentrate.

Rules for an addition:
- It must NOT already be in the record. You are given the list; do not repeat it.
- Resolve it through the knowledge_centre_* tools. A typology_id may only be one a tool returned. If search reports no match, it is emergent: typology_id null, emergent true, and put the emergent name in label.
- Confirm with knowledge_centre_get_typology before proposing, and read what the doctrine actually says.
- A QUOTE THAT EXISTS IS NOT A QUOTE THAT SUPPORTS. Your citation must describe the mechanism the typology names. Sharing vocabulary is not enough: a document about illegal logging is not evidence of a laundering typology just because both mention proceeds.
- In doctrine_justification, quote the doctrine's own words for the mechanism, then say how this document's evidence matches THAT mechanism.
- Confidence carries the weight, not omission. One bullet supports low or medium; high needs the document to develop the technique.
- Citation page is the n in the "=== PAGE n ===" marker, never the number printed on the page.
- Call knowledge_centre_propose_link once per addition before you finish.

If you cannot justify an addition against doctrine, DO NOT PROPOSE IT. An unjustified addition costs more than a miss: precision is this pipeline's strongest property and you are the first mechanism built that can spend it.

Returning zero additions is a valid and useful answer when the record is complete.
"""


def build_prompt(record: dict, pages: list) -> str:
    claimed = ["%s %s" % (t.get("typology_id") or "EMERGENT", t.get("label", ""))
               for t in record.get("typologies", [])]
    return (
        "Advisory ID: %s\n"
        "Pages: %d\n\n"
        "ALREADY CLAIMED by the extraction (%d) -- do not repeat any of these:\n%s\n\n"
        "Document text follows. Find what is missing and earn each addition.\n\n%s"
        % (record["advisory_id"], len(pages), len(claimed),
           "\n".join("  - " + c for c in claimed) or "  (nothing)",
           "\n\n".join(pages))
    )


async def review(pdf: Path, record: dict, model: str, max_budget_usd: float, max_turns: int) -> tuple:
    pages = pdf_to_pages(pdf)

    # Inherit the governed surface; replace only the brief and the output shape.
    options = dataclasses.replace(
        agent_options(model, max_budget_usd, max_turns),
        system_prompt=REVIEWER_PROMPT,
        output_format={"type": "json_schema", "schema": ReviewAdditions.model_json_schema()},
    )

    structured = None
    failure: str | None = None
    tool_calls: Counter = Counter()
    result: ResultMessage | None = None
    async for message in query(prompt=build_prompt(record, pages), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls[block.name] += 1
        elif isinstance(message, ResultMessage):
            result = message
            if message.is_error:
                # Recorded, not raised inside the loop: raising here abandons the
                # SDK's generator and its teardown masks the real error.
                failure = "Reviewer run failed: %s" % (message.errors or message.result)
            else:
                structured = message.structured_output

    if failure:
        raise RuntimeError(failure)
    if structured is None:
        raise RuntimeError("Reviewer returned no structured output (stop_reason=%s)"
                           % (result.stop_reason if result else None))

    additions = ReviewAdditions.model_validate(structured)

    # The same governance the extractor has: an id the library does not hold
    # cannot enter, whatever the prompt said.
    known = library_ids()
    unknown = sorted({a.typology_id for a in additions.additions
                      if a.typology_id and a.typology_id not in known})
    if unknown:
        raise ValueError("reviewer proposed ids the library does not contain: %s" % ", ".join(unknown))

    # And it may not re-propose what the extraction already claimed. The prompt
    # asks for this; the prompt asking is advice, so it is also enforced here.
    already = {t.get("typology_id") for t in record.get("typologies", []) if t.get("typology_id")}
    repeats = sorted({a.typology_id for a in additions.additions if a.typology_id in already})
    if repeats:
        raise ValueError("reviewer re-proposed typologies already in the record: %s" % ", ".join(repeats))

    telemetry = {
        "tool_calls": dict(tool_calls),
        "turns": result.num_turns if result else None,
        "cost_usd": result.total_cost_usd if result else None,
        "duration_s": round(result.duration_ms / 1000, 1) if result else None,
        "additions": len(additions.additions),
    }
    return additions, telemetry


def main() -> int:
    ap = argparse.ArgumentParser(description="Second-pass reviewer: what did the extraction miss?")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--record", type=Path, required=True, help="The extraction to review")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-budget-usd", type=float, default=5.0)
    ap.add_argument("--max-turns", type=int, default=60)
    args = ap.parse_args()

    if not args.pdf.exists():
        print("PDF not found: %s" % args.pdf, file=sys.stderr)
        return 2
    if not args.record.exists():
        print("Record not found: %s" % args.record, file=sys.stderr)
        return 2

    record = json.loads(args.record.read_text(encoding="utf-8"))

    try:
        additions, telemetry = asyncio.run(
            review(args.pdf, record, args.model, args.max_budget_usd, args.max_turns))
    except (RuntimeError, ValueError, ClaudeSDKError) as exc:
        detail = str(exc)
        print("review FAILED for %s: %s" % (record.get("advisory_id"), detail), file=sys.stderr)
        low = detail.lower()
        if "credit balance" in low or "quota" in low or "rate_limit" in low:
            print("  the account needs credit or has hit a limit; the run never reached the model.",
                  file=sys.stderr)
        return 1

    out = args.out or (ROOT / "data" / "reviewed" / ("%s.additions.json" % record["advisory_id"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(additions.model_dump_json(indent=2), encoding="utf-8")

    gov = [a.typology_id for a in additions.additions if a.typology_id]
    emg = [a.label for a in additions.additions if not a.typology_id]
    print("Wrote %s" % out)
    print("Additions: %d governed (%s) | %d emergent (%s)"
          % (len(gov), ", ".join(gov) or "-", len(emg), "; ".join(e[:40] for e in emg) or "-"))
    print("Telemetry: %s" % json.dumps(telemetry, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
