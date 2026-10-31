# Wolfsberg swept, FATF by hand (design)

Date: 2026-10-31. The owner asked for FATF, the Wolfsberg Group and Geopolitical Monitor (the site) as advisory
sources. Measured the same day with a plain fetch, no JavaScript, and taken on the owner's go:

- **Wolfsberg Group** joins the weekly sweep as the tenth live source.
- **FATF** gets an on-demand intake for a document the owner downloads in their own browser. Nothing in fc-08 fetches
  fatf-gafi.org.
- **Geopolitical Monitor** is not added.

## What each source publishes (measured 2026-10-31)

| Source | Listing | Item page | Document | Verdict |
|---|---|---|---|---|
| FATF | every URL tried (`/en/rss.html`, `/en/publications.html`, `…/publications.rss.xml`) answers 403 with Cloudflare's "Just a moment…" check | same | same | not sweepable; a bot check is not something fc-08 gets past |
| Wolfsberg | `https://wolfsberg-group.org/news`, server-rendered HTML (Nuxt), 10 items, ISO date beside each, newest 2026-07-15 | `/news/<slug>`, 200, ~2,700 characters of text without JavaScript, date at the top | the item page links ONE `/resources/<area>/<n>` page on the same host; that page links the PDF on `db.wolfsberg-group.org/assets/…`, served as `application/pdf` | sweepable |
| Geopolitical Monitor | `https://www.geopoliticalmonitor.com/feed/`, RSS, 10 items, RFC 822 dates, 1-2 posts a day | 403, Cloudflare "Attention Required!" | none | not sweepable, and not an advisory: the feed carries a ~200-character teaser and no `content:encoded`; triage must quote the page; the site publishes commentary, not an authority's notice |

Wolfsberg's volume is low: the ten listed items span 2025-08-27 to 2026-07-15, and about half are governance news
(appointments, an anniversary, a forum). A weekly listing fetch costs nothing when nothing is new.

`SourceType` already has `FATF` and `WOLFSBERG` (`schemas/advisory.py:46-61`), so **the schema does not change**.

## 1. Wolfsberg, swept

- A `Source` entry `wolfsberg` in `feeds/sources.py`: listing `https://wolfsberg-group.org/news`, `text/html`;
  `hosts = {"wolfsberg-group.org"}`; `document_hosts = {"db.wolfsberg-group.org"}`.
- `parse_wolfsberg(raw)` reads the rendered HTML (the measured shape), not the Nuxt data payload. Each item is a
  `/news/<slug>` link with its adjacent ISO date: `item_id` is the slug, `published` the date. An item without a
  readable date is refused as a parse error naming the item, as in every other parser. HTML listing parsers already
  exist (`parse_fincen`, `parse_ofac`); this is a third, not a new kind.
- **The document is one hop further than any source today.** `feeds/extraction.py` takes "a pinned HTML page linking
  exactly ONE PDF on its source's `document_hosts`" as the document. Wolfsberg's item page links a resource page,
  not the PDF. So `Source` gains an optional `document_via` path prefix (`"/resources/"` for Wolfsberg):
  - If the item page links no PDF on `document_hosts` but exactly ONE page on the source's own `hosts` under that
    prefix, extraction fetches that page and applies the existing exactly-one-PDF rule to it.
  - Every hop goes through `feeds/http.get` with its host allow-list and is pinned by sha256, as the item page is today.
  - Two candidate resource links is a refusal, never a choice. With no declaration, behaviour is exactly today's, so
    the nine existing sources are untouched.
- Triage rule draft for `feeds/triage_rules.json`, for the owner to edit: **keep guidance, statements, principles
  and FAQs on financial crime controls or typologies, and notes on a specific crime (HTWORLDCUP is the example);
  drop governance news: appointments, anniversaries, membership and forum announcements.**
- Baseline: the ten currently listed items are marked seen with `accept_run.py --baseline wolfsberg --on <date>` on
  the day this lands, before the next Friday run (R8's mechanism, unchanged).

## 2. FATF, by hand

### The existing script is retired

`tools/fetch_fatf_via_chrome.js` (2026-09-10) fetched the six FATF PDFs in the golden set. It does it by launching
Chrome with `--disable-blink-features=AutomationControlled`, hiding `navigator.webdriver` and presenting a normal user
agent: it disguises automation to pass FATF's bot check. That is getting past bot detection, and fc-08 should not
carry it. This package deletes it, and amends the three `CLAUDE.md` lines that point at it (15, 28, the week-3
entry) to name the intake below.

The PDFs it fetched stay where they are (`data/advisories/`, gitignored) and the golden set's hashes still match
them. Retiring the tool removes no evidence.

### The intake

The owner downloads the document from fatf-gafi.org in their own browser, then runs:

```
python tools/intake_document.py --source fatf --file <downloaded.pdf> \
    --url <the document's https://www.fatf-gafi.org/… address> --title "<title>" --published YYYY-MM-DD
```

- `feeds/sources.py` gains `MANUAL_SOURCES`, declaring `fatf` with `hosts = {"www.fatf-gafi.org"}`. A source may be
  live or manual, never both.
- The tool **fetches nothing**. `--url` is provenance: it must be https on a declared host, and it is recorded, not
  requested.
- The file must begin `%PDF-` and be within `feeds/http.py`'s size cap. Its sha256 is the pin.
- `item_id` is the URL's path, so a later re-download of the same document is the same item, and the ledger's
  existing duplicate rule refuses it twice.
- It writes a run in the Friday run's shape (`inbox/manual-<date>-<hash>/`: `items.json`, `run.json`, `report.md`).
  It has one source (`fatf`, status `manual`, listing fields null) and one item. The item's `document` records the
  path, sha256, bytes, `application/pdf`, the URL as `final_url`, and `delivered_by: "owner"`.
- **No triage agent runs.** Triage answers "is this worth extracting?", and the owner has answered it by choosing the
  document; the item records `triage: owner-selected`. Extraction runs on it through the same step the Friday run
  uses, under the same per-item US$1 cap (`run.json` ceiling 1.00). Every claim must still quote the pinned PDF,
  checked by the existing citation matcher.
- The owner then accepts or drops it with the unchanged `tools/accept_run.py`, which writes the ledger, copies the
  document to `data/advisories/<adv-id>-fatf.pdf` and the run to `data/feeds/runs/`. The ledger keeps its single
  writer.

## 3. Geopolitical Monitor, not added

The measurements above settle it: the articles are behind Cloudflare, the feed holds only teasers, and nothing on the
site is an authority's notice. It is not added to `SourceType` (it would be `PRESS`, which the scan page already
treats as not a feed), so nothing appears on the scan page. A context-only lane showing headlines without producing
advisories was offered and not taken.

## 4. Scan page

Wolfsberg moves from "not yet scanned" to live (ten live). FATF stays under "read by hand because its site blocks
automated fetching", now derived from `MANUAL_SOURCES` instead of from the script's existence
(`tools/build_scan_demo.py:363`). Europol keeps its reason. Rebuild, republish on the owner's go, and commit after the
portfolio (R1: the hook's publish gates read the working tree).

## Guards (each mutation-verified)

- **Wolfsberg adapter:** a recorded copy of `/news` (fetched 2026-10-31, committed with the other adapter fixtures)
  parses into the expected ten items and dates. Mutations: an item with no date; an item linking off `hosts`.
- **Document hop:** recorded item and resource pages. Mutations:
  - two resource links on the item page (must refuse);
  - a resource page whose PDF is off `document_hosts`;
  - a resource link to another host;
  - `document_via` declared on a source whose item page already links its PDF (the hop must not run).
- **Intake:** mutations:
  - a file that is not a PDF;
  - `--url` on an undeclared host, or http;
  - the same document twice (refused by the ledger);
  - a source declared both live and manual;
  - a manual run that names a triage verdict other than `owner-selected`.
- **No disguised automation:** a guard fails if any tracked file contains `AutomationControlled` or overrides
  `navigator.webdriver`. Mutation: plant either string in a tracked tool. This keeps the retirement from being undone
  quietly.
- **Rules:** the existing every-live-source guard requires the `wolfsberg` entry in `triage_rules.json`; no new
  guard.

## Order and landing

Lands after PR #2 (scan page three paths) and PR #3 (six regulators), stacked on #3.

It is deliberately **not** squeezed in before Thursday 2026-11-05. That baseline covers the six regulators and should
stay as small as planned. Wolfsberg gets its own baseline on its landing day.

Steps:
1. Wolfsberg source and parser.
2. Document hop.
3. Manual intake and `MANUAL_SOURCES`.
4. Retire the script, add the no-disguised-automation guard, amend `CLAUDE.md`.
5. Scan page rebuild and republish.

## Out of scope

Any automated fetch of fatf-gafi.org; Geopolitical Monitor and any context-only lane; Europol (needs a rendered
fetch); extraction or review changes beyond the document hop; the walkthrough.
