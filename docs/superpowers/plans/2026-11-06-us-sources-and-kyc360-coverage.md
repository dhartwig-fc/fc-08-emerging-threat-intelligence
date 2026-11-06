# FBI and IC3 as sources, a 200-challenge check, and the KYC360 coverage check: plan

> For agentic workers: implement task by task (superpowers:subagent-driven-development). Each task ends green on the
> guards it touches; the controller runs `tools/check_all.py` and commits.

**Spec:** `docs/superpowers/specs/2026-11-06-us-sources-and-kyc360-coverage-design.md`, approved by the owner on 2026-11-06
("Spec approved, O4 on the fix branch: write the plan"). O1, O2, O3 and O5 as the spec recommends; O4 lands the
200-challenge detection on `sdd/size-check-unreachable`.

**Goal:** sweep the FBI's IC3 announcements and the FBI's national press releases (which carry DOJ's national cases),
never pin a bot-check page as a document, and give the Friday Brief a weekly KYC360 coverage check.

## Measured since the spec (2026-11-06, fc-08's own client, no retries)

These replace the spec's "not yet confirmed" lines and settle plan step 1.

| | Measured |
| --- | --- |
| `fbi-in-the-news` entries | 300 entries, 19 Oct to 5 Nov; each URL is in `<guid>`, and there is **no `<link>`** |
| Entry paths | 285 `/contact-us/field-offices/...`, 11 `/news/press-releases/...`, 4 `/investigate/cyber/...` |
| A `/news/press-releases/` entry | redirects to `www.justice.gov/opa/pr/...` (DOJ Office of Public Affairs): 200, nginx, 94 KB, a real page |
| A `/contact-us/field-offices/` entry | redirects to `www.justice.gov/usao-*/pr/...`: 200, AkamaiGHost, 2.5 KB, the `bm-verify` challenge |
| DOJ national-only feed | none found: `component=` and `office=` parameters return the same 25-item feed |
| Volume kept by the R2 filter | 15 entries in 18 days, about 6 a week |

So R2 becomes: the `fbi` source keeps only `/news/press-releases/` and `/investigate/` entries, and its hosts are
`www.fbi.gov` and `www.justice.gov`, because redirects are checked against `Source.hosts` (`feeds/http.py` `_Redirects`)
and a redirect off-list is refused. DOJ's national releases arrive this way. The R4 check stops a district page that
slips through from being pinned. R3 still holds: there is no separate DOJ source.

## Order of landing

1. **Task 1 on `sdd/size-check-unreachable`** (O4), so that branch's unreachable logic is complete before it merges.
2. That branch lands. This branch is rebased onto the new `main`.
3. **Tasks 2-5 on `sdd/us-sources-coverage-check`.** `fbi` depends on Task 1, because `www.justice.gov` is one of its
   hosts.
4. This branch lands, then R5 (the owner's baseline) runs before the first Friday that reads the new sources.

Task 6 is the Friday Brief procedure and needs no fc-08 code.

## Task 1: a 200 that is a challenge page is a bot check (R4), on `sdd/size-check-unreachable`

**Files:** `feeds/http.py`; `evals/check_feeds_server.py` (the guard that owns `_is_bot_check`).

- After the 200 body is read in `get` (the `body = resp.read(max_bytes + 1)` line, about :72 on that branch), and only
  for `text/html`: if `_is_challenge_page(headers, body[:BODY_PEEK_BYTES])` holds, raise `BotCheck("%s answered a bot
  check (HTTP 200 challenge page) ..." % url)`.
- `_is_challenge_page` holds on either of:
  - an Akamai Bot Manager challenge: a `meta http-equiv="refresh"` whose URL carries `bm-verify=`;
  - a Cloudflare challenge: `cf-mitigated: challenge`, or `Server` containing "cloudflare" with a `BOT_CHECK_TITLE`
    title.

  Reuse `BOT_CHECK_TITLE` and `BODY_PEEK_BYTES`. Detection only, as before: no retry, no change to headers.
- The final-URL host check (`_check_host(final, ...)`) still runs first, so a redirect off-list is refused, never
  classified.
- Guards, each a new clause with a mutation:
  - the measured Akamai body (a 2.5 KB stub with the `bm-verify` refresh and the `&nbsp;` title) is a BotCheck;
  - a real 94 KB press-release page, stubbed by a body with an article, a `<title>` and no refresh, is NOT;
  - a page with an ordinary `meta refresh` and no `bm-verify` is NOT;
  - `_fetch` marks the item unreachable through the existing path (no new code there, one assertion).

  Mutations to verify:
  - `challenge-200-ignored`: the check is removed;
  - `challenge-any-refresh`: it matches any refresh;
  - `challenge-before-host-check`: it runs before `_check_host`.
- Controller: run `tools/check_all.py` (53 run, 0 failed), commit "Bot check: a 200 challenge page is a bot check too
  (R4) ...", and hand the owner the push. The PR for this branch gains the commit.

## Task 2: the source list and schema (`ic3`, `fbi`)

**Files:**
- `feeds/sources.py`: two `Source(...)` entries, appended to `ORDER` (append-only);
- `schemas/advisory.py`: the `SourceType` members `ic3` and `fbi`, and a `SCHEMA_VERSION` bump;
- the key patterns read by `mcp_server/feeds_server.py`, wherever `KEY_PATTERN`/`SOURCE_PATTERN` derive from.

Follow `docs/superpowers/plans/2026-10-31-six-more-regulators.md` Task 1-2 exactly.

| | `ic3` | `fbi` |
| --- | --- | --- |
| listing_url | `https://www.ic3.gov/PSA/RSS` | `https://www.fbi.gov/feeds/fbi-in-the-news/rss.xml` |
| listing_ext / types | `rss` / `application/rss+xml` | `rss` / `application/atom+xml` (as measured; the body is RSS 2.0) |
| hosts | `www.ic3.gov` | `www.fbi.gov`, `www.justice.gov` |
| parse | the shared `_rss(...)` | `_rss_guid_filtered(...)`, Task 3 |

## Task 3: the FBI parser

**Files:** `feeds/sources.py`.

- `_parse_rss` gains `url_from_guid: bool = False`. When it is set and `<link>` is empty, the item's URL is its
  `<guid>`. **Every existing source keeps the current behaviour** ("an item lacks its link" still raises for them),
  because the default is False.
- `_parse_rss` also gains `keep: Callable[[str], bool] | None`. When it is set, items whose URL path fails `keep` are
  skipped. They are not new and are never listed.

  For `fbi`, `keep = lambda path: path.startswith(("/news/press-releases/", "/investigate/"))`, a named module
  constant, not a lambda in the entry.
- A layout change still raises `LayoutChanged`. An FBI feed in which every item fails `keep` is not a layout change:
  that would be a quiet week. But an item with neither `<link>` nor `<guid>` is a layout change.

## Task 4: rules, publishers, scan page and fixtures

**Files:**
- `feeds/triage_rules.json`: one line per source. ic3: "a public service announcement describing a fraud, scam,
  cyber-enabled financial crime or sanctions method". fbi: "a press release describing a financial-crime case
  (fraud, money laundering, sanctions or export evasion, corruption, cyber-enabled theft); drop violent crime,
  exploitation and personnel news".
- `tools/accept_run.py` `PUBLISHERS`: "FBI Internet Crime Complaint Center (IC3)" and "Federal Bureau of
  Investigation".
- `tools/build_scan_demo.py` `DISPLAY`.
- `tests/fixtures/feeds/ic3.rss` and `fbi.rss`: NEW files recorded once from the live feeds (a fixture is never
  edited).
- `evals/check_feed_adapters.py`: SNAPSHOTS (sha pins), EXPECTED (count, ids digest, first and last items: for `fbi`,
  the count after the `keep` filter), NEW_HOSTS, and one BREAKS mutation per parser. Add `fbi-drops-guid-fallback`,
  `fbi-keeps-field-offices` and `guid-fallback-for-all` (the fallback leaking to other sources); each must turn the
  guard red.

**The scan page** is a published artefact. `build_scan_demo --check` will fail once `DISPLAY` changes, so rebuild the
committed page in this task. **Publishing it waits for the owner's go**, as always.

## Task 5: dry run and cost

**Files:** none changed.

- `python tools/count_new.py ic3 fbi`: the dry run that lists without triage. Record the counts in the PR.
- Compare: 29 items cost the 2026-11-06 orchestrator US$0.37, and the new sources add about 6 + 1 a week.
- If the first live count is far above that, stop and report before landing.

## Task 6: the KYC360 coverage check (R7, O5), no fc-08 code

**Files:** none in fc-08. The Friday Brief procedure (Claude's memory file `friday-brief.md`) gains the step.

Each Friday Brief gains a section, "Coverage check: KYC360 roundup":

1. Fetch `https://kyc360.com/knowledge-hub/resources/rss.xml` and take that week's "AML Roundup" item.
2. Read its page.
3. List its stories, paraphrased, linking to the roundup.
4. Classify each story: caught (ADV id), missed: source not swept, missed: swept but dropped or unread, or out of scope.
5. Name any publisher missed two weeks running as a source proposal.

Nothing of KYC360's enters fc-08. The brief is a private document. If the roundup is not out yet, the brief checks the
previous week's and says so.

The first use is the 2026-11-06 brief (`TtKNGGx3xdJQ2VaDtW1wzV`), which gains the section now. That roundup's
classification is already in the spec.

## After landing (owner)

- **R5:** `accept_run.py --baseline ic3 fbi --on <the day before the next Friday>` in `~/fc-08-schedule`, then commit
  `seen.json`.
- Republish the scan page.
