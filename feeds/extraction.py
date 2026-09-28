"""
Extraction for one feeds run (slice 2 C; spec sections 1 and 2): the agent REQUESTS, code EXTRACTS.

  inbox/<run_id>/extractions.jsonl      one REQUEST per item, appended by feeds_extract (the agent's tool)
  inbox/<run_id>/extraction_runs.jsonl  one OUTCOME per request, appended by tools/friday_run.py after the
                                        orchestrator stops: extracted, failed, or deferred for budget
  inbox/<run_id>/advisory_ids.jsonl     one line per advisory id ALLOCATED, written BEFORE its extraction starts

Each rule is carried here, whatever the agent intends:
  relevant only  a request needs the item's triage verdict to be RELEVANT (feeds/triage.py);
  once, capped   one request per item; at most MAX_PER_RUN (3) per run -- the fourth is refused, and that
                 item stays unfinished and returns next run;
  the document   what is extracted is chosen by RULE, never by the agent (document_choice): a pinned PDF is
                 itself; a pinned HTML page linking exactly ONE PDF on its source's document_hosts is that
                 PDF, fetched and pinned now, through feeds.http.get (https, exact host, PDF only, the size
                 cap, the 2-second gap); a page linking none is the page itself; a page linking several is
                 refused as ambiguous, for a person. The URL comes from the PINNED page's bytes, never an
                 argument, so the choice is re-derivable from the inbox by committed code.
  unreadable     a linked PDF pypdf cannot page, or one with no text, is refused ("Rejected:"), but RECORDED
                 with its reason and its pinned copy kept; a second request is answered from that line,
                 never fetched again;
  live only      an eval run (the back-catalogue, state["eval"]) is refused here, not only by the tool's
                 absence from an eval server: a live server pointed at an eval run still cannot queue;
  the hosts      "on the document hosts" is feeds.http._check_host, the ONE allowlist predicate (https,
                 exact lowercased netloc: another port, plain http or userinfo is off the list).
Every refusal starts "Rejected:" (feeds.triage.REJECTED), which telemetry counts as REFUSED.

Advisory ids are allocated by allocate_advisory_id() when the runner STARTS an extraction, never here: a
request deferred for budget consumes no id. The allocation is written before the extraction runs, so a run
that dies mid-extraction still holds its id. An id in any run's allocations (expired runs included) is never
allocated again, a stale computation raises rather than writing a duplicate, and load_allocations
raises on one; accept_run keeps it, so the id a proposal carries is the id it is accepted under.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from feeds import inbox, triage as feeds_triage
from feeds.sources import MAX_DOCUMENT_BYTES, SOURCES
from feeds.http import FetchRefused, _check_host

REQUESTS = "extractions.jsonl"
OUTCOMES = "extraction_runs.jsonl"
ALLOCATIONS = "advisory_ids.jsonl"
MAX_PER_RUN = 3
PDF_TYPES = frozenset({"application/pdf"})
ADVISORY_ID = re.compile(r"\AADV-(\d{4})-(\d{4})\Z")
REJECTED = feeds_triage.REJECTED


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lines(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append(run_id: str, name: str, entry: dict, root: Path) -> None:
    folder = inbox.run_dir(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / name, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def load_requests(run_id: str, root: Path = inbox.INBOX_ROOT) -> List[dict]:
    """The run's requests in the order the agent made them; a second line for one item is corruption."""
    out, seen = [], set()
    for entry in _lines(inbox.run_dir(run_id, root) / REQUESTS):
        if entry["key"] in seen:
            raise ValueError("%s: %s is requested twice" % (REQUESTS, entry["key"]))
        seen.add(entry["key"])
        out.append(entry)
    return out


def load_outcomes(run_id: str, root: Path = inbox.INBOX_ROOT) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for entry in _lines(inbox.run_dir(run_id, root) / OUTCOMES):
        if entry["key"] in out:
            raise ValueError("%s: %s has two outcomes" % (OUTCOMES, entry["key"]))
        out[entry["key"]] = entry
    return out


def append_outcome(run_id: str, outcome: dict, root: Path = inbox.INBOX_ROOT) -> None:
    if outcome["key"] in load_outcomes(run_id, root):
        raise ValueError("%s already has an outcome in run %s" % (outcome["key"], run_id))
    _append(run_id, OUTCOMES, outcome, root)


def _on_hosts(url: str, hosts) -> bool:
    """feeds.http's own allowlist rule, asked as a question: the link is chosen by the SAME predicate the
    fetch and every redirect hop are checked against, never a second copy that could drift from it."""
    try:
        _check_host(url, hosts)
    except FetchRefused:
        return False
    return True


def document_choice(item: dict) -> Tuple[str, List[str], List[str]]:
    """(kind, candidate URLs, ignored URLs) for an item's pinned document; kind is pinned|linked|ambiguous."""
    doc = item["document"]
    if doc["content_type"] == "application/pdf":
        return "pinned", [], []
    hosts = SOURCES[item["source"]].document_hosts
    links = doc.get("linked_pdfs") or []
    ok = [u for u in links if _on_hosts(u, hosts)]
    ignored = [u for u in links if u not in ok]
    if not ok:
        return "pinned", [], ignored
    return ("linked" if len(ok) == 1 else "ambiguous"), ok, ignored


def request(run_id: str, key: str, http_get, root: Path = inbox.INBOX_ROOT) -> Tuple[bool, str]:
    """Record one extraction request, or refuse it. Returns (recorded, the message the agent sees)."""
    state = inbox.load(run_id, root)
    if state.get("eval"):
        return False, ("%s %s is an eval run over the back-catalogue; nothing in it is extracted, and %s is not "
                       "queued." % (REJECTED, run_id, key))
    item = inbox.find_item(state, key)
    if item is None:
        return False, "%s %s was not listed as new in this run." % (REJECTED, key)
    verdict = feeds_triage.load(run_id, root).get(key)
    if verdict is None or verdict["verdict"] != feeds_triage.RELEVANT:
        return False, "%s %s has %s; only an item triaged relevant is extracted." % (
            REJECTED, key, "no verdict" if verdict is None else "the verdict %s" % verdict["verdict"])
    done = load_requests(run_id, root)
    if any(r["key"] == key for r in done):
        prior = next(r for r in done if r["key"] == key)
        if prior["error"]:  # its outcome is on the line already: say it, and never fetch again
            return False, "%s %s was already requested in this run, with the recorded outcome: %s It is not " \
                          "fetched again." % (REJECTED, key, prior["error"].rstrip(".") + ".")
        return False, "%s %s is already queued for extraction in this run." % (REJECTED, key)
    if len(done) >= MAX_PER_RUN:
        return False, ("%s this run has queued its cap of %d extractions; %s stays unfinished and returns next run."
                       % (REJECTED, MAX_PER_RUN, key))
    path, refusal = feeds_triage.pinned_document(run_id, item, root)
    if path is None:
        return False, refusal
    kind, urls, ignored = document_choice(item)
    if kind == "ambiguous":
        return False, ("%s %s's page links %d PDFs on %s's document hosts (%s); which one is the publication is a "
                       "person's call, not this run's." % (REJECTED, key, len(urls), item["source"], ", ".join(urls)))
    entry = {"key": key, "source": item["source"], "item_id": item["item_id"], "run_id": run_id,
             "requested_at": _now(), "chosen": kind, "ignored_links": ignored, "document": None, "error": None}
    if kind == "pinned":
        entry["document"] = dict(item["document"], url=item["document"]["final_url"])
    else:
        src = SOURCES[item["source"]]
        try:
            got = http_get(urls[0], allowed_hosts=src.document_hosts, allowed_types=PDF_TYPES,
                           max_bytes=MAX_DOCUMENT_BYTES)
        except FetchRefused as exc:
            entry["error"] = "the linked PDF could not be fetched: %s" % exc
            _append(run_id, REQUESTS, entry, root)
            return True, "Failed: %s is queued but its PDF could not be fetched (%s); it will be reported." % (key, exc)
        sha = hashlib.sha256(got.body).hexdigest()
        rel = inbox.write_file(run_id, "docs/%s.pdf" % sha, got.body, root)
        try:
            texts = feeds_triage.page_texts(inbox.run_dir(run_id, root) / rel)
        except Exception as exc:  # labelled a PDF, but not one pypdf can page: the copy stays pinned as evidence
            reason = "%s: %s" % (type(exc).__name__, exc)
            entry["document"] = {"path": rel, "sha256": sha, "content_type": got.content_type,
                                 "bytes": len(got.body), "url": got.final_url, "fetched_at": _now(), "pages": 0,
                                 "text_pages": 0, "page_error": reason}
            entry["error"] = ("%s %s's linked PDF %s was pinned but could not be read (%s); it is reported, not "
                              "extracted." % (REJECTED, key, got.final_url, reason))
            _append(run_id, REQUESTS, entry, root)  # recorded, so a retry is answered from the line, not refetched
            return True, entry["error"]  # recorded (the line exists), and refused: "Rejected:" says so
        entry["document"] = {"path": rel, "sha256": sha, "content_type": got.content_type, "bytes": len(got.body),
                             "url": got.final_url, "fetched_at": _now(), "pages": len(texts),
                             "text_pages": sum(1 for t in texts if t.strip()),
                             "page_error": None if any(t.strip() for t in texts) else "no text; not citable"}
        if entry["document"]["page_error"]:
            entry["error"] = ("%s %s's linked PDF %s was pinned but has no text (%s); it is reported, not "
                              "extracted." % (REJECTED, key, got.final_url, entry["document"]["page_error"]))
    _append(run_id, REQUESTS, entry, root)
    if entry["error"]:  # recorded, and refused: it will never be extracted, so it is never told "Queued"
        return True, entry["error"]
    doc = entry["document"]
    return True, "Queued: %s will be extracted after this session, from %s (%d page(s))." % (
        key, "its linked PDF %s" % doc["url"] if kind == "linked" else "the page itself", doc["pages"])


def _ids_in(path: Path) -> List[str]:
    return [e.get("advisory_id") for e in _lines(path) if e.get("advisory_id")]


def next_advisory_id(year: int, advisory_lists, inbox_root: Path = inbox.INBOX_ROOT) -> str:
    """The next ADV-<year>-NNNN after every id in the advisory lists (the golden one and the live-feed one) and
    every id any run has allocated, including expired runs (inbox/expired/): an id that ever reached a record
    or a queue is never reused. `advisory_lists` is one path or several; a list that does not exist yet is empty."""
    paths = [advisory_lists] if isinstance(advisory_lists, (str, Path)) else list(advisory_lists)
    taken = [a["advisory_id"] for p in paths if Path(p).exists()
             for a in json.loads(Path(p).read_text(encoding="utf-8"))["advisories"]]
    for path in sorted(Path(inbox_root).glob("**/%s" % ALLOCATIONS)):
        taken += _ids_in(path)
    numbers = [int(m.group(2)) for m in map(ADVISORY_ID.match, taken) if m and int(m.group(1)) == year]
    return "ADV-%04d-%04d" % (year, max(numbers, default=0) + 1)


def allocate_advisory_id(run_id: str, key: str, year: int, advisory_lists,
                         root: Path = inbox.INBOX_ROOT) -> str:
    """Allocate the next advisory id to `key` and record it in the run's allocations BEFORE extraction.

    Refused (ValueError), never written: a key that already holds an id in this run, and an id that any run
    has already allocated. The second is re-read immediately before the append, so a run whose computed id
    went stale (another run allocated it meanwhile) raises instead of writing a duplicate. It narrows the
    read-then-append window; it does not close it -- serialising Friday runs is tools/friday_run.py's job."""
    if key in load_allocations(run_id, root):
        raise ValueError("%s already holds an advisory id in run %s; it is not allocated another" % (key, run_id))
    advisory_id = next_advisory_id(year, advisory_lists, root)
    allocated = {i for p in Path(root).glob("**/%s" % ALLOCATIONS) for i in _ids_in(p)}
    if advisory_id in allocated:
        raise ValueError("%s is already allocated; an advisory id is never allocated twice" % advisory_id)
    _append(run_id, ALLOCATIONS, {"key": key, "advisory_id": advisory_id, "allocated_at": _now()}, root)
    return advisory_id


def load_allocations(run_id: str, root: Path = inbox.INBOX_ROOT) -> Dict[str, str]:
    """key -> advisory id; a key with two ids, or an id given to two keys, is corruption and RAISES, as a
    duplicated request or outcome line does: it is never resolved silently by keeping the last line."""
    out: Dict[str, str] = {}
    for entry in _lines(inbox.run_dir(run_id, root) / ALLOCATIONS):
        if entry["key"] in out or entry["advisory_id"] in out.values():
            raise ValueError("%s: %s / %s is allocated twice" % (ALLOCATIONS, entry["key"], entry["advisory_id"]))
        out[entry["key"]] = entry["advisory_id"]
    return out
