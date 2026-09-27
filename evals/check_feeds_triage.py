"""
Pin feeds_triage and feeds_read_page: the triage rules of slice 2, sub-project B (spec section 4).

Usage:
    python evals/check_feeds_triage.py
    python evals/check_feeds_triage.py --mutate no-quote-check     # a quote absent from the document is recorded
    python evals/check_feeds_triage.py --mutate second-verdict     # an item can be triaged twice
    python evals/check_feeds_triage.py --mutate drop-not-relevant  # a not_relevant verdict is never written
    python evals/check_feeds_triage.py --mutate long-reason        # the reason cap is 3000, not 300
    python evals/check_feeds_triage.py --mutate no-strip           # padding lengthens a short quote
    python evals/check_feeds_triage.py --mutate no-cap             # more than 10 verdicts in one run
    python evals/check_feeds_triage.py --mutate no-pin-check       # a changed pinned document is still quoted
    python evals/check_feeds_triage.py --mutate refused-prefix     # refusals read "Refused:", which telemetry calls SUCCESS
    python evals/check_feeds_triage.py --mutate wrong-document     # a quote is checked against another item's document

WHAT IT HOLDS:
  quoted        a verdict is recorded only when its quote is found, by the shared matcher, in the item's
                OWN pinned document; a fabricated quote is refused and nothing is written; a quote true
                only of a DIFFERENT item's document is refused for this one (fix round 1: the stub now
                serves a second, distinct document, so this binding is not vacuously true);
  one verdict   a second call for the same item is refused, and the first verdict stands on disk;
  kept          a not_relevant verdict is written like a relevant one and stays in triage.jsonl;
  bounded       reason 1..300 characters (including the empty-or-whitespace case), quote 10..600 after
                strip, verdict relevant|not_relevant, at most 10 verdicts per run (the 11th refused:
                that item stays unfinished);
  pinned        read and triage refuse an item not fetched, and a pinned file whose bytes changed;
  no run        feeds_triage AND feeds_read_page both refuse, and write nothing, with no run identity;
  counted       every refusal starts "Rejected:" -- the one prefix agents.telemetry.REFUSAL_PREFIX
                classifies REFUSED, which is also feeds.triage.REJECTED (fix round 1: the server now
                builds its own refusals from that constant instead of a second literal);
  reconciled    feeds.triage.reconcile lists every listed-or-expected item without a verdict as
                unfinished, including a whole source the agent never listed;
  inbox only    every file written is inside the temporary inbox; the repository's git status is unchanged.

HOW. As evals/check_feeds_server.py: the server's HTTP_GET, INBOX_ROOT and SEEN_PATH are swapped for a
stub serving the committed OFSI snapshot -- every item's URL answers with the committed OFSI FAQ page,
except the last of the twelve fetched items, which gets a byte-variant of it with its own sha256 and a
sentence the other document never holds, so the quote-to-its-own-document binding is checkable -- and a
temporary inbox and ledger. Cold: no network, no model.

NOT A VACUOUS PASS. Each --mutate rewrites feeds/triage.py or the server in memory and loads the pair
as modules; at least one check must fail. A mutation whose target text is missing is a failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import feeds  # noqa: E402
from feeds import http as fh, ledger  # noqa: E402
from feeds.sources import SOURCES  # noqa: E402
from agents import telemetry  # noqa: E402

TRIAGE_SRC = ROOT / "feeds" / "triage.py"
SERVER = ROOT / "mcp_server" / "feeds_server.py"
FIX = ROOT / "tests" / "fixtures"
RUN = "feeds-2026-10-02-bbb111"
PAGE1_QUOTE = "OFSI publishes FAQs providing short-form guidance and technical information on financial sanctions."
PAGE2_QUOTE = "20 questions added to the Russia section"
FABRICATED = "OFSI publishes a red-flag list of shell companies used to evade sanctions."
PADDED = "   FAQ 204   "  # 7 characters once stripped; on page 1 as "FAQ 204 added."
# On the SECOND, distinct document only (Stub.doc2) -- never on the shared one every other item pins.
ITEM_B_QUOTE = "This second fixture belongs to item B alone; it is never served for item A."

MUTATIONS = {
    "no-quote-check": (TRIAGE_SRC, "    if not pages:\n        return False, (", "    if False:\n        return False, ("),
    "second-verdict": (TRIAGE_SRC, "    if key in done:\n", "    if False:\n"),
    "drop-not-relevant": (TRIAGE_SRC, "    _append(run_id, entry, root)\n",
                          "    if verdict == RELEVANT:\n        _append(run_id, entry, root)\n"),
    "long-reason": (TRIAGE_SRC, "REASON_MAX = 300\n", "REASON_MAX = 3000\n"),
    "no-strip": (TRIAGE_SRC, '    reason, quote = (reason or "").strip(), (quote or "").strip()\n',
                 '    reason, quote = reason or "", quote or ""\n'),
    "no-cap": (TRIAGE_SRC, "MAX_PER_RUN = 10\n", "MAX_PER_RUN = 100\n"),
    "no-pin-check": (TRIAGE_SRC, '    if not path.exists() or file_sha256(path) != doc["sha256"]:\n',
                     "    if not path.exists():\n"),
    "refused-prefix": (TRIAGE_SRC, 'REJECTED = "Rejected:"\n', 'REJECTED = "Refused:"\n'),
    "wrong-document": (TRIAGE_SRC, "    path, refusal = pinned_document(run_id, item, root)\n",
                       "    path, refusal = pinned_document(run_id, inbox.items(inbox.load(run_id, root))[0], "
                       "root)\n"),
}


def _module(name: str, path: Path, source: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def load_pair(mutation):
    """feeds/triage.py and the server, each from its (possibly mutated) source; the server imports that triage."""
    sources = {TRIAGE_SRC: TRIAGE_SRC.read_text(encoding="utf-8"), SERVER: SERVER.read_text(encoding="utf-8")}
    if mutation:
        path, old, new = MUTATIONS[mutation]
        if sources[path].count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
        sources[path] = sources[path].replace(old, new)
    tri = _module("feeds.triage", TRIAGE_SRC, sources[TRIAGE_SRC])
    feeds.triage = tri
    return tri, _module("feeds_server_under_test", SERVER, sources[SERVER])


class Stub:
    """Stands in for feeds.http.get: the OFSI listing, the FAQ page for every www.gov.uk document URL --
    except the LAST of the twelve fetched items, which gets a distinct, byte-variant second document
    (its own sha256, and ITEM_B_QUOTE, a sentence the shared document never holds), so a quote checked
    against the wrong item's pinned document is something the guard can actually catch (fix round 1)."""

    def __init__(self) -> None:
        self.listing = (FIX / "feeds" / "ofsi.atom").read_bytes()
        self.doc = (FIX / "html" / "ofsi_uk_financial_sanctions_faqs.html").read_bytes()
        self.doc2 = self.doc.replace(
            b"OFSI publishes FAQs providing short-form guidance and technical information on "
            b"financial sanctions.",
            ITEM_B_QUOTE.encode("utf-8"),
        )
        if self.doc2 == self.doc:
            raise SystemExit("fixture swap matched nothing: the guard's premise of two distinct "
                             "documents is false")
        self.distinct_url = SOURCES["ofsi"].parse(self.listing)[11].url  # keys[11]: the last of the 12 fetched
        self.calls = []

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append(url)
        if url == SOURCES["ofsi"].listing_url:
            return fh.Fetched(url, url, "application/atom+xml", self.listing)
        if url == self.distinct_url:
            return fh.Fetched(url, url, "text/html", self.doc2)
        if url.startswith("https://www.gov.uk/"):
            return fh.Fetched(url, url, "text/html", self.doc)
        raise fh.FetchRefused("no route for %s" % url)


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


def checks(tri, fs) -> list:
    out = []
    stub = Stub()
    before = git_status()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fs.HTTP_GET, fs.INBOX_ROOT, fs.SEEN_PATH = stub, tmp / "inbox", tmp / "ledger.json"
        fs.SEEN_PATH.write_text(ledger.dump([]), encoding="utf-8")
        lines = lambda: [json.loads(l) for l in  # noqa: E731
                         (tmp / "inbox" / RUN / "triage.jsonl").read_text(encoding="utf-8").splitlines()
                         if l.strip()] if (tmp / "inbox" / RUN / "triage.jsonl").exists() else []

        def call(coro):
            try:
                return asyncio.run(coro)
            except Exception as exc:  # a mutation that makes the code raise must not stop the guard
                return "RAISED %s: %s" % (type(exc).__name__, exc)

        def triage(key, verdict, reason, quote):
            return call(fs.triage(fs.TriageInput(item_key=key, verdict=verdict, reason=reason, quote=quote)))

        def read(key, page):
            return call(fs.read_page(fs.ReadPageInput(item_key=key, page=page)))

        os.environ.pop(fs.RUN_ENV, None)
        said = triage("ofsi:0000000000000000", "relevant", "r", PAGE1_QUOTE)
        out.append((said.startswith("Rejected") and not (tmp / "inbox").exists(),
                    "with no run identity triage is refused and nothing is written", said[:80]))
        said = read("ofsi:0000000000000000", 1)
        out.append((said.startswith("Rejected") and not (tmp / "inbox").exists(),
                    "with no run identity feeds_read_page is refused and nothing is written", said[:80]))

        os.environ[fs.RUN_ENV] = RUN
        call(fs.list_new(fs.ListNewInput(source="ofsi")))
        keys = [it.key for it in SOURCES["ofsi"].parse(stub.listing)]
        refusals = []

        said = read(keys[0], 1)
        refusals.append(said)
        out.append((said.startswith("Rejected") and "feeds_fetch" in said, "a page cannot be read before a fetch",
                    said[:90]))
        said = triage(keys[0], "relevant", "Describes sanctions guidance.", PAGE1_QUOTE)
        refusals.append(said)
        out.append((said.startswith("Rejected") and not lines(), "an item cannot be triaged before a fetch",
                    said[:90]))

        for k in keys[:12]:
            call(fs.fetch(fs.FetchInput(item_key=k)))
        said = read(keys[0], 1)
        out.append((said.startswith("=== PAGE 1 of 2 ===") and PAGE1_QUOTE in said,
                    "feeds_read_page returns the pinned page the quote is checked against", said[:60]))
        said = read(keys[0], 3)
        refusals.append(said)
        out.append((said.startswith("Rejected") and "2 page" in said, "a page past the end is refused", said[:80]))

        said = triage(keys[0], "relevant", "Describes shell companies.", FABRICATED)
        refusals.append(said)
        out.append((said.startswith("Rejected") and not lines(),
                    "a quote that is not in the pinned document is refused and nothing is written", said[:90]))

        said = triage(keys[0], "relevant", "Wrong item's document.", ITEM_B_QUOTE)
        refusals.append(said)
        out.append((said.startswith("Rejected") and not lines(),
                    "a quote true only of item B's pinned document is refused when given for item A",
                    said[:90]))

        said = triage(keys[0], "not_relevant", "FAQ index page; no method, red flag or case.", PAGE1_QUOTE)
        got = lines()
        out.append((said.startswith("Recorded") and len(got) == 1 and got[0]["verdict"] == "not_relevant"
                    and got[0]["found_on"] == [1] and got[0]["document_sha256"],
                    "a not_relevant verdict with a real quote is recorded, with the page it was found on", said[:90]))
        said = triage(keys[0], "relevant", "Second thoughts.", PAGE1_QUOTE)
        refusals.append(said)
        got = lines()
        out.append((said.startswith("Rejected") and len(got) == 1 and got[0]["verdict"] == "not_relevant",
                    "a second verdict for the same item is refused; the first stands on disk", said[:90]))

        said = triage(keys[1], "relevant", "Lists Russia-section FAQs.", PAGE2_QUOTE)
        got = lines()
        out.append((said.startswith("Recorded") and got[-1]["found_on"] == [2],
                    "a quote on page 2 is found there", said[:90]))

        said = triage(keys[2], "relevant", "x" * 301, PAGE1_QUOTE)
        refusals.append(said)
        ok301 = said.startswith("Rejected")
        said = triage(keys[2], "relevant", "x" * 300, PAGE1_QUOTE)
        out.append((ok301 and said.startswith("Recorded"), "a 301-character reason is refused; 300 is accepted",
                    said[:60]))

        said = triage(keys[10], "relevant", "   ", PAGE1_QUOTE)
        refusals.append(said)
        out.append((said.startswith("Rejected") and len(lines()) == 3,
                    "an empty or whitespace-only reason is refused and nothing is written", said[:80]))

        said = triage(keys[3], "relevant", "Short quote.", PADDED)
        refusals.append(said)
        out.append((said.startswith("Rejected"), "a quote under 10 characters once stripped is refused, padding "
                    "or not", said[:80]))
        said = triage(keys[3], "maybe", "Unsure.", PAGE1_QUOTE)
        refusals.append(said)
        out.append((said.startswith("Rejected"), "a verdict other than relevant | not_relevant is refused", said[:80]))
        said = triage("ofsi:ffffffffffffffff", "relevant", "Unlisted.", PAGE1_QUOTE)
        refusals.append(said)
        out.append((said.startswith("Rejected"), "a key this run did not list is refused", said[:80]))

        pinned = tmp / "inbox" / RUN / json.loads((tmp / "inbox" / RUN / "items.json").read_text(
            encoding="utf-8"))["sources"]["ofsi"]["items"][3]["document"]["path"]
        original = pinned.read_bytes()
        pinned.write_bytes(original.replace(b"short-form guidance", b"short-form GUIDANCE"))
        said = triage(keys[3], "relevant", "Tampered.", PAGE1_QUOTE)
        refusals.append(said)
        said_read = read(keys[3], 1)
        pinned.write_bytes(original)
        out.append((said.startswith("Rejected") and said_read.startswith("Rejected"),
                    "a pinned document whose bytes changed is refused by triage and by read", said[:90]))

        said = triage(keys[11], "relevant", "Distinct fixture, correctly bound.", ITEM_B_QUOTE)
        got = lines()
        out.append((said.startswith("Recorded") and len(got) == 4 and got[-1]["key"] == keys[11]
                    and got[-1]["found_on"] == [1],
                    "the same quote is accepted when given for the item it actually belongs to (item B)",
                    said[:90]))

        for k in keys[3:9]:
            triage(k, "not_relevant", "General licence; no method, red flag or case.", PAGE1_QUOTE)
        said = triage(keys[9], "relevant", "Eleventh.", PAGE1_QUOTE)
        refusals.append(said)
        got = lines()
        out.append((len(got) == 10 and said.startswith("Rejected") and "cap" in said,
                    "the 11th verdict in one run is refused: the cap is 10", "%d verdicts; %s" % (len(got), said[:60])))
        out.append((sum(1 for g in got if g["verdict"] == "not_relevant") == 7,
                    "every not_relevant verdict stays in triage.jsonl (7 of the 10)",
                    "%d not_relevant" % sum(1 for g in got if g["verdict"] == "not_relevant")))

        try:
            rec = tri.reconcile(RUN, expected=keys[:12] + ["fincen:0123456789abcdef"], root=tmp / "inbox")
        except ValueError as exc:  # a second line for one item makes load() refuse the file
            rec = {"unfinished": None, "never_listed": None, "triaged": [], "error": str(exc)}
        out.append((rec["unfinished"] == sorted(keys[9:11] + keys[12:] + ["fincen:0123456789abcdef"])
                    and rec["never_listed"] == ["fincen:0123456789abcdef"] and len(rec["triaged"]) == 10,
                    "reconcile lists every untriaged item, and an expected item never listed, as unfinished",
                    "%d unfinished" % len(rec["unfinished"] or [])))

        classified = [telemetry.classify_response({"content": [{"type": "text", "text": r}]})[0] for r in refusals]
        out.append((len(refusals) >= 10 and all(r.startswith("Rejected:") for r in refusals)
                    and set(classified) == {telemetry.REFUSED}
                    and telemetry.classify_response("Recorded: x")[0] == telemetry.SUCCESS,
                    "every refusal starts 'Rejected:' and telemetry counts it REFUSED (%d refusals)" % len(refusals),
                    sorted(set(classified))))
        out.append((tri.REJECTED == telemetry.REFUSAL_PREFIX == "Rejected:" and fs.feeds_triage is tri,
                    "feeds.triage.REJECTED is the one prefix constant, equal to what "
                    "agents.telemetry.classify_response counts REFUSED, and the server's own refusals are "
                    "built from it rather than a second literal", tri.REJECTED))

        try:
            fs.TriageInput(item_key=keys[0], verdict="relevant", reason="r", quote=PAGE1_QUOTE, url="https://x")
            extra_refused = False
        except Exception:
            extra_refused = True
        out.append((extra_refused, "an extra argument is refused by the input model", ""))

        written = [str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file()]
        out.append((all(w == "ledger.json" or w.startswith("inbox/%s/" % RUN) for w in written)
                    and "inbox/%s/triage.jsonl" % RUN in written,
                    "every file written is inside this run's temporary inbox", "%d files" % len(written)))
    os.environ.pop(fs.RUN_ENV, None)
    out.append((git_status() == before, "the repository's git status is unchanged", ""))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin feeds_triage and feeds_read_page")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    tri, fs = load_pair(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(tri, fs):
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
