"""
Pin feeds_extract and where an extraction a feeds run starts may write (slice 2 C, spec sections 1 and 2).

Usage:
    python evals/check_feeds_extract.py
    python evals/check_feeds_extract.py --mutate no-verdict-check  # an item not triaged relevant is queued
    python evals/check_feeds_extract.py --mutate no-cap            # more than 3 extractions in one run
    python evals/check_feeds_extract.py --mutate second-request    # an item is queued twice
    python evals/check_feeds_extract.py --mutate any-host          # a linked PDF off the document hosts is fetched
    python evals/check_feeds_extract.py --mutate reuse-id          # an allocated advisory id is allocated again
    python evals/check_feeds_extract.py --mutate queue-escape      # a feeds extraction's queue lands in data/proposals
    python evals/check_feeds_extract.py --mutate unreadable-raises # a linked "PDF" pypdf cannot page escapes as an exception
    python evals/check_feeds_extract.py --mutate unreadable-unrecorded  # ...is refused but not recorded, so a retry refetches
    python evals/check_feeds_extract.py --mutate own-host-rule     # the link rule is a second copy, blind to scheme and port
    python evals/check_feeds_extract.py --mutate no-text-queued    # a linked PDF with no text is told "Queued"
    python evals/check_feeds_extract.py --mutate eval-extract      # request() queues an item of an eval run
    python evals/check_feeds_extract.py --mutate reallocate        # an id another run already allocated is allocated again
    python evals/check_feeds_extract.py --mutate hide-duplicates   # load_allocations keeps the last of two lines silently
    python evals/check_feeds_extract.py --mutate inbox-ids-only    # accepted runs' tracked allocations are not read
    python evals/check_feeds_extract.py --mutate no-identity-match-check  # extract() trusts a mismatched RunIdentity
    python evals/check_feeds_extract.py --mutate identity-check-refuses-all  # every passed identity is refused
    python evals/check_feeds_extract.py --mutate no-resolve         # the identity check compares an unresolved path
    python evals/check_feeds_extract.py --mutate stale-prompt-hash  # run_started is passed a constant/stale hash
    python evals/check_feeds_extract.py --mutate no-prompt-hash     # run_started is called with no prompt_sha256 at all

WHAT IT HOLDS:
  relevant only  a request is refused for an item not listed, with no verdict, or triaged not_relevant;
  once, capped   a second request for an item is refused; the fourth request in a run is refused;
  the document   a pinned page linking ONE PDF on its source's document hosts gets that PDF, fetched with
                 exactly those hosts and PDF only, pinned under docs/<sha256>.pdf; a page linking none is
                 extracted as itself; two is refused as ambiguous; a link on any other host is ignored and
                 recorded; a failed fetch is recorded, not retried; bytes labelled application/pdf that are not
                 a PDF are refused and recorded, the bytes stay pinned, and a retry is answered from the record
                 with no second fetch; a PDF with no text is refused ("Rejected:"), never told "Queued";
  the host rule  a plain-http link and an allowed host on another port are off the document hosts, by
                 feeds.http._check_host itself;
  live only      request() refuses an eval run itself, with no fetch and no line;
  ids            next_advisory_id is one past every id in the advisory list and every id any run allocated,
                 expired runs included; a key is never allocated a second id, an id already allocated is never
                 allocated again (a stale computation raises), and load_allocations RAISES on a duplicate;
                 an EMPTY inbox (a fresh clone) still allocates above every id in accepted runs' TRACKED copies,
                 data/feeds/runs/<run>/advisory_ids.jsonl (here a temporary one), and refuses one of them;
  the queue      an extraction naming its feeds run writes inbox/<run>/proposals/<run_id>.jsonl: the runner's
                 RunIdentity and the server derive the SAME path; a malformed feeds run is refused; with no
                 feeds run the queue is data/proposals/ exactly as in slice 1;
  the tool       the server's feeds_extract applies these rules under a run identity and refuses without one;
  identity       extract() refuses a passed RunIdentity that does not match its own call's advisory id or
                 document, before any session starts and with no file read for the mismatched path; a
                 MATCHING identity -- same document, differently spelled -- gets past the check, proved by
                 reaching (a stubbed) document_pages, never a session;
  inbox only     every file written is inside the temporary inbox; the repository's git status is unchanged.
  prompt sha     extract() passes run_started the sha256 of the prompt it actually sends: sha256(system_prompt)
                 == recorded prompt_sha256 == extract_advisory.PROMPT_SHA256, proved by stubbing query() so no
                 session can start.

COLD. Stubbed HTTP, temporary inbox and advisory list. No network, no model.

NOT A VACUOUS PASS. Each --mutate rewrites feeds/extraction.py or the Knowledge Centre server in memory;
at least one check must fail.
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
sys.path.insert(0, str(ROOT / "evals"))
import feeds  # noqa: E402
from agents import telemetry  # noqa: E402
from feeds import http as fh, inbox, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem  # noqa: E402
from feeds.sources import linked_pdfs  # noqa: E402
from check_document_pages import tiny_pdf  # noqa: E402

EXTRACTION = ROOT / "feeds" / "extraction.py"
KC = ROOT / "mcp_server" / "knowledge_centre_server.py"
SERVER = ROOT / "mcp_server" / "feeds_server.py"
EXTRACT_ADVISORY = ROOT / "agents" / "extract_advisory.py"
RUN = "feeds-2026-10-02-ccc333"
JUNK_RUN = "feeds-2026-10-02-eee555"  # its own run, so this run's cap of 3 is not spent on it
EVAL_RUN = "feeds-2026-10-02-fff666"  # an eval run (state["eval"]), as feeds_server's eval mode marks one
HTTP_LINK = "http://www.fincen.gov/system/files/2026-10/plain.pdf"  # the right host, the wrong scheme
PORT_LINK = "https://www.fincen.gov:8443/system/files/2026-10/port.pdf"  # the right host, another port
NOT_A_PDF = b"%PDF-1.4\nlabelled a PDF, but these bytes are not one\n"
PDF_URL = "https://www.fincen.gov/system/files/2026-10/advisory.pdf"
SENTENCE = "This advisory describes red flags for trade-based money laundering through shell companies."
MUTATIONS = {
    "no-verdict-check": (EXTRACTION, "    if verdict is None or verdict[\"verdict\"] != feeds_triage.RELEVANT:\n",
                         "    if False:\n"),
    "no-cap": (EXTRACTION, "MAX_PER_RUN = 3\n", "MAX_PER_RUN = 30\n"),
    "second-request": (EXTRACTION, "    if any(r[\"key\"] == key for r in done):\n", "    if False:\n"),
    "any-host": (EXTRACTION, "    ok = [u for u in links if _on_hosts(u, hosts)]\n", "    ok = list(links)\n"),
    "own-host-rule": (EXTRACTION, "if _on_hosts(u, hosts)]", "if u.split(\"/\")[2].split(\":\")[0].lower() in hosts]"),
    "no-text-queued": (EXTRACTION, "    if entry[\"error\"]:  # recorded, and refused", "    if False:  # recorded, and refused"),
    "eval-extract": (EXTRACTION, "    if state.get(\"eval\"):\n", "    if False:\n"),
    "reallocate": (EXTRACTION, "    if advisory_id in allocated:\n", "    if False:\n"),
    "hide-duplicates": (EXTRACTION, "        if entry[\"key\"] in out or entry[\"advisory_id\"] in out.values():\n",
                        "        if False:\n"),
    "reuse-id": (EXTRACTION, "        taken += _ids_in(path)\n", "        pass\n"),
    "inbox-ids-only": (EXTRACTION, '    files += sorted(Path(tracked_runs).glob("*/%s" % ALLOCATIONS))\n', ""),
    "unreadable-raises": (EXTRACTION, "        except Exception as exc:  # labelled a PDF, but not one pypdf can page",
                          "        except ZeroDivisionError as exc:  # labelled a PDF, but not one pypdf can page"),
    "unreadable-unrecorded": (EXTRACTION, "            _append(run_id, REQUESTS, entry, root)  # recorded, so a retry",
                              "            pass  # recorded, so a retry"),
    "queue-escape": (KC, "    folder = feeds_inbox.proposals_dir(feeds_run, FEEDS_INBOX_ROOT) if feeds_run else QUEUE_DIR\n",
                     "    folder = QUEUE_DIR\n"),
    "no-identity-match-check": (EXTRACT_ADVISORY,
        "    if run is not None:\n"
        "        resolved = Path(path).resolve()\n"
        '        if run.advisory_id != advisory_id or run.pdf_path != resolved:\n'
        '            raise ValueError("the run identity %s (advisory %s, document %s) does not match this '
        'call\'s own "\n'
        '                             "arguments (advisory %s, document %s)"\n'
        "                             % (run.run_id, run.advisory_id, run.pdf_path, advisory_id, resolved))\n",
        ""),
    # Fix round 1, Important (F6): a version that refuses EVERY passed identity, matching one included, must
    # also go red -- the negative-only guard above could not tell this apart from the real check.
    "identity-check-refuses-all": (EXTRACT_ADVISORY,
        '        if run.advisory_id != advisory_id or run.pdf_path != resolved:\n',
        "        if True:\n"),
    "no-resolve": (EXTRACT_ADVISORY, "        resolved = Path(path).resolve()\n", "        resolved = Path(path)\n"),
    "stale-prompt-hash": (EXTRACT_ADVISORY,
        "    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256=PROMPT_SHA256)\n",
        '    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256="0" * 64)\n'),
    "no-prompt-hash": (EXTRACT_ADVISORY,
        "    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256=PROMPT_SHA256)\n",
        "    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS)\n"),
}


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


def page(links=()) -> bytes:
    anchors = "".join('<a href="%s">document</a>' % u for u in links)
    return ("<html><body><main><h1>Advisory</h1><p>%s</p><p>%s</p></main></body></html>"
            % (SENTENCE, anchors)).encode("utf-8")


class Stub:
    def __init__(self, fail=False, body=None):
        self.calls, self.fail, self.body = [], fail, body

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append((url, sorted(allowed_hosts), sorted(allowed_types)))
        if self.fail:
            raise fh.FetchRefused("stub: connection reset")
        return fh.Fetched(url, url, "application/pdf",
                          self.body if self.body is not None else tiny_pdf(["Advisory text on shell companies."]))


def setup(tmp: Path, docs: dict, run: str = RUN) -> list:
    """A run that listed one fincen item per entry of `docs` (name -> page bytes), each fetched and pinned."""
    state = {"run_id": run, "sources": {"fincen": {"status": "ok", "items": []}}}
    keys = []
    for name, raw in docs.items():
        it = FeedItem("fincen", name, "Advisory %s" % name, "https://www.fincen.gov/resources/advisories/%s" % name,
                      "2026-10-01")
        rel = inbox.write_file(run, "docs/%s.html" % __import__("hashlib").sha256(raw).hexdigest(), raw, tmp)
        doc = {"path": rel, "sha256": __import__("hashlib").sha256(raw).hexdigest(), "content_type": "text/html",
               "bytes": len(raw), "final_url": it.url, "pages": 1, "text_pages": 1, "page_error": None,
               "linked_pdfs": linked_pdfs(raw, it.url)}
        state["sources"]["fincen"]["items"].append(dict(it.to_json(), document=doc))
        keys.append(it.key)
    inbox.save(run, state, tmp)
    return keys


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


def checks(mutation) -> list:
    ex = load("feeds.extraction", EXTRACTION, mutation)
    feeds.extraction = ex
    kc = load("kc_under_test", KC, mutation)
    out, before = [], git_status()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        box = tmp / "inbox"
        other = "https://evil.example/advisory.pdf"
        keys = setup(box, {"a1": page([PDF_URL, other, HTTP_LINK, PORT_LINK]), "a2": page(), "a3": page([PDF_URL]),
                           "a4": page(), "a5": page(["https://www.fincen.gov/x.pdf", "https://www.fincen.gov/y.pdf"]),
                           "a6": page(), "a7": page([PDF_URL])})
        a1, a2, a3, a4, a5, a6, a7 = keys
        stub = Stub()

        def requests() -> list:
            try:
                return ex.load_requests(RUN, box)
            except ValueError as exc:  # a duplicated request line is corruption the mutation produced
                return [{"corrupt": str(exc), "chosen": None, "document": None, "error": None, "ignored_links": None}] * 9

        def req(key, get=stub):
            try:
                return ex.request(RUN, key, get, box)
            except Exception as exc:
                return False, "RAISED %s: %s" % (type(exc).__name__, exc)

        said = req(a1)
        out.append((not said[0] and said[1].startswith("Rejected") and not requests(),
                    "an item with no verdict is refused and nothing is written", said[1][:80]))
        for k in (a1, a2, a3, a4, a5, a6, a7):
            ok, msg = feeds_triage.decide(RUN, k, "relevant" if k != a6 else "not_relevant", "Red flags.", SENTENCE, box)
            assert ok, msg
        said = req(a6)
        out.append((not said[0] and "not_relevant" in said[1], "an item triaged not_relevant is refused", said[1][:80]))
        said = req("fincen:0000000000000000")
        out.append((not said[0] and "not listed" in said[1], "an item not listed in this run is refused", said[1][:80]))

        said = req(a1)
        reqs = requests()
        pinned = box / RUN / (reqs[0]["document"]["path"] if reqs and reqs[0]["document"] else "none")
        out.append((said[0] and said[1].startswith("Queued") and len(stub.calls) == 1
                    and stub.calls[0] == (PDF_URL, ["www.fincen.gov"], ["application/pdf"])
                    and reqs[0]["chosen"] == "linked" and reqs[0]["ignored_links"] == [other, HTTP_LINK, PORT_LINK]
                    and pinned.exists() and pinned.name == "%s.pdf" % reqs[0]["document"]["sha256"],
                    "a page linking one PDF on the document hosts: that PDF, fetched with those hosts and PDF only, "
                    "pinned by sha256; the off-host, plain-http and other-port links are ignored and recorded", "%s %s" % (said[1][:60], stub.calls)))
        said = req(a1)
        out.append((not said[0] and "already queued" in said[1] and len(requests()) == 1,
                    "a second request for the same item is refused", said[1][:80]))
        said = req(a5)
        out.append((not said[0] and "2 PDFs" in said[1], "a page linking two PDFs is refused as ambiguous", said[1][:90]))
        said = req(a2)
        reqs = requests()
        out.append((said[0] and reqs[-1]["chosen"] == "pinned" and reqs[-1]["document"]["path"].endswith(".html")
                    and len(stub.calls) == 1, "a page linking no PDF is extracted as the page itself, with no fetch",
                    said[1][:80]))
        said = req(a3, Stub(fail=True))
        reqs = requests()
        out.append((said[1].startswith("Failed") and reqs[-1]["error"] and reqs[-1]["document"] is None,
                    "a failed fetch is recorded on the request, not retried", said[1][:80]))
        said = req(a4)
        out.append((not said[0] and "cap of 3" in said[1] and len(requests()) == 3,
                    "the fourth request in a run is refused: at most 3", said[1][:80]))

        j1, j2 = setup(box, {"j1": page([PDF_URL]), "j2": page([PDF_URL])}, JUNK_RUN)
        for k in (j1, j2):
            assert feeds_triage.decide(JUNK_RUN, k, "relevant", "Red flags.", SENTENCE, box)[0]
        junk = Stub(body=NOT_A_PDF)

        def junk_req():
            try:
                return ex.request(JUNK_RUN, j1, junk, box)
            except Exception as exc:
                return False, "RAISED %s: %s" % (type(exc).__name__, exc)

        said = junk_req()
        lines = ex.load_requests(JUNK_RUN, box)
        pin = box / JUNK_RUN / "docs" / ("%s.pdf" % __import__("hashlib").sha256(NOT_A_PDF).hexdigest())
        again = junk_req()
        out.append((said[1].startswith("Rejected") and "could not be read" in said[1] and len(junk.calls) == 1
                    and len(lines) == 1 and lines[0]["error"] == said[1] and lines[0]["document"]["page_error"]
                    and pin.exists() and pin.read_bytes() == NOT_A_PDF
                    and again[1].startswith("Rejected") and "could not be read" in again[1]
                    and "not fetched again" in again[1] and len(junk.calls) == 1
                    and len(ex.load_requests(JUNK_RUN, box)) == 1,
                    "bytes labelled application/pdf that are not a PDF: refused and recorded, the bytes pinned, "
                    "one fetch; a retry is answered from the record with no second fetch",
                    "%s | retry: %s | fetches %d" % (said[1][:70], again[1][:50], len(junk.calls))))

        blank = Stub(body=tiny_pdf([""]))
        try:
            said = ex.request(JUNK_RUN, j2, blank, box)
        except Exception as exc:
            said = False, "RAISED %s: %s" % (type(exc).__name__, exc)
        try:
            line = [r for r in ex.load_requests(JUNK_RUN, box) if r["key"] == j2]
        except ValueError as exc:  # a duplicated line (a mutation's corruption) must fail a check, not the guard
            line, said = [], (False, "CORRUPT %s" % exc)
        out.append((said[1].startswith("Rejected") and "no text" in said[1] and len(blank.calls) == 1
                    and len(line) == 1 and line[0]["error"] == said[1],
                    "a linked PDF with no text is refused with its reason and recorded, never told \"Queued\"",
                    said[1][:80]))

        (e1,) = setup(box, {"e1": page([PDF_URL])}, EVAL_RUN)
        state = inbox.load(EVAL_RUN, box)
        state["eval"] = True
        inbox.save(EVAL_RUN, state, box)
        assert feeds_triage.decide(EVAL_RUN, e1, "relevant", "Red flags.", SENTENCE, box)[0]
        live = Stub()
        try:
            said = ex.request(EVAL_RUN, e1, live, box)
        except Exception as exc:
            said = False, "RAISED %s: %s" % (type(exc).__name__, exc)
        out.append((not said[0] and said[1].startswith("Rejected") and "eval run" in said[1] and not live.calls
                    and not ex.load_requests(EVAL_RUN, box),
                    "request() itself refuses an eval run: no fetch, no line", said[1][:80]))

        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020"}, {"advisory_id": "ADV-2025-0400"}]}),
                         encoding="utf-8")
        tracked = tmp / "data" / "feeds" / "runs"   # temporary: the real one would move every id asserted here
        first = ex.allocate_advisory_id(RUN, a1, 2026, alist, box, tracked)
        expired = box / "expired" / "feeds-2026-09-01-ddd444"
        expired.mkdir(parents=True)
        (expired / ex.ALLOCATIONS).write_text(json.dumps({"key": "k", "advisory_id": "ADV-2026-0023"}) + "\n",
                                              encoding="utf-8")
        got = ex.next_advisory_id(2026, alist, box, tracked)
        out.append((first == "ADV-2026-0021" and got == "ADV-2026-0024" and ex.load_allocations(RUN, box) == {a1: first}
                    and ex.next_advisory_id(2027, alist, box, tracked) == "ADV-2027-0001",
                    "the next advisory id is past the list and every run's allocations, expired runs included", got))

        def refused(fn):
            try:
                return "ALLOWED %s" % (fn(),)
            except ValueError as exc:
                return "REFUSED %s" % exc
        twice = refused(lambda: ex.allocate_advisory_id(RUN, a1, 2026, alist, box, tracked))
        computed = ex.next_advisory_id
        ex.next_advisory_id = lambda *a, **k: "ADV-2026-0023"  # stale: an expired run allocated it meanwhile
        try:
            stale = refused(lambda: ex.allocate_advisory_id(RUN, a2, 2026, alist, box, tracked))
        finally:
            ex.next_advisory_id = computed
        out.append((twice.startswith("REFUSED") and stale.startswith("REFUSED") and "already allocated" in stale
                    and ex.load_allocations(RUN, box) == {a1: first},
                    "a key is never allocated a second id, and an id another run already allocated is refused, "
                    "not written", "%s | %s" % (twice[:45], stale[:45])))
        dups = []
        for run, lines in (("feeds-2026-10-02-aaa111", [("k1", "ADV-2026-0030"), ("k1", "ADV-2026-0031")]),
                           ("feeds-2026-10-02-bbb222", [("k2", "ADV-2026-0032"), ("k3", "ADV-2026-0032")])):
            (box / run).mkdir(parents=True)
            (box / run / ex.ALLOCATIONS).write_text("".join(json.dumps({"key": k, "advisory_id": i}) + "\n"
                                                            for k, i in lines), encoding="utf-8")
            dups.append(refused(lambda: ex.load_allocations(run, box)))
        out.append((all(d.startswith("REFUSED") for d in dups),
                    "load_allocations raises on a key with two ids and on an id given to two keys", str(dups)[:90]))

        # A fresh clone: NO inbox history, only an accepted run's tracked copy (the gap ADV-2026-0040 among them).
        fresh = tmp / "fresh-clone-inbox"
        (fresh / RUN).mkdir(parents=True)
        (tracked / "feeds-2026-09-18-eee555").mkdir(parents=True)
        (tracked / "feeds-2026-09-18-eee555" / ex.ALLOCATIONS).write_text(
            "".join(json.dumps({"key": k, "advisory_id": i}) + "\n" for k, i in (("ka", "ADV-2026-0039"),
                                                                                ("kb", "ADV-2026-0040"))),
            encoding="utf-8")
        nxt = ex.next_advisory_id(2026, alist, fresh, tracked)
        computed = ex.next_advisory_id
        ex.next_advisory_id = lambda *a, **k: "ADV-2026-0040"  # stale: the gap, computed without the tracked copy
        try:
            reissued = refused(lambda: ex.allocate_advisory_id(RUN, a1, 2026, alist, fresh, tracked))
        finally:
            ex.next_advisory_id = computed
        out.append((nxt == "ADV-2026-0041" and reissued.startswith("REFUSED") and "already allocated" in reissued
                    and not ex.load_allocations(RUN, fresh),
                    "a checkout with no inbox history still allocates above an accepted run's TRACKED allocations, and "
                    "refuses to issue one of them again", "%s | %s" % (nxt, reissued[:50])))

        from agents.run_identity import RunIdentity
        doc = tmp / "doc.html"
        doc.write_bytes(page())
        ident = RunIdentity.new("extractor", "ADV-2026-0024", doc, feeds_run=RUN, inbox_root=box)
        saved = {k: os.environ.get(k) for k in (kc.FEEDS_RUN_ENV,)}
        kc.FEEDS_INBOX_ROOT = box
        os.environ[kc.FEEDS_RUN_ENV] = RUN
        try:
            derived = kc._proposals_path(ident.env())
            refusal = kc._refuse_queue(ident.env())
            os.environ[kc.FEEDS_RUN_ENV] = "feeds-../../data"
            bad = kc._refuse_queue(dict(ident.env(), NEXUS_FEEDS_RUN="feeds-../../data"))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        out.append((derived == ident.queue_path == box / RUN / "proposals" / ("%s.jsonl" % ident.run_id)
                    and refusal is None and ident.env()["NEXUS_FEEDS_RUN"] == RUN,
                    "a feeds extraction's queue is inbox/<run>/proposals/<run_id>.jsonl, derived the same by runner "
                    "and server", "%s | %s" % (derived, refusal)))
        out.append((bool(bad) and bad.startswith("Rejected"), "a malformed feeds run is refused", str(bad)[:80]))
        plain = RunIdentity.new("extractor", "ADV-2026-0013", doc)
        out.append((kc._proposals_path(plain.env()) == plain.queue_path == kc.QUEUE_DIR / ("%s.jsonl" % plain.run_id)
                    and "NEXUS_FEEDS_RUN" not in plain.env(),
                    "with no feeds run the queue is data/proposals/ exactly as in slice 1", str(plain.queue_path)[-40:]))

        fs = load("feeds_server_under_test", SERVER, None)
        fs.HTTP_GET, fs.INBOX_ROOT = Stub(), box
        os.environ.pop(fs.RUN_ENV, None)

        def tool(key):
            try:
                return asyncio.run(fs.extract(fs.ExtractInput(item_key=key)))
            except Exception as exc:
                return "RAISED %s: %s" % (type(exc).__name__, exc)

        said = tool(a7)
        out.append((said.startswith("Rejected") and "run identity" in said, "the tool refuses without a run identity",
                    said[:80]))
        os.environ[fs.RUN_ENV] = RUN
        try:
            said = tool(a7)
        finally:
            os.environ.pop(fs.RUN_ENV, None)
        out.append((said.startswith("Rejected") and "cap of 3" in said,
                    "the server's feeds_extract applies the same rules (this run's cap is already reached)", said[:80]))
        written = [p.relative_to(tmp) for p in tmp.rglob("*") if p.is_file()]
        planted = {tracked.relative_to(tmp) / "feeds-2026-09-18-eee555" / ex.ALLOCATIONS}  # this guard's own fixture
        out.append((all(str(w).startswith("inbox/") or w.name in ("advisory_list.json", "doc.html") or w in planted
                        for w in written),
                    "every file written is inside the temporary inbox", "%d files; outside: %s" % (
                        len(written), [str(w) for w in written if not str(w).startswith("inbox/")
                                       and w.name not in ("advisory_list.json", "doc.html") and w not in planted][:3])))

        # F6 (2026-09-28 fixes brief): extract() must refuse a passed RunIdentity that does not match this
        # call's own arguments, before any session starts. Never actually calls the model: a mismatch is
        # caught before extract() even reads the document, proved here with a document that does not exist.
        ea = load("extract_advisory_under_test", EXTRACT_ADVISORY, mutation)
        from agents.run_identity import RunIdentity as RI
        doc_a = tmp / "identity-a.pdf"
        doc_a.write_bytes(page())  # RunIdentity.new hashes it, so it must exist; the CALL's own path need not
        ident = RI.new("extractor", "ADV-2026-0001", doc_a)

        def raised(coro):
            try:
                asyncio.run(coro)
                return None
            except Exception as exc:
                return exc

        exc1 = raised(ea.extract(tmp / "does-not-exist.pdf", "ADV-2026-0002", "stub-model", 1.0, 5, run=ident))
        exc2 = raised(ea.extract(tmp / "also-missing.pdf", "ADV-2026-0001", "stub-model", 1.0, 5, run=ident))
        out.append((isinstance(exc1, ValueError) and "ADV-2026-0001" in str(exc1) and "ADV-2026-0002" in str(exc1)
                   and isinstance(exc2, ValueError) and "also-missing.pdf" in str(exc2),
                   "extract() refuses a passed RunIdentity that does not match this call's own advisory id or "
                   "document, before any session starts (no file even read for the mismatched path)",
                   "%s | %s" % (exc1, exc2)))

        # Fix round 1, Important (F6): the case above only ever proves a REFUSAL. A version of the check that
        # refuses every passed identity (or that compares an unresolved path) would stay green. Add the
        # positive case: a MATCHING identity, the same document spelled differently (redundant ".." segments,
        # never resolved by hand here), must get PAST the check -- proved by reaching document_pages, stubbed
        # to raise a sentinel so no session can ever start.
        differently_spelled = doc_a.parent / ".." / doc_a.parent.name / doc_a.name
        assert differently_spelled != doc_a and differently_spelled.resolve() == doc_a.resolve(), (
            "the fixture must be an unresolved spelling of the SAME file, or this case proves nothing")

        class _GotPastIdentityCheck(Exception):
            pass

        real_document_pages = ea.document_pages

        def stubbed(_path):
            raise _GotPastIdentityCheck("stub: extract() reached document_pages -- no session was reachable")
        ea.document_pages = stubbed
        try:
            exc3 = raised(ea.extract(differently_spelled, "ADV-2026-0001", "stub-model", 1.0, 5, run=ident))
        finally:
            ea.document_pages = real_document_pages
        out.append((isinstance(exc3, _GotPastIdentityCheck),
                   "a MATCHING RunIdentity -- same document, spelled differently -- gets past the check "
                   "(reaches document_pages; a refuse-everything or an unresolved-path version would raise "
                   "ValueError here instead, before ever reaching it)", str(exc3)))

        # Prompt-sha brief (2026-09-29): the extractor must pass run_started the hash of the prompt it
        # actually SENDS, not a constant or a stale one. Get further than the identity-check positive case
        # above -- past run_started and the options -- and still start no session, by stubbing query()
        # (not document_pages) in the extract_advisory module namespace. TELEMETRY_DIR is redirected so the
        # real run_started, left in place, writes nowhere near the checkout.
        doc_b = tmp / "identity-b.pdf"
        doc_b.write_bytes(tiny_pdf(["Advisory text for the prompt-sha probe."]))  # a real PDF: document_pages()
        ident_b = RI.new("extractor", "ADV-2026-0077", doc_b)                    # runs for real, unlike exc1-exc3

        class _GotPastRunStarted(Exception):
            pass

        captured: dict = {}
        real_query = ea.query
        real_run_started = telemetry.run_started
        real_telemetry_dir = telemetry.TELEMETRY_DIR

        async def stub_query(*, prompt, options):
            captured["system_prompt"] = options.system_prompt
            raise _GotPastRunStarted("stub: extract() reached query() -- no session was started")
            yield  # pragma: no cover -- keeps this an async generator; the raise above is always hit first

        def capturing_run_started(run, model, max_budget_usd, max_turns, tools, **kwargs):
            captured["prompt_sha256"] = kwargs.get("prompt_sha256")
            return real_run_started(run, model, max_budget_usd, max_turns, tools, **kwargs)

        ea.query = stub_query
        telemetry.run_started = capturing_run_started
        telemetry.TELEMETRY_DIR = tmp / "telemetry-scratch"  # never data/telemetry/
        try:
            exc4 = raised(ea.extract(doc_b, "ADV-2026-0077", "stub-model", 1.0, 5, run=ident_b))
        finally:
            ea.query = real_query
            telemetry.run_started = real_run_started
            telemetry.TELEMETRY_DIR = real_telemetry_dir

        sent_hash = hashlib.sha256(captured.get("system_prompt", "").encode("utf-8")).hexdigest()
        out.append((isinstance(exc4, _GotPastRunStarted)
                   and captured.get("prompt_sha256") == ea.PROMPT_SHA256 == sent_hash,
                   "the extractor passes run_started the hash of the prompt it actually sends: "
                   "sha256(system_prompt) == recorded prompt_sha256 == extract_advisory.PROMPT_SHA256 "
                   "(reaches query(); no session was started)",
                   "%s | recorded %s | PROMPT_SHA256 %s" % (
                       type(exc4).__name__, str(captured.get("prompt_sha256"))[:16], ea.PROMPT_SHA256[:16])))

    out.append((git_status() == before, "the repository's git status is unchanged", ""))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin feeds_extract and an extraction's queue")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule in memory; a check MUST fail")
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
