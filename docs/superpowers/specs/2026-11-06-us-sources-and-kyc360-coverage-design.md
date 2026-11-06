# FBI and DOJ as sources, and a KYC360 coverage check: design

Status: draft for owner review, 2026-11-06. Branch `sdd/us-sources-coverage-check`, cut from origin/main 696217e.
Owner ask, 2026-11-06: "go, spec FBI and DOJ plus the KYC360 check".

## Why

The KYC360 Weekly Roundup of 6 November 2026 headlined seven stories. The same day's sweep (`feeds-2026-11-06-389ebb`)
caught one of them, the OFAC Iran shadow-fleet action (kept, not extracted: ADV-2026-0036). The others came from
publishers fc-08 does not read, or reads only by hand:

| Roundup story (paraphrased) | Primary publisher | In fc-08 today |
| --- | --- | --- |
| FBI attributes a US$6bn Binance theft to North Korea | FBI | not a source |
| Block's proposed three-year deferred prosecution agreement | US Department of Justice | not a source |
| A Venezuelan national sentenced in a laundering case over US$1bn | US Department of Justice | not a source |
| FATF principles for disrupting scam-compound proceeds | FATF | manual intake only (bot check) |
| A network shielding fraudulent call centres in Ukraine | NABU (Ukraine) | not a source |
| FCA quantum machine learning experiment | FCA | swept, dropped by triage (no method) |
| US action against Iran's shadow fleet, aviation and arms networks | OFAC | swept, kept (ADV-2026-0036) |

Two of the missed stories bear directly on Fault Lines: the FBI's DPRK attribution (Issue #2, DPRK IT workers) and
FATF's scam-compound principles (Issue #3, Prince Group).

## Measured 2026-11-06

All probes used fc-08's own client and user agent (`feeds/http.USER_AGENT`), a handful of requests each, no retries.

| Feed or page | Answer | What it holds |
| --- | --- | --- |
| `justice.gov/news/rss?type=press_release` | 200 RSS, nginx | the newest 25 items only, all from 5 Nov: every US Attorney's office, mostly unrelated to financial crime; descriptions ~146 characters |
| a `justice.gov/usao-*/pr/*` article | **200**, AkamaiGHost, 2.5 KB | an Akamai Bot Manager challenge: `meta refresh` to `?bm-verify=...` and a script, title `&nbsp;` |
| `fbi.gov/feeds/national-press-releases/rss.xml` | 200, Cloudflare | 300 entries, newest **20 Oct**: stale for 17 days |
| `fbi.gov/feeds/fbi-in-the-news/rss.xml` | 200, Cloudflare | 300 entries, newest 3 Nov; titles are case press releases (DOJ-style) |
| `ic3.gov/PSA/RSS` (FBI's Internet Crime Complaint Center) | 200 RSS | 5 public service announcements, newest 23 Oct; an announcement page opened (6.8 KB, no challenge) |
| `kyc360.com/knowledge-hub/resources/rss.xml` | 200 RSS, Cloudflare | 10 items: the Friday "AML Roundup" plus KYC360 marketing posts (law-firm guides, webinars) |
| `kyc360.com/robots.txt` | 200 | allows the Knowledge Hub; disallows only login, preview and private event paths |
| `kyc360.com/website-terms-of-use` | 200 | KYC360 owns or licenses all site content; using the site grants no rights in it |
| `nabu.gov.ua/en/news/` | **403** | not reachable |

Not yet confirmed (the probe's parser did not read them): the FBI feeds' entry links, and whether those pages open.

## Decisions proposed

**R1. Add the FBI's IC3 announcements as a live source, `ic3`.** RSS, host `www.ic3.gov`, pages readable. Low volume
(5 in the feed), squarely in scope: fraud, scams, cyber-enabled financial crime and, historically, DPRK IT workers.

**R2. Add FBI press releases as a live source, `fbi`, from `fbi-in-the-news`, subject to plan step 1.** That feed is
current (newest 3 Nov); the national press-release feed is stale and is not used. Plan step 1 must confirm the
entries' links resolve to `fbi.gov` pages that open without a challenge. If they do not, R2 falls and only R1 lands.

**R3. Do not add DOJ as a live source now.** Two measured reasons, either sufficient:

1. Its article pages answer an Akamai Bot Manager challenge, and fc-08 does not get past bot checks.
2. Its feed carries only the newest 25 releases across every US Attorney's office, about one day's worth. A weekly
   sweep would see one day in seven.

DOJ matters that the FBI investigated reach fc-08 through R2 when the FBI publishes them. Reconsider DOJ if it offers a
topic feed (for example a Criminal Division or money-laundering feed) whose pages open; plan step 1 probes for one.

**R4. Close a gap in the bot-check detection that DOJ exposed.** `sdd/size-check-unreachable` (54cd53c) detects a bot
check only on HTTP 403, 429 or 503. Akamai answers **200** with a challenge page, which fc-08 would pin as if it were
the document: a page with no text and nothing to cite. A 200 whose body is a challenge page (Akamai `bm-verify` meta
refresh; Cloudflare challenge titles) becomes a `BotCheck` too, so the item is unreachable, not pinned. Detection only,
as before.

**R5. Baseline the new sources before their first Friday,** as the six regulators were:
`accept_run --baseline ic3 fbi --on <date>`, so the first sweep treats only newer items as new.

**R6. Watch the triage cost.** FBI press releases cover every crime type, so triage will drop most of them. The
2026-11-06 orchestrator spent US$0.37 triaging 29 items. Plan step 1 measures a week of `fbi` volume against that and
the US$10.00 run ceiling.

**R7. KYC360 is a coverage check in the Friday Brief, not a sweep source.** Its terms grant no rights in its content,
so nothing of KYC360's enters fc-08 records, the ledger or any published page. Each week, after the sweep is accepted
and reviewed, the brief's author:

1. reads the Knowledge Hub RSS and takes that week's "AML Roundup" item (published Fridays);
2. lists the stories it covers, paraphrased, with a link to the roundup page;
3. classifies each against the sweep: **caught** (its ADV id), **missed: source not swept** (name the publisher),
   **missed: swept but dropped or unread** (say why), or **out of scope**;
4. turns repeated "source not swept" misses into a source proposal for the owner.

The brief is a private Claude Doc. If the roundup is not out when the brief is written, the brief says so and checks
the previous week's.

**R8. No fc-08 code for KYC360 in v1.** The check is a procedure in the brief. A helper that lists the roundup's
headlines can follow if the manual step proves tedious; it would stay internal and out of every publish path.

## Out of scope

- **NABU (Ukraine):** HTTP 403.
- **FATF:** stays a manual intake. Its scam-compound principles are a candidate for the first real FATF intake (up to
  US$1). Note the new size check does not gate the manual intake.
- **Reading DOJ through any route that gets past its challenge.** It is excluded on principle.

## Questions for the owner

- **O1.** Add `ic3` (R1)?
- **O2.** Add `fbi` from `fbi-in-the-news` if plan step 1 confirms its links (R2)?
- **O3.** Agree DOJ stays out until a reachable topic feed exists (R3)?
- **O4.** Land the 200-challenge detection (R4) on `sdd/size-check-unreachable` before that branch merges, or on this
  branch?
- **O5.** Start the KYC360 coverage check (R7) from the next Friday Brief?
