# Slice 2 B: Triage and its Eval Implementation Plan

> **Approved by the owner on 2026-09-27: "accept all recommendations".** This plan was drafted overnight on 2026-09-26/27 and verified in a scratch copy of `slice2-a` at `a25b584` (see "Verification done for this draft"). `main` has since moved to `236595c` (the walkthrough snapshot). That change touches none of this plan's files except CLAUDE.md, which Task 10 appends to. Still re-check Task 1's edit anchors before running it.
>
> **Owner decisions recorded 2026-09-27:**
> 1. What triage reads: **(a)**, the document as A pins it (the landing page for FinCEN and OFSI, the action page for OFAC).
> 2. **Add `feeds_read_page`.**
> 3. The labelling rubric: **as drafted** (Spanish translations relevant; rescinded advisories labelled by content; penalty and settlement notices relevant; combined OFAC actions with an enforcement, settlement or advisory relevant; general licences, events, FAQ indexes and restated obligations not relevant; doubt means relevant).
> 4. The spot check: **the default, 6 items**, from those that the draft and all three repeats called not_relevant.
> 5. The pilot go (Task 7) and 6. the disputed labels (Task 9) remain **STOPs**, decided when reached.
> 7. **Accepted:** A's refusals are renamed from `Refused:` to `Rejected:`, so telemetry counts them as REFUSED.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Every STOP is a hard stop: report, and wait for the owner.**

## For the owner

### Decisions this plan needed from you (taken 2026-09-27; see the note at the top)

1. **What triage reads (before Task 1).** A pins the URL each listing gives. For FinCEN and OFSI that URL is a landing page and the publication is a linked PDF, which A records and does not fetch (A's ruling 2 left following it to C). Measured tonight: FinCEN FIN-2026-A002's landing page pages to one page of 291 characters (title, number, PDF name, date, subject line); OFSI's Citibank penalty notice to 981 characters (the notice itself is a 16-page PDF on `assets.publishing.service.gov.uk`, which is not on the allowlist); OFAC's recent action is four pages of real content.
   - **(a) Recommended: triage reads the page as A pins it.** Triage is a filter whose rule is "when in doubt, keep it", and a FinCEN subject line or an OFSI penalty summary is enough to keep. The cost stays small. The eval then measures exactly what production triage will see.
   - (b) Bring C's decision forward: fetch the linked PDFs in B, widen the allowlist to `assets.publishing.service.gov.uk`, and let quotes come from them. Better-informed verdicts, several times the reading per item, and a sub-project C decision taken early.
   - Either way, **if C later changes what triage reads, B's band describes a different input and the three repeats must be re-run** (about the cost in "Cost" below).
2. **A fifth tool, `feeds_read_page` (before Task 1).** The spec gives triage-only mode "the list, fetch and triage tools only". But A's `feeds_fetch` returns a file name, a size and a page count, never text, so with those three tools the agent cannot read what it is triaging, and cannot copy a quote. The plan adds `feeds_read_page(item_key, page)`: read-only, pre-approved, refused before a fetch, and serving the same pages the quote is checked against. The alternative is changing A's `feeds_fetch` to return the text, which puts a whole document into one tool reply.
3. **The labelling rubric (before Task 6, because it is frozen with the drafts).** The rubric is in `tools/write_feeds_labels.py` (Task 6). The points that move the score, each ruled in the draft rubric as shown, for you to confirm or overturn:
   - a Spanish translation of a relevant FinCEN advisory is **relevant** (three are in the set; whether to accept a duplicate is `accept_run`'s question, not triage's);
   - a rescinded advisory is labelled **by its content** (one is in the set: FIN-2020-A006, ransomware, rescinded 2021);
   - an OFSI or OFAC penalty, enforcement or settlement notice is **relevant** (a case);
   - an OFAC action that combines designations with an enforcement action, a settlement or an advisory is **relevant**;
   - general licences, webinar or event listings, an FAQ index page, and guidance that restates obligations are **not relevant**;
   - when the pinned text leaves it open: **relevant**.
4. **A spot check of agreed items (Task 9; the plan's default is 6).** You decide only disagreements, so an item where Claude's draft and all three repeats agree is never looked at. Both the labeller and the triage agent are Claude. The plan adds, by default, 6 items sampled by hash from those where all four said "not relevant". That is the only place an agreed error costs recall (a relevant publication everyone missed). Say 0 to skip it, or a different number.
5. **The go after the pilot session (Task 7 STOP).** One real session runs first. You see its cost, its turns, its verdicts and what it refused, and the runner's projection for all 18 sessions, before the other 17 run.
6. **The disputed labels (Task 9 STOP).** This is the spec's step: one decision per card, relevant or not relevant, with a note if you want one. It is recorded as a dated owner decision.
7. **A ruling you may veto: A's refusals become `Rejected:` (Task 1).** Measured: `agents/telemetry.classify_response` counts a reply as REFUSED only when it starts `Rejected:`. A's feeds server answers every refusal `Refused: …`, which telemetry records as SUCCESS, so a refused list or fetch reads as a success in the run's evidence. Task 1 renames the prefix in the server and in `evals/check_feeds_server.py` (six `startswith` checks). That is a change to code A shipped.

### Measurements taken for this draft

Six live requests, each through the repository's own `feeds/http.get` (its descriptive user agent and its enforced gap of at least 2 seconds), run from a scratch copy on **2026-09-26 between 22:47:22Z and 22:48:16Z (UTC)**:

| UTC | Request | Result |
|---|---|---|
| 22:47:22 | FinCEN advisories `?page=1` | 200, 50,115 bytes; **15 items**, none on page 0; 2020-10-15 back to 2019-07-12 |
| 22:47:31 | OFAC recent actions `?page=1` | 200, 45,242 bytes; **10 items**, none on page 0; 2026-09-03 back to 2026-08-12 |
| 22:47:43 | OFSI Atom `?page=2` | 200, 12,423 bytes; **the same 20 entries** as page 0: the feed does not paginate |
| 22:48:04 | FinCEN FIN-2026-A002 landing page | 200, 31,361 bytes; 1 page of 291 characters; links one PDF on `www.fincen.gov` |
| 22:48:13 | OFSI Citibank penalty landing page | 200, 68,151 bytes; 1 page of 981 characters; links one PDF on `assets.publishing.service.gov.uk` |
| 22:48:16 | OFAC recent action 20260910 | 200, 50,957 bytes; 4 pages of 2,721, 2,712, 2,480 and 2,656 characters; no PDF |

From the committed fixtures (no network): the listings parse to OFSI 20, FinCEN 15 and OFAC 10. FinCEN's pager links run `?page=0` to `?page=12`, and OFAC's `?page=0` to `?page=316`. The OFSI Atom has no `next` link. The committed OFSI FAQ page links its FAQs as an HTML page rather than a PDF, which `linked_pdfs` does not report.

**So 20 per source is reachable, exactly:**
- OFSI: all 20 the feed holds.
- FinCEN: page 0's 15 plus the first 5 of page 1 (FIN-2020-A008, A007, A006 which is rescinded, A005 in Spanish and A003 in Spanish). FinCEN's 20 span 2020-08-18 to 2026-06-05 and include three Spanish translations (one on page 0, two on page 1).
- OFAC: pages 0 and 1, 10 each.

Building the catalogue is 5 listing requests plus about 60 document requests, about 3 minutes at the 2-second gap (Task 3).

**Telemetry, measured:** `classify_response("Refused: ofsi was already listed in this run")` gives `('SUCCESS', …)`. `classify_response("Rejected: x")` gives `('REFUSED', …)`.

**Cost anchors (slice 1, measured, in CLAUDE.md):**
- extraction: 14 runs, mean US$0.73, 33.9 turns, 270 s;
- reviewer: 27 runs, mean US$0.48, 29.1 turns, 159 s.

### Verification done for this draft

Every code block below was run in a scratch copy of `slice2-a`, under the session scratchpad and never in the repository, in task order:
- each guard ends `HELD (0 failures)`, and each of its named mutations prints `HELD: the mutation is detected`. The counts quoted in each task are the measured ones.
- `tools/check_all.py --cold` with the four new guards registered: `PASS: 27 run, 6 not run, 0 failed`.
- A's guards still hold after B's edits, mutations included: `check_feeds_server` (all eight), `check_feeds_ledger` (its new `newline-run-id`), `check_telemetry` (all three) and `check_tool_surface --mutate-queue`.
- `check_feeds_ledger`'s writer scan caught B twice. The first draft of the triage guard named `seen.json` for its temporary ledger; it now names `ledger.json`. A's final-review fixes then made the scan flag any module calling `ledger.dump(` outside a fixed list of writers and guards; the triage guard writes temporary ledgers with it, as A's server guard does, so Task 1 adds it to that list (one line in A's guard).
- `slice2-a` moved while this draft was being written (`b069c51` to `a25b584`, 23:13Z: a lock around each feeds tool, `fullmatch` run ids, a "no text; not citable" page error, a wider writer scan). The whole plan was rebuilt on `a25b584`, and every check in this section was re-run there.
- **Tasks 3 and 6-10 were exercised on synthetic evidence**, which proves the plumbing and nothing about triage quality:
  - the catalogue was built by the real builder, offline, from the committed listings and the pages fetched above (one earlier run also simulated an OFAC fetch failure, to exercise `excluded`);
  - the labels were drafted by a rule;
  - three repeats ran through the real `run_triage`, the real server tools and the real runner, with only the model replaced by a scripted agent;
  - then disputes, decisions, `score.json` and the committed-band checks.
- `run_triage`'s handling of the SDK's turn cap, budget cap, error and success results was checked with a fake model.
- **Not verified:**
  - a real agent session (no model was run);
  - the live catalogue build (only 6 of its roughly 65 requests were made);
  - the counts of Task 10's evidence mutations on the real repeats (they depend on them).

The edit blocks in this plan were generated from the tested files and re-applied mechanically to a fresh copy of `slice2-a`. That run reproduced the tested files byte for byte.

### What I think is wrong or unworkable in the spec

1. **Triage-only mode cannot read** with list, fetch and triage alone (decision 2). The tool table in section 1 has no reading tool at all, and extraction never needed one because slice 1 pastes the document into the prompt.
2. **"The quote must be found in the fetched document" proves less than it sounds for FinCEN and OFSI.** The fetched document is a landing page (decision 1), so a FinCEN quote is in practice the subject line. The check still guarantees that the quote is verbatim and was read, which is all it ever guaranteed.
3. **The overall recall band will be dominated by FinCEN.** FinCEN's listing is its advisories page, so its 20 items are advisories by construction, and all should be relevant. I expect about 26 relevant items in 60, about 20 of them FinCEN. The discriminating items are the handful of OFSI penalties and OFAC settlements, where one miss moves that source's recall by 0.2 or more. The scorer reports every figure per source, and the band should be read that way.
4. **"Three times" is 18 sessions.** Section 1 caps a run at 10 triaged items, and the plan carries that cap in the tool. So a repeat over about 60 items is 6 sessions of at most 10. The sessions interleave the three sources, because a Friday run's items arrive mixed.
5. **"Recent" means six years for FinCEN.** It publishes a few advisories a year, so its newest 20 go back to August 2020.
6. **Agreed errors are invisible by design.** The owner decides only disagreements, and the labeller and the triage agent are the same model family. The spot check (decision 4) samples the one stratum where an agreed error costs recall. Unsampled agreed items stay "unchallenged, not confirmed", which is slice 1's label-pass wording.
7. **A consequence for sub-project C.** 45 of the 60 back-catalogue items are on today's listings, so they are also the first live Friday's backlog. At 10 triaged per run, the first live runs would spend five Fridays re-triaging items this eval has already labelled, unless C seeds the ledger from them through `accept_run`. That is an owner decision for C.
8. **A's `Refused:` prefix** makes refusals read as successes in telemetry (decision 7). It was invisible because A's orchestrator did not exist yet.

### Cost, against the spec's budgets

- **One triage session (at most 10 items):**
  - about 35 to 45 tool calls: 3 lists, 10 fetches, 12 to 20 page reads, 10 verdicts and a few re-quoted refusals;
  - about 25 to 45 turns;
  - a small context: landing pages are a few hundred tokens, and an OFAC page is about 700.
  - **Estimate US$0.30 to US$0.80, central about US$0.50.** That is below an extraction's US$0.73, which starts with a whole PDF in its prompt, and near the reviewer's US$0.48 for 29 turns. It is an estimate; the Task 7 pilot measures it.
- **Three repeats = 18 sessions: about US$5.40 to US$14.40, central about US$9.** The hard cap is 18 × US$1.50 = US$27, set per session by `max_budget_usd`. Add one session's worth for any failed-and-retried session.
- **Against the spec's budgets.** The US$5 ceiling is per Friday run, and this eval is not a Friday run. Each session is capped instead, and the pilot comes first. On the subscription token these figures are the SDK's notional price, not a bill. CLAUDE.md records extraction as free on the token. But the subscription's usage windows may split the repeats over more than one sitting, and the runner resumes.
- **What it says about the Friday run.** One triage session of at most 10 items leaves the rest of the US$5 for C's three extractions at US$1.00 each, provided a session costs no more than US$2.00. The pilot tests that condition. If the pilot costs more than US$2.00, the pilot report says so and the section 1 budget needs revisiting before C.

---

**Goal:** Measure triage before trusting it:
- a `feeds_triage` tool that carries the spec's triage rules in code;
- a triage-only orchestrator;
- a fixed, labelled back-catalogue of about 60 items;
- three committed repeats, the owner's decisions on the disagreements, and a committed recall and precision band that a cold guard rebuilds from the committed records.

**Architecture:**
- `feeds/triage.py` holds the rules (one verdict, the quote found in the pinned document, not_relevant kept, bounds, the cap of 10).
- `mcp_server/feeds_server.py` gains `feeds_read_page` and `feeds_triage`, plus an eval mode. In eval mode, set only by the eval runner, the same tools list a batch of the tracked catalogue and serve its pinned copies, never the live page, the network or the ledger.
- `agents/orchestrate_feeds.py` is the orchestrator in triage-only mode: four tools, no built-ins, the write allowlist in `agents/permissions.py`, and slice 1's telemetry unchanged.
- `evals/run_feeds_triage.py` runs the repeats. `evals/score_feeds_triage.py` builds the disputes and the band.
- Each piece has a cold, mutation-verified guard in `tools/check_all.py`.

**Tech Stack:** Python 3 standard library, plus what `.venv` already holds (`claude-agent-sdk` 0.2.152, `mcp`, `pydantic`, `pypdf`). No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-slice2-live-intelligence-design.md`, section 4 ("week 3"). Built on sub-project A as committed on branch `slice2-a` at `a25b584` (A's final-review fixes, which landed at 23:13Z while this draft was being written; everything here was re-verified on it). Where the A plan and the committed code differ, this plan follows the code. **If `slice2-a` has moved again by the time this plan is executed, re-run the Task 1 edits' anchors before trusting them.**

## Global Constraints

- Run Python as `.venv/bin/python` from the repository root.
- No new dependencies.
- Never create `.bak`, `_backup`, `_before_*` or similar snapshot files; git is the version control.
- Never commit a file over 50 MB. Never use `git commit --no-verify`.
- The pre-commit hook runs `tools/check_all.py` (all guards, several minutes). It is the gate; if it refuses, the commit is not ready.
- Every `evals/check_*.py` must be in `tools/check_all.py`'s `GUARDS` in the SAME commit that adds it. `check_all` refuses an unregistered guard.
- A guard ends `HELD (0 failures)`. Each `--mutate` must print `HELD: the mutation is detected`. Run mutations with a per-run bytecode cache: `PYTHONPYCACHEPREFIX=/tmp/fc08-mut-<label> .venv/bin/python evals/<guard>.py --mutate <label>`.
- Commit messages start `Slice 2 B:`. Never add a `Co-Authored-By` trailer.
- Push only when the owner asks. Nothing is published; this sub-project does not touch the walkthrough, and `tools/publish_walkthrough.py` is never run.
- **Network:** only `tools/build_feeds_catalogue.py` (Task 3) makes requests, run once by hand, through `feeds/http.get`. No guard touches the network.
- **Model runs:** only `evals/run_feeds_triage.py` starts agent sessions (Tasks 7 and 8), after the Task 7 pilot STOP. Before any session: `unset ANTHROPIC_API_KEY`, and `claude auth status` must not report `authMethod: api_key` (CLAUDE.md, Auth).
- **Evidence is never overwritten:**
  - the catalogue is built once;
  - the draft labels are written once and never edited;
  - a repeat record is written once;
  - `disputes.json` is written once;
  - the owner's decisions live in dated files of their own.
- Documents stay gitignored: `inbox/` (A) and `evals/feeds/docs/` (B). Only their sha256 values are tracked.

## Rulings made while writing this plan (from measurements taken 2026-09-26)

1. **Triage reads the document as A pins it** (decision 1, recommendation (a)). The landing page for FinCEN and OFSI, the action page for OFAC. Measured sizes above. Cost if wrong: C changes the input and the repeats are re-run.
2. **A fifth tool, `feeds_read_page`** (decision 2). It reads from `feeds.triage.page_texts`, the same list the quote is checked against, so what the agent reads and what the tool verifies cannot diverge.
3. **`feeds_triage` takes no page number.** The spec's signature is `(item_id, verdict, reason, quote)`. The tool tries every page with the shared matcher and records every page the quote holds on (`found_on`), and the tier it matched (`match`). A quote that holds on no page is refused.
4. **Every bound lives in one place, `feeds/triage.py`.** The tool's input model carries types only. So a 301-character reason gets a governed `Rejected:` reply, which telemetry counts as REFUSED and which tells the agent to shorten it. As a pydantic bound it would be a raised call, recorded as FAILURE. It also leaves one mutation point per rule, so a guard cannot be satisfied by a second layer.
5. **The cap of 10 triaged items per run (spec section 1) is carried by the tool.** The 11th verdict in a run is refused, and that item stays unfinished and returns next run.
6. **Refusals start `Rejected:`, in A's server too** (decision 7). Measured above. Both new tools also run under A's `_STATE_LOCK`, like its two.
7. **Eval mode lists the tracked catalogue, not the live page, and ignores the ledger.** The live listings move weekly, and after C's first accepted run the ledger would hide catalogue items. Three repeats months apart must see the same items. Documents come from the catalogue's pinned copies, verified against its sha256, with no request. From the fetch onward (the inbox, the pages, the triage rules) eval mode runs the production code unchanged. The runner is the only thing that sets `FEEDS_CATALOGUE`, and C's launcher must never set it.
8. **Batches interleave the sources.** A batch is at most 10 items, interleaved ofsi, fincen, ofac in catalogue order, and the batches are the same in every repeat.
9. **An item left without a verdict is a miss, not an exclusion.** It is not kept, so a relevant one counts against recall. It is listed as unfinished. It is not a dispute, because there is no verdict to disagree with.
10. **A dispute is ANY repeat's verdict differing from the draft**, one of three being enough. The spot check samples by hash, reproducibly, only from items the draft and every repeat called not_relevant.
11. **The draft labels are frozen before the first repeat.** The runner refuses to start unless `labels.json` is committed and unchanged, and each repeat records its sha256. The Task 10 guard checks that all three still match the file.
12. **The catalogue is fixed once.** The builder refuses to rebuild, and the guard pins its sha256. An item whose document cannot be fetched or paged is recorded under `excluded` and left out of the scored set: it would score the network, not the triage.
13. **Model and limits.** The model is `claude-sonnet-5`, the extraction agent's default, with US$1.50 and 80 turns per session. All three are recorded in every repeat, and changing any of them re-opens the band. A session stopped by its own turn or budget cap COMPLETED, and what it left is measured as unfinished. Only other errors (auth, credit, the CLI) are failures, and those batches are re-run. Retrying a capped session would spend again to hide a measured behaviour.
14. **Eval sessions' telemetry goes to `evals/feeds/repeats/<rep>/telemetry/`** (tracked). `data/telemetry/` holds extraction runs, which the walkthrough reads by run id.
15. **The owner's decisions go in `evals/owner_decisions/feeds_triage_labels_<date>.json`.** `labels.json` is never edited after drafting; the scorer derives each final label from the draft and the decisions.

## File map

| File | Task | Responsibility |
|---|---|---|
| `feeds/triage.py` | 1 | the triage rules: `decide`, `load`, `reconcile`, `page_texts`, `pinned_document`, `find_quote` |
| `mcp_server/feeds_server.py` | 1, 2 | `feeds_read_page`, `feeds_triage`; `Rejected:`; eval mode (`_catalogue`, `_list_catalogue`, `_catalogue_document`) |
| `evals/check_feeds_triage.py` | 1, 2 | the triage rules and eval mode, with stubbed HTTP; 13 mutations |
| `evals/check_feeds_server.py` | 1 | `Rejected:`, and the four-tool list |
| `evals/check_feeds_ledger.py` | 1 | its writer scan admits the triage guard's temporary ledgers |
| `tools/build_feeds_catalogue.py` | 3 | builds the back-catalogue once (network) |
| `evals/feeds/catalogue.json` | 3 | the tracked item list, each document's sha256 |
| `evals/check_feeds_catalogue.py` | 3, 6 | the catalogue pinned; the draft labels' contract |
| `.gitignore` | 3 | `evals/feeds/docs/`, `evals/feeds/repeats/.progress/` |
| `agents/permissions.py` | 4 | `FEEDS_*` allowlists; `permission_callback(run, allowlist, may)`; `expected_shadowing(read_only)` |
| `agents/orchestrate_feeds.py` | 4 | the triage-only orchestrator: `FeedsRun`, `agent_options`, `run_triage`, `TRIAGE_PROMPT` |
| `evals/check_feeds_orchestrator.py` | 4 | the orchestrator's tool surface |
| `evals/score_feeds_triage.py` | 5 | disputes, final labels, the band |
| `evals/check_feeds_score.py` | 5, 10 | the scorer on hand-computed data; then the committed band |
| `tools/write_feeds_labels.py` | 6 | shows an item's pages; writes the draft labels once, with the rubric |
| `evals/feeds/labels.json` | 6 | Claude's draft labels, frozen |
| `evals/run_feeds_triage.py` | 7 | runs the pilot and the repeats; resumes |
| `evals/feeds/repeats/rep{1,2,3}.json`, `rep*/telemetry/` | 7, 8 | the committed repeats and their telemetry |
| `evals/feeds/disputes.json` | 9 | the question put to the owner |
| `evals/owner_decisions/feeds_triage_labels_<date>.json` | 9 | the owner's answer |
| `evals/feeds/score.json` | 10 | the committed band |
| `tools/check_all.py`, `CLAUDE.md` | 1, 3, 4, 5, 10 | registration; the record |

---

### Task 1: `feeds_triage` and `feeds_read_page`

**Files:**
- Create: `feeds/triage.py`, `evals/check_feeds_triage.py`
- Modify: `mcp_server/feeds_server.py`, `evals/check_feeds_server.py`, `evals/check_feeds_ledger.py` (one line), `tools/check_all.py`

**Interfaces:**
- Consumes (A):
  - `feeds.inbox` (`load`, `find_item`, `items`, `run_dir`, `INBOX_ROOT`);
  - `schemas.citation_match.PageIndex`, `file_sha256`;
  - `schemas.proposal_contract.QUOTE_MIN`, `QUOTE_MAX`;
  - `schemas.html_pages.html_pages`;
  - the server's `_run_id`, `NO_RUN`, `INBOX_ROOT`.
- Consumes also A's `_STATE_LOCK`: both new tools do their work under it, as `feeds_list_new` and `feeds_fetch` do, so a parallel call cannot interleave with a verdict's check-and-append.
- Produces, for Tasks 2, 4, 5 and 7:
  - `feeds.triage`:
    - `TRIAGE = "triage.jsonl"`, `RELEVANT`, `NOT_RELEVANT`, `VERDICTS`, `REASON_MAX = 300`, `MAX_PER_RUN = 10`, `REJECTED = "Rejected:"`;
    - `page_texts(path) -> List[str]`;
    - `pinned_document(run_id, item, root) -> (Path | None, refusal)`;
    - `find_quote(pages, quote) -> (tier, pages)`;
    - `load(run_id, root) -> {key: verdict}`;
    - `decide(run_id, key, verdict, reason, quote, root) -> (recorded, message)`;
    - `reconcile(run_id, expected, root) -> {listed, triaged, unfinished, never_listed}`.
  - The MCP tools:
    - `feeds_read_page(item_key, page)`, annotated read-only;
    - `feeds_triage(item_key, verdict, reason, quote)`.
  - A `triage.jsonl` line: `key, source, item_id, verdict, reason, quote, found_on, match, document_sha256, run_id, decided_at`.

- [ ] **Step 1: Write the guard first**

Create `evals/check_feeds_triage.py`:

```python
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

WHAT IT HOLDS:
  quoted        a verdict is recorded only when its quote is found, by the shared matcher, in the item's
                pinned document; a fabricated quote is refused and nothing is written;
  one verdict   a second call for the same item is refused, and the first verdict stands on disk;
  kept          a not_relevant verdict is written like a relevant one and stays in triage.jsonl;
  bounded       reason 1..300 characters, quote 10..600 after strip, verdict relevant|not_relevant,
                at most 10 verdicts per run (the 11th refused: that item stays unfinished);
  pinned        read and triage refuse an item not fetched, and a pinned file whose bytes changed;
  counted       every refusal starts "Rejected:" and agents/telemetry classifies it REFUSED;
  reconciled    feeds.triage.reconcile lists every listed-or-expected item without a verdict as
                unfinished, including a whole source the agent never listed;
  inbox only    every file written is inside the temporary inbox; the repository's git status is unchanged.

HOW. As evals/check_feeds_server.py: the server's HTTP_GET, INBOX_ROOT and SEEN_PATH are swapped for a
stub serving the committed OFSI snapshot (every item's URL answers with the committed OFSI FAQ page) and
a temporary inbox and ledger. Cold: no network, no model.

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
    """Stands in for feeds.http.get: the OFSI listing, and the FAQ page for every www.gov.uk document URL."""

    def __init__(self) -> None:
        self.listing = (FIX / "feeds" / "ofsi.atom").read_bytes()
        self.doc = (FIX / "html" / "ofsi_uk_financial_sanctions_faqs.html").read_bytes()
        self.calls = []

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append(url)
        if url == SOURCES["ofsi"].listing_url:
            return fh.Fetched(url, url, "application/atom+xml", self.listing)
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

        for k in keys[3:10]:
            triage(k, "not_relevant", "General licence; no method, red flag or case.", PAGE1_QUOTE)
        said = triage(keys[10], "relevant", "Eleventh.", PAGE1_QUOTE)
        refusals.append(said)
        got = lines()
        out.append((len(got) == 10 and said.startswith("Rejected") and "cap" in said,
                    "the 11th verdict in one run is refused: the cap is 10", "%d verdicts; %s" % (len(got), said[:60])))
        out.append((sum(1 for g in got if g["verdict"] == "not_relevant") == 8,
                    "every not_relevant verdict stays in triage.jsonl (8 of the 10)",
                    "%d not_relevant" % sum(1 for g in got if g["verdict"] == "not_relevant")))

        try:
            rec = tri.reconcile(RUN, expected=keys[:12] + ["fincen:0123456789abcdef"], root=tmp / "inbox")
        except ValueError as exc:  # a second line for one item makes load() refuse the file
            rec = {"unfinished": None, "never_listed": None, "triaged": [], "error": str(exc)}
        out.append((rec["unfinished"] == sorted(keys[10:] + ["fincen:0123456789abcdef"])
                    and rec["never_listed"] == ["fincen:0123456789abcdef"] and len(rec["triaged"]) == 10,
                    "reconcile lists every untriaged item, and an expected item never listed, as unfinished",
                    "%d unfinished" % len(rec["unfinished"] or [])))

        classified = [telemetry.classify_response({"content": [{"type": "text", "text": r}]})[0] for r in refusals]
        out.append((len(refusals) >= 10 and all(r.startswith("Rejected:") for r in refusals)
                    and set(classified) == {telemetry.REFUSED}
                    and telemetry.classify_response("Recorded: x")[0] == telemetry.SUCCESS,
                    "every refusal starts 'Rejected:' and telemetry counts it REFUSED (%d refusals)" % len(refusals),
                    sorted(set(classified))))

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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python evals/check_feeds_triage.py`
Expected: it fails at import or at the first tool call, because `feeds/triage.py` and the two tools do not exist yet.

- [ ] **Step 3: Write the rules**

Create `feeds/triage.py`:

```python
"""
Triage verdicts for one feeds run: inbox/<run_id>/triage.jsonl (gitignored), one line per item.

Each rule is carried here, in code, whatever the agent intends (spec section 4 and section 1's table):
  one verdict   an item that already has a line cannot be triaged again; the first verdict stands;
  kept, always  a NOT_RELEVANT verdict is written exactly like a RELEVANT one, and nothing in this
                module removes or rewrites a line: the file is only ever appended to;
  quoted        the quote must be found in the item's PINNED document -- the bytes feeds_fetch pinned,
                re-hashed here -- on at least one of its pages, by schemas/citation_match.PageIndex,
                the one matcher every other caller uses;
  bounded       a reason of 1..REASON_MAX characters; a quote within the proposal contract's bounds
                (after strip, so padding cannot lengthen a short quote); at most MAX_PER_RUN verdicts
                in one run (spec section 1's cap of 10 triaged items).

Every refusal starts "Rejected:", the prefix agents/telemetry.py classifies as REFUSED, so a refused
triage call is counted as the governance working, never as a success.

The pages a quote is checked against are the pages the agent reads (page_texts): schemas/html_pages
for HTML, pypdf for PDF -- the same lists PageIndex.from_html and PageIndex.from_pdf build.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from feeds import inbox
from schemas.citation_match import PageIndex, file_sha256
from schemas.proposal_contract import QUOTE_MAX, QUOTE_MIN

TRIAGE = "triage.jsonl"
RELEVANT, NOT_RELEVANT = "relevant", "not_relevant"
VERDICTS = (RELEVANT, NOT_RELEVANT)
REASON_MAX = 300
MAX_PER_RUN = 10
REJECTED = "Rejected:"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def page_texts(path: Path) -> List[str]:
    """The pinned document's pages, as the agent reads them and as the quote is checked against them."""
    if Path(path).suffix == ".pdf":
        from pypdf import PdfReader
        return [p.extract_text() or "" for p in PdfReader(str(path)).pages]
    from schemas.html_pages import html_pages
    return html_pages(Path(path).read_bytes())


def pinned_document(run_id: str, item: dict, root: Path = inbox.INBOX_ROOT) -> Tuple[Optional[Path], str]:
    """(path, "") for an item whose pinned document is intact, else (None, the refusal)."""
    doc = item.get("document")
    if not doc:
        return None, "%s %s has no pinned document; call feeds_fetch first." % (REJECTED, item["key"])
    if doc.get("page_error"):
        return None, "%s %s's document could not be paged (%s)." % (REJECTED, item["key"], doc["page_error"])
    path = inbox.run_dir(run_id, root) / doc["path"]
    if not path.exists() or file_sha256(path) != doc["sha256"]:
        return None, "%s %s's pinned document is missing or no longer matches its sha256." % (REJECTED, item["key"])
    return path, ""


def find_quote(pages: Sequence[str], quote: str) -> Tuple[str, List[int]]:
    """(match tier, every 1-based page the quote holds on); ("missing", []) when it holds on none."""
    index = PageIndex(pages)
    held = [(n, index.locate(n, quote)) for n in range(1, len(index) + 1)]
    ok = [(n, loc.status) for n, loc in held if loc.ok]
    return (ok[0][1], [n for n, _ in ok]) if ok else ("missing", [])


def load(run_id: str, root: Path = inbox.INBOX_ROOT) -> Dict[str, dict]:
    path = inbox.run_dir(run_id, root) / TRIAGE
    out: Dict[str, dict] = {}
    if not path.exists():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["key"] in out:
            raise ValueError("%s line %d: %s has a second verdict" % (TRIAGE, n, entry["key"]))
        out[entry["key"]] = entry
    return out


def _append(run_id: str, entry: dict, root: Path) -> None:
    folder = inbox.run_dir(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / TRIAGE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def decide(run_id: str, key: str, verdict: str, reason: str, quote: str,
           root: Path = inbox.INBOX_ROOT) -> Tuple[bool, str]:
    """Record one verdict, or refuse it. Returns (recorded, the message the agent sees)."""
    reason, quote = (reason or "").strip(), (quote or "").strip()
    if verdict not in VERDICTS:
        return False, "%s verdict %r is not one of %s." % (REJECTED, verdict, ", ".join(VERDICTS))
    if not reason or len(reason) > REASON_MAX:
        return False, "%s the reason is %d characters; it must be 1 to %d." % (REJECTED, len(reason), REASON_MAX)
    if not QUOTE_MIN <= len(quote) <= QUOTE_MAX:
        return False, "%s the quote is %d characters; it must be %d to %d." % (REJECTED, len(quote), QUOTE_MIN,
                                                                               QUOTE_MAX)
    item = inbox.find_item(inbox.load(run_id, root), key)
    if item is None:
        return False, "%s %s was not listed as new in this run." % (REJECTED, key)
    done = load(run_id, root)
    if key in done:
        return False, "%s %s already has a verdict (%s) in this run; the first verdict stands." % (
            REJECTED, key, done[key]["verdict"])
    if len(done) >= MAX_PER_RUN:
        return False, "%s this run has triaged its cap of %d items; %s stays unfinished and returns next run." % (
            REJECTED, MAX_PER_RUN, key)
    path, refusal = pinned_document(run_id, item, root)
    if path is None:
        return False, refusal
    match, pages = find_quote(page_texts(path), quote)
    if not pages:
        return False, ("%s the quote is not in %s's pinned document on any page. Copy it again, verbatim, "
                       "from feeds_read_page." % (REJECTED, key))
    entry = {"key": key, "source": item["source"], "item_id": item["item_id"], "verdict": verdict,
             "reason": reason, "quote": quote, "found_on": pages, "match": match,
             "document_sha256": item["document"]["sha256"], "run_id": run_id, "decided_at": _now()}
    _append(run_id, entry, root)
    return True, "Recorded: %s is %s (quote found on page %s)." % (key, verdict, ", ".join(map(str, pages)))


def reconcile(run_id: str, expected: Sequence[str] = (), root: Path = inbox.INBOX_ROOT) -> dict:
    """After the agent stops, in code: which items this run listed, triaged, and left unfinished.

    `expected` is what the run was meant to cover (a catalogue batch); an expected item the agent never
    listed is unfinished too, so skipping a whole source cannot read as "nothing to triage".
    """
    listed = sorted(it["key"] for it in inbox.items(inbox.load(run_id, root)))
    done = load(run_id, root)
    want = sorted(set(listed) | set(expected))
    return {"listed": listed, "triaged": sorted(done), "unfinished": [k for k in want if k not in done],
            "never_listed": sorted(set(expected) - set(listed))}
```

- [ ] **Step 4: Add the two tools to the server, and make every refusal `Rejected:`**

In `mcp_server/feeds_server.py`, make these replacements in order:

**Edit 1 of 6.** Replace:

```python
Both write only into inbox/<run_id>/ (feeds/inbox.py). The run identity comes from the runner's
environment (FEEDS_RUN_ID), never from a tool argument. feeds_triage and feeds_extract are
sub-projects B and C.

```

with:

```python
Both write only into inbox/<run_id>/ (feeds/inbox.py). The run identity comes from the runner's
environment (FEEDS_RUN_ID), never from a tool argument.

Sub-project B adds two tools (feeds/triage.py holds their rules):

  feeds_read_page(item_key, page)   one page of an item's PINNED document, the pages a triage quote
                                    is checked against; read-only, and refused before a fetch.
  feeds_triage(item_key, verdict, reason, quote)
                                    one verdict per item, the quote found in the pinned document, a
                                    NOT_RELEVANT verdict stored and reported like any other, a cap of
                                    10 per run. feeds_extract is sub-project C.

Every governed refusal starts "Rejected:", the prefix agents/telemetry.py counts as REFUSED. (Until
slice 2 B these read "Refused:", which telemetry recorded as SUCCESS.) Both new tools run under
_STATE_LOCK, like A's two.

```

**Edit 2 of 6.** Replace:

```python
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http, inbox, ledger  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
```

with:

```python
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http, inbox, ledger, triage as feeds_triage  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
```

**Edit 3 of 6.** Replace:

```python

NO_RUN = "Refused: this server has no run identity (%s is unset or malformed); the runner sets it." % RUN_ENV

```

with:

```python

NO_RUN = "Rejected: this server has no run identity (%s is unset or malformed); the runner sets it." % RUN_ENV

```

**Edit 4 of 6.** Replace:

```python
    if source in state["sources"]:
        return "Refused: %s was already listed in this run (status %s); a listing is fetched once per run." % (
            source, state["sources"][source]["status"])
```

with:

```python
    if source in state["sources"]:
        return "Rejected: %s was already listed in this run (status %s); a listing is fetched once per run." % (
            source, state["sources"][source]["status"])
```

**Edit 5 of 6.** Replace:

```python
    if item is None:
        return "Refused: %s was not listed as new in this run; call feeds_list_new first." % item_key
    if item.get("document"):
```

with:

```python
    if item is None:
        return "Rejected: %s was not listed as new in this run; call feeds_list_new first." % item_key
    if item.get("document"):
```

**Edit 6 of 6.** Replace:

```python

if __name__ == "__main__":
```

with:

```python

class ReadPageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key feeds_list_new returned in this run, already fetched")
    page: int = Field(..., ge=1, description="1-based page number")


@mcp.tool(
    name="feeds_read_page",
    annotations={"title": "Read a page of a fetched document", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def read_page(params: ReadPageInput) -> str:
    """
    Read one page of the document feeds_fetch pinned for an item in this run.

    These are the pages feeds_triage checks your quote against. The reply starts
    "=== PAGE n of N ===". Read page 1 first; read more when it does not settle the question.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return _read_page(run_id, params.item_key, params.page)


def _read_page(run_id: str, item_key: str, page: int) -> str:
    item = inbox.find_item(inbox.load(run_id, INBOX_ROOT), item_key)
    if item is None:
        return "Rejected: %s was not listed as new in this run; call feeds_list_new first." % item_key
    path, refusal = feeds_triage.pinned_document(run_id, item, INBOX_ROOT)
    if path is None:
        return refusal
    pages = feeds_triage.page_texts(path)
    if not 1 <= page <= len(pages):
        return "Rejected: %s's document has %d page(s); there is no page %d." % (item_key, len(pages), page)
    return "=== PAGE %d of %d === %s | %s\n%s" % (page, len(pages), item_key, item["title"], pages[page - 1].strip())


class TriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key feeds_list_new returned in this run, already fetched")
    verdict: str = Field(..., description="relevant or not_relevant")
    reason: str = Field(..., description="Why, in at most 300 characters")
    quote: str = Field(..., description="One verbatim quote of 10 to 600 characters, copied from the item's "
                                        "pages as feeds_read_page returned them, that supports the verdict")


@mcp.tool(
    name="feeds_triage",
    annotations={"title": "Record a triage verdict", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
async def triage(params: TriageInput) -> str:
    """
    Record whether an item is relevant: it describes methods, red flags or cases of financial crime
    that a typology could hold. When in doubt, keep it (relevant).

    One verdict per item, final. The quote must be found in the item's pinned document. A
    not_relevant verdict is stored and reported, never deleted. Lengths and bounds are checked by
    the tool, which replies "Rejected: ..." with the reason when it refuses.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return feeds_triage.decide(run_id, params.item_key, params.verdict, params.reason, params.quote,
                                   INBOX_ROOT)[1]


if __name__ == "__main__":
```

- [ ] **Step 5: Update A's server guard for the prefix and the four tools**

In `evals/check_feeds_server.py`:

**Edit 1 of 7.** Replace:

```python
          and "RemoteDisconnected" in (st.get("error") or "") and requested == [SOURCES["ofac"].listing_url]
          and isinstance(again, str) and again.startswith("Refused") and len(requested) == 1)
    return (ok, "a dropped connection (RemoteDisconnected, not a URLError) through the REAL feeds.http.get is "
```

with:

```python
          and "RemoteDisconnected" in (st.get("error") or "") and requested == [SOURCES["ofac"].listing_url]
          and isinstance(again, str) and again.startswith("Rejected") and len(requested) == 1)
    return (ok, "a dropped connection (RemoteDisconnected, not a URLError) through the REAL feeds.http.get is "
```

**Edit 2 of 7.** Replace:

```python
        said = list_new("ofsi")
        out.append((said.startswith("Refused") and not stub.calls and not (tmp / "inbox").exists(),
                    "with no run identity nothing is requested or written", said[:90]))
```

with:

```python
        said = list_new("ofsi")
        out.append((said.startswith("Rejected") and not stub.calls and not (tmp / "inbox").exists(),
                    "with no run identity nothing is requested or written", said[:90]))
```

**Edit 3 of 7.** Replace:

```python
        said = list_new("ofsi")
        out.append((said.startswith("Refused") and not stub.calls and not (tmp / "inbox").exists(),
                    "a run identity with a trailing newline is malformed: nothing is requested or written",
```

with:

```python
        said = list_new("ofsi")
        out.append((said.startswith("Rejected") and not stub.calls and not (tmp / "inbox").exists(),
                    "a run identity with a trailing newline is malformed: nothing is requested or written",
```

**Edit 4 of 7.** Replace:

```python
        said = list_new("ofsi")
        out.append((said.startswith("Refused") and len(stub.calls) == n,
                    "a second listing of the same source in one run is refused without a request", said[:90]))
```

with:

```python
        said = list_new("ofsi")
        out.append((said.startswith("Rejected") and len(stub.calls) == n,
                    "a second listing of the same source in one run is refused without a request", said[:90]))
```

**Edit 5 of 7.** Replace:

```python
        said = fetch("ofsi:0000000000000000")
        out.append((said.startswith("Refused") and len(stub.calls) == n + 2,
                    "fetching a key this run did not list is refused without a request", said[:90]))
```

with:

```python
        said = fetch("ofsi:0000000000000000")
        out.append((said.startswith("Rejected") and len(stub.calls) == n + 2,
                    "fetching a key this run did not list is refused without a request", said[:90]))
```

**Edit 6 of 7.** Replace:

```python
        said = fetch(other_key)
        out.append((said.startswith("Refused") and len(stub.calls) == n,
                    "an item another run listed cannot be fetched in this run", said[:90]))
```

with:

```python
        said = fetch(other_key)
        out.append((said.startswith("Rejected") and len(stub.calls) == n,
                    "an item another run listed cannot be fetched in this run", said[:90]))
```

**Edit 7 of 7.** Replace:

```python
    hint = lambda t, a, b: getattr(t.annotations, a, getattr(t.annotations, b, None))  # noqa: E731
    out.append((sorted(tools) == ["feeds_fetch", "feeds_list_new"]
                and all(hint(t, "readOnlyHint", "read_only_hint") is False
                        and hint(t, "openWorldHint", "open_world_hint") is True for t in tools.values()),
                "the server exposes exactly feeds_list_new and feeds_fetch, both annotated as writing, open-world",
                sorted(tools)))
    return out
```

with:

```python
    hint = lambda t, a, b: getattr(t.annotations, a, getattr(t.annotations, b, None))  # noqa: E731
    ro = {n: hint(t, "readOnlyHint", "read_only_hint") for n, t in tools.items()}
    ow = {n: hint(t, "openWorldHint", "open_world_hint") for n, t in tools.items()}
    out.append((sorted(tools) == ["feeds_fetch", "feeds_list_new", "feeds_read_page", "feeds_triage"]
                and ro == {"feeds_fetch": False, "feeds_list_new": False, "feeds_read_page": True,
                           "feeds_triage": False}
                and ow["feeds_fetch"] is True and ow["feeds_list_new"] is True,
                "the server exposes exactly its four tools; only feeds_read_page is annotated read-only, and the "
                "two that reach the network are open-world", sorted(tools)))
    return out
```

- [ ] **Step 6: Let A's writer scan admit the new guard's temporary ledgers**

In `evals/check_feeds_ledger.py`:

Replace:

```python
        if "ledger.dump(" in text and rel not in ("feeds/ledger.py", "tools/accept_run.py",
                                                  "evals/check_feeds_ledger.py", "evals/check_feeds_server.py"):
            out.append("%s calls ledger.dump()" % rel)
```

with:

```python
        if "ledger.dump(" in text and rel not in ("feeds/ledger.py", "tools/accept_run.py",
                                                  "evals/check_feeds_ledger.py", "evals/check_feeds_server.py",
                                                  "evals/check_feeds_triage.py"):
            out.append("%s calls ledger.dump()" % rel)
```

The triage guard writes an empty ledger and a one-entry ledger for the server to read, with `ledger.dump(`, exactly as `evals/check_feeds_server.py` does. It never names `seen.json`.

- [ ] **Step 7: Run the three guards and every mutation**

```bash
.venv/bin/python evals/check_feeds_triage.py
for m in no-quote-check second-verdict drop-not-relevant long-reason no-strip no-cap no-pin-check refused-prefix; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_triage.py --mutate $m | tail -1; done
.venv/bin/python evals/check_feeds_server.py
for m in no-ledger-filter relist refetch unlisted-fetch quiet-layout swap-http-get narrow-transport quiet-no-text; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_server.py --mutate $m | tail -1; done
.venv/bin/python evals/check_feeds_ledger.py
PYTHONPYCACHEPREFIX=/tmp/fc08-mut-newline .venv/bin/python evals/check_feeds_ledger.py --mutate newline-run-id | tail -1
```

Expected (measured in scratch):
- `check_feeds_triage`: 21 PASS lines, `HELD (0 failures)`. Mutations detected: no-quote-check 5, second-verdict 8, drop-not-relevant 6, long-reason 2, no-strip 3, no-cap 3, no-pin-check 3, refused-prefix 11.
- `check_feeds_server`: 21 PASS, `HELD (0 failures)`. Its eight mutations are still detected: no-ledger-filter 2, relist 3, refetch 1, unlisted-fetch 1, quiet-layout 1, swap-http-get 2, narrow-transport 1, quiet-no-text 1. (pypdf prints `EOF marker not found` on stderr for A's not-really-a-PDF check; that is expected.)
- `check_feeds_ledger`: 19 PASS, `HELD (0 failures)`, and `newline-run-id` still detected. Its writer scan reads every Python file for `seen.json`, `record_decisions(` and `ledger.dump(`. The new guard names its temporary ledger `ledger.json`, and Step 6 lists it beside A's server guard for `ledger.dump(`.

- [ ] **Step 8: Register, check cold, commit**

In `tools/check_all.py`:

Replace:

```python
    ("check_feeds_server", ["evals/check_feeds_server.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

with:

```python
    ("check_feeds_server", ["evals/check_feeds_server.py"], "cold"),
    ("check_feeds_triage", ["evals/check_feeds_triage.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add feeds/triage.py mcp_server/feeds_server.py evals/check_feeds_triage.py evals/check_feeds_server.py evals/check_feeds_ledger.py tools/check_all.py
git commit -m "Slice 2 B: feeds_triage and feeds_read_page -- one verdict, a quote found in the pinned document, not_relevant kept; refusals read Rejected"
```

---

### Task 2: eval mode — the same tools over the tracked back-catalogue

**Files:**
- Modify: `mcp_server/feeds_server.py`, `evals/check_feeds_triage.py`

**Interfaces:**
- Consumes: `feeds.model.FeedItem` (its derived `key`); Task 1's tools.
- Produces, for Tasks 3 and 7:
  - the environment variables `FEEDS_CATALOGUE` (a path to `evals/feeds/catalogue.json`) and `FEEDS_CATALOGUE_BATCH` (comma-separated keys);
  - the module attribute `CATALOGUE_DOCS` (default `evals/feeds/docs/`), which a guard swaps;
  - a catalogue item: `FeedItem.to_json()` plus `document: {sha256, ext, content_type, bytes, final_url, …}`.

- [ ] **Step 1: Extend the guard first**

In `evals/check_feeds_triage.py`:

**Edit 1 of 5.** Replace:

```python
    python evals/check_feeds_triage.py --mutate refused-prefix     # refusals read "Refused:", which telemetry calls SUCCESS

```

with:

```python
    python evals/check_feeds_triage.py --mutate refused-prefix     # refusals read "Refused:", which telemetry calls SUCCESS
    python evals/check_feeds_triage.py --mutate catalogue-network  # eval mode fetches from the network
    python evals/check_feeds_triage.py --mutate catalogue-ledger   # eval mode hides items the ledger holds
    python evals/check_feeds_triage.py --mutate catalogue-all      # eval mode lists the whole catalogue, not the batch
    python evals/check_feeds_triage.py --mutate catalogue-unverified  # a catalogue copy is served without its sha256 check
    python evals/check_feeds_triage.py --mutate minted-key         # a catalogue key not derived from its item is accepted

```

**Edit 2 of 5.** Replace:

```python
  inbox only    every file written is inside the temporary inbox; the repository's git status is unchanged.

```

with:

```python
  inbox only    every file written is inside the temporary inbox; the repository's git status is unchanged.
  eval mode     with FEEDS_CATALOGUE and FEEDS_CATALOGUE_BATCH set (only evals/run_feeds_triage.py sets
                them), feeds_list_new lists exactly the batch's catalogue items, whatever the ledger
                holds, and feeds_fetch serves the catalogue's pinned copy after checking its sha256 --
                with no request at all; a catalogue whose key is not derived from its item, or a batch
                naming an unknown key, is refused.

```

**Edit 3 of 5.** Replace:

```python
import asyncio
import json
```

with:

```python
import asyncio
import hashlib
import json
```

**Edit 4 of 5.** Replace:

```python
    "refused-prefix": (TRIAGE_SRC, 'REJECTED = "Rejected:"\n', 'REJECTED = "Refused:"\n'),
}
```

with:

```python
    "refused-prefix": (TRIAGE_SRC, 'REJECTED = "Rejected:"\n', 'REJECTED = "Refused:"\n'),
    "catalogue-network": (SERVER, "        got = (_catalogue_document(cat, item) if cat is not None else\n",
                          "        got = (HTTP_GET(item[\"url\"], allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES, "
                          "max_bytes=MAX_DOCUMENT_BYTES) if cat is not None else\n"),
    "catalogue-ledger": (SERVER, "    new = list(items)  # the tracked catalogue decides, never the ledger\n",
                         "    new = [it for it in items if (it.source, it.item_id) not in ledger.load(SEEN_PATH)]\n"),
    "catalogue-all": (SERVER, '             if it["source"] == source and it["key"] in batch]\n',
                      '             if it["source"] == source]\n'),
    "catalogue-unverified": (SERVER, '    if hashlib.sha256(body).hexdigest() != doc["sha256"]:\n', "    if False:\n"),
    "minted-key": (SERVER, '        if FeedItem(**{k: it[k] for k in ITEM_FIELDS}).key != it["key"]:\n', "        if False:\n"),
}
```

**Edit 5 of 5.** Replace:

```python
    os.environ.pop(fs.RUN_ENV, None)
    out.append((git_status() == before, "the repository's git status is unchanged", ""))
    return out

```

with:

```python
    os.environ.pop(fs.RUN_ENV, None)
    out += catalogue_checks(tri, fs, stub)
    out.append((git_status() == before, "the repository's git status is unchanged", ""))
    return out


def catalogue_checks(tri, fs, stub) -> list:
    """Eval mode: the catalogue's batch, its pinned copies, and no request."""
    out = []
    items = SOURCES["ofsi"].parse(stub.listing)[:3]
    doc = stub.doc
    sha = hashlib.sha256(doc).hexdigest()
    entry = lambda it: dict(it.to_json(), document={  # noqa: E731
        "sha256": sha, "ext": "html", "content_type": "text/html", "bytes": len(doc), "final_url": it.url})
    catalogue = {"schema": "fc08-triage-catalogue/1", "items": [entry(it) for it in items]}
    run = "feeds-2026-10-02-ccc222"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "docs").mkdir()
        (tmp / "docs" / ("%s.html" % sha)).write_bytes(doc)
        cat_path = tmp / "catalogue.json"
        cat_path.write_text(json.dumps(catalogue), encoding="utf-8")
        fs.INBOX_ROOT, fs.SEEN_PATH, fs.CATALOGUE_DOCS = tmp / "inbox", tmp / "ledger.json", tmp / "docs"
        # The ledger has already decided the batch's first item: eval mode must list it anyway.
        fs.SEEN_PATH.write_text(ledger.dump([{"source": "ofsi", "item_id": items[0].item_id, "decision": "drop",
                                              "first_seen_run": "feeds-2026-09-25-000000",
                                              "decided_on": "2026-09-25"}]), encoding="utf-8")
        os.environ.update({fs.RUN_ENV: run, fs.CATALOGUE_ENV: str(cat_path),
                           fs.BATCH_ENV: ",".join(it.key for it in items[:2])})

        def call(coro):
            try:
                return asyncio.run(coro)
            except Exception as exc:
                return "RAISED %s: %s" % (type(exc).__name__, exc)

        n = len(stub.calls)
        said = call(fs.list_new(fs.ListNewInput(source="ofsi")))
        state = inbox_state(tmp, run)
        listed = [it["key"] for it in state["sources"].get("ofsi", {}).get("items", [])]
        out.append((listed == [it.key for it in items[:2]] and len(stub.calls) == n,
                    "eval mode lists exactly the batch's items, with no request", said.splitlines()[0][:80]))
        out.append((items[0].key in listed, "eval mode lists an item the ledger already holds: the catalogue decides",
                    ""))
        said = call(fs.list_new(fs.ListNewInput(source="fincen")))
        out.append((said.startswith("No new items") and len(stub.calls) == n,
                    "a source with nothing in the batch lists nothing, with no request", said[:70]))

        said = call(fs.fetch(fs.FetchInput(item_key=items[0].key)))
        got = item_of(inbox_state(tmp, run), items[0].key).get("document") or {}
        out.append((said.startswith("Fetched") and len(stub.calls) == n and got.get("sha256") == sha,
                    "eval mode fetches the catalogue's pinned copy, with no request", said[:70]))
        said = call(fs.triage(fs.TriageInput(item_key=items[0].key, verdict="not_relevant",
                                             reason="An FAQ index; no method, red flag or case.", quote=PAGE1_QUOTE)))
        out.append((said.startswith("Recorded"), "triage works on a catalogue document exactly as on a live one",
                    said[:70]))

        (tmp / "docs" / ("%s.html" % sha)).write_bytes(doc + b"<!-- changed -->")
        said = call(fs.fetch(fs.FetchInput(item_key=items[1].key)))
        got = item_of(inbox_state(tmp, run), items[1].key)
        out.append((said.startswith("Failed") and not got.get("document") and len(stub.calls) == n,
                    "a catalogue copy whose bytes changed is refused, and no document is recorded", said[:90]))
        (tmp / "docs" / ("%s.html" % sha)).write_bytes(doc)

        os.environ[fs.RUN_ENV] = "feeds-2026-10-02-ddd333"
        os.environ[fs.BATCH_ENV] = items[0].key + ",ofsi:ffffffffffffffff"
        said = call(fs.list_new(fs.ListNewInput(source="ofsi")))
        out.append((said.startswith("Rejected"), "a batch naming a key the catalogue does not hold is refused",
                    said[:90]))
        os.environ[fs.RUN_ENV] = "feeds-2026-10-02-eee444"
        os.environ[fs.BATCH_ENV] = "ofsi:0123456789abcdef"
        catalogue["items"][0]["key"] = "ofsi:0123456789abcdef"  # a key the agent could have minted
        cat_path.write_text(json.dumps(catalogue), encoding="utf-8")
        said = call(fs.list_new(fs.ListNewInput(source="ofsi")))
        out.append((said.startswith("Rejected") and "derived" in said,
                    "a catalogue key that is not derived from its item is refused", said[:90]))
    for k in (fs.RUN_ENV, fs.CATALOGUE_ENV, fs.BATCH_ENV):
        os.environ.pop(k, None)
    return out


def item_of(state: dict, key: str) -> dict:
    return next((it for it in state["sources"].get("ofsi", {}).get("items", []) if it["key"] == key), {})


def inbox_state(tmp: Path, run: str) -> dict:
    path = tmp / "inbox" / run / "items.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sources": {}}

```

Run: `.venv/bin/python evals/check_feeds_triage.py`
Expected: it fails, because the server has no `CATALOGUE_ENV` yet.

- [ ] **Step 2: Add eval mode to the server**

In `mcp_server/feeds_server.py`:

**Edit 1 of 7.** Replace:

```python
import hashlib
import os
```

with:

```python
import hashlib
import json
import os
```

**Edit 2 of 7.** Replace:

```python
from feeds import http as feeds_http, inbox, ledger, triage as feeds_triage  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, MAX_LISTING_BYTES, SOURCES, linked_pdfs  # noqa: E402
```

with:

```python
from feeds import http as feeds_http, inbox, ledger, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem, LayoutChanged  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, MAX_LISTING_BYTES, SOURCES, linked_pdfs  # noqa: E402
```

**Edit 3 of 7.** Replace:

```python
HTTP_GET = feeds_http.get

```

with:

```python
HTTP_GET = feeds_http.get
# EVAL MODE (slice 2 B): the back-catalogue's pinned documents, gitignored. See _catalogue().
CATALOGUE_DOCS = ROOT / "evals" / "feeds" / "docs"
CATALOGUE_ENV = "FEEDS_CATALOGUE"
BATCH_ENV = "FEEDS_CATALOGUE_BATCH"

```

**Edit 4 of 7.** Replace:

```python
NO_RUN = "Rejected: this server has no run identity (%s is unset or malformed); the runner sets it." % RUN_ENV

```

with:

```python
NO_RUN = "Rejected: this server has no run identity (%s is unset or malformed); the runner sets it." % RUN_ENV
ITEM_FIELDS = ("source", "item_id", "title", "url", "published", "summary")


def _catalogue():
    """(catalogue, its sha256, the batch keys) when the runner started this server on the back-catalogue.

    EVAL MODE. evals/run_feeds_triage.py sets FEEDS_CATALOGUE (evals/feeds/catalogue.json) and
    FEEDS_CATALOGUE_BATCH (the keys one session triages), so the SAME tools triage the fixed, tracked
    back-catalogue: feeds_list_new returns the batch's items -- never the live page, and never filtered
    by the ledger, so three repeats months apart see the same items -- and feeds_fetch returns the
    catalogue's pinned copy from CATALOGUE_DOCS, refused unless it hashes to the sha256 the catalogue
    records, never the network. From there on (the inbox, the pages, feeds_read_page, feeds_triage) the
    path is the production one, unchanged. The agent cannot set either variable.

    Returns None when FEEDS_CATALOGUE is unset (a live run). Raises ValueError on a catalogue whose key
    is not derived from its item, or a batch that is empty or names a key the catalogue does not hold.
    """
    path = os.environ.get(CATALOGUE_ENV)
    if not path:
        return None
    raw = Path(path).read_bytes()
    catalogue = json.loads(raw)
    for it in catalogue["items"]:
        if FeedItem(**{k: it[k] for k in ITEM_FIELDS}).key != it["key"]:
            raise ValueError("catalogue key %s is not derived from its item" % it["key"])
    batch = [k for k in os.environ.get(BATCH_ENV, "").split(",") if k]
    unknown = sorted(set(batch) - {it["key"] for it in catalogue["items"]})
    if not batch or unknown:
        raise ValueError("the batch is empty or names keys the catalogue does not hold: %s" % unknown)
    return catalogue, hashlib.sha256(raw).hexdigest(), batch


def _load_catalogue():
    """(_catalogue() or None, refusal or None)."""
    try:
        return _catalogue(), None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, "Rejected: the eval catalogue is unusable: %s" % exc


def _new_items_reply(source: str, new: list, listed: int) -> str:
    rows = ["%s | %s | %s | %s" % (it.key, it.published, it.title, it.summary or "-") for it in new]
    return "%d new of %d listed on %s:\nkey | published | title | summary\n%s" % (
        len(new), listed, source, "\n".join(rows))


def _list_catalogue(run_id: str, state: dict, source: str, cat) -> str:
    catalogue, sha, batch = cat
    items = [FeedItem(**{k: it[k] for k in ITEM_FIELDS}) for it in catalogue["items"]
             if it["source"] == source and it["key"] in batch]
    new = list(items)  # the tracked catalogue decides, never the ledger
    state["sources"][source] = {"listed_at": _now(), "listing_url": "catalogue", "status": "ok", "error": None,
                                "listing": None, "listing_sha256": sha, "listed": len(items), "already_seen": 0,
                                "items": [dict(it.to_json(), document=None) for it in new]}
    inbox.save(run_id, state, INBOX_ROOT)
    if not new:
        return "No new items: %s has none in this catalogue batch." % source
    return _new_items_reply(source, new, len(items))


def _catalogue_document(cat, item: dict) -> feeds_http.Fetched:
    """The catalogue's pinned copy of an item's document, from CATALOGUE_DOCS; never the network."""
    doc = next(it for it in cat[0]["items"] if it["key"] == item["key"])["document"]
    path = Path(CATALOGUE_DOCS) / ("%s.%s" % (doc["sha256"], doc["ext"]))
    if not path.exists():
        raise feeds_http.FetchRefused("the catalogue copy %s is missing; see tools/build_feeds_catalogue.py" % path.name)
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != doc["sha256"]:
        raise feeds_http.FetchRefused("the catalogue copy %s no longer matches its sha256" % path.name)
    return feeds_http.Fetched(item["url"], doc["final_url"], doc["content_type"], body)

```

**Edit 5 of 7.** Replace:

```python
            source, state["sources"][source]["status"])
    src = SOURCES[source]
```

with:

```python
            source, state["sources"][source]["status"])
    cat, refusal = _load_catalogue()
    if refusal:
        return refusal
    if cat is not None:
        return _list_catalogue(run_id, state, source, cat)
    src = SOURCES[source]
```

**Edit 6 of 7.** Replace:

```python
        return "No new items: %s listed %d, every one already decided." % (source, len(items))
    rows = ["%s | %s | %s | %s" % (it.key, it.published, it.title, it.summary or "-") for it in new]
    return "%d new of %d listed on %s:\nkey | published | title | summary\n%s" % (
        len(new), len(items), source, "\n".join(rows))

```

with:

```python
        return "No new items: %s listed %d, every one already decided." % (source, len(items))
    return _new_items_reply(source, new, len(items))

```

**Edit 7 of 7.** Replace:

```python
        return "Already fetched: %s" % _describe(item["document"])
    src = SOURCES[item["source"]]
    try:
        got = HTTP_GET(item["url"], allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES,
                       max_bytes=MAX_DOCUMENT_BYTES)
    except feeds_http.FetchRefused as exc:
```

with:

```python
        return "Already fetched: %s" % _describe(item["document"])
    cat, refusal = _load_catalogue()
    if refusal:
        return refusal
    src = SOURCES[item["source"]]
    try:
        got = (_catalogue_document(cat, item) if cat is not None else
               HTTP_GET(item["url"], allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES,
                        max_bytes=MAX_DOCUMENT_BYTES))
    except feeds_http.FetchRefused as exc:
```

- [ ] **Step 3: Run the guards and every mutation**

```bash
.venv/bin/python evals/check_feeds_triage.py
for m in no-quote-check second-verdict drop-not-relevant long-reason no-strip no-cap no-pin-check refused-prefix catalogue-network catalogue-ledger catalogue-all catalogue-unverified minted-key; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_triage.py --mutate $m | tail -1; done
.venv/bin/python evals/check_feeds_server.py
```

Expected (measured):
- 29 PASS lines, `HELD (0 failures)`.
- The eight Task 1 mutations give the same counts as before.
- catalogue-network 2, catalogue-ledger 4, catalogue-all 1, catalogue-unverified 1, minted-key 1.
- `check_feeds_server` still `HELD (0 failures)`, 21 PASS. Live mode is unchanged: with `FEEDS_CATALOGUE` unset, `_catalogue()` returns None and A's code path runs as before.

- [ ] **Step 4: Commit**

```bash
.venv/bin/python tools/check_all.py --cold
git add mcp_server/feeds_server.py evals/check_feeds_triage.py
git commit -m "Slice 2 B: eval mode -- the feeds tools over a tracked catalogue batch, pinned copies verified, no network, no ledger"
```

---

### Task 3: the back-catalogue, built once

**Files:**
- Create: `tools/build_feeds_catalogue.py`, `evals/check_feeds_catalogue.py`, `evals/feeds/catalogue.json` (by running the builder)
- Modify: `.gitignore`, `tools/check_all.py`

**Interfaces:**
- Consumes (A): `feeds.http.get`, `feeds.sources` (`SOURCES`, `DOCUMENT_TYPES`, `MAX_*`, `linked_pdfs`), `PageIndex`.
- Produces, for Tasks 5 to 10:
  - `evals/feeds/catalogue.json`: `{schema, built_on, per_source, listing_pages, listings, items, excluded}`;
  - `evals/feeds/docs/<sha256>.<ext>`;
  - `tools/build_feeds_catalogue.dump`, `SCHEMA`, `ORDER`, `PER_SOURCE`.

- [ ] **Step 1: Ignore the documents**

In `.gitignore`:

Replace:

```gitignore
inbox/
```

with:

```gitignore
inbox/

# Slice 2 B: the triage back-catalogue's pinned documents and listings (hashes in evals/feeds/catalogue.json),
# and the eval runner's resume state. Never tracked.
evals/feeds/docs/
evals/feeds/repeats/.progress/
```

- [ ] **Step 2: Write the guard**

Create `evals/check_feeds_catalogue.py`:

```python
"""
Pin the triage back-catalogue (evals/feeds/catalogue.json) and its draft labels (evals/feeds/labels.json).

Usage:
    python evals/check_feeds_catalogue.py
    python evals/check_feeds_catalogue.py --mutate drop-item      # an item removed from the set
    python evals/check_feeds_catalogue.py --mutate minted-key     # a key not derived from its item
    python evals/check_feeds_catalogue.py --mutate dup-key        # one item listed twice
    python evals/check_feeds_catalogue.py --mutate no-text        # a document with no text pages
    python evals/check_feeds_catalogue.py --mutate unlabelled     # a catalogue item with no draft label
    python evals/check_feeds_catalogue.py --mutate bad-label      # a label other than relevant | not_relevant
    python evals/check_feeds_catalogue.py --mutate long-reason    # a draft reason over 300 characters
    python evals/check_feeds_catalogue.py --mutate rubric-edited  # the rubric changed after its hash was taken

WHAT IT HOLDS:
  fixed once    the catalogue's bytes are its canonical form and hash to CATALOGUE_SHA256, pinned the day
                it was built: the set cannot be rebuilt, re-ordered or edited without this guard saying so;
  the set       PER_SOURCE items listed per source, each either in "items" or in "excluded" with a reason;
  derived keys  every key is FeedItem's own derivation from the item, and no key or item id repeats;
  readable      every document is pinned by a 64-hex sha256, with at least one text page;
  where         the catalogue and labels are tracked; evals/feeds/docs/ is gitignored and holds nothing tracked;
  labels        (once labels.json exists) one draft label per catalogue item and no other, each relevant |
                not_relevant with a reason of 1..300 characters, drafted before any repeat, under a rubric
                whose sha256 is recorded beside it.

The documents themselves are gitignored, so this guard never opens them: evals/run_feeds_triage.py
refuses to start on a missing or changed copy, and the server refuses to serve one.

COLD. Tracked files and git only.

NOT A VACUOUS PASS. Each --mutate changes the loaded catalogue or labels in memory; a check must fail.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from feeds.model import FeedItem  # noqa: E402
from feeds.triage import REASON_MAX, VERDICTS  # noqa: E402
import build_feeds_catalogue as bfc  # noqa: E402

CATALOGUE = ROOT / "evals" / "feeds" / "catalogue.json"
LABELS = ROOT / "evals" / "feeds" / "labels.json"
# Pinned the day the catalogue was built (Task 3). Moving it is a new back-catalogue: an owner decision.
CATALOGUE_SHA256 = "PIN-FROM-TASK-3"
LABELS_SCHEMA = "fc08-triage-labels/1"
# False until Task 5 writes labels.json; flipped to True in that commit, after which a missing or
# partial labels file FAILS rather than being skipped.
LABELS_DRAFTED = False
FIELDS = ("source", "item_id", "title", "url", "published", "summary")


def _git(*args) -> str:
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True).stdout


def catalogue_checks(cat: dict, raw: bytes) -> list:
    out = []
    items, excluded = cat.get("items", []), cat.get("excluded", [])
    out.append((raw.decode("utf-8") == bfc.dump(json.loads(raw)) and cat.get("schema") == bfc.SCHEMA,
                "the file is the builder's canonical form, schema %s" % bfc.SCHEMA, cat.get("schema")))
    digest = hashlib.sha256(bfc.dump(cat).encode("utf-8")).hexdigest()
    out.append((digest == CATALOGUE_SHA256, "the catalogue hashes to the sha256 pinned when it was built",
                digest[:16]))
    per = {s: sum(1 for it in items + excluded if it["source"] == s) for s in bfc.ORDER}
    out.append((per == {s: bfc.PER_SOURCE for s in bfc.ORDER} and all(e.get("reason") for e in excluded),
                "each source lists %d items, every one scored or excluded with a reason" % bfc.PER_SOURCE,
                "%s; %d excluded" % (per, len(excluded))))
    minted = [it["key"] for it in items + excluded if FeedItem(**{k: it[k] for k in FIELDS}).key != it["key"]]
    out.append((not minted, "every key is FeedItem's derivation from its item", minted[:3]))
    keys = [it["key"] for it in items + excluded]
    ids = [(it["source"], it["item_id"]) for it in items + excluded]
    out.append((len(set(keys)) == len(keys) and len(set(ids)) == len(ids), "no key or item id repeats",
                "%d keys" % len(keys)))
    bad = [it["key"] for it in items
           if not (re.fullmatch(r"[0-9a-f]{64}", (it.get("document") or {}).get("sha256", ""))
                   and it["document"].get("ext") in ("html", "pdf") and it["document"].get("text_pages", 0) >= 1)]
    out.append((items and not bad, "every scored item's document is pinned by sha256 and has text",
                "%d items; bad %s" % (len(items), bad[:3])))
    tracked_docs = _git("ls-files", "evals/feeds/docs").strip()
    ignored = subprocess.run(["git", "check-ignore", "-q", "evals/feeds/docs/probe.html"], cwd=ROOT).returncode == 0
    tracked = _git("ls-files", "evals/feeds/catalogue.json").strip()
    out.append((ignored and not tracked_docs and tracked == "evals/feeds/catalogue.json",
                "the catalogue is tracked; evals/feeds/docs/ is gitignored and holds nothing tracked",
                "ignored=%s tracked_docs=%r" % (ignored, tracked_docs[:60])))
    return out


def label_checks(cat: dict, labels: dict) -> list:
    out = []
    keys = {it["key"] for it in cat["items"]}
    got = labels.get("labels", {})
    out.append((labels.get("schema") == LABELS_SCHEMA and set(got) == keys,
                "one draft label per scored catalogue item, and no other",
                "missing %s; extra %s" % (sorted(keys - set(got))[:3], sorted(set(got) - keys)[:3])))
    bad = sorted(k for k, v in got.items()
                 if v.get("label") not in VERDICTS or not 1 <= len((v.get("reason") or "").strip()) <= REASON_MAX)
    out.append((not bad, "every label is relevant | not_relevant with a reason of 1..%d characters" % REASON_MAX,
                bad[:3]))
    rubric = labels.get("rubric", "")
    out.append((rubric and hashlib.sha256(rubric.encode("utf-8")).hexdigest() == labels.get("rubric_sha256")
                and labels.get("catalogue_sha256") == CATALOGUE_SHA256
                and labels.get("drafted_by") == "claude-in-session"
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", labels.get("drafted_on", "")),
                "the labels name their rubric by sha256, the catalogue they label, who drafted them and when",
                labels.get("drafted_on")))
    on_disk = LABELS.read_text(encoding="utf-8") if LABELS.exists() else ""
    out.append((_git("ls-files", "evals/feeds/labels.json").strip() == "evals/feeds/labels.json"
                and on_disk == bfc.dump(json.loads(on_disk or "{}")),
                "the labels are tracked, in canonical form (their sha256 is what every repeat records)", ""))
    return out


def mutate(name: str, cat: dict, labels):
    cat, labels = copy.deepcopy(cat), copy.deepcopy(labels)
    first = cat["items"][0]["key"]
    if name == "drop-item":
        cat["items"].pop()
    elif name == "minted-key":
        cat["items"][0]["key"] = "%s:0123456789abcdef" % cat["items"][0]["source"]
    elif name == "dup-key":
        cat["items"].append(copy.deepcopy(cat["items"][0]))
    elif name == "no-text":
        cat["items"][0]["document"]["text_pages"] = 0
    elif labels is None:
        raise SystemExit("MUTATION %s needs the draft labels (LABELS_DRAFTED is False)" % name)
    elif name == "unlabelled":
        labels["labels"].pop(first)
    elif name == "bad-label":
        labels["labels"][first]["label"] = "maybe"
    elif name == "long-reason":
        labels["labels"][first]["reason"] = "x" * (REASON_MAX + 1)
    elif name == "rubric-edited":
        labels["rubric"] += " Edited later."
    return cat, labels


MUTATIONS = ("drop-item", "minted-key", "dup-key", "no-text", "unlabelled", "bad-label", "long-reason",
             "rubric-edited")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage back-catalogue and its draft labels")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    raw = CATALOGUE.read_bytes()
    cat = json.loads(raw)
    labels = None
    if LABELS_DRAFTED:
        labels = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {"labels": {}}
    if args.mutate:
        cat, labels = mutate(args.mutate, cat, labels)
        print("MUTATED: %s\n" % args.mutate)
    results = catalogue_checks(cat, raw)
    if labels is not None:
        results += label_checks(cat, labels)
    else:
        print("  NOTE LABELS_DRAFTED is False: the draft labels are Task 5's, and their checks did not run\n")
    failures = 0
    for ok, label, detail in results:
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

- [ ] **Step 3: Write the builder**

Create `tools/build_feeds_catalogue.py`:

```python
"""
Build the triage back-catalogue ONCE (slice 2 B, spec section 4): about 60 recent items, 20 per source.

Usage:
    python tools/build_feeds_catalogue.py            # fetch, pin, write evals/feeds/catalogue.json
    python tools/build_feeds_catalogue.py --dry-run  # the listings only: counts per source, nothing written

NETWORK. The one tool in sub-project B that makes requests. Run by hand, once; no guard calls it and
tools/check_all.py never runs it. Every request goes through feeds/http.get: the allowlist, the size
and type limits, a 2-second gap, the descriptive user agent. Measured 2026-09-27: OFSI's Atom feed
holds 20 entries and does not paginate (?page=2 returns the same 20); FinCEN's listing shows 15 per
page and OFAC's 10, and both paginate with ?page=1 (no overlap with page 0). So the listings are OFSI
page 0, FinCEN pages 0-1 and OFAC pages 0-1 (5 requests), then one request per item's document.

WRITES:
  evals/feeds/catalogue.json   TRACKED. The item list, each document's sha256 and paging, the listings'
                               sha256, and any item excluded with its reason.
  evals/feeds/docs/            GITIGNORED. <sha256>.<ext> per document; listings/<source>-p<n>.<ext>.

REFUSES when catalogue.json exists. The set is fixed once, so the three repeats and every later
comparison score the same items; a new set is a new file and an owner decision, never a rebuild.

An item whose document cannot be fetched, or pages to no text, is recorded under "excluded" with the
reason and is NOT in "items": the agent cannot quote a document it cannot read, so the item would be
scored as a miss that measures the network rather than the triage. The catalogue is not topped up
past a failure; "about 60" is what the spec asks for.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
from feeds.sources import DOCUMENT_TYPES, MAX_DOCUMENT_BYTES, MAX_LISTING_BYTES, SOURCES, linked_pdfs  # noqa: E402
from schemas.citation_match import PageIndex  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
DOCS = EVAL_DIR / "docs"
SCHEMA = "fc08-triage-catalogue/1"
PER_SOURCE = 20
ORDER = ("ofsi", "fincen", "ofac")
PAGES = {"ofsi": ("",), "fincen": ("", "?page=1"), "ofac": ("", "?page=1")}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pin(docs: Path, rel: str, data: bytes) -> Path:
    """Write once under docs/; the same bytes again is a no-op, different bytes are refused."""
    path = Path(docs) / rel
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("%s is pinned; refusing to overwrite it with different bytes" % rel)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def listed(source: str, get, docs: Path, pin: bool = True):
    """The newest PER_SOURCE items of a source, in listing order, and the listings they came from."""
    src = SOURCES[source]
    items, ids, listings = [], set(), []
    for n, suffix in enumerate(PAGES[source]):
        got = get(src.listing_url + suffix, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                  max_bytes=MAX_LISTING_BYTES)
        rel = "listings/%s-p%d.%s" % (source, n, src.listing_ext)
        if pin:
            _pin(docs, rel, got.body)
        listings.append({"url": src.listing_url + suffix, "path": rel, "fetched_at": _now(),
                         "sha256": hashlib.sha256(got.body).hexdigest()})
        for it in src.parse(got.body):
            if it.item_id not in ids:
                ids.add(it.item_id)
                items.append(it)
        if len(items) >= PER_SOURCE:
            break
    return items[:PER_SOURCE], listings


def pin_document(item, get, docs: Path) -> dict:
    src = SOURCES[item.source]
    got = get(item.url, allowed_hosts=src.hosts, allowed_types=DOCUMENT_TYPES, max_bytes=MAX_DOCUMENT_BYTES)
    digest = hashlib.sha256(got.body).hexdigest()
    is_pdf = got.content_type == "application/pdf"
    ext = "pdf" if is_pdf else "html"
    path = _pin(docs, "%s.%s" % (digest, ext), got.body)
    index = PageIndex.from_pdf(path) if is_pdf else PageIndex.from_html(got.body)
    text_pages = sum(1 for p in index.pages if p.strip())
    if not text_pages:
        raise ValueError("the document pages to no text")
    return {"sha256": digest, "ext": ext, "content_type": got.content_type, "bytes": len(got.body),
            "final_url": got.final_url, "fetched_at": _now(), "pages": len(index), "text_pages": text_pages,
            "linked_pdfs": [] if is_pdf else linked_pdfs(got.body, got.final_url)}


def build(get=feeds_http.get, docs: Path = DOCS, today: date = None) -> dict:
    items, excluded, listings = [], [], {}
    for source in ORDER:
        found, listings[source] = listed(source, get, docs)
        for it in found:
            try:
                items.append(dict(it.to_json(), document=pin_document(it, get, docs)))
                status = "pinned"
            except (feeds_http.FetchRefused, ValueError) as exc:
                excluded.append(dict(it.to_json(), reason="%s: %s" % (type(exc).__name__, exc)))
                status = "EXCLUDED: %s" % exc
            print("  %-6s %-40s %s" % (source, it.item_id[-40:], status))
    return {"schema": SCHEMA, "built_on": (today or date.today()).isoformat(), "per_source": PER_SOURCE,
            "listing_pages": {s: list(PAGES[s]) for s in ORDER}, "listings": listings,
            "items": items, "excluded": excluded}


def dump(catalogue: dict) -> str:
    return json.dumps(catalogue, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build the triage back-catalogue once")
    ap.add_argument("--dry-run", action="store_true", help="parse the listings only; write nothing")
    args = ap.parse_args(argv)
    if CATALOGUE.exists():
        print("REFUSED: %s exists. The back-catalogue is built once; a new set is a new file and an owner "
              "decision." % CATALOGUE.relative_to(ROOT))
        return 1
    try:
        if args.dry_run:
            for source in ORDER:
                found, _ = listed(source, feeds_http.get, DOCS, pin=False)
                print("  %-6s %2d items, newest %s, oldest %s" % (source, len(found), found[0].published,
                                                                   found[-1].published))
            return 0
        catalogue = build()
    except (feeds_http.FetchRefused, LayoutChanged) as exc:
        print("FAILED: %s -- nothing written to %s" % (exc, CATALOGUE.relative_to(ROOT)))
        return 1
    CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text(dump(catalogue), encoding="utf-8")
    counts = {s: sum(1 for it in catalogue["items"] if it["source"] == s) for s in ORDER}
    print("\nWROTE %s: %d items (%s), %d excluded; sha256 %s" % (
        CATALOGUE.relative_to(ROOT), len(catalogue["items"]), ", ".join("%s %d" % kv for kv in counts.items()),
        len(catalogue["excluded"]), hashlib.sha256(CATALOGUE.read_bytes()).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Dry run (5 requests), then build (about 65 requests, about 3 minutes)**

Run: `.venv/bin/python tools/build_feeds_catalogue.py --dry-run`

Expected: three lines like the ones below. The dates are measured 2026-09-26 and move as publishers post; OFAC's oldest in particular moves back as new actions are added.

```
  ofsi   20 items, newest 2026-09-24, oldest 2026-05-19
  fincen 20 items, newest 2026-06-05, oldest 2020-08-18
  ofac   20 items, newest 2026-09-24, oldest 2026-08-12
```

- If any source shows fewer than 20, STOP and report. The pagination measured above has changed.
- A `FAILED … layout` line means a live listing moved since A's snapshot. Report it; do not edit an adapter to match.

Then run: `.venv/bin/python tools/build_feeds_catalogue.py`

Expected: one line per item (`pinned`, or `EXCLUDED: <reason>`), then:

```
WROTE evals/feeds/catalogue.json: 60 items (ofsi 20, fincen 20, ofac 20), 0 excluded; sha256 <64 hex>
```

- If more than 3 items are excluded, STOP and report: a source is misbehaving, and a catalogue with holes is not what the spec asked for.
- The builder refuses to run again once `catalogue.json` exists. That is deliberate.

- [ ] **Step 5: Pin the catalogue and run the guard**

In `evals/check_feeds_catalogue.py`, replace `CATALOGUE_SHA256 = "PIN-FROM-TASK-3"` with the sha256 the builder printed.

```bash
git add evals/feeds/catalogue.json   # the guard checks that it is tracked
.venv/bin/python evals/check_feeds_catalogue.py
for m in drop-item minted-key dup-key no-text; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_catalogue.py --mutate $m | tail -1; done
git status --short evals/feeds
```

Expected:
- a NOTE that the label checks did not run, then 7 PASS lines and `HELD (0 failures)`.
- Mutations (measured on the scratch catalogue): drop-item 2, minted-key 2, dup-key 3, no-text 2.
- `git status` shows `A  evals/feeds/catalogue.json` and nothing under `evals/feeds/docs/`.

- [ ] **Step 6: Read what was built**

Open `evals/feeds/catalogue.json` and list, per source, each item's title and its document's `pages` and `linked_pdfs`. Report the list; Task 6 labels these items. Say which items are FinCEN translations and which OFAC actions name a settlement or enforcement action, because the rubric rules on both.

- [ ] **Step 7: Register and commit**

In `tools/check_all.py`:

Replace:

```python
    ("check_feeds_triage", ["evals/check_feeds_triage.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

with:

```python
    ("check_feeds_triage", ["evals/check_feeds_triage.py"], "cold"),
    ("check_feeds_catalogue", ["evals/check_feeds_catalogue.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add .gitignore tools/build_feeds_catalogue.py evals/check_feeds_catalogue.py evals/feeds/catalogue.json tools/check_all.py
git commit -m "Slice 2 B: the triage back-catalogue, 20 per source, built once and pinned by sha256"
```

---

### Task 4: the triage-only orchestrator

**Files:**
- Create: `agents/orchestrate_feeds.py`, `evals/check_feeds_orchestrator.py`
- Modify: `agents/permissions.py`, `tools/check_all.py`

**Interfaces:**
- Consumes:
  - `agents.telemetry` (`run_started`, `run_completed`, `tool_hooks`, `reconcile`), unchanged;
  - Task 1's `feeds.triage.reconcile`, `MAX_PER_RUN`;
  - Task 2's environment variables;
  - `evals/check_tool_surface.built_command`.
- Produces, for Task 7 (and for sub-project C, which extends it):
  - `agents.permissions.FEEDS_SERVER_KEY`, `FEEDS_READ_ONLY_TOOLS`, `FEEDS_WRITE_ALLOWLIST`;
  - `permission_callback(run, allowlist=None, may=…)`, `expected_shadowing(read_only=None)`, with defaults unchanged;
  - `agents.orchestrate_feeds`:
    - `FeedsRun(run_id, catalogue=None, batch=())`;
    - `agent_options(run, …)`;
    - `async run_triage(run, …) -> summary`;
    - `AGENT_TOOLS`, `TRIAGE_PROMPT`, `PROMPT_SHA256`, `MODEL`, `MAX_BUDGET_USD`, `MAX_TURNS`, `LIMIT_SUBTYPES`.
  - `run_triage`'s summary: `run_id, failure, limit, tool_calls, turns, cost_usd, duration_ms, stop_reason, terminal_check, listed, triaged, unfinished, never_listed`.

**How the agent is started:** one `claude_agent_sdk.query` per batch, with:
- the system prompt `TRIAGE_PROMPT` and the user prompt `Run <id>. Triage every new item from ofsi, fincen and ofac.`;
- `tools=[]` (so `--tools ""`), `setting_sources=[]`, `strict_mcp_config=True`;
- one stdio MCP server, `mcp_server/feeds_server.py`, whose environment is the run's identity and nothing else.

**Tool allowlist:**
- `allowed_tools` pre-approves `feeds_read_page` only;
- `feeds_list_new`, `feeds_fetch` and `feeds_triage` reach the permission callback, which allows exactly those three;
- everything else is denied and recorded.

**Telemetry:** slice 1's, unchanged:
- `RUN_STARTED` lists `AGENT_TOOLS`;
- the Post hooks and the callback leave one terminal event per tool call;
- `RUN_COMPLETED` carries `terminal_check`, the `limit` hit if any, and the unfinished keys.

**Budget:** US$1.50 and 80 turns per session. A session triages at most 10 items (the tool's cap).

- [ ] **Step 1: Generalise the permission callback, keeping its defaults**

In `agents/permissions.py`:

**Edit 1 of 5.** Replace:

```python

# The exact start of the SDK's advisory when these four are pre-approved.
```

with:

```python

# Slice 2 B: the feeds orchestrator (agents/orchestrate_feeds.py), declared HERE because this is the
# one place a tool that changes anything may be permitted. Triage-only mode: read_page is the only
# read, pre-approved; list, fetch and triage each write into the run's inbox and reach the callback.
# feeds_extract joins the allowlist in sub-project C, not before -- a triage-only run cannot extract.
FEEDS_SERVER_KEY = "feeds"
FEEDS_READ_ONLY_TOOLS = ("mcp__%s__feeds_read_page" % FEEDS_SERVER_KEY,)
FEEDS_WRITE_ALLOWLIST = frozenset("mcp__%s__%s" % (FEEDS_SERVER_KEY, t)
                                  for t in ("feeds_list_new", "feeds_fetch", "feeds_triage"))

# The exact start of the SDK's advisory when these four are pre-approved.
```

**Edit 2 of 5.** Replace:

```python

def permission_callback(run):
    """The can_use_tool callback for one run."""

```

with:

```python

def permission_callback(run, allowlist=None, may="propose links"):
    """The can_use_tool callback for one run.

    `allowlist` defaults to WRITE_ALLOWLIST, read at CALL time (a guard swaps the module global);
    the feeds orchestrator passes FEEDS_WRITE_ALLOWLIST. `may` completes the denial message.
    """

```

**Edit 3 of 5.** Replace:

```python
        tool_use_id = getattr(context, "tool_use_id", None)
        if tool_name in WRITE_ALLOWLIST and all(run.env().values()):
            telemetry.emit(run, telemetry.PERMISSION_ALLOWED, telemetry.ALLOWED,
```

with:

```python
        tool_use_id = getattr(context, "tool_use_id", None)
        allowed = WRITE_ALLOWLIST if allowlist is None else allowlist
        if tool_name in allowed and all(run.env().values()):
            telemetry.emit(run, telemetry.PERMISSION_ALLOWED, telemetry.ALLOWED,
```

**Edit 4 of 5.** Replace:

```python
            return PermissionResultAllow()
        reason = ("%s is not on the write allowlist" % tool_name if tool_name not in WRITE_ALLOWLIST
                  else "the run identity is incomplete")
        _record_denial(run, tool_name, tool_use_id, reason)
        return PermissionResultDeny(message="Denied: %s. This agent may only propose links; "
                                            "it writes nothing else." % reason)

```

with:

```python
            return PermissionResultAllow()
        reason = ("%s is not on the write allowlist" % tool_name if tool_name not in allowed
                  else "the run identity is incomplete")
        _record_denial(run, tool_name, tool_use_id, reason)
        return PermissionResultDeny(message="Denied: %s. This agent may only %s; "
                                            "it writes nothing else." % (reason, may))

```

**Edit 5 of 5.** Replace:

```python
@contextlib.contextmanager
def expected_shadowing():
    """Silence ONLY the SDK advisory naming exactly the four read-only tools.

    They are pre-approved on purpose, so the advisory is expected on every run.
    Any other shadowing -- a different tool pre-approved -- still warns.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning,
                                message=re.escape(SHADOWING_MESSAGE))
        yield
```

with:

```python
@contextlib.contextmanager
def expected_shadowing(read_only=None):
    """Silence ONLY the SDK advisory naming exactly the pre-approved read-only tools.

    They are pre-approved on purpose, so the advisory is expected on every run.
    Any other shadowing -- a different tool pre-approved -- still warns. `read_only`
    defaults to the four Knowledge Centre reads; the feeds orchestrator passes its own.
    """
    message = SHADOWING_MESSAGE if read_only is None else \
        "can_use_tool will not be invoked for: %s." % ", ".join(read_only)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning,
                                message=re.escape(message))
        yield
```

Run:

```bash
.venv/bin/python evals/check_telemetry.py
.venv/bin/python evals/check_tool_surface.py
for m in refusal allowlist terminal; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-t$m .venv/bin/python evals/check_telemetry.py --mutate $m | tail -1; done
```

Expected: both `HELD (0 failures)`, and all three mutations still detected.
- The `allowlist` mutation swaps `permissions.WRITE_ALLOWLIST` after import.
- The callback reads it at call time for that reason: `allowed = WRITE_ALLOWLIST if allowlist is None else allowlist` inside the inner function, not at creation.

- [ ] **Step 2: Write the guard**

Create `evals/check_feeds_orchestrator.py`:

```python
"""
Prove the triage-only orchestrator can reach the four feeds tools and nothing else (slice 2 B).

Usage:
    python evals/check_feeds_orchestrator.py
    python evals/check_feeds_orchestrator.py --mutate builtin-tools     # the base tool set is not removed
    python evals/check_feeds_orchestrator.py --mutate settings          # the operator's settings are inherited
    python evals/check_feeds_orchestrator.py --mutate preapprove-triage # feeds_triage bypasses the callback
    python evals/check_feeds_orchestrator.py --mutate allow-propose     # the callback allows propose_link
    python evals/check_feeds_orchestrator.py --mutate extract-tool      # an extraction tool reaches triage-only mode
    python evals/check_feeds_orchestrator.py --mutate no-asymmetry      # the prompt loses "when in doubt, keep it"

WHAT IT HOLDS (spec sections 1 and 4; the same questions evals/check_tool_surface.py asks of the
extraction agent, asked of this one):
  no built-ins   tools=[] and the argv carries --tools "", setting_sources=[], strict_mcp_config;
  one server     the feeds server only, started with the run's identity and nothing the agent chose;
  reads only     allowed_tools pre-approves exactly feeds_read_page, in options and in the argv, with no
  pre-approved   permission mode or skip flag, so every tool that writes reaches the callback;
  the callback   ALLOWS list_new, fetch and triage; DENIES propose_link, an extraction tool and Bash;
  the lists      AGENT_TOOLS is exactly the server's tools, split exactly into the write allowlist and
                 the read-only tools, and the read-only annotation agrees -- a tool added to the server
                 is added to these lists or this guard fails;
  identity       FeedsRun refuses a malformed run id, a half-set eval mode and a batch over the cap;
  telemetry      the Post hooks are installed; the SDK's shadowing advisory names only feeds_read_page
                 and expected_shadowing() silences that one and no other;
  the prompt     states the spec's asymmetry ("When in doubt, keep it") and PROMPT_SHA256 is its hash.

STATIC. No model, no network: the options object, the argv the SDK would build, and the installed
callback asked directly. Each --mutate changes the options or a module constant in memory.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from agents import telemetry  # noqa: E402

telemetry.TELEMETRY_DIR = Path(tempfile.mkdtemp(prefix="fc08_orchestrator_telemetry_"))  # never data/telemetry/
from agents import orchestrate_feeds as of  # noqa: E402
from agents.permissions import FEEDS_READ_ONLY_TOOLS, PROPOSE_TOOL, expected_shadowing  # noqa: E402
from check_tool_surface import built_command  # noqa: E402

MUTATIONS = ("builtin-tools", "settings", "preapprove-triage", "allow-propose", "extract-tool", "no-asymmetry")
RUN = of.FeedsRun("feeds-2026-10-02-fff555")
EVAL_RUN = of.FeedsRun("feeds-2026-10-02-fff666", catalogue=ROOT / "evals" / "feeds" / "catalogue.json",
                       batch=("ofsi:0123456789abcdef",))
TRIAGE = "mcp__feeds__feeds_triage"


def checks(mutation) -> list:
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    from claude_agent_sdk import types as sdk_types
    from claude_agent_sdk.types import ToolPermissionContext
    from mcp_server import feeds_server

    if mutation == "allow-propose":
        of.FEEDS_WRITE_ALLOWLIST = of.FEEDS_WRITE_ALLOWLIST | {PROPOSE_TOOL}
    if mutation == "extract-tool":
        of.AGENT_TOOLS = of.AGENT_TOOLS + ("mcp__feeds__feeds_extract",)
    if mutation == "no-asymmetry":
        of.TRIAGE_PROMPT = of.TRIAGE_PROMPT.replace("When in doubt, keep it", "When in doubt, drop it")
    o = of.agent_options(RUN)
    if mutation == "builtin-tools":
        o = dataclasses.replace(o, tools=None)
    if mutation == "settings":
        o = dataclasses.replace(o, setting_sources=["user", "project"])
    if mutation == "preapprove-triage":
        o = dataclasses.replace(o, allowed_tools=list(o.allowed_tools) + [TRIAGE])

    out = []
    cmd = built_command(o)
    pairs = list(zip(cmd, cmd[1:]))
    out.append((o.tools == [] and ("--tools", "") in pairs, 'tools=[] and the argv carries --tools ""',
                "tools=%r" % (o.tools,)))
    out.append((o.setting_sources == [] and o.strict_mcp_config is True,
                "setting_sources=[] and strict_mcp_config: nothing inherited from the machine",
                "setting_sources=%r" % (o.setting_sources,)))
    server = o.mcp_servers.get("feeds", {})
    out.append((list(o.mcp_servers) == ["feeds"] and server.get("args") == [str(of.SERVER_PATH)]
                and server.get("env") == {"FEEDS_RUN_ID": RUN.run_id},
                "one MCP server, the feeds server, started with the run's identity only", sorted(server.get("env", {}))))
    allowed_arg = cmd[cmd.index("--allowedTools") + 1] if "--allowedTools" in cmd else ""
    out.append((list(o.allowed_tools) == list(FEEDS_READ_ONLY_TOOLS) and allowed_arg.split(",") == list(FEEDS_READ_ONLY_TOOLS)
                and "--permission-mode" not in cmd and "--dangerously-skip-permissions" not in cmd
                and o.permission_prompt_tool_name is None and o.output_format is None,
                "only feeds_read_page is pre-approved, in options and argv, and nothing bypasses the callback",
                "--allowedTools %s" % allowed_arg))

    ctx = ToolPermissionContext(tool_use_id="static")
    ask = lambda name: asyncio.run(o.can_use_tool(name, {}, ctx))  # noqa: E731
    allows = {t: isinstance(ask("mcp__feeds__%s" % t), PermissionResultAllow)
              for t in ("feeds_list_new", "feeds_fetch", "feeds_triage")}
    denies = {t: isinstance(ask(t), PermissionResultDeny)
              for t in (PROPOSE_TOOL, "mcp__feeds__feeds_extract", "Bash")}
    out.append((all(allows.values()) and all(denies.values()),
                "the installed callback allows list, fetch and triage, and denies propose_link, extract and Bash",
                "allows %s; denies %s" % (allows, denies)))

    listed = asyncio.run(feeds_server.mcp.list_tools())
    names = sorted("mcp__feeds__%s" % t.name for t in listed)
    ro = sorted("mcp__feeds__%s" % t.name for t in listed
                if t.annotations is not None and getattr(t.annotations, "read_only_hint", False))
    out.append((sorted(of.AGENT_TOOLS) == names
                and set(of.FEEDS_WRITE_ALLOWLIST) | set(FEEDS_READ_ONLY_TOOLS) == set(names)
                and not set(of.FEEDS_WRITE_ALLOWLIST) & set(FEEDS_READ_ONLY_TOOLS) and ro == list(FEEDS_READ_ONLY_TOOLS),
                "AGENT_TOOLS is exactly the server's tools, split into the write allowlist and the read-only tools",
                names))

    refused = []
    for kwargs in ({"run_id": "not-a-run"}, {"run_id": RUN.run_id, "batch": ("ofsi:0123456789abcdef",)},
                   {"run_id": RUN.run_id, "catalogue": Path("c.json"),
                    "batch": tuple("ofsi:%016x" % i for i in range(11))}):
        try:
            of.FeedsRun(**kwargs)
        except ValueError:
            refused.append(True)
    env = EVAL_RUN.env()
    out.append((len(refused) == 3 and env["FEEDS_CATALOGUE_BATCH"] == "ofsi:0123456789abcdef"
                and Path(env["FEEDS_CATALOGUE"]).is_absolute(),
                "FeedsRun refuses a bad run id, a half-set eval mode and a batch over the cap of 10", sorted(env)))

    out.append((sorted(o.hooks or {}) == ["PostToolUse", "PostToolUseFailure"],
                "the Post hooks are installed for telemetry", str(sorted(o.hooks or {}))))
    msg = sdk_types._get_can_use_tool_shadowed_warning(o.permission_mode, list(o.allowed_tools)) or ""
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with expected_shadowing(FEEDS_READ_ONLY_TOOLS):
            warnings.warn(msg, sdk_types.CanUseToolShadowedWarning)
            warnings.warn("can_use_tool will not be invoked for: %s. x" % TRIAGE, sdk_types.CanUseToolShadowedWarning)
    out.append((msg.startswith("can_use_tool will not be invoked for: %s." % FEEDS_READ_ONLY_TOOLS[0])
                and len(seen) == 1 and TRIAGE in str(seen[0].message),
                "the shadowing advisory names only feeds_read_page, and only that advisory is silenced", msg[:70]))

    out.append(("When in doubt, keep it" in o.system_prompt
                and hashlib.sha256(of.TRIAGE_PROMPT.encode("utf-8")).hexdigest() == of.PROMPT_SHA256
                and "extract" not in o.system_prompt.replace("You do not extract", "").replace("worth extracting", ""),
                "the prompt states the asymmetry, offers no extraction, and PROMPT_SHA256 is its hash",
                of.PROMPT_SHA256[:16]))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Prove the triage-only orchestrator's tool surface")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule in memory; a check MUST fail")
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
```

- [ ] **Step 3: Write the orchestrator**

Create `agents/orchestrate_feeds.py`:

```python
"""
The feeds orchestrator, TRIAGE-ONLY mode (slice 2 sub-project B; spec sections 1 and 4).

One session is one orchestrating agent whose tools carry the invariants. In triage-only mode it has
four tools from mcp_server/feeds_server.py and nothing else:
  feeds_list_new, feeds_fetch   see and pin new items (sub-project A)
  feeds_read_page               read a pinned document's pages (B; the only read, pre-approved)
  feeds_triage                  one verdict per item, the quote found in the pinned document (B)
There is no extraction tool, no Knowledge Centre, and no built-in tool: `tools=[]` emits
`--tools ""`, `setting_sources=[]` ignores the operator's settings and hooks, `strict_mcp_config`
loads only the server passed here, and every tool that writes reaches agents/permissions.py's
callback, which allows FEEDS_WRITE_ALLOWLIST only. Guarded by evals/check_feeds_orchestrator.py.

Telemetry is slice 1's, unchanged: RUN_STARTED names the tools, the Post hooks and the callback leave
one terminal event per tool call, and RUN_COMPLETED carries telemetry.reconcile() as terminal_check.
After the agent stops, IN CODE, feeds.triage.reconcile() lists every listed or expected item without
a verdict as unfinished: whatever the agent skipped is reported, never read as success.

Sub-project B runs this only on the back-catalogue (evals/run_feeds_triage.py passes a catalogue and
a batch). The live Friday run, extraction, the budget ceiling across a run and the report are
sub-project C, which extends this module.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage, ClaudeAgentOptions, ResultError, ResultMessage, ToolUseBlock, query,
)

from agents import telemetry  # noqa: E402
from agents.permissions import (  # noqa: E402
    FEEDS_READ_ONLY_TOOLS, FEEDS_SERVER_KEY, FEEDS_WRITE_ALLOWLIST, expected_shadowing, permission_callback,
)
from feeds import inbox, triage as feeds_triage  # noqa: E402

SERVER_PATH = ROOT / "mcp_server" / "feeds_server.py"
TRIAGE_TOOLS = ("feeds_list_new", "feeds_fetch", "feeds_read_page", "feeds_triage")
AGENT_TOOLS = tuple("mcp__%s__%s" % (FEEDS_SERVER_KEY, t) for t in TRIAGE_TOOLS)
MODEL = "claude-sonnet-5"
# Per session. A session triages at most feeds.triage.MAX_PER_RUN (10) items.
MAX_BUDGET_USD = 1.50
MAX_TURNS = 80
# A session stopped by its own turn or budget cap COMPLETED: what it left is unfinished, and measured.
# Anything else that ends a run in error (auth, credit, the CLI) is a failure, and the batch is re-run.
LIMIT_SUBTYPES = ("error_max_turns", "error_max_budget_usd")

TRIAGE_PROMPT = """You are the triage stage of a financial-crime threat-intelligence desk's weekly feed run.
For each new publication you decide one thing: is it worth extracting? You do not extract.

Relevant: the publication describes methods, red flags or cases of financial crime that a typology could hold -- a money-laundering, fraud, sanctions-evasion, terrorist-financing, proliferation-financing or corruption technique; indicators an analyst could screen for; or an enforcement, penalty or settlement case that says what was done.
Not relevant: a bare designation or delisting list, a licence or general licence, a notice of a regulatory, procedural or website change, an event listing, or guidance that restates obligations without describing a method, red flag or case.
When in doubt, keep it: mark it relevant. A relevant publication missed here is lost to the desk; an irrelevant one kept costs a reviewer a minute.

How to work:
1. Call feeds_list_new once each for ofsi, fincen and ofac.
2. For every item listed, call feeds_fetch, then read the document with feeds_read_page. Start at page 1 and read on while the question is not settled.
3. Call feeds_triage exactly once per item: verdict relevant or not_relevant; a reason of at most 300 characters; one verbatim quote, copied from the pages feeds_read_page returned, that supports the verdict.
4. Triage every item. If an item cannot be fetched or read, do not guess a verdict: say so in your final message.
5. Finish with one line per item: key, verdict.

Tool replies that start "Rejected:" are refusals; read the reason and correct the call (a quote the tool cannot find must be copied again, exactly). You only ever pass keys the tools gave you, never a URL."""

PROMPT_SHA256 = hashlib.sha256(TRIAGE_PROMPT.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeedsRun:
    """Who a feeds session is, told to the MCP server by the runner, never by the agent."""

    run_id: str
    catalogue: Optional[Path] = None   # eval mode: evals/feeds/catalogue.json
    batch: Tuple[str, ...] = ()        # eval mode: the keys this session triages
    stage: str = "orchestrator"
    advisory_id: Optional[str] = None  # telemetry's payload field; a feeds session spans many items
    pdf_sha256: Optional[str] = None   # likewise: each document is pinned in the inbox, not here

    def __post_init__(self) -> None:
        if not inbox.RUN_ID.fullmatch(self.run_id):
            raise ValueError("run id %r is not feeds-YYYY-MM-DD-xxxxxx" % self.run_id)
        if (self.catalogue is None) != (not self.batch):
            raise ValueError("eval mode needs both a catalogue and a batch, and live mode neither")
        if len(self.batch) > feeds_triage.MAX_PER_RUN:
            raise ValueError("a session triages at most %d items; the batch has %d" % (feeds_triage.MAX_PER_RUN,
                                                                                        len(self.batch)))

    def env(self) -> dict:
        env = {"FEEDS_RUN_ID": self.run_id}
        if self.catalogue is not None:
            env.update(FEEDS_CATALOGUE=str(Path(self.catalogue).resolve()), FEEDS_CATALOGUE_BATCH=",".join(self.batch))
        return env


def agent_options(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                  max_turns: int = MAX_TURNS) -> ClaudeAgentOptions:
    """The triage agent's whole capability surface, in one place a guard can read."""
    return ClaudeAgentOptions(
        system_prompt=TRIAGE_PROMPT,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        mcp_servers={FEEDS_SERVER_KEY: {"type": "stdio", "command": sys.executable, "args": [str(SERVER_PATH)],
                                        "env": run.env()}},
        strict_mcp_config=True,
        tools=[],
        setting_sources=[],
        allowed_tools=list(FEEDS_READ_ONLY_TOOLS),
        can_use_tool=permission_callback(run, allowlist=FEEDS_WRITE_ALLOWLIST, may="list, fetch, read and "
                                         "triage feed items"),
        hooks=telemetry.tool_hooks(run),
    )


def _prompt(run: FeedsRun) -> str:
    return "Run %s. Triage every new item from ofsi, fincen and ofac." % run.run_id


async def run_triage(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                     max_turns: int = MAX_TURNS, inbox_root: Path = inbox.INBOX_ROOT) -> dict:
    """One triage-only session. Returns its summary; never raises for an agent-side failure, which
    is recorded (`failure`) so the caller decides. The summary is what a repeat record keeps."""
    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS)
    tool_calls: Counter = Counter()
    tool_use_ids: list = []
    result: Optional[ResultMessage] = None
    failure: Optional[str] = None
    limit: Optional[str] = None
    try:
        with expected_shadowing(FEEDS_READ_ONLY_TOOLS):
            async for message in query(prompt=_prompt(run), options=agent_options(run, model, max_budget_usd,
                                                                                  max_turns)):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls[block.name] += 1
                            tool_use_ids.append(block.id)
                elif isinstance(message, ResultMessage):
                    result = message
                    if message.is_error and message.subtype in LIMIT_SUBTYPES:
                        limit = message.subtype
                    elif message.is_error:
                        # Recorded, not raised inside the loop (see agents/extract_advisory.py).
                        failure = "agent run failed: %s" % (message.errors or message.result)
    except ResultError as exc:  # the CLI exits non-zero after an error result; the SDK raises this
        if exc.subtype in LIMIT_SUBTYPES:
            limit = exc.subtype
        else:
            failure = failure or "%s: %s" % (type(exc).__name__, exc)
    except Exception as exc:  # the SDK raises its own errors (auth, credit) from inside the loop
        failure = "%s: %s" % (type(exc).__name__, exc)
    terminal_check = telemetry.reconcile(run, tool_use_ids)
    items = feeds_triage.reconcile(run.run_id, run.batch, inbox_root)
    telemetry.run_completed(run, telemetry.FAILURE if failure else telemetry.SUCCESS,
                            (failure or limit or "triage session ended")[:300], result=result,
                            validated=failure is None, terminal_check=terminal_check, limit=limit,
                            unfinished=items["unfinished"])
    return {"run_id": run.run_id, "failure": failure, "limit": limit, "tool_calls": dict(tool_calls),
            "turns": getattr(result, "num_turns", None), "cost_usd": getattr(result, "total_cost_usd", None),
            "duration_ms": getattr(result, "duration_ms", None), "stop_reason": getattr(result, "stop_reason", None),
            "terminal_check": terminal_check, "listed": items["listed"], "triaged": items["triaged"],
            "unfinished": items["unfinished"], "never_listed": items["never_listed"]}
```

- [ ] **Step 4: Run the guard and every mutation**

```bash
.venv/bin/python evals/check_feeds_orchestrator.py
for m in builtin-tools settings preapprove-triage allow-propose extract-tool no-asymmetry; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_orchestrator.py --mutate $m | tail -1; done
```

Expected (measured):
- 10 PASS lines, `HELD (0 failures)`.
- Mutations: builtin-tools 1, settings 1, preapprove-triage 2, allow-propose 2, extract-tool 1, no-asymmetry 1.
- A line `Using bundled Claude Code CLI: …` on stderr is the SDK locating its CLI to build the argv. No session is started.

Also measured in scratch, with the model replaced by a fake `query`:
- `error_max_turns` and `error_max_budget_usd` results end with `failure=None` and `limit` set;
- `error_during_execution` ends with `failure` set;
- `success` ends with neither.

- [ ] **Step 5: Register and commit**

In `tools/check_all.py`:

Replace:

```python
    ("check_feeds_catalogue", ["evals/check_feeds_catalogue.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

with:

```python
    ("check_feeds_catalogue", ["evals/check_feeds_catalogue.py"], "cold"),
    ("check_feeds_orchestrator", ["evals/check_feeds_orchestrator.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add agents/permissions.py agents/orchestrate_feeds.py evals/check_feeds_orchestrator.py tools/check_all.py
git commit -m "Slice 2 B: the triage-only orchestrator -- four feeds tools, no built-ins, the write allowlist in permissions.py"
```

---

### Task 5: the scorer, before any data

**Files:**
- Create: `evals/score_feeds_triage.py`, `evals/check_feeds_score.py`
- Modify: `tools/check_all.py`

**Interfaces:**
- Consumes: `feeds.triage.RELEVANT`, `NOT_RELEVANT`, `VERDICTS`.
- Produces, for Tasks 9 and 10:
  - `disputed(draft, runs)`, `spot_sample(agreed, n)`;
  - `disputes_doc(catalogue, labels, repeats, spot_check)`;
  - `final_labels(labels, disputes, decisions)`, `score_one(verdicts, labels, keys)`, `band(values)`;
  - `build(catalogue, labels, disputes, decisions, repeats, decision_files)`, `render(obj)`, `load_inputs()`;
  - the CLI `--write-disputes [--spot-check N]`, `--check-disputes`, `--write`, `--check`.

Written now, while there is nothing to score, so the scoring rule is fixed before any repeat exists (CLAUDE.md rule 5: evaluate before improving).

- [ ] **Step 1: Write the guard first**

Create `evals/check_feeds_score.py`:

```python
"""
Pin the triage scorer (evals/score_feeds_triage.py): recall first, precision beside it, a band over repeats.

Usage:
    python evals/check_feeds_score.py
    python evals/check_feeds_score.py --mutate missing-excluded    # an unfinished relevant item leaves the denominator
    python evals/check_feeds_score.py --mutate swap                # recall and precision swapped
    python evals/check_feeds_score.py --mutate band-first          # the band is one repeat, not three
    python evals/check_feeds_score.py --mutate zero-as-one         # recall over no relevant items reads 1.0
    python evals/check_feeds_score.py --mutate draft-labels        # the owner's decisions are ignored
    python evals/check_feeds_score.py --mutate majority-dispute    # a dispute needs 2 of 3 repeats to disagree
    python evals/check_feeds_score.py --mutate unfinished-dispute  # a missing verdict counts as a dispute
    python evals/check_feeds_score.py --mutate decide-anything     # a decision on an undisputed item is accepted
    python evals/check_feeds_score.py --mutate spot-any-agreed     # the spot check samples agreed relevant items too

WHAT IT HOLDS, on a synthetic set whose every figure was computed by hand (ten items, three sources,
three repeats, four disputes, four owner decisions):
  the counts    tp, fn, fp, tn and the unfinished list of one repeat, and its recall and precision;
  unfinished    a relevant item with no verdict is a miss: it stays in recall's denominator;
  the band      min, max and mean over all three repeats, for recall and for precision;
  n/a           a ratio over an empty denominator is null, never 0 or 1;
  disputes      an item is disputed when ANY repeat's verdict differs from the draft, one of three is
                enough, and an item with no verdict is not disputed;
  decisions     the owner's decision replaces the draft; a decision on an undisputed item, a second
                decision, and an undecided dispute are each refused;
  spot check    the sample is drawn by hash, re-derivably, only from items the draft and every repeat
                called not_relevant (where an agreed error would cost recall), and must then be decided;
  determinism   the same inputs give the same bytes, whatever order the repeats arrive in.

COLD. No repeat, label or catalogue file is read: every input is built below.

NOT A VACUOUS PASS. Each --mutate rewrites the scorer's SOURCE in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCORER = ROOT / "evals" / "score_feeds_triage.py"
R, N = "relevant", "not_relevant"

MUTATIONS = {
    "missing-excluded": ("    rel = {k for k in keys if labels[k] == RELEVANT}\n",
                         "    rel = {k for k in keys if labels[k] == RELEVANT and k in verdicts}\n"),
    "swap": ('            "recall": _ratio(tp, len(rel)), "precision": _ratio(tp, len(kept))}',
             '            "recall": _ratio(tp, len(kept)), "precision": _ratio(tp, len(rel))}'),
    "band-first": ('    return {"min": min(got), "max": max(got),', '    return {"min": got[0], "max": got[0],'),
    "zero-as-one": ("    return round(num / den, 3) if den else None\n", "    return round(num / den, 3) if den else 1.0\n"),
    "draft-labels": ('    out.update({k: d["decision"] for k, d in decided.items()})\n', "    pass\n"),
    "majority-dispute": ("    return sorted(k for k in draft if any(k in r and r[k] != draft[k] for r in runs))\n",
                         "    return sorted(k for k in draft if sum(k in r and r[k] != draft[k] for r in runs) * 2 "
                         "> len(runs))\n"),
    "unfinished-dispute": ("    return sorted(k for k in draft if any(k in r and r[k] != draft[k] for r in runs))\n",
                           "    return sorted(k for k in draft if any(r.get(k) != draft[k] for r in runs))\n"),
    "decide-anything": ('        if d["key"] not in asked or d.get("kind") != asked[d["key"]]:\n', "        if False:\n"),
    "spot-any-agreed": ('    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT)\n',
                        '    agreed_not_relevant = sorted(k for k in draft if k not in keys)\n'),
}


def load_scorer(mutation) -> types.ModuleType:
    source = SCORER.read_text(encoding="utf-8")
    if mutation:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, SCORER))
        source = source.replace(old, new)
    module = types.ModuleType("score_feeds_triage_under_test")
    module.__file__ = str(SCORER)
    exec(compile(source, str(SCORER), "exec"), module.__dict__)
    return module


# Ten items: o = ofsi, f = fincen, a = ofac.
KEYS = ["o1", "o2", "o3", "o4", "f1", "f2", "f3", "a1", "a2", "a3"]
DRAFT = dict(zip(KEYS, [R, N, N, R, R, R, R, N, N, R]))
REP = {
    "rep1": dict(zip(KEYS, [R, N, R, N, R, R, R, N, N, R])),                  # o3 kept, o4 missed
    "rep2": {k: v for k, v in zip(KEYS, [R, N, N, R, R, R, None, R, R, R]) if v},  # f3 unfinished; a1, a2 kept
    "rep3": dict(DRAFT),                                                        # agrees with the draft
}
DECISIONS = [{"key": "o3", "kind": "dispute", "decision": R}, {"key": "o4", "kind": "dispute", "decision": R},
             {"key": "a1", "kind": "dispute", "decision": N}, {"key": "a2", "kind": "dispute", "decision": N}]


def fixtures():
    catalogue = {"items": [{"key": k, "source": {"o": "ofsi", "f": "fincen", "a": "ofac"}[k[0]], "title": k,
                            "url": "https://x/%s" % k, "published": "2026-09-01"} for k in KEYS]}
    labels = {"labels": {k: {"label": v, "reason": "draft"} for k, v in DRAFT.items()}}
    repeats = {r: {"verdicts": {k: {"verdict": v} for k, v in vs.items()},
                   "sessions": [{"terminal_check": {"calls": 3, "unterminated": [], "duplicated": []},
                                 "cost_usd": 0.5}]} for r, vs in REP.items()}
    return catalogue, labels, repeats


def checks(sc) -> list:
    out = []
    catalogue, labels, repeats = fixtures()
    disputes = sc.disputes_doc(catalogue, labels, repeats)

    def attempt(fn):
        try:
            return fn(), None
        except Exception as exc:  # a mutation that raises must not stop the guard
            return None, "%s: %s" % (type(exc).__name__, exc)

    keys = sorted(c["key"] for c in disputes["cards"])
    out.append((keys == ["a1", "a2", "o3", "o4"],
                "disputed: every item where ANY repeat's verdict differs from the draft; f3, with no verdict, is not",
                keys))

    score, err = attempt(lambda: sc.build(catalogue, labels, disputes, DECISIONS, repeats))
    ov = (score or {}).get("overall", {})
    rep2 = ov.get("per_repeat", {}).get("rep2", {})
    out.append((err is None and {k: rep2.get(k) for k in ("tp", "fn", "fp", "tn")} == {"tp": 5, "fn": 2, "fp": 2, "tn": 1}
                and rep2.get("unfinished") == ["f3"] and rep2.get("recall") == 0.714 and rep2.get("precision") == 0.714,
                "rep2's counts by hand: tp 5, fn 2 (o3, and unfinished f3), fp 2, tn 1; recall 0.714, precision 0.714",
                err or {k: rep2.get(k) for k in ("tp", "fn", "fp", "tn", "recall", "precision")}))
    rep1 = ov.get("per_repeat", {}).get("rep1", {})
    out.append((rep1.get("recall") == 0.857 and rep1.get("precision") == 1.0,
                "rep1: recall 0.857 (6 of 7 relevant kept), precision 1.0 (6 of 6 kept relevant)",
                {k: rep1.get(k) for k in ("recall", "precision")}))
    out.append((rep2.get("relevant") == 7, "an unfinished relevant item stays in recall's denominator (7, not 6)",
                rep2.get("relevant")))
    out.append((ov.get("recall") == {"min": 0.714, "max": 0.857, "mean": 0.809, "n": 3}
                and ov.get("precision") == {"min": 0.714, "max": 1.0, "mean": 0.905, "n": 3},
                "the band is min, max and mean over all three repeats", {"recall": ov.get("recall"),
                                                                         "precision": ov.get("precision")}))
    out.append(((score or {}).get("labels", {}).get("changed_by_owner") == ["o3"]
                and (score or {}).get("labels", {}).get("relevant") == 7,
                "the owner's decision replaces the draft: o3 becomes relevant, 7 relevant in all",
                (score or {}).get("labels")))
    per = (score or {}).get("per_source", {})
    sums = {k: sum(per.get(s, {}).get("per_repeat", {}).get("rep2", {}).get(k, 0) for s in ("ofsi", "fincen", "ofac"))
            for k in ("tp", "fn", "fp", "tn")}
    out.append((sums == {k: rep2.get(k) for k in ("tp", "fn", "fp", "tn")},
                "the three sources' counts sum to the overall counts", sums))
    out.append(((score or {}).get("false_negatives") == {"f3": ["rep2"], "o3": ["rep2", "rep3"], "o4": ["rep1"]},
                "every relevant item a repeat did not keep is listed with the repeats that missed it",
                (score or {}).get("false_negatives")))

    none_rel = sc.score_one({"x": N}, {"x": N}, ["x"])
    out.append((none_rel["recall"] is None and none_rel["precision"] is None,
                "recall over no relevant items, and precision over none kept, are null (n/a)", none_rel))

    refusals = []
    for bad in ([{"key": "o1", "kind": "dispute", "decision": R}] + DECISIONS,
                DECISIONS + [dict(DECISIONS[0])], DECISIONS[:3]):
        refusals.append(attempt(lambda: sc.final_labels(labels, disputes, bad))[1] is not None)
    out.append((refusals == [True, True, True],
                "a decision on an undisputed item, a second decision, and an undecided dispute are each refused",
                refusals))

    pool = ["k%02d" % i for i in range(20)]
    spot = sc.spot_sample(pool, 3)
    with_spot = sc.disputes_doc(catalogue, labels, repeats, spot_check=2)
    spot_cards = sorted(c["key"] for c in with_spot["cards"] if c["kind"] == "spot_check")
    need = attempt(lambda: sc.final_labels(labels, with_spot, DECISIONS))[1]
    out.append((len(spot) == 3 and set(spot) <= set(pool) and spot == sc.spot_sample(list(reversed(pool)), 3)
                and spot_cards == ["o2"] and need is not None,
                "the spot check samples by hash, re-derivably, only items all four called not_relevant (here o2 "
                "alone), and a sampled item must then be decided", {"pool sample": spot, "cards": spot_cards}))

    shuffled = {r: repeats[r] for r in ("rep3", "rep1", "rep2")}
    again, _ = attempt(lambda: sc.render(sc.build(catalogue, labels, disputes, DECISIONS, shuffled)))
    out.append((score is not None and again == sc.render(score), "the same inputs give the same bytes", ""))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage scorer")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    sc = load_scorer(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(sc):
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

- [ ] **Step 2: Write the scorer**

Create `evals/score_feeds_triage.py`:

```python
"""
Score the triage repeats against the labels: recall first, precision beside it, a band over the repeats.

Usage:
    python evals/score_feeds_triage.py                          # print the score; write nothing
    python evals/score_feeds_triage.py --write-disputes [--spot-check N]
                                                                # after the repeats: evals/feeds/disputes.json
    python evals/score_feeds_triage.py --check-disputes         # the committed disputes rebuild byte for byte
    python evals/score_feeds_triage.py --write                  # after the owner's decisions: evals/feeds/score.json
    python evals/score_feeds_triage.py --check                  # the committed score rebuilds byte for byte

THE LABEL of an item is Claude's draft (evals/feeds/labels.json, committed before the first repeat)
unless the owner decided it (evals/owner_decisions/feeds_triage_labels_*.json). The owner decides the
DISPUTES -- items where at least one repeat's verdict differs from the draft -- and the spot-check
sample, if disputes.json names one. The sample is drawn from the items the draft AND every repeat
called not_relevant: that is the only place an agreed error costs recall (a relevant publication all
four missed), and recall is the score that comes first. Every disputed or sampled item must be decided
exactly once, and nothing else may be: a decision on an item nobody disputed is refused. An item where
the draft and every repeat agree, and which was not sampled, is UNCHALLENGED, not confirmed.

THE SCORE, per repeat, over every scored catalogue item:
  kept       the items the repeat triaged relevant. An item with NO verdict is not kept: the run left
             it unfinished, and a relevant item left unfinished is a miss (spec section 1: whatever the
             agent skipped is reported as unfinished, never as success). Unfinished items are listed.
  recall     kept and relevant / relevant   -- first: a relevant publication missed is lost to the desk
  precision  kept and relevant / kept       -- beside it: an irrelevant one kept costs a reviewer a minute
  n/a        a ratio whose denominator is zero is null, never 0 or 1.
A band is the min, max and mean of a ratio over the repeats, overall and per source. Counts are exact
and ratios are rounded to 3 places; a band's mean is the mean of the three ratios as printed, so every
figure in score.json can be re-derived by hand from the counts beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.triage import NOT_RELEVANT, RELEVANT, VERDICTS  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
LABELS = EVAL_DIR / "labels.json"
REPEATS_DIR = EVAL_DIR / "repeats"
DISPUTES = EVAL_DIR / "disputes.json"
SCORE = EVAL_DIR / "score.json"
DECISIONS_DIR = ROOT / "evals" / "owner_decisions"
DECISIONS_GLOB = "feeds_triage_labels_*.json"
REPEATS = ("rep1", "rep2", "rep3")
SOURCES = ("ofsi", "fincen", "ofac")
SPOT_SEED = "fc08-slice2-triage-spot-check"


def render(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verdicts_of(repeat: dict) -> Dict[str, str]:
    return {k: v["verdict"] for k, v in repeat["verdicts"].items()}


def disputed(draft: Dict[str, str], runs: Sequence[Dict[str, str]]) -> List[str]:
    """Items where at least one repeat GAVE a verdict that differs from the draft. No verdict is no dispute."""
    return sorted(k for k in draft if any(k in r and r[k] != draft[k] for r in runs))


def spot_sample(agreed: Sequence[str], n: int, seed: str = SPOT_SEED) -> List[str]:
    """n agreed items, chosen by hash rather than by a random generator, so the sample re-derives."""
    ranked = sorted(agreed, key=lambda k: hashlib.sha256((seed + k).encode("utf-8")).hexdigest())
    return sorted(ranked[:n])


def disputes_doc(catalogue: dict, labels: dict, repeats: Dict[str, dict], spot_check: int = 0) -> dict:
    draft = {k: v["label"] for k, v in labels["labels"].items()}
    runs = [verdicts_of(repeats[r]) for r in REPEATS]
    keys = disputed(draft, runs)
    agreed_not_relevant = sorted(k for k in draft if k not in keys and draft[k] == NOT_RELEVANT)
    by_key = {it["key"]: it for it in catalogue["items"]}

    def card(k: str, kind: str) -> dict:
        it = by_key[k]
        return {"key": k, "kind": kind, "source": it["source"], "title": it["title"], "url": it["url"],
                "published": it["published"], "draft": labels["labels"][k],
                "repeats": {r: repeats[r]["verdicts"].get(k) for r in REPEATS}}

    return {"schema": "fc08-triage-disputes/1", "labels_sha256": hashlib.sha256(render(labels).encode()).hexdigest(),
            "repeats": list(REPEATS), "spot_check": {"n": spot_check, "seed": SPOT_SEED},
            "cards": [card(k, "dispute") for k in keys] + [card(k, "spot_check")
                                                          for k in spot_sample(agreed_not_relevant, spot_check)]}


def final_labels(labels: dict, disputes: dict, decisions: Sequence[dict]) -> Dict[str, str]:
    """The draft, overridden by the owner's decision on each disputed or sampled item. Raises ValueError."""
    out = {k: v["label"] for k, v in labels["labels"].items()}
    asked = {c["key"]: c["kind"] for c in disputes["cards"]}
    decided: Dict[str, dict] = {}
    for d in decisions:
        if d["key"] not in asked or d.get("kind") != asked[d["key"]]:
            raise ValueError("%s was not put to the owner as a %s" % (d["key"], d.get("kind")))
        if d["key"] in decided:
            raise ValueError("%s is decided twice" % d["key"])
        if d["decision"] not in VERDICTS:
            raise ValueError("%s: decision %r is not one of %s" % (d["key"], d["decision"], VERDICTS))
        decided[d["key"]] = d
    undecided = sorted(set(asked) - set(decided))
    if undecided:
        raise ValueError("undecided: %s" % ", ".join(undecided))
    out.update({k: d["decision"] for k, d in decided.items()})
    return out


def _ratio(num: int, den: int) -> Optional[float]:
    return round(num / den, 3) if den else None


def score_one(verdicts: Dict[str, str], labels: Dict[str, str], keys: Sequence[str]) -> dict:
    kept = {k for k in keys if verdicts.get(k) == RELEVANT}
    rel = {k for k in keys if labels[k] == RELEVANT}
    tp, fn, fp = len(kept & rel), len(rel - kept), len(kept - rel)
    return {"items": len(keys), "relevant": len(rel), "kept": len(kept), "tp": tp, "fn": fn, "fp": fp,
            "tn": len(keys) - tp - fn - fp, "unfinished": sorted(k for k in keys if k not in verdicts),
            "recall": _ratio(tp, len(rel)), "precision": _ratio(tp, len(kept))}


def band(values: Sequence[Optional[float]]) -> Optional[dict]:
    got = [v for v in values if v is not None]
    if not got:
        return None
    return {"min": min(got), "max": max(got), "mean": round(sum(got) / len(got), 3), "n": len(got)}


def build(catalogue: dict, labels: dict, disputes: dict, decisions: Sequence[dict], repeats: Dict[str, dict],
          decision_files: Sequence[str] = ()) -> dict:
    final = final_labels(labels, disputes, decisions)
    keys = sorted(it["key"] for it in catalogue["items"])
    src = {it["key"]: it["source"] for it in catalogue["items"]}
    runs = {r: verdicts_of(repeats[r]) for r in REPEATS}

    def section(ks: List[str]) -> dict:
        per = {r: score_one(runs[r], final, ks) for r in REPEATS}
        return {"per_repeat": per, "recall": band([per[r]["recall"] for r in REPEATS]),
                "precision": band([per[r]["precision"] for r in REPEATS])}

    sessions = [s for r in REPEATS for s in repeats[r]["sessions"]]
    return {
        "schema": "fc08-triage-score/1",
        "inputs": {"catalogue_sha256": hashlib.sha256(render(catalogue).encode()).hexdigest(),
                   "labels_sha256": hashlib.sha256(render(labels).encode()).hexdigest(),
                   "decision_files": sorted(decision_files), "repeats": list(REPEATS)},
        "labels": {"items": len(keys), "relevant": sum(1 for k in keys if final[k] == RELEVANT),
                   "not_relevant": sum(1 for k in keys if final[k] == NOT_RELEVANT),
                   "owner_decided": len(decisions), "unchallenged": len(keys) - len(disputes["cards"]),
                   "changed_by_owner": sorted(d["key"] for d in decisions
                                              if d["decision"] != labels["labels"][d["key"]]["label"])},
        "overall": section(keys),
        "per_source": {s: section([k for k in keys if src[k] == s]) for s in SOURCES},
        "false_negatives": {k: [r for r in REPEATS if runs[r].get(k) != RELEVANT]
                            for k in keys if final[k] == RELEVANT and any(runs[r].get(k) != RELEVANT for r in REPEATS)},
        "unanimous": sum(1 for k in keys if len({runs[r].get(k) for r in REPEATS}) == 1),
        "sessions": {"count": len(sessions),
                     "terminal_check_clean": sum(1 for s in sessions if not s["terminal_check"]["unterminated"]
                                                 and not s["terminal_check"]["duplicated"]),
                     "cost_usd": round(sum(s.get("cost_usd") or 0 for s in sessions), 2)},
    }


def load_inputs() -> tuple:
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731
    repeats = {r: load(REPEATS_DIR / ("%s.json" % r)) for r in REPEATS}
    files = sorted(DECISIONS_DIR.glob(DECISIONS_GLOB))
    decisions = [d for f in files for d in load(f)["decisions"]]
    disputes = load(DISPUTES) if DISPUTES.exists() else None
    return load(CATALOGUE), load(LABELS), disputes, decisions, repeats, [str(f.relative_to(ROOT)) for f in files]


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Score the triage repeats")
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--write-disputes", "--check-disputes", "--write", "--check"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--spot-check", type=int, default=0, help="with --write-disputes: sample N agreed items")
    args = ap.parse_args(argv)
    catalogue, labels, disputes, decisions, repeats, files = load_inputs()
    if args.write_disputes or args.check_disputes:
        n = args.spot_check if args.write_disputes else (disputes or {}).get("spot_check", {}).get("n", 0)
        text = render(disputes_doc(catalogue, labels, repeats, n))
        if args.check_disputes:
            ok = DISPUTES.exists() and DISPUTES.read_text(encoding="utf-8") == text
            print("HOLDS: disputes.json rebuilds" if ok else "REFUSED: disputes.json does not rebuild")
            return 0 if ok else 1
        if DISPUTES.exists():
            print("REFUSED: %s exists; it is the question put to the owner and is never rewritten" % DISPUTES.name)
            return 1
        DISPUTES.write_text(text, encoding="utf-8")
        print("WROTE %s: %d card(s)" % (DISPUTES.relative_to(ROOT), len(json.loads(text)["cards"])))
        return 0
    if disputes is None:
        print("REFUSED: no disputes.json yet; run --write-disputes after the repeats")
        return 1
    try:
        text = render(build(catalogue, labels, disputes, decisions, repeats, files))
    except ValueError as exc:
        print("REFUSED: %s" % exc)
        return 1
    if args.check:
        ok = SCORE.exists() and SCORE.read_text(encoding="utf-8") == text
        print("HOLDS: score.json rebuilds from the committed repeats" if ok else "REFUSED: score.json does not rebuild")
        return 0 if ok else 1
    if args.write:
        SCORE.write_text(text, encoding="utf-8")
        print("WROTE %s" % SCORE.relative_to(ROOT))
    s = json.loads(text)
    for name, sec in [("overall", s["overall"])] + sorted(s["per_source"].items()):
        fmt = lambda b: "n/a" if b is None else "%.3f-%.3f (mean %.3f)" % (b["min"], b["max"], b["mean"])  # noqa: E731
        print("  %-8s recall %-26s precision %s" % (name, fmt(sec["recall"]), fmt(sec["precision"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: Run the guard and every mutation**

```bash
.venv/bin/python evals/check_feeds_score.py
for m in missing-excluded swap band-first zero-as-one draft-labels majority-dispute unfinished-dispute decide-anything spot-any-agreed; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_score.py --mutate $m | tail -1; done
```

Expected (measured):
- 12 PASS lines, `HELD (0 failures)`.
- Mutations: missing-excluded 3, swap 2, band-first 1, zero-as-one 1, draft-labels 6, majority-dispute 10, unfinished-dispute 9, decide-anything 1, spot-any-agreed 1.

Check the hand computation in the guard's comments yourself: it is the only thing standing between the scorer and a plausible wrong number.

- [ ] **Step 4: Register and commit**

In `tools/check_all.py`:

Replace:

```python
    ("check_feeds_orchestrator", ["evals/check_feeds_orchestrator.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

with:

```python
    ("check_feeds_orchestrator", ["evals/check_feeds_orchestrator.py"], "cold"),
    ("check_feeds_score", ["evals/check_feeds_score.py"], "cold"),
    ("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold"),
```

```bash
.venv/bin/python tools/check_all.py --cold
git add evals/score_feeds_triage.py evals/check_feeds_score.py tools/check_all.py
git commit -m "Slice 2 B: the triage scorer -- recall first, precision beside it, a band over three repeats, pinned on hand-computed data"
```

---

### Task 6: Claude's draft labels, frozen before any repeat

**STOP before Step 1 unless the owner has ruled on decision 3, the rubric.** The rubric is written into `labels.json` beside its sha256 and is frozen with the drafts. If the owner changed it, edit `RUBRIC` in the file below before anything else.

**Files:**
- Create: `tools/write_feeds_labels.py`, `evals/feeds/labels.json` (by running it)
- Modify: `evals/check_feeds_catalogue.py` (one line)

**Interfaces:**
- Consumes: Task 3's catalogue and documents; `feeds.triage.page_texts`.
- Produces: `evals/feeds/labels.json`: `{schema, catalogue_sha256, rubric, rubric_sha256, drafted_by, drafted_on, labels: {key: {label, reason}}}`.

- [ ] **Step 1: Write the tool**

Create `tools/write_feeds_labels.py`:

```python
"""
Write the draft triage labels once: evals/feeds/labels.json, from the drafter's notes (slice 2 B, Task 5).

Usage:
    python tools/write_feeds_labels.py --show KEY                      # print an item and its pinned pages
    python tools/write_feeds_labels.py --drafts FILE --drafted-on YYYY-MM-DD

FILE is JSON Lines, one {"key", "label", "reason"} per scored catalogue item. The tool validates every
line against the catalogue (each scored key exactly once; relevant | not_relevant; a reason of 1..300
characters) and writes labels.json in canonical form with the RUBRIC below and its sha256. It refuses
if labels.json exists: the drafts are frozen before the first repeat, and the owner's later decisions
live in evals/owner_decisions/, never in this file.

The drafter is Claude in the implementing session, reading each item with --show, never the triage
agent and never its output: the drafts must be written and committed before any repeat runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.triage import REASON_MAX, VERDICTS, page_texts  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
LABELS = EVAL_DIR / "labels.json"
DOCS = EVAL_DIR / "docs"
SCHEMA = "fc08-triage-labels/1"

RUBRIC = """Label the publication as pinned: the page feeds_fetch pinned for the item, which for FinCEN and OFSI is the landing page (the advisory itself is a linked PDF that is not fetched), read together with the item's title and summary.
relevant: the publication describes methods, red flags or cases of financial crime that a typology could hold -- a money-laundering, fraud, sanctions-evasion, terrorist-financing, proliferation-financing or corruption technique; indicators an analyst could screen for; or an enforcement, penalty or settlement case that says what was done. A FinCEN advisory is relevant when its landing page names such a subject. A translation of a relevant advisory is relevant (whether to accept a duplicate is accept_run's question, not triage's). A rescinded advisory is labelled by its content, and the reason says it was rescinded.
not_relevant: a bare designation or delisting list, a licence or general licence, a notice of a regulatory, procedural or website change, an event or webinar listing, or guidance that restates obligations without describing a method, red flag or case.
An OFAC recent action that combines designations with anything relevant (an enforcement action, a settlement, an advisory or alert) is relevant.
When the pinned text leaves the question open, the label is relevant, and the reason says what was missing (the spec's asymmetry: when in doubt, keep it)."""


def show(key: str) -> int:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    item = next((it for it in catalogue["items"] if it["key"] == key), None)
    if item is None:
        print("no scored catalogue item %s" % key)
        return 1
    print("%s | %s | %s\n%s\nsummary: %s\n" % (item["key"], item["published"], item["title"], item["url"],
                                               item["summary"] or "-"))
    doc = item["document"]
    for n, text in enumerate(page_texts(DOCS / ("%s.%s" % (doc["sha256"], doc["ext"]))), 1):
        print("=== PAGE %d ===\n%s\n" % (n, text.strip()))
    return 0


def write(drafts: Path, drafted_on: str) -> int:
    if LABELS.exists():
        print("REFUSED: %s exists; the drafts are frozen" % LABELS.relative_to(ROOT))
        return 1
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", drafted_on):
        print("REFUSED: --drafted-on %r is not YYYY-MM-DD" % drafted_on)
        return 1
    catalogue_raw = CATALOGUE.read_bytes()
    keys = {it["key"] for it in json.loads(catalogue_raw)["items"]}
    labels, problems = {}, []
    for n, line in enumerate(drafts.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        d = json.loads(line)
        reason = (d.get("reason") or "").strip()
        if d.get("key") not in keys:
            problems.append("line %d: %r is not a scored catalogue item" % (n, d.get("key")))
        elif d["key"] in labels:
            problems.append("line %d: %s is labelled twice" % (n, d["key"]))
        elif d.get("label") not in VERDICTS or not 1 <= len(reason) <= REASON_MAX:
            problems.append("line %d: %s needs relevant | not_relevant and a reason of 1..%d characters"
                            % (n, d["key"], REASON_MAX))
        else:
            labels[d["key"]] = {"label": d["label"], "reason": reason}
    missing = sorted(keys - set(labels))
    if missing:
        problems.append("unlabelled: %s" % ", ".join(missing))
    if problems:
        print("REFUSED, nothing written:\n  " + "\n  ".join(problems))
        return 1
    doc = {"schema": SCHEMA, "catalogue_sha256": hashlib.sha256(catalogue_raw).hexdigest(), "rubric": RUBRIC,
           "rubric_sha256": hashlib.sha256(RUBRIC.encode("utf-8")).hexdigest(), "drafted_by": "claude-in-session",
           "drafted_on": drafted_on, "labels": labels}
    LABELS.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    rel = sum(1 for v in labels.values() if v["label"] == "relevant")
    print("WROTE %s: %d labels, %d relevant, %d not_relevant" % (LABELS.relative_to(ROOT), len(labels), rel,
                                                                len(labels) - rel))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Write the draft triage labels once")
    ap.add_argument("--show", metavar="KEY")
    ap.add_argument("--drafts", type=Path)
    ap.add_argument("--drafted-on")
    args = ap.parse_args(argv)
    if args.show:
        return show(args.show)
    if not (args.drafts and args.drafted_on):
        ap.error("--drafts and --drafted-on, or --show")
    return write(args.drafts, args.drafted_on)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Draft one label per item, reading each document**

For every scored key in `evals/feeds/catalogue.json`, in catalogue order:

```bash
.venv/bin/python tools/write_feeds_labels.py --show <key>
```

Read every page shown, and decide by `RUBRIC` alone. Append one line to a drafts file OUTSIDE the repository, for example `/tmp/fc08-triage-drafts.jsonl`:

```json
{"key": "fincen:06d25c9680e16a19", "label": "relevant", "reason": "Joint advisory on risks from non-work-authorized populations and their employers: a FinCEN advisory naming a financial-crime subject."}
```

Rules for the drafter:
- **You are Claude in the implementing session.** Never delegate this to the triage agent, and never read any triage output. None exists yet: the runner refuses to start until these drafts are committed.
- **The reason says why, in the rubric's terms**, in at most 300 characters. For a translation or a rescinded advisory, the reason says so.
- **Spend the time.** About 60 short pages, roughly an hour. A label drafted from the title alone is a guess, and the owner will only ever see it if a repeat happens to disagree.

- [ ] **Step 3: Write the labels**

```bash
.venv/bin/python tools/write_feeds_labels.py --drafts /tmp/fc08-triage-drafts.jsonl --drafted-on "$(date +%Y-%m-%d)"
```

Expected: `WROTE evals/feeds/labels.json: 60 labels, R relevant, N not_relevant`.
- Report R and N per source.
- My expectation, as a prior and not a target: FinCEN about 20 relevant; OFSI about 3 to 6 (the penalty notices, the penalty press release, perhaps the impersonation-scam guidance); OFAC about 1 to 3 (actions naming a settlement or enforcement action).
- A refusal names the offending line; fix the drafts file and run again. Nothing was written.

- [ ] **Step 4: Turn on the label checks**

In `evals/check_feeds_catalogue.py`, replace:

```python
LABELS_DRAFTED = False
```

with:

```python
LABELS_DRAFTED = True
```

```bash
git add evals/feeds/labels.json
.venv/bin/python evals/check_feeds_catalogue.py
for m in drop-item minted-key dup-key no-text unlabelled bad-label long-reason rubric-edited; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_catalogue.py --mutate $m | tail -1; done
```

Expected (measured):
- 11 PASS lines, `HELD (0 failures)`.
- Mutations: drop-item 3, minted-key 3, dup-key 3, no-text 2, unlabelled 1, bad-label 1, long-reason 1, rubric-edited 1.

- [ ] **Step 5: Commit, which freezes the drafts**

```bash
.venv/bin/python tools/check_all.py --cold
git add tools/write_feeds_labels.py evals/feeds/labels.json evals/check_feeds_catalogue.py
git commit -m "Slice 2 B: Claude's draft triage labels and rubric, frozen before the first repeat"
```

---

### Task 7: the runner, and ONE pilot session

**Files:**
- Create: `evals/run_feeds_triage.py`

**Interfaces:**
- Consumes: Task 4's `FeedsRun` and `run_triage`; Task 1's `feeds.triage.load`; Task 3's catalogue and documents; Task 6's labels.
- Produces, for Tasks 8 and 10:
  - `evals/feeds/repeats/<rep>.json`: `{schema, repeat, prompt_sha256, model, max_budget_usd, max_turns, catalogue_sha256, labels_draft_sha256, sessions, failed_attempts, verdicts}`;
  - `evals/feeds/repeats/<rep>/telemetry/<run_id>.jsonl`.

- [ ] **Step 1: Write the runner**

Create `evals/run_feeds_triage.py`:

```python
"""
Run the triage-only orchestrator over the back-catalogue: one repeat is one session per batch.

Usage:
    python evals/run_feeds_triage.py --repeat rep1 --pilot   # ONE session (the first batch), then stop
    python evals/run_feeds_triage.py --repeat rep1           # every batch not yet done; resumes after a failure
    python evals/run_feeds_triage.py --plan                  # print the batches; no session, no model

A REPEAT. The catalogue's scored items, the three sources interleaved (ofsi, fincen, ofac, ofsi, ...)
in catalogue order and cut into batches of at most feeds.triage.MAX_PER_RUN (10) -- batch-1 to batch-6
for 59 or 60 items -- one orchestrator session (agents/orchestrate_feeds.py) in eval mode per batch.
Interleaved, because a Friday run's new items arrive mixed: a session of ten OFAC designations would
measure a situation production never presents. The batches are the same in every repeat. When every
batch has a completed session the repeat is written to evals/feeds/repeats/<rep>.json, TRACKED, and
each session's telemetry is under evals/feeds/repeats/<rep>/telemetry/, TRACKED. Until then progress
is kept in evals/feeds/repeats/.progress/<rep>.json (gitignored), so a failed session is re-run alone.

REFUSES TO START when:
  - the repeat's record already exists (evidence is never overwritten);
  - ANTHROPIC_API_KEY is set: it takes precedence over the subscription token (CLAUDE.md, Auth);
  - catalogue.json or labels.json is untracked or differs from HEAD: the draft labels are frozen
    before the first repeat, and the record names both by sha256;
  - a catalogue document is missing, or its bytes do not hash to the catalogue's sha256;
  - the progress file was started under a different prompt, model, budget, catalogue or labels.

A session whose agent FAILED (is_error, or the SDK raised) does not advance the progress: it is kept
under failed_attempts and the command is simply run again. A session that ran and left items
unfinished DID complete: skipping is triage behaviour, and it is measured, never retried away.

MODEL RUNS. The only file in sub-project B that starts agent sessions. check_all never runs it.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agents import orchestrate_feeds as of, telemetry  # noqa: E402
from feeds import inbox, triage as feeds_triage  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
LABELS = EVAL_DIR / "labels.json"
DOCS = EVAL_DIR / "docs"
REPEATS_DIR = EVAL_DIR / "repeats"
PROGRESS_DIR = REPEATS_DIR / ".progress"
SCHEMA = "fc08-triage-repeat/1"
REPEATS = ("rep1", "rep2", "rep3")
SOURCES = ("ofsi", "fincen", "ofac")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def batches(catalogue: dict) -> list:
    per = [[it["key"] for it in catalogue["items"] if it["source"] == s] for s in SOURCES]
    mixed = [k for row in itertools.zip_longest(*per) for k in row if k]
    size = feeds_triage.MAX_PER_RUN
    return [("batch-%d" % (n + 1), mixed[i:i + size]) for n, i in enumerate(range(0, len(mixed), size))]


def identity() -> dict:
    return {"prompt_sha256": of.PROMPT_SHA256, "model": of.MODEL, "max_budget_usd": of.MAX_BUDGET_USD,
            "max_turns": of.MAX_TURNS, "catalogue_sha256": _sha(CATALOGUE), "labels_draft_sha256": _sha(LABELS)}


def _committed(path: Path) -> bool:
    rel = str(Path(path).relative_to(ROOT))
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=ROOT).returncode == 0
    return tracked and clean


def preflight(rep: str, catalogue: dict) -> list:
    problems = []
    if (REPEATS_DIR / ("%s.json" % rep)).exists():
        problems.append("%s.json exists; a repeat is never overwritten" % rep)
    if os.environ.get("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY is set; unset it so the run uses the subscription token")
    for path in (CATALOGUE, LABELS):
        if not path.exists() or not _committed(path):
            problems.append("%s is missing, untracked or differs from HEAD; commit it first" % path.relative_to(ROOT))
    for it in catalogue["items"]:
        doc = DOCS / ("%s.%s" % (it["document"]["sha256"], it["document"]["ext"]))
        if not doc.exists() or _sha(doc) != it["document"]["sha256"]:
            problems.append("the catalogue copy for %s is missing or changed (%s)" % (it["key"], doc.name))
    return problems


def _save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run(rep: str, pilot: bool, session=of.run_triage, today: date = None) -> int:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    problems = preflight(rep, catalogue)
    if problems:
        print("REFUSED:\n  " + "\n  ".join(problems))
        return 1
    progress_path = PROGRESS_DIR / ("%s.json" % rep)
    progress = (json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists()
                else dict(identity(), repeat=rep, sessions={}, failed_attempts=[]))
    moved = sorted(k for k, v in identity().items() if progress.get(k) != v)
    if moved:
        print("REFUSED: %s was started under a different %s; see the plan (Task 7) for a changed arm"
              % (progress_path.relative_to(ROOT), ", ".join(moved)))
        return 1
    telemetry.TELEMETRY_DIR = REPEATS_DIR / rep / "telemetry"
    plan = batches(catalogue)
    for name, keys in plan:
        if name in progress["sessions"]:
            continue
        run = of.FeedsRun(inbox.mint_run_id(today or date.today()), catalogue=CATALOGUE, batch=tuple(keys))
        summary = dict(asyncio.run(session(run)), batch=name, keys=keys)
        if summary["failure"]:
            progress["failed_attempts"].append(summary)
            _save(progress_path, progress)
            print("FAILED  %s %s: %s\n  Nothing is lost; run the same command again to retry this batch."
                  % (name, run.run_id, summary["failure"]))
            return 1
        summary["verdicts"] = feeds_triage.load(run.run_id)
        progress["sessions"][name] = summary
        _save(progress_path, progress)
        print("done    %-9s %s  %d/%d triaged, %d unfinished, %s turns, US$%s" % (
            name, run.run_id, len(summary["triaged"]), len(keys), len(summary["unfinished"]), summary["turns"],
            summary["cost_usd"]))
        if pilot:
            print("PILOT: stopped after one session. Projected for three repeats of %d sessions: US$%.2f"
                  % (len(plan), (summary["cost_usd"] or 0) * len(plan) * len(REPEATS)))
            return 0
    sessions = [progress["sessions"][name] for name, _ in plan]
    verdicts = {k: {f: v[f] for f in ("verdict", "reason", "quote", "found_on", "match", "run_id", "decided_at")}
                for s in sessions for k, v in s["verdicts"].items()}
    record = dict(identity(), schema=SCHEMA, repeat=rep, verdicts=verdicts,
                  failed_attempts=progress["failed_attempts"],
                  sessions=[{f: s[f] for f in s if f != "verdicts"} for s in sessions])
    _save(REPEATS_DIR / ("%s.json" % rep), record)
    print("WROTE evals/feeds/repeats/%s.json: %d sessions, %d verdicts, US$%.2f" % (
        rep, len(sessions), len(verdicts), sum(s["cost_usd"] or 0 for s in sessions)))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Run triage-only repeats over the back-catalogue")
    ap.add_argument("--repeat", choices=REPEATS)
    ap.add_argument("--pilot", action="store_true", help="one session, then stop and project the cost")
    ap.add_argument("--plan", action="store_true", help="print the batches; start nothing")
    args = ap.parse_args(argv)
    if args.plan:
        for name, keys in batches(json.loads(CATALOGUE.read_text(encoding="utf-8"))):
            print("  %-9s %2d items" % (name, len(keys)))
        return 0
    if not args.repeat:
        ap.error("--repeat is required unless --plan")
    return run(args.repeat, args.pilot)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Check the batches, then commit the runner**

Run: `.venv/bin/python evals/run_feeds_triage.py --plan`

Expected: six batches of 10, or 10,10,10,10,10,9 if one item was excluded. No session is started.

```bash
git add evals/run_feeds_triage.py
git commit -m "Slice 2 B: the triage repeat runner -- frozen inputs, resumable, a failed session re-run alone"
```

- [ ] **Step 3: The auth preflight, by hand**

```bash
unset ANTHROPIC_API_KEY
claude auth status
```

- `authMethod` must not be `api_key` (CLAUDE.md, Auth).
- If the CLI is not logged in, stop and ask the owner to run `claude setup-token`. Never paste a token anywhere.

- [ ] **Step 4: Run the pilot: one real session, the first batch**

Run: `.venv/bin/python evals/run_feeds_triage.py --repeat rep1 --pilot`

**Cost: one session, estimated US$0.30 to US$0.80, capped at US$1.50.**

Expected: a line like the one below, then the `PILOT:` line with the projection for all 18 sessions.

```
done    batch-1   feeds-YYYY-MM-DD-xxxxxx  10/10 triaged, 0 unfinished, NN turns, US$0.NN
```

- A `FAILED` line means auth, credit or the CLI. Fix it and run the same command again; nothing is lost.
- A `REFUSED:` line names the preflight problem.

- [ ] **Step 5: Read the pilot, do not only count it**

Report all of the following:
- **Every verdict** in `inbox/<run_id>/triage.jsonl`: key, verdict, reason, quote and `found_on`.
- **From the session's telemetry**, `evals/feeds/repeats/rep1/telemetry/<run_id>.jsonl`:
  - the number of `feeds_read_page` calls;
  - the number of REFUSED events and their outcomes (how often a quote was re-copied);
  - `RUN_COMPLETED`'s `terminal_check`, `limit` and `unfinished`.
- **The cost, the turns, the duration, and the runner's projection.**
- **Anything odd:**
  - an item triaged without a `feeds_read_page` call;
  - the same quote refused more than twice;
  - a verdict whose reason contradicts its quote;
  - a `limit` hit.

- [ ] **Step 6: STOP — the owner's go for the remaining 17 sessions**

Give the owner:
- the pilot report;
- the projection (pilot cost × 18);
- the Friday implication: whether the pilot's cost for up to 10 items leaves US$3.00 of the US$5 ceiling for C's three extractions, which it does if it is at most US$2.00.

Do not run Task 8 without the go.

- **If the owner wants the prompt changed**, the pilot becomes the evidence of a discarded arm:
  - move `evals/feeds/repeats/.progress/rep1.json` and `evals/feeds/repeats/rep1/telemetry/` to `evals/feeds/pilot-<date>/` (`mv`, never delete);
  - commit that folder with a message naming the old `PROMPT_SHA256`;
  - change the prompt;
  - re-run `check_feeds_orchestrator` (its prompt check);
  - run Step 4 again.
- The runner refuses to resume a progress file started under another prompt. That refusal is the guard against mixing two arms in one repeat.

---

### Task 8: the three repeats

**Files:**
- Create (by running): `evals/feeds/repeats/rep1.json`, `rep2.json`, `rep3.json`, and `evals/feeds/repeats/rep{1,2,3}/telemetry/`

**Cost:** the remaining 17 sessions, estimated US$5 to US$14, hard-capped at US$1.50 each. Wall clock is roughly 3 to 6 minutes per session. If the subscription's usage window runs out, wait and re-run the same command; the runner resumes at the first batch without a completed session.

- [ ] **Step 1: Finish repeat 1 (it resumes after the pilot) and commit it**

```bash
unset ANTHROPIC_API_KEY
.venv/bin/python evals/run_feeds_triage.py --repeat rep1
git add evals/feeds/repeats/rep1.json evals/feeds/repeats/rep1/telemetry
git commit -m "Slice 2 B: triage repeat 1 over the back-catalogue"
```

Expected: five more `done` lines, then `WROTE evals/feeds/repeats/rep1.json: 6 sessions, V verdicts, US$X`.
- Report V, the unfinished count and US$X.
- A `FAILED` line: re-run the same command.

- [ ] **Step 2: Repeat 2, commit**

```bash
.venv/bin/python evals/run_feeds_triage.py --repeat rep2
git add evals/feeds/repeats/rep2.json evals/feeds/repeats/rep2/telemetry
git commit -m "Slice 2 B: triage repeat 2 over the back-catalogue"
```

- [ ] **Step 3: Repeat 3, commit**

```bash
.venv/bin/python evals/run_feeds_triage.py --repeat rep3
git add evals/feeds/repeats/rep3.json evals/feeds/repeats/rep3/telemetry
git commit -m "Slice 2 B: triage repeat 3 over the back-catalogue"
```

Nothing changes between repeats: not the prompt, the model, the limits, the catalogue or the labels. The runner records each by sha256 and refuses a mismatch within a repeat, and Task 10's guard refuses a mismatch across repeats.

- [ ] **Step 4: Report the run**

Report:
- per repeat: sessions, verdicts, unfinished, failed attempts, cost;
- in all: 18 sessions and the total cost against the estimate.

Also report how many of the 18 `terminal_check`s are clean (no `unterminated`, no `duplicated`). Each one is a live `terminal_check`. That is evidence toward the spec's definition-of-done box 4, which belongs to C, and it should be named as such rather than claimed.

---

### Task 9: the disputes, and the owner's decisions

**Files:**
- Create: `evals/feeds/disputes.json` (by the scorer), `evals/owner_decisions/feeds_triage_labels_<date>.json` (the owner's decisions, verbatim)

- [ ] **Step 1: Build the disputes, and commit them before anyone decides**

```bash
.venv/bin/python evals/score_feeds_triage.py --write-disputes --spot-check 6
.venv/bin/python evals/score_feeds_triage.py --check-disputes
git add evals/feeds/disputes.json
git commit -m "Slice 2 B: the triage disputes put to the owner"
```

- `6` is decision 4's default. Use the owner's number, or `0`.
- Expected: `WROTE evals/feeds/disputes.json: C card(s)`, then `HOLDS: disputes.json rebuilds`.
- `disputes.json` is the question. It is never rewritten, and `--write-disputes` refuses once it exists.

- [ ] **Step 2: Put the cards to the owner**

One card per entry in `disputes.json`, numbered, each showing:
- the source, title, published date and URL;
- the kind: `dispute`, or `spot_check` (an item all four said was not relevant);
- the draft label and its reason;
- each repeat's verdict, reason and quote.

Present them in chat, or, if the owner asks for a page, as a page that embeds every card in its own HTML. Slice 1's label pass nearly recorded nothing because its page loaded its cards from a database that resolved to nothing in the owner's view. Recommend a decision on each card and say why, but the decision is the owner's.

- [ ] **Step 3: STOP — the owner decides each card**

Wait for one decision per card: `relevant` or `not_relevant`, with an optional note. Never record a decision the owner has not given in chat.

- [ ] **Step 4: Record the decisions exactly as given**

Create `evals/owner_decisions/feeds_triage_labels_<YYYY-MM-DD>.json`, dated the day of the decisions:

```json
{
  "date": "YYYY-MM-DD",
  "what": "Owner decisions on the triage disputes and spot-check sample (evals/feeds/disputes.json). Covers those items only; every other label is Claude's draft, unchallenged, not confirmed.",
  "decisions": [
    {"key": "<key>", "kind": "dispute", "decision": "relevant", "note": "", "decided_at": "YYYY-MM-DDTHH:MM:SSZ"}
  ]
}
```

- One entry per card, with the card's `kind`.
- A change of mind after the commit is outside this plan. The scorer refuses a key decided twice, so it cannot happen silently: raise it with the owner, and never edit a committed decisions file.

Run: `.venv/bin/python evals/score_feeds_triage.py`

Expected: four lines, overall and per source, with recall and precision bands. `REFUSED: undecided: …` means a card has no decision; go back to Step 3 for it.

- [ ] **Step 5: Commit the decisions**

```bash
git add evals/owner_decisions/feeds_triage_labels_*.json
git commit -m "Slice 2 B: the owner's decisions on the triage disputes"
```

---

### Task 10: the committed band, and the guard that rebuilds it

**Files:**
- Create: `evals/feeds/score.json`
- Modify: `evals/check_feeds_score.py`, `CLAUDE.md`

- [ ] **Step 1: Write the band**

```bash
.venv/bin/python evals/score_feeds_triage.py --write
.venv/bin/python evals/score_feeds_triage.py --check
```

Expected: the four band lines, then `HOLDS: score.json rebuilds from the committed repeats`.

- [ ] **Step 2: Extend the guard to the committed evidence**

In `evals/check_feeds_score.py`:

**Edit 1 of 5.** Replace:

```python
    python evals/check_feeds_score.py --mutate spot-any-agreed     # the spot check samples agreed relevant items too

```

with:

```python
    python evals/check_feeds_score.py --mutate spot-any-agreed     # the spot check samples agreed relevant items too
    python evals/check_feeds_score.py --mutate edited-repeat       # a committed repeat's verdict edited in memory
    python evals/check_feeds_score.py --mutate edited-labels       # a draft label edited after the repeats ran

```

**Edit 2 of 5.** Replace:

```python

COLD. No repeat, label or catalogue file is read: every input is built below.

```

with:

```python

AND ON THE COMMITTED EVIDENCE (added in Task 9, with the files it reads):
  reproducible  evals/feeds/score.json is exactly what the scorer builds from the committed catalogue,
                draft labels, three repeats and owner decisions, and disputes.json exactly what was put
                to the owner -- so the committed band cannot drift from the records behind it;
  one arm       the three repeats share one prompt, model, budget and turn cap, name the committed
                catalogue by sha256, and name the draft labels as they are NOW (drafted before the
                repeats and unchanged since);
  coverage      each repeat's sessions cover every scored item exactly once, and every verdict carries
                its verified quote and the pages it was found on;
  decisions     each decision file is dated in its name and its body, each decision timestamped.

COLD. The synthetic checks read nothing; the committed checks read tracked files only.

```

**Edit 3 of 5.** Replace:

```python
}

```

with:

```python
}
DATA_MUTATIONS = ("edited-repeat", "edited-labels")  # applied to the loaded evidence, not to the scorer

```

**Edit 4 of 5.** Replace:

```python

def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage scorer")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    sc = load_scorer(args.mutate)
    if args.mutate:
```

with:

```python

def committed_checks(sc, mutation) -> list:
    """The committed evidence: the band and the disputes rebuild, and the repeats are one arm."""
    import hashlib
    import json
    import re
    out = []
    catalogue, labels, disputes, decisions, repeats, files = sc.load_inputs()
    if mutation == "edited-repeat":
        key = sorted(repeats["rep1"]["verdicts"])[0]
        v = repeats["rep1"]["verdicts"][key]
        v["verdict"] = sc.NOT_RELEVANT if v["verdict"] == sc.RELEVANT else sc.RELEVANT
    if mutation == "edited-labels":
        labels["labels"][sorted(labels["labels"])[0]]["reason"] += " (edited after the repeats)"
    try:
        text, err = sc.render(sc.build(catalogue, labels, disputes, decisions, repeats, files)), None
    except Exception as exc:
        text, err = None, "%s: %s" % (type(exc).__name__, exc)
    out.append((text is not None and sc.SCORE.read_text(encoding="utf-8") == text,
                "the committed score.json is exactly what the scorer builds from the committed evidence",
                err or "score.json %s" % ("matches" if text == sc.SCORE.read_text(encoding="utf-8") else "DIFFERS")))
    rebuilt = sc.render(sc.disputes_doc(catalogue, labels, repeats, disputes["spot_check"]["n"]))
    out.append((sc.DISPUTES.read_text(encoding="utf-8") == rebuilt,
                "disputes.json is exactly the question the evidence poses (%d cards)" % len(disputes["cards"]), ""))
    arm = {r: tuple(repeats[r].get(k) for k in ("prompt_sha256", "model", "max_budget_usd", "max_turns"))
           for r in sc.REPEATS}
    cat_sha = hashlib.sha256(sc.CATALOGUE.read_bytes()).hexdigest()
    lab_sha = hashlib.sha256(sc.render(labels).encode("utf-8")).hexdigest()
    out.append((len(set(arm.values())) == 1 and all(repeats[r].get("schema") == "fc08-triage-repeat/1"
                                                    and repeats[r].get("repeat") == r
                                                    and repeats[r].get("catalogue_sha256") == cat_sha
                                                    and repeats[r].get("labels_draft_sha256") == lab_sha
                                                    for r in sc.REPEATS),
                "the three repeats are one arm over the committed catalogue and the unchanged draft labels",
                {r: repeats[r].get("labels_draft_sha256", "")[:12] for r in sc.REPEATS}))
    keys = sorted(it["key"] for it in catalogue["items"])
    covered = {r: sorted(k for s in repeats[r]["sessions"] for k in s["keys"]) for r in sc.REPEATS}
    quoted = all(v.get("quote") and v.get("found_on") and set(v) >= {"verdict", "reason", "run_id"}
                 and k in keys for r in sc.REPEATS for k, v in repeats[r]["verdicts"].items())
    out.append((all(c == keys for c in covered.values()) and quoted,
                "each repeat's sessions cover every scored item exactly once; every verdict carries its quote",
                {r: len(c) for r, c in covered.items()}))
    dated = all(re.fullmatch(r"evals/owner_decisions/feeds_triage_labels_(\d{4}-\d{2}-\d{2})\.json", f)
                and json.loads((sc.ROOT / f).read_text(encoding="utf-8"))["date"] == f[-15:-5] for f in files)
    out.append((files and dated and all(d.get("decided_at") for d in decisions),
                "each owner decision file is dated in its name and body, and each decision is timestamped", files))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage scorer")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS) + list(DATA_MUTATIONS),
                    help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    sc = load_scorer(args.mutate if args.mutate in MUTATIONS else None)
    if args.mutate:
```

**Edit 5 of 5.** Replace:

```python
    failures = 0
    for ok, label, detail in checks(sc):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
```

with:

```python
    failures = 0
    for ok, label, detail in checks(sc) + committed_checks(sc, args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
```

- [ ] **Step 3: Run the guard and every mutation**

```bash
git add evals/feeds/score.json
.venv/bin/python evals/check_feeds_score.py
for m in missing-excluded swap band-first zero-as-one draft-labels majority-dispute unfinished-dispute decide-anything spot-any-agreed edited-repeat edited-labels; do PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_score.py --mutate $m | tail -1; done
```

Expected: 17 PASS lines (12 synthetic, 5 on the committed evidence), `HELD (0 failures)`, and all eleven mutations detected.
- The counts depend on the real evidence.
- Measured on the scratch run's synthetic evidence: missing-excluded 3, swap 3, band-first 2, zero-as-one 1, draft-labels 7, majority-dispute 11, unfinished-dispute 10, decide-anything 1, spot-any-agreed 2, edited-repeat 2, edited-labels 3.
- The two that must be seen failing on the REAL evidence are `edited-repeat` and `edited-labels`. They prove the committed band cannot drift from the committed records.

- [ ] **Step 4: Record it in CLAUDE.md**

In `CLAUDE.md`, fill the angle-bracketed figures from `evals/feeds/score.json` and the Task 8 report:

Replace:

```markdown
**An OFSI item's id carries its Atom timestamp**, so a revised GOV.UK publication is a new item.
```

with:

```markdown
**An OFSI item's id carries its Atom timestamp**, so a revised GOV.UK publication is a new item.

## Slice 2: triage and its eval (sub-project B, built <DATE>)

Plan: `docs/superpowers/plans/2026-09-27-slice2-b-triage-and-its-eval.md`.

| File | What it holds |
|---|---|
| `feeds/triage.py` | THE triage rules: `inbox/<run_id>/triage.jsonl`, one verdict per item, appended only; the quote found in the PINNED document by the shared matcher, every page it holds on recorded; reason 1..300; at most 10 verdicts per run; every refusal starts `Rejected:` (REFUSED in telemetry) |
| `mcp_server/feeds_server.py` (B) | adds `feeds_read_page` (the only read, pre-approved) and `feeds_triage`. EVAL MODE, set only by `evals/run_feeds_triage.py` (`FEEDS_CATALOGUE` + `FEEDS_CATALOGUE_BATCH`): lists a catalogue batch and serves its pinned copies, never the live page, the network or the ledger. A's refusals now read `Rejected:` too |
| `agents/orchestrate_feeds.py` | the orchestrator, triage-only in B: four feeds tools, `tools=[]`, `setting_sources=[]`, the writes through `FEEDS_WRITE_ALLOWLIST` in `agents/permissions.py`. A session stopped by its own turn or budget cap COMPLETED (its leftovers are unfinished); only other errors are failures |
| `evals/feeds/catalogue.json` | the back-catalogue: 20 listed per source, built ONCE by `tools/build_feeds_catalogue.py`, sha256 pinned in `evals/check_feeds_catalogue.py`; its documents are in `evals/feeds/docs/` (gitignored) |
| `evals/feeds/labels.json` | Claude's draft labels and rubric, frozen before the first repeat. The owner's decisions are in `evals/owner_decisions/feeds_triage_labels_<date>.json`, NEVER in this file |
| `evals/feeds/repeats/rep{1,2,3}.json`, `rep*/telemetry/` | the three committed triage repeats (6 sessions of at most 10 items each) and every session's telemetry |
| `evals/score_feeds_triage.py` | disputes (ANY repeat differing from the draft) and the band (recall first, precision beside it, min/max/mean over three repeats, per source); `--check` rebuilds `evals/feeds/score.json`, and so does `evals/check_feeds_score.py` in `check_all` |

**The triage band, measured <DATE>: recall <MIN>-<MAX> (mean <MEAN>), precision <MIN>-<MAX> (mean <MEAN>) over <N> items and three repeats.** Per source, recall: OFSI <..>, FinCEN <..>, OFAC <..>. <D> disputes and <P> spot-checked items went to the owner, who changed <C> labels; the other <U> labels are Claude's drafts, UNCHALLENGED, not confirmed. 18 sessions, US$<COST>, <T> of 18 `terminal_check`s clean.

**Read it per source.** FinCEN's listing is its advisories page, so its 20 items are advisories by construction and dominate the overall recall; the discriminating items are the few OFSI and OFAC cases. **Triage read landing pages** (FinCEN, OFSI) and action pages (OFAC), as A pins them: if sub-project C changes what triage reads, this band describes a different input and the repeats must be re-run.
```

- [ ] **Step 5: Check cold, commit, report**

```bash
.venv/bin/python tools/check_all.py --cold
git add evals/feeds/score.json evals/check_feeds_score.py CLAUDE.md
git commit -m "Slice 2 B: the committed triage band, rebuilt cold from the committed repeats and the owner's decisions"
```

Report to the owner:
- the band, overall and per source;
- every false negative, with the reasons the repeats gave;
- the disputes count, and how many labels the owner changed;
- the spot-check result;
- the total cost against the estimate;
- the clean `terminal_check` count.

Name the band's limits in the same report:
- unchallenged labels are not confirmed;
- FinCEN dominates the overall recall;
- triage read landing pages.

Push nothing until the owner asks.

---

## Definition of done for sub-project B

Each item is traced to the spec (section 4 and the definition-of-done list in section 6).

- **Spec DoD 3 — Tasks 3 and 5 to 10.** A committed triage eval with a recall and a precision band over three committed repeats, the owner's decisions recorded and dated, and a cold guard (`check_feeds_score`) that rebuilds the committed band from the committed repeats and is mutation-verified.
- **Spec DoD 2, for `feeds_triage` — Tasks 1 and 2.** The tool enforces:
  - the quote found in the pinned document;
  - one verdict per item;
  - not_relevant stored, reported and never deleted;
  - the 300-character reason;
  - the cap of 10.
  `feeds_extract`'s "only after a relevant verdict" is C's.
- **Section 4's triage-only mode — Task 4.** The list, fetch, read and triage tools only, with no extraction, guarded by `check_feeds_orchestrator`.
- **Four new cold guards in `check_all`, each mutation-verified, 38 mutations in all:**
  - `check_feeds_triage` 13;
  - `check_feeds_catalogue` 8;
  - `check_feeds_orchestrator` 6;
  - `check_feeds_score` 11 (9 on the scorer, 2 on the evidence);
  - plus A's `check_feeds_server`, whose 8 still hold after B's edits, and `check_feeds_ledger`'s `newline-run-id`.
- **Not in B:** the live Friday run, extraction, the budget ceiling across a run, the Friday report and `accept_run`'s accept path are sub-project C.
