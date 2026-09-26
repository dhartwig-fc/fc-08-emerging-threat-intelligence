# Slice 2 A: Foundations and Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ground slice 2's weekly run stands on:
- deterministic pages for HTML documents;
- the seen-items ledger and a drop-only `accept_run`;
- adapters for OFSI, FinCEN and OFAC with loud layout guards;
- the `feeds` MCP server's `feeds_list_new` and `feeds_fetch`;
- the walkthrough's resolver sentence, made computed so the first live extraction cannot block every commit.

**Architecture:** A new `feeds/` package holds the pieces:
- the item model;
- the ledger (the ONLY record of what is new);
- the run inbox (the only place a run writes);
- the adapters and an allowlisted fetch.

`mcp_server/feeds_server.py` wraps them as two tools, and each tool enforces its invariant in code. `schemas/html_pages.py` gives `PageIndex.from_html`, so the unchanged citation matcher works on HTML. Each piece gets a cold, mutation-verified guard registered in `tools/check_all.py`.

**Tech Stack:** Python 3 standard library (`html.parser`, `xml.etree`, `urllib`), plus what is already installed in `.venv` (`pydantic`, `mcp`, `pypdf`). No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-slice2-live-intelligence-design.md`. Sub-project A covers sections 3 and 5 (the tripwire), the ledger, the `accept_run` skeleton, and the list and fetch tools.

## Global Constraints

- Run Python as `.venv/bin/python` from the repository root.
- No new dependencies.
- Never create `.bak`, `_backup`, `_before_*` or similar snapshot files; git is the version control.
- Never commit a file over 50 MB. Never use `git commit --no-verify`.
- The pre-commit hook runs `tools/check_all.py` (several minutes, all guards). It is the gate; if it refuses, the commit is not ready.
- Every `evals/check_*.py` must be in `tools/check_all.py`'s `GUARDS` in the SAME commit that adds it. `check_all` refuses an unregistered guard.
- A guard ends `HELD (0 failures)`.
- Each `--mutate` must print `HELD: the mutation is detected`. Run mutations with a per-run bytecode cache: `PYTHONPYCACHEPREFIX=/tmp/fc08-mut-<label> .venv/bin/python evals/<guard>.py --mutate <label>`.
- Commit messages start `Slice 2 A:`. Never add a `Co-Authored-By` trailer.
- Push only when the owner asks. Nothing is published without the owner's go.
- Never run `tools/publish_walkthrough.py` against the real portfolio without the owner's go on the day. The portfolio is shared with other sessions, so fetch it first.
- Network: only `tools/feeds_probe.py` (Task 3) makes live requests, run by hand. No guard touches the network.
- Documents a run fetches stay in the gitignored `inbox/`. Only the listing snapshots under `tests/fixtures/` are tracked.

## Rulings made while writing this plan (from measurements taken 2026-09-26)

1. **An OFSI item's id is its Atom `<id>`, which carries a timestamp** (`…/uk-financial-sanctions-faqs#2026-09-24T08:49:08Z`). A revised publication is therefore a new item. Why: GOV.UK revises guidance in place, and a revision can add a new method. Cost if wrong: a heavily revised page comes back to triage each time it changes.
2. **`feeds_fetch` pins the URL the listing gives, and nothing more.** Measured: FinCEN's and OFSI's listed URLs are HTML landing pages, and the advisory itself is a linked PDF. FinCEN's is at `www.fincen.gov/system/files/…`; OFSI's attachments are at `assets.publishing.service.gov.uk`. OFAC's recent action IS the page.
   - `feeds_fetch` records the linked PDFs (absolute) but does not fetch them.
   - Following them, and adding the attachment host to the allowlist, is decided in sub-project C.
   - Cost if wrong: sub-project C adds one step.
3. **A listing that parses to zero items raises `LayoutChanged`.** Measured: the three listings always show their latest 20, 15 and 10 entries, so an empty parse means the page changed.
4. **`accept_run` in A records drops only and refuses `accept`.** Accepting also moves the record, the queue file and the document into tracked data, which is sub-project C. A ledger saying "accepted" over nothing moved would be false.
5. **`items.json` stores only the NEW items per source, plus the counts `listed` and `already_seen`.** Items already decided are counted, not copied.
6. **The tripwire task is LAST (Task 5).** It is the only task that changes the published page, so it is the only one that needs the owner's go to republish. Nothing in Tasks 1-4 writes a proposal queue, so the tripwire cannot fire meanwhile.
7. **Section 10 counts runs, and no longer relies on a typed date.** This closes the slice 1 parked item "RESOLVER_ADDED typed in the builder".
   - The resolver sentence counts committed extraction runs (queue files), then splits them:
     - runs whose `RUN_STARTED` telemetry lists the resolver among the agent's tools;
     - runs with no tool list recorded (all history);
     - runs where a resolve call answered `Resolved:`.
   - `RUN_STARTED` gains a `tools` field so future runs are measured, not inferred from a date.
8. **Section 10's "no live ingestion: nothing fetches a new publication" becomes false once Task 4 lands.** It is reworded in Task 5 to say live ingestion is being built, with a computed count of feed items accepted into the corpus (0 in A).
9. **Parsing uses the stdlib only.** HTML goes through `html.parser`. XML goes through `xml.etree`, whose expat backend refuses entity-expansion bombs. No `defusedxml`, because no new dependency.

## File map

| File | Task | Responsibility |
|---|---|---|
| `schemas/html_pages.py` | 1 | the HTML pagination rule: `paragraphs`, `paginate`, `html_pages`, `pages_digest` |
| `schemas/citation_match.py` | 1 | gains `PageIndex.from_html` |
| `evals/check_html_pages.py` | 1 | pins the rule, two page digests, and determinism across hash seeds |
| `feeds/__init__.py`, `feeds/model.py` | 2 | `FeedItem` (with its derived `key`), `LayoutChanged` |
| `feeds/ledger.py` | 2 | `data/feeds/seen.json`: `load`, `dump`, `record_decisions` |
| `feeds/inbox.py` | 2 | `inbox/<run_id>/`: `RUN_ID`, `mint_run_id`, `run_dir`, `load`, `save`, `write_file`, `items`, `find_item` |
| `tools/accept_run.py` | 2 | the drop-only skeleton: `plan`, `main` |
| `data/feeds/seen.json` | 2 | the tracked, empty ledger |
| `evals/check_feeds_ledger.py` | 2 | ledger, inbox and accept_run guard, with a writer scan |
| `feeds/sources.py` | 3 | the three adapters, the `SOURCES` registry, `linked_pdfs` |
| `feeds/http.py` | 3 | `get`: allowlisted hosts (redirects too), type and size limits, polite gap |
| `tools/feeds_probe.py` | 3 | the manual live probe |
| `evals/check_feed_adapters.py` | 3 | snapshot contracts, layout-changed refusals, transport rules |
| `mcp_server/feeds_server.py` | 4 | `feeds_list_new`, `feeds_fetch` |
| `evals/check_feeds_server.py` | 4 | the server's invariants, with stubbed HTTP |
| `tools/build_walkthrough.py`, `evals/check_walkthrough.py`, `agents/telemetry.py`, `agents/extract_advisory.py`, `agents/review_advisory.py`, `evals/check_telemetry.py` | 5 | the computed resolver and ingestion sentences; `RUN_STARTED` records tools |
| `tests/fixtures/feeds/*`, `tests/fixtures/html/*` | committed with this plan | listing snapshots and one GOV.UK document page, fetched 2026-09-26 |

The fixtures are already committed with this plan. The four sha256 values each guard pins are:

```
b63d891e06aceaaf42021a4637573ad16cedc7c6b84ab7082332903b4b6d31c9  tests/fixtures/feeds/ofsi.atom
295483b8950e51cd839f1b0198c6b20d8a802180b55487ee6551412bcbd3b10b  tests/fixtures/feeds/fincen_advisories.html
9b2cdcdc61a65f954e3157d216ce154aa3ad1fddfea810f97d78ad6bb9f0e669  tests/fixtures/feeds/ofac_recent_actions.html
1d3987e30a44c4387c5fe72382290f33d302f871177bc28e34afa4050da8a664  tests/fixtures/html/ofsi_uk_financial_sanctions_faqs.html
```

Every code block below was run before this plan was written:
- all four guards were run in a scratch copy of the repository and HELD;
- every one of their 24 mutations was detected;
- the probe parsed all three live listings (FinCEN 15, OFAC 10, OFSI 20).

The code is transcription. Copy it exactly.

---

### Task 1: `PageIndex.from_html` and the pagination rule

**Files:**
- Create: `schemas/html_pages.py`
- Modify: `schemas/citation_match.py` (add `from_html` right after `from_pdf`)
- Create: `evals/check_html_pages.py`
- Modify: `tools/check_all.py` (one `GUARDS` entry)

**Interfaces:**
- Consumes: `schemas.citation_match.PageIndex(page_texts)`, `.locate(page, quote)`, `EXACT`, `OFF_PAGE`.
- Produces:
  - `schemas.html_pages.html_pages(raw: bytes) -> List[str]`
  - `paragraphs(raw: bytes) -> List[str]`, which raises `ValueError` on non-UTF-8 input
  - `paginate(paras) -> List[str]`
  - `pages_digest(pages) -> str`
  - `PAGE_CHARS = 3000`
  - `PageIndex.from_html(raw: bytes) -> PageIndex`

  Tasks 3 and 4 use `html_pages` and `from_html`.

- [ ] **Step 1: Write the guard first**

Create `evals/check_html_pages.py`:

```python
"""
Pin the HTML pagination rule (schemas/html_pages.py) that PageIndex.from_html cites against.

Usage:
    python evals/check_html_pages.py
    python evals/check_html_pages.py --mutate keep-nav        # <nav> kept; navigation text MUST reach a page
    python evals/check_html_pages.py --mutate split-long      # long paragraphs cut; a paragraph MUST be split
    python evals/check_html_pages.py --mutate body-first      # <body> preferred to <main>; the pins MUST move
    python evals/check_html_pages.py --mutate page-size       # PAGE_CHARS 3000 -> 2500; the pins MUST move
    python evals/check_html_pages.py --mutate lenient-decode  # bad UTF-8 replaced, not refused
    python evals/check_html_pages.py --mutate no-entities     # entities not decoded; "&amp;" MUST go missing

WHY. A citation into an HTML document is (page, verbatim quote), and the page number comes from
this rule. Change the rule and every cited HTML page number moves, silently, so the rule is pinned
twice: by its behaviour (dropped chrome, whole paragraphs, the <main>/<article>/<body> fallback,
strict UTF-8, decoded entities) and by the digest of the pages it gives two documents -- a real
OFSI publication page (tests/fixtures/html/, public GOV.UK content under the Open Government
Licence) and a synthetic advisory built below. Moving a pin is a deliberate act: it re-pages every
committed HTML citation.

DETERMINISM. The same bytes must give the same pages on every run: the guard computes the digest
in four subprocesses under different PYTHONHASHSEED values. (fc-10 measured that two seeds can
agree by luck on non-deterministic code.)

COLD. A committed fixture and synthetic strings; no network.

NOT A VACUOUS PASS. Each --mutate rewrites the rule's SOURCE in memory and loads it as a separate
module; at least one check must then fail. A mutation whose target text is missing is a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schemas import citation_match as cm  # noqa: E402

RULE = ROOT / "schemas" / "html_pages.py"
FIXTURE = ROOT / "tests" / "fixtures" / "html" / "ofsi_uk_financial_sanctions_faqs.html"
FIXTURE_SHA256 = "1d3987e30a44c4387c5fe72382290f33d302f871177bc28e34afa4050da8a664"
FIXTURE_PAGES = 2
FIXTURE_DIGEST = "77ac9c09aa2ad2e223bc57e77545a34b58b229cb0566080b26c16d67c6f85ef6"
SYNTH_PAGES = 3
SYNTH_DIGEST = "01cf07ca19add9908db77fb5187057c83889b8d4842f1abaad2d9aa982c77c6b"
DROPPED = ("SCRIPT-TEXT", "HEADER-TEXT", "NAV-TEXT", "ASIDE-TEXT", "FOOTER-TEXT")
SEEDS = ("0", "1", "42", "4242")


def synthetic(main_tag: str = "main") -> bytes:
    return ("<!DOCTYPE html><html><head><title>T</title><style>p{color:red}</style>"
            "<script>var x='SCRIPT-TEXT';</script></head><body>"
            "<header>HEADER-TEXT</header><nav><a href='/'>NAV-TEXT</a></nav>"
            "<%s><h1>Synthetic advisory</h1>" % main_tag
            + "".join("<p>Paragraph %02d says funds moved through shell companies &amp; front firms in sentence "
                      "%02d of this synthetic advisory.</p>" % (i, i) for i in range(1, 41))
            + "<p>" + "Long " * 700 + "end.</p>"
            + "<aside>ASIDE-TEXT</aside></%s><footer>FOOTER-TEXT</footer></body></html>" % main_tag).encode("utf-8")


MUTATIONS = {
    "keep-nav": ('"svg", "nav", ', '"svg", '),
    "split-long": ("    for para in paras:\n",
                   "    for para in [p[i:i + PAGE_CHARS] for p in paras for i in range(0, len(p), PAGE_CHARS)]:\n"),
    "body-first": ('SCOPES = ("main", "article", "body")', 'SCOPES = ("body", "article", "main")'),
    "page-size": ("PAGE_CHARS = 3000", "PAGE_CHARS = 2500"),
    "lenient-decode": ('text = raw.decode("utf-8")', 'text = raw.decode("utf-8", "replace")'),
    "no-entities": ("super().__init__(convert_charrefs=True)", "super().__init__(convert_charrefs=False)"),
}


def load_rule(mutation):
    source = RULE.read_text(encoding="utf-8")
    if mutation:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, RULE))
        source = source.replace(old, new)
    spec = importlib.util.spec_from_loader("html_pages_under_test", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(RULE), "exec"), module.__dict__)
    return module


def seeded_digests(path: Path) -> set:
    code = ("import sys; sys.path.insert(0, %r); from schemas.html_pages import html_pages, pages_digest; "
            "print(pages_digest(html_pages(open(%r, 'rb').read())))" % (str(ROOT), str(path)))
    out = set()
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        out.add(r.stdout.strip() if r.returncode == 0 else "ERROR: " + r.stderr.strip()[-200:])
    return out


def checks(hp) -> list:
    out = []
    raw = FIXTURE.read_bytes()
    out.append((hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, "the OFSI fixture is the pinned bytes",
                "sha256 %s" % hashlib.sha256(raw).hexdigest()))

    pages = hp.html_pages(raw)
    out.append((len(pages) == FIXTURE_PAGES and hp.pages_digest(pages) == FIXTURE_DIGEST,
                "the OFSI page gives the pinned pages (moving this pin re-pages every HTML citation)",
                "%d pages, digest %s" % (len(pages), hp.pages_digest(pages))))
    index = cm.PageIndex(pages)
    q2 = "FAQs 49-51, 55, 61-66, 72-73, 76 and 84 amended to reflect new Legal Services General Licence"
    got2, got1 = index.locate(2, q2), index.locate(1, q2)
    out.append((got2.status == cm.EXACT and got1.status == cm.OFF_PAGE and got1.found_on == (2,),
                "a quote on page 2 is EXACT there, and OFF_PAGE (found on 2) when cited on page 1",
                "page 2: %s; page 1: %s %s" % (got2.status, got1.status, got1.found_on)))
    q1 = "provided by the Foreign, Commonwealth & Development Office (FCDO)"
    out.append((index.locate(1, q1).status == cm.EXACT, "a quote with a decoded & is EXACT on page 1",
                index.locate(1, q1).status))

    synth = synthetic()
    spages = hp.html_pages(synth)
    joined = "\n".join(spages)
    leaked = [t for t in DROPPED if t in joined]
    out.append((not leaked, "script, header, nav, aside and footer text never reaches a page", "leaked: %s" % leaked))
    out.append(("shell companies & front firms" in joined, "entities are decoded (&amp; is &)", ""))
    paras = hp.paragraphs(synth)
    split = [p[:40] for p in paras if sum(1 for pg in spages if p in pg.split("\n\n")) != 1]
    out.append((bool(paras) and not split, "every paragraph is whole on exactly one page",
                "%d paragraphs; not whole on one page: %s" % (len(paras), split)))
    over = [n + 1 for n, pg in enumerate(spages) if len(pg) > 3000 and "\n\n" in pg]
    long_alone = any(pg.startswith("Long Long") and "\n\n" not in pg for pg in spages)
    out.append((not over and long_alone, "a page passes 3000 characters only when it is one paragraph, and the "
                "3504-character paragraph stands alone", "multi-paragraph pages over 3000: %s" % over))
    out.append((len(spages) == SYNTH_PAGES and hp.pages_digest(spages) == SYNTH_DIGEST,
                "the synthetic advisory gives the pinned pages",
                "%d pages %s, digest %s" % (len(spages), [len(p) for p in spages], hp.pages_digest(spages))))

    out.append((hp.paragraphs(synthetic("div")) == paras,
                "with no <main>, <body> is used, and the same chrome is dropped", ""))
    art = b"<html><body><div>OUTSIDE-TEXT</div><article><p>Inside the article.</p></article></body></html>"
    out.append((hp.paragraphs(art) == ["Inside the article."], "with no <main>, <article> is preferred to <body>",
                repr(hp.paragraphs(art))))
    try:
        hp.paragraphs(b"<main><p>caf\xe9</p></main>")
        refused = False
    except ValueError:
        refused = True
    out.append((refused, "a page that is not UTF-8 is refused, not repaired", ""))

    real = cm.PageIndex.from_html(raw).pages
    out.append((real == cm.PageIndex(pages).pages, "PageIndex.from_html is PageIndex over these pages", ""))

    with tempfile.TemporaryDirectory() as tmp:
        sp = Path(tmp) / "synthetic.html"
        sp.write_bytes(synth)
        for label, path, pin in (("OFSI", FIXTURE, FIXTURE_DIGEST), ("synthetic", sp, SYNTH_DIGEST)):
            got = seeded_digests(path)
            out.append((got == {pin}, "the %s digest is the same under %d hash seeds" % (label, len(SEEDS)),
                        "digests: %s" % sorted(got)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the HTML pagination rule")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    hp = load_rule(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(hp):
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python evals/check_html_pages.py`
Expected: a `FileNotFoundError` naming `schemas/html_pages.py`. The guard reads the rule's source in order to mutate it, so a missing rule fails before any check runs.

- [ ] **Step 3: Write the rule**

Create `schemas/html_pages.py`:

```python
"""
Deterministic text pages for an HTML document, so a quote can be cited as (page, verbatim text).

THE RULE, which is part of every HTML citation -- change it and every cited page number moves:
  1. Decode the pinned bytes as UTF-8, strictly. A page that is not UTF-8 is refused, never
     repaired, because a replacement character would sit inside a quote the matcher then checks.
  2. Keep the text inside <main>; if the page has none, inside <article>; else inside <body>.
  3. Drop everything inside DROP (navigation, headers, footers, scripts, forms and the like).
  4. A BLOCK tag ends a paragraph. Whitespace inside a paragraph collapses to single spaces.
     Entities are decoded (&amp; is &).
  5. Pages are filled with whole paragraphs, joined by a blank line, until the next paragraph
     would take the page past PAGE_CHARS. A paragraph is never split: one longer than
     PAGE_CHARS stands alone on its own page.
Only the standard library's html.parser is used, so the same bytes give the same pages on any
machine; no browser, whose rendering changes with its version, is involved.
"""

from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
from typing import Dict, List

PAGE_CHARS = 3000
SCOPES = ("main", "article", "body")
DROP = frozenset({"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "aside",
                  "form", "button"})
BLOCK = frozenset({"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th",
                   "table", "section", "article", "main", "blockquote", "pre", "dt", "dd", "dl", "br",
                   "hr", "figcaption", "caption"})
VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
                  "track", "wbr"})


class _Paragraphs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.paras: Dict[str, List[str]] = {s: [] for s in SCOPES}
        self.cur: Dict[str, List[str]] = {s: [] for s in SCOPES}

    def _break(self) -> None:
        for scope in SCOPES:
            text = " ".join("".join(self.cur[scope]).split())
            if text:
                self.paras[scope].append(text)
            self.cur[scope] = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self._break()
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in BLOCK:
            self._break()

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self._break()
        if tag in self.stack:  # an end tag with no open start tag is ignored
            while self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if any(t in DROP for t in self.stack):
            return
        for scope in SCOPES:
            if scope in self.stack:
                self.cur[scope].append(data)


def paragraphs(raw: bytes) -> List[str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("the document is not UTF-8 (%s); it is refused, not repaired" % exc)
    parser = _Paragraphs()
    parser.feed(text)
    parser.close()
    parser._break()
    for scope in SCOPES:
        if parser.paras[scope]:
            return parser.paras[scope]
    return []


def paginate(paras: List[str]) -> List[str]:
    pages: List[str] = []
    cur: List[str] = []
    size = 0
    for para in paras:
        if cur and size + 2 + len(para) > PAGE_CHARS:
            pages.append("\n\n".join(cur))
            cur, size = [], 0
        size += (2 if cur else 0) + len(para)
        cur.append(para)
    if cur:
        pages.append("\n\n".join(cur))
    return pages


def html_pages(raw: bytes) -> List[str]:
    return paginate(paragraphs(raw))


def pages_digest(pages: List[str]) -> str:
    """sha256 of the pages as canonical JSON: the value a guard pins."""
    return hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode("utf-8")).hexdigest()
```

In `schemas/citation_match.py`, add this method directly after `from_pdf`, inside `class PageIndex`:

```python
    @classmethod
    def from_html(cls, raw: bytes) -> "PageIndex":
        """Pages of a pinned HTML document, by schemas/html_pages.py's fixed rule (slice 2)."""
        from schemas.html_pages import html_pages
        return cls(html_pages(raw))
```

- [ ] **Step 4: Run the guard and every mutation**

```bash
.venv/bin/python evals/check_html_pages.py
for m in keep-nav split-long body-first page-size lenient-decode no-entities; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_html_pages.py --mutate $m | tail -1; done
```

Expected:
- the plain run ends `HELD (0 failures)`, with 15 PASS lines;
- each of the six mutations prints `HELD: the mutation is detected (N checks failed)`.

The measured counts are keep-nav 3, split-long 2, body-first 4, page-size 4, lenient-decode 1 and no-entities 5.

Also run `.venv/bin/python evals/check_citation_match.py`. Expected: `HELD (0 failures)`, because the matcher itself did not change.

- [ ] **Step 5: Register the guard**

In `tools/check_all.py`, add this line to `GUARDS` directly after the `("check_publisher", ...)` entry:

```python
    ("check_html_pages", ["evals/check_html_pages.py"], "cold"),
```

Run: `.venv/bin/python tools/check_all.py --cold`
Expected: every cold guard passes, `check_html_pages` among them.

- [ ] **Step 6: Commit**

```bash
git add schemas/html_pages.py schemas/citation_match.py evals/check_html_pages.py tools/check_all.py
git commit -m "Slice 2 A: PageIndex.from_html -- deterministic pages for HTML documents, pinned two ways"
```

The hook runs the full `check_all`. Expected: it passes.

---

### Task 2: the item model, the seen-items ledger, the run inbox, and the `accept_run` skeleton

**Files:**
- Create: `feeds/__init__.py`, `feeds/model.py`, `feeds/ledger.py`, `feeds/inbox.py`
- Create: `tools/accept_run.py`
- Create: `data/feeds/seen.json`
- Create: `evals/check_feeds_ledger.py`
- Modify: `.gitignore` (add `inbox/`), `tools/check_all.py` (one `GUARDS` entry)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces, for Tasks 3 and 4:
  - `feeds.model`:
    - `FeedItem(source, item_id, title, url, published, summary="")`, with `.key` equal to `"<source>:<16 hex>"` and `.to_json()` returning the fields plus `key`;
    - `LayoutChanged(Exception)`.
  - `feeds.ledger`:
    - `SEEN_PATH`, `SCHEMA = "fc08-seen-items/1"`, `DECISIONS = ("accept", "drop")`;
    - `load(path) -> {(source, item_id): entry}`;
    - `dump(entries) -> str`;
    - `record_decisions(run_id, decided_on, decisions, path) -> list`.
  - `feeds.inbox`:
    - `INBOX_ROOT`, `ITEMS = "items.json"`;
    - `RUN_ID` (the regex `^feeds-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}$`);
    - `mint_run_id(day)`, `run_dir(run_id, root)`, `load(run_id, root)`, `save(run_id, state, root)`;
    - `write_file(run_id, rel, data, root) -> rel`, `items(state)`, `find_item(state, key)`.
  - `items.json`'s shape is `{"run_id": str, "sources": {<source>: {"items": [FeedItem.to_json() + {"document": None | {...}}], ...}}}`. Task 4 fills the other per-source fields.

- [ ] **Step 1: Write the model, the empty ledger and the ignore rule**

Create `feeds/__init__.py`:

```python
"""Slice 2: live publication feeds (spec docs/superpowers/specs/2026-09-26-slice2-live-intelligence-design.md)."""
```

Create `feeds/model.py`:

```python
"""The one shape of a listed item, shared by the adapters, the inbox, the ledger and the feeds server."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass


class LayoutChanged(Exception):
    """A listing no longer has the structure its adapter depends on. Reported loudly, never as "0 new items"."""


@dataclass(frozen=True)
class FeedItem:
    source: str
    # The publisher's own identifier: OFSI's Atom <id>, which carries a timestamp, so a REVISED
    # publication is a new item; FinCEN's and OFAC's last URL path segment.
    item_id: str
    title: str
    url: str
    published: str  # YYYY-MM-DD
    summary: str = ""

    @property
    def key(self) -> str:
        """The id the agent sees: fixed-width and DERIVED from the item, so an agent cannot mint one."""
        return "%s:%s" % (self.source, hashlib.sha256(self.item_id.encode("utf-8")).hexdigest()[:16])

    def to_json(self) -> dict:
        out = asdict(self)
        out["key"] = self.key
        return out
```

Create `data/feeds/seen.json` with exactly these bytes. This is the canonical form of an empty ledger: keys are sorted, the indent is 2, and there is a trailing newline.

```json
{
  "items": [],
  "schema": "fc08-seen-items/1"
}
```

Append to `.gitignore`:

```
# Slice 2: a feeds run's working folder (listings, fetched documents, items.json). Never tracked;
# a run's results enter tracked data only through tools/accept_run.py.
inbox/
```

- [ ] **Step 2: Write the guard**

Create `evals/check_feeds_ledger.py`:

```python
"""
Pin the seen-items ledger, the run inbox and the accept_run skeleton (slice 2, sub-project A).

Usage:
    python evals/check_feeds_ledger.py
    python evals/check_feeds_ledger.py --mutate unsorted        # ledger written in arrival order
    python evals/check_feeds_ledger.py --mutate allow-reseen    # an already-decided item may be decided again
    python evals/check_feeds_ledger.py --mutate escape-inbox    # a path outside the run's folder is written
    python evals/check_feeds_ledger.py --mutate overwrite-pin   # a pinned file is overwritten with other bytes
    python evals/check_feeds_ledger.py --mutate skip-coverage   # accept_run takes decisions that miss an item
    python evals/check_feeds_ledger.py --mutate accept-allowed  # accept_run records an accept it cannot carry out

WHAT IT HOLDS. "New" is decided by data/feeds/seen.json and nothing else, so that file must be
canonical (the same decisions give the same bytes), must never decide an item twice, and must be
written only by tools/accept_run.py, which refuses the whole run unless every listed item is decided
exactly once. In sub-project A an "accept" is refused: accepting also moves the item's record and
document into tracked data, which is sub-project C, and a ledger saying "accepted" over nothing
moved would be false. A run's inbox is written only inside inbox/<run_id>/, and a pinned file there
is immutable.

WRITER SCAN. Only feeds/ledger.py names seen.json and only tools/accept_run.py calls
record_decisions(), among the repository's Python files. The scanner is itself checked on a planted
rogue writer, so an empty scan cannot pass by matching nothing.

COLD. Temporary folders only; the tracked ledger is read, never written.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.model import FeedItem  # noqa: E402

LEDGER = ROOT / "feeds" / "ledger.py"
INBOX = ROOT / "feeds" / "inbox.py"
ACCEPT = ROOT / "tools" / "accept_run.py"
SELF = Path(__file__).resolve()
RUN = "feeds-2026-10-02-abc123"
TODAY = date(2026, 10, 2)

MUTATIONS = {
    "unsorted": (LEDGER, 'items = sorted(entries, key=lambda e: (e["source"], e["item_id"]))', "items = list(entries)"),
    "allow-reseen": (LEDGER, "        if key in seen:\n", "        if False:\n"),
    "escape-inbox": (INBOX, "    if folder not in target.parents:\n", "    if False:\n"),
    "overwrite-pin": (INBOX, "        if target.read_bytes() != data:\n", "        if False:\n"),
    "skip-coverage": (ACCEPT, "    if missing or extra:\n", "    if False:\n"),
    "accept-allowed": (ACCEPT, "    if accepted:\n", "    if False:\n"),
}


def load(name: str, path: Path, mutation) -> types.ModuleType:
    """Load a module from source, mutated when the mutation targets this file, and install it."""
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
    if package:
        setattr(importlib.import_module(package), leaf, module)
    return module


def writer_violations(files: dict) -> list:
    out = []
    for rel, text in sorted(files.items()):
        if "seen.json" in text and rel not in ("feeds/ledger.py", "evals/check_feeds_ledger.py"):
            out.append("%s names seen.json" % rel)
        if "record_decisions(" in text and rel not in ("feeds/ledger.py", "tools/accept_run.py",
                                                       "evals/check_feeds_ledger.py"):
            out.append("%s calls record_decisions()" % rel)
    return out


def repo_python() -> dict:
    skip = {".venv", ".superpowers", ".git", "__pycache__"}
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8", errors="replace")
            for p in ROOT.rglob("*.py") if not skip & set(p.relative_to(ROOT).parts)}


def item(source: str, item_id: str) -> dict:
    return dict(FeedItem(source, item_id, "Title " + item_id, "https://example.invalid/" + item_id,
                         "2026-10-01").to_json(), document=None)


def checks(ledger, inbox, accept) -> list:
    out = []
    tracked = ledger.SEEN_PATH.read_text(encoding="utf-8")
    out.append((tracked == ledger.dump(ledger.load().values()), "the tracked ledger loads and is in canonical form",
                "%d entries" % len(ledger.load())))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        a, b = tmp / "a.json", tmp / "b.json"
        for p in (a, b):
            p.write_text(ledger.dump([]), encoding="utf-8")
        ds = [{"source": "ofsi", "item_id": "z", "decision": "drop"},
              {"source": "fincen", "item_id": "m", "decision": "drop"},
              {"source": "ofac", "item_id": "a", "decision": "accept"}]
        ledger.record_decisions(RUN, "2026-10-02", ds, path=a)
        ledger.record_decisions(RUN, "2026-10-02", list(reversed(ds)), path=b)
        out.append((a.read_bytes() == b.read_bytes(), "the same decisions give the same bytes in any arrival order", ""))

        before = a.read_bytes()
        for label, call in (
                ("an already-decided item", lambda: ledger.record_decisions("feeds-2026-10-09-def456", "2026-10-09",
                                                                            [ds[0]], path=a)),
                ("an item decided twice in one call", lambda: ledger.record_decisions(
                    RUN, "2026-10-02", [dict(ds[0], item_id="n"), dict(ds[0], item_id="n")], path=a)),
                ("a decision that is not accept or drop", lambda: ledger.record_decisions(
                    RUN, "2026-10-02", [dict(ds[0], item_id="k", decision="keep")], path=a)),
                ("a malformed date", lambda: ledger.record_decisions(
                    RUN, "2 Oct", [dict(ds[0], item_id="q")], path=a))):
            try:
                call()
                refused = False
            except ValueError:
                refused = True
            out.append((refused and a.read_bytes() == before, "record_decisions refuses %s and writes nothing" % label, ""))

        root = tmp / "inbox"
        for label, rel in (("a parent-relative path", "../escape.txt"), ("an absolute path", str(tmp / "abs.txt"))):
            try:
                inbox.write_file(RUN, rel, b"x", root)
                refused = False
            except ValueError:
                refused = True
            out.append((refused and not (tmp / "escape.txt").exists() and not (tmp / "abs.txt").exists(),
                        "inbox.write_file refuses %s outside the run's folder" % label, rel))
        inbox.write_file(RUN, "docs/pinned.html", b"one", root)
        same = inbox.write_file(RUN, "docs/pinned.html", b"one", root) == "docs/pinned.html"
        try:
            inbox.write_file(RUN, "docs/pinned.html", b"two", root)
            refused = False
        except ValueError:
            refused = True
        out.append((same and refused and (root / RUN / "docs" / "pinned.html").read_bytes() == b"one",
                    "a pinned file takes the same bytes again and refuses different ones", ""))
        try:
            inbox.run_dir("../escape", root)
            refused = False
        except ValueError:
            refused = True
        out.append((refused, "a malformed run id is refused", ""))

        seen = tmp / "seen.json"
        seen.write_text(ledger.dump([]), encoding="utf-8")
        listed = [item("ofsi", "o1"), item("ofsi", "o2"), item("fincen", "f1")]
        inbox.save(RUN, {"run_id": RUN, "sources": {"ofsi": {"items": listed[:2]}, "fincen": {"items": listed[2:]}}},
                   root)
        keys = sorted(it["key"] for it in listed)

        def run(decisions: dict, *extra) -> tuple:
            f = tmp / "decisions.json"
            f.write_text(json.dumps(decisions), encoding="utf-8")
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = accept.main([RUN, "--decisions", str(f), *extra], inbox_root=root, seen_path=seen,
                                       today=TODAY)
            except Exception as exc:  # a crash is not a refusal: the check must fail, not the guard
                return None, "CRASHED: %s: %s" % (type(exc).__name__, exc)
            return code, buf.getvalue()

        empty = seen.read_bytes()
        for label, decisions in (("a decision missing for one item", {k: "drop" for k in keys[1:]}),
                                 ("a key the run did not list", dict({k: "drop" for k in keys}, **{"ofac:0": "drop"})),
                                 ("an accept", dict({k: "drop" for k in keys}, **{keys[0]: "accept"}))):
            code, said = run(decisions)
            out.append((code == 1 and "REFUSED" in said and seen.read_bytes() == empty,
                        "accept_run refuses %s and writes nothing" % label, said.strip()[:160]))
        code, said = run({k: "drop" for k in keys}, "--dry-run")
        out.append((code == 0 and "DRY RUN" in said and seen.read_bytes() == empty,
                    "a dry run writes nothing", said.strip()))
        code, said = run({k: "drop" for k in keys})
        got = ledger.load(seen)
        out.append((code == 0 and len(got) == 3 and all(e["first_seen_run"] == RUN and e["decision"] == "drop"
                                                         and e["decided_on"] == "2026-10-02" for e in got.values()),
                    "an all-drop run records every listed item, with its run and date", said.strip()))
        code, said = run({k: "drop" for k in keys})
        out.append((code == 1 and "already decided" in said, "the same run cannot be decided twice", said.strip()[:160]))
        f = tmp / "none.json"
        f.write_text("{}", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = accept.main(["feeds-2026-10-02-000000", "--decisions", str(f)], inbox_root=root, seen_path=seen)
        out.append((code == 1 and "no items.json" in buf.getvalue(), "a run with no inbox is refused", ""))

    real = writer_violations(repo_python())
    planted = writer_violations({"tools/rogue.py": "ledger.record_decisions(r, d, x)\nopen('data/feeds/seen.json')"})
    out.append((not real and len(planted) == 2, "only feeds/ledger.py names seen.json and only tools/accept_run.py "
                "records decisions (and a planted rogue writer is caught twice)",
                "violations %s; planted %s" % (real, planted)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the seen-items ledger, the inbox and accept_run")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    ledger = load("feeds.ledger", LEDGER, args.mutate)
    inbox = load("feeds.inbox", INBOX, args.mutate)
    accept = load("accept_run_under_test", ACCEPT, args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(ledger, inbox, accept):
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
```

Run: `.venv/bin/python evals/check_feeds_ledger.py`
Expected: a `FileNotFoundError` naming `feeds/ledger.py`. The guard loads `feeds/ledger.py`, `feeds/inbox.py` and `tools/accept_run.py` from source, and none exists yet.

- [ ] **Step 3: Write the ledger, the inbox and the skeleton**

Create `feeds/ledger.py`:

```python
"""
The seen-items ledger, data/feeds/seen.json: every listed item a person has already decided.

"New" means "not in this file", so the agent can never declare an item new or old. The file is
tracked, and tools/accept_run.py is its only writer (evals/check_feeds_ledger.py scans for any
other). A run that is never accepted leaves the file untouched, so its items are listed again the
next Friday. record_decisions() refuses the WHOLE call on any problem, so a partial write cannot
happen, and writes a canonical form (sorted, fixed layout), so the same decisions give the same
bytes whatever order they arrive in.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SEEN_PATH = ROOT / "data" / "feeds" / "seen.json"
SCHEMA = "fc08-seen-items/1"
DECISIONS = ("accept", "drop")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Key = Tuple[str, str]


def load(path: Path = SEEN_PATH) -> Dict[Key, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError("%s: schema %r, expected %r" % (path, data.get("schema"), SCHEMA))
    out: Dict[Key, dict] = {}
    for entry in data["items"]:
        key = (entry["source"], entry["item_id"])
        if key in out:
            raise ValueError("%s: %s:%s is recorded twice" % (path, key[0], key[1]))
        out[key] = entry
    return out


def dump(entries: Iterable[dict]) -> str:
    """The canonical bytes of the ledger holding these entries."""
    items = sorted(entries, key=lambda e: (e["source"], e["item_id"]))
    return json.dumps({"schema": SCHEMA, "items": items}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def record_decisions(run_id: str, decided_on: str, decisions: List[dict], path: Path = SEEN_PATH) -> List[dict]:
    if not DAY.match(decided_on):
        raise ValueError("decided_on %r is not YYYY-MM-DD" % decided_on)
    seen = load(path)
    new: Dict[Key, dict] = {}
    for d in decisions:
        key = (d["source"], d["item_id"])
        if d["decision"] not in DECISIONS:
            raise ValueError("%s:%s: decision %r is not one of %s" % (key[0], key[1], d["decision"], DECISIONS))
        if key in seen:
            raise ValueError("%s:%s was already decided, in run %s" % (key[0], key[1], seen[key]["first_seen_run"]))
        if key in new:
            raise ValueError("%s:%s is decided twice in one call" % key)
        new[key] = {"source": key[0], "item_id": key[1], "decision": d["decision"],
                    "first_seen_run": run_id, "decided_on": decided_on}
    tmp = Path(path).with_name("." + Path(path).name + ".tmp")
    tmp.write_text(dump(list(seen.values()) + list(new.values())), encoding="utf-8")
    os.replace(tmp, path)
    return list(new.values())
```

Create `feeds/inbox.py`:

```python
"""
One run's working folder, inbox/<run_id>/ (gitignored): the only place a feeds run writes.

  items.json          per source: when it was listed, the pinned listing, its status, and the NEW items
  listings/<source>.* the raw listing bytes the adapter parsed
  docs/<sha256>.<ext> each fetched document, named by its own hash

A pinned file is immutable: writing different bytes to an existing path is refused. Every path is
resolved and must stay inside the run's folder.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import date
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
INBOX_ROOT = ROOT / "inbox"
ITEMS = "items.json"
RUN_ID = re.compile(r"^feeds-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}$")


def mint_run_id(day: date) -> str:
    return "feeds-%s-%s" % (day.isoformat(), secrets.token_hex(3))


def run_dir(run_id: str, root: Path = INBOX_ROOT) -> Path:
    if not RUN_ID.match(run_id or ""):
        raise ValueError("run id %r is not feeds-YYYY-MM-DD-xxxxxx" % run_id)
    return Path(root) / run_id


def load(run_id: str, root: Path = INBOX_ROOT) -> dict:
    path = run_dir(run_id, root) / ITEMS
    if not path.exists():
        return {"run_id": run_id, "sources": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save(run_id: str, state: dict, root: Path = INBOX_ROOT) -> None:
    folder = run_dir(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (".%s.tmp" % ITEMS)
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, folder / ITEMS)


def write_file(run_id: str, rel: str, data: bytes, root: Path = INBOX_ROOT) -> str:
    folder = run_dir(run_id, root).resolve()
    target = (folder / rel).resolve()
    if folder not in target.parents:
        raise ValueError("%r is outside the run's inbox" % rel)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("%s is pinned; refusing to overwrite it with different bytes" % rel)
        return rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel


def items(state: dict) -> List[dict]:
    return [it for name in sorted(state["sources"]) for it in state["sources"][name].get("items", [])]


def find_item(state: dict, key: str) -> Optional[dict]:
    return next((it for it in items(state) if it["key"] == key), None)
```

Create `tools/accept_run.py`:

```python
"""
Decide the items of one feeds run: the ONLY way a live result enters tracked data.

Sub-project A builds the skeleton. It validates a run's decisions and records DROPS in the
seen-items ledger. Accepting an item also moves its record, queue file and document into the
tracked folders and gives it an advisory id (spec section 2); that path is sub-project C, and until
it exists an "accept" is refused, so the ledger can never say an item was accepted when nothing moved.

Usage:
    python tools/accept_run.py RUN_ID --decisions FILE [--dry-run]

FILE is JSON, {"<item key>": "accept" | "drop"}, with one entry for every item the run listed as
new, and nothing else. Any problem refuses the whole run; nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import inbox, ledger  # noqa: E402

ACCEPT_NOT_BUILT = ("accepting an item moves its record, queue file and document into tracked data, and that "
                    "path is built in sub-project C; this skeleton records drops only")


def plan(run_id: str, decisions: dict, *, inbox_root: Path = inbox.INBOX_ROOT,
         seen_path: Path = ledger.SEEN_PATH) -> list:
    """Validate everything and return the ledger entries to write. Raises ValueError on any problem."""
    if not (inbox.run_dir(run_id, inbox_root) / inbox.ITEMS).exists():
        raise ValueError("run %s has no %s in the inbox" % (run_id, inbox.ITEMS))
    if not isinstance(decisions, dict):
        raise ValueError("the decisions file must be a JSON object of item key -> decision")
    listed = {it["key"]: it for it in inbox.items(inbox.load(run_id, inbox_root))}
    missing, extra = sorted(set(listed) - set(decisions)), sorted(set(decisions) - set(listed))
    if missing or extra:
        raise ValueError("the decisions must cover every listed item exactly: missing %s, not listed %s"
                         % (missing, extra))
    bad = sorted(k for k, v in decisions.items() if v not in ledger.DECISIONS)
    if bad:
        raise ValueError("these decisions are not accept or drop: %s" % bad)
    accepted = sorted(k for k, v in decisions.items() if v == "accept")
    if accepted:
        raise ValueError("%s (accept requested for %s)" % (ACCEPT_NOT_BUILT, accepted))
    seen = ledger.load(seen_path)
    already = sorted(k for k, it in listed.items() if (it["source"], it["item_id"]) in seen)
    if already:
        raise ValueError("already decided in an earlier run: %s" % already)
    return [{"source": listed[k]["source"], "item_id": listed[k]["item_id"], "decision": decisions[k]}
            for k in sorted(listed)]


def main(argv: list, *, inbox_root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         today: date = None) -> int:
    ap = argparse.ArgumentParser(description="Decide the items of one feeds run")
    ap.add_argument("run_id")
    ap.add_argument("--decisions", required=True, type=Path, help="JSON: item key -> accept | drop")
    ap.add_argument("--dry-run", action="store_true", help="validate and say what would be written")
    args = ap.parse_args(argv)
    try:
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        entries = plan(args.run_id, decisions, inbox_root=inbox_root, seen_path=seen_path)
    except (ValueError, OSError) as exc:
        print("REFUSED: %s" % exc)
        return 1
    if args.dry_run:
        print("DRY RUN: would record %d decision(s) for run %s" % (len(entries), args.run_id))
        return 0
    ledger.record_decisions(args.run_id, (today or date.today()).isoformat(), entries, path=seen_path)
    print("RECORDED: %d decision(s) for run %s in %s" % (len(entries), args.run_id, seen_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the guard and every mutation**

```bash
.venv/bin/python evals/check_feeds_ledger.py
for m in unsorted allow-reseen escape-inbox overwrite-pin skip-coverage accept-allowed; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_ledger.py --mutate $m | tail -1; done
```

Expected:
- `HELD (0 failures)`, with 17 PASS lines;
- each mutation `HELD: the mutation is detected`. The measured counts are unsorted 1, allow-reseen 4, escape-inbox 2, overwrite-pin 1, skip-coverage 5 and accept-allowed 3.

The writer scan must report no violations in the real repository.
- If it names a file, read that file.
- A legitimate new reader of `seen.json` must go through `feeds.ledger.load`, never the literal path.

- [ ] **Step 5: Register, check cold, commit**

In `tools/check_all.py`, add this directly after the `check_html_pages` entry:

```python
    ("check_feeds_ledger", ["evals/check_feeds_ledger.py"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add feeds/__init__.py feeds/model.py feeds/ledger.py feeds/inbox.py tools/accept_run.py data/feeds/seen.json evals/check_feeds_ledger.py .gitignore tools/check_all.py
git commit -m "Slice 2 A: the seen-items ledger, the run inbox and a drop-only accept_run"
```

---

### Task 3: the three source adapters and the allowlisted fetch

**Files:**
- Create: `feeds/sources.py`, `feeds/http.py`, `tools/feeds_probe.py`
- Create: `evals/check_feed_adapters.py`
- Modify: `tools/check_all.py` (one `GUARDS` entry)
- Read-only: `tests/fixtures/feeds/*` (committed with the plan)

**Interfaces:**
- Consumes: `feeds.model.FeedItem`, `LayoutChanged` (Task 2).
- Produces, for Task 4:
  - from `feeds.sources`:
    - `SOURCES: {"fincen" | "ofac" | "ofsi": Source}`, where `Source` has `name`, `listing_url`, `listing_ext` (`"html"` or `"atom"`), `listing_types`, `hosts` and `parse(raw) -> List[FeedItem]`;
    - `DOCUMENT_TYPES = {"text/html", "application/pdf"}`;
    - `MAX_LISTING_BYTES = 2_000_000`, `MAX_DOCUMENT_BYTES = 20_000_000`;
    - `linked_pdfs(raw, base_url) -> List[str]`;
  - from `feeds.http`:
    - `get(url, *, allowed_hosts, allowed_types, max_bytes) -> Fetched`;
    - `Fetched(url, final_url, content_type, body)`;
    - `FetchRefused`, `USER_AGENT`, `REQUEST_GAP_SECONDS = 2.0`.

- [ ] **Step 1: Write the guard**

Create `evals/check_feed_adapters.py`:

```python
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
```

Run: `.venv/bin/python evals/check_feed_adapters.py`
Expected: a `FileNotFoundError` naming `feeds/http.py`.

- [ ] **Step 2: Write the fetch and the adapters**

Create `feeds/http.py`:

```python
from __future__ import annotations
import time, urllib.request, urllib.error
from dataclasses import dataclass
from typing import FrozenSet, Optional
from urllib.parse import urlsplit

USER_AGENT = "NEXUS-FC08-threat-intel/2.0 (+https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence)"
REQUEST_GAP_SECONDS = 2.0
TIMEOUT_SECONDS = 30
_last_request = [0.0]

class FetchRefused(Exception):
    pass

@dataclass(frozen=True)
class Fetched:
    url: str
    final_url: str
    content_type: str
    body: bytes

def _check_host(url: str, allowed_hosts: FrozenSet[str]) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or parts.hostname not in allowed_hosts:
        raise FetchRefused("%s is not on the allowlist %s" % (url, sorted(allowed_hosts)))

class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = allowed_hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect off the allowlist is refused here, BEFORE the request to the other host is made.
        _check_host(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def get(url: str, *, allowed_hosts: FrozenSet[str], allowed_types: FrozenSet[str], max_bytes: int) -> Fetched:
    _check_host(url, allowed_hosts)
    wait = _last_request[0] + REQUEST_GAP_SECONDS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    opener = urllib.request.build_opener(_Redirects(allowed_hosts))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in allowed_types:
                raise FetchRefused("%s answered %r, not one of %s" % (url, ctype, sorted(allowed_types)))
            body = resp.read(max_bytes + 1)
            final = resp.geturl()
    except urllib.error.URLError as exc:
        raise FetchRefused("%s could not be fetched: %s" % (url, getattr(exc, "reason", exc)))
    finally:
        _last_request[0] = time.monotonic()
    if len(body) > max_bytes:
        raise FetchRefused("%s is larger than %d bytes" % (url, max_bytes))
    _check_host(final, allowed_hosts)
    return Fetched(url, final, ctype, body)
```

Create `feeds/sources.py`:

```python
"""
The three automated sources and their adapters: raw listing bytes in, FeedItems out.

Each adapter checks the structural MARKER it depends on and raises LayoutChanged when it is
missing, when the marker is present but no item parses, or when an item lacks its link or date.
An empty result is never returned: each of these listings always shows its latest entries
(measured 2026-09-26: OFSI 20, FinCEN 15, OFAC 10), so "nothing parsed" means the page changed.

Measured 2026-09-26, and why fetch pins LANDING pages in sub-project A: the URL a FinCEN or OFSI
item lists is an HTML landing page; the advisory itself is a PDF linked from it (FinCEN on
www.fincen.gov, OFSI on assets.publishing.service.gov.uk). OFAC's recent action IS the HTML page.
linked_pdfs() records those links; following them is decided in sub-project C.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, FrozenSet, List
from urllib.parse import urljoin, urlsplit

from feeds.model import FeedItem, LayoutChanged

MAX_LISTING_BYTES = 2_000_000
MAX_DOCUMENT_BYTES = 20_000_000
DOCUMENT_TYPES = frozenset({"text/html", "application/pdf"})
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T")

# ---------------------------------------------------------------------------- OFSI: GOV.UK Atom

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_ofsi(raw: bytes) -> List[FeedItem]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LayoutChanged("ofsi: not well-formed XML (%s)" % exc)
    if root.tag != ATOM + "feed":
        raise LayoutChanged("ofsi: the root element is %r, not an Atom feed" % root.tag)
    items = []
    for entry in root.findall(ATOM + "entry"):
        eid, updated, title = (entry.findtext(ATOM + t) for t in ("id", "updated", "title"))
        link = entry.find(ATOM + "link[@rel='alternate']")
        if not (eid and updated and title and link is not None and link.get("href")):
            raise LayoutChanged("ofsi: an entry lacks its id, updated, title or alternate link")
        if not ISO_DATE.match(updated):
            raise LayoutChanged("ofsi: updated %r is not an ISO timestamp" % updated)
        items.append(FeedItem("ofsi", eid.strip(), " ".join(title.split()), link.get("href"), updated[:10],
                              " ".join((entry.findtext(ATOM + "summary") or "").split())))
    if not items:
        raise LayoutChanged("ofsi: the feed parsed but holds no entries")
    return items

# ---------------------------------------------------------------------------- the HTML listings


class _Events(HTMLParser):
    """Start tags, end tags and text in document order: the one walker both HTML listings use."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list = []

    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, dict(attrs)))

    def handle_endtag(self, tag):
        self.events.append(("end", tag, {}))

    def handle_data(self, data):
        self.events.append(("text", data, {}))


def _events(source: str, raw: bytes) -> list:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LayoutChanged("%s: the listing is not UTF-8 (%s)" % (source, exc))
    parser = _Events()
    parser.feed(text)
    parser.close()
    return parser.events


def _classes(attrs: dict) -> set:
    return set((attrs.get("class") or "").split())


FINCEN_BASE = "https://www.fincen.gov"


def parse_fincen(raw: bytes) -> List[FeedItem]:
    events = _events("fincen", raw)
    if not any(k == "start" and t == "th" and a.get("id") == "view-title-table-column" for k, t, a in events):
        raise LayoutChanged("fincen: the listing table (th#view-title-table-column) is missing")
    items, row = [], None
    for kind, tag, attrs in events:
        if kind == "start" and tag == "tr":
            row = {"href": None, "title": [], "date": None, "subject": [], "in_a": False, "in_subject": False}
        elif row is None:
            continue
        elif kind == "start" and tag == "a" and row["href"] is None \
                and (attrs.get("href") or "").startswith("/resources/advisories/"):
            row["href"], row["in_a"] = attrs["href"], True
        elif kind == "end" and tag == "a":
            row["in_a"] = False
        elif kind == "start" and tag == "time" and row["date"] is None:
            row["date"] = attrs.get("datetime")
        elif kind == "start" and tag == "td" and attrs.get("headers") == "view-field-advisory-subject-table-column":
            row["in_subject"] = True
        elif kind == "end" and tag == "td":
            row["in_subject"] = False
        elif kind == "text" and row["in_a"]:
            row["title"].append(tag)
        elif kind == "text" and row["in_subject"]:
            row["subject"].append(tag)
        elif kind == "end" and tag == "tr":
            if row["href"]:
                if not (row["date"] and ISO_DATE.match(row["date"])):
                    raise LayoutChanged("fincen: the row for %s has no <time datetime>" % row["href"])
                items.append(FeedItem("fincen", row["href"].rstrip("/").rsplit("/", 1)[1],
                                      " ".join("".join(row["title"]).split()),
                                      urljoin(FINCEN_BASE, row["href"]), row["date"][:10],
                                      " ".join("".join(row["subject"]).split())))
            row = None
    if not items:
        raise LayoutChanged("fincen: the table is present but no advisory row parsed")
    return items


OFAC_BASE = "https://ofac.treasury.gov"
OFAC_DATE = re.compile(r"^\s*([A-Z][a-z]+) (\d{2}), (\d{4})\s*-")
# Month names by table, not strptime("%B"), which follows the process locale.
MONTHS = {m: n for n, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"), 1)}


def parse_ofac(raw: bytes) -> List[FeedItem]:
    events = _events("ofac", raw)
    if not any(k == "start" and "view-recent-actions-search" in _classes(a) for k, t, a in events):
        raise LayoutChanged("ofac: the recent-actions view (div.view-recent-actions-search) is missing")
    items, row, depth = [], None, 0
    for kind, tag, attrs in events:
        if kind == "start" and tag == "div" and {"search-result", "views-row"} <= _classes(attrs):
            row, depth = {"href": None, "title": [], "date": None, "in_a": False}, 0
        if row is None:
            continue
        if kind == "start" and tag == "div":
            depth += 1
        elif kind == "end" and tag == "div":
            depth -= 1
            if depth == 0:
                if not row["href"] or not row["date"]:
                    raise LayoutChanged("ofac: a views-row lacks its link or its 'Month DD, YYYY -' date line")
                items.append(FeedItem("ofac", row["href"].rstrip("/").rsplit("/", 1)[1],
                                      " ".join("".join(row["title"]).split()),
                                      urljoin(OFAC_BASE, row["href"]), row["date"]))
                row = None
        elif kind == "start" and tag == "a" and row["href"] is None \
                and (attrs.get("href") or "").startswith("/recent-actions/"):
            row["href"], row["in_a"] = attrs["href"], True
        elif kind == "end" and tag == "a":
            row["in_a"] = False
        elif kind == "text" and row["in_a"]:
            row["title"].append(tag)
        elif kind == "text" and row["href"] and row["date"] is None:
            m = OFAC_DATE.match(tag)
            if m and m.group(1) in MONTHS:
                row["date"] = "%s-%02d-%s" % (m.group(3), MONTHS[m.group(1)], m.group(2))
    if not items:
        raise LayoutChanged("ofac: the view is present but no views-row parsed")
    return items

# ---------------------------------------------------------------------------- the registry


@dataclass(frozen=True)
class Source:
    name: str
    listing_url: str
    listing_ext: str
    listing_types: FrozenSet[str]
    hosts: FrozenSet[str]  # the listing's host and every item URL's host
    parse: Callable[[bytes], List[FeedItem]]


SOURCES = {
    "fincen": Source("fincen", "https://www.fincen.gov/resources/advisoriesbulletinsfact-sheets/advisories", "html",
                     frozenset({"text/html"}), frozenset({"www.fincen.gov"}), parse_fincen),
    "ofac": Source("ofac", "https://ofac.treasury.gov/recent-actions", "html",
                   frozenset({"text/html"}), frozenset({"ofac.treasury.gov"}), parse_ofac),
    "ofsi": Source("ofsi", "https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation.atom",
                   "atom", frozenset({"application/atom+xml"}), frozenset({"www.gov.uk"}), parse_ofsi),
}


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: List[str] = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.append(href)


def linked_pdfs(raw: bytes, base_url: str) -> List[str]:
    """Absolute URLs of the PDFs an HTML page links to, first occurrence order. Listed, never fetched, in A."""
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
        if urlsplit(url).path.lower().endswith(".pdf") and url not in out:
            out.append(url)
    return out
```

- [ ] **Step 3: Run the guard and every mutation**

```bash
.venv/bin/python evals/check_feed_adapters.py
for m in no-marker-fincen empty-ok ofsi-link-id relative-url ofac-date-optional follow-redirects no-size-cap; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feed_adapters.py --mutate $m | tail -1; done
```

Expected:
- `HELD (0 failures)`, with 31 PASS lines;
- all seven mutations detected.

The measured counts are no-marker-fincen 1, empty-ok 1, ofsi-link-id 4, relative-url 3, ofac-date-optional 1, follow-redirects 1 and no-size-cap 1.

The follow-redirects check needs more than a refusal. It asserts that no request reached the other host. Without that, the final-URL check alone would still refuse, after the body had already been downloaded from off the allowlist.

- [ ] **Step 4: Write the live probe and run it once, by hand**

Create `tools/feeds_probe.py`:

```python
"""
Live probe: fetch each source's listing once, through the allowlisted fetch, and parse it.

Usage:
    python tools/feeds_probe.py

NETWORK. This is the one tool in sub-project A that makes requests; no guard calls it and
tools/check_all.py never runs it. It writes nothing. It answers one question -- does each adapter
still parse its LIVE listing -- and exits 1 naming the source when a layout changed or a source is
unreachable. Run it by hand before trusting a change to feeds/sources.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
from feeds.sources import MAX_LISTING_BYTES, SOURCES  # noqa: E402


def main() -> int:
    failed = 0
    for name in sorted(SOURCES):
        src = SOURCES[name]
        try:
            got = feeds_http.get(src.listing_url, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                                 max_bytes=MAX_LISTING_BYTES)
            items = src.parse(got.body)
        except (feeds_http.FetchRefused, LayoutChanged) as exc:
            print("  FAIL %-6s %s" % (name, exc))
            failed += 1
            continue
        print("  OK   %-6s %2d items, newest %s, oldest %s (%d bytes)" % (
            name, len(items), max(i.published for i in items), min(i.published for i in items), len(got.body)))
    print("\n%s" % ("ALL SOURCES PARSE" if not failed else "%d SOURCE(S) FAILED" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `.venv/bin/python tools/feeds_probe.py`

Expected (measured 2026-09-26; the counts can move as publishers post):

```
  OK   fincen 15 items, newest 2026-06-05, oldest 2020-11-06 (48982 bytes)
  OK   ofac   10 items, newest 2026-09-24, oldest 2026-09-04 (44818 bytes)
  OK   ofsi   20 items, newest 2026-09-24, oldest 2026-05-19 (12416 bytes)

ALL SOURCES PARSE
```

Copy the actual output into the task report.
- A `FAIL … layout` line means the live page moved since the snapshot. Report it; do not edit the adapter to match without saying so.
- A network failure is not a code defect. Report it, and move on.

- [ ] **Step 5: Register, check cold, commit**

In `tools/check_all.py`, add this directly after the `check_feeds_ledger` entry:

```python
    ("check_feed_adapters", ["evals/check_feed_adapters.py"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add feeds/sources.py feeds/http.py tools/feeds_probe.py evals/check_feed_adapters.py tools/check_all.py
git commit -m "Slice 2 A: OFSI, FinCEN and OFAC adapters with loud layout guards, and an allowlisted fetch"
```

---

### Task 4: the `feeds` MCP server's `feeds_list_new` and `feeds_fetch`

**Files:**
- Create: `mcp_server/feeds_server.py`
- Create: `evals/check_feeds_server.py`
- Modify: `tools/check_all.py` (one `GUARDS` entry), `CLAUDE.md` (one new section)

**Interfaces:**
- Consumes: everything Tasks 1-3 produce (names listed in their Interfaces blocks).
- Produces, for sub-projects B and C:
  - the MCP tools `feeds_list_new(source)` and `feeds_fetch(item_key)` on the server named `feeds_mcp`;
  - the run identity from the environment variable `FEEDS_RUN_ID`;
  - module attributes `INBOX_ROOT`, `SEEN_PATH` and `HTTP_GET`, which only guards swap;
  - the per-source entry in `items.json`: `listed_at`, `listing_url`, `status` (`ok`, `unreachable` or `layout_changed`), `error`, `listing`, `listing_sha256`, `listed`, `already_seen`, `items`;
  - per item, `document`: `path`, `sha256`, `content_type`, `bytes`, `final_url`, `fetched_at`, `pages`, `text_pages`, `page_error`, `linked_pdfs`; or a `fetch_error` string.

- [ ] **Step 1: Write the guard**

Create `evals/check_feeds_server.py`:

```python
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
```

Run: `.venv/bin/python evals/check_feeds_server.py`
Expected: a `FileNotFoundError` naming `mcp_server/feeds_server.py`.

- [ ] **Step 2: Write the server**

Create `mcp_server/feeds_server.py`:

```python
"""
The feeds MCP server: the orchestrator's only way to see and fetch new publications (slice 2).

Each tool carries one invariant, whatever the agent intends (spec section 1):

  feeds_list_new(source)  "new" is decided by the committed seen-items ledger, never by the agent;
                          only the three allowlisted sources exist; a listing is fetched at most once
                          per run; a listing whose layout no longer parses is a loud failure, never
                          "0 new items".
  feeds_fetch(item_key)   fetches only the URL of an item THIS RUN listed, on its source's
                          allowlisted hosts (redirects included), within size and type limits; pins
                          the document by sha256; a second call does not fetch again.

Both write only into inbox/<run_id>/ (feeds/inbox.py). The run identity comes from the runner's
environment (FEEDS_RUN_ID), never from a tool argument. feeds_triage and feeds_extract are
sub-projects B and C.

Works on MCP Python SDK 2.x (MCPServer) and 1.x (FastMCP).
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
# The server is launched as a script, so the repo root is not on sys.path.
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http, inbox, ledger  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, MAX_LISTING_BYTES, SOURCES, linked_pdfs  # noqa: E402
from schemas.citation_match import PageIndex  # noqa: E402

RUN_ENV = "FEEDS_RUN_ID"
# Module attributes, never tool arguments, so the agent cannot choose them. A guard swaps them.
INBOX_ROOT = inbox.INBOX_ROOT
SEEN_PATH = ledger.SEEN_PATH
HTTP_GET = feeds_http.get

mcp = FastMCP("feeds_mcp")


class ListNewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., pattern=r"^(ofsi|fincen|ofac)$", description="ofsi, fincen or ofac")


class FetchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key feeds_list_new returned in this run")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id():
    run_id = os.environ.get(RUN_ENV, "")
    return run_id if inbox.RUN_ID.match(run_id) else None


NO_RUN = "Refused: this server has no run identity (%s is unset or malformed); the runner sets it." % RUN_ENV


@mcp.tool(
    name="feeds_list_new",
    annotations={"title": "List new items", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": True},
)
async def list_new(params: ListNewInput) -> str:
    """
    List a source's publications that no one has decided yet.

    Fetches the source's listing once per run. An item is new only if it is not in the seen-items
    ledger; you cannot declare an item new or old. Returns one row per new item:
    key | published | title | summary. Pass a key to feeds_fetch to download that item.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    state = inbox.load(run_id, INBOX_ROOT)
    if params.source in state["sources"]:
        return "Refused: %s was already listed in this run (status %s); a listing is fetched once per run." % (
            params.source, state["sources"][params.source]["status"])
    src = SOURCES[params.source]
    entry = {"listed_at": _now(), "listing_url": src.listing_url, "status": "ok", "error": None, "listing": None,
             "listing_sha256": None, "listed": 0, "already_seen": 0, "items": []}
    state["sources"][params.source] = entry
    try:
        got = HTTP_GET(src.listing_url, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                       max_bytes=MAX_LISTING_BYTES)
    except feeds_http.FetchRefused as exc:
        entry.update(status="unreachable", error=str(exc))
        inbox.save(run_id, state, INBOX_ROOT)
        return "Failed: %s is unreachable: %s. Report it; it is not retried in this run." % (params.source, exc)
    entry["listing"] = inbox.write_file(run_id, "listings/%s.%s" % (params.source, src.listing_ext), got.body,
                                        INBOX_ROOT)
    entry["listing_sha256"] = hashlib.sha256(got.body).hexdigest()
    try:
        items = src.parse(got.body)
    except LayoutChanged as exc:
        entry.update(status="layout_changed", error=str(exc))
        inbox.save(run_id, state, INBOX_ROOT)
        return "Failed: layout changed: %s. The listing is saved in the inbox. This is not '0 new items'." % exc
    seen = ledger.load(SEEN_PATH)
    new = [it for it in items if (it.source, it.item_id) not in seen]
    entry.update(listed=len(items), already_seen=len(items) - len(new),
                 items=[dict(it.to_json(), document=None) for it in new])
    inbox.save(run_id, state, INBOX_ROOT)
    if not new:
        return "No new items: %s listed %d, every one already decided." % (params.source, len(items))
    rows = ["%s | %s | %s | %s" % (it.key, it.published, it.title, it.summary or "-") for it in new]
    return "%d new of %d listed on %s:\nkey | published | title | summary\n%s" % (
        len(new), len(items), params.source, "\n".join(rows))


def _describe(doc: dict) -> str:
    pages = ("%d page(s), %d with text" % (doc["pages"], doc["text_pages"]) if doc["page_error"] is None
             else "NOT PAGED (%s)" % doc["page_error"])
    links = ("; it links %d PDF(s), not fetched: %s" % (len(doc["linked_pdfs"]), ", ".join(doc["linked_pdfs"]))
             if doc["linked_pdfs"] else "")
    return "%s (%s, %d bytes, sha256 %s), %s%s" % (doc["path"], doc["content_type"], doc["bytes"], doc["sha256"],
                                                    pages, links)


@mcp.tool(
    name="feeds_fetch",
    annotations={"title": "Fetch an item's document", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": True},
)
async def fetch(params: FetchInput) -> str:
    """
    Download the document of an item feeds_list_new listed in this run, and pin it by sha256.

    You give the key, never a URL: the tool fetches the item's own listed URL, on its source's
    allowlisted hosts only. Returns the pinned file, its size, its number of text pages, and any
    PDFs the page links to (listed, not fetched). A second call for the same item returns the
    pinned file without fetching again.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    state = inbox.load(run_id, INBOX_ROOT)
    item = inbox.find_item(state, params.item_key)
    if item is None:
        return "Refused: %s was not listed as new in this run; call feeds_list_new first." % params.item_key
    if item.get("document"):
        return "Already fetched: %s" % _describe(item["document"])
    src = SOURCES[item["source"]]
    try:
        got = HTTP_GET(item["url"], allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES,
                       max_bytes=MAX_DOCUMENT_BYTES)
    except feeds_http.FetchRefused as exc:
        item["fetch_error"] = str(exc)
        inbox.save(run_id, state, INBOX_ROOT)
        return "Failed: %s could not be fetched: %s" % (params.item_key, exc)
    sha = hashlib.sha256(got.body).hexdigest()
    is_pdf = got.content_type == "application/pdf"
    rel = inbox.write_file(run_id, "docs/%s.%s" % (sha, "pdf" if is_pdf else "html"), got.body, INBOX_ROOT)
    try:
        index = (PageIndex.from_pdf(inbox.run_dir(run_id, INBOX_ROOT) / rel) if is_pdf
                 else PageIndex.from_html(got.body))
        pages, text_pages, error = len(index), sum(1 for p in index.pages if p.strip()), None
    except Exception as exc:  # the document stays pinned, and the failure is recorded and returned
        pages, text_pages, error = 0, 0, "%s: %s" % (type(exc).__name__, exc)
    item["document"] = {"path": rel, "sha256": sha, "content_type": got.content_type, "bytes": len(got.body),
                        "final_url": got.final_url, "fetched_at": _now(), "pages": pages,
                        "text_pages": text_pages, "page_error": error,
                        "linked_pdfs": [] if is_pdf else linked_pdfs(got.body, got.final_url)}
    inbox.save(run_id, state, INBOX_ROOT)
    return "Fetched: %s" % _describe(item["document"])


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 3: Run the guard and every mutation**

```bash
.venv/bin/python evals/check_feeds_server.py
for m in no-ledger-filter relist refetch unlisted-fetch quiet-layout; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_server.py --mutate $m | tail -1; done
```

Expected:
- `HELD (0 failures)`, with 16 PASS lines;
- all five mutations detected. The measured counts are no-ledger-filter 2, relist 2, refetch 1, unlisted-fetch 1 and quiet-layout 1.

The git-status check compares the repository's status before and after the guard. Run the guard with the working tree in whatever state it is in: it compares, it does not require clean.

Also run `.venv/bin/python evals/check_tool_surface.py`. Expected: `HELD`. The Knowledge Centre surface is unchanged, and no agent is given the feeds tools in A.

- [ ] **Step 4: Record the feeds layer in CLAUDE.md**

Append this section to the end of `CLAUDE.md`:

```markdown
## Slice 2: live feeds (sub-project A, built 2026-09)

Spec: `docs/superpowers/specs/2026-09-26-slice2-live-intelligence-design.md`. Plan: `docs/superpowers/plans/2026-09-26-slice2-a-foundations-and-sources.md`.

| File | What it holds |
|---|---|
| `feeds/model.py` | `FeedItem`; its `key` (`<source>:<16 hex>`) is derived, so an agent cannot mint one; `LayoutChanged` |
| `feeds/ledger.py` | `data/feeds/seen.json`, the ONLY record of what is new. Tracked. Written only by `tools/accept_run.py` (writer scan in `evals/check_feeds_ledger.py`) |
| `feeds/inbox.py` | `inbox/<run_id>/` (gitignored): `items.json`, `listings/`, `docs/<sha256>.<ext>`. Pinned files are immutable; paths cannot leave the run's folder |
| `feeds/sources.py` | the OFSI (Atom), FinCEN and OFAC (HTML listing) adapters. Each raises `LayoutChanged` when its marker is gone, when nothing parses, or when an item has no date -- never "0 new items" |
| `feeds/http.py` | the one fetch: allowlisted hosts (a redirect off the list is refused BEFORE the request), content types, a size cap, a 2-second gap, a descriptive user agent |
| `mcp_server/feeds_server.py` | `feeds_list_new(source)` and `feeds_fetch(item_key)`. Run identity from `FEEDS_RUN_ID`; the agent never supplies a URL |
| `tools/accept_run.py` | the only way live results enter tracked data. In A it records DROPS only; `accept` is refused until sub-project C builds the move |
| `tools/feeds_probe.py` | the one tool that touches the network in A: parses each LIVE listing, by hand, never from `check_all` |
| `schemas/html_pages.py` | the HTML pagination rule behind `PageIndex.from_html`: `<main>`, else `<article>`, else `<body>`; chrome dropped; whole paragraphs; pages of about 3000 characters. **Changing it re-pages every HTML citation**; both page digests are pinned in `evals/check_html_pages.py` |

**Measured 2026-09-26: FinCEN's and OFSI's listed URLs are landing pages.** The advisory is a PDF linked from them. `feeds_fetch` pins the landing page and records its linked PDFs, but does not fetch them; following them is a sub-project C decision. OFAC's recent action is the page itself.

**An OFSI item's id carries its Atom timestamp**, so a revised GOV.UK publication is a new item.
```

- [ ] **Step 5: Register, check cold, commit**

In `tools/check_all.py`, add this directly after the `check_feed_adapters` entry:

```python
    ("check_feeds_server", ["evals/check_feeds_server.py"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add mcp_server/feeds_server.py evals/check_feeds_server.py tools/check_all.py CLAUDE.md
git commit -m "Slice 2 A: the feeds MCP server -- list_new decided by the ledger, fetch pinned to the inbox"
```

---

### Task 5: the walkthrough's resolver and ingestion sentences, made computed (defuses the tripwire)

**This is the only task that changes the published page, so its commit needs a republish. STOP before Step 7 and get the owner's go.**

**Files:**
- Modify: `agents/telemetry.py`, `agents/extract_advisory.py`, `agents/review_advisory.py`, `evals/check_telemetry.py`
- Modify: `tools/build_walkthrough.py`, `evals/check_walkthrough.py`
- Regenerate: `site/threat-intel/index.html`. Then, after the publish, `site/PUBLISHED`.
- Modify: `CLAUDE.md` (the tripwire sentence)

**Interfaces:**
- Consumes: `feeds.ledger.load` (Task 2).
- Produces:
  - `telemetry.run_started(run, model, max_budget_usd, max_turns, tools)`, whose `RUN_STARTED` payload carries `tools` (a list of qualified tool names);
  - `agents.extract_advisory.AGENT_TOOLS`.

- [ ] **Step 1: Record the agent's tools in `RUN_STARTED`**

In `agents/telemetry.py`, replace:

```python
def run_started(run, model: str, max_budget_usd: float, max_turns: int) -> dict:
    return emit(run, RUN_STARTED, SUCCESS, "%s run started" % run.stage, model=model,
                max_budget_usd=max_budget_usd, max_turns=max_turns, pdf_sha256=run.pdf_sha256)
```

with:

```python
def run_started(run, model: str, max_budget_usd: float, max_turns: int, tools) -> dict:
    """`tools` is every qualified tool name the agent can call. It is recorded so what a run HAD is
    measured, not inferred from its date (the walkthrough's section 10 counts it)."""
    return emit(run, RUN_STARTED, SUCCESS, "%s run started" % run.stage, model=model,
                max_budget_usd=max_budget_usd, max_turns=max_turns, pdf_sha256=run.pdf_sha256,
                tools=list(tools))
```

In `agents/extract_advisory.py`, add this directly after the `KC_TOOLS = (...)` tuple:

```python
# The qualified names the agent can call, recorded in RUN_STARTED (agents/telemetry.run_started).
AGENT_TOOLS = tuple("mcp__%s__%s" % (SERVER_KEY, name) for name in KC_TOOLS)
```

Then change its call `telemetry.run_started(run, model, max_budget_usd, max_turns)` to `telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS)`.

In `agents/review_advisory.py`:
- add `AGENT_TOOLS` to its existing `from agents.extract_advisory import ...` line;
- change `run_telemetry.run_started(run, model, max_budget_usd, max_turns)` to `run_telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS)`.

Run `grep -rn "run_started(" --include=*.py . | grep -v "\.venv\|\.superpowers"`. Every caller must now pass tools.

In `evals/check_telemetry.py`, replace:

```python
    started = telemetry.run_started(RUN, "claude-sonnet-5", 5.0, 60)
```

with:

```python
    started = telemetry.run_started(RUN, "claude-sonnet-5", 5.0, 60,
                                    ("mcp__knowledge_centre__knowledge_centre_resolve_actor",))
```

In the same check's condition, add `and started["payload"]["tools"] == ["mcp__knowledge_centre__knowledge_centre_resolve_actor"]` after `started["payload"]["model"] == "claude-sonnet-5"`. Change its label to:

```
"run_started records the agent's tools; run_completed its validated flag and terminal_check"
```

Run: `.venv/bin/python evals/check_telemetry.py`. Expected: `HELD (0 failures)`.

- [ ] **Step 2: Change the guard first**

In `evals/check_walkthrough.py`, make each edit below.

**(a) Mutations.** In the usage docstring, replace the line:

```
    python evals/check_walkthrough.py --mutate proposal-date   # the newest-proposal date ignores the run queues; MUST fail
```

with:

```
    python evals/check_walkthrough.py --mutate resolver-runs   # #limits' resolver counts skip a committed run; MUST fail
    python evals/check_walkthrough.py --mutate resolver-prompt # #limits misstates whether the prompt names the resolver; MUST fail
    python evals/check_walkthrough.py --mutate feed-accepted   # #limits' accepted-feed-items count is off by one; MUST fail
```

In `MUTATIONS`, replace `"proposal-date", ` with `"resolver-runs", "resolver-prompt", "feed-accepted", `.

**(b) The typed date.** Delete the `_resolver_added()` function. Delete `SERVER = "mcp_server/knowledge_centre_server.py"` if nothing else uses `SERVER` (grep first). Keep `NOT_RUN` and `main`'s handling of it.

**(c) The ingestion bullet.** Replace:

```python
    out.append(("no live ingestion" in lim and "Nothing flows into detection yet" in lim,
                "#limits says the corpus is a fixed list with no live ingestion, and that nothing flows into "
                "detection yet", ""))
```

with:

```python
    out.append(("Live ingestion is being built" in lim and "Nothing flows into detection yet" in lim,
                "#limits says live ingestion is still being built, and that nothing flows into detection yet", ""))
```

**(d) The guard's OWN counts.** Directly before `want_lim = {`, insert this block. It reads the files itself and does not call the builder's function, so the two can disagree:

```python
    runs = sorted(q.stem for q in QUEUE_DIR.glob("*.jsonl"))
    with_tool = no_record = resolved = 0
    for run in runs:
        tel = ROOT / "data" / "telemetry" / ("%s.jsonl" % run)
        evs = ([json.loads(line) for line in tel.read_text(encoding="utf-8").splitlines() if line.strip()]
               if tel.exists() else [])
        start = next((ev for ev in evs if ev.get("stage") == "RUN_STARTED"), None)
        tools = None if start is None else start["payload"].get("tools")
        no_record += tools is None
        with_tool += tools is not None and any(t.endswith("__knowledge_centre_resolve_actor") for t in tools)
        resolved += any(ev.get("stage") == "FC08_TOOL_CALL"
                        and ev["payload"].get("tool", "").endswith("__knowledge_centre_resolve_actor")
                        and ev["payload"].get("outcome", "").startswith('{"result":"Resolved: ') for ev in evs)
    feed_accepted = sum(1 for e in json.loads((ROOT / "data" / "feeds" / "seen.json").read_text(encoding="utf-8"))
                        ["items"] if e["decision"] == "accept")
```

Then, in `want_lim`, replace its last entry `"emergent-undecided": str(len(undecided_emergent))}` with:

```python
                "emergent-undecided": str(len(undecided_emergent)),
                "feed-accepted": str(feed_accepted),
                "extraction-runs": str(len(runs)), "runs-with-resolver": str(with_tool),
                "runs-no-tool-record": str(no_record), "runs-resolved": str(resolved)}
```

**(e) The date check.** Replace the whole block that starts:

```python
    newest = max(json.loads(line)["proposed_at"][:10] for q in [LEGACY_QUEUE] + sorted(QUEUE_DIR.glob("*.jsonl"))
```

and ends with:

```python
                    "git %s; page %s" % (added, shown_added)))
```

with:

```python
    flag = _attrs(lim, "data-flag").get("prompt-names-resolver")
    names = "resolve_actor" in SYSTEM_PROMPT
    out.append((flag == ("name" if names else "do not name") and not _attrs(lim, "data-date"),
                "#limits says truly whether the extractor's prompt names resolve_actor, and carries no typed date",
                "prompt names it: %s; page %r" % (names, flag)))
```

If `LEGACY_QUEUE` is now unused in the guard, drop it from its import.

Run: `.venv/bin/python evals/check_walkthrough.py`.
Expected: REFUSED, because the committed page still carries the old sentences. Among the failures:
- the `#limits` count check names `feed-accepted` and `extraction-runs`;
- the ingestion and prompt-flag checks fail.

That is the failing test.

- [ ] **Step 3: Change the builder**

In `tools/build_walkthrough.py`:

**(a) Imports and the typed date.**
- Change `from agents.extract_advisory import KC_TOOLS, SYSTEM_PROMPT  # noqa: E402` to `from agents.extract_advisory import SYSTEM_PROMPT  # noqa: E402`.
- Add `from feeds import ledger as feeds_ledger  # noqa: E402` after the `from agents...` imports.
- Delete these three lines:

```python
# The day the resolver tool entered the Knowledge Centre (commit 891b2b0). The builder may not call git;
# evals/check_walkthrough.py holds this date against the repository history.
RESOLVER_ADDED = "2026-09-25"
```

**(b) The count.** Add this module-level function directly above the function that contains the block replaced in (c):

```python
def _resolver_runs() -> dict:
    """Section 10's resolver counts, from the committed queues and their telemetry. A run is COMMITTED
    when it has a queue file; it HAD the resolver when its RUN_STARTED event lists the tool; it has NO
    RECORD when it has no telemetry or its RUN_STARTED predates the tools field; it RESOLVED when a
    resolver call answered "Resolved:"."""
    runs = sorted(q.stem for q in QUEUE_DIR.glob("*.jsonl"))
    if _MUTATE == "resolver-runs":
        runs = runs[1:]
    out = {"runs": runs, "with_tool": [], "no_record": [], "resolved": []}
    for run in runs:
        path = telemetry.TELEMETRY_DIR / ("%s.jsonl" % run)
        events = ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                  if path.exists() else [])
        started = [ev for ev in events if ev.get("stage") == telemetry.RUN_STARTED]
        tools = started[0]["payload"].get("tools") if started else None
        if tools is None:
            out["no_record"].append(run)
        elif any(t.endswith("__" + RESOLVER) for t in tools):
            out["with_tool"].append(run)
        if any(ev.get("stage") == telemetry.TOOL_CALL and ev["payload"].get("tool", "").endswith("__" + RESOLVER)
               and ev["payload"].get("outcome", "").startswith('{"result":"Resolved: ') for ev in events):
            out["resolved"].append(run)
    return out
```

**(c) The refusal.** Replace this block:

```python
    # Section 10: "the extractor is not asked to resolve actors" must stay true to be said -- the
    # substring, so any spelling of the tool in the prompt counts as asking.
    if "resolve_actor" in SYSTEM_PROMPT:
        raise ValueError("the extractor's prompt now names resolve_actor; section 10 says it does not")
    # "No committed extraction had the resolver": every committed queue's newest proposal predates it.
    queues = [LEGACY_QUEUE] + sorted(QUEUE_DIR.glob("*.jsonl"))
    if _MUTATE == "proposal-date":
        queues = [LEGACY_QUEUE]
    newest = max(json.loads(line)["proposed_at"][:10] for q in queues
                 for line in q.read_text(encoding="utf-8").splitlines() if line.strip())
    if newest >= RESOLVER_ADDED:
        raise ValueError("a committed proposal is dated %s, on or after the resolver's %s; section 10 says no "
                         "committed extraction had it" % (newest, RESOLVER_ADDED))
```

with:

```python
    # Section 10's resolver sentence is COUNTED (slice 2 A). It replaced a refusal that would have fired
    # on the first new extraction's queue file and blocked every commit.
    resolver_runs = _resolver_runs()
```

**(d) The inputs.** In the returned dict, replace:

```python
        "resolver_available": RESOLVER in KC_TOOLS,
        "newest_proposal": newest,
```

with:

```python
        "resolver_runs": resolver_runs,
        "prompt_names_resolver": "resolve_actor" in SYSTEM_PROMPT,
        "feed_accepted": sum(1 for e in feeds_ledger.load().values() if e["decision"] == "accept"),
```

**(e) The section.** In `section_limits`, replace:

```python
    tools = ("the extraction agent&rsquo;s current instructions do not name it, though it is among the agent&rsquo;s tools"
             if inp["resolver_available"] else "the extraction agent neither has it among its tools nor is told of it")
```

with:

```python
    rr = inp["resolver_runs"]
    prompt = "name" if inp["prompt_names_resolver"] else "do not name"
    if _MUTATE == "resolver-prompt":
        prompt = "do not name" if prompt == "name" else "name"
    feed_accepted = inp["feed_accepted"] + (1 if _MUTATE == "feed-accepted" else 0)
```

Replace the first `<li>`:

```
    <li><strong>The corpus is fixed.</strong> <span data-count="advisories">%d</span> advisories on a fixed list, each pinned by its sha256, with no live ingestion: nothing fetches a new publication.</li>
```

with:

```
    <li><strong>The corpus is fixed.</strong> <span data-count="advisories">%d</span> advisories on a fixed list, each pinned by its sha256. Live ingestion is being built: a feeds server lists and fetches new publications into a local inbox, and <span data-count="feed-accepted">%d</span> feed items have been accepted into the corpus.</li>
```

Replace the `<li>` that starts `<li><strong>Actor resolution is not part of extraction.</strong>` (the whole line) with:

```
    <li><strong>Actor resolution during extraction is counted, not assumed.</strong> Of the <span data-count="extraction-runs">%d</span> committed extraction runs with a proposal queue, <span data-count="runs-with-resolver">%d</span> recorded <code>%s</code> among the agent&rsquo;s tools, <span data-count="runs-no-tool-record">%d</span> recorded no list of tools, and <span data-count="runs-resolved">%d</span> resolved an actor with it. The extraction agent&rsquo;s current instructions <span data-flag="prompt-names-resolver">%s</span> it. Section 6&rsquo;s resolution was run over the committed records, after extraction.</li>
```

Replace the head of the format tuple:

```python
""" % (n_corpus, RESOLVER, RESOLVER_ADDED, e(inp["newest_proposal"]), tools, keyed, len(register), emergent_ok,
```

with:

```python
""" % (n_corpus, feed_accepted, len(rr["runs"]), len(rr["with_tool"]), RESOLVER, len(rr["no_record"]),
       len(rr["resolved"]), prompt, keyed, len(register), emergent_ok,
```

If `LEGACY_QUEUE` is now unused in the builder, drop it from its import. Run `grep -n "RESOLVER_ADDED\|newest_proposal\|resolver_available\|KC_TOOLS" tools/build_walkthrough.py`. Expected: no output.

- [ ] **Step 4: Rebuild and verify**

```bash
.venv/bin/python tools/build_walkthrough.py
.venv/bin/python tools/build_walkthrough.py --check
.venv/bin/python evals/check_walkthrough.py
for m in resolver-runs resolver-prompt feed-accepted corpus-count emergent-undecided; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_walkthrough.py --mutate $m | tail -1; done
grep -o 'data-count="\(feed-accepted\|extraction-runs\|runs-with-resolver\|runs-no-tool-record\|runs-resolved\)">[0-9]*' site/threat-intel/index.html
```

Expected:
- `--check` passes;
- the guard ends `HELD (0 failures)`;
- all five mutations are detected.

The grep shows (measured 2026-09-26: two committed queues, only `…69eeab7b41` has telemetry, and neither has a tools list):

```
data-count="feed-accepted">0
data-count="extraction-runs">2
data-count="runs-with-resolver">0
data-count="runs-no-tool-record">2
data-count="runs-resolved">0
```

READ the rebuilt section 10 in a browser or as text. Each of its sentences must be true, and a count check does not see prose.

Then run the cold suite: `.venv/bin/python tools/check_all.py --cold`.
- Expected: everything passes EXCEPT `check_published_walkthrough --cold`.
- That one refuses because `site/PUBLISHED` still names the old page. This is the republish obligation, not a defect.

- [ ] **Step 5: Prove the tripwire is gone**

This proves a new extraction's queue file is now counted, not refused. Plant one, count, then remove it:

```bash
printf '%s\n' '{"proposed_at": "2026-10-02T09:00:00Z"}' > data/proposals/feeds-probe-extractor-000000.jsonl
.venv/bin/python -c "import sys; sys.path[:0] = ['.', 'tools']; import build_walkthrough as bw; r = bw._resolver_runs(); print(len(r['runs']), len(r['no_record']))"
rm data/proposals/feeds-probe-extractor-000000.jsonl
git status --short data/proposals
grep -n "on or after the resolver" tools/build_walkthrough.py
```

Expected:
- the count prints `3 3`: the planted run is counted, as a run with no tool record;
- `git status` shows nothing after the `rm`;
- the final grep prints nothing: the refusal text is gone.

Before this task, the same planted file (dated 2026-10-02, after 2026-09-25) made the builder raise "a committed proposal is dated … on or after the resolver's …". That refusal failed `build_walkthrough --check` inside `check_all` and so blocked every commit.

- [ ] **Step 6: Reword the tripwire note in CLAUDE.md**

In `CLAUDE.md`, replace the sentence that begins `**A tripwire in the same obligation:**` and ends `in the same commit as that run.` with:

```
**The resolver tripwire is defused (slice 2 A):** section 10's resolver sentence is COUNTED from the committed queues and their telemetry -- runs with a queue file, runs whose `RUN_STARTED` lists the resolver (`telemetry.run_started` records `tools` since slice 2), runs with no tool list, runs whose resolver call answered "Resolved:" -- so a new extraction's queue file no longer makes the builder refuse. It still changes the page, and therefore still carries the republish obligation above in the same commit as that run.
```

- [ ] **Step 7: STOP — the owner's go, then republish**

Report to the controller:
- the rebuilt section 10 text;
- the counts above;
- that the commit is blocked until a republish.

The controller asks the owner. **Do not run `tools/publish_walkthrough.py` without that go.** On the go, run CLAUDE.md's "The publish procedure" block exactly:
- fetch the portfolio and check `main` against `origin/main` first;
- steps 1-5 publish and commit IN THE PORTFOLIO;
- then this repository's commit is step 6, staging everything from this task together.

```bash
git add agents/telemetry.py agents/extract_advisory.py agents/review_advisory.py evals/check_telemetry.py tools/build_walkthrough.py evals/check_walkthrough.py site/threat-intel/index.html site/PUBLISHED CLAUDE.md
git commit -m "Slice 2 A: section 10 counts resolver runs and accepted feed items; the tripwire is defused"
```

The hook runs the full `check_all`, including the warm staleness gate against the portfolio's committed copy. Expected: every guard passes. Push neither repository until the owner asks (procedure step 7).

---

## Definition of done for sub-project A

Each item below is traced to the task that delivers it, against the spec's definition of done.

- DoD 1 (in part) — Task 3. Three adapters with cold snapshot guards and loud "layout changed" failures.
- DoD 2 (for the two tools A builds) — Tasks 2 and 4. The `feeds` server enforces:
  - newness through the ledger;
  - the domain allowlist;
  - pinning;
  - inbox-only writes.
- DoD 5 (its skeleton) — Task 2. `accept_run` is the only writer of the ledger.
- DoD 8 — Task 5. The walkthrough still builds and is current, with the resolver sentence computed.
- Four new cold guards in `check_all`, each mutation-verified, 24 mutations in all.
