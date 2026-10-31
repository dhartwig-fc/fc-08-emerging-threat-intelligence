# Wolfsberg swept, FATF by hand: Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Wolfsberg becomes the tenth live source, reaching its PDFs through one declared hop; FATF arrives as an owner-downloaded PDF through an intake that fetches nothing; the Chrome script that disguised automation is retired and guarded against.

**Architecture:** Wolfsberg is one `Source` entry, one HTML listing parser and one new optional `Source.document_via` field. Extraction follows exactly one same-host link under that prefix when an item page links no PDF. FATF gets a `MANUAL_SOURCES` declaration and `tools/intake_document.py`. That tool writes one run in the Friday run's shape: the owner's selection becomes a triage line held to the quote rule, then the Friday run's own extraction and `accept_run` take over. `reconcile_run` learns that a manual run has no orchestrator session.

**Tech Stack:** Python 3 stdlib (`html.parser`, `urllib.parse`), pypdf via `schemas.citation_match.PageIndex`, the fc-08 guards in `evals/`, and `tools/check_all.py` as the pre-commit hook.

**Spec:** `docs/superpowers/specs/2026-10-31-wolfsberg-swept-fatf-by-hand-design.md` (approved 2026-10-31). Branch `sdd/wolfsberg-fatf`, stacked on `sdd/six-regulators` (PR #3).

---

## Global constraints

- Python is `~/fc-08-schedule/.venv/bin/python`, written `$PY` below.
- Every guard run and every commit goes under `env -u ANTHROPIC_API_KEY`. With the key set, the scheduled-run checks refuse.
- Every commit also puts the venv first on `PATH` (`PATH=~/fc-08-schedule/.venv/bin:$PATH`). The hook calls `python3`; without the venv, 29 guards fail on missing packages (measured 2026-10-31).
- Commit from this FULL clone (`~/fc-08-scan-mechanics`), staged explicitly, never `git commit -a`, never `--no-verify`, no Co-Authored-By trailer, no `.bak` or `_before_*` files.
- **Nothing in fc-08 fetches fatf-gafi.org.** No code, test, fixture or script may launch a browser, disguise automation, or request a fatf-gafi.org URL.
- The fixtures under `tests/fixtures/feeds/` are byte-for-byte recordings. Never edit one.
- Nothing is pushed or published without the owner's go.
- **One commit at the end (R1, carried from the six-regulators plan).** The hook runs every guard on the working tree, and the scan page's publish gates go red the moment `SOURCES` gains Wolfsberg, until the page is rebuilt AND republished. Tasks 1-4 verify with targeted guards and do not commit; Task 5 republishes, then commits once.

## Rulings (made while planning)

- **R1. One commit at the end.** See above.
- **R2. Spec correction: Wolfsberg's dates.** The ten listed items run from 2025-06-17 to 2026-07-15, not 2025-08-27 to 2026-07-15. Re-measured from the fixture; nothing depends on the old figure.
- **R3. Manual runs use the normal run id.**
  - The spec named the folder `inbox/manual-<date>-<hash>/`. That cannot work: `inbox.RUN_ID`, `FeedsRun.__post_init__` and `inbox.run_dir` all require `feeds-YYYY-MM-DD-xxxxxx`.
  - So a manual run takes `inbox.mint_run_id(today)` and marks itself in `items.json` with `"manual": {"by": "owner", "at": <iso>}`.
  - Cost if wrong: a manual run lists beside Friday runs in `accept_run --pending`. It reads `manual` there, so it is not mistaken for one.
- **R4. The owner's selection is a real triage line.**
  - `accept_run` refuses an extracted item with no verdict, and `reconcile_run` reports a request with no relevant verdict.
  - So the intake records the selection through `feeds.triage.decide`: verdict `relevant`, reason `owner-selected: <--reason>`, and a `--quote` the owner copies verbatim from the PDF, checked by the same `find_quote` every agent verdict passes.
  - `decide()` gains a keyword `by`. `"owner"` adds `"by": "owner"` to the line; the default leaves every agent line byte-identical.
  - The spec's "triage: owner-selected" is this line.
  - Cost if wrong: the owner types one sentence they already read.
- **R5. `reconcile_run` treats a manual run as having no orchestrator by design.** Four sites change, all gated on `state.get("manual")`: `ended`, the request-without-outcome check, "the orchestrator session left no telemetry", and the FAILED test. `never_listed` is empty for a manual run. The source status in `items.json` is `"ok"` (not the spec's `"manual"`), so `source_failures` needs no change.
- **R6. `accept_run` changes in two small places, not zero.**
  - `PUBLISHERS` gains `wolfsberg` and `fatf`.
  - An owner-selected verdict (`verdict.get("by") == "owner"`) is recorded as tier `owner intake`, with the selection rationale `owner intake run <id>, item <key>: owner-selected: …`. A live item keeps the existing strings byte for byte.
  - The spec said "unchanged"; leaving "live feed" on a FATF document would misstate its provenance in the advisory list.
- **R7. The hop's PDF link is percent-encoded before it is fetched.**
  - Wolfsberg writes its PDF link with raw spaces (`…/Wolfsberg Group - Risk Based Approach Guidance _June2026.pdf`, measured 2026-10-31).
  - `http.client` refuses a URL containing a space, so the hop applies `quote(path, safe="/%")` to the one URL it chose. `linked_pdfs()` is untouched, so no other source's recorded links change.
- **R8. `linked_pages()` does not filter hosts.** Extraction filters them with `_on_hosts`, the one allowlist predicate. `check_feeds_extract --mutate own-host-rule` exists because a second copy of that rule drifted once.
- **R9. The intake reuses the Friday run's machinery.** It holds the inbox lock (`friday_run.run_lock`) and points telemetry at the run folder. It allocates with `extraction.allocate_advisory_id`, queues with the unchanged `extraction.request` (the pinned PDF is `kind == "pinned"`, so it fetches nothing), extracts with `friday_run.extract_one`, and checks citations with `friday_run.citation_check`. Nothing is duplicated.
- **R10. Accepting a manual run is not guarded end to end.** `accept_run.plan` needs a validating `AdvisoryRecord`, placed citations and a gate-clean queue, which a cold guard cannot produce without a real extraction. The guard covers everything up to the run's reconcile status (COMPLETE). The first real FATF intake is the end-to-end check, and Task 6 names it as an owner step.

## File structure

| File | Change | Task |
|---|---|---|
| `tests/fixtures/feeds/wolfsberg_news.html` | recorded listing (committed with this plan) | 1 |
| `tests/fixtures/feeds/wolfsberg_item_rba.html` | recorded item page (committed with this plan) | 2 |
| `tests/fixtures/feeds/wolfsberg_resource_rba_205.html` | recorded resource page (committed with this plan) | 2 |
| `tests/fixtures/feeds/README.md` | three rows | 1 |
| `feeds/sources.py` | `parse_wolfsberg`, `wolfsberg` Source, ORDER, `document_via`, `linked_pages`, `ManualSource`, `MANUAL_SOURCES` | 1, 2, 3 |
| `feeds/triage_rules.json` | `wolfsberg` rule | 1 |
| `tools/accept_run.py` | PUBLISHERS + owner-intake tier | 1, 3 |
| `evals/check_feed_adapters.py` | Wolfsberg snapshot, expected items, breaks, hosts; publishers include manual | 1, 3 |
| `evals/check_feeds_orchestrator.py` | re-pin the prompt hash ORDER moves | 1 |
| `mcp_server/feeds_server.py` | `_fetch` records `linked_pages` for a declaring source | 2 |
| `feeds/extraction.py` | `document_choice` via / ambiguous_via; `request()` hop; `_encoded` | 2 |
| `evals/check_document_hop.py` | new guard | 2 |
| `feeds/triage.py` | `decide(..., by=)` | 3 |
| `feeds/reconcile.py` | manual run has no orchestrator | 3 |
| `tools/intake_document.py` | new tool | 3 |
| `evals/check_intake.py` | new guard | 3 |
| `tools/fetch_fatf_via_chrome.js` | deleted | 4 |
| `evals/check_no_disguised_automation.py` | new guard | 4 |
| `tools/build_scan_demo.py`, `evals/check_scan_demo.py` | manual from `MANUAL_SOURCES` | 4 |
| `tools/check_all.py`, `evals/check_mutation_anchors.py` | register three guards | 2, 3, 4 |
| `CLAUDE.md` | three amendments + new rows | 4 |
| portfolio `projects/nexus/threat-intel/scan.html` | republished | 5 |

## Pre-flight: tasks that share a file

| Tasks | Shared | Produces → consumes | Finding |
|---|---|---|---|
| 1, 2, 3 | `feeds/sources.py` | 1 adds the `wolfsberg` Source positionally (7 args); 2 appends `"/resources/"` as the 8th | consistent: 2 edits 1's line |
| 1, 3 | `tools/accept_run.py` PUBLISHERS | 1 adds wolfsberg, 3 adds fatf | consistent |
| 1, 3 | `evals/check_feed_adapters.py` publisher_checks | 3 widens to `SOURCES ∪ MANUAL_SOURCES` | 3 must run after 1 |
| 2, 3, 4 | `tools/check_all.py`, `evals/check_mutation_anchors.py` | one registration each | additive |
| 3, 4 | `MANUAL_SOURCES` | 3 declares it, 4 reads it in the scan page | 4 after 3 |
| all | the scan page | its coverage reads `SOURCES` and `MANUAL_SOURCES` | rebuilt once, in 5 (R1) |

---

### Task 1: Wolfsberg, the tenth live source

**Files:**
- Modify: `feeds/sources.py` (after `parse_ofac`, the SOURCES dict, ORDER, the module docstring's measured counts)
- Modify: `feeds/triage_rules.json`, `tools/accept_run.py:118-122`
- Modify: `evals/check_feed_adapters.py` (SNAPSHOTS, EXPECTED, BREAKS, NEW_HOSTS)
- Modify: `evals/check_feeds_orchestrator.py` (the pinned prompt hash, if it moves)
- Modify: `tests/fixtures/feeds/README.md`

- [ ] **Step 1: Pin the fixture in the adapter guard (the failing test).** In `evals/check_feed_adapters.py`, add to `SNAPSHOTS`:

```python
             "wolfsberg": ("wolfsberg_news.html", "0f8707eb271f1de4f61c5e77904490bf382a49852ed8e712e731516c5b47e2a1"),
```

  Add to `EXPECTED`. The `ids` digest is computed in Step 4.

```python
    "wolfsberg": {"count": 10, "ids": "PIN-IN-STEP-4",
                  "first": {"item_id": "guidance-on-the-provision-of-banking-services",
                            "title": "The Wolfsberg Group publishes Guidance on the provision of banking services to "
                                     "non-bank payment service providers (PSPs)",
                            "url": "https://wolfsberg-group.org/news/guidance-on-the-provision-of-banking-services",
                            "published": "2026-07-15", "summary": ""},
                  "last": {"item_id": "the-wolfsberg-group-celebrates-its-25th-anniversary-and-welcomes-new-management-"
                                      "committee-members",
                           "title": "The Wolfsberg Group Celebrates its 25th Anniversary and Welcomes New Management "
                                    "Committee Members",
                           "url": "https://wolfsberg-group.org/news/the-wolfsberg-group-celebrates-its-25th-anniversary-"
                                  "and-welcomes-new-management-committee-members",
                           "published": "2025-06-17"}},
```

  Add to `BREAKS`:

```python
    ("marker gone", "wolfsberg", r'class="news-item', 'class="renamed-item'),
    ("an item without a date", "wolfsberg", r"<!--\[-->2026-07-15<!--\]-->", "<!--[-->soon<!--]-->"),
    ("an item with an empty title", "wolfsberg",
     r"<!--\[-->The Wolfsberg Group publishes Guidance on the provision of banking services to non-bank payment service "
     r"providers \(PSPs\)<!--\]-->", "<!--[--> <!--]-->"),
    ("a body ending inside an open news card", "wolfsberg",
     r'(?s)(<a href="/news/the-wolfsberg-group-celebrates[^"]*"[^>]*></a>).*', r"\1"),
```

  Add to `NEW_HOSTS`:

```python
             "wolfsberg": ({"wolfsberg-group.org"}, {"db.wolfsberg-group.org"}),
```

- [ ] **Step 2: Run it and watch it fail.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_feed_adapters.py`
  Expected: FAIL. `wolfsberg` is not in `SOURCES` (a KeyError or a FAIL line naming wolfsberg).

- [ ] **Step 3: Write the parser and the Source.** In `feeds/sources.py`, after `parse_ofac`:

```python
WOLFSBERG_BASE = "https://wolfsberg-group.org"
DAY_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_wolfsberg(raw: bytes) -> List[FeedItem]:
    """The Wolfsberg Group's /news page, server-rendered (measured 2026-10-31): one <article class="news-item"> per
    item, holding a /news/<slug> link, the date in its first <span> as YYYY-MM-DD and the title in its <h3>."""
    events = _events("wolfsberg", raw)
    if not any(k == "start" and t == "article" and "news-item" in _classes(a) for k, t, a in events):
        raise LayoutChanged("wolfsberg: the news cards (article.news-item) are missing")
    items, card = [], None
    for kind, tag, attrs in events:
        if kind == "start" and tag == "article" and "news-item" in _classes(attrs):
            card = {"href": None, "date": [], "title": [], "in": None}
        elif card is None:
            continue
        elif kind == "start" and tag == "a" and card["href"] is None \
                and (attrs.get("href") or "").startswith("/news/"):
            card["href"] = attrs["href"]
        elif kind == "start" and tag == "span" and not card["date"] and card["in"] is None:
            card["in"] = "date"
        elif kind == "start" and tag == "h3" and not card["title"] and card["in"] is None:
            card["in"] = "title"
        elif kind == "end" and tag in ("span", "h3"):
            card["in"] = None
        elif kind == "text" and card["in"]:
            card[card["in"]].append(tag)
        elif kind == "end" and tag == "article":
            if not card["href"]:
                raise LayoutChanged("wolfsberg: a news card has no /news/ link")
            date = "".join(card["date"]).strip()
            if not DAY_ONLY.match(date):
                raise LayoutChanged("wolfsberg: the card for %s has no date" % card["href"])
            items.append(FeedItem("wolfsberg", card["href"].rstrip("/").rsplit("/", 1)[1],
                                  _title("wolfsberg", card["title"], card["href"]),
                                  urljoin(WOLFSBERG_BASE, card["href"]), date))
            card = None
    if card is not None:  # the body ended inside a card: truncated, never a card to drop
        raise LayoutChanged("wolfsberg: the listing ends inside an open news card (a truncated body)")
    if not items:
        raise LayoutChanged("wolfsberg: the cards are present but none parsed")
    return items
```

  Add to `SOURCES`, after `amla`:

```python
    "wolfsberg": Source("wolfsberg", "https://wolfsberg-group.org/news", "html", frozenset({"text/html"}),
                        frozenset({"wolfsberg-group.org"}), parse_wolfsberg, frozenset({"db.wolfsberg-group.org"})),
```

  Append to ORDER (appending keeps every earlier source's position):

```python
ORDER = ("ofsi", "fincen", "ofac", "otsi", "fca", "nca", "eu_council", "eba", "amla", "wolfsberg")
```

  In the module docstring's measured counts line, append `; 2026-10-31: Wolfsberg 10`.

  If `_events` does not emit `("text", data, …)` for text inside `<span>` because of the `<!--[-->` comments, check how `parse_fincen` reads text (it appends `tag` on `kind == "text"`) and match that. Do not regex the HTML.

- [ ] **Step 4: Pin the ids digest.** Read `adapter_checks` (`evals/check_feed_adapters.py:200-240`) for the expression it digests ids with. Compute it over `parse_wolfsberg(raw("wolfsberg"))` with that same expression and replace `"PIN-IN-STEP-4"`. Then run:

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_feed_adapters.py`
  Expected: the wolfsberg contract, breaks and hosts PASS. The publisher check and the rules check FAIL (Steps 5-6).

- [ ] **Step 5: Publisher and triage rule.** In `tools/accept_run.py` PUBLISHERS, add `"wolfsberg": "The Wolfsberg Group"`. In `feeds/triage_rules.json`, add after `amla`:

```json
  "wolfsberg": "A Wolfsberg Group page is relevant when it is guidance, a statement, principles or FAQs on financial crime controls or typologies, or a note on a specific crime. Governance news (appointments, anniversaries, membership and forum announcements) is not relevant."
```

- [ ] **Step 6: Fixture README rows.** Append to the table in `tests/fixtures/feeds/README.md`, under a line `Fetched 2026-10-31 through feeds.http.get (fc-08's own user agent), one request each:`

```markdown
| `wolfsberg_news.html` | https://wolfsberg-group.org/news (The Wolfsberg Group) | `evals/check_feed_adapters.py` |
| `wolfsberg_item_rba.html` | https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach | `evals/check_document_hop.py` |
| `wolfsberg_resource_rba_205.html` | https://wolfsberg-group.org/resources/rba/205 | `evals/check_document_hop.py` |
```

- [ ] **Step 7: Every guard that pins the source list or the prompt.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_feed_adapters.py && for g in feeds_orchestrator feeds_server feeds_triage feeds_runner feeds_ledger friday_run accept_run; do env -u ANTHROPIC_API_KEY $PY evals/check_$g.py >/dev/null || echo "FAIL $g"; done`
  Expected: check_feed_adapters PASS (plain and `--mutate hand-list`, `--mutate rule-missing`, `--mutate publisher-missing` each HELD).

  If `check_feeds_orchestrator` fails on a pinned prompt hash, that is `named()` gaining "wolfsberg". Print `of.PROMPT_SHA256` and `of.FULL_PROMPT_SHA256` and re-pin whichever the guard holds, recording old and new values for the final commit message. Any other failure is a real defect: stop and diagnose.

  **Do not commit (R1).**

---

### Task 2: the document hop

**Files:**
- Modify: `feeds/sources.py` (Source gains `document_via`; `linked_pages()` beside `linked_pdfs()`; the wolfsberg entry gains `"/resources/"`)
- Modify: `mcp_server/feeds_server.py` `_fetch` (around :120-123)
- Modify: `feeds/extraction.py` (`document_choice`, `request`, a new `_encoded`, imports)
- Create: `evals/check_document_hop.py`
- Modify: `tools/check_all.py` GUARDS, `evals/check_mutation_anchors.py` CHECKED

- [ ] **Step 1: Write the guard (the failing test).** Create `evals/check_document_hop.py`:

```python
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
from feeds import inbox  # noqa: E402
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
```

  `via-any-host` and `hop-undeclared` share an anchor, which is allowed: `check_mutation_anchors` requires only that each label's `old` occurs exactly once in its TARGET, and it does.

  Then copy the `load()` loader **verbatim** from `evals/check_feed_adapters.py:180-193`, including the `source.count(old) != 1` refusal and the package attach, and add:

```python
class Stub:
    """http_get: serves the recorded resource page, then a one-page PDF; records every call."""

    def __init__(self, resource: bytes):
        self.calls, self.resource = [], resource

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append((url, frozenset(allowed_hosts), frozenset(allowed_types)))
        if "text/html" in allowed_types:
            return types.SimpleNamespace(body=self.resource, content_type="text/html", final_url=url)
        return types.SimpleNamespace(body=tiny_pdf(["Wolfsberg Group guidance on the risk-based approach."]),
                                     content_type="application/pdf", final_url=url)


def run_item(ex, src_mod, tmp: Path, source: str, page: bytes, linked_pages: list, resource: bytes, run: str = RUN):
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
    stub = Stub(resource)
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
                    and "text/html" in stub.calls[0][2],
                    "the resource page is fetched first, on the source's hosts, as HTML", calls))
        out.append((len(stub.calls) == 2 and stub.calls[1][:2] == (PDF_ENCODED, wb.document_hosts),
                    "then the ONE PDF on the document hosts, percent-encoded", calls))
        via = (line or {}).get("via") or {}
        out.append((ok and line["chosen"] == "via" and via.get("sha256") == hashlib.sha256(resource).hexdigest()
                    and via.get("url") == RES_URL and not line["error"],
                    "the request records the hop (url, sha256) and no error", msg))
    with tempfile.TemporaryDirectory() as t:
        two = [RES_URL, "https://wolfsberg-group.org/resources/rba/206"]
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page, two, resource)
        out.append((not ok and not stub.calls and msg.startswith(feeds_triage.REJECTED),
                    "two resource links are refused before any fetch", msg))
    with tempfile.TemporaryDirectory() as t:
        off = resource.replace(b"https://db.wolfsberg-group.org/assets/", b"https://elsewhere.example/assets/")
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page, pages, off)
        out.append((len(stub.calls) == 1 and line is not None and bool(line["error"])
                    and line["error"].startswith(feeds_triage.REJECTED),
                    "a resource page with no PDF on the document hosts is refused and recorded", msg))
    with tempfile.TemporaryDirectory() as t:
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "wolfsberg", item_page,
                                         ["https://evil.example/resources/rba/205"], resource)
        out.append((not stub.calls and line is not None and line["chosen"] == "pinned",
                    "a resource link on another host is not followed", msg))
    with tempfile.TemporaryDirectory() as t:
        (ok, msg), stub, line = run_item(ex, src_mod, Path(t), "fincen", item_page, [RES_URL], resource)
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
```

  If importing `check_document_pages` runs anything beyond definitions, copy `tiny_pdf` (`evals/check_document_pages.py:77`) verbatim into this file instead.

- [ ] **Step 2: Run it and watch it fail.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_document_hop.py`
  Expected: FAIL. `feeds.sources` has no `linked_pages` (an AttributeError).

- [ ] **Step 3: The Source field and the link lister.** In `feeds/sources.py`, add to `Source` after `document_hosts`:

```python
    # One page between an item and its PDF (Wolfsberg, measured 2026-10-31): a path prefix on the source's own hosts.
    # When an item's page links no PDF on document_hosts, exactly ONE link under this prefix is followed to the page
    # that does (feeds/extraction.py). Empty: no hop -- the behaviour of every source before it.
    document_via: str = ""
```

  Append `, "/resources/"` as the eighth argument of the wolfsberg entry. Add beside `linked_pdfs`:

```python
def linked_pages(raw: bytes, base_url: str, prefix: str) -> List[str]:
    """Absolute URLs an HTML page links to whose path starts with `prefix`, first occurrence order. Listed, never
    fetched; the host is NOT checked here -- extraction asks feeds.http's one allowlist predicate (plan R8)."""
    if not prefix:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    parser = _Links()
    parser.feed(text)
    parser.close()
    out: List[str] = []
    for href in parser.hrefs:
        url = urljoin(base_url, href)
        if urlsplit(url).path.startswith(prefix) and url not in out:
            out.append(url)
    return out
```

- [ ] **Step 4: Record the links at fetch.** In `mcp_server/feeds_server.py` `_fetch`, directly after the `item["document"] = {…}` assignment and before `inbox.save`:

```python
    if src.document_via and not is_pdf:  # only a declaring source's documents gain the key; no other bytes move
        item["document"]["linked_pages"] = linked_pages(got.body, got.final_url, src.document_via)
```

  Add `linked_pages` to the import from `feeds.sources` there.

- [ ] **Step 5: The hop in extraction.** In `feeds/extraction.py`, replace `document_choice` with:

```python
def document_choice(item: dict) -> Tuple[str, List[str], List[str]]:
    """(kind, candidate URLs, ignored URLs) for an item's pinned document; kind is pinned|linked|ambiguous|via|
    ambiguous_via. "via": the page links no PDF on the document hosts but exactly one page under the source's
    document_via on its own hosts, which request() follows to the PDF (spec 2026-10-31 §1)."""
    doc = item["document"]
    if doc["content_type"] == "application/pdf":
        return "pinned", [], []
    src = SOURCES[item["source"]]
    links = doc.get("linked_pdfs") or []
    ok = [u for u in links if _on_hosts(u, src.document_hosts)]
    ignored = [u for u in links if u not in ok]
    if ok:
        return ("linked" if len(ok) == 1 else "ambiguous"), ok, ignored
    via = [u for u in (doc.get("linked_pages") or []) if src.document_via and _on_hosts(u, src.hosts)]
    if via:
        return ("via" if len(via) == 1 else "ambiguous_via"), via, ignored
    return "pinned", [], ignored
```

  In `request()`, directly after the existing `if kind == "ambiguous":` block:

```python
    if kind == "ambiguous_via":
        return False, ("%s %s's page links %d pages under %s on %s's hosts (%s); which one holds the publication is "
                       "a person's call, not this run's." % (REJECTED, key, len(urls), SOURCES[item["source"]].document_via,
                                                             item["source"], ", ".join(urls)))
```

  After the `entry = {…}` line and before `if kind == "pinned":`:

```python
    if kind == "via":
        src = SOURCES[item["source"]]
        try:
            hop = http_get(urls[0], allowed_hosts=src.hosts, allowed_types=HTML_TYPES, max_bytes=MAX_DOCUMENT_BYTES)
        except FetchRefused as exc:
            entry["error"] = "the resource page could not be fetched: %s" % exc
            _append(run_id, REQUESTS, entry, root)
            return True, "Failed: %s is queued but its resource page could not be fetched (%s); it will be reported." % (
                key, exc)
        hop_sha = hashlib.sha256(hop.body).hexdigest()
        entry["via"] = {"url": hop.final_url, "sha256": hop_sha,
                        "path": inbox.write_file(run_id, "docs/%s.html" % hop_sha, hop.body, root)}
        pdfs = [u for u in linked_pdfs(hop.body, hop.final_url) if _on_hosts(u, src.document_hosts)]
        if len(pdfs) != 1:
            entry["error"] = ("%s %s's resource page %s links %d PDFs on %s's document hosts; the publication is "
                              "identified only by exactly one." % (REJECTED, key, hop.final_url, len(pdfs),
                                                                    item["source"]))
            _append(run_id, REQUESTS, entry, root)
            return True, entry["error"]
        urls = [_encoded(pdfs[0])]
```

  The existing `else:` branch (the linked-PDF fetch) now serves both `linked` and the resolved `via`. Change its success message condition from `kind == "linked"` to `kind in ("linked", "via")`. Add near the constants and imports:

```python
HTML_TYPES = frozenset({"text/html"})


def _encoded(url: str) -> str:
    """A link as a page writes it ("…/Risk Based Approach Guidance _June2026.pdf", Wolfsberg, measured 2026-10-31),
    made fetchable: http.client refuses a URL with a space, so the path is percent-encoded; an encoded one is
    unchanged (plan R7)."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(parts.path, safe="/%")))
```

```python
from urllib.parse import quote, urlsplit, urlunsplit
from feeds.sources import MAX_DOCUMENT_BYTES, SOURCES, linked_pdfs
```

  Grep `feeds/report.py` and `tools/accept_run.py` for `"chosen"`. If either maps its values to text, add `"via": "via its resource page"`.

- [ ] **Step 6: Register the guard.** In `tools/check_all.py` GUARDS, after `check_feeds_extract`:

```python
    ("check_document_hop", ["evals/check_document_hop.py"], "cold"),
```

  In `evals/check_mutation_anchors.py` CHECKED:

```python
    "check_document_hop.py": (("MUTATIONS", PATH_OLD, None, (ONCE,)),),
```

  If that guard pins a count of checked guards in a literal (its docstring says "All 13"), update the literal and the docstring together.

- [ ] **Step 7: Run it, then each mutation.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_document_hop.py && for m in via-first-of-many via-any-host via-pdf-off-hosts no-encoding hop-undeclared; do env -u ANTHROPIC_API_KEY PYTHONPYCACHEPREFIX=/tmp/hop-$m $PY evals/check_document_hop.py --mutate $m | tail -1; done`
  Expected: `HOLDS`, then five lines of `HELD: …`. Each mutation must turn at least one clause red, and the clause it turns red should be the one its label names.

  Run: `for g in feeds_extract feeds_server mutation_anchors feed_adapters; do env -u ANTHROPIC_API_KEY $PY evals/check_$g.py >/dev/null || echo "FAIL $g"; done`
  Expected: no output. (`check_feeds_extract` proves the linked and pinned paths are unchanged for every other source.)

  **Do not commit (R1).**

---

### Task 3: FATF by hand, the intake

**Files:**
- Modify: `feeds/sources.py` (`ManualSource`, `MANUAL_SOURCES`, the overlap refusal)
- Modify: `feeds/triage.py` `decide()` (the `by` keyword)
- Modify: `feeds/reconcile.py` `reconcile_run` (R5)
- Modify: `tools/accept_run.py` (PUBLISHERS `fatf`, the owner-intake tier, R6)
- Modify: `evals/check_feed_adapters.py` `publisher_checks` (`SOURCES ∪ MANUAL_SOURCES`)
- Create: `tools/intake_document.py`, `evals/check_intake.py`
- Modify: `tools/check_all.py`, `evals/check_mutation_anchors.py`

- [ ] **Step 1: Write the guard (the failing test).** Create `evals/check_intake.py`:

```python
"""
Pin tools/intake_document.py (spec 2026-10-31 §2): a document the owner downloaded becomes one run in the Friday
run's shape, and nothing is fetched.

Usage:
    python evals/check_intake.py
    python evals/check_intake.py --mutate owner-as-agent             # the selection is recorded as the agent's
    python evals/check_intake.py --mutate no-pdf-check               # a file that is not a PDF is taken in
    python evals/check_intake.py --mutate any-url-host               # a provenance URL on any host is accepted
    python evals/check_intake.py --mutate ledger-unchecked           # a document already in the ledger is taken in again
    python evals/check_intake.py --mutate quote-unchecked            # a quote on no page reaches the run
    python evals/check_intake.py --mutate manual-needs-orchestrator  # reconcile calls a manual run FAILED

WHAT IT HOLDS, in a temporary inbox with a stub extractor (cold; feeds.http.get is replaced by one that raises):
  shape      the run is marked manual; its one item's document carries exactly a live item's keys plus
             delivered_by; the selection is a triage line by the owner, reason "owner-selected: ...", its quote
             found on a page; reconcile_run calls the run COMPLETE; report.md is written;
  refusals   each refused BEFORE anything is written: a file that is not a PDF; a URL over http; a URL on
             another host; a live source; a quote on no page; a document already in the ledger;
  overlap    feeds.sources refuses at import a source declared both live and manual.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "tools"))

from check_document_pages import tiny_pdf  # noqa: E402
from feeds import http as feeds_http, inbox, ledger, reconcile  # noqa: E402
from feeds import triage as feeds_triage  # noqa: E402

INTAKE = ROOT / "tools" / "intake_document.py"
RECONCILE = ROOT / "feeds" / "reconcile.py"
SOURCES_PY = ROOT / "feeds" / "sources.py"
LIVE_RUN = ROOT / "data" / "feeds" / "runs" / "feeds-2026-10-30-b2a3cf" / "items.json"  # tracked
SENTENCE = "Professional money launderers use trade-based schemes and shell companies to move proceeds."
URL = "https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Professional-Money-Laundering.pdf"
ITEM_ID = "/content/dam/fatf-gafi/reports/Professional-Money-Laundering.pdf"
MUTATIONS = {
    "owner-as-agent": (INTAKE, 'by="owner"', 'by="agent"'),
    "no-pdf-check": (INTAKE, 'if not body.startswith(b"%PDF-"):', "if False:"),
    "any-url-host": (INTAKE, "_check_host(args.url, src.hosts)",
                     "_check_host(args.url, frozenset({urlsplit(args.url).netloc}))"),
    "ledger-unchecked": (INTAKE, "if (item.source, item.item_id) in seen:", "if False:"),
    "quote-unchecked": (INTAKE, "if not found_on:", "if False:"),
    "manual-needs-orchestrator": (RECONCILE, "elif (orchestrator is None and not manual)", "elif (orchestrator is None)"),
}
```

  Copy `load()` **verbatim** from `evals/check_feed_adapters.py:180-193`. Then:

```python
def stub_extractor(run, request, advisory_id, root):
    """Writes the two fields reconcile_run checks, as an extraction would; spends nothing."""
    rel = "%s/%s.json" % (inbox.RECORDS, advisory_id)
    inbox.write_file(run.run_id, rel, json.dumps({"advisory_id": advisory_id, "source": {
        "document_sha256": request["document"]["sha256"]}}).encode("utf-8"), root)

    async def done():
        return {"key": request["key"], "advisory_id": advisory_id, "extraction_run_id": None, "status": "extracted",
                "record": rel, "error": None, "cost_usd": 0.0}
    return done()


def argv(pdf: Path, **over) -> list:
    a = {"--source": "fatf", "--file": str(pdf), "--url": URL, "--title": "Professional Money Laundering",
         "--published": "2018-07-26", "--reason": "sets out professional laundering methods", "--quote": SENTENCE}
    a.update(over)
    return [x for k, v in a.items() for x in (k, v)]


def runs_in(root: Path) -> list:
    return sorted(p.name for p in root.glob("feeds-*") if p.is_dir()) if root.exists() else []


def world(t: Path, ledger_items: list):
    root, seen, alist = t / "inbox", t / "seen.json", t / "feed_advisory_list.json"
    seen.write_text(ledger.dump(ledger_items), encoding="utf-8")
    pdf = t / "fatf.pdf"
    pdf.write_bytes(tiny_pdf([SENTENCE]))
    bad = t / "not.pdf"
    bad.write_bytes(b"<html>not a pdf</html>")
    return root, seen, alist, pdf, bad


def checks(mutation) -> list:
    rec_mod = load("feeds.reconcile", RECONCILE, mutation)
    intake = load("intake_document", INTAKE, mutation)
    intake.reconcile = rec_mod  # the intake reads the (possibly mutated) reconcile, as the guard does
    feeds_http.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the intake fetched something"))
    live_keys = set(json.loads(LIVE_RUN.read_text(encoding="utf-8"))["sources"]["ofac"]["items"][0]["document"])
    out = []
    with tempfile.TemporaryDirectory() as t:
        root, seen, alist, pdf, _ = world(Path(t), [])
        code = intake.main(argv(pdf), root=root, seen_path=seen, advisory_lists=[alist], extractor=stub_extractor)
        names = runs_in(root)
        out.append((code == 0 and len(names) == 1, "a good intake writes one run and exits 0", (code, names)))
        if len(names) == 1:
            run = names[0]
            state = inbox.load(run, root)
            item = inbox.items(state)[0]
            out.append(((state.get("manual") or {}).get("by") == "owner", "the run is marked manual, by the owner",
                        state.get("manual")))
            out.append((set(item["document"]) == live_keys | {"delivered_by"},
                        "its document carries a live item's keys plus delivered_by",
                        sorted(set(item["document"]) ^ (live_keys | {"delivered_by"}))))
            verdict = feeds_triage.load(run, root).get(item["key"], {})
            out.append((verdict.get("by") == "owner" and verdict.get("reason", "").startswith("owner-selected: ")
                        and bool(verdict.get("found_on")),
                        "the selection is a triage line by the owner, its quote found",
                        {k: verdict.get(k) for k in ("by", "reason", "found_on")}))
            rec = rec_mod.reconcile_run(run, root)
            out.append((rec["status"] == rec_mod.COMPLETE, "reconcile_run calls the manual run COMPLETE",
                        (rec["status"], rec["problems"][:2])))
            out.append(((inbox.run_dir(run, root) / "report.md").exists(), "report.md is written", run))
    refusals = {"a file that is not a PDF": ({"--file": None}, []),
                "a URL over http": ({"--url": URL.replace("https://", "http://")}, []),
                "a URL on another host": ({"--url": "https://evil.example/report.pdf"}, []),
                "a live source": ({"--source": "wolfsberg"}, []),
                "a quote on no page": ({"--quote": "This sentence appears nowhere in the document at all."}, []),
                "a document already in the ledger": ({}, [{"source": "fatf", "item_id": ITEM_ID, "decision": "accept",
                                                           "first_seen_run": "feeds-2026-10-01-abcdef",
                                                           "decided_on": "2026-10-01"}])}
    for label, (over, ledger_items) in refusals.items():
        with tempfile.TemporaryDirectory() as t:
            root, seen, alist, pdf, bad = world(Path(t), ledger_items)
            if "--file" in over:
                over = dict(over, **{"--file": str(bad)})
            try:
                code = intake.main(argv(pdf, **over), root=root, seen_path=seen, advisory_lists=[alist],
                                   extractor=stub_extractor)
            except Exception as exc:  # noqa: BLE001 -- a crash is not a refusal
                code = "raised %s" % type(exc).__name__
            out.append((code == 2 and not runs_in(root), "refused, nothing written: %s" % label, (code, runs_in(root))))
    src = SOURCES_PY.read_text(encoding="utf-8").replace(
        'MANUAL_SOURCES = {"fatf"', 'MANUAL_SOURCES = {"fca": ManualSource("fca", frozenset()), "fatf"', 1)
    try:
        exec(compile(src, str(SOURCES_PY), "exec"), types.ModuleType("overlap").__dict__)
        out.append((False, "a source declared live and manual is refused at import", "imported"))
    except RuntimeError as exc:
        out.append(("both live and manual" in str(exc), "a source declared live and manual is refused at import",
                    str(exc)[:120]))
    return out
```

  Add the same `main()` as `check_document_hop.py`, with `--mutate` choices `sorted(MUTATIONS)`. If `ledger.dump` of an empty list is not what `ledger.load` reads back as empty, read `feeds/ledger.py:31-56` and write what `load` expects.

- [ ] **Step 2: Run it and watch it fail.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_intake.py`
  Expected: FAIL. `tools/intake_document.py` does not exist.

- [ ] **Step 3: Declare the manual source.** In `feeds/sources.py`, after the ORDER block:

```python
@dataclass(frozen=True)
class ManualSource:
    """A source whose site blocks automated fetching (FATF, measured 2026-10-31: Cloudflare's bot check on every URL).
    The owner downloads a document and tools/intake_document.py takes it in. Nothing in fc-08 fetches these hosts;
    they bound the provenance URL the owner records."""
    name: str
    hosts: FrozenSet[str]


MANUAL_SOURCES = {"fatf": ManualSource("fatf", frozenset({"www.fatf-gafi.org"}))}
if set(MANUAL_SOURCES) & set(SOURCES):
    raise RuntimeError("feeds.sources: %s are declared both live and manual" % sorted(set(MANUAL_SOURCES) & set(SOURCES)))
```

- [ ] **Step 4: `decide()` takes `by`.** In `feeds/triage.py`, change the signature to:

```python
def decide(run_id: str, key: str, verdict: str, reason: str, quote: str,
           root: Path = inbox.INBOX_ROOT, *, by: str = "agent") -> Tuple[bool, str]:
```

  and directly after the `entry = {…}` line:

```python
    if by != "agent":  # the owner's selection at intake (plan R4); an agent's line stays byte-identical
        entry["by"] = by
```

- [ ] **Step 5: Reconcile a manual run (R5).** In `feeds/reconcile.py` `reconcile_run`:
  - After `state = inbox.load(run_id, root)`: `manual = bool(state.get("manual"))  # tools/intake_document.py: no orchestrator, by design`
  - `ended = orchestrator is not None and orchestrator["completed"]` becomes `ended = manual or (orchestrator is not None and orchestrator["completed"])`
  - `if ended and orchestrator["status"] != "FAILURE":` becomes `if ended and (manual or orchestrator["status"] != "FAILURE"):`
  - `if refusal is None and run and orchestrator is None:` becomes `if refusal is None and run and orchestrator is None and not manual:`
  - `never_listed = [s for s in SOURCES if s not in state["sources"]]` becomes `never_listed = [] if manual else [s for s in SOURCES if s not in state["sources"]]`
  - `elif orchestrator is None or orchestrator["status"] == "FAILURE" or run.get("failure"):` becomes `elif (orchestrator is None and not manual) or (orchestrator is not None and orchestrator["status"] == "FAILURE") or run.get("failure"):`

- [ ] **Step 6: `accept_run` (R6).** PUBLISHERS gains `"fatf": "Financial Action Task Force (FATF)"`. In `_check_accepted`, before `entry = {`:

```python
    how = "owner intake" if verdict.get("by") == "owner" else "live feed"  # plan R6: provenance, not a live feed
```

  In the entry, `"source_matrix_tier": "live feed"` becomes `"source_matrix_tier": how`, and the rationale becomes:

```python
             "selection_rationale": ("live feed run %s, item %s: triaged relevant: %s" % (run_id, key, verdict["reason"])
                                     if how == "live feed" else
                                     "owner intake run %s, item %s: %s" % (run_id, key, verdict["reason"])),
```

  In `evals/check_feed_adapters.py` `publisher_checks`, change `missing = sorted(set(sources.SOURCES) - set(names))` to `missing = sorted((set(sources.SOURCES) | set(sources.MANUAL_SOURCES)) - set(names))`.

- [ ] **Step 7: The intake tool.** Create `tools/intake_document.py`:

```python
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
import json
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
    if not title or not DAY.match(args.published) or not args.reason.strip():
        return _refuse("a title, a YYYY-MM-DD --published and a --reason are all required")
    body = Path(args.file).expanduser().read_bytes()
    if not body.startswith(b"%PDF-"):
        return _refuse("%s is not a PDF" % args.file)
    if len(body) > MAX_DOCUMENT_BYTES:
        return _refuse("%s is larger than %d bytes" % (args.file, MAX_DOCUMENT_BYTES))
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.pdf"
        probe.write_bytes(body)
        index = PageIndex.from_pdf(probe)
        texts = feeds_triage.page_texts(probe)
    text_pages = sum(1 for p in index.pages if p.strip())
    if text_pages == 0:
        return _refuse("%s has no text; nothing in it could be cited" % args.file)
    _, found_on = feeds_triage.find_quote(texts, args.quote.strip())
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
    try:
        outcome = asyncio.run(extractor(of.FeedsRun(run_id), req, advisory_id, root))
    finally:
        telemetry.TELEMETRY_DIR = previous
    if outcome.get("status") == "extracted" and outcome.get("record"):
        outcome["citation_check"] = friday_run.citation_check(run_id, outcome, req, root)
    extraction.append_outcome(run_id, outcome, root)
    (inbox.run_dir(run_id, root) / reconcile.RUN_JSON).write_text(json.dumps(
        {"run_id": run_id, "manual": True, "started_at": started, "ended_at": _now(), "failure": None, "crash": None,
         "unrecorded": None, "limit": None, "orchestrator_cost_usd": None,
         "spent_usd": outcome.get("cost_usd") if outcome.get("cost_usd") is not None else of.EXTRACTION_BUDGET_USD,
         "ceiling_usd": of.EXTRACTION_BUDGET_USD, "prompt_sha256": None, "model": of.MODEL},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.write(run_id, root)
    rec = reconcile.reconcile_run(run_id, root)
    print("%s: %s, %s (%s). Next: python tools/accept_run.py %s" % (run_id, item.key, outcome.get("status"),
                                                                    rec["status"], run_id))
    return 0 if outcome.get("status") == "extracted" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

  Three details to check against the code rather than assume:
  - **The advisory-list constant.** `friday_run.ADVISORY_LISTS` is the name `friday()` takes as its default (`advisory_list=ADVISORY_LISTS`). If the module spells it differently, use that name.
  - **The extractor's return type.** `extract_one` is `async def`, so `extractor(...)` returns a coroutine for `asyncio.run`. The guard's stub returns one too.
  - **How `run.json` is written.** If `friday_run._save(path, obj)` writes `run.json` with a particular format, call it instead of the inline `write_text`, so both writers stay byte-compatible.

- [ ] **Step 8: Register the guard.** In `tools/check_all.py`, after `check_document_hop`:

```python
    ("check_intake", ["evals/check_intake.py"], "cold"),
```

  In `evals/check_mutation_anchors.py` CHECKED:

```python
    "check_intake.py": (("MUTATIONS", PATH_OLD, None, (ONCE,)),),
```

- [ ] **Step 9: Run it, each mutation, and every guard the change touches.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_intake.py && for m in owner-as-agent no-pdf-check any-url-host ledger-unchecked quote-unchecked manual-needs-orchestrator; do env -u ANTHROPIC_API_KEY PYTHONPYCACHEPREFIX=/tmp/intake-$m $PY evals/check_intake.py --mutate $m | tail -1; done`
  Expected: `HOLDS`, then six lines of `HELD: …`.

  Run: `for g in feed_adapters feeds_triage feeds_runner friday_run accept_run feeds_extract mutation_anchors; do env -u ANTHROPIC_API_KEY $PY evals/check_$g.py >/dev/null || echo "FAIL $g"; done`
  Expected: no output. (`check_friday_run` and `check_feeds_runner` prove reconcile is unchanged for a Friday run. `check_accept_run` proves the live-feed strings are unchanged.)

  **Do not commit (R1).**

---

### Task 4: retire the script; the scan page reads `MANUAL_SOURCES`

**Files:**
- Delete: `tools/fetch_fatf_via_chrome.js`
- Create: `evals/check_no_disguised_automation.py`
- Modify: `tools/build_scan_demo.py:26-27, :78, :363`
- Modify: `evals/check_scan_demo.py:493`
- Modify: `tools/check_all.py`, `evals/check_mutation_anchors.py` EXEMPT
- Modify: `CLAUDE.md:15, :28, :148`, plus the evals rows

- [ ] **Step 1: Write the guard (the failing test).** Create `evals/check_no_disguised_automation.py`:

```python
"""
Refuse disguised browser automation anywhere in the tracked tree (spec 2026-10-31 §2).

Usage:
    python evals/check_no_disguised_automation.py
    python evals/check_no_disguised_automation.py --mutate plant   # a tracked tool that switches AutomationControlled off

WHY. tools/fetch_fatf_via_chrome.js (2026-09-10 to 2026-10-31) launched Chrome with AutomationControlled off and
navigator.webdriver hidden, to pass fatf-gafi.org's bot check. fc-08 does not get past bot checks: FATF arrives
through tools/intake_document.py, from a file the owner downloaded. This keeps that retirement from being undone.

WHAT IT HOLDS: no tracked file outside ALLOWED (this guard, and the spec and plan that record the retirement)
carries either signature, and at least 200 tracked text files were read -- a scan of nothing passes nothing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNATURES = (re.compile(r"AutomationControlled"),
              re.compile(r"""navigator\s*,\s*['"]webdriver['"]|navigator\.webdriver\s*="""))
ALLOWED = {"evals/check_no_disguised_automation.py",
           "docs/superpowers/specs/2026-10-31-wolfsberg-swept-fatf-by-hand-design.md",
           "docs/superpowers/plans/2026-10-31-wolfsberg-swept-fatf-by-hand.md"}
PLANT = ("tools/planted.js", "chromium.launch({ args: ['--disable-blink-features=AutomationControlled'] })")
MIN_FILES = 200


def tracked() -> list:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def checks(mutation) -> list:
    files = []
    for rel in tracked():
        try:
            files.append((rel, (ROOT / rel).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
    if mutation == "plant":
        files.append(PLANT)
    hits = sorted(rel for rel, text in files if rel not in ALLOWED and any(s.search(text) for s in SIGNATURES))
    return [(len(files) >= MIN_FILES, "the scan read the tracked tree", "%d text files" % len(files)),
            (not hits, "no tracked file disguises browser automation", hits)]
```

  Add the same `main()` as `check_document_hop.py`, with `--mutate` choices `["plant"]`.

- [ ] **Step 2: Run it and watch it fail.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_no_disguised_automation.py`
  Expected: FAIL, naming `tools/fetch_fatf_via_chrome.js`. If it also names other files (for example a September plan quoting the script), those are records of the retirement's history. Add each to `ALLOWED` with a comment saying why, rather than editing a dated record.

- [ ] **Step 3: Retire the script and repoint the scan page.**

  Run: `git rm tools/fetch_fatf_via_chrome.js`

  In `tools/build_scan_demo.py`:
  - delete the `FATF_MANUAL = …` line;
  - import `MANUAL_SOURCES` beside the existing `SOURCES` import;
  - `"manual": ["fatf"] if FATF_MANUAL.exists() else [],` becomes `"manual": sorted(MANUAL_SOURCES),`;
  - in the docstring, `tools/fetch_fatf_via_chrome.js (manual)` becomes `feeds.sources.MANUAL_SOURCES (manual: taken in by tools/intake_document.py)`.

  In `evals/check_scan_demo.py:493`, `live_types | {"fatf"} | set(bs.NOT_A_FEED)` becomes `live_types | set(MANUAL_SOURCES) | set(bs.NOT_A_FEED)`, importing `MANUAL_SOURCES` from `feeds.sources`.

- [ ] **Step 4: Register the guard.** In `tools/check_all.py`:

```python
    ("check_no_disguised_automation", ["evals/check_no_disguised_automation.py"], "cold"),
```

  In `evals/check_mutation_anchors.py` EXEMPT:

```python
    "check_no_disguised_automation.py": "--mutate adds a planted file to the scanned set in memory",
```

- [ ] **Step 5: CLAUDE.md.**
  - **Line 15:** replace `fatf-gafi.org blocks curl; fetch advisories through a real browser` with `fatf-gafi.org answers every automated client with Cloudflare's bot check, and fc-08 does not get past bot checks: the owner downloads a FATF document in their own browser and takes it in with tools/intake_document.py`.
  - **Line 28:** replace the row with `tools/intake_document.py          takes in a document the owner downloaded (FATF); fetches nothing; writes one run for accept_run`.
  - **Line 148:** replace the sentence ``fatf-gafi.org needs a real browser: `tools/fetch_fatf_via_chrome.js` (cached playwright module + installed Chrome, stealth headless) works; the Playwright MCP servers drop on downloads.`` with `The six FATF PDFs were fetched 2026-09-10 by a Chrome script that disguised automation to pass fatf-gafi.org's bot check; it was retired 2026-10-31 (fc-08 does not get past bot checks) and FATF now arrives through tools/intake_document.py. The PDFs and their golden hashes are unchanged.`
  - **Evals table:** next to the other `evals/check_*` rows, add one row each for `evals/check_document_hop.py` (the one-hop document rule), `evals/check_intake.py` (the manual intake) and `evals/check_no_disguised_automation.py` (no disguised browser automation in the tracked tree).

  None of the replacement text may contain `AutomationControlled`.

- [ ] **Step 6: Run it, the mutation, and the scan-page guards.**

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_no_disguised_automation.py && env -u ANTHROPIC_API_KEY $PY evals/check_no_disguised_automation.py --mutate plant | tail -1`
  Expected: `HOLDS`, then `HELD: …`.

  Run: `env -u ANTHROPIC_API_KEY $PY evals/check_scan_demo.py | tail -3; env -u ANTHROPIC_API_KEY $PY evals/check_tool_surface.py | tail -1`
  Expected:
  - `check_scan_demo`'s coverage clauses PASS, with Wolfsberg live and FATF manual. Clauses comparing the built page to a rebuild may FAIL until Task 5 rebuilds it.
  - `check_tool_surface` passes.

  **Do not commit (R1).**

---

### Task 5: rebuild, publish (owner's go), one commit

- [ ] **Step 1: Rebuild and check the scan page.**

  Run: `env -u ANTHROPIC_API_KEY $PY tools/build_scan_demo.py && env -u ANTHROPIC_API_KEY $PY tools/build_scan_demo.py --check && env -u ANTHROPIC_API_KEY $PY evals/check_scan_demo.py | tail -1`
  Expected: the page builds, `--check` matches, and check_scan_demo HOLDS. Open `site/scan-demo/index.html` through the `fc08-scan-mechanics` preview (port 8794). Confirm the coverage panel reads ten live, including Wolfsberg; FATF manual; and Europol not yet, with its reason.

- [ ] **Step 2: Whole-suite run.**

  Run: `env -u ANTHROPIC_API_KEY PATH=~/fc-08-schedule/.venv/bin:$PATH python3 tools/check_all.py | tail -6`
  Expected: every guard passes except the two publish gates for the scan page (`check_published_scan_demo --cold` and plain), which go red until Step 3.

- [ ] **Step 3: Publish, on the owner's go only.**
  - Fetch the portfolio first and check its log (it is shared).
  - Run `$PY tools/publish_scan_demo.py`.
  - Commit the portfolio's `projects/nexus/threat-intel/scan.html`, staged explicitly, with no trailer. Do not push.

- [ ] **Step 4: One fc-08 commit.** Stage explicitly. The list:
  - the three fixtures and their README;
  - `feeds/sources.py`, `feeds/triage_rules.json`, `feeds/triage.py`, `feeds/reconcile.py`, `feeds/extraction.py`;
  - `mcp_server/feeds_server.py`;
  - `tools/accept_run.py`, `tools/intake_document.py`, `tools/build_scan_demo.py`, `tools/check_all.py`;
  - the deleted `tools/fetch_fatf_via_chrome.js`;
  - `evals/check_feed_adapters.py`, `evals/check_feeds_orchestrator.py` (if re-pinned), `evals/check_document_hop.py`, `evals/check_intake.py`, `evals/check_no_disguised_automation.py`, `evals/check_scan_demo.py`, `evals/check_mutation_anchors.py`;
  - `CLAUDE.md`, `site/SCAN_PUBLISHED`, and the rebuilt `site/scan-demo/index.html`.

  Then:

  Run: `env -u ANTHROPIC_API_KEY PATH=~/fc-08-schedule/.venv/bin:$PATH git commit -m "<message: Wolfsberg tenth live source with the one-hop rule; FATF intake; the disguised-automation script retired and guarded; prompt hash old -> new if re-pinned; scan page republished as portfolio <hash>>"`
  Expected: the hook reports `PASS: N run, 0 not run, 0 failed`.

- [ ] **Step 5: Hand over the pushes** (fc-08 branch and portfolio) as bash blocks for the owner. Open the PR stacked on PR #3.

### Task 6: after landing (owner-gated)

- [ ] **Step 1: Baseline Wolfsberg on its landing day, before the next Friday run.** In `~/fc-08-schedule`, on `main` after a fast-forward:
  - Run: `env -u ANTHROPIC_API_KEY .venv/bin/python tools/accept_run.py --baseline wolfsberg --on <landing date> --dry-run`, then again without `--dry-run`.
  - Commit `data/feeds/seen.json`, staged explicitly, and hand the push to the owner.
- [ ] **Step 2 (optional): the first real FATF intake is the end-to-end check (R10).** The owner downloads one FATF report in their own browser and runs `tools/intake_document.py` with its URL, a reason and a quote. This spends up to US$1 on extraction. Then run `tools/accept_run.py <run_id>`. Acceptance writing `owner intake` as the tier proves the whole path.
