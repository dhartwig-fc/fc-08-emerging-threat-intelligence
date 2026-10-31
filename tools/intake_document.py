"""
Take in a document the owner downloaded from a source whose site blocks automated fetching. FATF, measured
2026-10-31: every fatf-gafi.org URL answers Cloudflare's bot check, and fc-08 does not get past bot checks.
NOTHING HERE FETCHES ANYTHING.

Usage:
    python tools/intake_document.py --source fatf --file ~/Downloads/report.pdf \\
        --url https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/report.pdf \\
        --title "Report title" --published 2026-10-24 \\
        --reason "why it matters" --quote "a sentence copied verbatim from the PDF"

Writes ONE run in inbox/<run_id>/ (gitignored), in the Friday run's shape, holding the one item:
items.json (marked manual), the pinned PDF, the owner's selection as a triage line -- by: owner, held to the
quote rule every verdict is (plan R4) -- the extraction request, the advisory id, the extraction under its
US$1 cap, run.json and report.md. Then `python tools/accept_run.py <run_id>` decides it, as it decides every
run: the ledger keeps its one writer.

Refused, exit 2, BEFORE anything is written: a source that is not manual; a URL that is not https on that
source's hosts (the one allowlist predicate, feeds.http._check_host); a title, date or reason missing or
malformed; a file that is not a PDF or is over the size cap; a PDF with no text; a quote on no page; a document
already in the ledger; another Friday run or intake holding the inbox lock.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import friday_run  # noqa: E402
from agents import orchestrate_feeds as of, telemetry  # noqa: E402
from feeds import extraction, inbox, ledger, reconcile, report  # noqa: E402
from feeds import triage as feeds_triage  # noqa: E402
from feeds.http import FetchRefused, _check_host  # noqa: E402
from feeds.model import FeedItem  # noqa: E402
from feeds.sources import MANUAL_SOURCES, MAX_DOCUMENT_BYTES  # noqa: E402
from schemas.citation_match import PageIndex  # noqa: E402
from schemas.proposal_contract import QUOTE_MAX, QUOTE_MIN  # noqa: E402

DAY = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _refuse(why: str) -> int:
    print("REFUSED: %s" % why)
    return 2


def _no_fetch(*_a, **_k):
    raise AssertionError("the intake fetches nothing")


def main(argv: list, root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         advisory_lists=None, today: date = None, extractor=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    for flag in ("--source", "--file", "--url", "--title", "--published", "--reason", "--quote"):
        ap.add_argument(flag, required=True)
    args = ap.parse_args(argv)
    src = MANUAL_SOURCES.get(args.source)
    if src is None:
        return _refuse("%s is not a manual source (manual: %s)" % (args.source, ", ".join(sorted(MANUAL_SOURCES))))
    try:
        _check_host(args.url, src.hosts)
    except FetchRefused as exc:
        return _refuse("the URL is not https on %s's hosts: %s" % (src.name, exc))
    title = " ".join(args.title.split())
    try:
        date.fromisoformat(args.published)
        real_day = bool(DAY.match(args.published))
    except ValueError:
        real_day = False
    if not title or not real_day or not args.reason.strip():
        return _refuse("a title, a real YYYY-MM-DD --published and a --reason are all required")
    reason, quote = "owner-selected: " + args.reason.strip(), args.quote.strip()
    if len(reason) > feeds_triage.REASON_MAX:
        return _refuse("the reason is %d characters with its prefix; at most %d" % (len(reason), feeds_triage.REASON_MAX))
    if not QUOTE_MIN <= len(quote) <= QUOTE_MAX:
        return _refuse("the quote is %d characters; it must be %d to %d" % (len(quote), QUOTE_MIN, QUOTE_MAX))
    try:
        body = Path(args.file).expanduser().read_bytes()
    except OSError as exc:
        return _refuse("%s cannot be read: %s" % (args.file, exc))
    if not body.startswith(b"%PDF-"):
        return _refuse("%s is not a PDF" % args.file)
    if len(body) > MAX_DOCUMENT_BYTES:
        return _refuse("%s is larger than %d bytes" % (args.file, MAX_DOCUMENT_BYTES))
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.pdf"
        probe.write_bytes(body)
        try:
            index = PageIndex.from_pdf(probe)
            texts = feeds_triage.page_texts(probe)
        except Exception as exc:  # noqa: BLE001 -- a PDF pypdf cannot read is a refusal, not a crash
            return _refuse("%s cannot be read as a PDF: %s: %s" % (args.file, type(exc).__name__, exc))
    text_pages = sum(1 for p in index.pages if p.strip())
    if text_pages == 0:
        return _refuse("%s has no text; nothing in it could be cited" % args.file)
    _, found_on = feeds_triage.find_quote(texts, quote)
    if not found_on:
        return _refuse("the quote is on no page of %s; copy it again, verbatim" % args.file)
    item = FeedItem(src.name, urlsplit(args.url).path, title, args.url, args.published)
    seen = ledger.load(seen_path)
    if (item.source, item.item_id) in seen:
        return _refuse("%s:%s was already decided, in run %s" % (item.source, item.item_id,
                                                                  seen[(item.source, item.item_id)]["first_seen_run"]))
    with friday_run.run_lock(root) as held:
        if not held:
            return _refuse("another Friday run or intake holds the inbox lock")
        return _intake(item, body, len(index), text_pages, args, root, advisory_lists or friday_run.ADVISORY_LISTS,
                       today or date.today(), extractor or friday_run.extract_one)


def _intake(item, body, pages, text_pages, args, root, advisory_lists, today, extractor) -> int:
    started = _now()
    run_id = inbox.mint_run_id(today)
    sha = hashlib.sha256(body).hexdigest()
    rel = inbox.write_file(run_id, "docs/%s.pdf" % sha, body, root)
    doc = {"path": rel, "sha256": sha, "content_type": "application/pdf", "bytes": len(body),
           "final_url": item.url, "fetched_at": started, "pages": pages, "text_pages": text_pages,
           "page_error": None, "linked_pdfs": [], "delivered_by": "owner"}
    inbox.save(run_id, {"run_id": run_id, "manual": {"by": "owner", "at": started},
                        "sources": {item.source: {"status": "ok", "items": [dict(item.to_json(), document=doc)]}}}, root)
    ok, msg = feeds_triage.decide(run_id, item.key, feeds_triage.RELEVANT, "owner-selected: " + args.reason.strip(),
                                  args.quote.strip(), root, by="owner")
    if not ok:
        raise RuntimeError("the selection was refused after its checks passed: %s" % msg)
    ok, msg = extraction.request(run_id, item.key, _no_fetch, root)
    if not ok:
        raise RuntimeError("the extraction request was refused: %s" % msg)
    req = extraction.load_requests(run_id, root)[0]
    advisory_id = extraction.allocate_advisory_id(run_id, item.key, today.year, advisory_lists, root)
    previous = telemetry.TELEMETRY_DIR
    telemetry.TELEMETRY_DIR = inbox.run_dir(run_id, root) / inbox.TELEMETRY  # accept_run reads the session here
    crash, unrecorded, outcome, interrupt = None, None, {}, None
    try:
        outcome = asyncio.run(extractor(of.FeedsRun(run_id), req, advisory_id, root))
    except Exception as exc:  # the Friday run's crash path: a FAILED outcome, a crash run.json, a report
        crash = ("the run raised %s: %s" % (type(exc).__name__, exc))[:500]
    except (KeyboardInterrupt, asyncio.CancelledError) as exc:  # Ctrl-C: the same crash path, then re-raised below
        interrupt, crash = exc, "the run raised KeyboardInterrupt: interrupted"
    finally:
        telemetry.TELEMETRY_DIR = previous
    if crash is not None:
        unrecorded = friday_run.record_crash(run_id, "the run crashed before this item was extracted (%s)" % (
            crash[len("the run raised "):]), root)
    else:
        if outcome.get("status") == "extracted" and outcome.get("record"):
            outcome["citation_check"] = friday_run.citation_check(run_id, outcome, req, root)
        extraction.append_outcome(run_id, outcome, root)
    friday_run._save(inbox.run_dir(run_id, root) / reconcile.RUN_JSON,
                     {"run_id": run_id, "manual": True, "started_at": started, "ended_at": _now(), "failure": crash,
                      "crash": crash, "unrecorded": unrecorded, "limit": None, "orchestrator_cost_usd": None,
                      "spent_usd": outcome.get("cost_usd") if outcome.get("cost_usd") is not None
                      else of.EXTRACTION_BUDGET_USD,
                      "ceiling_usd": of.EXTRACTION_BUDGET_USD, "prompt_sha256": None, "model": of.MODEL})
    report.write(run_id, root)
    rec = reconcile.reconcile_run(run_id, root)
    print("%s: %s, %s (%s). Next: python tools/accept_run.py %s" % (
        run_id, item.key, outcome.get("status") if crash is None else "crashed", rec["status"], run_id))
    if interrupt is not None:
        raise interrupt
    return 0 if outcome.get("status") == "extracted" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
