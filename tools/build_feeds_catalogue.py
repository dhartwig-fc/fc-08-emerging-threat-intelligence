"""
Build the triage back-catalogue ONCE (slice 2 B, spec section 4): about 60 recent items, 20 per source.

Usage:
    python tools/build_feeds_catalogue.py            # fetch, pin, write evals/feeds/catalogue.json
    python tools/build_feeds_catalogue.py --dry-run  # the listings only: counts per source, nothing written

NETWORK. The one tool in sub-project B that makes requests. Run by hand, once; no guard calls it and
tools/check_all.py never runs it. Every request goes through feeds/http.get: the allowlist, the size
and type limits, a 2-second gap, the descriptive user agent. Measured 2026-09-27: OFSI's Atom feed
holds 20 entries and does not paginate (?page=2 returns the same 20); FinCEN's listing shows 15 per
page and OFAC's 10, and both paginate with ?page=1 (no overlap with page 0). So the listings are OFSI
page 0, FinCEN pages 0-1 and OFAC pages 0-1 (5 requests), then one request per item's document.

WRITES:
  evals/feeds/catalogue.json   TRACKED. The item list, each document's sha256 and paging, the listings'
                               sha256, and any item excluded with its reason.
  evals/feeds/docs/            GITIGNORED. <sha256>.<ext> per document; listings/<source>-p<n>.<ext>.

REFUSES when catalogue.json exists. The set is fixed once, so the three repeats and every later
comparison score the same items; a new set is a new file and an owner decision, never a rebuild.

An item whose document cannot be fetched, or pages to no text, is recorded under "excluded" with the
reason and is NOT in "items": the agent cannot quote a document it cannot read, so the item would be
scored as a miss that measures the network rather than the triage. The catalogue is not topped up
past a failure; "about 60" is what the spec asks for.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, MAX_LISTING_BYTES, SOURCES, linked_pdfs  # noqa: E402
from schemas.citation_match import PageIndex  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
DOCS = EVAL_DIR / "docs"
SCHEMA = "fc08-triage-catalogue/1"
PER_SOURCE = 20
ORDER = ("ofsi", "fincen", "ofac")
PAGES = {"ofsi": ("",), "fincen": ("", "?page=1"), "ofac": ("", "?page=1")}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pin(docs: Path, rel: str, data: bytes) -> Path:
    """Write once under docs/; the same bytes again is a no-op, different bytes are refused."""
    path = Path(docs) / rel
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("%s is pinned; refusing to overwrite it with different bytes" % rel)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def listed(source: str, get, docs: Path, pin: bool = True):
    """The newest PER_SOURCE items of a source, in listing order, and the listings they came from."""
    src = SOURCES[source]
    items, ids, listings = [], set(), []
    for n, suffix in enumerate(PAGES[source]):
        got = get(src.listing_url + suffix, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                  max_bytes=MAX_LISTING_BYTES)
        rel = "listings/%s-p%d.%s" % (source, n, src.listing_ext)
        if pin:
            _pin(docs, rel, got.body)
        listings.append({"url": src.listing_url + suffix, "path": rel, "fetched_at": _now(),
                         "sha256": hashlib.sha256(got.body).hexdigest()})
        for it in src.parse(got.body):
            if it.item_id not in ids:
                ids.add(it.item_id)
                items.append(it)
        if len(items) >= PER_SOURCE:
            break
    return items[:PER_SOURCE], listings


def pin_document(item, get, docs: Path) -> dict:
    src = SOURCES[item.source]
    got = get(item.url, allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES, max_bytes=MAX_DOCUMENT_BYTES)
    digest = hashlib.sha256(got.body).hexdigest()
    is_pdf = got.content_type == "application/pdf"
    ext = "pdf" if is_pdf else "html"
    path = _pin(docs, "%s.%s" % (digest, ext), got.body)
    index = PageIndex.from_pdf(path) if is_pdf else PageIndex.from_html(got.body)
    text_pages = sum(1 for p in index.pages if p.strip())
    if not text_pages:
        raise ValueError("the document pages to no text")
    return {"sha256": digest, "ext": ext, "content_type": got.content_type, "bytes": len(got.body),
            "final_url": got.final_url, "fetched_at": _now(), "pages": len(index), "text_pages": text_pages,
            "linked_pdfs": [] if is_pdf else linked_pdfs(got.body, got.final_url)}


def build(get=feeds_http.get, docs: Path = DOCS, today: date = None) -> dict:
    items, excluded, listings = [], [], {}
    for source in ORDER:
        found, listings[source] = listed(source, get, docs)
        for it in found:
            try:
                items.append(dict(it.to_json(), document=pin_document(it, get, docs)))
                status = "pinned"
            except (feeds_http.FetchRefused, ValueError) as exc:
                excluded.append(dict(it.to_json(), reason="%s: %s" % (type(exc).__name__, exc)))
                status = "EXCLUDED: %s" % exc
            print("  %-6s %-40s %s" % (source, it.item_id[-40:], status))
    return {"schema": SCHEMA, "built_on": (today or date.today()).isoformat(), "per_source": PER_SOURCE,
            "listing_pages": {s: list(PAGES[s]) for s in ORDER}, "listings": listings,
            "items": items, "excluded": excluded}


def dump(catalogue: dict) -> str:
    return json.dumps(catalogue, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build the triage back-catalogue once")
    ap.add_argument("--dry-run", action="store_true", help="parse the listings only; write nothing")
    args = ap.parse_args(argv)
    if CATALOGUE.exists():
        print("REFUSED: %s exists. The back-catalogue is built once; a new set is a new file and an owner "
              "decision." % CATALOGUE.relative_to(ROOT))
        return 1
    try:
        if args.dry_run:
            for source in ORDER:
                found, _ = listed(source, feeds_http.get, DOCS, pin=False)
                print("  %-6s %2d items, newest %s, oldest %s" % (source, len(found), found[0].published,
                                                                   found[-1].published))
            return 0
        catalogue = build()
    except (feeds_http.FetchRefused, LayoutChanged) as exc:
        print("FAILED: %s -- nothing written to %s" % (exc, CATALOGUE.relative_to(ROOT)))
        return 1
    CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text(dump(catalogue), encoding="utf-8")
    counts = {s: sum(1 for it in catalogue["items"] if it["source"] == s) for s in ORDER}
    print("\nWROTE %s: %d items (%s), %d excluded; sha256 %s" % (
        CATALOGUE.relative_to(ROOT), len(catalogue["items"]), ", ".join("%s %d" % kv for kv in counts.items()),
        len(catalogue["excluded"]), hashlib.sha256(CATALOGUE.read_bytes()).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
