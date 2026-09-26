"""
Pin the feeds MCP server's invariants: feeds_list_new and feeds_fetch (slice 2, sub-project A).

Usage:
    python evals/check_feeds_server.py
    python evals/check_feeds_server.py --mutate no-ledger-filter  # every listed item reported new
    python evals/check_feeds_server.py --mutate relist            # a listing fetched twice in one run
    python evals/check_feeds_server.py --mutate refetch           # a pinned document fetched again
    python evals/check_feeds_server.py --mutate unlisted-fetch    # fetch reaches an item another run listed
    python evals/check_feeds_server.py --mutate quiet-layout      # a layout change reported as "0 new items"

WHAT IT HOLDS (spec section 1, and definition-of-done box 2 for the two tools A builds):
  newness      an item in the seen-items ledger is never reported new;
  once         a source's listing is requested once per run, a document once per item;
  allowlist    every request goes to a URL the SERVER chose (a listing URL, or a URL this run listed)
               with the SOURCE's hosts and types, never anything a tool argument carries; extra
               arguments such as a url are refused by the input model;
  inbox only   every file the tools write is inside inbox/<run_id>/, and the repository's git status
               is the same before and after;
  loud         a layout change or an unreachable source is a "Failed:" line and a status in
               items.json, never "no new items".

HOW. The server's module attributes HTTP_GET, INBOX_ROOT and SEEN_PATH are swapped for a stub that
serves the committed listing snapshots and a temporary inbox and ledger; the tool functions are
called directly. Cold: no network. The redirect and size rules of the real fetch are feeds/http.py's,
pinned by evals/check_feed_adapters.py.

NOT A VACUOUS PASS. Each --mutate rewrites the server's SOURCE in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import http as fh, ledger  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, SOURCES  # noqa: E402

SERVER = ROOT / "mcp_server" / "feeds_server.py"
FIX = ROOT / "tests" / "fixtures"
RUN = "feeds-2026-10-02-abc123"
OTHER_RUN = "feeds-2026-10-02-def456"
OFSI_DOC_URL = "https://www.gov.uk/government/publications/uk-financial-sanctions-faqs"
FINCEN_DOC_URL = "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2026-a002"
FINCEN_DOC = (b"<html><body><main><h1>FinCEN Advisory FIN-2026-A002</h1><p>Joint Advisory on synthetic risks.</p>"
              b"<a href='/system/files/2026-06/advisory.pdf'>Advisory (PDF)</a></main></body></html>")

MUTATIONS = {
    "no-ledger-filter": ("    new = [it for it in items if (it.source, it.item_id) not in seen]\n",
                         "    new = list(items)\n"),
    "relist": ("    if params.source in state[\"sources\"]:\n", "    if False:\n"),
    "refetch": ("    if item.get(\"document\"):\n", "    if False:\n"),
    "unlisted-fetch": ("    state = inbox.load(run_id, INBOX_ROOT)\n    item = inbox.find_item(state, params.item_key)\n",
                       "    state = inbox.load(run_id, INBOX_ROOT)\n    item = inbox.find_item(state, params.item_key) or "
                       "inbox.find_item(inbox.load(%r, INBOX_ROOT), params.item_key)\n" % OTHER_RUN),
    "quiet-layout": ('        return "Failed: layout changed: %s. The listing is saved in the inbox. This is not \'0 new '
                     'items\'." % exc\n', '        return "No new items."\n'),
}


def load_server(mutation) -> types.ModuleType:
    source = SERVER.read_text(encoding="utf-8")
    if mutation:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, SERVER))
        source = source.replace(old, new)
    module = types.ModuleType("feeds_server_under_test")
    module.__file__ = str(SERVER)
    exec(compile(source, str(SERVER), "exec"), module.__dict__)
    return module


class Stub:
    """Stands in for feeds.http.get: serves fixed bytes by URL and records every request."""

    def __init__(self, routes: dict) -> None:
        self.routes, self.calls = routes, []

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append({"url": url, "hosts": allowed_hosts, "types": allowed_types})
        route = self.routes.get(url)
        if isinstance(route, Exception):
            raise route
        if route is None:
            raise fh.FetchRefused("no route for %s" % url)
        return fh.Fetched(url, url, route[0], route[1])


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


def checks(fs) -> list:
    out = []
    snap = lambda f: (FIX / "feeds" / f).read_bytes()  # noqa: E731
    broken_ofac = snap("ofac_recent_actions.html").replace(b"view-recent-actions-search", b"view-renamed")
    stub = Stub({SOURCES["ofsi"].listing_url: ("application/atom+xml", snap("ofsi.atom")),
                 SOURCES["fincen"].listing_url: ("text/html", snap("fincen_advisories.html")),
                 SOURCES["ofac"].listing_url: ("text/html", broken_ofac),
                 OFSI_DOC_URL: ("text/html", (FIX / "html" / "ofsi_uk_financial_sanctions_faqs.html").read_bytes()),
                 FINCEN_DOC_URL: ("text/html", FINCEN_DOC)})
    before = git_status()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fs.HTTP_GET, fs.INBOX_ROOT, fs.SEEN_PATH = stub, tmp / "inbox", tmp / "seen.json"
        fs.SEEN_PATH.write_text(ledger.dump([]), encoding="utf-8")

        def list_new(source):
            return asyncio.run(fs.list_new(fs.ListNewInput(source=source)))

        def fetch(key):
            return asyncio.run(fs.fetch(fs.FetchInput(item_key=key)))

        os.environ.pop(fs.RUN_ENV, None)
        said = list_new("ofsi")
        out.append((said.startswith("Refused") and not stub.calls and not (tmp / "inbox").exists(),
                    "with no run identity nothing is requested or written", said[:90]))

        # A ledger that has already decided the first five OFSI items.
        ofsi_items = SOURCES["ofsi"].parse(snap("ofsi.atom"))
        fs.SEEN_PATH.write_text(ledger.dump([{"source": "ofsi", "item_id": i.item_id, "decision": "drop",
                                              "first_seen_run": "feeds-2026-09-25-000000",
                                              "decided_on": "2026-09-25"} for i in ofsi_items[:5]]), encoding="utf-8")
        os.environ[fs.RUN_ENV] = RUN
        said = list_new("ofsi")
        state = json.loads((tmp / "inbox" / RUN / "items.json").read_text(encoding="utf-8"))
        entry = state["sources"]["ofsi"]
        keys = [it["key"] for it in entry["items"]]
        out.append((said.startswith("15 new of 20 listed") and entry["listed"] == 20 and entry["already_seen"] == 5
                    and keys == [i.key for i in ofsi_items[5:]],
                    "an item in the ledger is never new: 15 of 20 OFSI items reported, the decided 5 withheld",
                    said.splitlines()[0]))
        out.append(((tmp / "inbox" / RUN / "listings" / "ofsi.atom").read_bytes() == snap("ofsi.atom")
                    and len(entry["listing_sha256"]) == 64, "the raw listing is pinned in the inbox", ""))
        n = len(stub.calls)
        said = list_new("ofsi")
        out.append((said.startswith("Refused") and len(stub.calls) == n,
                    "a second listing of the same source in one run is refused without a request", said[:90]))

        said = list_new("ofac")
        st = json.loads((tmp / "inbox" / RUN / "items.json").read_text(encoding="utf-8"))["sources"]["ofac"]
        out.append((said.startswith("Failed: layout changed") and st["status"] == "layout_changed" and not st["items"],
                    "a changed layout is a loud failure with its status recorded, not '0 new items'", said[:90]))

        stub.routes[SOURCES["fincen"].listing_url] = fh.FetchRefused("connection refused")
        said = list_new("fincen")
        st = json.loads((tmp / "inbox" / RUN / "items.json").read_text(encoding="utf-8"))["sources"]["fincen"]
        out.append((said.startswith("Failed:") and st["status"] == "unreachable", "an unreachable source is a loud "
                    "failure with its status recorded", said[:90]))

        said = fetch("ofsi:0000000000000000")
        out.append((said.startswith("Refused") and len(stub.calls) == n + 2,
                    "fetching a key this run did not list is refused without a request", said[:90]))

        # The FAQ page is the feed's FIRST item, which the ledger above decided; list it in a fresh run.
        os.environ[fs.RUN_ENV] = OTHER_RUN
        fs.SEEN_PATH.write_text(ledger.dump([]), encoding="utf-8")
        list_new("ofsi")
        faq = ofsi_items[0]
        n = len(stub.calls)
        said = fetch(faq.key)
        doc = json.loads((tmp / "inbox" / OTHER_RUN / "items.json").read_text(encoding="utf-8"))["sources"]["ofsi"]
        doc = next(it for it in doc["items"] if it["key"] == faq.key)["document"]
        pinned = tmp / "inbox" / OTHER_RUN / doc["path"]
        last = stub.calls[-1]
        out.append((said.startswith("Fetched") and len(stub.calls) == n + 1 and last["url"] == OFSI_DOC_URL
                    and last["hosts"] == SOURCES["ofsi"].hosts and last["types"] == DOCUMENT_TYPES,
                    "fetch requests the item's own listed URL with its source's hosts and the document types",
                    said[:120]))
        out.append((pinned.exists() and hashlib.sha256(pinned.read_bytes()).hexdigest() == doc["sha256"]
                    and doc["path"] == "docs/%s.html" % doc["sha256"] and doc["pages"] == 2 and doc["text_pages"] == 2,
                    "the document is pinned under its own sha256 and paged by PageIndex.from_html (2 pages)",
                    "%s pages=%s" % (doc["path"], doc["pages"])))
        said = fetch(faq.key)
        out.append((said.startswith("Already fetched") and len(stub.calls) == n + 1,
                    "a second fetch of the same item makes no request", said[:60]))

        os.environ[fs.RUN_ENV] = RUN
        other_key = faq.key  # listed in OTHER_RUN only: in RUN it was withheld as already decided
        n = len(stub.calls)
        said = fetch(other_key)
        out.append((said.startswith("Refused") and len(stub.calls) == n,
                    "an item another run listed cannot be fetched in this run", said[:90]))

        stub.routes[SOURCES["fincen"].listing_url] = ("text/html", snap("fincen_advisories.html"))
        os.environ[fs.RUN_ENV] = "feeds-2026-10-03-aaaaaa"
        list_new("fincen")
        fin = SOURCES["fincen"].parse(snap("fincen_advisories.html"))[0]
        said = fetch(fin.key)
        out.append(("advisory.pdf" in said and "https://www.fincen.gov/system/files/2026-06/advisory.pdf" in said,
                    "a landing page's linked PDFs are reported (absolute), not fetched", said[-110:]))

        try:
            fs.FetchInput(item_key=fin.key, url="https://evil.invalid/x")
            refused = False
        except Exception:
            refused = True
        out.append((refused, "a url argument is refused by the input model: the agent never supplies a URL", ""))

        written = [str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file()]
        out.append((all(w == "seen.json" or w.startswith("inbox/feeds-") for w in written),
                    "every file written is inside the temporary inbox", "%d files" % len(written)))
    os.environ.pop(fs.RUN_ENV, None)
    out.append((git_status() == before, "the repository's git status is unchanged", ""))

    tools = {t.name: t for t in asyncio.run(fs.mcp.list_tools())}
    hint = lambda t, a, b: getattr(t.annotations, a, getattr(t.annotations, b, None))  # noqa: E731
    out.append((sorted(tools) == ["feeds_fetch", "feeds_list_new"]
                and all(hint(t, "readOnlyHint", "read_only_hint") is False
                        and hint(t, "openWorldHint", "open_world_hint") is True for t in tools.values()),
                "the server exposes exactly feeds_list_new and feeds_fetch, both annotated as writing, open-world",
                sorted(tools)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the feeds MCP server's invariants")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    fs = load_server(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(fs):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
