"""
Pin the three source adapters (feeds/sources.py) and the allowlisted fetch (feeds/http.py).

Usage:
    python evals/check_feed_adapters.py
    python evals/check_feed_adapters.py --mutate no-marker-fincen   # FinCEN's marker unchecked; a changed page MUST pass
    python evals/check_feed_adapters.py --mutate empty-ok           # OFAC returns [] when nothing parses
    python evals/check_feed_adapters.py --mutate ofsi-link-id       # OFSI keyed by link; a revision MUST collapse
    python evals/check_feed_adapters.py --mutate relative-url       # FinCEN URLs left relative
    python evals/check_feed_adapters.py --mutate ofac-date-optional # an OFAC row without a date is accepted
    python evals/check_feed_adapters.py --mutate follow-redirects   # a redirect off the allowlist is followed
    python evals/check_feed_adapters.py --mutate no-size-cap        # an oversized body is accepted

CONTRACT. Each adapter, run on the committed snapshot of its listing (tests/fixtures/feeds/, fetched
2026-09-26, public government pages), must return the pinned items: count, the digest of their ids in
order, and the first and last item field by field. Each must raise LayoutChanged, never return an
empty list, when its marker is gone, when the marker is there but nothing parses, and when an item
has no date. OFSI keys an item by its Atom <id>, which carries a timestamp, so a revised publication
is a NEW item (a ruling of the sub-project A plan).

TRANSPORT. feeds.http.get refuses a URL off the allowlist, a redirect off the allowlist BEFORE any
request reaches the other host, a body over the size cap, and a content type not allowed. Checked
against a local HTTP server on 127.0.0.1, so it stays cold.

NOT A VACUOUS PASS. Each --mutate rewrites one module's SOURCE in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import importlib
import re
import socketserver
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.model import LayoutChanged  # noqa: E402

SOURCES_PY = ROOT / "feeds" / "sources.py"
HTTP_PY = ROOT / "feeds" / "http.py"
FIX = ROOT / "tests" / "fixtures" / "feeds"
SNAPSHOTS = {"ofsi": ("ofsi.atom", "b63d891e06aceaaf42021a4637573ad16cedc7c6b84ab7082332903b4b6d31c9"),
             "fincen": ("fincen_advisories.html", "295483b8950e51cd839f1b0198c6b20d8a802180b55487ee6551412bcbd3b10b"),
             "ofac": ("ofac_recent_actions.html", "9b2cdcdc61a65f954e3157d216ce154aa3ad1fddfea810f97d78ad6bb9f0e669")}
EXPECTED = {
    "ofsi": {"count": 20, "ids": "db1898e619e089de7649a2443ffbe1ca707fa31d623ebae87729f76e5916067e",
             "first": {"item_id": "https://www.gov.uk/government/publications/uk-financial-sanctions-faqs#2026-09-24T08:49:08Z",
                       "title": "Guidance: UK Financial Sanctions FAQs",
                       "url": "https://www.gov.uk/government/publications/uk-financial-sanctions-faqs",
                       "published": "2026-09-24",
                       "summary": "OFSI publishes FAQs providing short-form guidance and technical information on "
                                  "financial sanctions."},
             "last": {"item_id": "https://www.gov.uk/government/publications/russia-sanctions-guidance#2026-05-19T23:01:01Z",
                      "title": "Statutory guidance: Russia sanctions: guidance",
                      "url": "https://www.gov.uk/government/publications/russia-sanctions-guidance",
                      "published": "2026-05-19"}},
    "fincen": {"count": 15, "ids": "b683612db4df8f00f89d80adb2180b3256d556f37ae6be087ef8bbe2f54665c6",
               "first": {"item_id": "fincen-advisory-fin-2026-a002", "title": "FinCEN Advisory FIN-2026-A002",
                         "url": "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2026-a002",
                         "published": "2026-06-05",
                         "summary": "Joint Advisory on Non-Work Authorized Populations and Their Employers and Risks "
                                    "to the Integrity of the U.S. Financial System"},
               "last": {"item_id": "fincen-advisory-fin-2020-a009", "title": "FinCEN Advisory FIN-2020-A009",
                        "url": "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2020-a009",
                        "published": "2020-11-06"}},
    "ofac": {"count": 10, "ids": "a2d84aa40095354bec149d01c732dc24373f92e406777ccede587061ed21b629",
             "first": {"item_id": "20260924", "url": "https://ofac.treasury.gov/recent-actions/20260924",
                       "published": "2026-09-24", "summary": "",
                       "title": "Publication of Regulatory Amendments; Publication of Report for Licensing Activities "
                                "Undertaken Pursuant to the Trade Sanctions Reform and Export Enhancement Act (TSRA)"},
             "last": {"item_id": "20260904", "url": "https://ofac.treasury.gov/recent-actions/20260904",
                      "published": "2026-09-04",
                      "title": "Iran-related Designations; Issuance of Iran-related General License"}},
}
# (label, source, regex, replacement), applied to EVERY match: each must make the adapter raise LayoutChanged.
BREAKS = [
    ("marker gone", "ofsi", r"<feed ", "<rss "),
    ("marker gone", "fincen", r'id="view-title-table-column"', 'id="view-renamed"'),
    ("marker gone", "ofac", r"view-recent-actions-search", "view-renamed"),
    ("nothing parses", "ofsi", r"(?s)<entry>.*</entry>", ""),
    ("nothing parses", "fincen", r'href="/resources/advisories/', 'href="/elsewhere/'),
    ("nothing parses", "ofac", r"search-result views-row", "search-result"),
    ("an item without a date", "ofsi", r"<updated>2026-09-24T08:49:08Z</updated>\s*<link", "<updated>yesterday</updated><link"),
    ("an item without a date", "fincen", r'datetime="2026-06-05T12:00:00Z"', ""),
    ("an item without a date", "ofac", r"September 24, 2026 -", "24 Sep -"),
]

MUTATIONS = {
    "no-marker-fincen": (SOURCES_PY, 'raise LayoutChanged("fincen: the listing table (th#view-title-table-column) is missing")',
                         "pass"),
    "empty-ok": (SOURCES_PY, 'raise LayoutChanged("ofac: the view is present but no views-row parsed")', "pass"),
    "ofsi-link-id": (SOURCES_PY, 'FeedItem("ofsi", eid.strip(),', 'FeedItem("ofsi", link.get("href"),'),
    "relative-url": (SOURCES_PY, 'urljoin(FINCEN_BASE, row["href"])', 'row["href"]'),
    "ofac-date-optional": (SOURCES_PY, 'if not row["href"] or not row["date"]:', 'if not row["href"]:'),
    "follow-redirects": (HTTP_PY, "        _check_host(newurl, self.allowed_hosts)\n", ""),
    "no-size-cap": (HTTP_PY, "    if len(body) > max_bytes:\n", "    if False:\n"),
}


def load(name: str, path: Path, mutation) -> types.ModuleType:
    source = path.read_text(encoding="utf-8")
    if mutation and MUTATIONS[mutation][0] == path:
        old, new = MUTATIONS[mutation][1:]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
        source = source.replace(old, new)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    package, _, leaf = name.rpartition(".")
    setattr(importlib.import_module(package), leaf, module)
    return module


def raw(source: str) -> bytes:
    return (FIX / SNAPSHOTS[source][0]).read_bytes()


def adapter_checks(sources) -> list:
    out = []
    for name, (fname, sha) in sorted(SNAPSHOTS.items()):
        body = raw(name)
        out.append((hashlib.sha256(body).hexdigest() == sha, "%s: the snapshot %s is the pinned bytes" % (name, fname), ""))
        try:
            items = sources.SOURCES[name].parse(body)
        except LayoutChanged as exc:
            out.append((False, "%s: the snapshot parses" % name, str(exc)))
            continue
        want = EXPECTED[name]
        ids = hashlib.sha256("\n".join(i.item_id for i in items).encode("utf-8")).hexdigest()
        out.append((len(items) == want["count"] and ids == want["ids"],
                    "%s: %d items, ids in the pinned order" % (name, want["count"]), "%d items, ids %s" % (len(items), ids)))
        for end, it in (("first", items[0]), ("last", items[-1])):
            got = {k: getattr(it, k) for k in want[end]}
            out.append((got == want[end], "%s: the %s item is the pinned one, field by field" % (name, end),
                        "" if got == want[end] else "got %s" % got))
        hosts = sources.SOURCES[name].hosts
        off = [i.url for i in items if not re.match(r"^https://(%s)/" % "|".join(map(re.escape, hosts)), i.url)]
        out.append((not off and len({i.key for i in items}) == len(items),
                    "%s: every item URL is absolute on the source's hosts, and keys are unique" % name, "off: %s" % off[:2]))
    for label, name, pattern, repl in BREAKS:
        broken, n = re.subn(pattern, repl, raw(name).decode("utf-8"))
        try:
            got = sources.SOURCES[name].parse(broken.encode("utf-8"))
            ok, detail = False, "returned %d items" % len(got)
        except LayoutChanged as exc:
            ok, detail = True, str(exc)
        out.append((n >= 1 and ok, "%s: %s raises LayoutChanged, never an empty or partial list" % (name, label), detail))
    text = raw("ofsi").decode("utf-8")
    first = re.search(r"(?s)<entry>.*?</entry>", text).group(0)
    revised = first.replace("#2026-09-24T08:49:08Z</id>", "#2026-09-25T10:00:00Z</id>").replace(
        "<updated>2026-09-24T08:49:08Z</updated>", "<updated>2026-09-25T10:00:00Z</updated>")
    items = sources.parse_ofsi(text.replace(first, revised + first, 1).encode("utf-8"))
    out.append((len(items) == 21 and len({i.key for i in items}) == 21 and items[0].url == items[1].url,
                "ofsi: a revised publication (same link, new <id> timestamp) is a new item", "%d items" % len(items)))
    return out


def transport_checks(fh) -> list:
    fh.REQUEST_GAP_SECONDS = 0
    hosts_seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            hosts_seen.append(self.headers.get("Host", "").split(":")[0])
            port = self.server.server_address[1]
            if self.path == "/away":
                self.send_response(302)
                self.send_header("Location", "http://localhost:%d/doc" % port)
                self.end_headers()
                return
            if self.path == "/home":
                self.send_response(302)
                self.send_header("Location", "/doc")
                self.end_headers()
                return
            ctype, body = {"/big": ("text/html", b"x" * 2000), "/zip": ("application/zip", b"PK")}.get(
                self.path, ("text/html; charset=utf-8", b"<p>ok</p>"))
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    allowed, types_ = frozenset({"127.0.0.1"}), frozenset({"text/html", "application/pdf"})

    def get(path: str, host: str = "127.0.0.1"):
        try:
            got = fh.get("http://%s:%d%s" % (host, port, path), allowed_hosts=allowed, allowed_types=types_, max_bytes=1000)
            return "OK", got
        except fh.FetchRefused as exc:
            return "REFUSED", str(exc)

    out = []
    try:
        s, got = get("/doc")
        out.append((s == "OK" and got.body == b"<p>ok</p>" and got.content_type == "text/html",
                    "an allowlisted URL is fetched, with its content type", s))
        s, got = get("/home")
        out.append((s == "OK" and got.final_url.endswith("/doc"), "a redirect within the allowlist is followed", s))
        del hosts_seen[:]
        s, why = get("/away")
        out.append((s == "REFUSED" and "localhost" not in hosts_seen,
                    "a redirect off the allowlist is refused before any request reaches the other host",
                    "%s; hosts requested %s" % (s, hosts_seen)))
        del hosts_seen[:]
        s, why = get("/doc", host="localhost")
        out.append((s == "REFUSED" and not hosts_seen, "a URL off the allowlist is refused without a request", s))
        s, why = get("/big")
        out.append((s == "REFUSED" and "larger" in str(why), "a body over the size cap is refused", str(why)[-60:]))
        s, why = get("/zip")
        out.append((s == "REFUSED" and "application/zip" in str(why), "a content type not allowed is refused", str(why)[-60:]))
    finally:
        server.shutdown()
        server.server_close()
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the feed adapters and the allowlisted fetch")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    fh = load("feeds.http", HTTP_PY, args.mutate)
    sources = load("feeds.sources", SOURCES_PY, args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in adapter_checks(sources) + transport_checks(fh):
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
