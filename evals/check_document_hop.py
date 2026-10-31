"""
Pin the one-hop document rule (spec 2026-10-31 §1): a source that declares document_via reaches its PDF through
exactly one same-host page under that prefix; nothing else changes for a source that declares none.

Usage:
    python evals/check_document_hop.py
    python evals/check_document_hop.py --mutate via-first-of-many  # two resource links: the first is followed
    python evals/check_document_hop.py --mutate via-any-host       # a resource link off the source's hosts is followed
    python evals/check_document_hop.py --mutate via-pdf-off-hosts  # the resource page's PDFs are not host-filtered
    python evals/check_document_hop.py --mutate no-encoding        # the PDF URL is fetched with its raw spaces
    python evals/check_document_hop.py --mutate hop-undeclared     # a source with no document_via hops anyway

WHAT IT HOLDS, on the recorded Wolfsberg pages (tests/fixtures/feeds/, fetched 2026-10-31):
  listed     linked_pages() on the item page finds exactly its one /resources/ page;
  hop        request() fetches the resource page on the source's HOSTS as text/html, pins it, then fetches the ONE
             PDF on its DOCUMENT hosts, percent-encoded, and records the hop (url, sha256, path) on the request;
  refusals   two resource links are refused before any fetch; a resource page whose only PDFs are off the
             document hosts is refused and recorded; a resource link on another host is not followed;
  undeclared a source with no document_via never hops, whatever its page links.
Cold: the fetches are a stub; nothing touches the network.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from check_document_pages import tiny_pdf  # noqa: E402
from feeds import http as feeds_http, inbox  # noqa: E402
from feeds import triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem  # noqa: E402

EXTRACTION = ROOT / "feeds" / "extraction.py"
FIX = ROOT / "tests" / "fixtures" / "feeds"
ITEM_URL = "https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach"
RES_URL = "https://wolfsberg-group.org/resources/rba/205"
PDF_ENCODED = ("https://db.wolfsberg-group.org/assets/6c32b34b-bc02-4e8b-9b3f-f36e9bd109c3/"
               "Wolfsberg%20Group%20-%20Risk%20Based%20Approach%20Guidance%20_June2026.pdf")
QUOTE = "The risk-based approach (RBA) has long been the cornerstone of effective financial crime risk management."
RUN = "feeds-2026-10-31-aaa111"
MUTATIONS = {
    "via-first-of-many": (EXTRACTION, 'return ("via" if len(via) == 1 else "ambiguous_via"), via, ignored',
                          'return "via", via[:1], ignored'),
    "via-any-host": (EXTRACTION, "if src.document_via and _on_hosts(u, src.hosts)]", "if src.document_via]"),
    "via-pdf-off-hosts": (EXTRACTION, "if _on_hosts(u, src.document_hosts)]\n        if len(pdfs) != 1:",
                          "]\n        if len(pdfs) != 1:"),
    "no-encoding": (EXTRACTION, "urls = [_encoded(pdfs[0])]", "urls = [pdfs[0]]"),
    "hop-undeclared": (EXTRACTION, "if src.document_via and _on_hosts(u, src.hosts)]", "if _on_hosts(u, src.hosts)]"),
}


def load(name: str, path: Path, mutation) -> types.ModuleType:
    source = path.read_text(encoding="utf-8")
    if mutation in MUTATIONS and MUTATIONS[mutation][0] == path:
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


class Stub:
    """http_get: serves the recorded resource page, then a one-page PDF; records every call."""

    def __init__(self, resource: bytes, refuse: bool = False):
        self.calls, self.resource, self.refuse = [], resource, refuse

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append((url, frozenset(allowed_hosts), frozenset(allowed_types)))
        if "text/html" in allowed_types and self.refuse:
            raise feeds_http.FetchRefused("connection refused")
        if "text/html" in allowed_types:
            return types.SimpleNamespace(body=self.resource, content_type="text/html", final_url=url)
        return types.SimpleNamespace(body=tiny_pdf(["Wolfsberg Group guidance on the risk-based approach."]),
                                     content_type="application/pdf", final_url=url)


def run_item(ex, src_mod, tmp: Path, source: str, page: bytes, linked_pages: list, resource: bytes, run: str = RUN, refuse: bool = False):
    """One listed, pinned, triaged-relevant item; returns (request() result, stub, the request line)."""
    it = FeedItem(source, "rba", "Guidance on the Risk-Based Approach", ITEM_URL, "2026-06-23")
    sha = hashlib.sha256(page).hexdigest()
    rel = inbox.write_file(run, "docs/%s.html" % sha, page, tmp)
    doc = {"path": rel, "sha256": sha, "content_type": "text/html", "bytes": len(page), "final_url": ITEM_URL,
           "fetched_at": "2026-10-31T09:00:00Z", "pages": 1, "text_pages": 1, "page_error": None,
           "linked_pdfs": src_mod.linked_pdfs(page, ITEM_URL), "linked_pages": linked_pages}
    inbox.save(run, {"run_id": run, "sources": {source: {"status": "ok", "items": [dict(it.to_json(), document=doc)]}}}, tmp)
    ok, msg = feeds_triage.decide(run, it.key, feeds_triage.RELEVANT, "guidance on controls", QUOTE, tmp)
    assert ok, msg
    stub = Stub(resource, refuse)
    result = ex.request(run, it.key, stub, tmp)
    lines = ex.load_requests(run, tmp)
    return result, stub, (lines[0] if lines else None)


def checks(mutation) -> list:
    src_mod = importlib.import_module("feeds.sources")
    ex = load("feeds.extraction", EXTRACTION, mutation)
    item_page = (FIX / "wolfsberg_item_rba.html").read_bytes()
    resource = (FIX / "wolfsberg_resource_rba_205.html").read_bytes()
    wb = src_mod.SOURCES["wolfsberg"]
    out = []
    pages = src_mod.linked_pages(item_page, ITEM_URL, wb.document_via)
    out.append((pages == [RES_URL], "linked_pages finds the item page's one /resources/ page", pages))
    with tempfile.TemporaryDirectory() as t:
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page, pages, resource)
        calls = [(u, sorted(h), sorted(ty)) for u, h, ty in stub.calls]
        out.append((len(stub.calls) == 2 and stub.calls[0][:2] == (RES_URL, wb.hosts)
                    and stub.calls[0][2] == frozenset({"text/html"}),
                    "the resource page is fetched first, on the source's hosts, as HTML", calls))
        out.append((len(stub.calls) == 2 and stub.calls[1][:2] == (PDF_ENCODED, wb.document_hosts),
                    "then the ONE PDF on the document hosts, percent-encoded", calls))
        via = (line or {}).get("via") or {}
        pinned = Path(t) / RUN / via["path"] if via.get("path") else None
        out.append((ok and line["chosen"] == "via" and via.get("sha256") == hashlib.sha256(resource).hexdigest()
                    and via.get("url") == RES_URL and via.get("requested") == RES_URL and not line["error"]
                    and pinned is not None and pinned.is_file() and pinned.read_bytes() == resource,
                    "the request records the hop (requested url, final url, sha256), the pinned page is on disk, "
                    "and no error", msg))
    with tempfile.TemporaryDirectory() as t:
        two = [RES_URL, "https://wolfsberg-group.org/resources/rba/206"]
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page, two, resource)
        out.append((not ok and not stub.calls and msg.startswith(feeds_triage.REJECTED),
                    "two resource links are refused before any fetch", msg))
    with tempfile.TemporaryDirectory() as t:
        off = b'<html><body><a href="https://elsewhere.example/assets/one.pdf">one</a></body></html>'
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page, pages, off)
        out.append((len(stub.calls) == 1 and line is not None and bool(line["error"])
                    and line["error"].startswith(feeds_triage.REJECTED) and " links 0 PDFs " in line["error"]
                    and bool(line.get("via")),
                    "a resource page with no PDF on the document hosts is refused and recorded", msg))
    with tempfile.TemporaryDirectory() as t:
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page, pages, resource, refuse=True)
        out.append((ok and len(stub.calls) == 1 and line is not None and msg.startswith("Failed:")
                    and "resource page could not be fetched" in line["error"] and "via" not in line
                    and line["document"] is None,
                    "a refused resource-page fetch is recorded as an error, with nothing pinned and no PDF fetched", msg))
    with tempfile.TemporaryDirectory() as t:
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page,
                                         ["https://evil.example/resources/rba/205"], resource)
        out.append((not stub.calls and line is not None and line["chosen"] == "pinned",
                    "a resource link on another host is not followed", msg))
    with tempfile.TemporaryDirectory() as t:
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "fincen", item_page,
                                         ["https://www.fincen.gov/resources/rba/205"], resource)
        out.append((not stub.calls and line is not None and line["chosen"] == "pinned",
                    "a source with no document_via never hops", msg))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--mutate", choices=sorted(MUTATIONS))
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s" % ("HOLDS" if not failures else "FAILED: %d" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
