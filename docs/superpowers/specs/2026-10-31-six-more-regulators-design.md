# Six more regulators in the weekly sweep (design)

Date: 2026-10-31. Owner decisions taken the same day:

- UK: add **OTSI, FCA, NCA** beside OFSI.
- EU: add **the EU Council, the EBA, AMLA**. Europol was chosen too and is deferred (below).
- Budget: the run's ceiling rises to **US$10** and its triage cap to **20 items**. Extraction stays at 3 a week.

After this the sweep reads 9 regulators: 2 US (FinCEN, OFAC), 4 UK (OFSI, OTSI, FCA, NCA), 3 EU (Council, EBA, AMLA).

## What each new source publishes (measured 2026-10-31, a plain fetch, no JavaScript)

| Source | Listing | Format | Items | Newest | Item and document host | Date field |
|---|---|---|---|---|---|---|
| OTSI | `https://www.gov.uk/government/organisations/office-of-trade-sanctions-implementation.atom` | Atom | 20 | 2026-10-27 | www.gov.uk, assets.publishing.service.gov.uk | `updated`, ISO 8601 (as OFSI) |
| FCA | `https://www.fca.org.uk/news/rss.xml` | RSS | 13+ | 2026-10-30 | www.fca.org.uk | `pubDate` like `Friday, October 30, 2026 - 09:00`, no timezone |
| NCA | `https://www.nationalcrimeagency.gov.uk/news?format=feed&type=rss` | RSS | 20 | 2026-10-28 | www.nationalcrimeagency.gov.uk | `pubDate`, RFC 822 |
| EU Council | `https://www.consilium.europa.eu/en/rss/pressreleases.ashx` | RSS (`text/xml`) | 20 | 2026-10-30 | www.consilium.europa.eu | no `pubDate`; `a10:updated`, ISO 8601. Sanctions items carry `<category>Sanctions</category>` |
| EBA | `https://www.eba.europa.eu/news-press/news/rss.xml` | RSS | 10 | 2026-10-29 | www.eba.europa.eu | `pubDate`, RFC 822 |
| AMLA | `https://www.amla.europa.eu/node/19/rss_en` | RSS | 30 | 2026-10-30 | www.amla.europa.eu | `pubDate`, RFC 822; items NOT in date order |

**Europol is deferred.** Its feed (`https://www.europol.europa.eu/rss.xml`, redirecting on the same host to
`/cms/api/rss/news`) lists 10 items but carries no date, and an article page is a JavaScript shell ("Loading
application") to a plain fetch. Triage reads the page and every accepted claim must quote it, so a page that cannot
be read cannot pass. Europol stays under "not yet scanned" on the scan page with that reason. A rendered fetch would
bring it back; it is not in scope.

## Design

### 1. One source list (first, before any new source)

`feeds/sources.py` `SOURCES` is the only declaration of live sources, but the list is copied by hand into
`mcp_server/feeds_server.py` (the `^(ofsi|fincen|ofac)` key pattern, five sites), `feeds/reconcile.py`
(`SOURCES = ("ofsi","fincen","ofac")`) and `agents/orchestrate_feeds.py` (three sites). Each copy is replaced by a
read of `SOURCES` (the key pattern built from its keys, sorted). A guard fails if any tracked module other than
`feeds/sources.py` names two or more source ids together as literals, so a copy cannot reappear. This step changes
no behaviour: the three sources fetch byte-identically before and after.

### 2. Sources and parsers

- OTSI is a gov.uk organisation feed: a `Source` entry reusing `parse_ofsi` (renamed `parse_govuk_atom`, with
  `parse_ofsi` kept as its alias only if a guard or test names it).
- One `parse_rss(xml, source)` serves FCA, NCA, Council, EBA and AMLA. It returns the same item shape the existing
  parsers return. Dates, in order of preference: `pubDate` (RFC 822, or FCA's `Weekday, Month D, YYYY - HH:MM`,
  read as Europe/London), then `a10:updated` / `atom:updated` (ISO 8601). An item with no readable date is REFUSED
  as a parse error naming the source and item, never silently dated today. Items are sorted by date (AMLA).
- Each `Source` declares its own `hosts` and `document_hosts` from the table above; the existing host and redirect
  guards in `feeds/http.py` apply unchanged.
- `schemas/advisory.py` `SourceType` gains `OTSI`, `EU_COUNCIL`, `EBA`, `AMLA` (FCA and NCA exist). This changes the
  advisory schema, so its version moves (minor); the extraction agent's schema and the scan page's displayed
  version follow.

### 3. Triage rules as per-source data

Today the one owner rule (OFAC designation pages, 2026-10-11) is a prompt constant appended for every source. It
becomes the first entry of `feeds/triage_rules.json`: `{source: rule text}`, owner-authored. The orchestrator
appends only the rules of the sources present in the batch, in source order. A guard requires an entry for every
live source; an entry may be the empty string, meaning "no source-specific rule", which must be written explicitly.

Drafts for the owner to edit before they are used (one line each):

- **OTSI:** keep notices and guidance that describe how trade sanctions are evaded or breached; drop licence
  notices and procedural updates.
- **FCA:** keep final notices, enforcement and fines that describe a control failure or a laundering or fraud
  method; drop consultations, speeches and corporate news.
- **NCA:** keep items that describe a laundering, fraud or sanctions-evasion method; an arrest or a sentence alone
  is not relevant.
- **EU Council:** keep items in the Sanctions category or that describe an evasion method; drop other policy news.
- **EBA:** keep AML/CFT guidelines, risk opinions and peer reviews; drop procedural, staffing and non-AML items.
- **AMLA:** keep risk assessments, guidance and supervisory findings; drop institutional and recruitment news.

The rules are guidance to the triage agent, not code; quotes are still required for every verdict.

### 4. Budget

The Friday run's ceiling becomes US$10.00 and its triage cap 20 (constants in `tools/friday_run.py`); extraction
stays at 3 items at US$1 each. The report and the run notice print the new limits.

### 5. Scan page and walkthrough

The scan page's coverage panel reads live sources from `SOURCES`, so it moves from 3 to 9 live with a rebuild;
`DISPLAY` gains the four new names; "not yet scanned" keeps Europol and Wolfsberg (and loses NCA and FCA). Europol's
entry shows the reason above. The walkthrough is pinned and does not change.

### 6. Dry run before the first live Friday

A listing-only run (feeds_list_new for every source, no agents, no spend) prints new items per source, so the owner
sees each source's weekly volume before the 2026-11-06 run spends anything. It writes nothing to `seen.json`.

## Guards (each mutation-verified)

- **Adapters:** each new source parses a RECORDED copy of its real feed (fetched 2026-10-31, committed under the
  existing adapter-fixture directory) into the expected items, dates and hosts. Mutations: a date in an unknown
  format, an item linking to an undeclared host, AMLA's items left unsorted.
- **One list:** the copy guard of §1. Mutation: a hand-written `("ofsi", "fincen", "ofac")` in a feeds module.
- **Rules:** every live source has a `triage_rules.json` entry. Mutation: delete one.
- **Budget:** the run's limits are US$10 and 20. Mutation: either constant reverted.
- **Existing guards** that name the three sources (`check_feeds_server`, `check_feeds_triage`, `check_feed_adapters`,
  `check_feeds_extract`, `check_feeds_runner`, `check_friday_run`, `check_document_pages`,
  `check_feeds_orchestrator`) are updated to iterate `SOURCES` where they mean "every source", and keep naming a
  specific source where they test that source's parser.

## Order and landing

1. §1 one source list (no behaviour change; all guards green).
2. §2-§3 sources, parser, rules (owner edits the six rule drafts before landing).
3. §4 budget, §5 scan page rebuild and republish (owner's go), §6 dry run.

Lands on fc-08 `main` after the scan-page branch it is stacked on, and before Thursday 2026-11-05, so the 06
November run reads all nine. The schedule clone fast-forwards after landing.

## Out of scope

Europol (needs a rendered fetch); ESMA; national EU supervisors; any change to extraction or review; the
walkthrough.
