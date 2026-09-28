"""
Triage verdicts for one feeds run: inbox/<run_id>/triage.jsonl (gitignored), one line per item.

Each rule is carried here, in code, whatever the agent intends (spec section 4 and section 1's table):
  one verdict   an item that already has a line cannot be triaged again; the first verdict stands;
  kept, always  a NOT_RELEVANT verdict is written exactly like a RELEVANT one, and nothing in this
                module removes or rewrites a line: the file is only ever appended to;
  quoted        the quote must be found in the item's PINNED document -- the bytes feeds_fetch pinned,
                re-hashed here -- on at least one of its pages, by schemas/citation_match.PageIndex,
                the one matcher every other caller uses;
  bounded       a reason of 1..REASON_MAX characters; a quote within the proposal contract's bounds
                (after strip, so padding cannot lengthen a short quote); at most MAX_PER_RUN verdicts
                in one run (spec section 1's cap of 10 triaged items).

Every refusal starts "Rejected:", the prefix agents/telemetry.py classifies as REFUSED, so a refused
triage call is counted as the governance working, never as a success.

The pages a quote is checked against are the pages the agent reads (page_texts), and page_texts IS
schemas.citation_match.document_texts: one page rule for triage, extraction, the review gate and the
citation audit (slice 2 C), pinned by evals/check_document_pages.py. Measured before delegating: all
263 local documents (243 pinned HTML pages, 20 golden PDFs) paged byte-identically either way.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from feeds import inbox
from schemas.citation_match import PageIndex, document_texts, file_sha256
from schemas.proposal_contract import QUOTE_MAX, QUOTE_MIN

TRIAGE = "triage.jsonl"
RELEVANT, NOT_RELEVANT = "relevant", "not_relevant"
VERDICTS = (RELEVANT, NOT_RELEVANT)
REASON_MAX = 300
MAX_PER_RUN = 10
REJECTED = "Rejected:"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def page_texts(path: Path) -> List[str]:
    """The pinned document's pages, as the agent reads them and as the quote is checked against them.
    schemas.citation_match's one loader, never a second copy of its rule: a .pdf by pypdf, a .html by
    schemas/html_pages, anything else refused."""
    return document_texts(path)


def pinned_document(run_id: str, item: dict, root: Path = inbox.INBOX_ROOT) -> Tuple[Optional[Path], str]:
    """(path, "") for an item whose pinned document is intact, else (None, the refusal)."""
    doc = item.get("document")
    if not doc:
        return None, "%s %s has no pinned document; call feeds_fetch first." % (REJECTED, item["key"])
    if doc.get("page_error"):
        return None, "%s %s's document could not be paged (%s)." % (REJECTED, item["key"], doc["page_error"])
    path = inbox.run_dir(run_id, root) / doc["path"]
    if not path.exists() or file_sha256(path) != doc["sha256"]:
        return None, "%s %s's pinned document is missing or no longer matches its sha256." % (REJECTED, item["key"])
    return path, ""


def find_quote(pages: Sequence[str], quote: str) -> Tuple[str, List[int]]:
    """(match tier, every 1-based page the quote holds on); ("missing", []) when it holds on none."""
    index = PageIndex(pages)
    held = [(n, index.locate(n, quote)) for n in range(1, len(index) + 1)]
    ok = [(n, loc.status) for n, loc in held if loc.ok]
    return (ok[0][1], [n for n, _ in ok]) if ok else ("missing", [])


def load(run_id: str, root: Path = inbox.INBOX_ROOT) -> Dict[str, dict]:
    path = inbox.run_dir(run_id, root) / TRIAGE
    out: Dict[str, dict] = {}
    if not path.exists():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["key"] in out:
            raise ValueError("%s line %d: %s has a second verdict" % (TRIAGE, n, entry["key"]))
        out[entry["key"]] = entry
    return out


def _append(run_id: str, entry: dict, root: Path) -> None:
    folder = inbox.run_dir(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / TRIAGE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def decide(run_id: str, key: str, verdict: str, reason: str, quote: str,
           root: Path = inbox.INBOX_ROOT) -> Tuple[bool, str]:
    """Record one verdict, or refuse it. Returns (recorded, the message the agent sees)."""
    reason, quote = (reason or "").strip(), (quote or "").strip()
    if verdict not in VERDICTS:
        return False, "%s verdict %r is not one of %s." % (REJECTED, verdict, ", ".join(VERDICTS))
    if not reason or len(reason) > REASON_MAX:
        return False, "%s the reason is %d characters; it must be 1 to %d." % (REJECTED, len(reason), REASON_MAX)
    if not QUOTE_MIN <= len(quote) <= QUOTE_MAX:
        return False, "%s the quote is %d characters; it must be %d to %d." % (REJECTED, len(quote), QUOTE_MIN,
                                                                               QUOTE_MAX)
    item = inbox.find_item(inbox.load(run_id, root), key)
    if item is None:
        return False, "%s %s was not listed as new in this run." % (REJECTED, key)
    done = load(run_id, root)
    if key in done:
        return False, "%s %s already has a verdict (%s) in this run; the first verdict stands." % (
            REJECTED, key, done[key]["verdict"])
    if len(done) >= MAX_PER_RUN:
        return False, "%s this run has triaged its cap of %d items; %s stays unfinished and returns next run." % (
            REJECTED, MAX_PER_RUN, key)
    path, refusal = pinned_document(run_id, item, root)
    if path is None:
        return False, refusal
    match, pages = find_quote(page_texts(path), quote)
    if not pages:
        return False, ("%s the quote is not in %s's pinned document on any page. Copy it again, verbatim, "
                       "from feeds_read_page." % (REJECTED, key))
    entry = {"key": key, "source": item["source"], "item_id": item["item_id"], "verdict": verdict,
             "reason": reason, "quote": quote, "found_on": pages, "match": match,
             "document_sha256": item["document"]["sha256"], "run_id": run_id, "decided_at": _now()}
    _append(run_id, entry, root)
    return True, "Recorded: %s is %s (quote found on page %s)." % (key, verdict, ", ".join(map(str, pages)))


def reconcile(run_id: str, expected: Sequence[str] = (), root: Path = inbox.INBOX_ROOT) -> dict:
    """After the agent stops, in code: which items this run listed, triaged, and left unfinished.

    `expected` is what the run was meant to cover (a catalogue batch); an expected item the agent never
    listed is unfinished too, so skipping a whole source cannot read as "nothing to triage".
    """
    listed = sorted(it["key"] for it in inbox.items(inbox.load(run_id, root)))
    done = load(run_id, root)
    want = sorted(set(listed) | set(expected))
    return {"listed": listed, "triaged": sorted(done), "unfinished": [k for k in want if k not in done],
            "never_listed": sorted(set(expected) - set(listed))}
