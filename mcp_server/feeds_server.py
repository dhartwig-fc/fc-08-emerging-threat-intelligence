"""
The feeds MCP server: the orchestrator's only way to see and fetch new publications (slice 2).

Each tool carries one invariant, whatever the agent intends (spec section 1):

  feeds_list_new(source)  "new" is decided by the committed seen-items ledger, never by the agent;
                          only the three allowlisted sources exist; a listing is fetched at most once
                          per run; a listing whose layout no longer parses is a loud failure, never
                          "0 new items".
  feeds_fetch(item_key)   fetches only the URL of an item THIS RUN listed, on its source's
                          allowlisted hosts (redirects included), within size and type limits; pins
                          the document by sha256; a second call does not fetch again.

Both write only into inbox/<run_id>/ (feeds/inbox.py). The run identity comes from the runner's
environment (FEEDS_RUN_ID), never from a tool argument.

Sub-project B adds two tools (feeds/triage.py holds their rules):

  feeds_read_page(item_key, page)   one page of an item's PINNED document, the pages a triage quote
                                    is checked against; read-only, and refused before a fetch.
  feeds_triage(item_key, verdict, reason, quote)
                                    one verdict per item, the quote found in the pinned document, a
                                    NOT_RELEVANT verdict stored and reported like any other, a cap of
                                    10 per run. feeds_extract is sub-project C.

Every governed refusal starts with feeds_triage.REJECTED ("Rejected:"), the one prefix
agents/telemetry.REFUSAL_PREFIX counts as REFUSED -- the server never spells the prefix itself as a
literal (fix round 1). (Until slice 2 B these read "Refused:", which telemetry recorded as SUCCESS.)
Both new tools run under _STATE_LOCK, like A's two.

Works on MCP Python SDK 2.x (MCPServer) and 1.x (FastMCP).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
# The server is launched as a script, so the repo root is not on sys.path.
sys.path.insert(0, str(ROOT))
from feeds import extraction as feeds_extraction, http as feeds_http, inbox, ledger, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem, LayoutChanged  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, MAX_LISTING_BYTES, SOURCES, linked_pdfs  # noqa: E402
from schemas.citation_match import PageIndex  # noqa: E402

RUN_ENV = "FEEDS_RUN_ID"
# Module attributes, never tool arguments, so the agent cannot choose them. A guard swaps them.
INBOX_ROOT = inbox.INBOX_ROOT
SEEN_PATH = ledger.SEEN_PATH
HTTP_GET = feeds_http.get
# EVAL MODE (slice 2 B): the back-catalogue's pinned documents, gitignored. See _catalogue().
CATALOGUE_DOCS = ROOT / "evals" / "feeds" / "docs"
CATALOGUE_ENV = "FEEDS_CATALOGUE"
BATCH_ENV = "FEEDS_CATALOGUE_BATCH"

mcp = FastMCP("feeds_mcp")
# Each tool loads, changes and saves items.json. The MCP server may run parallel tool calls
# concurrently, so without this lock any await inside a body (e.g. HTTP moved to a thread) would let
# two calls save stale states and lose one source's entry.
_STATE_LOCK = asyncio.Lock()
NO_TEXT = "no text; not citable"


class ListNewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., pattern=r"^(ofsi|fincen|ofac)$", description="ofsi, fincen or ofac")


class FetchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key feeds_list_new returned in this run")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id():
    run_id = os.environ.get(RUN_ENV, "")
    return run_id if inbox.RUN_ID.fullmatch(run_id) else None


NO_RUN = "%s this server has no run identity (%s is unset or malformed); the runner sets it." % (
    feeds_triage.REJECTED, RUN_ENV)
ITEM_FIELDS = ("source", "item_id", "title", "url", "published", "summary")


def _catalogue():
    """(catalogue, its sha256, the batch keys) when the runner started this server on the back-catalogue.

    EVAL MODE. evals/run_feeds_triage.py sets FEEDS_CATALOGUE (evals/feeds/catalogue.json) and
    FEEDS_CATALOGUE_BATCH (the keys one session triages), so the SAME tools triage the fixed, tracked
    back-catalogue: feeds_list_new returns the batch's items -- never the live page, and never filtered
    by the ledger, so three repeats months apart see the same items -- and feeds_fetch returns the
    catalogue's pinned copy from CATALOGUE_DOCS, refused unless it hashes to the sha256 the catalogue
    records, never the network. From there on (the inbox, the pages, feeds_read_page, feeds_triage) the
    path is the production one, unchanged. The agent cannot set either variable.

    Returns None when FEEDS_CATALOGUE is unset (a live run). Raises ValueError on a catalogue whose key
    is not derived from its item, an item with no document, or a batch that is empty or names a key the
    catalogue does not hold.
    """
    path = os.environ.get(CATALOGUE_ENV)
    if not path:
        return None
    raw = Path(path).read_bytes()
    catalogue = json.loads(raw)
    for it in catalogue["items"]:
        if FeedItem(**{k: it[k] for k in ITEM_FIELDS}).key != it["key"]:
            raise ValueError("catalogue key %s is not derived from its item" % it["key"])
        if not it.get("document"):
            raise ValueError("catalogue item %s has no document" % it["key"])
    batch = [k for k in os.environ.get(BATCH_ENV, "").split(",") if k]
    unknown = sorted(set(batch) - {it["key"] for it in catalogue["items"]})
    if not batch or unknown:
        raise ValueError("the batch is empty or names keys the catalogue does not hold: %s" % unknown)
    return catalogue, hashlib.sha256(raw).hexdigest(), batch


def _load_catalogue():
    """(_catalogue() or None, refusal or None)."""
    try:
        return _catalogue(), None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, "%s the eval catalogue is unusable: %s" % (feeds_triage.REJECTED, exc)


def _new_items_reply(source: str, new: list, listed: int) -> str:
    rows = ["%s | %s | %s | %s" % (it.key, it.published, it.title, it.summary or "-") for it in new]
    return "%d new of %d listed on %s:\nkey | published | title | summary\n%s" % (
        len(new), listed, source, "\n".join(rows))


def _list_catalogue(run_id: str, state: dict, source: str, cat) -> str:
    catalogue, sha, batch = cat
    items = [FeedItem(**{k: it[k] for k in ITEM_FIELDS}) for it in catalogue["items"]
             if it["source"] == source and it["key"] in batch]
    new = list(items)  # the tracked catalogue decides, never the ledger
    state["eval"] = True  # tools/accept_run.py refuses a run carrying this: an eval run never reaches the ledger
    state["sources"][source] = {"listed_at": _now(), "listing_url": "catalogue", "status": "ok", "error": None,
                                "listing": None, "listing_sha256": sha, "listed": len(items), "already_seen": 0,
                                "items": [dict(it.to_json(), document=None) for it in new]}
    inbox.save(run_id, state, INBOX_ROOT)
    if not new:
        return "No new items: %s has none in this catalogue batch." % source
    return _new_items_reply(source, new, len(items))


def _catalogue_document(cat, item: dict) -> feeds_http.Fetched:
    """The catalogue's pinned copy of an item's document, from CATALOGUE_DOCS; never the network."""
    entry = next((it for it in cat[0]["items"] if it["key"] == item["key"]), None)
    if entry is None:
        raise feeds_http.FetchRefused("the catalogue has no entry for %s" % item["key"])
    doc = entry["document"]
    path = Path(CATALOGUE_DOCS) / ("%s.%s" % (doc["sha256"], doc["ext"]))
    if not path.exists():
        raise feeds_http.FetchRefused("the catalogue copy %s is missing; see tools/build_feeds_catalogue.py" % path.name)
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != doc["sha256"]:
        raise feeds_http.FetchRefused("the catalogue copy %s no longer matches its sha256" % path.name)
    return feeds_http.Fetched(item["url"], doc["final_url"], doc["content_type"], body)


@mcp.tool(
    name="feeds_list_new",
    annotations={"title": "List new items", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": True},
)
async def list_new(params: ListNewInput) -> str:
    """
    List a source's publications that no one has decided yet.

    Fetches the source's listing once per run. An item is new only if it is not in the seen-items
    ledger; you cannot declare an item new or old. Returns one row per new item:
    key | published | title | summary. Pass a key to feeds_fetch to download that item.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return _list_new(run_id, params.source)


def _list_new(run_id: str, source: str) -> str:
    state = inbox.load(run_id, INBOX_ROOT)
    if source in state["sources"]:
        return "%s %s was already listed in this run (status %s); a listing is fetched once per run." % (
            feeds_triage.REJECTED, source, state["sources"][source]["status"])
    cat, refusal = _load_catalogue()
    if refusal:
        return refusal
    if cat is not None:
        return _list_catalogue(run_id, state, source, cat)
    src = SOURCES[source]
    entry = {"listed_at": _now(), "listing_url": src.listing_url, "status": "ok", "error": None, "listing": None,
             "listing_sha256": None, "listed": 0, "already_seen": 0, "items": []}
    state["sources"][source] = entry
    try:
        got = HTTP_GET(src.listing_url, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                       max_bytes=MAX_LISTING_BYTES)
    except feeds_http.FetchRefused as exc:
        entry.update(status="unreachable", error=str(exc))
        inbox.save(run_id, state, INBOX_ROOT)
        return "Failed: %s is unreachable: %s. Report it; it is not retried in this run." % (source, exc)
    entry["listing"] = inbox.write_file(run_id, "listings/%s.%s" % (source, src.listing_ext), got.body,
                                        INBOX_ROOT)
    entry["listing_sha256"] = hashlib.sha256(got.body).hexdigest()
    try:
        items = src.parse(got.body)
    except LayoutChanged as exc:
        entry.update(status="layout_changed", error=str(exc))
        inbox.save(run_id, state, INBOX_ROOT)
        return "Failed: layout changed: %s. The listing is saved in the inbox. This is not '0 new items'." % exc
    seen = ledger.load(SEEN_PATH)
    new = [it for it in items if (it.source, it.item_id) not in seen]
    entry.update(listed=len(items), already_seen=len(items) - len(new),
                 items=[dict(it.to_json(), document=None) for it in new])
    inbox.save(run_id, state, INBOX_ROOT)
    if not new:
        return "No new items: %s listed %d, every one already decided." % (source, len(items))
    return _new_items_reply(source, new, len(items))


def _describe(doc: dict) -> str:
    if doc["page_error"] is None:
        pages = "%d page(s), %d with text" % (doc["pages"], doc["text_pages"])
    elif doc["page_error"] == NO_TEXT:
        pages = "%d page(s), 0 with text: %s" % (doc["pages"], NO_TEXT)
    else:
        pages = "NOT PAGED (%s)" % doc["page_error"]
    links = ("; it links %d PDF(s), not fetched: %s" % (len(doc["linked_pdfs"]), ", ".join(doc["linked_pdfs"]))
             if doc["linked_pdfs"] else "")
    return "%s (%s, %d bytes, sha256 %s), %s%s" % (doc["path"], doc["content_type"], doc["bytes"], doc["sha256"],
                                                    pages, links)


@mcp.tool(
    name="feeds_fetch",
    annotations={"title": "Fetch an item's document", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": True},
)
async def fetch(params: FetchInput) -> str:
    """
    Download the document of an item feeds_list_new listed in this run, and pin it by sha256.

    You give the key, never a URL: the tool fetches the item's own listed URL, on its source's
    allowlisted hosts only. Returns the pinned file, its size, its number of text pages, and any
    PDFs the page links to (listed, not fetched). A second call for the same item returns the
    pinned file without fetching again.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return _fetch(run_id, params.item_key)


def _fetch(run_id: str, item_key: str) -> str:
    state = inbox.load(run_id, INBOX_ROOT)
    item = inbox.find_item(state, item_key)
    if item is None:
        return "%s %s was not listed as new in this run; call feeds_list_new first." % (feeds_triage.REJECTED,
                                                                                        item_key)
    if item.get("document"):
        return "Already fetched: %s" % _describe(item["document"])
    cat, refusal = _load_catalogue()
    if refusal:
        return refusal
    src = SOURCES[item["source"]]
    try:
        got = (_catalogue_document(cat, item) if cat is not None else
               HTTP_GET(item["url"], allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES,
                        max_bytes=MAX_DOCUMENT_BYTES))
    except feeds_http.FetchRefused as exc:
        item["fetch_error"] = str(exc)
        inbox.save(run_id, state, INBOX_ROOT)
        return "Failed: %s could not be fetched: %s" % (item_key, exc)
    sha = hashlib.sha256(got.body).hexdigest()
    is_pdf = got.content_type == "application/pdf"
    rel = inbox.write_file(run_id, "docs/%s.%s" % (sha, "pdf" if is_pdf else "html"), got.body, INBOX_ROOT)
    try:
        index = (PageIndex.from_pdf(inbox.run_dir(run_id, INBOX_ROOT) / rel) if is_pdf
                 else PageIndex.from_html(got.body))
        pages, text_pages, error = len(index), sum(1 for p in index.pages if p.strip()), None
        if text_pages == 0:  # pinned, but a document with no text cannot carry a citation: say so
            error = NO_TEXT
    except Exception as exc:  # the document stays pinned, and the failure is recorded and returned
        pages, text_pages, error = 0, 0, "%s: %s" % (type(exc).__name__, exc)
    item["document"] = {"path": rel, "sha256": sha, "content_type": got.content_type, "bytes": len(got.body),
                        "final_url": got.final_url, "fetched_at": _now(), "pages": pages,
                        "text_pages": text_pages, "page_error": error,
                        "linked_pdfs": [] if is_pdf else linked_pdfs(got.body, got.final_url)}
    inbox.save(run_id, state, INBOX_ROOT)
    return "Fetched: %s" % _describe(item["document"])


class ReadPageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key feeds_list_new returned in this run, already fetched")
    page: int = Field(..., ge=1, description="1-based page number")


@mcp.tool(
    name="feeds_read_page",
    annotations={"title": "Read a page of a fetched document", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def read_page(params: ReadPageInput) -> str:
    """
    Read one page of the document feeds_fetch pinned for an item in this run.

    These are the pages feeds_triage checks your quote against. The reply starts
    "=== PAGE n of N ===". Read page 1 first; read more when it does not settle the question.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return _read_page(run_id, params.item_key, params.page)


def _read_page(run_id: str, item_key: str, page: int) -> str:
    item = inbox.find_item(inbox.load(run_id, INBOX_ROOT), item_key)
    if item is None:
        return "%s %s was not listed as new in this run; call feeds_list_new first." % (feeds_triage.REJECTED,
                                                                                        item_key)
    path, refusal = feeds_triage.pinned_document(run_id, item, INBOX_ROOT)
    if path is None:
        return refusal
    pages = feeds_triage.page_texts(path)
    if not 1 <= page <= len(pages):
        return "%s %s's document has %d page(s); there is no page %d." % (feeds_triage.REJECTED, item_key,
                                                                          len(pages), page)
    return "=== PAGE %d of %d === %s | listing title (not quotable): %s\n%s" % (
        page, len(pages), item_key, item["title"], pages[page - 1].strip())


class TriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key feeds_list_new returned in this run, already fetched")
    verdict: str = Field(..., description="relevant or not_relevant")
    reason: str = Field(..., description="Why, in at most 300 characters")
    quote: str = Field(..., description="One verbatim quote of 10 to 600 characters, copied from the item's "
                                        "pages as feeds_read_page returned them, that supports the verdict")


@mcp.tool(
    name="feeds_triage",
    annotations={"title": "Record a triage verdict", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
async def triage(params: TriageInput) -> str:
    """
    Record whether an item is relevant: it describes methods, red flags or cases of financial crime
    that a typology could hold. When in doubt, keep it (relevant).

    One verdict per item, final. The quote must be found in the item's pinned document. A
    not_relevant verdict is stored and reported, never deleted. Lengths and bounds are checked by
    the tool, which replies "Rejected: ..." with the reason when it refuses.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return feeds_triage.decide(run_id, params.item_key, params.verdict, params.reason, params.quote,
                                   INBOX_ROOT)[1]


class ExtractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key triaged relevant in this run")


async def extract(params: ExtractInput) -> str:
    """
    Queue a relevant item for extraction after this session. You do not extract, and you do not see
    the result: the run extracts in code once you finish, within its budget.

    Refused unless the item is triaged relevant in this run; one request per item; at most 3 per run.
    The tool chooses what is extracted: the publication's own PDF when the page you read links exactly
    one on the source's document hosts (it fetches and pins it now), otherwise the page itself.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return feeds_extraction.request(run_id, params.item_key, HTTP_GET, INBOX_ROOT)[1]


# EVAL MODE never sees extraction (slice 2 C): the tool is not even listed to a session the eval runner
# starts, so B's triage-only measurement keeps exactly the four tools it was measured with.
if not os.environ.get(CATALOGUE_ENV):
    mcp.tool(
        name="feeds_extract",
        annotations={"title": "Queue an item for extraction", "readOnlyHint": False, "destructiveHint": False,
                     "idempotentHint": False, "openWorldHint": True},
    )(extract)


if __name__ == "__main__":
    mcp.run()
