# Slice 2 design: live intelligence

Date: 2026-09-26. Status: approved section by section in chat; awaiting owner review of this
written form before the first sub-project's plan.

Slice 1 (`fc08-threatintel-slice1-v1.0.0`) extracts a governed record from a fixed corpus of 20
advisories, with a human review gate as the only write path. Its stated investigator outcome was
"live doctrine: the Knowledge Centre stops being the static half and starts being refreshed by the
world". The release did not reach it: nothing ingests new publications, and nothing flows into
detection. Slice 2 makes the intelligence live, weekly, without weakening the gate.

It is a six-week plan at about 10 hours a week, split into four sub-projects, each with its own
plan.

## What was measured, 2026-09-26

| Item | Measured | Consequence |
|---|---|---|
| Corpus publishers | Of the 20 advisories: FATF 8, FinCEN 3, NCA 3, OFAC 2, OFSI 1, FCA 1, Europol 1, Wolfsberg 1 | The corpus is FATF-weighted |
| OFSI | GOV.UK Atom feed for the Office of Financial Sanctions Implementation returns 200, `application/atom+xml` | A real feed with stable ids and dates |
| FinCEN | Advisories listing returns 200 (HTML); `/rss.xml` returns 404 | A listing to parse, not a feed |
| OFAC | Recent-actions listing returns 200 (HTML) | A listing to parse; most items are designation notices, not advisories |
| NCA | Publications listing returns 200 (HTML) | Reachable; not selected for slice 2 |
| FATF | Publications listing returns 403 to plain HTTP | Needs the browser path used for slice 1's downloads; stays manual |
| Formats | FinCEN advisories are PDFs; OFAC actions and most OFSI notices are HTML | Citations need pages for HTML documents |
| Auth | The Agent SDK drives the `claude` CLI, whose OAuth is separate from the desktop app and has expired before | An unattended run needs the long-lived subscription token and a loud preflight |
| Walkthrough | The published page's section 10 says no committed extraction had the resolver; the builder refuses once a queue holds a proposal dated on or after 2026-09-25 | The first accepted live run would block every commit unless this is changed first |

## Decisions taken in the design conversation

1. Slice 2's theme is **live intelligence**. Trustworthy measurement and FC10 integration are the
   slice 3 queue.
2. Feeds bring in **advisory publications only**, not designation lists.
3. Sources automated: **OFSI (Atom), FinCEN (listing), OFAC (listing)**. FATF stays a manual drop-in.
4. A scheduled run goes as far as **detect, triage, extract into an inbox**. Nothing is committed
   automatically. The owner accepts runs.
5. The schedule is **launchd on the owner's Mac, weekly on Fridays**.
6. Triage is measured by a **labelled back-catalogue**, Claude-drafted, with the owner deciding
   disagreements, and scored on recall first.
7. Orchestration is **one orchestrating agent** whose tools carry the invariants (option b of
   three). A plain Python runner with narrow agents (option a) was the alternative recommended in
   the conversation and not chosen.

## Build order

- **A. Foundations and sources** (weeks 1-2): Sections 3 and 5 (tripwire), the ledger, the
  `accept_run` skeleton, the `feeds` server's list and fetch tools.
- **B. Triage and its eval** (week 3): Section 4.
- **C. The orchestrator and the schedule** (weeks 4-5): Sections 1, 2 and 5.
- **D. Operation and release** (week 6): Section 6.

---

## Section 1: architecture

One Friday run is one orchestrator agent session, started by a thin launcher from launchd. The
launcher sets the run identity, the budget and the output folder, then starts the agent.

The agent's tools come from a new MCP server, `feeds`, alongside the existing Knowledge Centre
server. Each tool enforces one invariant, whatever the agent intends:

| Tool | What the agent can do | What the tool enforces |
|---|---|---|
| `feeds_list_new(source)` | see candidate items from OFSI, FinCEN or OFAC | "new" is decided by the committed seen-items ledger; the agent cannot declare an item new or old; only the three allowlisted sources exist |
| `feeds_fetch(item_id)` | download an item's document | only URLs from a listed item, on allowlisted domains; pins the sha256; size and type limits; writes only into this run's inbox |
| `feeds_triage(item_id, verdict, reason, quote)` | record a relevant / not-relevant decision | the quote must be found in the fetched document; one verdict per item; a "not relevant" is stored and reported, never deleted |
| `feeds_extract(item_id)` | extract a relevant item | refuses unless the item has a "relevant" verdict; runs slice 1's extraction on the pinned document with its own run identity, so the gate, `propose_link`, citations and telemetry are reused unchanged |
| Knowledge Centre tools | search, get, resolve actors | read-only, as in slice 1 |

At the end of the run, **in code, after the agent stops**, the runner reconciles:
- every listed item has exactly one triage verdict;
- every relevant item was extracted, or its failure is reported;
- every tool call has one telemetry event (`terminal_check`).

Whatever the agent skipped is reported as **unfinished**, never as success.

Budget and blast radius:
- **a hard cost ceiling of US$4 for the whole run** (owner decision, 2026-09-26). Measured: an
  extraction averages US$0.73 (14 runs), and the one telemetry run cost US$0.50. On the subscription
  token this is the SDK's notional price, not a bill, but it is capped all the same;
- **caps: at most 10 listed items triaged and at most 3 extracted per run**, each extraction with its
  own `max_budget_usd` of US$1.00. The runner starts an extraction only if the spend so far plus
  US$1.00 stays within US$4; otherwise the item is deferred. Deferred items stay unseen and come back
  next Friday, and the report lists them as deferred for budget;
- no write tools other than `feeds_*` into the inbox and `propose_link` into the run's queue;
- the seen-items ledger is updated only by `accept_run`.

## Section 2: the inbox, the Friday report, and accepting a run

Each run writes one gitignored folder, `inbox/<run_id>/`, and nothing else:
- `items.json`: every candidate listed, per source, with the raw listing snapshot the adapter parsed;
- `docs/<sha256>.<ext>`: each fetched document, pinned by hash;
- `triage.jsonl`: one verdict per item, with the reason and the verified quote;
- the extraction outputs for relevant items: records, the run's proposal queue files, and
  telemetry, in slice 1's shapes;
- `report.md`: the Friday report.

**The Friday report is written on every run**, including "nothing new" and "failed". It covers:
- new items per source;
- dropped items listed with their reasons;
- extractions and proposal counts;
- the reconciliation result, including unfinished items;
- cost against the US$4 ceiling, and any items deferred for budget;
- any failure stated loudly: auth expired, a source down, or a listing whose layout no longer parses.

launchd posts one macOS notification at the end of the run.

**Accepting a run is `tools/accept_run.py <run_id>`:**
1. It shows the report and takes a decision per item: **accept** or **drop**.
2. An accepted item gets a new advisory id in `evals/golden/advisory_list.json` (source, URL, hash,
   date). Its record, queue file and telemetry move into the tracked folders, and its document goes
   to the gitignored `data/advisories/`.
3. It validates everything first (schema, every citation against the pinned document, the queue
   contract) and refuses the whole acceptance on any failure.
4. Every listed item, accepted or dropped, is added to the seen-items ledger. A run not accepted
   leaves the ledger untouched, and its items return next Friday.
5. The owner commits. Proposals then go through `tools/review.py` as in slice 1.

## Section 3: documents, citations and the source adapters

**PDFs** go through slice 1's `PageIndex.from_pdf`, unchanged.

**HTML pages** are pinned as raw HTML, with the sha256 recorded. A new, deterministic
`PageIndex.from_html(raw)` handles them:
- it canonicalises the page, keeping the main content element and dropping navigation, headers and
  footers;
- it splits the text into numbered pages by a fixed rule, at paragraph boundaries around a fixed
  size.

The same raw HTML always gives the same pages, re-derivable from the pinned file by committed code.
The citation matcher, `propose_link`'s refusal, the review gate's re-check and `check_citations` all
work on those pages without changing their rules. Printing HTML to PDF with a headless browser was
rejected: the output depends on the browser version.

**The adapters** are ordinary code behind `feeds_list_new`:
- **OFSI** parses the GOV.UK Atom feed.
- **FinCEN** and **OFAC** parse the HTML listings (title, URL, date per item).

**Guards:**
- *Cold:* each adapter runs against committed snapshots of its listing (public government pages,
  under `tests/fixtures/feeds/`) and must extract the expected items.
- *Live:* each adapter checks a structural marker it depends on (the listing container, a date
  format). If the marker is missing, it raises **"layout changed"**, which the report shows as a
  loud failure. It never returns "0 new items".

**Politeness:** one fetch per listing per run, documents only for new items, a descriptive user
agent, and a delay between requests.

**Data:**
- Listing snapshots used in guards are tracked.
- Live listings stay in the inbox.
- Documents stay gitignored, pinned by hash.
- The ledger, `data/feeds/seen.json`, records source, item id, first-seen run and decision. It is
  tracked, and written only by `accept_run`.

## Section 4: triage, and how it is measured

Triage is the orchestrator's own judgement, recorded through `feeds_triage`:
- the verdict is **relevant** when the publication describes methods, red flags or cases of
  financial crime that a typology could hold;
- a bare designation list, a licence notice or a website change is **not relevant**;
- each verdict carries a reason (at most 300 characters) and one verbatim quote, verified against
  the document's pages;
- the prompt states the asymmetry: **when in doubt, keep it**.

**The back-catalogue eval, `evals/feeds/`:**
- **The set:** about 60 recent items, roughly 20 per source, fetched once. Documents are pinned and
  gitignored; the item list is tracked.
- **Labels:** Claude drafts relevant / not relevant with a reason. The orchestrator runs in a
  triage-only mode (list, fetch and triage tools only, no extraction) over the same items, three
  times. The owner decides only the items where the draft label and triage disagree, recorded as
  dated owner decisions.
- **The score:** recall of relevant items first, precision beside it, both as a band over the three
  repeats. The repeat records are committed, fixing the gap slice 1's journal named.
- **Guard (cold):** the scorer is mutation-verified, and the committed band must be reproducible
  from the committed repeats.

**Extraction on live items:** slice 1's extractor is reused, with one prompt change. It names
`resolve_actor` and asks the agent to resolve each named actor, exact matches only, with suggestions
labelled, as the tool enforces.
- The change is measured by the resolution rate on live runs, per run and summed over the slice.
- The slice 1 golden scores are not re-measured; re-scoring with the new prompt is a slice 3
  candidate.

## Section 5: operations — the schedule, auth, telemetry and the public walkthrough

**The schedule:**
- `scripts/schedule/uk.fc08.friday-run.plist` (tracked) runs `scripts/schedule/friday_run.sh` every
  **Friday at 09:00**.
- `tools/schedule.py install|uninstall|status` manages it. Nothing installs itself.
- The runner refuses to start if the checkout is not on `main`, if a previous run is still in the
  inbox unaccepted and less than 14 days old (older runs expire: `accept_run --expire` discards them
  without touching the ledger, so their items return), or if the auth preflight fails. Each refusal is written up as a run
  report with a notification.

**Auth:**
- The run uses the long-lived subscription token.
- A preflight checks the CLI's auth status before the agent starts, and fails loudly on expiry.
- The token is never written into the repo, the plist or a log.

**Telemetry:** every tool call in the orchestrator, and in each extraction it starts, gets one
terminal event. The runner calls `reconcile` at the end, so `terminal_check` runs live. A run whose
reconciliation fails is marked unfinished and cannot be accepted without an explicit override.

**The walkthrough tripwire is defused in week 1:**
- Section 10's resolver sentence becomes computed ("N committed extraction runs; M had the resolver
  available; K resolved at least one actor"), derived from the committed queues and records.
- The builder's refusal is removed, and the guard checks the computed numbers.
- The page stays about ADV-2026-0013. If its inputs change, the staleness gate says so.

**The public site** is not part of the weekly loop. Nothing is published automatically.

## Section 6: the plan, the definition of done, and scope

**A. Foundations and sources (weeks 1-2)**
- *Week 1:*
  - defuse the walkthrough tripwire;
  - `PageIndex.from_html` with its determinism guard;
  - the seen-items ledger and the `accept_run` skeleton.
  - *Learn:* HTML canonicalisation and reproducible pagination.
- *Week 2:*
  - the three adapters, each with snapshot contract guards and layout markers;
  - the `feeds` MCP server's `list_new` and `fetch` tools.
  - *Learn:* designing MCP tools that carry side effects and invariants.

**B. Triage and its eval (week 3)**
- The back-catalogue, `feeds_triage`, the triage-only mode, three repeats, owner decisions on
  disagreements, and a committed band.
- *Learn:* evaluating a classifier with asymmetric costs.

**C. The orchestrator and the schedule (weeks 4-5)**
- *Week 4:*
  - `feeds_extract` with `resolve_actor` in the extractor prompt;
  - the orchestrator agent, with budgets, item caps and reconciliation;
  - the Friday report; manual dry runs.
  - *Learn:* Agent SDK orchestration, hooks, budgets.
- *Week 5:*
  - `accept_run` end to end;
  - launchd install and uninstall, auth preflight, notification, back-pressure;
  - the first real Friday run and the first accepted run.

**D. Operation and release (week 6)**
- Two more Fridays of operation.
- A measurement note: the triage band, the live resolution rate, cost per run, items per source.
- A release audit; tag `fc08-threatintel-slice2-v1.0.0`; a journal entry.
- Any portfolio update only on the owner's go.

**Definition of done:**
1. Three source adapters with cold snapshot guards and loud "layout changed" failures.
2. A `feeds` MCP server whose tools enforce newness through the ledger, the domain allowlist,
   pinning, inbox-only writes, and extraction only after a relevant verdict.
3. A committed triage eval with a recall and precision band over three committed repeats, with the
   owner's decisions recorded.
4. An orchestrator run that reconciles every listed item and every tool call; `terminal_check` has
   run live at least three times.
5. `accept_run` as the only way live results enter tracked data, validating everything, and updating
   the ledger only on acceptance.
6. launchd running weekly on Fridays, with an auth preflight, a notification, back-pressure, and no
   run exceeding US$4.
7. At least one accepted live run whose proposals went through `tools/review.py`.
8. The walkthrough still building and current, with the resolver sentence computed.

**Out of scope (the slice 3 queue):**
- designation-list feeds;
- FATF automation;
- embedding-based search;
- `entity_key` linking and the Knowledge Centre overlay;
- re-scoring the golden set with the new extractor, and growing it to 50;
- OCR;
- cloud scheduling;
- automatic publishing.
