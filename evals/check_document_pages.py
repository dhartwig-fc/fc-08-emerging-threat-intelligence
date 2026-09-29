"""
Pin the one document loader: a PDF or a pinned HTML page, paged the same way by every caller (slice 2 C).

Usage:
    python evals/check_document_pages.py
    python evals/check_document_pages.py --mutate pdf-only       # document_texts pages only PDFs
    python evals/check_document_pages.py --mutate server-pdf     # propose_link's index is PDF-only again
    python evals/check_document_pages.py --mutate gate-pdf       # the review gate's re-check is PDF-only again
    python evals/check_document_pages.py --mutate extractor-pdf  # the extractor's prompt pages are PDF-only again
    python evals/check_document_pages.py --mutate triage-pdf     # triage's pages are PDF-only again
    python evals/check_document_pages.py --mutate triage-own-loader  # triage keeps B's second copy of the rule

WHAT IT HOLDS. A live feed item may be an HTML page (every OFAC action; OFSI notices with no PDF). Its
quotes must be found, and a fabricated one refused, by every caller that re-finds a quote:
  loader      schemas.citation_match.document_texts / PageIndex.from_document give a PDF exactly
              from_pdf's pages and an HTML page exactly from_html's; any other suffix is refused;
  extractor   agents/extract_advisory.document_pages numbers those same pages "=== PAGE n ===";
  triage      feeds.triage.page_texts -- what feeds_read_page shows, what a triage quote is checked
              against, and what feeds_extract pages a linked PDF with -- IS the loader: the same pages
              for a PDF and an HTML page, and the same refusal of any other suffix (B's own copy of the
              rule paged a .txt as HTML, to no pages, rather than refusing it);
  server      knowledge_centre_server._page_index finds a true quote on an HTML document's page and
              not a fabricated one;
  gate        governance.proposals.recheck passes a proposal quoting the HTML page and quarantines
              one quoting text the page does not hold;
  checker     evals/check_citations.check_record counts the true quote EXACT on the HTML page.

COLD. The HTML is the committed tests/fixtures/html page; the PDF is built here, in memory, with two
pages of known text. Temporary files only. No network, no model.

NOT A VACUOUS PASS. Each --mutate rewrites one module's source in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from schemas.proposal_contract import SCHEMA, proposal_id  # noqa: E402

HTML = ROOT / "tests" / "fixtures" / "html" / "ofsi_uk_financial_sanctions_faqs.html"
TRUE_QUOTE = "OFSI publishes FAQs providing short-form guidance and technical information on financial sanctions."
FABRICATED = "OFSI publishes a red-flag list of shell companies used to evade sanctions."
PDF_LINES = ("Trade based laundering moves value through invoices.", "Front companies disguise the origin of funds.")
CM = ROOT / "schemas" / "citation_match.py"
KC = ROOT / "mcp_server" / "knowledge_centre_server.py"
GATE = ROOT / "governance" / "proposals.py"
EXTRACTOR = ROOT / "agents" / "extract_advisory.py"
TRIAGE = ROOT / "feeds" / "triage.py"
MUTATIONS = {
    "pdf-only": (CM, '    if suffix in (".html", ".htm"):\n        from schemas.html_pages import html_pages\n'
                     '        return html_pages(Path(path).read_bytes())\n', ""),
    "server-pdf": (KC, "    return PageIndex.from_document(pdf_path)", "    return PageIndex.from_pdf(pdf_path)"),
    "gate-pdf": (GATE, "PageIndex.from_document(pdf) if ok", "PageIndex.from_pdf(pdf) if ok"),
    "extractor-pdf": (EXTRACTOR, "enumerate(document_texts(path), start=1)",
                      "enumerate([p.extract_text() for p in __import__('pypdf').PdfReader(str(path)).pages], start=1)"),
    "triage-pdf": (TRIAGE, "    return document_texts(path)\n",
                   "    return [p.extract_text() or '' for p in __import__('pypdf').PdfReader(str(path)).pages]\n"),
    "triage-own-loader": (TRIAGE, "    return document_texts(path)\n",  # B's page_texts, verbatim, before C
                          '    if Path(path).suffix == ".pdf":\n'
                          "        from pypdf import PdfReader\n"
                          '        return [p.extract_text() or "" for p in PdfReader(str(path)).pages]\n'
                          "    from schemas.html_pages import html_pages\n"
                          "    return html_pages(Path(path).read_bytes())\n"),
}


def tiny_pdf(lines) -> bytes:
    """A valid PDF with one line of Helvetica text per page, built by hand (no dependency, no fixture)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for line in lines:
        stream = "BT /F1 12 Tf 72 720 Td (%s) Tj ET" % line
        objs.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>" % len(objs))
        kids.append("%d 0 R" % len(objs))
    objs[1] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(kids), len(kids))
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (n, body)).encode("latin-1")
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    out += "".join("%010d 00000 n \n" % o for o in offsets).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    return out


def load(name: str, path: Path, mutation):
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
    return module


def checks(mutation) -> list:
    cm = load("schemas.citation_match", CM, mutation)  # every module below imports THIS one
    kc = load("kc_under_test", KC, mutation)
    gate = load("governance.proposals", GATE, mutation)
    ex = load("extractor_under_test", EXTRACTOR, mutation)
    tri = load("triage_under_test", TRIAGE, mutation)
    import check_citations
    check_citations.PageIndex = cm.PageIndex
    out = []

    def attempt(fn):
        try:
            return fn()
        except Exception as exc:  # a mutation that makes a loader raise must fail a check, not the guard
            return "RAISED %s: %s" % (type(exc).__name__, exc)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pdf = tmp / "doc.pdf"
        pdf.write_bytes(tiny_pdf(PDF_LINES))
        html = tmp / ("%s.html" % hashlib.sha256(HTML.read_bytes()).hexdigest())
        html.write_bytes(HTML.read_bytes())
        txt = tmp / "doc.txt"
        txt.write_text("text", encoding="utf-8")

        from_pdf = cm.PageIndex.from_pdf(pdf).pages
        got = attempt(lambda: cm.PageIndex.from_document(pdf).pages)
        out.append((got == from_pdf and len(got) == 2 and "invoices" in got[0],
                    "a PDF is paged by from_document exactly as by from_pdf", str(got)[:80]))
        want = cm.PageIndex.from_html(HTML.read_bytes()).pages
        got = attempt(lambda: cm.PageIndex.from_document(html).pages)
        out.append((got == want and len(want) >= 1, "an HTML page is paged by from_document exactly as by from_html",
                    "%s pages" % (len(got) if isinstance(got, list) else got)))
        got = attempt(lambda: cm.document_texts(txt))
        out.append((isinstance(got, str) and "ValueError" in got, "any other suffix is refused", str(got)[:80]))

        got = attempt(lambda: ex.document_pages(html))
        from schemas.html_pages import html_pages
        raw = html_pages(HTML.read_bytes())
        out.append((got == ["=== PAGE %d ===\n%s" % (n, t.strip()) for n, t in enumerate(raw, 1)],
                    "the extractor's prompt pages of an HTML document are its html_pages, numbered",
                    str(got)[:80]))

        from pypdf import PdfReader
        pdf_raw = [p.extract_text() or "" for p in PdfReader(str(pdf)).pages]
        got = (attempt(lambda: tri.page_texts(pdf)), attempt(lambda: tri.page_texts(html)))
        out.append((got == (pdf_raw, raw), "triage's page_texts gives a PDF and an HTML page exactly the loader's pages",
                    str(got)[:80]))
        got = attempt(lambda: tri.page_texts(txt))
        out.append((isinstance(got, str) and "ValueError" in got and "neither a PDF nor an HTML" in got,
                    "triage's page_texts refuses any other suffix, as the loader does", str(got)[:80]))

        sha = hashlib.sha256(html.read_bytes()).hexdigest()
        kc._page_index.cache_clear()
        index = attempt(lambda: kc._page_index(str(html), sha))
        ok = not isinstance(index, str) and index.locate(1, TRUE_QUOTE).ok and not index.locate(1, FABRICATED).ok
        out.append((ok, "propose_link's index finds a true quote on the HTML page and not a fabricated one",
                    str(index)[:80]))

        advisories = tmp / "advisories"
        advisories.mkdir()
        (advisories / html.name).write_bytes(html.read_bytes())
        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0099", "file": html.name,
                                                     "sha256": sha}]}), encoding="utf-8")
        run_id = "adv-2026-0099-extractor-0123456789"
        lines = []
        for quote in (TRUE_QUOTE, FABRICATED):
            body = {"schema": SCHEMA, "run_id": run_id, "stage": "extractor", "advisory_id": "ADV-2026-0099",
                    "document_sha256": sha, "typology_id": "SAN001", "emergent_label": None,
                    "rationale": "The page describes sanctions guidance.", "confidence": "low",
                    "citations": [{"page": 1, "quote": quote}]}
            lines.append(dict(body, proposal_id=proposal_id(body), proposed_at="2026-10-02T09:00:00+00:00"))
        proposals = [gate.Proposal.from_line(d, source_file="%s.jsonl" % run_id) for d in lines]
        # feed_list=None: this is a fixture id (ADV-2026-0099) against a TEMPORARY golden list, never the
        # real live-feed list -- the default merges that in, and once a real acceptance reaches this id the
        # cold guard fails with "in both" (F3, 2026-09-28 fixes brief).
        got = attempt(lambda: gate.recheck(proposals, advisory_list=alist, advisories_dir=advisories, feed_list=None))
        ok = (not isinstance(got, str) and [p.citations[0][1] for p in got[0]] == [TRUE_QUOTE]
              and len(got[1]) == 1 and "not in the document" in got[1][0].reason)
        out.append((ok, "the gate passes the proposal quoting the HTML page and quarantines the fabricated one",
                    str(got)[:120] if isinstance(got, str) else "clean %d, quarantined %s" % (
                        len(got[0]), [q.reason[:50] for q in got[1]])))

        record = {"advisory_id": "ADV-2026-0099", "typologies": [
            {"typology_id": "SAN001", "citations": [{"page": 1, "quote": TRUE_QUOTE}]}], "actors": [], "indicators": []}
        rpath = tmp / "ADV-2026-0099.json"
        rpath.write_text(json.dumps(record), encoding="utf-8")
        got = attempt(lambda: check_citations.check_record(rpath, html, verbose=False))
        out.append((not isinstance(got, str) and got[0] == 1 and got[1] == 1,
                    "check_citations counts the true quote EXACT on the HTML page", str(got)[:80]))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the one document loader")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one caller in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
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
