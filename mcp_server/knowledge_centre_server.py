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
import sys
from datetime import datetime, timezone
from functools import lru_cache
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

# The server is launched as a script, so the repo root is not on sys.path.
sys.path.insert(0, str(ROOT))
from schemas.citation_match import PageIndex, file_sha256  # noqa: E402
# The contract the review gate re-asserts: one definition for both sides.
from schemas.proposal_contract import QUOTE_MAX, QUOTE_MIN, SCHEMA, proposal_id  # noqa: E402

# Set by the RUNNER (agents/run_identity.py), never by the agent. Read at call
# time, not import time, so a guard can vary them between calls.
RUN_ENV = ("NEXUS_RUN_ID", "NEXUS_STAGE", "NEXUS_ADVISORY_ID", "NEXUS_PDF_PATH", "NEXUS_PDF_SHA256")

# The queue path is part of the run identity too, with no default: a runner
# that supplies the five identity keys but not this one must not fall back to
# the retired data/proposals.jsonl. Since week 6 it can no longer CHOOSE the
# file: the server derives <QUEUE_DIR>/<run_id>.jsonl and refuses any other,
# so the environment cannot redirect a governed write.
QUEUE_ENV = "NEXUS_PROPOSALS_PATH"
QUEUE_DIR = ROOT / "data" / "proposals"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")

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


class ProposedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(..., ge=1, description="PDF page index: the n in the '=== PAGE n ===' marker")
    quote: str = Field(..., min_length=QUOTE_MIN, max_length=QUOTE_MAX, description="Verbatim text from that page")


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
    citations: List[ProposedCitation] = Field(
        ..., min_length=1, max_length=5,
        description="The page and verbatim quote this link rests on -- the same citations as the record entry. "
                    "A quote that is not on the page it names is refused.",
    )


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
            t = TYPOLOGY_TWINS.get(params.typology_id)
            if t:
                # Attached to the doctrine the agent is reading, at the moment it
                # decides. The governed export itself is never modified.
                twin_label = next((x["label"] for x in _typologies() if x["typology_id"] == t["twin"]), "?")
                r = dict(r, twin={"typology_id": t["twin"], "label": twin_label,
                                  "prefer": t["prefer"], "convention": t["note"]})
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


# Vocabulary the doctrine does not carry, added to the search index only.
#
# WHY THIS EXISTS. Traced 2026-09-12 on ADV-2026-0016. The alert's red flag 4
# reads "a customer that significantly OVERPAYS for a Common High Priority list
# item". TBML001 Over Invoicing describes itself as "the price of goods is
# intentionally inflated beyond their true market value" and never says overpay,
# so the document's own sentence could not reach it: the tool returned only
# TBML002U Under Invoicing, the agent correctly rejected that on the mechanism
# test ("the opposite direction of value distortion"), and the typology was
# missed in 13 of 13 runs.
#
# Worse, TBML002U's doctrine DOES mention overpayment, in a mirror-image
# contrast. `overpa` is the highest-IDF term in such a query (4.06), so the
# OPPOSITE-direction typology outranked the right one 0.78 to 0.42. A typology
# pair differing only in direction was the one case the scorer could not separate.
#
# RULES FOR THIS MAP, because it is the kind of thing that rots into a hack:
#   1. Aliases are hand-written from the DOCTRINE'S MEANING, never mined from
#      evals/golden/. Mining the eval corpus and then measuring recall on it
#      would be circular, and the resulting number would be a fiction.
#   2. Direction pairs are added SYMMETRICALLY. Giving TBML001 payment-side
#      vocabulary while leaving TBML002U without its own biases the pair rather
#      than fixing it.
#   3. It goes in the SEARCH INDEX only. data/typologies.json is a governed
#      export from fc-10 and is never edited here; get_typology still returns
#      the governed doctrine verbatim, so nothing the agent cites changes.
#   4. The proper home for most of these is fc-10's doctrine, where the
#      description genuinely under-describes the technique. This layer is the
#      fast fix; the upstream one is the correct fix.
#
# Guarded by evals/search_aliases_probe.py, and evals/search_probes.py must stay
# 12 of 12 -- an alias that buys recall by matching everything is a regression.
SEARCH_ALIASES = {
    "TBML001": ["overpayment", "overpays", "overpaid", "pays above market value",
                "price inflated above market value"],
    "TBML002U": ["underpayment", "underpays", "underpaid", "pays below market value",
                 "price deflated below market value"],
}

def _search_index() -> tuple:
    """(docs, idf) over the current library. 57 records; rebuilt per call on purpose."""
    docs = []
    for r in _typologies():
        label = set(_stems(r["label"]))
        body = set(_stems(" ".join(
            [r.get("summary", ""), r.get("intelligence_question", "")]
            + r.get("indicators", [])
            + SEARCH_ALIASES.get(r["typology_id"], []))))
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


# ---------------------------------------------------------------------------
# Cross-family twins: the same technique carried by two typology codes.
#
# WHY THIS IS DATA AND NOT A PROMPT LINE. The system prompt said "Two typologies
# can share a label; choose by family". Measured 2026-09-13 across ten runs of
# ADV-2026-0017: SAN002 and PAT008 are both labelled "Shadow Fleet", so the rule
# fires and the agent chooses correctly 10 of 10. SAN006 "Trade Based Sanctions
# Evasion" and TBML010 "Sanctions Evasion Through Trade" are the same concept
# with the words reordered, so the rule NEVER FIRES -- SAN006 was asserted in 0
# of 10 runs and TBML010 in 8 of 10. One wrong choice scores as a false negative
# AND a false positive, so it inflates the measured recall gap twice over.
#
# A rule whose predicate is string equality is correct English and the wrong
# test: it is satisfied by the pair that does not need it and silent on the pair
# that does. So the relation is declared here, surfaced in every search and
# get_typology result, and propose_link refuses a twinned link whose rationale
# does not say why that family. The agent can no longer choose a twin without
# knowing the other exists, and cannot commit without recording the reason.
#
# PREFERENCE. For the three sanctions/trade pairs the owner decision of
# 2026-09-10 (evals/golden/README.md) is that an advisory framed as sanctions or
# export-control evasion takes the SANCTIONS twin. BA008/CM004 was found by
# measurement on 2026-09-13, is NOT an owner decision, and has no stated
# preference -- it is declared so the ambiguity is visible, with `prefer` None so
# nothing is asserted that nobody decided.
_TWIN_PAIRS = (
    ("SAN006", "TBML010", "SAN006",
     "An advisory framed as sanctions or export-control evasion takes the sanctions twin."),
    ("SAN007", "TBML007", "SAN007",
     "An advisory framed as sanctions or export-control evasion takes the sanctions twin."),
    ("SAN002", "PAT008", "SAN002",
     "An advisory framed as sanctions or export-control evasion takes the sanctions twin."),
)

# REJECTED CANDIDATES, and why the rejection is recorded rather than silent.
#
# The pairs above were found by reading doctrine. A cheaper detector -- identical
# or near-identical labels across families -- also proposes BA008/CM004, and on
# 2026-09-13 that one was briefly ADDED to the map on label overlap alone, before
# anyone read what the two codes say:
#
#   BA008 (correspondent_banking) "Layering" -- the classic middle stage of
#     laundering: funds already placed are pushed through a chain of transfers to
#     sever the audit trail.
#   CM004 (capital_markets) "Layering" -- ORDER-BOOK layering: staggering
#     non-bona-fide orders across price levels to fake depth, then cancelling.
#
# A homonym, not a twin. The three real pairs are one technique under two codes;
# these are two techniques under one word. Declaring it would have been actively
# harmful: BA008 appears in 13 of the 20 golden labels, more than any other
# typology, so every BA008 link would have demanded a meaningless justification
# naming CM004 -- and a refusal the agent cannot satisfy honestly is a refusal it
# answers by dropping the claim, which is measured behaviour (see df8d4aa).
#
# Kept here so the candidate is not rediscovered and re-added by the same
# shortcut. LABEL OVERLAP PROPOSES; DOCTRINE DECIDES.
_REJECTED_TWIN_CANDIDATES = {
    ("BA008", "CM004"): "homonym: AML layering vs order-book layering, different techniques",
}


def _twins() -> dict:
    """typology_id -> {twin, prefer, note}. Bidirectional, built from _TWIN_PAIRS."""
    out = {}
    for a, b, prefer, note in _TWIN_PAIRS:
        out[a] = {"twin": b, "prefer": prefer, "note": note}
        out[b] = {"twin": a, "prefer": prefer, "note": note}
    return out


TYPOLOGY_TWINS = _twins()


def _twin_line(typology_id: str) -> str:
    """One-line twin declaration for a search result, or empty."""
    t = TYPOLOGY_TWINS.get(typology_id)
    if not t:
        return ""
    if t["prefer"]:
        return " (TWIN of %s; prefer %s when the advisory is framed that way)" % (t["twin"], t["prefer"])
    return " (TWIN of %s; no preference set, choose on framing)" % t["twin"]


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
    tool did not return.

    A result marked TWIN carries the same technique as another code in a different
    family. The declaration names the twin and the preference where one exists;
    propose_link will refuse the link unless the rationale says why that family.
    Do not rely on the two labels looking alike -- SAN006 and TBML010 are the same
    technique with the words reordered.
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
        # Declared here rather than left to the prompt: see _TWIN_PAIRS.
        line += _twin_line(r["typology_id"])
        out.append(line)
    return "\n".join(out)


def _run_context() -> Optional[dict]:
    ctx = {k: os.environ.get(k, "") for k in RUN_ENV + (QUEUE_ENV,)}
    return ctx if all(ctx.values()) else None


def _proposals_path(run: dict) -> Path:
    return QUEUE_DIR / ("%s.jsonl" % run["NEXUS_RUN_ID"])


def _refuse_queue(run: dict) -> Optional[str]:
    if not RUN_ID_PATTERN.match(run["NEXUS_RUN_ID"]):
        return "Rejected: run id %r is not a safe file name." % run["NEXUS_RUN_ID"]
    want = _proposals_path(run)
    if Path(run[QUEUE_ENV]).resolve() != want.resolve():
        return ("Rejected: this run's queue is %s, but the runner named %s. A proposal is written only to "
                "its own run's queue." % (want.name, Path(run[QUEUE_ENV]).name))
    return None


@lru_cache(maxsize=4)
def _page_index(pdf_path: str, expected_sha: str) -> PageIndex:
    if file_sha256(pdf_path) != expected_sha:
        raise ValueError("document hash mismatch: %s is not the document this run was started on" % pdf_path)
    return PageIndex.from_pdf(pdf_path)


def _refuse_for_run(params: "ProposeLinkInput", run: dict) -> Optional[str]:
    if params.advisory_id != run["NEXUS_ADVISORY_ID"]:
        return ("Rejected: this run is extracting %s; a proposal for %s cannot come from it."
                % (run["NEXUS_ADVISORY_ID"], params.advisory_id))
    return None


def _refuse_citations(params: "ProposeLinkInput", run: dict) -> Optional[str]:
    try:
        index = _page_index(run["NEXUS_PDF_PATH"], run["NEXUS_PDF_SHA256"])
    except (OSError, ValueError) as exc:
        return "Rejected: %s" % exc
    bad = []
    for c in params.citations:
        hit = index.locate(c.page, c.quote)
        if hit.ok:
            continue
        where = (" It appears on page %s." % ", ".join(str(n) for n in hit.found_on)) if hit.found_on \
            else " It is not in the document."
        bad.append("page %d: %r.%s" % (c.page, c.quote[:80], where))
    if bad:
        return ("Rejected: %d citation%s not found on the page named. Quote the page text verbatim, with the "
                "page number from its '=== PAGE n ===' marker, and propose again. %s"
                % (len(bad), "" if len(bad) == 1 else "s", " | ".join(bad[:3])))
    return None


@mcp.tool(
    name="knowledge_centre_propose_link",
    annotations={"title": "Propose advisory link", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def propose_link(params: ProposeLinkInput) -> str:
    """
    Propose that an advisory be pinned to a typology, or propose an emergent typology.

    This never writes to the library. It appends to this run's review queue; a
    human decides in tools/review.py. Exactly one of typology_id or
    emergent_label must be given, and every proposal carries the citations it
    rests on, each verified against the page it names.
    """
    # GOVERNANCE: a proposal nobody can trace to a run and a document cannot be
    # reviewed. The runner supplies the identity; without it, nothing is written.
    run = _run_context()
    if run is None:
        return ("Rejected: this server was started without a run identity (%s). A proposal that cannot be "
                "traced to a run and a document cannot be reviewed." % ", ".join(RUN_ENV + (QUEUE_ENV,)))
    refusal = _refuse_queue(run)
    if refusal:
        return refusal
    if bool(params.typology_id) == bool(params.emergent_label):
        return "Rejected: provide exactly one of typology_id or emergent_label."
    refusal = _refuse_for_run(params, run)
    if refusal:
        return refusal
    if params.typology_id and not any(r["typology_id"] == params.typology_id for r in _typologies()):
        return "Rejected: %s is not in the library. Use emergent_label if this is new." % params.typology_id

    # GOVERNANCE, not advice. A twinned code may not be pinned without the
    # rationale naming the twin it was chosen over. The refusal is what makes the
    # reason exist: trace one on ADV-2026-0016 found a typology retrieved,
    # confirmed and then dropped with no record anywhere of why.
    twin = TYPOLOGY_TWINS.get(params.typology_id or "")
    if twin and twin["twin"] not in (params.rationale or ""):
        return ("Rejected: %s has a cross-family twin, %s. These carry the same technique under "
                "two codes, so the choice has to be recorded. %s Name %s in the rationale and say "
                "why this family fits the advisory's framing, then propose again."
                % (params.typology_id, twin["twin"], twin["note"], twin["twin"]))

    # GOVERNANCE: the quote is checked where it is made, so the agent can correct
    # it, and again by the review gate, because the queue is a file.
    refusal = _refuse_citations(params, run)
    if refusal:
        return refusal

    body = {
        "schema": SCHEMA,
        "run_id": run["NEXUS_RUN_ID"],
        "stage": run["NEXUS_STAGE"],
        "advisory_id": params.advisory_id,
        "document_sha256": run["NEXUS_PDF_SHA256"],
        "typology_id": params.typology_id,
        "emergent_label": params.emergent_label,
        "rationale": params.rationale,
        "confidence": params.confidence,
        "citations": [{"page": c.page, "quote": c.quote} for c in params.citations],
    }
    record = {"proposal_id": proposal_id(body),
              "proposed_at": datetime.now(timezone.utc).isoformat(), **body}
    path = _proposals_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return "Accepted into review queue: %s -> %s (proposal %s)" % (
        params.advisory_id,
        params.typology_id or "EMERGENT(%s)" % params.emergent_label,
        record["proposal_id"],
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
