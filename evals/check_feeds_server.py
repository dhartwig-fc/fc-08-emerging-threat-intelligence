"""
Pin the feeds MCP server's invariants: feeds_list_new and feeds_fetch (slice 2, sub-project A).

Usage:
    python evals/check_feeds_server.py
    python evals/check_feeds_server.py --mutate no-ledger-filter  # every listed item reported new
    python evals/check_feeds_server.py --mutate relist            # a listing fetched twice in one run
    python evals/check_feeds_server.py --mutate refetch           # a pinned document fetched again
    python evals/check_feeds_server.py --mutate unlisted-fetch    # fetch reaches an item another run listed
    python evals/check_feeds_server.py --mutate quiet-layout      # a layout change reported as "0 new items"
    python evals/check_feeds_server.py --mutate swap-http-get     # the server's fetch is not feeds.http.get
    python evals/check_feeds_server.py --mutate narrow-transport  # feeds.http.get turns only URLError into FetchRefused
    python evals/check_feeds_server.py --mutate quiet-no-text     # a document with no text is reported as paged

WHAT IT HOLDS (spec section 1, and definition-of-done box 2 for the two tools A builds):
  newness      an item in the seen-items ledger is never reported new;
  once         a source's listing is requested once per run, a document once per item;
  allowlist    every request goes to a URL the SERVER chose (a listing URL, or a URL this run listed)
               with the SOURCE's hosts and types, never anything a tool argument carries; extra
               arguments such as a url are refused by the input model;
  inbox only   every file the tools write is inside inbox/<run_id>/, and the repository's git status
               is the same before and after;
  loud         a layout change or an unreachable source is a "Failed:" line and a status in
               items.json, never "no new items" -- including a source that drops the connection,
               proved END TO END through the real feeds.http.get against a local socket (no network);
  real fetch   an unmutated server's HTTP_GET IS feeds.http.get, so the allowlisted fetch the other
               checks' stub stands in for is the one the server really calls;
  citable      a fetched document with no text is pinned but recorded as "no text; not citable", and
               one that cannot be paged at all (bytes labelled PDF that are not a PDF) is pinned and
               reported NOT PAGED, with its page_error recorded.

HOW. The server's module attributes HTTP_GET, INBOX_ROOT and SEEN_PATH are swapped for a stub that
serves the committed listing snapshots and a temporary inbox and ledger; the tool functions are
called directly. Cold: no network. The redirect and size rules of the real fetch are feeds/http.py's,
pinned by evals/check_feed_adapters.py.

NOT A VACUOUS PASS. Each --mutate rewrites the server's SOURCE in memory (narrow-transport rewrites
feeds/http.py's instead); at least one check must fail.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import http as fh, ledger  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, SOURCES  # noqa: E402

SERVER = ROOT / "mcp_server" / "feeds_server.py"
HTTP_PY = ROOT / "feeds" / "http.py"
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
    "relist": ("    if source in state[\"sources\"]:\n", "    if False:\n"),
    "refetch": ("    if item.get(\"document\"):\n", "    if False:\n"),
    "unlisted-fetch": ("    state = inbox.load(run_id, INBOX_ROOT)\n    item = inbox.find_item(state, item_key)\n",
                       "    state = inbox.load(run_id, INBOX_ROOT)\n    item = inbox.find_item(state, item_key) or "
                       "inbox.find_item(inbox.load(%r, INBOX_ROOT), item_key)\n" % OTHER_RUN),
    "quiet-layout": ('        return "Failed: layout changed: %s. The listing is saved in the inbox. This is not \'0 new '
                     'items\'." % exc\n', '        return "No new items."\n'),
    "swap-http-get": ("HTTP_GET = feeds_http.get\n", "HTTP_GET = __import__('urllib.request').request.urlopen\n"),
    "quiet-no-text": ("        if text_pages == 0:", "        if False:"),
}
# Mutations of feeds/http.py, installed as feeds.http before the server is loaded.
HTTP_MUTATIONS = {
    "narrow-transport": ("    except (OSError, http.client.HTTPException) as exc:\n", "    except () as exc:\n"),
}


def _install_http(mutation) -> None:
    source = HTTP_PY.read_text(encoding="utf-8")
    old, new = HTTP_MUTATIONS[mutation]
    if source.count(old) != 1:
        raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, HTTP_PY))
    module = types.ModuleType("feeds.http")
    module.__file__ = str(HTTP_PY)
    sys.modules["feeds.http"] = module
    exec(compile(source.replace(old, new), str(HTTP_PY), "exec"), module.__dict__)
    importlib.import_module("feeds").http = module


def load_server(mutation) -> types.ModuleType:
    source = SERVER.read_text(encoding="utf-8")
    if mutation in HTTP_MUTATIONS:
        _install_http(mutation)
    elif mutation:
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


def _closing_server():
    """A local socket server that accepts a connection and closes it without a response: the
    RemoteDisconnected a government site gives when it drops us, with no network involved."""
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(65536)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads, block_on_close = True, False

    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def dropped_connection_check(fs, real_get, tmp: Path) -> tuple:
    """list_new over the REAL feeds.http.get, pointed at a local server that drops the connection."""
    http_mod = importlib.import_module("feeds.http")
    saved = (http_mod.ALLOWED_SCHEMES, http_mod.REQUEST_GAP_SECONDS, http_mod.TIMEOUT_SECONDS, fs.HTTP_GET)
    server = _closing_server()
    netloc = "127.0.0.1:%d" % server.server_address[1]
    requested = []

    def via_local(url, *, allowed_hosts, allowed_types, max_bytes):
        # The server chose `url` and its hosts; only the address changes, to the local socket.
        requested.append(url)
        return real_get("http://%s/listing" % netloc, allowed_hosts=frozenset({netloc}),
                        allowed_types=allowed_types, max_bytes=max_bytes)

    run = "feeds-2026-10-04-cccccc"
    try:
        http_mod.ALLOWED_SCHEMES, http_mod.REQUEST_GAP_SECONDS, http_mod.TIMEOUT_SECONDS = ("http",), 0, 2
        fs.HTTP_GET = via_local
        os.environ[fs.RUN_ENV] = run
        try:
            said = asyncio.run(fs.list_new(fs.ListNewInput(source="ofac")))
        except Exception as exc:  # an escaping failure is the defect: the check fails, not the guard
            said = "ESCAPED %s: %s" % (type(exc).__name__, exc)
        path = tmp / "inbox" / run / "items.json"
        st = json.loads(path.read_text(encoding="utf-8"))["sources"].get("ofac", {}) if path.exists() else {}
        again = said.startswith("ESCAPED") or asyncio.run(fs.list_new(fs.ListNewInput(source="ofac")))
    finally:
        http_mod.ALLOWED_SCHEMES, http_mod.REQUEST_GAP_SECONDS, http_mod.TIMEOUT_SECONDS, fs.HTTP_GET = saved
        server.shutdown()
        server.server_close()
    ok = (said.startswith("Failed:") and "RemoteDisconnected" in said and st.get("status") == "unreachable"
          and "RemoteDisconnected" in (st.get("error") or "") and requested == [SOURCES["ofac"].listing_url]
          and isinstance(again, str) and again.startswith("Rejected") and len(requested) == 1)
    return (ok, "a dropped connection (RemoteDisconnected, not a URLError) through the REAL feeds.http.get is "
            "recorded as unreachable, and the source is not listed again in the run", said[:120])


def checks(fs) -> list:
    out = []
    # An exported FEEDS_CATALOGUE/FEEDS_CATALOGUE_BATCH must not turn these live-mode checks into an eval run.
    os.environ.pop(fs.CATALOGUE_ENV, None)
    os.environ.pop(fs.BATCH_ENV, None)
    real_get = fs.HTTP_GET
    out.append((real_get is importlib.import_module("feeds.http").get,
                "the unmutated server's HTTP_GET is feeds.http.get, the allowlisted fetch",
                getattr(real_get, "__module__", "?") + "." + getattr(real_get, "__name__", "?")))
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
        out.append((said.startswith("Rejected") and not stub.calls and not (tmp / "inbox").exists(),
                    "with no run identity nothing is requested or written", said[:90]))
        os.environ[fs.RUN_ENV] = RUN + "\n"
        said = list_new("ofsi")
        out.append((said.startswith("Rejected") and not stub.calls and not (tmp / "inbox").exists(),
                    "a run identity with a trailing newline is malformed: nothing is requested or written",
                    said[:90]))

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
        out.append((said.startswith("Rejected") and len(stub.calls) == n,
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
        out.append((said.startswith("Rejected") and len(stub.calls) == n + 2,
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
        out.append((said.startswith("Rejected") and len(stub.calls) == n,
                    "an item another run listed cannot be fetched in this run", said[:90]))

        stub.routes[SOURCES["fincen"].listing_url] = ("text/html", snap("fincen_advisories.html"))
        os.environ[fs.RUN_ENV] = "feeds-2026-10-03-aaaaaa"
        list_new("fincen")
        fin = SOURCES["fincen"].parse(snap("fincen_advisories.html"))[0]
        said = fetch(fin.key)
        out.append(("advisory.pdf" in said and "https://www.fincen.gov/system/files/2026-06/advisory.pdf" in said,
                    "a landing page's linked PDFs are reported (absolute), not fetched", said[-110:]))

        fins = SOURCES["fincen"].parse(snap("fincen_advisories.html"))
        fin_state = lambda: {it["key"]: it for it in json.loads(  # noqa: E731
            (tmp / "inbox" / "feeds-2026-10-03-aaaaaa" / "items.json").read_text(encoding="utf-8"))["sources"]["fincen"]["items"]}
        stub.routes[fins[1].url] = ("text/html", b"<html><body><nav><a href='/'>Home</a> <a href='/a'>Advisories</a>"
                                                 b"</nav></body></html>")
        said = fetch(fins[1].key)
        doc = fin_state()[fins[1].key]["document"]
        out.append((said.startswith("Fetched") and "no text; not citable" in said and "NOT PAGED" not in said
                    and doc["page_error"] == "no text; not citable" and doc["text_pages"] == 0
                    and (tmp / "inbox" / "feeds-2026-10-03-aaaaaa" / doc["path"]).exists(),
                    "a page whose only content is navigation is pinned, recorded and reported as no text; not citable",
                    said[-80:]))
        stub.routes[fins[2].url] = ("application/pdf", b"%PDF-not really a PDF, only labelled as one")
        said = fetch(fins[2].key)
        doc = fin_state()[fins[2].key]["document"]
        out.append((said.startswith("Fetched") and "NOT PAGED" in said and bool(doc["page_error"])
                    and doc["page_error"] != "no text; not citable" and doc["path"] == "docs/%s.pdf" % doc["sha256"]
                    and (tmp / "inbox" / "feeds-2026-10-03-aaaaaa" / doc["path"]).exists(),
                    "bytes labelled application/pdf that are not a PDF are pinned, page_error is recorded, and the "
                    "reply says NOT PAGED", said[-100:]))

        try:
            fs.FetchInput(item_key=fin.key, url="https://evil.invalid/x")
            refused = False
        except Exception:
            refused = True
        out.append((refused, "a url argument is refused by the input model: the agent never supplies a URL", ""))

        out.append(dropped_connection_check(fs, real_get, tmp))

        written = [str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file()]
        out.append((all(w == "seen.json" or w.startswith("inbox/feeds-") for w in written),
                    "every file written is inside the temporary inbox", "%d files" % len(written)))
    os.environ.pop(fs.RUN_ENV, None)
    out.append((git_status() == before, "the repository's git status is unchanged", ""))

    tools = {t.name: t for t in asyncio.run(fs.mcp.list_tools())}
    hint = lambda t, a, b: getattr(t.annotations, a, getattr(t.annotations, b, None))  # noqa: E731
    ro = {n: hint(t, "readOnlyHint", "read_only_hint") for n, t in tools.items()}
    ow = {n: hint(t, "openWorldHint", "open_world_hint") for n, t in tools.items()}
    out.append((sorted(tools) == ["feeds_extract", "feeds_fetch", "feeds_list_new", "feeds_read_page", "feeds_triage"]
                and ro == {"feeds_extract": False, "feeds_fetch": False, "feeds_list_new": False,
                           "feeds_read_page": True, "feeds_triage": False}
                and ow["feeds_fetch"] is True and ow["feeds_list_new"] is True and ow["feeds_extract"] is True,
                "a live server exposes exactly its five tools; only feeds_read_page is annotated read-only, and the "
                "three that reach the network are open-world", sorted(tools)))
    # Slice 2 C: a server the eval runner starts (FEEDS_CATALOGUE set) must not even LIST feeds_extract, so
    # B's triage-only sessions keep the four tools they were measured with.
    os.environ[fs.CATALOGUE_ENV] = str(ROOT / "evals" / "feeds" / "catalogue.json")
    try:
        eval_tools = sorted(t.name for t in asyncio.run(load_server(None).mcp.list_tools()))
    finally:
        os.environ.pop(fs.CATALOGUE_ENV, None)
    out.append((eval_tools == ["feeds_fetch", "feeds_list_new", "feeds_read_page", "feeds_triage"],
                "a server started in eval mode lists the four triage tools and not feeds_extract", eval_tools))
    return out


def main(argv: list) -> int:
    global fh
    ap = argparse.ArgumentParser(description="Pin the feeds MCP server's invariants")
    ap.add_argument("--mutate", choices=sorted(set(MUTATIONS) | set(HTTP_MUTATIONS)), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    fs = load_server(args.mutate)
    fh = sys.modules["feeds.http"]  # the module the server holds (a mutated one under narrow-transport)
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
