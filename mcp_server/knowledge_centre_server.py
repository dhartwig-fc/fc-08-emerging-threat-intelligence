"""
NEXUS Track 2 · Threat Intelligence · Slice 1
Week 2 skeleton: the Knowledge Centre exposed as an MCP server.
Works on MCP Python SDK 2.x (MCPServer) and 1.x (FastMCP).

Governance lives here, not in the prompt. The extraction agent can only touch
the typology library through these tools. Proposals are written to a staging
file for human review; nothing writes to the library itself.

Run locally (stdio transport, the default for Claude Desktop and Claude Code):
    python mcp_server/knowledge_centre_server.py

Register in Claude Code:
    claude mcp add knowledge-centre -- python "$PWD/mcp_server/knowledge_centre_server.py"
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

try:
    # MCP Python SDK 2.x: FastMCP was renamed to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
TYPOLOGY_PATH = Path(os.environ.get("NEXUS_TYPOLOGY_PATH", ROOT / "data" / "typologies.json"))
PROPOSALS_PATH = Path(os.environ.get("NEXUS_PROPOSALS_PATH", ROOT / "data" / "proposals.jsonl"))

mcp = FastMCP("knowledge_centre_mcp")


# ---------------------------------------------------------------------------
# Library access (read-only)
# ---------------------------------------------------------------------------

def _load_library() -> dict:
    with open(TYPOLOGY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _typologies() -> List[dict]:
    return _load_library().get("typologies", [])


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class ListTypologiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: Optional[str] = Field(
        None,
        description="Filter by family such as tbml, sanctions, correspondent_banking. Omit for all.",
    )
    limit: int = Field(50, ge=1, le=200, description="Maximum rows to return")


class GetTypologyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    typology_id: str = Field(..., pattern=r"^[A-Z]{2,6}\d{3}[A-Z]?$", description="Knowledge Centre ID such as TBML001")


class SearchTypologiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=3, max_length=300, description="Free-text phrase from the advisory")
    limit: int = Field(5, ge=1, le=20)


class ProposeLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advisory_id: str = Field(..., pattern=r"^ADV-\d{4}-\d{4}$")
    typology_id: Optional[str] = Field(
        None,
        pattern=r"^[A-Z]{2,6}\d{3}[A-Z]?$",
        description="Existing typology to link. Omit when proposing an emergent typology.",
    )
    emergent_label: Optional[str] = Field(None, min_length=3, max_length=120)
    rationale: str = Field(..., min_length=20, max_length=1000, description="Why this link holds, citing page numbers")
    confidence: str = Field(..., pattern=r"^(high|medium|low)$")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="knowledge_centre_list_typologies",
    annotations={"title": "List typologies", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def list_typologies(params: ListTypologiesInput) -> str:
    """
    List typologies in the governed Knowledge Centre library.

    Returns id, family and label for each typology, optionally filtered by family.
    Use this first to learn the valid typology_id values before proposing a link.
    Never invent a typology_id that this tool did not return.
    """
    rows = _typologies()
    if params.family:
        rows = [r for r in rows if r.get("family") == params.family.lower()]
    rows = rows[: params.limit]
    if not rows:
        return "No typologies found for family %r. Call without a filter to see all families." % params.family
    lines = ["%s | %s | %s" % (r["typology_id"], r["family"], r["label"]) for r in rows]
    return "typology_id | family | label\n" + "\n".join(lines)


@mcp.tool(
    name="knowledge_centre_get_typology",
    annotations={"title": "Get typology", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def get_typology(params: GetTypologyInput) -> str:
    """
    Return the full doctrine record for one typology by ID, including its summary
    and known indicators. Use this to confirm a match before proposing a link.
    """
    for r in _typologies():
        if r["typology_id"] == params.typology_id:
            return json.dumps(r, indent=2)
    return "Typology %s not found. Use knowledge_centre_list_typologies to see valid IDs." % params.typology_id


# ---------------------------------------------------------------------------
# Search: stemmed tokens, inverse document frequency, label bonus, a floor.
#
# Replaced 2026-09-10 (week 2). The first version was raw token overlap with no
# stemming and no floor; on the governed 57-typology library it ranked BA001
# Structuring above TBML004 for "phantom shipments" ("shipments" did not match
# "shipping") and returned a 0.17 hit for Black Market Peso Exchange instead of
# "no match". A weak match reported as a match makes the agent link an emergent
# typology to the wrong doctrine. evals/search_probes.py holds the measured
# cases; the floor below was chosen from them: emergent phrases top out at 0.12,
# the weakest true match scored 0.33 before the stemming fix. Still stdlib,
# still deterministic; week 3 may swap in embeddings behind the same contract.
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    "the and of is in at all no not for with are this that from by or to be as on its an a it their "
    "there where who which when than then into onto through same other another one two used using use "
    "via such may can will has have had been being also any each".split()
)
_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ers", "er", "ed", "es", "ly", "s")
_STEM_LEN = 6
SEARCH_SCORE_FLOOR = 0.25


def _stem(word: str) -> str:
    if len(word) <= 3:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if suffix == "ies":
                word += "y"
            break
    if word.endswith("e") and len(word) > 4:
        word = word[:-1]
    if len(word) > 3 and word[-1] == word[-2]:
        word = word[:-1]
    return word[:_STEM_LEN]


def _stems(text: str) -> List[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS and len(w) > 2]


def _search_index() -> tuple:
    """(docs, idf) over the current library. 57 records; rebuilt per call on purpose."""
    docs = []
    for r in _typologies():
        label = set(_stems(r["label"]))
        body = set(_stems(" ".join([r.get("summary", ""), r.get("intelligence_question", "")] + r.get("indicators", []))))
        docs.append((r, label, body | label))
    df: dict = {}
    for _, _, terms in docs:
        for t in terms:
            df[t] = df.get(t, 0) + 1
    n = len(docs)

    def idf(term: str) -> float:
        return math.log(1 + n / df.get(term, 0.5))

    return docs, idf


def rank_typologies(query: str) -> List[tuple]:
    """Every typology scored 0..1 against the query, best first. Pure; used by the tool and by evals.

    TWO SCORES, and the better one wins. Measured 2026-09-11 over the 413 governed
    citations in the golden set, which is real FATF/OFAC/NCA sentences rather than
    phrases written here:

        query length    1-10 words   11-20   21-35   36+
        mean score of
        the CORRECT id       0.425   0.250   0.193   0.180

    The first score divides by the whole query's weight, so a long sentence dilutes
    itself: most of its words are not doctrine terms, and the denominator grows
    while the numerator does not. Advisories write long sentences. The twelve
    hand-written probes in evals/search_probes.py are short phrases, which is
    exactly why they scored 12 of 12 and hid this.

    The second score asks the question the other way round: how much of the
    TYPOLOGY'S LABEL does this sentence contain? A label is two or three
    distinctive words ("Phantom Shipping", "Under Invoicing"), so a sentence
    naming the technique scores high however long it runs. That is length
    invariant, which is what lets a single floor mean the same thing for a
    six-word phrase and a forty-word paragraph.

    Lowering the floor instead was tried and rejected: it lifts top-5 recall from
    0.351 to 0.625 but weakens the "no match, treat as emergent" answer the floor
    exists to give, which evals/search_probes.py guards.
    """
    docs, idf = _search_index()
    q = list(dict.fromkeys(_stems(query)))
    q_set = set(q)
    denom = sum(idf(t) for t in q) or 1.0
    ranked = []
    for r, label, terms in docs:
        num = sum(idf(t) * (2.0 if t in label else 1.0) for t in q if t in terms)
        by_query = num / denom
        # TWO label terms, or the whole of a one-term label. A single shared word
        # is not a match: measured, "Black Market Peso Exchange" hit CM002 Market
        # Manipulation at 0.39 on the word "market" alone, and "surrogate shoppers
        # purchasing luxury goods" hit Dual Use Goods at 0.34 on "goods". Both are
        # emergent techniques the floor exists to send to emergent, and both
        # regressed the moment this second score was added without this guard.
        hits = [t for t in label if t in q_set]
        by_label = 0.0
        if len(hits) >= 2 or (len(label) == 1 and hits):
            label_denom = sum(idf(t) for t in label)
            by_label = (sum(idf(t) for t in hits) / label_denom) if label_denom else 0.0
        ranked.append((min(max(by_query, by_label), 1.0), r))
    ranked.sort(key=lambda x: (-x[0], x[1]["typology_id"]))
    return ranked


@mcp.tool(
    name="knowledge_centre_search_typologies",
    annotations={"title": "Search typologies", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def search_typologies(params: SearchTypologiesInput) -> str:
    """
    Search typology labels, summaries, intelligence questions and indicators
    for a phrase from the advisory. Returns ranked matches with a 0..1 score.

    A result is only returned when it clears the score floor. "No match" means
    the library has nothing close: treat the phrase as a possible emergent
    typology and propose it with emergent_label. Never link a typology this
    tool did not return. Two typologies can share a label (SAN002 and PAT008
    are both Shadow Fleet); pick by family.
    """
    ranked = rank_typologies(params.query)
    above = [(s, r) for s, r in ranked if s >= SEARCH_SCORE_FLOOR]
    if not above:
        best = ranked[0] if ranked else None
        hint = " Closest below the floor was %s at %.2f, which is not a match." % (best[1]["typology_id"], best[0]) if best and best[0] > 0 else ""
        return ("No match above the floor (%.2f). Treat as a possible emergent typology and propose it with emergent_label.%s"
                % (SEARCH_SCORE_FLOOR, hint))
    out = ["score | typology_id | family | label"]
    for score, r in above[: params.limit]:
        line = "%.2f | %s | %s | %s" % (score, r["typology_id"], r["family"], r["label"])
        # A typology whose doctrine is borrowed from another code ties with it on
        # every query. Say so, from the export's own provenance field, so the
        # agent can prefer the code the doctrine was actually written for.
        if r.get("doctrine_authored_as"):
            line += " (doctrine authored as %s)" % r["doctrine_authored_as"]
        out.append(line)
    return "\n".join(out)


@mcp.tool(
    name="knowledge_centre_propose_link",
    annotations={"title": "Propose advisory link", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def propose_link(params: ProposeLinkInput) -> str:
    """
    Propose that an advisory be pinned to a typology, or propose an emergent typology.

    This never writes to the library. It appends to a review queue that a human
    approves in week 5. Exactly one of typology_id or emergent_label must be given.
    """
    if bool(params.typology_id) == bool(params.emergent_label):
        return "Rejected: provide exactly one of typology_id or emergent_label."
    if params.typology_id and not any(r["typology_id"] == params.typology_id for r in _typologies()):
        return "Rejected: %s is not in the library. Use emergent_label if this is new." % params.typology_id

    record = {
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "advisory_id": params.advisory_id,
        "typology_id": params.typology_id,
        "emergent_label": params.emergent_label,
        "rationale": params.rationale,
        "confidence": params.confidence,
        "status": "pending_review",
    }
    PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSALS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return "Accepted into review queue: %s -> %s" % (
        params.advisory_id,
        params.typology_id or "EMERGENT(%s)" % params.emergent_label,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
