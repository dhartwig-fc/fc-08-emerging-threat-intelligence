# Slice 2 C1: Extraction, the Full Orchestrator, the Friday Report and `accept_run` Implementation Plan

> **Approved by the owner on 2026-09-28: "accept all recommendations".** Every decision in "For the owner" is taken as recommended (decisions 1-11). Drafted and verified in a scratch clone of `main` at `2375fd8`; re-check each edit's anchor before running it if `main` has moved.
>
> This is the first of TWO plans for sub-project C (decision 8). C1 is the spec's week 4 plus `accept_run` end to end: everything that can be built and proved offline, and one manual dry run. **C2** (`2026-09-28-slice2-c2-schedule-and-first-fridays.md`) is week 5: the schedule, the auth preflight, the notification, back-pressure, the first real Friday run and the first accepted run.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Every STOP is a hard stop: report, and wait for the owner.** Never brief a subagent to run the whole `tools/check_all.py` in the foreground if it runs more than 10 minutes; run the named guards, and let the pre-commit hook run the rest.

## For the owner

### The decisions this plan needs from you, each with my recommendation

1. **What extraction reads.** Measured below: every FinCEN landing page links exactly one PDF (20 of 20, all on `www.fincen.gov`); OFSI pages link 0, 1 or 2 PDFs, all on `assets.publishing.service.gov.uk`; OFAC pages link no `.pdf` at all.
   - **Recommended (a): `feeds_extract` follows the ONE linked PDF, at extraction time, not at fetch time.** When an item's pinned page links exactly one PDF on its source's *document hosts*, `feeds_extract` fetches and pins that PDF through `feeds/http.get` (https, exact host, `application/pdf` only, the size cap, the 2-second gap) and the extraction reads it. A page linking none is extracted as itself (every OFAC action; OFSI notices such as the scam-email guidance and the Sabre press release, which carry their content in HTML). A page linking several is refused as ambiguous, for a person (in the catalogue that is only OFSI general licences, which are not relevant anyway).
   - What it changes in A: `Source` gains `document_hosts` (FinCEN `www.fincen.gov`, OFSI `assets.publishing.service.gov.uk`, OFAC none). `assets.publishing.service.gov.uk` is a **document host only**, never a listing or item host. A's rule "only URLs from a listed item" becomes "only URLs from a listed item, or the one PDF link read from that item's PINNED page, on its source's document hosts". The URL still never comes from the agent; it is re-derivable from the pinned bytes. `feeds_fetch` is unchanged, so **triage reads exactly what B's band measured** and the band stays valid. Guarded by `check_feeds_extract` (`--mutate any-host`).
   - Not followed: OFAC's `/media/<n>/download?inline` links. One is a real PDF (measured: the Rice Lake settlement, 4 pages), but `/media/935656` is linked from every OFAC page in the catalogue, so no rule identifies "the" document. The Rice Lake page itself (1,136 characters) states the case, the amount and the violations.
   - (b) Pin the PDF at `feeds_fetch`: triage would read PDFs, B's band would describe a different input, and the three repeats (US$3.61) would have to be re-run. (c) Extract landing pages: a FinCEN landing page is 213 to 366 characters.
2. **The walkthrough.** **Recommended: one planned republish, in Task 6, and no builder change.** Measured in the scratch clone: adding the resolver line to the extractor's prompt changes the page by exactly one flag ("current instructions <b>do not name</b> it" becomes "<b>name</b> it"), and `build_walkthrough --check`, `check_walkthrough` and `check_publisher` go red until it is rebuilt, then `check_published_walkthrough --cold` until it is republished. Pinning the flag in the snapshot does not avoid that republish: the sentence says "current instructions", so a pinned "do not name" would be false the moment the prompt changes, and making it honest means rewording it, which is itself a page change. Pinning would add builder and guard surface and save nothing now. **Accepted runs do not force a republish:** measured after a simulated acceptance, the page stays byte-identical and `check_walkthrough` prints only its INFO line.
3. **Backlog seeding.** **Recommended: yes, seed all 60 back-catalogue items as drops** with `tools/accept_run.py --seed-catalogue` (Task 8), before the dry run. The ledger records them under the run label `catalogue:<sha256[:12]>`, so the source of each decision is visible. Why: 45 of the 60 are on today's listings; the triage cap is 10 per run and the agent works OFSI, then FinCEN, then OFAC, so without seeding the first five or so Fridays re-triage items the eval already labelled, and genuinely new items can wait behind the backlog. The FinCEN backlog goes back to 2020, which is not "live".
   - (b) Seed only the items labelled not relevant. The relevant FinCEN backlog then flows at 3 extractions per Friday: real corpus growth, but about five Fridays of 2020 to 2026 advisories before the stream is live. (c) No seeding.
4. **The eval runs in the production `inbox/`.** **Recommended: filter on the eval marker, in ONE classifier (`feeds/runs.py`),** used by back-pressure, `--expire` and `accept_run`; do not move them. B's runner and server stay untouched, and the marker is already the thing `accept_run` refuses on. Measured: 18 runs, all dated 2026-09-27; unfiltered, they would block every Friday until 2026-10-11.
5. **B's carry-forwards.**
   - `FEEDS_CATALOGUE` inherited from the shell: **fix.** A live server is started with `FEEDS_CATALOGUE=""` and `FEEDS_CATALOGUE_BATCH=""`, and `tools/friday_run.py` refuses to start when either is set. Found while doing it: the permission callback allows a write only when *every* value of `run.env()` is non-empty, so putting the blanks in `env()` would have denied every write of every live run. They go in a separate `server_env()`. Guarded (`--mutate inherit-catalogue`).
   - Unpinned `MAX_BUDGET_USD` / `MAX_TURNS`: **fix.** Pinned by `check_feeds_orchestrator`, with the run's ceiling, the extraction budget and the caps, and a check that one session plus three extractions fits in US$5.
   - The 18 eval runs: decision 4.
   - `validated` true for a session that triaged nothing: **fix.** `validated` now also requires nothing unfinished.
   - The ELLIPSIS tier against the word "verbatim": **leave.** 0 of B's 180 verdicts matched by ELLIPSIS. Changing the rule or the tool's wording would move the condition B measured. Slice 3.
   - The excess `feeds_triage` calls that never reached telemetry: **fix, from measured evidence.** In B's pilot transcript (read-only, outside the repository) each of the three unterminated calls has a `tool_result` with `is_error: true` and "InputValidationError: mcp__feeds__feeds_triage was called with input that could not be parsed as JSON". The runner sees that result in the message stream. It now records ONE terminal event for any call that got a `tool_result` and no hook event, marked `source: "transcript"`. A call with neither stays unterminated, so a genuinely lost call still fails reconciliation. The same is done in slice 1's extractor, whose `terminal_check` is now part of the run's reconciliation.
6. **The long-lived token.** This is C2's (Task 4 there). The owner runs `claude setup-token` in their own Terminal and stores the result in the login Keychain with `security add-generic-password -a "$USER" -s uk.fc08.claude-oauth-token -w`, which prompts for the value, so it never reaches the command line or shell history. `scripts/schedule/friday_run.sh` reads it at run time into the Python run's environment only. Claude never creates, reads, prints or enters it.
7. **Installing launchd** is an owner step in C2 (`tools/schedule.py install`). An agent runs `status` at most.
8. **Scope.** **Recommended: split.** C1 (this plan) is everything provable offline plus one dry run. C2 changes persistent configuration and needs the owner at each step, and it should wrap a runner the dry run has already exercised. Both plans are written in full.
9. **New: extraction runs in code after the agent stops, not inside the MCP tool.** The spec says `feeds_extract` "runs slice 1's extraction". In this plan the tool QUEUES a relevant item, choosing and pinning its document, and `tools/friday_run.py` extracts after the orchestrator session ends. **Recommended.**
   - The spec's own budget rule is the runner's: "the runner starts an extraction only if the spend so far plus US$1.00 stays within US$5". The orchestrator's spend is only known when its session ends.
   - An in-tool extraction would be a 4-to-5-minute nested agent session inside one MCP call, with a tool timeout nobody has measured.
   - The agent still decides what is extracted, and the tool still enforces "relevant only", "at most 3" and the document rule.
10. **New: where an accepted item goes. Recommended: `data/feeds/records/` and a separate `data/feeds/advisory_list.json`, not `data/records/` and `evals/golden/advisory_list.json`.** Measured in the scratch clone:
    - one planted record in `data/records/` fails `check_citation_repair` (its pin covers that folder's whole file set) and `actor_resolution --check`;
    - one appended entry in the golden list fails `build_digests --current --check` and `check_digest_batch` ("inputs moved since this batch: advisory_list.json"), because the current digest batch pins that file by sha256.

    Either one would refuse the acceptance commit and every commit after it. The review gate reads both lists, and an id in both is refused. The spec names the golden list; this deviates, deliberately.
11. **New: an advisory id is allocated when its extraction starts, not at acceptance.** `proposal_id` hashes the proposal's `advisory_id` and `run_id`, and the queue file is named by the run id. An id assigned at acceptance would mean rewriting evidence. The allocation is written before the extraction runs, and no id is ever reused (expired runs included). **Consequence: a dropped or deferred extracted item leaves a gap in the ADV numbering.** Recommended: accept the gaps.

### Measurements taken for this draft (2026-09-28)

Three requests through the repository's own `feeds/http.get` (its user agent and its 2-second gap), from a scratch clone, with the allowlist widened in the measuring script only:

| UTC | Request | Result |
|---|---|---|
| 07:05:52 | FinCEN FIN-2026-A002's linked PDF, `www.fincen.gov/system/files/2026-06/...Non-Work-Authorized-Populations.pdf` | 200, `application/pdf`, 527,118 bytes, no redirect; 12 pages, all with text, 37,025 characters |
| 07:06:00 | OFSI Citibank penalty notice PDF on `assets.publishing.service.gov.uk` | 200, `application/pdf`, 164,223 bytes, no redirect; 16 pages, all with text, 47,097 characters |
| 07:06:03 | OFAC `/media/936706/download?inline` (the Rice Lake settlement) | 200, `application/pdf`, 239,305 bytes, no redirect; 4 pages, 13,030 characters |

Offline, from B's pinned catalogue copies on this Mac (`evals/feeds/docs/`, gitignored), with no network:
- FinCEN: 20 of 20 landing pages link exactly one PDF, on `www.fincen.gov`; each pages to 1 page of 213 to 366 characters (median 291).
- OFSI: 12 of 20 link PDFs, 9 of them two each, 21 in all, every one on `assets.publishing.service.gov.uk`; pages of 898 to 13,705 characters.
- OFAC: 0 of 20 link a `.pdf`; every page links `/media/935656/download?inline`; pages of 603 to 125,387 characters.
- The four relevant OFSI items: Citibank (1 PDF), Sabre notice (1 PDF), the scam-email guidance (0, content in HTML), the Sabre press release (0, 4,337 characters of HTML).

Other measurements:
- **Costs.** Slice 1's extraction: mean US$0.73 over 14 runs (`evals/traces/SINGLE_VS_MULTI_2026-09-13.md`), a week-2 run at US$1.14, the one tracked telemetry run (ADV-2026-0013) at US$0.50, 29 turns and 250 s. B's triage: US$3.61 for 18 sessions.
- **B's pilot transcript** (`~/.claude/projects/-Users-danhartwig-fc-08-emerging-threat-intelligence/601d8903-....jsonl`, read only): the three unterminated ids are `feeds_triage` calls with input `__unparsedToolInput`, each answered by an `is_error` `tool_result` (decision 5).
- **The CLI.** `claude --version`: 2.1.269. `claude auth status`: `loggedIn: true`, `authMethod: "claude.ai"` (the interactive login, not the long-lived token), subscription `max`. `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` unset in this shell. From the installed CLI's code (read, not run with a token): a token in the environment reports `authMethod: "oauth_token"`. C2's owner step confirms it.
- **macOS.** 14.8.9 (23J631). `~/Library/LaunchAgents` exists, holding 6 entries, none for fc08. Nothing was created there.
- **The walkthrough** (decision 2). **Record placement** (decision 10).
- **A guard writing into the checkout.** A's ledger guard called `accept_run.main` with no data paths. Once `accept_run` copies run evidence, that wrote `data/feeds/runs/...` into the scratch checkout, including an eval run's under one mutation. Task 5 passes temporary paths everywhere.

### Verification done for this draft

- Every code block below was run in a scratch clone of `main` at `2375fd8`, under the session scratchpad, never in the repository.
- Each new or changed guard ends `HELD (0 failures)`, and each named mutation prints `HELD: the mutation is detected`:
  - `check_document_pages`: 7 checks, 4 mutations;
  - `check_feeds_extract`: 17 checks, 6 mutations;
  - `check_feeds_orchestrator`: 16 checks, 11 mutations, B's 6 among them;
  - `check_friday_run`: 10 checks, 6 mutations;
  - `check_accept_run`: 14 checks, 7 mutations;
  - `check_feeds_server`: 22 checks, all 8 of A's mutations;
  - `check_feeds_ledger`: 20 checks, all 8 mutations (`accept-allowed` retargeted).

  Every mutation ran with its own `PYTHONPYCACHEPREFIX`.
- A's and B's mutations were re-run after C's edits, and all hold: `check_feeds_triage` (all 14 named), `check_telemetry` (3), `check_tool_surface --mutate-queue`. `check_feeds_runner` and `check_feeds_score` hold, and B's `PROMPT_SHA256` is unchanged.
- `tools/check_all.py --cold` on the finished C1 tree: all guards pass except the walkthrough chain that Task 6 resolves by the planned republish. The four needs-PDFs guards were run by hand against copies of the PDFs, and all hold.
- **End to end:** a synthetic run was built with the real `friday()` (stub session and extractor) and accepted with the real `accept_run` into the scratch clone's tracked folders. Afterwards the whole cold suite, `check_review_gate`, `check_proposal_contract`, `check_twin_pairs` and `check_citations --all` all hold; `review.py --list` shows the new link with 0 quarantined.
- **Reproduction:** the edit blocks and full files below were re-applied mechanically to a fresh clone of `main`, and reproduced all 26 tested C1 files byte for byte.
- **Not verified:**
  - a real agent session (no model was run);
  - the linked-PDF fetch against the live site inside `feeds_extract` (only the three requests above);
  - whether the SDK stream carries the CLI's `is_error` `tool_result` as a `UserMessage` (the parser does, and the transcript shows the result; the dry run confirms it);
  - the republish itself.

### What I think is wrong or unworkable in the spec

1. **US$5 is not a hard ceiling under the spec's own rule.** The rule checks *before* starting an extraction, and an agent session can overshoot its own `max_budget_usd` by up to one turn. `check_friday_run`'s first case shows it on purpose: a session at US$2.50 and three extractions at US$1.30 give US$5.10. Definition-of-done item 6 ("no run exceeding US$5") is therefore a measured claim, not a guaranteed one. Recommended: measure the overshoot in the dry run, and add a margin to the start rule only if one appears.
2. **US$1.00 per extraction is below slice 1's upper tail** (mean US$0.73, one run at US$1.14). Some extractions will hit the cap and fail with no record, reported loudly. FinCEN PDFs are shorter than slice 1's FATF reports (12 pages measured, against up to 100), so it may rarely bite. The dry run measures it.
3. **"`feeds_extract` runs slice 1's extraction"**: see decision 9.
4. **"Deferred items stay unseen" needs a third decision.** With accept or drop only, a budget-deferred relevant item would have to be dropped for ever. `accept_run` takes `defer`, which writes nothing to the ledger.
5. **"Moved into the tracked folders" is COPIED here.** The inbox run stays whole until expired, so a failed acceptance loses nothing. The run's own evidence (items, triage verdicts with their reasons, the report) is copied to `data/feeds/runs/<run_id>/`, because the ledger records decisions but not why.
6. **The golden advisory list**: see decision 10.
7. **Reconciliation "fails" is undefined in the spec.** This plan separates bookkeeping that does not add up, which is RECONCILIATION_FAILED and needs a recorded override to accept, from work that was skipped, which is UNFINISHED: reported, and deferred by `accept_run`. A run with more than 10 new items is UNFINISHED by design.

### Expected spend (C1)

- **One dry run (Task 9), hard-capped at US$5.** Expected:
  - the orchestrator session: about US$0.20 to US$0.45 (B's triage sessions measured US$0.12 to US$0.33, plus the extraction requests);
  - up to 3 extractions at about US$0.50 to US$1.00 each.

  **Central estimate US$2 to US$3.50.**
- Everything else in C1 is offline and spends nothing. On the subscription token these are the SDK's notional prices, not a bill.

---

**Goal:** Build the live half of a Friday run and the only door into tracked data, in the order the spec's sections 1 and 2 name them:
- `feeds_extract` (a request that carries the invariants);
- the full-mode orchestrator;
- extraction in code within the run's budget;
- reconciliation in code;
- `report.md` on every run;
- `accept_run` end to end;
- one manual dry run.

**Architecture:**
- **Every document is loaded one way.** `schemas/citation_match.document_texts` and `PageIndex.from_document` load a PDF or a pinned HTML page. The extractor's prompt, `propose_link`, the review gate and `check_citations` all use them.
- **The agent requests; code extracts.** `feeds/extraction.py` holds the request rules and the advisory-id allocation. `feeds_extract` applies them.
- **The orchestrator has two modes.** `agents/orchestrate_feeds.py` gains a LIVE (full) mode beside B's EVAL (triage-only) mode.
- **The Friday run is one command.** `tools/friday_run.py` runs one live session, then slice 1's extractor per request within the budget. It writes `run.json`, and `feeds/reconcile.py` plus `feeds/report.py` turn the run's own files into a status and `report.md`.
- **Which runs are waiting.** `feeds/runs.py` classifies the runs in the inbox, the eval marker included.
- **The door.** `tools/accept_run.py` validates everything, then copies, and writes the ledger last.
- Every piece has a cold, mutation-verified guard in `tools/check_all.py`.

**Tech Stack:** Python 3 standard library plus what `.venv` holds (`claude-agent-sdk` 0.2.152, `mcp`, `pydantic`, `pypdf`). No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-slice2-live-intelligence-design.md`, sections 1, 2 and 5 (week 4), and section 6's C with definition-of-done items 4, 5 and 7. Built on `main` at `2375fd8`; where the A and B plans differ from the code, this plan follows the code.

## Global Constraints

- Run Python as `.venv/bin/python` from the repository root. Work on a branch (`slice2-c1`); never commit to `main` directly.
- No new dependencies. Never create `.bak`, `_backup`, `_before_*` or similar files. Never commit a file over 50 MB. Never use `git commit --no-verify`.
- The pre-commit hook runs `tools/check_all.py` (every guard, several minutes). It is the gate.
- Every `evals/check_*.py` is registered in `tools/check_all.py` in the SAME commit that adds it.
- A guard ends `HELD (0 failures)`, and each `--mutate` prints `HELD: the mutation is detected`. Run mutations with their own bytecode cache: `PYTHONPYCACHEPREFIX=/tmp/fc08-mut-<label> .venv/bin/python evals/<guard>.py --mutate <label>`.
- **A guard writes only temporary files.** Every guard that calls `accept_run`, `friday()` or the servers passes temporary inbox, data, ledger and advisory-list paths, and asserts the repository's `git status` is unchanged. This was measured, not assumed: see "A guard writing into the checkout" above.
- Commit messages start `Slice 2 C1:`. Never add a `Co-Authored-By` trailer. Push only when the owner asks.
- **Model runs:** only `tools/friday_run.py` starts agent sessions, and only in Task 9, after its STOP. Before it:
  - `unset ANTHROPIC_API_KEY FEEDS_CATALOGUE FEEDS_CATALOGUE_BATCH`;
  - `claude auth status` must not report `authMethod: api_key`.
- **Network:** only `feeds_list_new`, `feeds_fetch` and `feeds_extract` inside that run. No guard touches the network.
- **No launchd, no Keychain, no token** in C1.
- **The walkthrough:** Task 6 rebuilds and republishes once, on the owner's go, by CLAUDE.md's publish procedure. Nothing else in C1 changes the page.
- Evidence is never overwritten. The inbox is gitignored working data. `accept_run` copies, never moves, and refuses to overwrite any target.

## Rulings made while writing this plan

1. **The agent requests, code extracts** (decision 9). `feeds_extract` records one request per item, at most 3 per run, only for an item triaged relevant, and chooses and pins the document by rule (decision 1). `tools/friday_run.py` runs slice 1's `extract()` for each request after the session, in request order, each with its own `RunIdentity` naming the feeds run.
2. **The budget, all in `agents/orchestrate_feeds.py` and pinned:**
   - the session: US$1.50 and 80 turns (B's values, now guarded);
   - an extraction: US$1.00 and 60 turns;
   - a US$5.00 ceiling.

   An extraction starts only if spend + US$1.00 ≤ US$5.00. Otherwise it is **deferred for budget** and gets no advisory id. A cost that never arrived counts at its cap. 1.50 + 3 × 1.00 = 4.50 leaves US$0.50 for overshoot.
3. **Where an extraction writes, until it is accepted.** Its queue goes to `inbox/<run>/proposals/<extraction run id>.jsonl`, its record to `inbox/<run>/records/<ADV>.json`, and its telemetry to `inbox/<run>/telemetry/`.
   - The Knowledge Centre server derives the queue folder from the runner-set `NEXUS_FEEDS_RUN` through `feeds.inbox.proposals_dir`, the one definition `RunIdentity` also uses.
   - With no feeds run, the queue is `data/proposals/` exactly as in slice 1. `check_tool_surface`'s QUEUE_DIR agreement is unchanged.
4. **One loader for documents.** `document_texts` chooses by suffix (`.pdf`, `.html`, `.htm`; anything else is refused). The rules of the matcher are untouched. `pdf_to_pages` remains as a name for `agents/review_advisory.py`.
5. **Advisory ids** are allocated when an extraction starts, recorded in `inbox/<run>/advisory_ids.jsonl` before it runs, and never reused (decision 11). The year comes from the run's date.
6. **Run statuses, first match wins:**
   - `REFUSED`: `refusal.json`;
   - `FAILED`: the orchestrator session failed (auth, credit, the CLI);
   - `RECONCILIATION_FAILED`: bookkeeping that does not add up, or a session with a call lacking exactly one terminal event, or one that never completed;
   - `UNFINISHED`: skipped, deferred or failed items, a source down or with a changed layout, or a source never listed;
   - `NOTHING_NEW`;
   - `COMPLETE`.

   `accept_run` refuses `FAILED` and `RECONCILIATION_FAILED` without `--override-reconciliation "<reason>"`, and records the reason.
7. **`accept_run`** takes accept, drop or defer for every listed item.
   - **accept** is only for an extracted item. Its document, record, queue and telemetry are copied to `data/advisories/`, `data/feeds/records/`, `data/proposals/` and `data/telemetry/`, and its entry goes to `data/feeds/advisory_list.json`.
   - **drop** is written to the ledger.
   - **defer** is not written anywhere, so the item returns next Friday.

   The run's evidence goes to `data/feeds/runs/<run_id>/`. Everything is validated first, including the review gate's own re-check of every queue line. The ledger is written last, and a failure before it removes the copies this call made.
8. **The live-feed advisory list is separate** (decision 10). The gate's `recheck` reads it beside the golden list (`feed_list`, default `data/feeds/advisory_list.json`). An id in both is refused.
9. **The transcript's terminal event** (decision 5): one event, `source: "transcript"`, only for a call with a `tool_result` and no hook or permission event. The same rule applies in the orchestrator and in slice 1's extractor.
10. **An eval server does not list `feeds_extract`** (conditional registration at import, keyed on `FEEDS_CATALOGUE`). B's triage-only sessions keep exactly the four tools they were measured with, and B's `PROMPT_SHA256` is unchanged: the live prompt is B's bytes plus an appended extraction section.

## File map

| File | Task | Responsibility |
|---|---|---|
| `schemas/citation_match.py` | 1 | `document_texts`, `PageIndex.from_document` |
| `agents/extract_advisory.py` | 1, 2, 3, 6 | `document_pages` (PDF or HTML); `extract(..., run=)`; transcript terminal events; the resolver lines in `SYSTEM_PROMPT` (Task 6) |
| `mcp_server/knowledge_centre_server.py` | 1, 2 | `_page_index` by kind; the queue folder of a feeds run (`NEXUS_FEEDS_RUN`) |
| `governance/proposals.py` | 1, 5 | the gate's index by kind; `feed_list` beside the golden list |
| `evals/check_citations.py` | 1 | `from_document` (two lines) |
| `evals/check_document_pages.py` | 1 | NEW guard, 4 mutations |
| `feeds/sources.py` | 2 | `Source.document_hosts` |
| `feeds/inbox.py` | 2 | `proposals_dir`, the `proposals` / `records` / `telemetry` folder names |
| `feeds/extraction.py` | 2 | NEW: requests, outcomes, `document_choice`, `allocate_advisory_id` |
| `mcp_server/feeds_server.py` | 2 | `feeds_extract`, not registered in eval mode |
| `agents/run_identity.py` | 2 | `feeds_run`, `inbox_root`; queue path and env |
| `evals/check_feeds_extract.py` | 2 | NEW guard, 6 mutations |
| `evals/check_feeds_server.py` | 2 | five tools live, four in eval mode |
| `agents/permissions.py` | 3 | `FEEDS_FULL_WRITE_ALLOWLIST` |
| `agents/telemetry.py` | 3 | `terminated`, `record_unhooked` |
| `agents/orchestrate_feeds.py` | 3 | FULL REPLACEMENT: two modes, the budget constants, `server_env`, `run_session` |
| `evals/check_feeds_orchestrator.py` | 3 | FULL REPLACEMENT: both modes, the pinned budget, 11 mutations |
| `feeds/runs.py` | 4 | NEW: pending / accepted / eval / nothing, blocking, expire |
| `feeds/reconcile.py` | 4 | NEW: the run's reconciliation and status |
| `feeds/report.py` | 4 | NEW: `report.md` |
| `tools/friday_run.py` | 4 | NEW: the Friday run |
| `evals/check_friday_run.py` | 4 | NEW guard, 6 mutations |
| `tools/accept_run.py` | 5 | FULL REPLACEMENT: end to end |
| `evals/check_accept_run.py` | 5 | NEW guard, 7 mutations |
| `evals/check_feeds_ledger.py` | 5 | temporary data paths; `accept-allowed` retargeted |
| `tools/check_all.py` | 1, 2, 4, 5 | registration |
| `site/threat-intel/index.html`, `site/PUBLISHED` | 6 | the one planned rebuild and republish |
| `CLAUDE.md` | 7 | the record |
| `data/feeds/seen.json` | 8 | the seeded backlog (owner's go) |

---

### Task 1: one loader for a PDF or a pinned HTML page

**Files:**
- Create: `evals/check_document_pages.py`
- Modify: `schemas/citation_match.py`, `agents/extract_advisory.py`, `mcp_server/knowledge_centre_server.py`, `governance/proposals.py`, `evals/check_citations.py`, `tools/check_all.py`

**Interfaces:**
- Produces:
  - `schemas.citation_match.document_texts(path) -> List[str]`;
  - `PageIndex.from_document(path)`;
  - `agents.extract_advisory.document_pages(path)`, with `pdf_to_pages` as an alias.
- Consumed by Tasks 2 and 5, and by every existing caller that re-finds a quote.

- [ ] **Step 1: Write the guard first**

Create `evals/check_document_pages.py`:

```python
"""
Pin the one document loader: a PDF or a pinned HTML page, paged the same way by every caller (slice 2 C).

Usage:
    python evals/check_document_pages.py
    python evals/check_document_pages.py --mutate pdf-only       # document_texts pages only PDFs
    python evals/check_document_pages.py --mutate server-pdf     # propose_link's index is PDF-only again
    python evals/check_document_pages.py --mutate gate-pdf       # the review gate's re-check is PDF-only again
    python evals/check_document_pages.py --mutate extractor-pdf  # the extractor's prompt pages are PDF-only again

WHAT IT HOLDS. A live feed item may be an HTML page (every OFAC action; OFSI notices with no PDF). Its
quotes must be found, and a fabricated one refused, by every caller that re-finds a quote:
  loader      schemas.citation_match.document_texts / PageIndex.from_document give a PDF exactly
              from_pdf's pages and an HTML page exactly from_html's; any other suffix is refused;
  extractor   agents/extract_advisory.document_pages numbers those same pages "=== PAGE n ===";
  server      knowledge_centre_server._page_index finds a true quote on an HTML document's page and
              not a fabricated one;
  gate        governance.proposals.recheck passes a proposal quoting the HTML page and quarantines
              one quoting text the page does not hold;
  checker     evals/check_citations.check_record counts the true quote EXACT on the HTML page.

COLD. The HTML is the committed tests/fixtures/html page; the PDF is built here, in memory, with two
pages of known text. Temporary files only. No network, no model.

NOT A VACUOUS PASS. Each --mutate rewrites one module's source in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from schemas.proposal_contract import SCHEMA, proposal_id  # noqa: E402

HTML = ROOT / "tests" / "fixtures" / "html" / "ofsi_uk_financial_sanctions_faqs.html"
TRUE_QUOTE = "OFSI publishes FAQs providing short-form guidance and technical information on financial sanctions."
FABRICATED = "OFSI publishes a red-flag list of shell companies used to evade sanctions."
PDF_LINES = ("Trade based laundering moves value through invoices.", "Front companies disguise the origin of funds.")
CM = ROOT / "schemas" / "citation_match.py"
KC = ROOT / "mcp_server" / "knowledge_centre_server.py"
GATE = ROOT / "governance" / "proposals.py"
EXTRACTOR = ROOT / "agents" / "extract_advisory.py"
MUTATIONS = {
    "pdf-only": (CM, '    if suffix in (".html", ".htm"):\n        from schemas.html_pages import html_pages\n'
                     '        return html_pages(Path(path).read_bytes())\n', ""),
    "server-pdf": (KC, "    return PageIndex.from_document(pdf_path)", "    return PageIndex.from_pdf(pdf_path)"),
    "gate-pdf": (GATE, "PageIndex.from_document(pdf) if ok", "PageIndex.from_pdf(pdf) if ok"),
    "extractor-pdf": (EXTRACTOR, "enumerate(document_texts(path), start=1)",
                      "enumerate([p.extract_text() for p in __import__('pypdf').PdfReader(str(path)).pages], start=1)"),
}


def tiny_pdf(lines) -> bytes:
    """A valid PDF with one line of Helvetica text per page, built by hand (no dependency, no fixture)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for line in lines:
        stream = "BT /F1 12 Tf 72 720 Td (%s) Tj ET" % line
        objs.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>" % len(objs))
        kids.append("%d 0 R" % len(objs))
    objs[1] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(kids), len(kids))
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (n, body)).encode("latin-1")
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    out += "".join("%010d 00000 n \n" % o for o in offsets).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    return out


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


def checks(mutation) -> list:
    cm = load("schemas.citation_match", CM, mutation)  # every module below imports THIS one
    kc = load("kc_under_test", KC, mutation)
    gate = load("governance.proposals", GATE, mutation)
    ex = load("extractor_under_test", EXTRACTOR, mutation)
    import check_citations
    check_citations.PageIndex = cm.PageIndex
    out = []

    def attempt(fn):
        try:
            return fn()
        except Exception as exc:  # a mutation that makes a loader raise must fail a check, not the guard
            return "RAISED %s: %s" % (type(exc).__name__, exc)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pdf = tmp / "doc.pdf"
        pdf.write_bytes(tiny_pdf(PDF_LINES))
        html = tmp / ("%s.html" % hashlib.sha256(HTML.read_bytes()).hexdigest())
        html.write_bytes(HTML.read_bytes())
        txt = tmp / "doc.txt"
        txt.write_text("text", encoding="utf-8")

        from_pdf = cm.PageIndex.from_pdf(pdf).pages
        got = attempt(lambda: cm.PageIndex.from_document(pdf).pages)
        out.append((got == from_pdf and len(got) == 2 and "invoices" in got[0],
                    "a PDF is paged by from_document exactly as by from_pdf", str(got)[:80]))
        want = cm.PageIndex.from_html(HTML.read_bytes()).pages
        got = attempt(lambda: cm.PageIndex.from_document(html).pages)
        out.append((got == want and len(want) >= 1, "an HTML page is paged by from_document exactly as by from_html",
                    "%s pages" % (len(got) if isinstance(got, list) else got)))
        got = attempt(lambda: cm.document_texts(txt))
        out.append((isinstance(got, str) and "ValueError" in got, "any other suffix is refused", str(got)[:80]))

        got = attempt(lambda: ex.document_pages(html))
        from schemas.html_pages import html_pages
        raw = html_pages(HTML.read_bytes())
        out.append((got == ["=== PAGE %d ===\n%s" % (n, t.strip()) for n, t in enumerate(raw, 1)],
                    "the extractor's prompt pages of an HTML document are its html_pages, numbered",
                    str(got)[:80]))

        sha = hashlib.sha256(html.read_bytes()).hexdigest()
        kc._page_index.cache_clear()
        index = attempt(lambda: kc._page_index(str(html), sha))
        ok = not isinstance(index, str) and index.locate(1, TRUE_QUOTE).ok and not index.locate(1, FABRICATED).ok
        out.append((ok, "propose_link's index finds a true quote on the HTML page and not a fabricated one",
                    str(index)[:80]))

        advisories = tmp / "advisories"
        advisories.mkdir()
        (advisories / html.name).write_bytes(html.read_bytes())
        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0099", "file": html.name,
                                                     "sha256": sha}]}), encoding="utf-8")
        run_id = "adv-2026-0099-extractor-0123456789"
        lines = []
        for quote in (TRUE_QUOTE, FABRICATED):
            body = {"schema": SCHEMA, "run_id": run_id, "stage": "extractor", "advisory_id": "ADV-2026-0099",
                    "document_sha256": sha, "typology_id": "SAN001", "emergent_label": None,
                    "rationale": "The page describes sanctions guidance.", "confidence": "low",
                    "citations": [{"page": 1, "quote": quote}]}
            lines.append(dict(body, proposal_id=proposal_id(body), proposed_at="2026-10-02T09:00:00+00:00"))
        proposals = [gate.Proposal.from_line(d, source_file="%s.jsonl" % run_id) for d in lines]
        got = attempt(lambda: gate.recheck(proposals, advisory_list=alist, advisories_dir=advisories))
        ok = (not isinstance(got, str) and [p.citations[0][1] for p in got[0]] == [TRUE_QUOTE]
              and len(got[1]) == 1 and "not in the document" in got[1][0].reason)
        out.append((ok, "the gate passes the proposal quoting the HTML page and quarantines the fabricated one",
                    str(got)[:120] if isinstance(got, str) else "clean %d, quarantined %s" % (
                        len(got[0]), [q.reason[:50] for q in got[1]])))

        record = {"advisory_id": "ADV-2026-0099", "typologies": [
            {"typology_id": "SAN001", "citations": [{"page": 1, "quote": TRUE_QUOTE}]}], "actors": [], "indicators": []}
        rpath = tmp / "ADV-2026-0099.json"
        rpath.write_text(json.dumps(record), encoding="utf-8")
        got = attempt(lambda: check_citations.check_record(rpath, html, verbose=False))
        out.append((not isinstance(got, str) and got[0] == 1 and got[1] == 1,
                    "check_citations counts the true quote EXACT on the HTML page", str(got)[:80]))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the one document loader")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one caller in memory; a check MUST fail")
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

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/bin/python evals/check_document_pages.py
```

Expected: it dies on the missing `document_texts`, or reports FAIL lines. That is the missing code, not a defect.

- [ ] **Step 3: Make the edits**

In `schemas/citation_match.py` (edit `t1-citation-imports`), replace:

```python
from dataclasses import dataclass
from typing import Sequence, Tuple
```

with:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple
```

In `schemas/citation_match.py` (edit `t1-citation-from-document`), replace:

```python
    @classmethod
    def from_html(cls, raw: bytes) -> "PageIndex":
        """Pages of a pinned HTML document, by schemas/html_pages.py's fixed rule (slice 2)."""
        from schemas.html_pages import html_pages
        return cls(html_pages(raw))
```

with:

```python
    @classmethod
    def from_html(cls, raw: bytes) -> "PageIndex":
        """Pages of a pinned HTML document, by schemas/html_pages.py's fixed rule (slice 2)."""
        from schemas.html_pages import html_pages
        return cls(html_pages(raw))

    @classmethod
    def from_document(cls, path) -> "PageIndex":
        """A pinned document's pages, chosen by its kind (slice 2 C). THE loader for every caller that
        re-finds a quote -- the extractor's prompt, propose_link, the review gate, check_citations -- so a
        live feed's HTML advisory is paged by the same rule everywhere, and a PDF exactly as before."""
        return cls(document_texts(path))
```

In `schemas/citation_match.py` (edit `t1-citation-document-texts`), replace:

```python
@dataclass(frozen=True)
class Located:
```

with:

```python
DOCUMENT_SUFFIXES = (".pdf", ".html", ".htm")


def document_texts(path) -> List[str]:
    """The raw text of each page of a pinned document: pypdf for a .pdf, schemas/html_pages for .html/.htm.

    By SUFFIX, never by sniffing, so the choice is visible in the file name every caller already holds
    (feeds/inbox.py names a pinned file <sha256>.pdf or <sha256>.html from its content type). Anything
    else is refused: a document that cannot be paged cannot carry a citation.
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        return [p.extract_text() or "" for p in PdfReader(str(path)).pages]
    if suffix in (".html", ".htm"):
        from schemas.html_pages import html_pages
        return html_pages(Path(path).read_bytes())
    raise ValueError("%s is neither a PDF nor an HTML document (%s)" % (path, ", ".join(DOCUMENT_SUFFIXES)))


@dataclass(frozen=True)
class Located:
```

In `agents/extract_advisory.py` (edit `t1-extractor-pages`), replace:

```python
def pdf_to_pages(path: Path) -> list:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append("=== PAGE %d ===\n%s" % (i, text.strip()))
    return pages
```

with:

```python
def document_pages(path: Path) -> list:
    """The prompt's pages, "=== PAGE n ===" each: a PDF through pypdf exactly as before, a pinned HTML
    page (a live feed item, slice 2 C) through schemas/html_pages -- the pages propose_link and the
    review gate re-find every quote on, through the same schemas.citation_match.document_texts."""
    return ["=== PAGE %d ===\n%s" % (i, (text or "").strip()) for i, text in enumerate(document_texts(path), start=1)]


# The name agents/review_advisory.py imports; a PDF's pages are unchanged by the rename.
pdf_to_pages = document_pages
```

In `agents/extract_advisory.py` (edit `t1-extractor-imports`), replace:

```python
from pypdf import PdfReader

```

with:

```python

```

In `agents/extract_advisory.py` (edit `t1-extractor-import-texts`), replace:

```python
from schemas.citation_match import file_sha256  # noqa: E402
```

with:

```python
from schemas.citation_match import document_texts, file_sha256  # noqa: E402
```

In `agents/extract_advisory.py` (edit `t1-extractor-use`), replace:

```python
    pages = pdf_to_pages(path)
```

with:

```python
    pages = document_pages(path)
```

In `mcp_server/knowledge_centre_server.py` (edit `t1-server-index`), replace:

```python
    return PageIndex.from_pdf(pdf_path)
```

with:

```python
    return PageIndex.from_document(pdf_path)  # a PDF, or a live feed's pinned HTML (slice 2 C)
```

In `governance/proposals.py` (edit `t1-gate-index`), replace:

```python
            indexes[aid] = PageIndex.from_pdf(pdf) if ok else None
```

with:

```python
            indexes[aid] = PageIndex.from_document(pdf) if ok else None  # PDF or pinned HTML
```

In `evals/check_citations.py` (edit `t1-citations-one`), replace:

```python
    index = PageIndex.from_pdf(pdf_path)
```

with:

```python
    index = PageIndex.from_document(pdf_path)
```

In `evals/check_citations.py` (edit `t1-citations-all`), replace:

```python
        rows = check_record_citations(advisory_id, record, PageIndex.from_pdf(pdf_path))
```

with:

```python
        rows = check_record_citations(advisory_id, record, PageIndex.from_document(pdf_path))
```


- [ ] **Step 4: Register the guard**

In `tools/check_all.py` (edit `t1-check-all`), replace:

```python
    ("check_feeds_score", ["evals/check_feeds_score.py"], "cold"),
```

with:

```python
    ("check_feeds_score", ["evals/check_feeds_score.py"], "cold"),
    ("check_document_pages", ["evals/check_document_pages.py"], "cold"),
```


- [ ] **Step 5: Run it, and each mutation**

```bash
.venv/bin/python evals/check_document_pages.py
for m in pdf-only server-pdf gate-pdf extractor-pdf; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_document_pages.py --mutate $m | tail -1
done
.venv/bin/python evals/check_citations.py --all && .venv/bin/python evals/check_review_gate.py | tail -1
```

Expected:
- `HELD (0 failures)`, 7 checks;
- each mutation `HELD: the mutation is detected` (`pdf-only` fails 5 checks, the others 1 each);
- `check_citations --all` unchanged: 713 checked, 12 attested, 0 new;
- `check_review_gate` `HELD`.

- [ ] **Step 6: Commit**

```bash
git add schemas/citation_match.py agents/extract_advisory.py mcp_server/knowledge_centre_server.py governance/proposals.py evals/check_citations.py evals/check_document_pages.py tools/check_all.py
git commit -m "Slice 2 C1: one loader for a PDF or a pinned HTML page, used by every caller that re-finds a quote"
```

---

### Task 2: `feeds_extract`, the extraction document, and an extraction's queue in the inbox

**Files:**
- Create: `feeds/extraction.py`, `evals/check_feeds_extract.py`
- Modify: `feeds/sources.py`, `feeds/inbox.py`, `mcp_server/feeds_server.py`, `mcp_server/knowledge_centre_server.py`, `agents/run_identity.py`, `agents/extract_advisory.py` (the `run=` parameter only; the prompt is Task 6), `evals/check_feeds_server.py`, `tools/check_all.py`

**Interfaces:**
- Consumes: A's `feeds.inbox` and `feeds.http`, B's `feeds.triage` (`load`, `pinned_document`, `page_texts`, `REJECTED`), and Task 1.
- Produces, for Tasks 3 to 5:
  - `feeds.extraction`:
    - `REQUESTS`, `OUTCOMES`, `ALLOCATIONS`, `MAX_PER_RUN = 3`;
    - `request(run_id, key, http_get, root)`;
    - `load_requests`, `load_outcomes`, `append_outcome`, `load_allocations`;
    - `document_choice(item)`;
    - `next_advisory_id(year, lists, root)` and `allocate_advisory_id(run_id, key, year, lists, root)`.
  - A request line: `key, source, item_id, run_id, requested_at, chosen (pinned|linked), ignored_links, document {path, sha256, content_type, bytes, url, pages, text_pages, page_error}, error`.
  - The tool `feeds_extract(item_key)`, open-world, not read-only, and **not registered when `FEEDS_CATALOGUE` is set**.
  - `feeds.inbox.proposals_dir(run_id, root)`.
  - `RunIdentity(..., feeds_run=, inbox_root=)`, whose `queue_path` is `inbox/<feeds run>/proposals/<run_id>.jsonl` and whose `env()` adds `NEXUS_FEEDS_RUN`.
  - `extract(..., run=)`.

- [ ] **Step 1: Write the guard first**

Create `evals/check_feeds_extract.py`:

```python
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

WHAT IT HOLDS:
  relevant only  a request is refused for an item not listed, with no verdict, or triaged not_relevant;
  once, capped   a second request for an item is refused; the fourth request in a run is refused;
  the document   a pinned page linking ONE PDF on its source's document hosts gets that PDF, fetched with
                 exactly those hosts and PDF only, pinned under docs/<sha256>.pdf; a page linking none is
                 extracted as itself; two is refused as ambiguous; a link on any other host is ignored and
                 recorded; a failed fetch is recorded, not retried;
  ids            next_advisory_id is one past every id in the advisory list and every id any run allocated,
                 expired runs included;
  the queue      an extraction naming its feeds run writes inbox/<run>/proposals/<run_id>.jsonl: the runner's
                 RunIdentity and the server derive the SAME path; a malformed feeds run is refused; with no
                 feeds run the queue is data/proposals/ exactly as in slice 1;
  the tool       the server's feeds_extract applies these rules under a run identity and refuses without one;
  inbox only     every file written is inside the temporary inbox; the repository's git status is unchanged.

COLD. Stubbed HTTP, temporary inbox and advisory list. No network, no model.

NOT A VACUOUS PASS. Each --mutate rewrites feeds/extraction.py or the Knowledge Centre server in memory;
at least one check must fail.
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
sys.path.insert(0, str(ROOT / "evals"))
import feeds  # noqa: E402
from feeds import http as fh, inbox, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem  # noqa: E402
from feeds.sources import linked_pdfs  # noqa: E402
from check_document_pages import tiny_pdf  # noqa: E402

EXTRACTION = ROOT / "feeds" / "extraction.py"
KC = ROOT / "mcp_server" / "knowledge_centre_server.py"
SERVER = ROOT / "mcp_server" / "feeds_server.py"
RUN = "feeds-2026-10-02-ccc333"
PDF_URL = "https://www.fincen.gov/system/files/2026-10/advisory.pdf"
SENTENCE = "This advisory describes red flags for trade-based money laundering through shell companies."
MUTATIONS = {
    "no-verdict-check": (EXTRACTION, "    if verdict is None or verdict[\"verdict\"] != feeds_triage.RELEVANT:\n",
                         "    if False:\n"),
    "no-cap": (EXTRACTION, "MAX_PER_RUN = 3\n", "MAX_PER_RUN = 30\n"),
    "second-request": (EXTRACTION, "    if any(r[\"key\"] == key for r in done):\n", "    if False:\n"),
    "any-host": (EXTRACTION, " and (urlsplit(u).netloc or \"\").lower() in hosts]", "]"),
    "reuse-id": (EXTRACTION, "        taken += _ids_in(path)\n", "        pass\n"),
    "queue-escape": (KC, "    folder = feeds_inbox.proposals_dir(feeds_run, FEEDS_INBOX_ROOT) if feeds_run else QUEUE_DIR\n",
                     "    folder = QUEUE_DIR\n"),
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
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append((url, sorted(allowed_hosts), sorted(allowed_types)))
        if self.fail:
            raise fh.FetchRefused("stub: connection reset")
        return fh.Fetched(url, url, "application/pdf", tiny_pdf(["Advisory text on shell companies."]))


def setup(tmp: Path, docs: dict) -> list:
    """A run that listed one fincen item per entry of `docs` (name -> page bytes), each fetched and pinned."""
    state = {"run_id": RUN, "sources": {"fincen": {"status": "ok", "items": []}}}
    keys = []
    for name, raw in docs.items():
        it = FeedItem("fincen", name, "Advisory %s" % name, "https://www.fincen.gov/resources/advisories/%s" % name,
                      "2026-10-01")
        rel = inbox.write_file(RUN, "docs/%s.html" % __import__("hashlib").sha256(raw).hexdigest(), raw, tmp)
        doc = {"path": rel, "sha256": __import__("hashlib").sha256(raw).hexdigest(), "content_type": "text/html",
               "bytes": len(raw), "final_url": it.url, "pages": 1, "text_pages": 1, "page_error": None,
               "linked_pdfs": linked_pdfs(raw, it.url)}
        state["sources"]["fincen"]["items"].append(dict(it.to_json(), document=doc))
        keys.append(it.key)
    inbox.save(RUN, state, tmp)
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
        keys = setup(box, {"a1": page([PDF_URL, other]), "a2": page(), "a3": page([PDF_URL]),
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
                    and reqs[0]["chosen"] == "linked" and reqs[0]["ignored_links"] == [other]
                    and pinned.exists() and pinned.name == "%s.pdf" % reqs[0]["document"]["sha256"],
                    "a page linking one PDF on the document hosts: that PDF, fetched with those hosts and PDF only, "
                    "pinned by sha256; the off-host link is ignored and recorded", "%s %s" % (said[1][:60], stub.calls)))
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

        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020"}, {"advisory_id": "ADV-2025-0400"}]}),
                         encoding="utf-8")
        first = ex.allocate_advisory_id(RUN, a1, 2026, alist, box)
        expired = box / "expired" / "feeds-2026-09-01-ddd444"
        expired.mkdir(parents=True)
        (expired / ex.ALLOCATIONS).write_text(json.dumps({"key": "k", "advisory_id": "ADV-2026-0023"}) + "\n",
                                              encoding="utf-8")
        got = ex.next_advisory_id(2026, alist, box)
        out.append((first == "ADV-2026-0021" and got == "ADV-2026-0024" and ex.load_allocations(RUN, box) == {a1: first}
                    and ex.next_advisory_id(2027, alist, box) == "ADV-2027-0001",
                    "the next advisory id is past the list and every run's allocations, expired runs included", got))

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
        out.append((all(str(w).startswith("inbox/") or w.name in ("advisory_list.json", "doc.html") for w in written),
                    "every file written is inside the temporary inbox", "%d files" % len(written)))
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
```

- [ ] **Step 2: Create `feeds/extraction.py`**

```python
"""
Extraction for one feeds run (slice 2 C; spec sections 1 and 2): the agent REQUESTS, code EXTRACTS.

  inbox/<run_id>/extractions.jsonl      one REQUEST per item, appended by feeds_extract (the agent's tool)
  inbox/<run_id>/extraction_runs.jsonl  one OUTCOME per request, appended by tools/friday_run.py after the
                                        orchestrator stops: extracted, failed, or deferred for budget
  inbox/<run_id>/advisory_ids.jsonl     one line per advisory id ALLOCATED, written BEFORE its extraction starts

Each rule is carried here, whatever the agent intends:
  relevant only  a request needs the item's triage verdict to be RELEVANT (feeds/triage.py);
  once, capped   one request per item; at most MAX_PER_RUN (3) per run -- the fourth is refused, and that
                 item stays unfinished and returns next run;
  the document   what is extracted is chosen by RULE, never by the agent (document_choice): a pinned PDF is
                 itself; a pinned HTML page linking exactly ONE PDF on its source's document_hosts is that
                 PDF, fetched and pinned now, through feeds.http.get (https, exact host, PDF only, the size
                 cap, the 2-second gap); a page linking none is the page itself; a page linking several is
                 refused as ambiguous, for a person. The URL comes from the PINNED page's bytes, never an
                 argument, so the choice is re-derivable from the inbox by committed code.
Every refusal starts "Rejected:" (feeds.triage.REJECTED), which telemetry counts as REFUSED.

Advisory ids are allocated by allocate_advisory_id() when the runner STARTS an extraction, never here: a
request deferred for budget consumes no id. The allocation is written before the extraction runs, so a run
that dies mid-extraction still holds its id. An id in any run's allocations (expired runs included) is never
allocated again; accept_run keeps it, so the id a proposal carries is the id it is accepted under.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from feeds import inbox, triage as feeds_triage
from feeds.sources import MAX_DOCUMENT_BYTES, SOURCES
from feeds.http import FetchRefused

REQUESTS = "extractions.jsonl"
OUTCOMES = "extraction_runs.jsonl"
ALLOCATIONS = "advisory_ids.jsonl"
MAX_PER_RUN = 3
PDF_TYPES = frozenset({"application/pdf"})
ADVISORY_ID = re.compile(r"\AADV-(\d{4})-(\d{4})\Z")
REJECTED = feeds_triage.REJECTED


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lines(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append(run_id: str, name: str, entry: dict, root: Path) -> None:
    folder = inbox.run_dir(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / name, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def load_requests(run_id: str, root: Path = inbox.INBOX_ROOT) -> List[dict]:
    """The run's requests in the order the agent made them; a second line for one item is corruption."""
    out, seen = [], set()
    for entry in _lines(inbox.run_dir(run_id, root) / REQUESTS):
        if entry["key"] in seen:
            raise ValueError("%s: %s is requested twice" % (REQUESTS, entry["key"]))
        seen.add(entry["key"])
        out.append(entry)
    return out


def load_outcomes(run_id: str, root: Path = inbox.INBOX_ROOT) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for entry in _lines(inbox.run_dir(run_id, root) / OUTCOMES):
        if entry["key"] in out:
            raise ValueError("%s: %s has two outcomes" % (OUTCOMES, entry["key"]))
        out[entry["key"]] = entry
    return out


def append_outcome(run_id: str, outcome: dict, root: Path = inbox.INBOX_ROOT) -> None:
    if outcome["key"] in load_outcomes(run_id, root):
        raise ValueError("%s already has an outcome in run %s" % (outcome["key"], run_id))
    _append(run_id, OUTCOMES, outcome, root)


def document_choice(item: dict) -> Tuple[str, List[str], List[str]]:
    """(kind, candidate URLs, ignored URLs) for an item's pinned document; kind is pinned|linked|ambiguous."""
    doc = item["document"]
    if doc["content_type"] == "application/pdf":
        return "pinned", [], []
    hosts = SOURCES[item["source"]].document_hosts
    links = doc.get("linked_pdfs") or []
    ok = [u for u in links if urlsplit(u).scheme == "https" and (urlsplit(u).netloc or "").lower() in hosts]
    ignored = [u for u in links if u not in ok]
    if not ok:
        return "pinned", [], ignored
    return ("linked" if len(ok) == 1 else "ambiguous"), ok, ignored


def request(run_id: str, key: str, http_get, root: Path = inbox.INBOX_ROOT) -> Tuple[bool, str]:
    """Record one extraction request, or refuse it. Returns (recorded, the message the agent sees)."""
    state = inbox.load(run_id, root)
    item = inbox.find_item(state, key)
    if item is None:
        return False, "%s %s was not listed as new in this run." % (REJECTED, key)
    verdict = feeds_triage.load(run_id, root).get(key)
    if verdict is None or verdict["verdict"] != feeds_triage.RELEVANT:
        return False, "%s %s has %s; only an item triaged relevant is extracted." % (
            REJECTED, key, "no verdict" if verdict is None else "the verdict %s" % verdict["verdict"])
    done = load_requests(run_id, root)
    if any(r["key"] == key for r in done):
        return False, "%s %s is already queued for extraction in this run." % (REJECTED, key)
    if len(done) >= MAX_PER_RUN:
        return False, ("%s this run has queued its cap of %d extractions; %s stays unfinished and returns next run."
                       % (REJECTED, MAX_PER_RUN, key))
    path, refusal = feeds_triage.pinned_document(run_id, item, root)
    if path is None:
        return False, refusal
    kind, urls, ignored = document_choice(item)
    if kind == "ambiguous":
        return False, ("%s %s's page links %d PDFs on %s's document hosts (%s); which one is the publication is a "
                       "person's call, not this run's." % (REJECTED, key, len(urls), item["source"], ", ".join(urls)))
    entry = {"key": key, "source": item["source"], "item_id": item["item_id"], "run_id": run_id,
             "requested_at": _now(), "chosen": kind, "ignored_links": ignored, "document": None, "error": None}
    if kind == "pinned":
        entry["document"] = dict(item["document"], url=item["document"]["final_url"])
    else:
        src = SOURCES[item["source"]]
        try:
            got = http_get(urls[0], allowed_hosts=src.document_hosts, allowed_types=PDF_TYPES,
                           max_bytes=MAX_DOCUMENT_BYTES)
        except FetchRefused as exc:
            entry["error"] = "the linked PDF could not be fetched: %s" % exc
            _append(run_id, REQUESTS, entry, root)
            return True, "Failed: %s is queued but its PDF could not be fetched (%s); it will be reported." % (key, exc)
        sha = hashlib.sha256(got.body).hexdigest()
        rel = inbox.write_file(run_id, "docs/%s.pdf" % sha, got.body, root)
        texts = feeds_triage.page_texts(inbox.run_dir(run_id, root) / rel)
        entry["document"] = {"path": rel, "sha256": sha, "content_type": got.content_type, "bytes": len(got.body),
                             "url": got.final_url, "fetched_at": _now(), "pages": len(texts),
                             "text_pages": sum(1 for t in texts if t.strip()),
                             "page_error": None if any(t.strip() for t in texts) else "no text; not citable"}
        if entry["document"]["page_error"]:
            entry["error"] = entry["document"]["page_error"]
    _append(run_id, REQUESTS, entry, root)
    doc = entry["document"]
    return True, "Queued: %s will be extracted after this session, from %s (%d page(s))." % (
        key, "its linked PDF %s" % doc["url"] if kind == "linked" else "the page itself", doc["pages"])


def _ids_in(path: Path) -> List[str]:
    return [e.get("advisory_id") for e in _lines(path) if e.get("advisory_id")]


def next_advisory_id(year: int, advisory_lists, inbox_root: Path = inbox.INBOX_ROOT) -> str:
    """The next ADV-<year>-NNNN after every id in the advisory lists (the golden one and the live-feed one) and
    every id any run has allocated, including expired runs (inbox/expired/): an id that ever reached a record
    or a queue is never reused. `advisory_lists` is one path or several; a list that does not exist yet is empty."""
    paths = [advisory_lists] if isinstance(advisory_lists, (str, Path)) else list(advisory_lists)
    taken = [a["advisory_id"] for p in paths if Path(p).exists()
             for a in json.loads(Path(p).read_text(encoding="utf-8"))["advisories"]]
    for path in sorted(Path(inbox_root).glob("**/%s" % ALLOCATIONS)):
        taken += _ids_in(path)
    numbers = [int(m.group(2)) for m in map(ADVISORY_ID.match, taken) if m and int(m.group(1)) == year]
    return "ADV-%04d-%04d" % (year, max(numbers, default=0) + 1)


def allocate_advisory_id(run_id: str, key: str, year: int, advisory_lists,
                         root: Path = inbox.INBOX_ROOT) -> str:
    """Allocate the next advisory id to `key` and record it in the run's allocations BEFORE extraction."""
    advisory_id = next_advisory_id(year, advisory_lists, root)
    _append(run_id, ALLOCATIONS, {"key": key, "advisory_id": advisory_id, "allocated_at": _now()}, root)
    return advisory_id


def load_allocations(run_id: str, root: Path = inbox.INBOX_ROOT) -> Dict[str, str]:
    return {e["key"]: e["advisory_id"] for e in _lines(inbox.run_dir(run_id, root) / ALLOCATIONS)}
```

- [ ] **Step 3: Make the edits**

In `feeds/sources.py` (edit `t2-sources-field`), replace:

```python
    hosts: FrozenSet[str]  # the listing's host and every item URL's host
    parse: Callable[[bytes], List[FeedItem]]
```

with:

```python
    hosts: FrozenSet[str]  # the listing's host and every item URL's host
    parse: Callable[[bytes], List[FeedItem]]
    # Slice 2 C: hosts a PDF LINKED from an item's pinned page may be fetched from, for extraction only
    # (feeds/extraction.py). Measured 2026-09-26/28: FinCEN links its advisory PDF on www.fincen.gov, OFSI
    # on assets.publishing.service.gov.uk; OFAC's action IS the page, and its /media/ downloads are not
    # followed (every OFAC page links /media/935656, so "the" document is not identifiable by rule).
    document_hosts: FrozenSet[str] = frozenset()
```

In `feeds/sources.py` (edit `t2-sources-fincen`), replace:

```python
                     frozenset({"text/html"}), frozenset({"www.fincen.gov"}), parse_fincen),
```

with:

```python
                     frozenset({"text/html"}), frozenset({"www.fincen.gov"}), parse_fincen,
                     frozenset({"www.fincen.gov"})),
```

In `feeds/sources.py` (edit `t2-sources-ofsi`), replace:

```python
                   "atom", frozenset({"application/atom+xml"}), frozenset({"www.gov.uk"}), parse_ofsi),
```

with:

```python
                   "atom", frozenset({"application/atom+xml"}), frozenset({"www.gov.uk"}), parse_ofsi,
                   frozenset({"assets.publishing.service.gov.uk"})),
```

In `mcp_server/feeds_server.py` (edit `t2-server-import`), replace:

```python
from feeds import http as feeds_http, inbox, ledger, triage as feeds_triage  # noqa: E402
```

with:

```python
from feeds import extraction as feeds_extraction, http as feeds_http, inbox, ledger, triage as feeds_triage  # noqa: E402
```

In `mcp_server/feeds_server.py` (edit `t2-server-tool`), replace:

```python
if __name__ == "__main__":
    mcp.run()
```

with:

```python
class ExtractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(..., pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$",
                          description="A key triaged relevant in this run")


async def extract(params: ExtractInput) -> str:
    """
    Queue a relevant item for extraction after this session. You do not extract, and you do not see
    the result: the run extracts in code once you finish, within its budget.

    Refused unless the item is triaged relevant in this run; one request per item; at most 3 per run.
    The tool chooses what is extracted: the publication's own PDF when the page you read links exactly
    one on the source's document hosts (it fetches and pins it now), otherwise the page itself.
    """
    run_id = _run_id()
    if run_id is None:
        return NO_RUN
    async with _STATE_LOCK:
        return feeds_extraction.request(run_id, params.item_key, HTTP_GET, INBOX_ROOT)[1]


# EVAL MODE never sees extraction (slice 2 C): the tool is not even listed to a session the eval runner
# starts, so B's triage-only measurement keeps exactly the four tools it was measured with.
if not os.environ.get(CATALOGUE_ENV):
    mcp.tool(
        name="feeds_extract",
        annotations={"title": "Queue an item for extraction", "readOnlyHint": False, "destructiveHint": False,
                     "idempotentHint": False, "openWorldHint": True},
    )(extract)


if __name__ == "__main__":
    mcp.run()
```

In `mcp_server/knowledge_centre_server.py` (edit `t2-kc-import`), replace:

```python
from schemas.actor_match import resolve as resolve_names  # noqa: E402
```

with:

```python
from schemas.actor_match import resolve as resolve_names  # noqa: E402
from feeds import inbox as feeds_inbox  # noqa: E402
```

In `mcp_server/knowledge_centre_server.py` (edit `t2-kc-queue-const`), replace:

```python
QUEUE_DIR = ROOT / "data" / "proposals"
```

with:

```python
QUEUE_DIR = ROOT / "data" / "proposals"
# Slice 2 C: an extraction a feeds run starts writes its queue into THAT run's inbox,
# inbox/<feeds run>/proposals/<run_id>.jsonl, gitignored until tools/accept_run.py moves it to QUEUE_DIR.
# The runner names the feeds run (never a path); the server derives the folder through
# feeds.inbox.proposals_dir, the one definition the runner uses too, and refuses a malformed run id.
FEEDS_RUN_ENV = "NEXUS_FEEDS_RUN"
FEEDS_INBOX_ROOT = feeds_inbox.INBOX_ROOT
```

In `mcp_server/knowledge_centre_server.py` (edit `t2-kc-proposals-path`), replace:

```python
def _proposals_path(run: dict) -> Path:
    return QUEUE_DIR / ("%s.jsonl" % run["NEXUS_RUN_ID"])
```

with:

```python
def _proposals_path(run: dict) -> Path:
    feeds_run = os.environ.get(FEEDS_RUN_ENV, "")
    folder = feeds_inbox.proposals_dir(feeds_run, FEEDS_INBOX_ROOT) if feeds_run else QUEUE_DIR
    return folder / ("%s.jsonl" % run["NEXUS_RUN_ID"])
```

In `mcp_server/knowledge_centre_server.py` (edit `t2-kc-refuse-queue`), replace:

```python
    want = _proposals_path(run)
    if Path(run[QUEUE_ENV]).resolve() != want.resolve():
```

with:

```python
    try:
        want = _proposals_path(run)
    except ValueError as exc:  # a malformed feeds run id: no folder is derived from it
        return "Rejected: %s." % exc
    if Path(run[QUEUE_ENV]).resolve() != want.resolve():
```

In `feeds/inbox.py` (edit `t2-inbox-dirs`), replace:

```python
def load(run_id: str, root: Path = INBOX_ROOT) -> dict:
```

with:

```python
# Slice 2 C: what an extraction the run starts writes, inside the run's own folder.
PROPOSALS, RECORDS, TELEMETRY = "proposals", "records", "telemetry"


def proposals_dir(run_id: str, root: Path = INBOX_ROOT) -> Path:
    """The ONE definition of where a feeds run's extraction queues go; the runner and the server both call it."""
    return run_dir(run_id, root) / PROPOSALS


def load(run_id: str, root: Path = INBOX_ROOT) -> dict:
```

In `agents/run_identity.py` (edit `t2-identity-imports`), replace:

```python
from dataclasses import dataclass
from pathlib import Path
```

with:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
```

In `agents/run_identity.py` (edit `t2-identity-feeds-import`), replace:

```python
from schemas.proposal_contract import STAGES  # noqa: E402
```

with:

```python
from schemas.proposal_contract import STAGES  # noqa: E402
from feeds import inbox as feeds_inbox  # noqa: E402
```

In `agents/run_identity.py` (edit `t2-identity-fields`), replace:

```python
    pdf_path: Path
    pdf_sha256: str

    def __post_init__(self) -> None:
```

with:

```python
    pdf_path: Path
    pdf_sha256: str
    # Slice 2 C: the feeds run that started this extraction, if any. Its queue then lives in that run's
    # inbox until tools/accept_run.py moves it to QUEUE_DIR; the server derives the same folder.
    feeds_run: Optional[str] = None
    inbox_root: Optional[Path] = None

    def __post_init__(self) -> None:
```

In `agents/run_identity.py` (edit `t2-identity-new`), replace:

```python
    def new(cls, stage: str, advisory_id: str, pdf_path: Path) -> "RunIdentity":
        pdf_path = Path(pdf_path).resolve()
        run_id = "%s-%s-%s" % (advisory_id.lower(), stage, secrets.token_hex(5))
        return cls(run_id, stage, advisory_id, pdf_path, file_sha256(pdf_path))
```

with:

```python
    def new(cls, stage: str, advisory_id: str, pdf_path: Path, feeds_run: Optional[str] = None,
            inbox_root: Optional[Path] = None) -> "RunIdentity":
        pdf_path = Path(pdf_path).resolve()
        run_id = "%s-%s-%s" % (advisory_id.lower(), stage, secrets.token_hex(5))
        return cls(run_id, stage, advisory_id, pdf_path, file_sha256(pdf_path), feeds_run, inbox_root)
```

In `agents/run_identity.py` (edit `t2-identity-queue`), replace:

```python
        return QUEUE_DIR / ("%s.jsonl" % self.run_id)
```

with:

```python
        if self.feeds_run:
            return feeds_inbox.proposals_dir(self.feeds_run, self.inbox_root or feeds_inbox.INBOX_ROOT) / (
                "%s.jsonl" % self.run_id)
        return QUEUE_DIR / ("%s.jsonl" % self.run_id)
```

In `agents/run_identity.py` (edit `t2-identity-env`), replace:

```python
    def env(self) -> dict:
        return {
            "NEXUS_RUN_ID": self.run_id,
            "NEXUS_STAGE": self.stage,
            "NEXUS_ADVISORY_ID": self.advisory_id,
            "NEXUS_PDF_PATH": str(self.pdf_path),
            "NEXUS_PDF_SHA256": self.pdf_sha256,
            "NEXUS_PROPOSALS_PATH": str(self.queue_path),
        }
```

with:

```python
    def env(self) -> dict:
        env = {
            "NEXUS_RUN_ID": self.run_id,
            "NEXUS_STAGE": self.stage,
            "NEXUS_ADVISORY_ID": self.advisory_id,
            "NEXUS_PDF_PATH": str(self.pdf_path),
            "NEXUS_PDF_SHA256": self.pdf_sha256,
            "NEXUS_PROPOSALS_PATH": str(self.queue_path),
        }
        if self.feeds_run:
            env["NEXUS_FEEDS_RUN"] = self.feeds_run
        return env
```

In `agents/extract_advisory.py` (edit `t2-extractor-run-param`), replace:

```python
async def extract(path: Path, advisory_id: str, model: str, max_budget_usd: float, max_turns: int) -> tuple:
    pages = document_pages(path)

    run = RunIdentity.new("extractor", advisory_id, path)
```

with:

```python
async def extract(path: Path, advisory_id: str, model: str, max_budget_usd: float, max_turns: int,
                  run: RunIdentity = None) -> tuple:
    """`run` is passed by a feeds run (tools/friday_run.py), whose identity names the feeds run so the
    queue goes to its inbox; slice 1's command line leaves it None and gets a fresh identity as before."""
    pages = document_pages(path)

    run = run or RunIdentity.new("extractor", advisory_id, path)
```

In `evals/check_feeds_server.py` (edit `t2-server-guard-tools`), replace:

```python
    out.append((sorted(tools) == ["feeds_fetch", "feeds_list_new", "feeds_read_page", "feeds_triage"]
                and ro == {"feeds_fetch": False, "feeds_list_new": False, "feeds_read_page": True,
                           "feeds_triage": False}
                and ow["feeds_fetch"] is True and ow["feeds_list_new"] is True,
                "the server exposes exactly its four tools; only feeds_read_page is annotated read-only, and the "
                "two that reach the network are open-world", sorted(tools)))
    return out
```

with:

```python
    out.append((sorted(tools) == ["feeds_extract", "feeds_fetch", "feeds_list_new", "feeds_read_page", "feeds_triage"]
                and ro == {"feeds_extract": False, "feeds_fetch": False, "feeds_list_new": False,
                           "feeds_read_page": True, "feeds_triage": False}
                and ow["feeds_fetch"] is True and ow["feeds_list_new"] is True and ow["feeds_extract"] is True,
                "a live server exposes exactly its five tools; only feeds_read_page is annotated read-only, and the "
                "three that reach the network are open-world", sorted(tools)))
    # Slice 2 C: a server the eval runner starts (FEEDS_CATALOGUE set) must not even LIST feeds_extract, so
    # B's triage-only sessions keep the four tools they were measured with.
    os.environ[fs.CATALOGUE_ENV] = str(ROOT / "evals" / "feeds" / "catalogue.json")
    try:
        eval_tools = sorted(t.name for t in asyncio.run(load_server(None).mcp.list_tools()))
    finally:
        os.environ.pop(fs.CATALOGUE_ENV, None)
    out.append((eval_tools == ["feeds_fetch", "feeds_list_new", "feeds_read_page", "feeds_triage"],
                "a server started in eval mode lists the four triage tools and not feeds_extract", eval_tools))
    return out
```


- [ ] **Step 4: Register the guard**

In `tools/check_all.py` (edit `t2-check-all`), replace:

```python
    ("check_document_pages", ["evals/check_document_pages.py"], "cold"),
```

with:

```python
    ("check_document_pages", ["evals/check_document_pages.py"], "cold"),
    ("check_feeds_extract", ["evals/check_feeds_extract.py"], "cold"),
```


- [ ] **Step 5: Run it, each mutation, and A's server guard**

```bash
.venv/bin/python evals/check_feeds_extract.py
for m in no-verdict-check no-cap second-request any-host reuse-id queue-escape; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_extract.py --mutate $m | tail -1
done
.venv/bin/python evals/check_feeds_server.py | tail -1
.venv/bin/python evals/check_tool_surface.py | tail -1 && .venv/bin/python evals/check_tool_surface.py --mutate-queue | tail -1
```

Expected:
- `check_feeds_extract`: `HELD (0 failures)`, 17 checks, and six `HELD: the mutation is detected`;
- `check_feeds_server`: `HELD`, 22 checks. Its last check shows an eval-mode server listing four tools;
- `check_tool_surface`: `HELD`, and its queue mutation detected.

`check_feeds_orchestrator` goes red here, because the live server now lists five tools. Task 3 replaces that guard; do not commit Task 2 until Task 3's guard exists, or commit them together.

- [ ] **Step 6: Commit (with Task 3, see above)**

---

### Task 3: the full-mode orchestrator, the write allowlist, and the transcript's terminal event

**Files:**
- Replace: `agents/orchestrate_feeds.py`, `evals/check_feeds_orchestrator.py`
- Modify: `agents/permissions.py`, `agents/telemetry.py`, `agents/extract_advisory.py`

**Interfaces:**
- Produces:
  - `FeedsRun.live`, `FeedsRun.server_env()`;
  - `FULL_PROMPT`, `FULL_PROMPT_SHA256`, `FULL_AGENT_TOOLS`;
  - `RUN_CEILING_USD = 5.00`, `EXTRACTION_BUDGET_USD = 1.00`, `EXTRACTION_MAX_TURNS = 60`;
  - `run_session(run, ...)`, with `run_triage` kept as B's name;
  - `telemetry.record_unhooked(run, calls, results)`, `telemetry.terminated(run)`.
- A session's summary gains `queued` and `validated`. `RUN_COMPLETED` gains `queued` and `terminated_from_transcript`.
- Unchanged, and asserted: B's `TRIAGE_PROMPT` bytes and `PROMPT_SHA256`, and `evals/run_feeds_triage.py`'s `identity()`, so B's runner still resumes and refuses exactly as before.

- [ ] **Step 1: Replace the guard first**

Replace `evals/check_feeds_orchestrator.py` with:

```python
"""
Prove the orchestrator reaches its mode's tools and nothing else, and pin the run's budget (slice 2 B, C).

Usage:
    python evals/check_feeds_orchestrator.py
    python evals/check_feeds_orchestrator.py --mutate builtin-tools      # the base tool set is not removed
    python evals/check_feeds_orchestrator.py --mutate settings           # the operator's settings are inherited
    python evals/check_feeds_orchestrator.py --mutate preapprove-triage  # feeds_triage bypasses the callback
    python evals/check_feeds_orchestrator.py --mutate allow-propose      # the callback allows propose_link
    python evals/check_feeds_orchestrator.py --mutate extract-tool       # an extraction tool reaches triage-only mode
    python evals/check_feeds_orchestrator.py --mutate no-asymmetry       # the prompt loses "when in doubt, keep it"
    python evals/check_feeds_orchestrator.py --mutate extract-in-eval    # an eval run's callback allows feeds_extract
    python evals/check_feeds_orchestrator.py --mutate inherit-catalogue  # a live server inherits FEEDS_CATALOGUE
    python evals/check_feeds_orchestrator.py --mutate triage-drift       # a live run's triage instructions differ from B's
    python evals/check_feeds_orchestrator.py --mutate unpinned-budget    # the session cap moves off US$1.50
    python evals/check_feeds_orchestrator.py --mutate over-ceiling       # the caps no longer fit the US$5 ceiling

WHAT IT HOLDS (spec sections 1 and 4; the questions evals/check_tool_surface.py asks of the extractor):
  no built-ins   tools=[] and the argv carries --tools "", setting_sources=[], strict_mcp_config -- both modes;
  one server     the feeds server only, with the run's identity: an EVAL run's catalogue and batch, and a
                 LIVE run's FEEDS_CATALOGUE and FEEDS_CATALOGUE_BATCH set EMPTY, so a shell export cannot
                 turn a Friday run into an eval run (B carry-forward);
  reads only     allowed_tools pre-approves exactly feeds_read_page, and nothing bypasses the callback;
  the callback   EVAL allows list, fetch, triage and DENIES feeds_extract; LIVE allows those and feeds_extract;
                 both DENY propose_link and Bash;
  the lists      AGENT_TOOLS is exactly an EVAL server's tools and FULL_AGENT_TOOLS a LIVE server's, each split
                 into the mode's write allowlist and the read-only tools;
  identity       FeedsRun refuses a malformed run id, a half-set eval mode and a batch over the cap of 10;
  telemetry      the Post hooks are installed; the shadowing advisory names only feeds_read_page;
  the prompts    triage-only states the asymmetry, offers no extraction, and PROMPT_SHA256 is its hash; the
                 LIVE prompt BEGINS with those exact bytes and adds the extraction step (at most 3);
  the budget     pinned: US$1.50 and 80 turns per session, US$1.00 and 60 turns per extraction, 3
                 extractions and 10 verdicts per run, a US$5.00 ceiling -- and session + 3 extractions fits it.

STATIC. No model, no network. Each --mutate changes the options or a module constant in memory.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import os
import sys
import tempfile
import types
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
from feeds import extraction as feeds_extraction, triage as feeds_triage  # noqa: E402

MUTATIONS = ("builtin-tools", "settings", "preapprove-triage", "allow-propose", "extract-tool", "no-asymmetry",
             "extract-in-eval", "inherit-catalogue", "triage-drift", "unpinned-budget", "over-ceiling")
LIVE = of.FeedsRun("feeds-2026-10-02-fff555")
EVAL_RUN = of.FeedsRun("feeds-2026-10-02-fff666", catalogue=ROOT / "evals" / "feeds" / "catalogue.json",
                       batch=("ofsi:0123456789abcdef",))
TRIAGE = "mcp__feeds__feeds_triage"
EXTRACT = "mcp__feeds__feeds_extract"
SERVER = ROOT / "mcp_server" / "feeds_server.py"
PINNED = {"MAX_BUDGET_USD": 1.50, "MAX_TURNS": 80, "RUN_CEILING_USD": 5.00, "EXTRACTION_BUDGET_USD": 1.00,
          "EXTRACTION_MAX_TURNS": 60}


def server_tools(eval_mode: bool) -> tuple:
    """(names, read-only names) of a feeds server started in the given mode, loaded afresh from source."""
    if eval_mode:
        os.environ["FEEDS_CATALOGUE"] = str(ROOT / "evals" / "feeds" / "catalogue.json")
    try:
        module = types.ModuleType("feeds_server_mode_%s" % eval_mode)
        module.__file__ = str(SERVER)
        exec(compile(SERVER.read_text(encoding="utf-8"), str(SERVER), "exec"), module.__dict__)
        listed = asyncio.run(module.mcp.list_tools())
    finally:
        os.environ.pop("FEEDS_CATALOGUE", None)
    names = sorted("mcp__feeds__%s" % t.name for t in listed)
    ro = sorted("mcp__feeds__%s" % t.name for t in listed
                if t.annotations is not None and getattr(t.annotations, "read_only_hint", False))
    return names, ro


def surface(o, run, mutation) -> list:
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    from claude_agent_sdk.types import ToolPermissionContext
    mode = "live" if run.live else "eval"
    if mutation == "builtin-tools":
        o = dataclasses.replace(o, tools=None)
    if mutation == "settings":
        o = dataclasses.replace(o, setting_sources=["user", "project"])
    if mutation == "preapprove-triage":
        o = dataclasses.replace(o, allowed_tools=list(o.allowed_tools) + [TRIAGE])
    out = []
    cmd = built_command(o)
    pairs = list(zip(cmd, cmd[1:]))
    out.append((o.tools == [] and ("--tools", "") in pairs and o.setting_sources == [] and o.strict_mcp_config is True,
                '%s: tools=[] and --tools "", setting_sources=[], strict_mcp_config' % mode,
                "tools=%r setting_sources=%r" % (o.tools, o.setting_sources)))
    server = o.mcp_servers.get("feeds", {})
    want_env = run.env() if not run.live else {"FEEDS_RUN_ID": run.run_id, "FEEDS_CATALOGUE": "",
                                                 "FEEDS_CATALOGUE_BATCH": ""}
    out.append((list(o.mcp_servers) == ["feeds"] and server.get("args") == [str(of.SERVER_PATH)]
                and server.get("env") == want_env,
                "%s: one MCP server, the feeds server, with the run's identity%s" % (
                    mode, " and the eval variables set EMPTY" if run.live else ""), server.get("env")))
    allowed_arg = cmd[cmd.index("--allowedTools") + 1] if "--allowedTools" in cmd else ""
    out.append((list(o.allowed_tools) == list(FEEDS_READ_ONLY_TOOLS) and allowed_arg.split(",") == list(FEEDS_READ_ONLY_TOOLS)
                and "--permission-mode" not in cmd and "--dangerously-skip-permissions" not in cmd
                and o.permission_prompt_tool_name is None and o.output_format is None,
                "%s: only feeds_read_page is pre-approved, and nothing bypasses the callback" % mode,
                "--allowedTools %s" % allowed_arg))
    ctx = ToolPermissionContext(tool_use_id="static")
    ask = lambda name: asyncio.run(o.can_use_tool(name, {}, ctx))  # noqa: E731
    allows = {t: isinstance(ask("mcp__feeds__%s" % t), PermissionResultAllow)
              for t in ("feeds_list_new", "feeds_fetch", "feeds_triage")}
    extract_allowed = isinstance(ask(EXTRACT), PermissionResultAllow)
    denies = {t: isinstance(ask(t), PermissionResultDeny) for t in (PROPOSE_TOOL, "Bash")}
    out.append((all(allows.values()) and all(denies.values()) and extract_allowed == run.live,
                "%s: the callback allows list, fetch and triage, %s feeds_extract, and denies propose_link and Bash"
                % (mode, "ALLOWS" if run.live else "DENIES"),
                "allows %s; extract allowed %s; denies %s" % (allows, extract_allowed, denies)))
    out.append((sorted(o.hooks or {}) == ["PostToolUse", "PostToolUseFailure"],
                "%s: the Post hooks are installed for telemetry" % mode, str(sorted(o.hooks or {}))))
    return out


def checks(mutation) -> list:
    from claude_agent_sdk import types as sdk_types
    if mutation == "allow-propose":
        of.FEEDS_WRITE_ALLOWLIST = of.FEEDS_WRITE_ALLOWLIST | {PROPOSE_TOOL}
        of.FEEDS_FULL_WRITE_ALLOWLIST = of.FEEDS_FULL_WRITE_ALLOWLIST | {PROPOSE_TOOL}
    if mutation == "extract-in-eval":
        of.FEEDS_WRITE_ALLOWLIST = of.FEEDS_WRITE_ALLOWLIST | {EXTRACT}
    if mutation == "extract-tool":
        of.AGENT_TOOLS = of.AGENT_TOOLS + (EXTRACT,)
    if mutation == "no-asymmetry":
        of.TRIAGE_PROMPT = of.TRIAGE_PROMPT.replace("When in doubt, keep it", "When in doubt, drop it")
    if mutation == "inherit-catalogue":
        of.LIVE_SERVER_BLANKS = {}
    if mutation == "triage-drift":
        of.FULL_PROMPT = of.FULL_PROMPT.replace("When in doubt, keep it", "When in doubt, keep it, always", 1)
    if mutation == "unpinned-budget":
        of.MAX_BUDGET_USD = 3.00
    if mutation == "over-ceiling":
        of.EXTRACTION_BUDGET_USD = 1.50
        PINNED["EXTRACTION_BUDGET_USD"] = 1.50  # the pin moved WITH it: only the ceiling arithmetic can catch this
    out = []
    for run in (EVAL_RUN, LIVE):
        out += surface(of.agent_options(run), run, mutation)

    live_names, live_ro = server_tools(False)
    eval_names, eval_ro = server_tools(True)
    out.append((sorted(of.AGENT_TOOLS) == eval_names and sorted(of.FULL_AGENT_TOOLS) == live_names
                and set(of.FEEDS_WRITE_ALLOWLIST) | set(FEEDS_READ_ONLY_TOOLS) == set(eval_names)
                and set(of.FEEDS_FULL_WRITE_ALLOWLIST) | set(FEEDS_READ_ONLY_TOOLS) == set(live_names)
                and eval_ro == live_ro == list(FEEDS_READ_ONLY_TOOLS),
                "AGENT_TOOLS is exactly an eval server's tools and FULL_AGENT_TOOLS a live server's, each split into "
                "the mode's write allowlist and the read-only tools", "eval %s | live %s" % (eval_names, live_names)))

    refused = []
    for kwargs in ({"run_id": "not-a-run"}, {"run_id": LIVE.run_id, "batch": ("ofsi:0123456789abcdef",)},
                   {"run_id": LIVE.run_id, "catalogue": Path("c.json"),
                    "batch": tuple("ofsi:%016x" % i for i in range(11))}):
        try:
            of.FeedsRun(**kwargs)
        except ValueError:
            refused.append(True)
    out.append((len(refused) == 3 and LIVE.live and not EVAL_RUN.live,
                "FeedsRun refuses a bad run id, a half-set eval mode and a batch over 10; live is decided by the run",
                "%d refused" % len(refused)))

    o = of.agent_options(EVAL_RUN)
    msg = sdk_types._get_can_use_tool_shadowed_warning(o.permission_mode, list(o.allowed_tools)) or ""
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with expected_shadowing(FEEDS_READ_ONLY_TOOLS):
            warnings.warn(msg, sdk_types.CanUseToolShadowedWarning)
            warnings.warn("can_use_tool will not be invoked for: %s. x" % TRIAGE, sdk_types.CanUseToolShadowedWarning)
    out.append((msg.startswith("can_use_tool will not be invoked for: %s." % FEEDS_READ_ONLY_TOOLS[0])
                and len(seen) == 1 and TRIAGE in str(seen[0].message),
                "the shadowing advisory names only feeds_read_page, and only that advisory is silenced", msg[:70]))

    live_prompt = of.agent_options(LIVE).system_prompt
    out.append(("When in doubt, keep it" in o.system_prompt
                and hashlib.sha256(of.TRIAGE_PROMPT.encode("utf-8")).hexdigest() == of.PROMPT_SHA256
                and "extract" not in o.system_prompt.replace("You do not extract", "").replace("worth extracting", ""),
                "triage-only: the prompt states the asymmetry, offers no extraction, and PROMPT_SHA256 is its hash",
                of.PROMPT_SHA256[:16]))
    out.append((live_prompt.startswith(of.TRIAGE_PROMPT) and live_prompt == of.FULL_PROMPT
                and hashlib.sha256(live_prompt[:len(of.TRIAGE_PROMPT)].encode("utf-8")).hexdigest() == of.PROMPT_SHA256
                and "feeds_extract" in live_prompt[len(of.TRIAGE_PROMPT):] and "At most 3" in live_prompt,
                "live: the prompt BEGINS with B's measured triage bytes and adds the extraction step (at most 3)",
                of.FULL_PROMPT_SHA256[:16]))

    got = {k: getattr(of, k) for k in PINNED}
    fits = of.MAX_BUDGET_USD + feeds_extraction.MAX_PER_RUN * of.EXTRACTION_BUDGET_USD <= of.RUN_CEILING_USD
    out.append((got == PINNED and feeds_extraction.MAX_PER_RUN == 3 and feeds_triage.MAX_PER_RUN == 10 and fits,
                "the budget is pinned (session US$1.50/80 turns, extraction US$1.00/60, 3 extractions, 10 verdicts, "
                "US$5 ceiling) and session + 3 extractions fits the ceiling",
                "%s, fits %s" % (got, fits)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Prove the orchestrator's tool surface and pin the run's budget")
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

- [ ] **Step 2: Replace the orchestrator**

Replace `agents/orchestrate_feeds.py` with (the `TRIAGE_PROMPT` block is B's, byte for byte):

```python
"""
The feeds orchestrator: one orchestrating agent whose tools carry the invariants (spec sections 1 and 4).

TWO MODES, chosen by the run, never by the agent:
  triage-only (EVAL)  a FeedsRun with a catalogue and a batch -- evals/run_feeds_triage.py (slice 2 B). Four
                      tools: feeds_list_new, feeds_fetch, feeds_read_page, feeds_triage. The server started
                      in eval mode does not even list feeds_extract.
  full (LIVE)         a FeedsRun with neither -- tools/friday_run.py (slice 2 C). The four, plus
                      feeds_extract, which QUEUES a relevant item: the extraction itself runs in code after
                      the session, within the run's budget (tools/friday_run.py). The agent never extracts.
Both: `tools=[]` emits `--tools ""`, `setting_sources=[]` ignores the operator's settings and hooks,
`strict_mcp_config` loads only the server passed here, feeds_read_page is the only pre-approved tool, and
every tool that writes reaches agents/permissions.py's callback, which allows the mode's allowlist only.
A LIVE server is started with FEEDS_CATALOGUE and FEEDS_CATALOGUE_BATCH set EMPTY, so a value exported in
the operator's shell cannot turn a Friday run into an eval run (B's carry-forward). Guarded by
evals/check_feeds_orchestrator.py.

Telemetry is slice 1's, plus one rule (slice 2 C): a tool call the CLI answered before any hook could run
-- measured in B's pilot transcript: three feeds_triage calls whose input "could not be parsed as JSON",
each answered by a tool_result with is_error and no hook event -- gets its ONE terminal event from the
transcript (telemetry.record_unhooked, `source: transcript`). terminal_check then reads what the hooks and
the transcript together recorded; a call with neither is still unterminated.

After the agent stops, IN CODE, feeds.triage.reconcile() lists every listed or expected item without a
verdict as unfinished. A session is `validated` only when it failed nothing and left nothing unfinished.
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
    AssistantMessage, ClaudeAgentOptions, ResultError, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage,
    query,
)

from agents import telemetry  # noqa: E402
from agents.permissions import (  # noqa: E402
    FEEDS_FULL_WRITE_ALLOWLIST, FEEDS_READ_ONLY_TOOLS, FEEDS_SERVER_KEY, FEEDS_WRITE_ALLOWLIST, expected_shadowing,
    permission_callback,
)
from feeds import extraction as feeds_extraction, inbox, triage as feeds_triage  # noqa: E402

SERVER_PATH = ROOT / "mcp_server" / "feeds_server.py"
TRIAGE_TOOLS = ("feeds_list_new", "feeds_fetch", "feeds_read_page", "feeds_triage")
FULL_TOOLS = TRIAGE_TOOLS + ("feeds_extract",)
AGENT_TOOLS = tuple("mcp__%s__%s" % (FEEDS_SERVER_KEY, t) for t in TRIAGE_TOOLS)
FULL_AGENT_TOOLS = tuple("mcp__%s__%s" % (FEEDS_SERVER_KEY, t) for t in FULL_TOOLS)
MODEL = "claude-sonnet-5"
# Per orchestrator session. PINNED by evals/check_feeds_orchestrator.py since slice 2 C (B's carry-forward:
# they were unguarded). B measured US$0.12-0.33 for a 10-item triage session; the cap leaves room for the
# extraction requests and for one turn's overshoot inside the run's ceiling below.
MAX_BUDGET_USD = 1.50
MAX_TURNS = 80
# THE FRIDAY RUN'S BUDGET (spec section 1, owner decisions 2026-09-26), in the one place a guard reads it.
RUN_CEILING_USD = 5.00        # the whole run: orchestrator session plus every extraction
EXTRACTION_BUDGET_USD = 1.00  # each extraction's own max_budget_usd
EXTRACTION_MAX_TURNS = 60     # slice 1's extractor default
# A session stopped by its own turn or budget cap COMPLETED: what it left is unfinished, and measured.
# Anything else that ends a run in error (auth, credit, the CLI) is a failure.
LIMIT_SUBTYPES = ("error_max_turns", "error_max_budget_usd")
# A live server must never inherit an eval catalogue from the operator's shell (B carry-forward 1).
LIVE_SERVER_BLANKS = {"FEEDS_CATALOGUE": "", "FEEDS_CATALOGUE_BATCH": ""}
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

# Appended, never interleaved: the triage instructions a live run follows are byte-for-byte the ones B's
# band measured (PROMPT_SHA256), and the extraction request is one step after them.
EXTRACTION_SECTION = """Before your final message, queue extraction. This run extracts at most 3 items; the extraction runs after you finish, in code, and you do not see it.
- Call feeds_extract once for each relevant item worth extracting, the most substantive first: a publication that sets out methods, red flags or a case in its own text before a notice that only points to one. At most 3; the tool refuses a fourth, and a relevant item left over returns next run.
- feeds_extract refuses an item not triaged relevant. It may fetch the publication's own PDF, linked from the page you read. If it replies "Failed:", name the item in your final message.
- In your final message, mark each queued item "queued"."""

FULL_PROMPT = TRIAGE_PROMPT + "\n\n" + EXTRACTION_SECTION
PROMPT_SHA256 = hashlib.sha256(TRIAGE_PROMPT.encode("utf-8")).hexdigest()
FULL_PROMPT_SHA256 = hashlib.sha256(FULL_PROMPT.encode("utf-8")).hexdigest()


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

    @property
    def live(self) -> bool:
        """A live run is FULL mode: triage and extraction requests. An eval run is triage-only."""
        return self.catalogue is None

    def env(self) -> dict:
        """The run's identity, as the permission callback checks it: every value set."""
        env = {"FEEDS_RUN_ID": self.run_id}
        if self.catalogue is not None:
            env.update(FEEDS_CATALOGUE=str(Path(self.catalogue).resolve()), FEEDS_CATALOGUE_BATCH=",".join(self.batch))
        return env

    def server_env(self) -> dict:
        """What the feeds server is started with: the identity, and in live mode the eval variables BLANKED."""
        return dict(self.env(), **LIVE_SERVER_BLANKS) if self.live else self.env()


def agent_options(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                  max_turns: int = MAX_TURNS) -> ClaudeAgentOptions:
    """The orchestrator's whole capability surface, in one place a guard can read."""
    return ClaudeAgentOptions(
        system_prompt=FULL_PROMPT if run.live else TRIAGE_PROMPT,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        mcp_servers={FEEDS_SERVER_KEY: {"type": "stdio", "command": sys.executable, "args": [str(SERVER_PATH)],
                                        "env": run.server_env()}},
        strict_mcp_config=True,
        tools=[],
        setting_sources=[],
        allowed_tools=list(FEEDS_READ_ONLY_TOOLS),
        can_use_tool=permission_callback(
            run, allowlist=FEEDS_FULL_WRITE_ALLOWLIST if run.live else FEEDS_WRITE_ALLOWLIST,
            may="list, fetch, read and triage feed items%s" % (", and queue relevant ones for extraction"
                                                               if run.live else "")),
        hooks=telemetry.tool_hooks(run),
    )


def _prompt(run: FeedsRun) -> str:
    if run.live:
        return "Run %s. Triage every new item from ofsi, fincen and ofac, then queue extraction." % run.run_id
    return "Run %s. Triage every new item from ofsi, fincen and ofac." % run.run_id


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(str(c.get("text", "")) for c in content or [] if isinstance(c, dict))


async def run_session(run: FeedsRun, model: str = MODEL, max_budget_usd: float = MAX_BUDGET_USD,
                      max_turns: int = MAX_TURNS, inbox_root: Path = inbox.INBOX_ROOT) -> dict:
    """One orchestrator session, in the run's mode. Returns its summary; never raises for an agent-side
    failure, which is recorded (`failure`) so the caller decides."""
    telemetry.run_started(run, model, max_budget_usd, max_turns, FULL_AGENT_TOOLS if run.live else AGENT_TOOLS)
    tool_calls: Counter = Counter()
    calls: dict = {}    # tool_use_id -> tool name, every call the agent made, in order
    results: dict = {}  # tool_use_id -> (is_error, text), every tool_result the transcript carried
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
                            calls[block.id] = block.name
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            results[block.tool_use_id] = (bool(block.is_error), _result_text(block.content))
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
    from_transcript = telemetry.record_unhooked(run, calls, results)
    terminal_check = telemetry.reconcile(run, list(calls))
    items = feeds_triage.reconcile(run.run_id, run.batch, inbox_root)
    queued = [r["key"] for r in feeds_extraction.load_requests(run.run_id, inbox_root)] if run.live else []
    validated = failure is None and not items["unfinished"]
    telemetry.run_completed(run, telemetry.FAILURE if failure else telemetry.SUCCESS,
                            (failure or limit or "%s session ended" % ("orchestrator" if run.live else "triage"))[:300],
                            result=result, validated=validated, terminal_check=terminal_check, limit=limit,
                            unfinished=items["unfinished"], queued=queued,
                            terminated_from_transcript=[e["payload"]["tool_use_id"] for e in from_transcript])
    return {"run_id": run.run_id, "failure": failure, "limit": limit, "tool_calls": dict(tool_calls),
            "turns": getattr(result, "num_turns", None), "cost_usd": getattr(result, "total_cost_usd", None),
            "duration_ms": getattr(result, "duration_ms", None), "stop_reason": getattr(result, "stop_reason", None),
            "terminal_check": terminal_check, "listed": items["listed"], "triaged": items["triaged"],
            "unfinished": items["unfinished"], "never_listed": items["never_listed"], "queued": queued,
            "validated": validated}


# B's name: evals/run_feeds_triage.py and its guard call run_triage for an eval session.
run_triage = run_session
```

- [ ] **Step 3: Make the edits**

In `agents/permissions.py` (edit `t3-permissions-full`), replace:

```python
FEEDS_WRITE_ALLOWLIST = frozenset("mcp__%s__%s" % (FEEDS_SERVER_KEY, t)
                                  for t in ("feeds_list_new", "feeds_fetch", "feeds_triage"))
```

with:

```python
FEEDS_WRITE_ALLOWLIST = frozenset("mcp__%s__%s" % (FEEDS_SERVER_KEY, t)
                                  for t in ("feeds_list_new", "feeds_fetch", "feeds_triage"))
# Slice 2 C: a LIVE (full-mode) run may also queue a relevant item for extraction. An eval run may not:
# its allowlist above is unchanged, and its server does not list the tool.
FEEDS_FULL_WRITE_ALLOWLIST = FEEDS_WRITE_ALLOWLIST | {"mcp__%s__feeds_extract" % FEEDS_SERVER_KEY}
```

In `agents/telemetry.py` (edit `t3-telemetry-unhooked`), replace:

```python
def reconcile(run, tool_use_ids) -> dict:
```

with:

```python
def terminated(run) -> set:
    """The tool_use ids this run's telemetry already holds a terminal event for."""
    path = telemetry_path(run)
    out = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = json.loads(line)
                if event.get("stage") in (TOOL_CALL, PERMISSION_DENIED):
                    out.add(event.get("payload", {}).get("tool_use_id"))
    return out


def record_unhooked(run, calls: dict, results: dict) -> list:
    """The ONE terminal event for each call the CLI answered before any hook ran (slice 2 C).

    Measured in B's pilot transcript (2026-09-27): three feeds_triage calls whose input "could not be
    parsed as JSON" were each answered by a tool_result with is_error -- and fired no hook and no
    permission callback, so the run's telemetry held nothing for them and terminal_check called them
    unterminated. The runner saw both halves in the message stream. `calls` is tool_use_id -> tool name,
    `results` tool_use_id -> (is_error, text); a call with a result and no terminal event gets one here,
    marked source "transcript" so the evidence says where it came from. A call with NEITHER stays
    unterminated: nothing is invented.
    """
    done = terminated(run)
    out = []
    for tool_use_id, tool in calls.items():
        if tool_use_id in done or tool_use_id not in results:
            continue
        is_error, text = results[tool_use_id]
        status = FAILURE if is_error else SUCCESS
        out.append(emit(run, TOOL_CALL, status, "%s %s (answered by the CLI; no hook fired)" % (tool, status.lower()),
                        tool=tool, tool_use_id=tool_use_id, latency_ms=None, outcome=(text or "")[:200],
                        source="transcript"))
    return out


def reconcile(run, tool_use_ids) -> dict:
```

In `agents/extract_advisory.py` (edit `t3-extractor-imports`), replace:

```python
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, query  # noqa: E402
```

with:

```python
from claude_agent_sdk import (  # noqa: E402
    AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage, query,
)
```

In `agents/extract_advisory.py` (edit `t3-extractor-collect`), replace:

```python
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls[block.name] += 1
                            tool_use_ids.append(block.id)
                elif isinstance(message, ResultMessage):
                    result = message
                    if message.is_error:
```

with:

```python
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls[block.name] += 1
                            tool_use_ids.append(block.id)
                            names[block.id] = block.name
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            text = block.content if isinstance(block.content, str) else " ".join(
                                str(c.get("text", "")) for c in block.content or [] if isinstance(c, dict))
                            results[block.tool_use_id] = (bool(block.is_error), text)
                elif isinstance(message, ResultMessage):
                    result = message
                    if message.is_error:
```

In `agents/extract_advisory.py` (edit `t3-extractor-state`), replace:

```python
    tool_use_ids: list = []
    result: ResultMessage | None = None
```

with:

```python
    tool_use_ids: list = []
    # Slice 2 C: a call the CLI answered with no hook gets its terminal event from the transcript.
    names: dict = {}
    results: dict = {}
    result: ResultMessage | None = None
```

In `agents/extract_advisory.py` (edit `t3-extractor-fail-reconcile`), replace:

```python
    except Exception as exc:
        telemetry.run_completed(run, telemetry.FAILURE, str(exc)[:300], result=result, validated=False,
                                terminal_check=telemetry.reconcile(run, tool_use_ids))
        raise
    terminal_check = telemetry.reconcile(run, tool_use_ids)
```

with:

```python
    except Exception as exc:
        telemetry.record_unhooked(run, names, results)
        telemetry.run_completed(run, telemetry.FAILURE, str(exc)[:300], result=result, validated=False,
                                terminal_check=telemetry.reconcile(run, tool_use_ids))
        raise
    telemetry.record_unhooked(run, names, results)
    terminal_check = telemetry.reconcile(run, tool_use_ids)
```


- [ ] **Step 4: Run the guards B's code depends on, and the new one**

```bash
.venv/bin/python evals/check_feeds_orchestrator.py
for m in builtin-tools settings preapprove-triage allow-propose extract-tool no-asymmetry extract-in-eval inherit-catalogue triage-drift unpinned-budget over-ceiling; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_feeds_orchestrator.py --mutate $m | tail -1
done
for g in check_feeds_runner check_feeds_score check_telemetry check_feeds_triage check_tool_surface; do .venv/bin/python evals/$g.py | tail -1; done
```

Expected:
- `check_feeds_orchestrator`: 16 checks `HELD`, and 11 mutations detected;
- B's runner, score, telemetry, triage and tool-surface guards: `HELD`.

- [ ] **Step 5: Commit Tasks 2 and 3 together**

```bash
git add feeds/extraction.py feeds/sources.py feeds/inbox.py mcp_server/feeds_server.py mcp_server/knowledge_centre_server.py agents/run_identity.py agents/extract_advisory.py agents/permissions.py agents/telemetry.py agents/orchestrate_feeds.py evals/check_feeds_extract.py evals/check_feeds_server.py evals/check_feeds_orchestrator.py tools/check_all.py
git commit -m "Slice 2 C1: feeds_extract queues a relevant item, the live orchestrator, and a terminal event for a call no hook saw"
```

---

### Task 4: the Friday run: extraction within the budget, reconciliation, and the report

**Files:**
- Create: `feeds/runs.py`, `feeds/reconcile.py`, `feeds/report.py`, `tools/friday_run.py`, `evals/check_friday_run.py`
- Modify: `tools/check_all.py`

**Interfaces:**
- `feeds.runs`:
  - `classify(run_id, root) -> eval|accepted|nothing_to_decide|pending`;
  - `pending`, `blocking`, `expirable`, `expire`, `mark_accepted`, `run_date`;
  - `EXPIRE_DAYS = 14`.
- `feeds.reconcile`:
  - `reconcile_run(run_id, root) -> {status, listed, verdicts, relevant, not_relevant, unfinished, queued, extracted, failed, deferred_budget, not_queued, sessions, problems, spent_usd, ...}`;
  - `session(path)`, `session_cost(path)`;
  - the status names, and `ACCEPTABLE`.
- `feeds.report`: `render(run_id, root)`, `write(run_id, root)`, `summary_line(rec)`. Line 1 is `# Friday run <id>: <STATUS>`; line 3 is one sentence (C2's notification reads both).
- `tools.friday_run`:
  - `friday(run, session, extractor, root, advisory_list) -> reconciliation`;
  - `extract_one`, `may_start`, `counted`, `write_refusal`, `refusals`;
  - `main(argv, root, today, extra_refusals)`, and `--plan`.
- The run's files: `run.json`, `advisory_ids.jsonl`, `extraction_runs.jsonl`, `records/`, `proposals/`, `telemetry/`, `report.md` (and `refusal.json` when refused).

- [ ] **Step 1: Write the guard first**

Create `evals/check_friday_run.py`:

```python
"""
Pin the Friday run's budget, reconciliation and report, and the terminal event for a call no hook saw (slice 2 C).

Usage:
    python evals/check_friday_run.py
    python evals/check_friday_run.py --mutate no-budget-check         # an extraction starts past the ceiling
    python evals/check_friday_run.py --mutate unknown-cost-free       # a cost that never arrived counts as zero
    python evals/check_friday_run.py --mutate no-transcript-terminal  # a call the CLI refused stays unterminated
    python evals/check_friday_run.py --mutate validated-empty         # a session leaving items unfinished is validated
    python evals/check_friday_run.py --mutate quiet-reconcile         # an unterminated call does not fail reconciliation
    python evals/check_friday_run.py --mutate report-hides-drops      # the report omits what triage dropped

WHAT IT HOLDS (spec sections 1, 2 and 5):
  budget       extractions start in queue order only while spend + US$1.00 <= US$5.00; the next is DEFERRED
               FOR BUDGET with no advisory id; ids are allocated in order (ADV-2026-0021, -0022); a cost that
               never arrived counts at its cap (the session's US$1.50, an extraction's US$1.00);
  failure      a failed orchestrator session starts no extraction and the run is FAILED;
  refusal      ANTHROPIC_API_KEY or an eval variable in the environment refuses the run before any agent,
               with a REFUSED report;
  reconcile    an unterminated tool call makes the run RECONCILIATION_FAILED; a layout change is UNFINISHED
               and LOUD; a run that listed nothing is NOTHING_NEW;
  report       written on every run above; names every dropped item with its reason and quote, the deferred,
               the cost against the ceiling; renders the same bytes twice;
  transcript   run_session, driven by a scripted message stream: a call answered by a tool_result and no
               hook gets ONE terminal event (source "transcript"), terminal_check is clean, and a session that
               left a listed item without a verdict is NOT validated.

COLD. Stub sessions and extractors, a scripted message stream in place of the SDK's query, a temporary
inbox and advisory list. No network, no model, no CLI.

NOT A VACUOUS PASS. Each --mutate rewrites one module's source in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
import agents  # noqa: E402
import feeds  # noqa: E402
from feeds import extraction, http as fh, inbox, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem  # noqa: E402
from feeds.sources import linked_pdfs  # noqa: E402
from check_document_pages import tiny_pdf  # noqa: E402

FILES = {"telemetry": ROOT / "agents" / "telemetry.py", "of": ROOT / "agents" / "orchestrate_feeds.py",
         "reconcile": ROOT / "feeds" / "reconcile.py", "report": ROOT / "feeds" / "report.py",
         "friday": ROOT / "tools" / "friday_run.py"}
MUTATIONS = {
    "no-budget-check": ("friday", "    return spent + of.EXTRACTION_BUDGET_USD <= of.RUN_CEILING_USD + 1e-9\n",
                        "    return True\n"),
    "unknown-cost-free": ("friday", "    return cap if cost is None else cost\n", "    return cost or 0.0\n"),
    "no-transcript-terminal": ("telemetry", "        if tool_use_id in done or tool_use_id not in results:\n",
                               "        if True:\n"),
    "validated-empty": ("of", '    validated = failure is None and not items["unfinished"]\n',
                        "    validated = failure is None\n"),
    "quiet-reconcile": ("reconcile", '        if s["unterminated"] or s["duplicated"]:\n', "        if False:\n"),
    "report-hides-drops": ("report", '                        ("Dropped by triage (not relevant), with the reason and '
                                     'the quote", rec["not_relevant"])):\n',
                           '                        ("Dropped by triage (not relevant), with the reason and the quote", [])):\n'),
}
SENTENCE = "This advisory describes red flags for trade-based money laundering through shell companies."


def load_all(mutation):
    """telemetry, orchestrate_feeds, reconcile, report, friday_run -- each from its (possibly mutated) source,
    installed so the ones loaded after it import it."""
    mods = {}
    for name, (pkg, attr, modname) in (("telemetry", (agents, "telemetry", "agents.telemetry")),
                                       ("of", (agents, "orchestrate_feeds", "agents.orchestrate_feeds")),
                                       ("reconcile", (feeds, "reconcile", "feeds.reconcile")),
                                       ("report", (feeds, "report", "feeds.report")),
                                       ("friday", (None, None, "friday_run_under_test"))):
        path = FILES[name]
        source = path.read_text(encoding="utf-8")
        if mutation and MUTATIONS[mutation][0] == name:
            old, new = MUTATIONS[mutation][1:]
            if source.count(old) != 1:
                raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
            source = source.replace(old, new)
        module = types.ModuleType(modname)
        module.__file__ = str(path)
        sys.modules[modname] = module
        if pkg is not None:
            setattr(pkg, attr, module)
        exec(compile(source, str(path), "exec"), module.__dict__)
        mods[name] = module
    return mods


class Stub:
    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        return fh.Fetched(url, url, "application/pdf", tiny_pdf(["Advisory text on shell companies."]))


def listed_run(m, root: Path, run_id: str, n_relevant: int, n_dropped: int, queue: int, cost, fail=None,
               unterminated=(), layout_changed=False, nothing=False):
    """What an orchestrator session leaves: items listed and pinned, verdicts, requests, and its telemetry."""
    run = m["of"].FeedsRun(run_id)
    m["telemetry"].TELEMETRY_DIR = inbox.run_dir(run_id, root) / inbox.TELEMETRY
    state = {"run_id": run_id, "sources": {s: {"status": "ok", "error": None, "listed": 0, "already_seen": 0,
                                               "items": []} for s in ("ofsi", "fincen", "ofac")}}
    if layout_changed:
        state["sources"]["fincen"].update(status="layout_changed", error="fincen: the listing table is missing")
    keys = []
    for i in range(0 if nothing else n_relevant + n_dropped):
        link = "https://www.fincen.gov/system/files/a%d.pdf" % i
        raw = ("<html><body><main><h1>Advisory %d</h1><p>%s</p><p><a href=\"%s\">PDF</a></p></main></body></html>"
               % (i, SENTENCE, link)).encode("utf-8")
        it = FeedItem("fincen", "fin-%s-%d" % (run_id[-6:], i), "Advisory number %d" % i,
                      "https://www.fincen.gov/resources/advisories/f%s-%d" % (run_id[-6:], i),
                      "2026-10-01")
        sha = hashlib.sha256(raw).hexdigest()
        rel = inbox.write_file(run_id, "docs/%s.html" % sha, raw, root)
        state["sources"]["fincen"]["items"].append(dict(it.to_json(), document={
            "path": rel, "sha256": sha, "content_type": "text/html", "bytes": len(raw), "final_url": it.url,
            "pages": 1, "text_pages": 1, "page_error": None, "linked_pdfs": linked_pdfs(raw, it.url)}))
        keys.append(it.key)
    inbox.save(run_id, state, root)
    for i, k in enumerate(keys):
        ok, msg = feeds_triage.decide(run_id, k, "relevant" if i < n_relevant else "not_relevant",
                                      "Drop reason %d: a licence notice." % i if i >= n_relevant else "Red flags.",
                                      SENTENCE, root)
        assert ok, msg
    for k in keys[:queue]:
        ok, msg = extraction.request(run_id, k, Stub(), root)
        assert ok, msg
    tel = m["telemetry"]
    tel.run_started(run, "stub", 1.5, 80, m["of"].FULL_AGENT_TOOLS)
    for tid in ("toolu_a",):
        tel.emit(run, tel.TOOL_CALL, tel.SUCCESS, "stub", tool="mcp__feeds__feeds_list_new", tool_use_id=tid,
                 latency_ms=1, outcome="ok")
    check = {"calls": 1 + len(unterminated), "unterminated": list(unterminated), "duplicated": []}
    tel.run_completed(run, tel.FAILURE if fail else tel.SUCCESS, fail or "ended",
                      result=types.SimpleNamespace(num_turns=9, total_cost_usd=cost, duration_ms=1,
                                                   permission_denials=[]),
                      validated=fail is None, terminal_check=check)

    async def session(_run):
        return {"run_id": run_id, "failure": fail, "cost_usd": cost, "limit": None}
    return run, keys, session


def extractor_with(m, costs: list):
    """A stub extraction: a record of the pinned document under the allocated id, a two-line queue and its
    telemetry, as slice 1's extract leaves them. Costs are taken in order; None = a cost that never arrived."""
    costs = list(costs)

    async def extractor(run, req, advisory_id, root):
        from agents.run_identity import RunIdentity
        folder = inbox.run_dir(run.run_id, root)
        ident = RunIdentity.new("extractor", advisory_id, folder / req["document"]["path"], feeds_run=run.run_id,
                                inbox_root=root)
        cost = costs.pop(0)
        tel = m["telemetry"]
        tel.run_started(ident, "stub", 1.0, 60, ())
        tel.run_completed(ident, tel.SUCCESS, "record validated", validated=True,
                          result=types.SimpleNamespace(num_turns=20, total_cost_usd=cost, duration_ms=1,
                                                       permission_denials=[]),
                          terminal_check={"calls": 0, "unterminated": [], "duplicated": []})
        rel = "records/%s.json" % advisory_id
        inbox.write_file(run.run_id, rel, json.dumps({"advisory_id": advisory_id, "actors": [], "source": {
            "document_sha256": ident.pdf_sha256}}).encode("utf-8"), root)
        ident.queue_path.parent.mkdir(parents=True, exist_ok=True)
        ident.queue_path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
        return {"key": req["key"], "advisory_id": advisory_id, "extraction_run_id": ident.run_id, "status": "extracted",
                "record": rel, "error": None, "cost_usd": cost}
    return extractor


def scripted_query(m):
    """Stands in for claude_agent_sdk.query: one call a hook records, one the CLI refuses with no hook."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage

    async def fake(prompt, options):
        yield AssistantMessage(content=[ToolUseBlock(id="toolu_ok", name="mcp__feeds__feeds_list_new", input={"source": "ofsi"}),
                                        ToolUseBlock(id="toolu_bad", name="mcp__feeds__feeds_triage",
                                                     input={"__unparsedToolInput": "{\"para"})], model="stub")
        await options.hooks["PostToolUse"][0].hooks[0](
            {"tool_name": "mcp__feeds__feeds_list_new", "tool_use_id": "toolu_ok", "tool_response": "No new items",
             "duration_ms": 3}, "toolu_ok", None)
        yield UserMessage(content=[ToolResultBlock(tool_use_id="toolu_ok", content="No new items", is_error=False),
                                   ToolResultBlock(tool_use_id="toolu_bad", is_error=True,
                                                   content="<tool_use_error>InputValidationError: mcp__feeds__feeds_triage"
                                                           " was called with input that could not be parsed as JSON.")])
        yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=5, is_error=False, num_turns=2,
                            session_id="s", total_cost_usd=0.05)
    return fake


def checks(mutation) -> list:
    m = load_all(mutation)
    fr, rec_mod = m["friday"], m["reconcile"]
    out = []

    def run_friday(root, run, session, extractor, alist):
        try:
            return asyncio.run(fr.friday(run, session=session, extractor=extractor, root=root, advisory_list=alist))
        except Exception as exc:
            return {"status": "RAISED %s: %s" % (type(exc).__name__, exc)}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020"}]}), encoding="utf-8")
        box = tmp / "inbox"

        rid = "feeds-2026-10-02-aaa001"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=2, queue=3, cost=2.50)
        rec = run_friday(box, run, session, extractor_with(m, [1.30, 1.30, 1.30]), alist)
        outs = extraction.load_outcomes(rid, box)
        statuses = [outs.get(k, {}).get("status") for k in keys[:3]]
        out.append((statuses == ["extracted", "extracted", "deferred_budget"]
                    and extraction.load_allocations(rid, box) == {keys[0]: "ADV-2026-0021", keys[1]: "ADV-2026-0022"}
                    and abs((rec.get("spent_usd") or 0) - 5.10) < 1e-6 and rec.get("status") == "UNFINISHED",
                    "session US$2.50, extractions US$1.30 each: two start (2.50+1 and 3.80+1 fit US$5), the third is "
                    "DEFERRED FOR BUDGET with no id; ids -0021, -0022; UNFINISHED",
                    "%s, spent %s, %s" % (statuses, rec.get("spent_usd"), rec.get("status"))))
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        again = m["report"].render(rid, box)
        out.append((text.startswith("# Friday run %s: UNFINISHED\n" % rid) and "1 deferred for budget" in text
                    and all(("Drop reason %d" % i) in text for i in (3, 4)) and SENTENCE[:40] in text
                    and "US$5.10 counted against the US$5.00 ceiling" in text and text == again,
                    "the report names every dropped item with its reason and quote, the deferral and the cost against "
                    "the ceiling, and renders the same bytes twice", text.splitlines()[0][:80]))

        rid = "feeds-2026-10-02-aaa002"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=0, queue=3, cost=None)
        rec = run_friday(box, run, session, extractor_with(m, [None, None, None]), alist)
        n = sum(1 for o in extraction.load_outcomes(rid, box).values() if o["status"] == "extracted")
        out.append((abs((rec.get("spent_usd") or 0) - 4.50) < 1e-6 and n == 3,
                    "a cost that never arrived counts at its cap: US$1.50 + 3 x US$1.00 = US$4.50", rec.get("spent_usd")))

        rid = "feeds-2026-10-02-aaa003"
        run, keys, session = listed_run(m, box, rid, n_relevant=2, n_dropped=0, queue=2, cost=0.4,
                                        fail="CLIConnectionError: not authenticated")
        rec = run_friday(box, run, session, extractor_with(m, [0.5, 0.5]), alist)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((rec.get("status") == "FAILED" and not extraction.load_allocations(rid, box)
                    and "**FAILED: CLIConnectionError: not authenticated**" in text,
                    "a failed orchestrator session starts no extraction; the run is FAILED, loudly", rec.get("status")))

        rid = "feeds-2026-10-02-aaa004"
        reasons = fr.refusals({"ANTHROPIC_API_KEY": "x", "FEEDS_CATALOGUE": "/tmp/c.json"})
        rec = fr.write_refusal(rid, reasons, box)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((len(reasons) == 2 and rec["status"] == "REFUSED" and text.startswith("# Friday run %s: REFUSED" % rid)
                    and "**REFUSED: ANTHROPIC_API_KEY" in text and not (inbox.run_dir(rid, box) / "items.json").exists(),
                    "an API key or an eval catalogue in the environment refuses the run before any agent, with a report",
                    reasons))

        rid = "feeds-2026-10-02-aaa005"
        run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3,
                                        unterminated=("toolu_lost",))
        rec = run_friday(box, run, session, extractor_with(m, [0.5]), alist)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((rec.get("status") == "RECONCILIATION_FAILED" and "**RECONCILIATION: session %s: 1 tool call" % rid in text
                    and "--override-reconciliation" in text,
                    "an unterminated tool call fails reconciliation, loudly, and the report names the override",
                    rec.get("status")))

        rid = "feeds-2026-10-02-aaa006"
        run, keys, session = listed_run(m, box, rid, n_relevant=0, n_dropped=0, queue=0, cost=0.1, nothing=True)
        rec = run_friday(box, run, session, extractor_with(m, []), alist)
        out.append((rec.get("status") == "NOTHING_NEW" and (inbox.run_dir(rid, box) / "report.md").exists(),
                    "a run that listed nothing new is NOTHING_NEW, and still writes its report", rec.get("status")))

        rid = "feeds-2026-10-02-aaa007"
        run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3, layout_changed=True)
        rec = run_friday(box, run, session, extractor_with(m, [0.5]), alist)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((rec.get("status") == "UNFINISHED" and "**LAYOUT CHANGED: fincen" in text,
                    "a listing whose layout changed is UNFINISHED and stated loudly", rec.get("status")))

        rid = "feeds-2026-10-02-aaa008"
        state = {"run_id": rid, "sources": {"ofsi": {"status": "ok", "items": [dict(FeedItem(
            "ofsi", "x#1", "A notice", "https://www.gov.uk/x", "2026-10-01").to_json(), document=None)]}}}
        inbox.save(rid, state, box)
        live = m["of"].FeedsRun(rid)
        m["telemetry"].TELEMETRY_DIR = tmp / "tel8"
        m["of"].query = scripted_query(m)
        try:
            summary = asyncio.run(m["of"].run_session(live, inbox_root=box))
        except Exception as exc:
            summary = {"terminal_check": {"unterminated": ["RAISED %s" % exc]}, "validated": None}
        events = [json.loads(l) for l in (tmp / "tel8" / ("%s.jsonl" % rid)).read_text().splitlines() if l.strip()]
        tx = [e for e in events if e["payload"].get("source") == "transcript"]
        out.append((summary["terminal_check"]["unterminated"] == [] and len(tx) == 1
                    and tx[0]["payload"]["tool_use_id"] == "toolu_bad" and tx[0]["status"] == "FAILURE",
                    "a call the CLI answered with no hook gets ONE terminal event from the transcript; terminal_check "
                    "is clean", "%s; transcript events %d" % (summary["terminal_check"], len(tx))))
        out.append((summary.get("validated") is False,
                    "a session that left a listed item without a verdict is not validated", summary.get("validated")))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the Friday run's budget, reconciliation and report")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:160]))
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

- [ ] **Step 2: Create the four modules**

`feeds/runs.py`:

```python
"""
Which feeds runs are waiting for a person (slice 2 C): back-pressure, expiry, and the eval marker, in ONE place.

A run folder under inbox/ is exactly one of:
  eval               items.json carries "eval": true (evals/run_feeds_triage.py, slice 2 B). NEVER pending:
                     B's 18 eval runs share the production inbox, and a Friday must not wait on them.
  accepted           tools/accept_run.py wrote accepted.json into it.
  nothing_to_decide  no items.json (refused or failed before listing), or no item listed as new.
  pending            listed at least one new item and has not been accepted.
inbox/expired/<run_id>/ holds runs `accept_run --expire` moved aside; nothing here counts them.

A pending run BLOCKS the next Friday while it is younger than EXPIRE_DAYS (spec section 5); from then on it is
expirable and does not block. A run's age is from the date in its id, never a file time.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import List, Tuple

from feeds import inbox

EXPIRE_DAYS = 14
EXPIRED = "expired"
ACCEPTED = "accepted.json"
EVAL, ACCEPTED_STATE, NOTHING, PENDING = "eval", "accepted", "nothing_to_decide", "pending"


def run_date(run_id: str) -> date:
    return date.fromisoformat(run_id[len("feeds-"):len("feeds-") + 10])


def classify(run_id: str, root: Path = inbox.INBOX_ROOT) -> str:
    folder = inbox.run_dir(run_id, root)
    if not (folder / inbox.ITEMS).exists():
        return NOTHING
    state = inbox.load(run_id, root)
    if state.get("eval"):
        return EVAL
    if (folder / ACCEPTED).exists():
        return ACCEPTED_STATE
    return PENDING if inbox.items(state) else NOTHING


def run_ids(root: Path = inbox.INBOX_ROOT) -> List[str]:
    root = Path(root)
    return sorted(p.name for p in root.iterdir() if p.is_dir() and inbox.RUN_ID.fullmatch(p.name)) \
        if root.exists() else []


def pending(root: Path = inbox.INBOX_ROOT, today: date = None) -> List[Tuple[str, int]]:
    """(run id, age in days) of every pending production run, oldest first."""
    today = today or date.today()
    return [(r, (today - run_date(r)).days) for r in run_ids(root) if classify(r, root) == PENDING]


def blocking(root: Path = inbox.INBOX_ROOT, today: date = None) -> List[Tuple[str, int]]:
    return [(r, age) for r, age in pending(root, today) if age < EXPIRE_DAYS]


def expirable(root: Path = inbox.INBOX_ROOT, today: date = None) -> List[Tuple[str, int]]:
    return [(r, age) for r, age in pending(root, today) if age >= EXPIRE_DAYS]


def expire(run_id: str, root: Path = inbox.INBOX_ROOT, today: date = None) -> Path:
    """Move a pending run of at least EXPIRE_DAYS to inbox/expired/<run_id>/. Moved, never deleted, and the
    ledger is not touched, so its items are listed again next Friday. Raises ValueError otherwise."""
    today = today or date.today()
    state = classify(run_id, root)
    if state != PENDING:
        raise ValueError("run %s is %s, not pending; only a pending run expires" % (run_id, state))
    age = (today - run_date(run_id)).days
    if age < EXPIRE_DAYS:
        raise ValueError("run %s is %d day(s) old; a run expires at %d" % (run_id, age, EXPIRE_DAYS))
    target = Path(root) / EXPIRED / run_id
    if target.exists():
        raise ValueError("%s already exists" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(inbox.run_dir(run_id, root), target)
    return target


def mark_accepted(run_id: str, record: dict, root: Path = inbox.INBOX_ROOT) -> None:
    path = inbox.run_dir(run_id, root) / ACCEPTED
    if path.exists():
        raise ValueError("run %s was already accepted" % run_id)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
```

`feeds/reconcile.py`:

```python
"""
A Friday run's reconciliation, IN CODE, after every agent has stopped (spec sections 1 and 5).

Reads only what the run wrote -- items.json, triage.jsonl, extractions.jsonl, advisory_ids.jsonl,
extraction_runs.jsonl, records/, proposals/, telemetry/, run.json, refusal.json -- and answers:
  every listed item has one verdict, or it is UNFINISHED;
  every relevant item was extracted, or its failure, its budget deferral or its not being queued is REPORTED;
  every tool call of every session has exactly one terminal event (each session's terminal_check), and
  every session that started also completed.
Bookkeeping that does not add up is a PROBLEM, and any problem makes the run RECONCILIATION_FAILED, which
tools/accept_run.py refuses without an explicit, recorded override (spec section 5). Skipped work is not a
problem: it is UNFINISHED, and accept_run defers it to next Friday.

STATUS, first match wins: REFUSED (refusal.json) | FAILED (the orchestrator session failed: auth, credit,
the CLI) | RECONCILIATION_FAILED | UNFINISHED | NOTHING_NEW | COMPLETE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from feeds import extraction, inbox, triage as feeds_triage

RUN_JSON = "run.json"
REFUSAL = "refusal.json"
RESOLVER = "knowledge_centre_resolve_actor"
SOURCES = ("ofsi", "fincen", "ofac")
REFUSED, FAILED, RECON_FAILED, UNFINISHED, NOTHING_NEW, COMPLETE = (
    "REFUSED", "FAILED", "RECONCILIATION_FAILED", "UNFINISHED", "NOTHING_NEW", "COMPLETE")
ACCEPTABLE = (UNFINISHED, NOTHING_NEW, COMPLETE)


def _json(path: Path) -> Optional[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def session(path: Path) -> dict:
    """One session's telemetry file, summarised: who, whether it completed, its cost and terminal_check."""
    events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    started = [e for e in events if e["stage"] == "RUN_STARTED"]
    done = [e for e in events if e["stage"] == "RUN_COMPLETED"]
    last = done[-1]["payload"] if done else {}
    check = last.get("terminal_check") or {}
    resolver = [e for e in events if e["stage"] == "FC08_TOOL_CALL" and str(e["payload"].get("tool", "")).endswith(RESOLVER)]
    return {"run_id": path.stem, "agent": (started or events or [{"payload": {}}])[0]["payload"].get("agent"),
            "started": bool(started), "completed": bool(done), "status": done[-1]["status"] if done else None,
            "message": done[-1]["message"] if done else None, "cost_usd": last.get("cost_usd"),
            "turns": last.get("turns"), "limit": last.get("limit"), "validated": last.get("validated"),
            "calls": check.get("calls"), "unterminated": check.get("unterminated") or [],
            "duplicated": check.get("duplicated") or [],
            "from_transcript": sum(1 for e in events if e["payload"].get("source") == "transcript"),
            "resolver_calls": len(resolver),
            "resolved": sum(1 for e in resolver if str(e["payload"].get("outcome", "")).startswith("Resolved:"))}


def session_cost(path: Path) -> Optional[float]:
    return session(path)["cost_usd"] if Path(path).exists() else None


def reconcile_run(run_id: str, root: Path = inbox.INBOX_ROOT) -> dict:
    folder = inbox.run_dir(run_id, root)
    refusal = _json(folder / REFUSAL)
    run = _json(folder / RUN_JSON) or {}
    state = inbox.load(run_id, root)
    listed = {it["key"]: it for it in inbox.items(state)}
    verdicts = feeds_triage.load(run_id, root) if (folder / feeds_triage.TRIAGE).exists() else {}
    requests = {r["key"]: r for r in extraction.load_requests(run_id, root)}
    outcomes = extraction.load_outcomes(run_id, root)
    allocations = extraction.load_allocations(run_id, root)
    tel = folder / inbox.TELEMETRY
    sessions = [session(p) for p in sorted(tel.glob("*.jsonl"))] if tel.exists() else []
    problems: List[str] = []

    relevant = sorted(k for k, v in verdicts.items() if v["verdict"] == feeds_triage.RELEVANT)
    for k in sorted(set(verdicts) - set(listed)):
        problems.append("a verdict for %s, which this run did not list" % k)
    for k in sorted(set(requests) - set(relevant)):
        problems.append("an extraction request for %s, which has no relevant verdict" % k)
    orchestrator = next((s for s in sessions if s["run_id"] == run_id), None)
    ended = orchestrator is not None and orchestrator["completed"]
    for k in sorted(set(outcomes) - set(requests)):
        problems.append("an extraction outcome for %s, which was never requested" % k)
    if ended and orchestrator["status"] != "FAILURE":
        for k in sorted(set(requests) - set(outcomes)):
            problems.append("the extraction request for %s has no outcome" % k)
    extracted, failed, deferred = [], {}, []
    for k, o in sorted(outcomes.items()):
        if o["status"] == "extracted":
            extracted.append(k)
            record = _json(folder / (o.get("record") or "none")) if o.get("record") else None
            want_sha = (requests.get(k, {}).get("document") or {}).get("sha256")
            if record is None:
                problems.append("%s is recorded extracted but its record is missing" % k)
            elif record.get("advisory_id") != allocations.get(k) or record.get("advisory_id") != o.get("advisory_id"):
                problems.append("%s's record names %s, but the run allocated %s" % (k, record.get("advisory_id"),
                                                                                     allocations.get(k)))
            elif (record.get("source") or {}).get("document_sha256") != want_sha:
                problems.append("%s's record is not of the document its request pinned" % k)
        elif o["status"] == "deferred_budget":
            deferred.append(k)
        else:
            failed[k] = o.get("error") or o["status"]
    for s in sessions:
        if s["started"] and not s["completed"]:
            problems.append("session %s started and never completed" % s["run_id"])
        if s["unterminated"] or s["duplicated"]:
            problems.append("session %s: %d tool call(s) with no terminal event, %d with more than one" % (
                s["run_id"], len(s["unterminated"]), len(s["duplicated"])))
    if refusal is None and run and orchestrator is None:
        problems.append("the orchestrator session left no telemetry")

    source_state = {name: {k: v for k, v in st.items() if k in ("status", "error", "listed", "already_seen")}
                    for name, st in state["sources"].items()}
    never_listed = [s for s in SOURCES if s not in state["sources"]]
    source_failures = sorted(n for n, st in source_state.items() if st.get("status") not in (None, "ok"))
    unfinished = sorted(k for k in listed if k not in verdicts)
    not_queued = [k for k in relevant if k not in requests]
    known = [s["cost_usd"] for s in sessions if s["cost_usd"] is not None]
    if refusal is not None:
        status = REFUSED
    elif orchestrator is None or orchestrator["status"] == "FAILURE" or run.get("failure"):
        status = FAILED
    elif problems:
        status = RECON_FAILED
    elif unfinished or not_queued or failed or deferred or source_failures or never_listed:
        status = UNFINISHED
    elif not listed:
        status = NOTHING_NEW
    else:
        status = COMPLETE
    return {"run_id": run_id, "status": status, "refusal": refusal, "failure": run.get("failure"),
            "sources": source_state, "never_listed_sources": never_listed, "source_failures": source_failures,
            "listed": sorted(listed), "verdicts": verdicts, "unfinished": unfinished, "relevant": relevant,
            "not_relevant": sorted(k for k, v in verdicts.items() if v["verdict"] == feeds_triage.NOT_RELEVANT),
            "queued": sorted(requests), "extracted": extracted, "failed": failed, "deferred_budget": deferred,
            "not_queued": not_queued, "allocations": allocations, "sessions": sessions, "problems": problems,
            "spent_usd": run.get("spent_usd"), "known_cost_usd": round(sum(known), 6),
            "unknown_cost_sessions": sum(1 for s in sessions if s["cost_usd"] is None)}
```

`feeds/report.py`:

```python
"""
The Friday report, inbox/<run_id>/report.md, written on EVERY run -- refused, failed, nothing new or full
(spec section 2). A deterministic projection of the run's own files through feeds/reconcile.py: the same
folder always renders the same bytes, and nothing here reads a clock, git or the network.

Its first two lines are the contract with the notification (C2): "# Friday run <id>: <STATUS>" and one
plain sentence. Failures are stated loudly, in capitals, above everything else.
"""

from __future__ import annotations

import json
from pathlib import Path

from feeds import extraction, inbox, reconcile

REPORT = "report.md"
CEILING_NOTE = "US$%.2f ceiling"


def _usd(x) -> str:
    return "unknown" if x is None else "US$%.2f" % x


def _cell(text, limit=160) -> str:
    return " ".join(str(text or "").split())[:limit].replace("|", "/")


def actor_resolution(record: dict) -> tuple:
    """(named, resolvable) actors of a record against the governed register, exact matches only -- the same
    rule as evals/actor_resolution.py -- so a run's resolution rate does not depend on the agent's calls."""
    from schemas.actor_match import resolve, variants_of
    from tools.build_actor_register import load_register
    register = load_register()
    named = resolved = 0
    for actor in record.get("actors", []):
        got = resolve(variants_of(actor), actor.get("actor_type"), register)
        if got["status"] == "category":
            continue
        named += 1
        resolved += got["status"] == "resolved"
    return named, resolved


def summary_line(rec: dict) -> str:
    if rec["status"] == reconcile.REFUSED:
        return "Refused before any agent ran: %s." % "; ".join(rec["refusal"].get("reasons", []))
    if rec["status"] == reconcile.FAILED:
        return "The orchestrator session failed: %s." % _cell(rec["failure"] or "no session telemetry", 200)
    return "%d new item(s), %d kept, %d dropped by triage, %d extracted, %d unfinished; %s spent of the %s." % (
        len(rec["listed"]), len(rec["relevant"]), len(rec["not_relevant"]), len(rec["extracted"]),
        len(rec["unfinished"]) + len(rec["not_queued"]) + len(rec["failed"]) + len(rec["deferred_budget"]),
        _usd(rec["spent_usd"]), CEILING_NOTE % 5.0)


def render(run_id: str, root: Path = inbox.INBOX_ROOT) -> str:
    rec = reconcile.reconcile_run(run_id, root)
    folder = inbox.run_dir(run_id, root)
    items = {it["key"]: it for it in inbox.items(inbox.load(run_id, root))}
    outcomes = extraction.load_outcomes(run_id, root)
    out = ["# Friday run %s: %s" % (run_id, rec["status"]), "", summary_line(rec), ""]
    loud = []
    if rec["refusal"]:
        loud += ["**REFUSED: %s**" % r for r in rec["refusal"].get("reasons", [])]
    if rec["status"] == reconcile.FAILED:
        loud.append("**FAILED: %s**" % _cell(rec["failure"] or "the orchestrator session left no telemetry", 300))
    for name in rec["source_failures"]:
        st = rec["sources"][name]
        word = "LAYOUT CHANGED" if st["status"] == "layout_changed" else "SOURCE DOWN"
        loud.append("**%s: %s (%s)**" % (word, name, _cell(st.get("error"), 200)))
    for name in rec["never_listed_sources"]:
        if not rec["refusal"]:
            loud.append("**NOT LISTED: %s was never listed in this run**" % name)
    if rec["problems"]:
        loud += ["**RECONCILIATION: %s**" % p for p in rec["problems"]]
    if loud:
        out += loud + [""]

    out += ["## Sources", "", "| source | status | listed | already decided | new |", "|---|---|---|---|---|"]
    for name in reconcile.SOURCES:
        st = rec["sources"].get(name)
        if st is None:
            out.append("| %s | not listed | - | - | - |" % name)
        else:
            new = sum(1 for it in items.values() if it["source"] == name)
            out.append("| %s | %s | %s | %s | %d |" % (name, st.get("status"), st.get("listed"), st.get("already_seen"),
                                                      new))
    for title, keys in (("Kept by triage (relevant)", rec["relevant"]),
                        ("Dropped by triage (not relevant), with the reason and the quote", rec["not_relevant"])):
        out += ["", "## %s: %d" % (title, len(keys)), ""]
        for k in keys:
            v = rec["verdicts"][k]
            out.append("- `%s` %s -- %s. Quote (p.%s): \"%s\"" % (
                k, _cell(items[k]["title"], 120), _cell(v["reason"], 300), ",".join(map(str, v["found_on"])),
                _cell(v["quote"], 200)))
    unfinished = [(k, "no verdict") for k in rec["unfinished"]] + [(k, "relevant, not queued for extraction")
                                                                   for k in rec["not_queued"]]
    out += ["", "## Unfinished: %d (they return next Friday unless dropped)" % len(unfinished), ""]
    out += ["- `%s` %s: %s" % (k, _cell(items.get(k, {}).get("title"), 120), why) for k, why in unfinished]

    out += ["", "## Extraction: %d queued, %d extracted, %d failed, %d deferred for budget" % (
        len(rec["queued"]), len(rec["extracted"]), len(rec["failed"]), len(rec["deferred_budget"])), ""]
    if rec["queued"]:
        out += ["| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable "
                "| cost |", "|---|---|---|---|---|---|---|"]
    by_id = {s["run_id"]: s for s in rec["sessions"]}
    for k in rec["queued"]:
        o = outcomes.get(k, {"status": "no outcome"})
        s = by_id.get(o.get("extraction_run_id"), {})
        queue = folder / inbox.PROPOSALS / ("%s.jsonl" % o.get("extraction_run_id"))
        proposals = sum(1 for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()) if queue.exists() else 0
        actors = "-"
        if o.get("status") == "extracted" and o.get("record"):
            named, resolvable = actor_resolution(json.loads((folder / o["record"]).read_text(encoding="utf-8")))
            actors = "%d of %d" % (resolvable, named)
        status = o["status"] if o["status"] != "failed" else "failed: %s" % _cell(o.get("error"), 80)
        out.append("| `%s` | %s | %s | %d | %s | %s | %s |" % (
            k, o.get("advisory_id") or "-", status, proposals,
            "%d (%d)" % (s.get("resolver_calls", 0), s.get("resolved", 0)) if s else "-", actors, _usd(o.get("cost_usd"))))

    out += ["", "## Reconciliation: %s" % ("clean" if not rec["problems"] else "%d problem(s)" % len(rec["problems"])), "",
            "| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |",
            "|---|---|---|---|---|---|---|---|---|"]
    for s in rec["sessions"]:
        out.append("| %s | %s | %s | %s | %s | %s | %d | %d | %d |" % (
            s["run_id"], s["agent"], s["status"], _usd(s["cost_usd"]), s["turns"], s["calls"], len(s["unterminated"]),
            len(s["duplicated"]), s["from_transcript"]))
    out += ["", "## Cost", "",
            "%s counted against the %s (a session whose cost never arrived is counted at its cap); %s reported by the "
            "sessions' own telemetry." % (_usd(rec["spent_usd"]), CEILING_NOTE % 5.0, _usd(rec["known_cost_usd"])), ""]
    if rec["status"] in reconcile.ACCEPTABLE and rec["listed"]:
        out += ["## Next", "", "`python tools/accept_run.py %s` -- accept, drop or defer each item." % run_id, ""]
    elif rec["status"] == reconcile.RECON_FAILED:
        out += ["## Next", "", "Reconciliation failed: accepting this run needs `--override-reconciliation "
                "\"<reason>\"`, and the reason is recorded.", ""]
    return "\n".join(out)


def write(run_id: str, root: Path = inbox.INBOX_ROOT) -> Path:
    path = inbox.run_dir(run_id, root) / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(run_id, root), encoding="utf-8")
    return path
```

`tools/friday_run.py`:

```python
"""
One Friday run (spec sections 1 and 2): the orchestrator session, then extraction IN CODE within the budget,
then reconciliation in code, then inbox/<run_id>/report.md -- on every run, refused and failed included.

Usage:
    python tools/friday_run.py           # one live run now (sub-project C1: the manual dry runs)
    python tools/friday_run.py --plan    # print the budget and the caps; start nothing, spend nothing

THE BUDGET (agents/orchestrate_feeds.py, pinned by evals/check_feeds_orchestrator.py). The orchestrator
session is capped at MAX_BUDGET_USD. Then each queued item, in the order the agent queued it: an extraction
starts only if the spend so far plus EXTRACTION_BUDGET_USD stays within RUN_CEILING_USD; otherwise the item
is DEFERRED FOR BUDGET (no advisory id is allocated, and accept_run defers it to next Friday). Each
extraction is slice 1's agents/extract_advisory.extract, unchanged in its gate, propose_link, citations and
telemetry, with its OWN run identity naming this feeds run, so its queue and telemetry land in this run's
inbox. A cost that never arrived (the SDK raised before its result) is counted at the session's cap.

WRITES only inbox/<run_id>/ (gitignored): run.json, advisory_ids.jsonl, extraction_runs.jsonl, records/,
proposals/, telemetry/, report.md. Nothing tracked changes; tools/accept_run.py is the only way in.

REFUSES before any agent runs, with a refusal report (refusal.json + report.md) and exit 1, when:
  ANTHROPIC_API_KEY is set (it takes precedence over the subscription token: CLAUDE.md, Auth);
  FEEDS_CATALOGUE or FEEDS_CATALOGUE_BATCH is set (an eval catalogue in the shell; B carry-forward).
Sub-project C2 adds the scheduled preflight (on main, back-pressure, auth) through the same refusal path.

EXIT 0 for COMPLETE, NOTHING_NEW and UNFINISHED (a person decides the rest); 1 for REFUSED, FAILED and
RECONCILIATION_FAILED.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agents import orchestrate_feeds as of, telemetry  # noqa: E402
from feeds import extraction, inbox, reconcile, report  # noqa: E402
from feeds.runs import run_date  # noqa: E402

# Every list an advisory id may already be in: the golden corpus and the accepted live-feed advisories.
ADVISORY_LISTS = (ROOT / "evals" / "golden" / "advisory_list.json", ROOT / "data" / "feeds" / "advisory_list.json")
EVAL_VARIABLES = ("FEEDS_CATALOGUE", "FEEDS_CATALOGUE_BATCH")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def counted(cost: Optional[float], cap: float) -> float:
    """What a session counts against the ceiling: its reported cost, or its cap when none arrived."""
    return cap if cost is None else cost


def may_start(spent: float) -> bool:
    """Spec section 1: an extraction starts only if the spend so far plus its budget stays within the ceiling."""
    return spent + of.EXTRACTION_BUDGET_USD <= of.RUN_CEILING_USD + 1e-9


def _save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


async def extract_one(run: of.FeedsRun, request: dict, advisory_id: str, root: Path) -> dict:
    """Slice 1's extraction on the pinned document, with its own identity; the outcome, never an exception."""
    from agents import extract_advisory
    from agents.run_identity import RunIdentity
    folder = inbox.run_dir(run.run_id, root)
    doc = folder / request["document"]["path"]
    ident = RunIdentity.new("extractor", advisory_id, doc, feeds_run=run.run_id, inbox_root=root)
    out = {"key": request["key"], "advisory_id": advisory_id, "extraction_run_id": ident.run_id,
           "document_sha256": ident.pdf_sha256, "started_at": _now(), "status": None, "error": None, "record": None}
    try:
        record, _ = await extract_advisory.extract(doc, advisory_id, of.MODEL, of.EXTRACTION_BUDGET_USD,
                                                   of.EXTRACTION_MAX_TURNS, run=ident)
        rel = "%s/%s.json" % (inbox.RECORDS, advisory_id)
        inbox.write_file(run.run_id, rel, record.model_dump_json(indent=2).encode("utf-8"), root)
        out.update(status="extracted", record=rel)
    except Exception as exc:  # recorded: an extraction that fails is reported, never raised past the run
        out.update(status="failed", error=("%s: %s" % (type(exc).__name__, exc))[:500])
    out["cost_usd"] = reconcile.session_cost(telemetry.telemetry_path(ident))
    return out


async def friday(run: of.FeedsRun, session=None, extractor=None, root: Path = inbox.INBOX_ROOT,
                 advisory_list=ADVISORY_LISTS) -> dict:
    session = session or of.run_session
    extractor = extractor or extract_one
    started = _now()
    summary = await session(run)
    spent = counted(summary.get("cost_usd"), of.MAX_BUDGET_USD)
    if summary.get("failure") is None:
        for req in extraction.load_requests(run.run_id, root):
            if req.get("error") or not req.get("document"):
                outcome = {"key": req["key"], "status": "failed", "error": req.get("error") or "no document",
                           "cost_usd": 0.0}
            elif not may_start(spent):
                outcome = {"key": req["key"], "status": "deferred_budget", "cost_usd": 0.0,
                           "error": "US$%.2f spent; US$%.2f more would pass the US$%.2f ceiling" % (
                               spent, of.EXTRACTION_BUDGET_USD, of.RUN_CEILING_USD)}
            else:
                advisory_id = extraction.allocate_advisory_id(run.run_id, req["key"], run_date(run.run_id).year,
                                                              advisory_list, root)
                outcome = await extractor(run, req, advisory_id, root)
                spent += counted(outcome.get("cost_usd"), of.EXTRACTION_BUDGET_USD)
            extraction.append_outcome(run.run_id, outcome, root)
    _save(inbox.run_dir(run.run_id, root) / reconcile.RUN_JSON,
          {"run_id": run.run_id, "started_at": started, "ended_at": _now(), "failure": summary.get("failure"),
           "limit": summary.get("limit"), "orchestrator_cost_usd": summary.get("cost_usd"), "spent_usd": round(spent, 6),
           "ceiling_usd": of.RUN_CEILING_USD, "prompt_sha256": of.FULL_PROMPT_SHA256, "model": of.MODEL})
    report.write(run.run_id, root)
    return reconcile.reconcile_run(run.run_id, root)


def write_refusal(run_id: str, reasons: list, root: Path = inbox.INBOX_ROOT) -> dict:
    """A refused run still gets a folder, refusal.json and report.md -- and never lists, fetches or spends."""
    _save(inbox.run_dir(run_id, root) / reconcile.REFUSAL, {"run_id": run_id, "refused_at": _now(), "reasons": reasons})
    report.write(run_id, root)
    return reconcile.reconcile_run(run_id, root)


def refusals(env=None) -> list:
    env = os.environ if env is None else env
    out = []
    if env.get("ANTHROPIC_API_KEY"):
        out.append("ANTHROPIC_API_KEY is set; it takes precedence over the subscription token -- unset it")
    for name in EVAL_VARIABLES:
        if env.get(name):
            out.append("%s is set in the environment; a Friday run is never an eval run -- unset it" % name)
    return out


def main(argv: list, root: Path = inbox.INBOX_ROOT, today: date = None, extra_refusals=None) -> int:
    ap = argparse.ArgumentParser(description="One Friday feeds run")
    ap.add_argument("--plan", action="store_true", help="print the budget and caps; start nothing")
    args = ap.parse_args(argv)
    if args.plan:
        print("orchestrator: US$%.2f, %d turns; extraction: US$%.2f, %d turns each, at most %d; ceiling US$%.2f"
              % (of.MAX_BUDGET_USD, of.MAX_TURNS, of.EXTRACTION_BUDGET_USD, of.EXTRACTION_MAX_TURNS,
                 extraction.MAX_PER_RUN, of.RUN_CEILING_USD))
        return 0
    run = of.FeedsRun(inbox.mint_run_id(today or date.today()))
    telemetry.TELEMETRY_DIR = inbox.run_dir(run.run_id, root) / inbox.TELEMETRY
    reasons = refusals() + list(extra_refusals or [])
    rec = write_refusal(run.run_id, reasons, root) if reasons else asyncio.run(friday(run, root=root))
    print("%s: %s -- %s" % (run.run_id, rec["status"], inbox.run_dir(run.run_id, root) / report.REPORT))
    return 0 if rec["status"] in reconcile.ACCEPTABLE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: Register the guard**

In `tools/check_all.py` (edit `t4-check-all`), replace:

```python
    ("check_feeds_extract", ["evals/check_feeds_extract.py"], "cold"),
```

with:

```python
    ("check_feeds_extract", ["evals/check_feeds_extract.py"], "cold"),
    ("check_friday_run", ["evals/check_friday_run.py"], "cold"),
```


- [ ] **Step 4: Run it and each mutation**

```bash
.venv/bin/python evals/check_friday_run.py
for m in no-budget-check unknown-cost-free no-transcript-terminal validated-empty quiet-reconcile report-hides-drops; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_friday_run.py --mutate $m | tail -1
done
.venv/bin/python tools/friday_run.py --plan
```

Expected:
- `HELD (0 failures)`, 10 checks, and six mutations detected;
- `--plan` prints `orchestrator: US$1.50, 80 turns; extraction: US$1.00, 60 turns each, at most 3; ceiling US$5.00`.

The first check's detail line reads `spent 5.1`. **That is the spec's overshoot, shown on purpose** (see "What I think is wrong", item 1): the rule held, and the total still passed US$5.

- [ ] **Step 5: Commit**

```bash
git add feeds/runs.py feeds/reconcile.py feeds/report.py tools/friday_run.py evals/check_friday_run.py tools/check_all.py
git commit -m "Slice 2 C1: the Friday run -- extraction within the budget, reconciliation in code, a report on every run"
```

---

### Task 5: `accept_run` end to end, and the live-feed advisory list

**Files:**
- Replace: `tools/accept_run.py`
- Create: `evals/check_accept_run.py`
- Modify: `governance/proposals.py`, `evals/check_feeds_ledger.py`, `tools/check_all.py`

**Interfaces:**
- `accept_run`:
  - `plan(run_id, decisions, inbox_root, seen_path, data, advisory_list, golden_list, override) -> dict`;
  - `apply(plan, today, ...)`, `seed_catalogue(today, seen_path, catalogue, dry_run)`;
  - `main(argv, inbox_root, seen_path, today, data, advisory_list, golden_list, catalogue)`.
- The CLI forms: `RUN_ID`, `--decisions`, `--dry-run`, `--override-reconciliation`, `--pending`, `--expire`, `--seed-catalogue`.
- `governance.proposals.recheck(..., feed_list=FEED_ADVISORY_LIST)`.
- `data/feeds/advisory_list.json`: `{"schema": "fc08-feed-advisories/1", "advisories": [...]}`. Each entry carries the golden list's fields plus `feed {run_id, key, item_id, listed_url, extraction_run_id}`.
- `data/feeds/runs/<run_id>/`: the run's files, `telemetry/<run_id>.jsonl` and `accepted.json`.

- [ ] **Step 1: Write the guard first**

Create `evals/check_accept_run.py`:

```python
"""
Pin tools/accept_run.py end to end: the only way a live result enters tracked data (slice 2 C, spec section 2).

Usage:
    python evals/check_accept_run.py
    python evals/check_accept_run.py --mutate no-citation-check   # a record citing text not on its page is accepted
    python evals/check_accept_run.py --mutate no-gate-recheck     # a queue line the review gate would quarantine is accepted
    python evals/check_accept_run.py --mutate ledger-defers       # a deferred item is written to the ledger
    python evals/check_accept_run.py --mutate no-override-needed  # a RECONCILIATION_FAILED run is accepted without a reason
    python evals/check_accept_run.py --mutate overwrite-target    # an existing tracked file is overwritten
    python evals/check_accept_run.py --mutate no-rollback         # a failure mid-write leaves copies behind
    python evals/check_accept_run.py --mutate slice1-records      # an accepted record lands in data/records/

WHAT IT HOLDS:
  accept      an EXTRACTED item's document, record, queue and telemetry are copied byte for byte to
              data/advisories/<adv>-<source>.<ext>, data/feeds/records/, data/proposals/, data/telemetry/; the
              advisory list gains its entry (source, URL, sha256, date, the feed run) and its counts; the run's
              evidence is copied to data/feeds/runs/<run>/; the REVIEW GATE passes the copied queue against
              the new entry and document; the ledger holds the accepted and the dropped item and NOT the deferred;
              the run is marked accepted, and a second acceptance is refused;
  refuse all  an accept of an item never extracted, a record citing text not on its page, a queue line the
              gate would quarantine, an existing target, or a RECONCILIATION_FAILED run without an override
              refuses the WHOLE run: no file, no ledger line, the advisory list byte-identical;
  override    with --override-reconciliation "<reason>" that run is accepted and the reason is recorded;
  rollback    a failure while writing removes every copy this call made and restores the advisory list;
  expire      a pending run under 14 days refuses --expire; at 14 it moves to inbox/expired/ and the ledger is
              untouched; an eval-marked run is never pending;
  seed        --seed-catalogue records every catalogue item as a drop under "catalogue:<sha12>", once.

COLD. Temporary inbox, data folders, advisory list and ledger; the document is a hand-built PDF; the queue
and record are built to slice 1's contracts. No network, no model. The repository's git status is unchanged.

NOT A VACUOUS PASS. Each --mutate rewrites tools/accept_run.py in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from feeds import extraction, inbox, ledger, runs  # noqa: E402
from schemas.proposal_contract import SCHEMA, proposal_id  # noqa: E402
from check_friday_run import listed_run, load_all  # noqa: E402

ACCEPT = ROOT / "tools" / "accept_run.py"
TODAY = date(2026, 10, 3)
QUOTE = "Advisory text on shell companies."
MUTATIONS = {
    "no-citation-check": ("    if bad:\n        problems.append(\"%s: %d citation(s)", "    if False:\n        problems.append(\"%s: %d citation(s)"),
    "no-gate-recheck": ("    for q in quarantined:\n", "    for q in []:\n"),
    "ledger-defers": ('               for k in sorted(listed) if decisions[k] != "defer"]\n', "               for k in sorted(listed)]\n"),
    "no-override-needed": ('    if rec["status"] not in reconcile.ACCEPTABLE and not override:\n', "    if False:\n"),
    "overwrite-target": ("        if path.exists():\n            problems.append(\"%s: %s already exists", "        if False:\n            problems.append(\"%s: %s already exists"),
    "no-rollback": ("            if path.exists():\n                path.unlink()\n", "            pass\n"),
    "slice1-records": ('            "record": data / "feeds" / "records" / ("%s.json" % adv),', '            "record": data / "records" / ("%s.json" % adv),'),
}


def load_accept(mutation):
    source = ACCEPT.read_text(encoding="utf-8")
    if mutation:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, ACCEPT))
        source = source.replace(old, new)
    module = types.ModuleType("accept_run_under_test")
    module.__file__ = str(ACCEPT)
    exec(compile(source, str(ACCEPT), "exec"), module.__dict__)
    return module


def valid_extractor(m, tamper=None):
    """A stub extraction leaving what slice 1's extract leaves, to its contracts: a VALID record citing the pinned
    PDF, a proposal queue the gate accepts, and completed, clean telemetry. `tamper`: "record" | "queue"."""

    async def extractor(run, req, advisory_id, root):
        from agents.run_identity import RunIdentity
        folder = inbox.run_dir(run.run_id, root)
        ident = RunIdentity.new("extractor", advisory_id, folder / req["document"]["path"], feeds_run=run.run_id,
                                inbox_root=root)
        tel = m["telemetry"]
        tel.run_started(ident, "stub", 1.0, 60, ())
        tel.run_completed(ident, tel.SUCCESS, "record validated", validated=True,
                          result=types.SimpleNamespace(num_turns=20, total_cost_usd=0.6, duration_ms=1, permission_denials=[]),
                          terminal_check={"calls": 0, "unterminated": [], "duplicated": []})
        cite = [{"page": 1, "quote": QUOTE if tamper != "record" else "Advisory text on front companies."}]
        record = {"schema_version": "1.4.0", "advisory_id": advisory_id,
                  "source": {"source_type": "fincen", "publisher": "FinCEN", "title": "A FinCEN advisory",
                             "published_on": "2026-10-01", "published_on_precision": "day", "url": req["document"]["url"],
                             "document_sha256": ident.pdf_sha256, "page_count": 1},
                  "summary": "A synthetic advisory about shell companies, built by the accept_run guard.",
                  "jurisdictions": ["US"], "actors": [], "indicators": [], "suggested_desks": ["trade_desk"],
                  "overall_confidence": "low", "extraction_notes": None,
                  "typologies": [{"family": "sanctions", "typology_id": "SAN001", "label": "Sanctions evasion", "emergent": False,
                                  "confidence": "low", "citations": cite}]}
        rel = "records/%s.json" % advisory_id
        inbox.write_file(run.run_id, rel, json.dumps(record, indent=2).encode("utf-8"), root)
        body = {"schema": SCHEMA, "run_id": ident.run_id, "stage": "extractor", "advisory_id": advisory_id,
                "document_sha256": ident.pdf_sha256, "typology_id": "SAN001", "emergent_label": None,
                "rationale": "Page 1 describes shell companies.", "confidence": "low",
                "citations": [{"page": 1, "quote": QUOTE if tamper != "queue" else "Text this document never held."}]}
        ident.queue_path.parent.mkdir(parents=True, exist_ok=True)
        ident.queue_path.write_text(json.dumps(dict(body, proposal_id=proposal_id(body),
                                                    proposed_at="2026-10-02T09:00:00+00:00")) + "\n", encoding="utf-8")
        return {"key": req["key"], "advisory_id": advisory_id, "extraction_run_id": ident.run_id, "status": "extracted",
                "record": rel, "error": None, "cost_usd": 0.6}
    return extractor


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


def checks(mutation) -> list:
    import asyncio
    m = load_all(None)
    acc = load_accept(mutation)
    out, before = [], git_status()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        box, data, seen = tmp / "inbox", tmp / "data", tmp / "ledger.json"
        golden, alist = tmp / "golden.json", tmp / "feed_advisory_list.json"
        seen.write_text(ledger.dump([]), encoding="utf-8")
        golden.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020", "source_type": "fatf"}]}),
                          encoding="utf-8")
        alist.write_text(json.dumps({"schema": "fc08-feed-advisories/1", "advisories": []}, indent=2) + "\n",
                         encoding="utf-8")
        golden_bytes = golden.read_bytes()

        def make(rid, tamper=None, unterminated=()):
            run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=1, queue=1, cost=0.3,
                                            unterminated=unterminated)
            asyncio.run(m["friday"].friday(run, session=session, extractor=valid_extractor(m, tamper), root=box,
                                           advisory_list=(golden, alist)))
            return keys

        def accept(rid, decisions, *extra):
            f = tmp / ("%s.decisions.json" % rid)
            f.write_text(json.dumps(decisions), encoding="utf-8")
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = acc.main([rid, "--decisions", str(f), *extra], inbox_root=box, seen_path=seen, today=TODAY,
                                    data=data, advisory_list=alist, golden_list=golden)
            except Exception as exc:
                return None, "CRASHED %s: %s" % (type(exc).__name__, exc)
            return code, buf.getvalue()

        def untouched(label, said, alist_before, ledger_before):
            files = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file()) if data.exists() else []
            return (not files and alist.read_bytes() == alist_before and seen.read_bytes() == ledger_before,
                    "refused, writing nothing: %s" % label, "%s | files %s" % (said.strip()[:120], files[:3]))

        rid = "feeds-2026-10-02-bbb001"
        keys = make(rid)
        k_acc, k_def, k_def2, k_drop = keys[0], keys[1], keys[2], keys[3]
        decisions = {k_acc: "accept", k_def: "defer", k_def2: "defer", k_drop: "drop"}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        code, said = accept(rid, dict(decisions, **{k_drop: "accept"}))
        out.append(untouched("an accept of an item never extracted", said, a0, l0) + ())
        code, said = accept(rid, decisions, "--dry-run")
        out.append((code == 0 and "DRY RUN" in said and untouched("", said, a0, l0)[0], "a dry run writes nothing",
                    said.strip()[:120]))
        code, said = accept(rid, decisions)
        adv = "ADV-2026-0021"
        xrun = extraction.load_outcomes(rid, box)[k_acc]["extraction_run_id"]
        folder = box / rid
        req = extraction.load_requests(rid, box)[0]
        copies = {data / "advisories" / ("%s-fincen.pdf" % adv.lower()): folder / req["document"]["path"],
                  data / "feeds" / "records" / ("%s.json" % adv): folder / "records" / ("%s.json" % adv),
                  data / "proposals" / ("%s.jsonl" % xrun): folder / "proposals" / ("%s.jsonl" % xrun),
                  data / "telemetry" / ("%s.jsonl" % xrun): folder / "telemetry" / ("%s.jsonl" % xrun)}
        same = all(dst.exists() and dst.read_bytes() == src.read_bytes() for dst, src in copies.items())
        got = json.loads(alist.read_text(encoding="utf-8"))
        entry = got["advisories"][-1]
        out.append((code == 0 and same and entry["advisory_id"] == adv and entry["sha256"] == req["document"]["sha256"]
                    and entry["url"] == req["document"]["url"] and entry["feed"]["run_id"] == rid
                    and len(got["advisories"]) == 1 and golden.read_bytes() == golden_bytes,
                    "an accepted item's document, record, queue and telemetry are copied byte for byte; the LIVE-FEED "
                    "advisory list gains its entry and the golden list is byte-identical",
                    "%s | %s" % (said.strip()[:100], entry.get("advisory_id"))))
        from governance import proposals as gate
        qpath = data / "proposals" / ("%s.jsonl" % xrun)
        props = [gate.Proposal.from_line(json.loads(l), source_file=qpath.name) for l in
                 (qpath.read_text().splitlines() if qpath.exists() else []) if l.strip()]
        clean, quarantined = gate.recheck(props, advisory_list=golden, advisories_dir=data / "advisories",
                                          feed_list=alist)
        out.append((len(clean) == 1 and not quarantined,
                    "the review gate passes the accepted queue against the new entry and the copied document",
                    [q.reason for q in quarantined]))
        entries = ledger.load(seen)
        decided = {"%s:%s" % k: v["decision"] for k, v in entries.items()}
        items = {it["key"]: it for it in inbox.items(inbox.load(rid, box))}
        want = {"%s:%s" % (items[k]["source"], items[k]["item_id"]): d for k, d in ((k_acc, "accept"), (k_drop, "drop"))}
        run_dest = data / "feeds" / "runs" / rid
        out.append((decided == want and runs.classify(rid, box) == runs.ACCEPTED_STATE
                    and all((run_dest / n).exists() for n in ("triage.jsonl", "report.md", "accepted.json", "items.json"))
                    and (run_dest / "telemetry" / ("%s.jsonl" % rid)).exists(),
                    "the ledger holds the accepted and the dropped item and not the two deferred; the run's evidence is "
                    "in data/feeds/runs/<run>/ and the run is marked accepted", decided))
        code, said = accept(rid, decisions)
        out.append((code == 1 and "already accepted" in said, "a second acceptance is refused", said.strip()[:100]))

        for n, (tamper, label) in enumerate((("record", "a record citing text not on its page"),
                                             ("queue", "a queue line the review gate would quarantine"))):
            rid = "feeds-2026-10-02-bbb00%d" % (n + 2)
            keys = make(rid, tamper=tamper)
            snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
            a0, l0 = alist.read_bytes(), seen.read_bytes()
            code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
            now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
            out.append((code == 1 and now == snap and alist.read_bytes() == a0 and seen.read_bytes() == l0,
                        "refused, writing nothing: %s" % label, said.strip()[:140]))

        rid = "feeds-2026-10-02-bbb004"
        keys = make(rid)
        xrun = extraction.load_outcomes(rid, box)[keys[0]]["extraction_run_id"]
        blocker = data / "proposals" / ("%s.jsonl" % xrun)
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("pre-existing\n", encoding="utf-8")
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        out.append((code == 1 and blocker.read_text() == "pre-existing\n" and alist.read_bytes() == a0
                    and seen.read_bytes() == l0, "refused, writing nothing: a target that already exists",
                    said.strip()[:120]))
        blocker.rename(tmp / "moved-blocker")

        rid = "feeds-2026-10-02-bbb005"
        keys = make(rid, unterminated=("toolu_lost",))
        dec = {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        code, said = accept(rid, dec)
        refused = code == 1 and "RECONCILIATION_FAILED" in said and alist.read_bytes() == a0 and seen.read_bytes() == l0
        code2, said2 = accept(rid, dec, "--override-reconciliation", "owner read the transcript; the call was a retry")
        record = json.loads((data / "feeds" / "runs" / rid / "accepted.json").read_text()) if code2 == 0 else {}
        out.append((refused and code2 == 0 and record.get("override_reconciliation", "").startswith("owner read"),
                    "a RECONCILIATION_FAILED run is refused without an override, and accepted with one, the reason "
                    "recorded", "%s | %s" % (said.strip()[:80], said2.strip()[:60])))

        rid = "feeds-2026-10-02-bbb006"
        keys = make(rid)
        snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        real = acc.ledger.record_decisions
        acc.ledger = types.SimpleNamespace(**{k: getattr(ledger, k) for k in dir(ledger) if not k.startswith("__")})
        acc.ledger.record_decisions = lambda *a, **k: (_ for _ in ()).throw(ValueError("disk full (planted)"))
        code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        acc.ledger.record_decisions = real
        now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        out.append((code == 1 and "disk full" in said and now == snap and alist.read_bytes() == a0
                    and seen.read_bytes() == l0 and runs.classify(rid, box) == runs.PENDING,
                    "a failure while writing removes every copy this call made and restores the advisory list",
                    said.strip()[:120]))

        young, old = "feeds-2026-09-25-ccc001", "feeds-2026-09-19-ccc002"
        for r in (young, old, "feeds-2026-09-01-ccc003"):
            inbox.save(r, {"run_id": r, "sources": {"ofac": {"items": [{"key": "ofac:%016x" % len(r), "source": "ofac",
                                                                          "item_id": r}]}}}, box)
        inbox.save("feeds-2026-09-02-ccc004", {"run_id": "feeds-2026-09-02-ccc004", "eval": True,
                                               "sources": {"ofac": {"items": [{"key": "ofac:1", "source": "ofac"}]}}}, box)
        l0 = seen.read_bytes()
        blocking = [r for r, _ in runs.blocking(box, TODAY)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            young_code = acc.main(["--expire", young], inbox_root=box, seen_path=seen, today=TODAY, data=data,
                                  advisory_list=alist)
            all_code = acc.main(["--expire"], inbox_root=box, seen_path=seen, today=TODAY, data=data, advisory_list=alist)
        out.append((young in blocking and old not in blocking and "feeds-2026-09-02-ccc004" not in
                    [r for r, _ in runs.pending(box, TODAY)] and young_code == 1 and all_code == 0
                    and (box / "expired" / old).is_dir() and (box / "expired" / "feeds-2026-09-01-ccc003").is_dir()
                    and (box / young).is_dir() and seen.read_bytes() == l0,
                    "a pending run under 14 days blocks and refuses --expire; at 14+ it moves to inbox/expired/, the "
                    "ledger untouched; an eval run is never pending", "%s | blocking %s" % (buf.getvalue().strip()[:80],
                                                                                          blocking)))

        cat = tmp / "catalogue.json"
        cat.write_text(json.dumps({"items": [{"source": "ofsi", "item_id": "c%d" % i} for i in range(4)]}), encoding="utf-8")
        seed_ledger = tmp / "seed-ledger.json"
        seed_ledger.write_text(ledger.dump([]), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            dry = acc.seed_catalogue(TODAY, seed_ledger, cat, dry_run=True)
            first = acc.seed_catalogue(TODAY, seed_ledger, cat)
            second = acc.seed_catalogue(TODAY, seed_ledger, cat)
        got = ledger.load(seed_ledger)
        label = "catalogue:%s" % hashlib.sha256(cat.read_bytes()).hexdigest()[:12]
        out.append((dry == 0 and first == 0 and second == 1 and len(got) == 4
                    and all(e["decision"] == "drop" and e["first_seen_run"] == label for e in got.values()),
                    "--seed-catalogue records every catalogue item as a drop under catalogue:<sha12>, once",
                    buf.getvalue().strip().splitlines()[-1][:100]))
    out.append((git_status() == before, "the repository's git status is unchanged", ""))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin accept_run end to end")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:160]))
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

- [ ] **Step 2: Replace `tools/accept_run.py`**

```python
"""
Decide the items of one feeds run: the ONLY way a live result enters tracked data (spec section 2).

Usage:
    python tools/accept_run.py RUN_ID                     # show the report, ask accept/drop/defer per item, confirm
    python tools/accept_run.py RUN_ID --decisions FILE [--dry-run] [--override-reconciliation REASON]
    python tools/accept_run.py --pending                  # every run in the inbox and what it is waiting for
    python tools/accept_run.py --expire [RUN_ID]          # move pending runs 14+ days old to inbox/expired/
    python tools/accept_run.py --seed-catalogue [--dry-run]  # ONE-TIME: the back-catalogue's items, as drops

FILE is JSON, {"<item key>": "accept" | "drop" | "defer"}, one entry for EVERY item the run listed as new.
  accept  only an item the run EXTRACTED. It gets the advisory id its extraction was allocated (the id its
          record and every proposal already carry), a new entry in data/feeds/advisory_list.json (source, URL,
          sha256, date, the feed run) -- NOT evals/golden/advisory_list.json, the labelled corpus, which every
          digest batch pins by sha256 (measured 2026-09-28: one appended entry fails build_digests --check and
          check_digest_batch); the review gate reads both lists -- and its files are COPIED into tracked folders:
            the document      -> data/advisories/<adv-id>-<source>.<pdf|html>   (gitignored, as in slice 1)
            the record        -> data/feeds/records/<ADV-id>.json  (NOT data/records/: that folder is slice 1's
                                 pinned evidence -- check_citation_repair pins its file set and actor_resolution
                                 --check reads it; measured 2026-09-28, one planted record fails both)
            the queue         -> data/proposals/<extraction run id>.jsonl   (tools/review.py reads it there)
            the telemetry     -> data/telemetry/<extraction run id>.jsonl
  drop    any item. Recorded in the ledger, never listed again.
  defer   any item. NOT recorded: it is listed again next Friday (spec section 1: unfinished and budget-deferred
          items come back).
Once per run: the run's evidence -- items.json, triage.jsonl, the extraction files, run.json, report.md,
accepted.json and the orchestrator's telemetry -- is copied to data/feeds/runs/<run_id>/, so every ledger
decision is traceable to the verdict and reason behind it from a clone. The inbox copy is left whole.

VALIDATES EVERYTHING FIRST, and refuses the whole run on any failure, writing nothing:
  - the run exists, is not an eval run, is not already accepted, and every listed item is decided exactly once;
  - the run's reconciliation (feeds/reconcile.py) is acceptable -- a FAILED or RECONCILIATION_FAILED run needs
    --override-reconciliation "<reason>", which is recorded -- and a REFUSED run has nothing to accept;
  - per accepted item: the record validates against schemas/advisory.py, names its allocated id and the pinned
    document's sha256, names only library typology ids, and every citation is found on the page it names in
    the pinned document (the shared matcher, PDF or HTML); every queue line passes the review gate's own
    re-check (governance/proposals.recheck) against the advisory-list entry about to be written; its
    extraction session completed with a clean terminal_check (or the override); nothing it would write exists;
  - no listed item is already in the ledger.
Then writes, in this order: the copies, the live-feed advisory list, the ledger (accepted and dropped items only), and
accepted.json in the run's inbox folder. A failure before the ledger removes the copies this call made and
restores the advisory list. The owner commits; proposals then go through tools/review.py as in slice 1.

--expire moves a pending run of 14 days or more to inbox/expired/<run_id>/ and does not touch the ledger, so its
items return (feeds/runs.py). --seed-catalogue records every evals/feeds/catalogue.json item as a drop, run
"catalogue:<sha256[:12]>", refusing if any is already decided (owner decision 3, slice 2 C).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import extraction, inbox, ledger, reconcile, runs  # noqa: E402

DATA = ROOT / "data"
GOLDEN_LIST = ROOT / "evals" / "golden" / "advisory_list.json"
ADVISORY_LIST = DATA / "feeds" / "advisory_list.json"   # the live-feed list: this tool is its only writer
FEED_LIST_SCHEMA = "fc08-feed-advisories/1"
CATALOGUE = ROOT / "evals" / "feeds" / "catalogue.json"
DECISIONS = ("accept", "drop", "defer")
PUBLISHERS = {"fincen": "FinCEN (US Treasury)", "ofsi": "OFSI (HM Treasury)", "ofac": "OFAC (US Treasury)"}
OVERRIDE_MIN = 10
RUN_FILES = ("items.json", "triage.jsonl", extraction.REQUESTS, extraction.ALLOCATIONS, extraction.OUTCOMES,
             reconcile.RUN_JSON, "report.md")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def targets(adv: str, source: str, ext: str, xrun: str, data: Path) -> dict:
    return {"document": data / "advisories" / ("%s-%s.%s" % (adv.lower(), source, ext)),
            "record": data / "feeds" / "records" / ("%s.json" % adv),
            "queue": data / "proposals" / ("%s.jsonl" % xrun),
            "telemetry": data / "telemetry" / ("%s.jsonl" % xrun)}


class _Unreadable:
    """A quarantine-shaped reason for a queue line that cannot even be read."""

    def __init__(self, reason):
        self.reason = "unreadable queue line: %s" % reason


def _check_accepted(run_id, key, item, verdict, outcome, request, alloc, folder, data, alist_entries, override):
    """(the plan for one accepted item, problems). Nothing is written here."""
    from pydantic import ValidationError
    from schemas.advisory import AdvisoryRecord
    from schemas.citation_match import PageIndex
    from governance import proposals as gate
    sys.path.insert(0, str(ROOT / "evals"))
    from check_citations import check_record_citations
    problems = []
    if not outcome or outcome.get("status") != "extracted":
        return None, ["%s cannot be accepted: it was not extracted (%s)" % (key, (outcome or {}).get("status", "never queued"))]
    adv, xrun = outcome["advisory_id"], outcome["extraction_run_id"]
    doc = folder / request["document"]["path"]
    ext = doc.suffix.lstrip(".")
    t = targets(adv, item["source"], ext, xrun, data)
    if alloc != adv:
        problems.append("%s: the outcome names %s but the run allocated %s" % (key, adv, alloc))
    if adv in {a["advisory_id"] for a in alist_entries}:
        problems.append("%s: %s is already in the advisory list" % (key, adv))
    if not doc.exists() or _sha(doc) != request["document"]["sha256"]:
        return None, problems + ["%s: the pinned document is missing or changed" % key]
    for name, path in sorted(t.items()):
        if path.exists():
            problems.append("%s: %s already exists; nothing is overwritten" % (key, path))
    record_path = folder / outcome["record"]
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    try:
        record = AdvisoryRecord.model_validate(raw)
    except ValidationError as exc:
        return None, problems + ["%s: the record does not validate: %s" % (key, str(exc).splitlines()[0])]
    if record.advisory_id != adv or record.source.document_sha256 != request["document"]["sha256"]:
        problems.append("%s: the record names %s and document %s..., not %s and the pinned %s..." % (
            key, record.advisory_id, record.source.document_sha256[:12], adv, request["document"]["sha256"][:12]))
    known = gate._library_ids(gate.LIBRARY)
    unknown = sorted({x.typology_id for x in record.typologies if x.typology_id and x.typology_id not in known})
    if unknown:
        problems.append("%s: the record names typology ids the library does not hold: %s" % (key, unknown))
    index = PageIndex.from_document(doc)
    bad = [d for _, ok, d in check_record_citations(adv, raw, index) if not ok]
    if bad:
        problems.append("%s: %d citation(s) are not on the page they name, first: %s p%s (%s)" % (
            key, len(bad), bad[0]["section"], bad[0]["page"], bad[0]["kind"]))
    entry = {"advisory_id": adv, "file": t["document"].name, "publisher": PUBLISHERS[item["source"]],
             "source_type": item["source"], "title": item["title"], "published_on": item["published"],
             "published_on_precision": "day", "url": request["document"].get("url") or item["url"],
             "source_matrix_tier": "live feed", "sha256": request["document"]["sha256"],
             "bytes": doc.stat().st_size, "pages": len(index),
             "selection_rationale": "live feed run %s, item %s: triaged relevant: %s" % (run_id, key, verdict["reason"]),
             "feed": {"run_id": run_id, "key": key, "item_id": item["item_id"], "listed_url": item["url"],
                      "extraction_run_id": xrun}}
    queue = folder / inbox.PROPOSALS / ("%s.jsonl" % xrun)
    lines = [json.loads(l) for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()] if queue.exists() else []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "advisory_list.json").write_text(json.dumps({"advisories": [entry]}), encoding="utf-8")
        (tmp / "docs").mkdir()
        shutil.copyfile(doc, tmp / "docs" / entry["file"])
        try:
            props = [gate.Proposal.from_line(d, source_file=queue.name) for d in lines]
            clean, quarantined = gate.recheck(props, advisory_list=tmp / "advisory_list.json",
                                              advisories_dir=tmp / "docs", feed_list=None)
        except (KeyError, TypeError, ValueError) as exc:
            clean, quarantined = [], [_Unreadable(str(exc))]
    for q in quarantined:
        problems.append("%s: a proposal the review gate would quarantine: %s" % (key, q.reason[:160]))
    if any(p.run_id != xrun or p.advisory_id != adv for p in clean):
        problems.append("%s: a queue line names another run or advisory" % key)
    tel = folder / inbox.TELEMETRY / ("%s.jsonl" % xrun)
    s = reconcile.session(tel) if tel.exists() else None
    if s is None or not s["completed"]:
        problems.append("%s: the extraction session's telemetry is missing or never completed" % key)
    elif (s["unterminated"] or s["duplicated"]) and not override:
        problems.append("%s: the extraction session has %d unterminated / %d duplicated tool call(s); accepting it "
                        "needs --override-reconciliation" % (key, len(s["unterminated"]), len(s["duplicated"])))
    copies = {"document": (doc, t["document"]), "record": (record_path, t["record"]), "queue": (queue, t["queue"]),
              "telemetry": (tel, t["telemetry"])}
    return {"key": key, "advisory_id": adv, "entry": entry, "copies": copies, "proposals": len(lines)}, problems


def plan(run_id: str, decisions: dict, *, inbox_root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         data: Path = DATA, advisory_list: Path = ADVISORY_LIST, golden_list: Path = GOLDEN_LIST,
         override: str = None) -> dict:
    """Validate everything and return what to write. Raises ValueError, naming every problem, on any."""
    if not (inbox.run_dir(run_id, inbox_root) / inbox.ITEMS).exists():
        raise ValueError("run %s has no %s in the inbox" % (run_id, inbox.ITEMS))
    state = inbox.load(run_id, inbox_root)
    if state.get("eval"):
        raise ValueError("run %s is an eval run; eval runs never reach the ledger" % run_id)
    folder = inbox.run_dir(run_id, inbox_root)
    if (folder / runs.ACCEPTED).exists():
        raise ValueError("run %s was already accepted" % run_id)
    if not isinstance(decisions, dict):
        raise ValueError("the decisions file must be a JSON object of item key -> decision")
    listed = {it["key"]: it for it in inbox.items(state)}
    missing, extra = sorted(set(listed) - set(decisions)), sorted(set(decisions) - set(listed))
    if missing or extra:
        raise ValueError("the decisions must cover every listed item exactly: missing %s, not listed %s"
                         % (missing, extra))
    bad = sorted(k for k, v in decisions.items() if v not in DECISIONS)
    if bad:
        raise ValueError("these decisions are not accept, drop or defer: %s" % bad)
    if override is not None and len(override.strip()) < OVERRIDE_MIN:
        raise ValueError("an override needs a reason of at least %d characters" % OVERRIDE_MIN)
    rec = reconcile.reconcile_run(run_id, inbox_root)
    if rec["status"] == reconcile.REFUSED:
        raise ValueError("run %s was refused before any agent ran; there is nothing to accept" % run_id)
    if rec["status"] not in reconcile.ACCEPTABLE and not override:
        raise ValueError("run %s is %s (%s); accepting it needs --override-reconciliation \"<reason>\"" % (
            run_id, rec["status"], "; ".join(rec["problems"][:3]) or rec["failure"] or "no session"))
    seen = ledger.load(seen_path)
    already = sorted(k for k, it in listed.items() if (it["source"], it["item_id"]) in seen)
    if already:
        raise ValueError("already decided in an earlier run: %s" % already)
    alist = (json.loads(Path(advisory_list).read_text(encoding="utf-8")) if Path(advisory_list).exists()
             else {"schema": FEED_LIST_SCHEMA, "advisories": []})
    golden = json.loads(Path(golden_list).read_text(encoding="utf-8"))["advisories"] if Path(golden_list).exists() else []
    verdicts = rec["verdicts"]
    requests = {r["key"]: r for r in extraction.load_requests(run_id, inbox_root)}
    outcomes = extraction.load_outcomes(run_id, inbox_root)
    allocations = extraction.load_allocations(run_id, inbox_root)
    problems, accepted = [], []
    for key in sorted(k for k, v in decisions.items() if v == "accept"):
        got, why = _check_accepted(run_id, key, listed[key], verdicts.get(key), outcomes.get(key), requests.get(key),
                                   allocations.get(key), folder, Path(data), golden + alist["advisories"], override)
        problems += why
        if got:
            accepted.append(got)
    run_dest = Path(data) / "feeds" / "runs" / run_id
    if run_dest.exists():
        problems.append("%s already exists; nothing is overwritten" % run_dest)
    if problems:
        raise ValueError("; ".join(problems))
    entries = [{"source": listed[k]["source"], "item_id": listed[k]["item_id"], "decision": decisions[k]}
               for k in sorted(listed) if decisions[k] != "defer"]
    return {"run_id": run_id, "accepted": accepted, "entries": entries, "status": rec["status"],
            "deferred": sorted(k for k, v in decisions.items() if v == "defer"), "run_dest": run_dest,
            "folder": folder, "alist": alist, "override": override}


def apply(p: dict, today: date, *, inbox_root: Path, seen_path: Path, advisory_list: Path) -> None:
    created = []
    original = Path(advisory_list).read_text(encoding="utf-8") if Path(advisory_list).exists() else None
    try:
        for a in p["accepted"]:
            for src, dst in a["copies"].values():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                created.append(dst)
        dest = p["run_dest"]
        record = {"run_id": p["run_id"], "decided_on": today.isoformat(), "status": p["status"],
                  "override_reconciliation": p["override"],
                  "accepted": {a["key"]: a["advisory_id"] for a in p["accepted"]},
                  "dropped": sorted("%s:%s" % (e["source"], e["item_id"]) for e in p["entries"] if e["decision"] == "drop"),
                  "deferred": p["deferred"]}
        for name in RUN_FILES:
            if (p["folder"] / name).exists():
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p["folder"] / name, dest / name)
                created.append(dest / name)
        orchestrator = p["folder"] / inbox.TELEMETRY / ("%s.jsonl" % p["run_id"])
        if orchestrator.exists():
            (dest / "telemetry").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(orchestrator, dest / "telemetry" / orchestrator.name)
            created.append(dest / "telemetry" / orchestrator.name)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / runs.ACCEPTED).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        created.append(dest / runs.ACCEPTED)
        if p["accepted"]:
            alist = p["alist"]
            alist["advisories"] += [a["entry"] for a in p["accepted"]]
            Path(advisory_list).parent.mkdir(parents=True, exist_ok=True)
            Path(advisory_list).write_text(json.dumps(alist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ledger.record_decisions(p["run_id"], today.isoformat(), p["entries"], path=seen_path)
    except BaseException:
        for path in reversed(created):
            if path.exists():
                path.unlink()
        if original is None:
            if Path(advisory_list).exists():
                Path(advisory_list).unlink()
        else:
            Path(advisory_list).write_text(original, encoding="utf-8")
        raise
    runs.mark_accepted(p["run_id"], record, inbox_root)


def ask(run_id: str, inbox_root: Path) -> dict:
    """The interactive form: the report, then one decision per item, with the evidence's default."""
    folder = inbox.run_dir(run_id, inbox_root)
    report = folder / "report.md"
    print(report.read_text(encoding="utf-8") if report.exists() else "(no report.md)")
    rec = reconcile.reconcile_run(run_id, inbox_root)
    outcomes = extraction.load_outcomes(run_id, inbox_root)
    decisions = {}
    for it in inbox.items(inbox.load(run_id, inbox_root)):
        k = it["key"]
        v = rec["verdicts"].get(k, {}).get("verdict")
        default = "accept" if outcomes.get(k, {}).get("status") == "extracted" else ("drop" if v == "not_relevant"
                                                                                      else "defer")
        answer = input("%s  %s\n   verdict %s, extraction %s  [a]ccept/[d]rop/de[f]er (default %s): " % (
            k, it["title"][:90], v, outcomes.get(k, {}).get("status", "-"), default)).strip().lower()
        decisions[k] = {"a": "accept", "d": "drop", "f": "defer", "": default}.get(answer[:1], answer)
    path = folder / "decisions.json"
    path.write_text(json.dumps(decisions, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("decisions written to %s" % path)
    return decisions


def seed_catalogue(today: date, seen_path: Path, catalogue: Path = CATALOGUE, dry_run: bool = False) -> int:
    raw = Path(catalogue).read_bytes()
    items = json.loads(raw)["items"]
    run_label = "catalogue:%s" % hashlib.sha256(raw).hexdigest()[:12]
    entries = [{"source": it["source"], "item_id": it["item_id"], "decision": "drop"} for it in items]
    seen = ledger.load(seen_path)
    already = sorted("%s:%s" % (e["source"], e["item_id"]) for e in entries if (e["source"], e["item_id"]) in seen)
    if already:
        print("REFUSED: %d catalogue item(s) are already decided, e.g. %s" % (len(already), already[0]))
        return 1
    if dry_run:
        print("DRY RUN: would record %d catalogue item(s) as drops under %s" % (len(entries), run_label))
        return 0
    ledger.record_decisions(run_label, today.isoformat(), entries, path=seen_path)
    print("RECORDED: %d catalogue item(s) as drops under %s in %s" % (len(entries), run_label, seen_path))
    return 0


def main(argv: list, *, inbox_root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         today: date = None, data: Path = DATA, advisory_list: Path = ADVISORY_LIST, golden_list: Path = GOLDEN_LIST,
         catalogue: Path = CATALOGUE) -> int:
    ap = argparse.ArgumentParser(description="Decide the items of one feeds run")
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--decisions", type=Path, help="JSON: item key -> accept | drop | defer")
    ap.add_argument("--dry-run", action="store_true", help="validate and say what would be written")
    ap.add_argument("--override-reconciliation", metavar="REASON", help="accept a FAILED or RECONCILIATION_FAILED run")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--expire", action="store_true")
    ap.add_argument("--seed-catalogue", action="store_true")
    args = ap.parse_args(argv)
    today = today or date.today()
    if args.seed_catalogue:
        return seed_catalogue(today, seen_path, catalogue, args.dry_run)
    if args.pending:
        for r in runs.run_ids(inbox_root):
            print("%-26s %s" % (r, runs.classify(r, inbox_root)))
        return 0
    if args.expire:
        todo = [(args.run_id, None)] if args.run_id else runs.expirable(inbox_root, today)
        for r, _ in todo:
            try:
                print("EXPIRED: %s -> %s" % (r, runs.expire(r, inbox_root, today)))
            except ValueError as exc:
                print("REFUSED: %s" % exc)
                return 1
        return 0
    if not args.run_id:
        ap.error("RUN_ID is required")
    try:
        decisions = (json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions
                     else ask(args.run_id, inbox_root))
        p = plan(args.run_id, decisions, inbox_root=inbox_root, seen_path=seen_path, data=data,
                 advisory_list=advisory_list, golden_list=golden_list, override=args.override_reconciliation)
    except (ValueError, OSError) as exc:
        print("REFUSED: %s" % exc)
        return 1
    what = "%d accepted (%s), %d dropped, %d deferred" % (
        len(p["accepted"]), ", ".join(a["advisory_id"] for a in p["accepted"]) or "-",
        sum(1 for e in p["entries"] if e["decision"] == "drop"), len(p["deferred"]))
    if args.dry_run:
        print("DRY RUN: would record %d decision(s) for run %s: %s" % (len(p["entries"]), args.run_id, what))
        return 0
    if not args.decisions and input("Apply: %s? [y/N] " % what).strip().lower() != "y":
        print("NOTHING WRITTEN")
        return 1
    try:
        apply(p, today, inbox_root=inbox_root, seen_path=seen_path, advisory_list=advisory_list)
    except ValueError as exc:
        print("REFUSED: %s" % exc)
        return 1
    print("RECORDED: %d decision(s) for run %s in %s: %s. Commit, then review the proposals with tools/review.py."
          % (len(p["entries"]), args.run_id, seen_path, what))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: The gate reads the live-feed list; A's ledger guard uses temporary data paths**

In `governance/proposals.py` (edit `t5b-gate-const`), replace:

```python
ADVISORY_LIST = ROOT / "evals" / "golden" / "advisory_list.json"
```

with:

```python
ADVISORY_LIST = ROOT / "evals" / "golden" / "advisory_list.json"
# Slice 2 C: advisories accepted from the live feeds (tools/accept_run.py is the only writer). Kept apart from
# the golden list, which is the labelled corpus and a pinned input of every digest batch.
FEED_ADVISORY_LIST = ROOT / "data" / "feeds" / "advisory_list.json"
```

In `governance/proposals.py` (edit `t5b-gate-advisories`), replace:

```python
def _advisories(path: Path) -> Dict[str, dict]:
    return {a["advisory_id"]: a for a in json.loads(path.read_text(encoding="utf-8"))["advisories"]}
```

with:

```python
def _advisories(path: Path, feed_list: Optional[Path] = None) -> Dict[str, dict]:
    """The golden list, plus the live-feed list when it exists. An id in both is refused, never shadowed."""
    out = {a["advisory_id"]: a for a in json.loads(path.read_text(encoding="utf-8"))["advisories"]}
    if feed_list is not None and Path(feed_list).exists():
        feed = {a["advisory_id"]: a for a in json.loads(Path(feed_list).read_text(encoding="utf-8"))["advisories"]}
        both = sorted(set(out) & set(feed))
        if both:
            raise ValueError("advisory ids in both the golden and the live-feed list: %s" % both)
        out.update(feed)
    return out
```

In `governance/proposals.py` (edit `t5b-gate-recheck`), replace:

```python
def recheck(proposals, advisory_list: Path = ADVISORY_LIST, advisories_dir: Path = ADVISORIES_DIR,
            library: Path = LIBRARY) -> Tuple[List[Proposal], List[Quarantined]]:
    """Split proposals into clean and quarantined. A quarantined proposal can never be approved."""
    advisories = _advisories(advisory_list)
```

with:

```python
def recheck(proposals, advisory_list: Path = ADVISORY_LIST, advisories_dir: Path = ADVISORIES_DIR,
            library: Path = LIBRARY, feed_list: Optional[Path] = FEED_ADVISORY_LIST) -> Tuple[List[Proposal], List[Quarantined]]:
    """Split proposals into clean and quarantined. A quarantined proposal can never be approved.
    `feed_list` is the live-feed advisory list (slice 2 C); None leaves it out."""
    advisories = _advisories(advisory_list, feed_list)
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-doc-usage`), replace:

```python
    python evals/check_feeds_ledger.py --mutate accept-allowed  # accept_run records an accept it cannot carry out
```

with:

```python
    python evals/check_feeds_ledger.py --mutate accept-allowed  # accept_run accepts an item that was never extracted
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-doc-body`), replace:

```python
exactly once. In sub-project A an "accept" is refused: accepting also moves the item's record and
document into tracked data, which is sub-project C, and a ledger saying "accepted" over nothing
moved would be false.
```

with:

```python
exactly once. An "accept" of an item the run never extracted is refused (sub-project C built the
accept path, pinned end to end by evals/check_accept_run.py): a ledger saying "accepted" over
nothing moved would be false. The fixture runs here have no session, so reconciliation calls them
FAILED and each decision passes --override-reconciliation, as a person would have to.
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-mutation`), replace:

```python
    "accept-allowed": (ACCEPT, "    if accepted:\n", "    if False:\n"),
```

with:

```python
    "accept-allowed": (ACCEPT, '    if not outcome or outcome.get("status") != "extracted":\n', "    if False:\n"),
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-override`), replace:

```python
                    code = accept.main([run_id, "--decisions", str(f), *extra], inbox_root=root, seen_path=seen,
                                       today=TODAY)
```

with:

```python
                    code = accept.main([run_id, "--decisions", str(f), "--override-reconciliation",
                                        "ledger guard fixture: no session ran", *extra], inbox_root=root,
                                       seen_path=seen, today=TODAY, data=tmp / "data", advisory_list=alist)
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-writers`), replace:

```python
                                                  "evals/check_feeds_ledger.py", "evals/check_feeds_server.py",
                                                  "evals/check_feeds_triage.py"):
```

with:

```python
                                                  "evals/check_feeds_ledger.py", "evals/check_feeds_server.py",
                                                  "evals/check_feeds_triage.py", "evals/check_accept_run.py"):
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-twice`), replace:

```python
        out.append((code == 1 and "already decided" in said, "the same run cannot be decided twice", said.strip()[:160]))
```

with:

```python
        out.append((code == 1 and "already accepted" in said and ledger.load(seen) == got,
                    "the same run cannot be decided twice (accept_run marks it accepted), and the ledger is unchanged",
                    said.strip()[:160]))
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-temp-data`), replace:

```python
        seen.write_text(ledger.dump([]), encoding="utf-8")
```

with:

```python
        seen.write_text(ledger.dump([]), encoding="utf-8")
        # accept_run now copies a run's evidence into data/feeds/runs/: every call here names TEMPORARY data
        # and advisory-list paths. Measured while drafting C: without them this guard wrote into the checkout.
        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": []}), encoding="utf-8")
```

In `evals/check_feeds_ledger.py` (edit `t5-ledger-temp-data-2`), replace:

```python
            code = accept.main(["feeds-2026-10-02-000000", "--decisions", str(f)], inbox_root=root, seen_path=seen)
```

with:

```python
            code = accept.main(["feeds-2026-10-02-000000", "--decisions", str(f)], inbox_root=root, seen_path=seen,
                               data=tmp / "data", advisory_list=alist)
```


- [ ] **Step 4: Register the guard**

In `tools/check_all.py` (edit `t5-check-all`), replace:

```python
    ("check_friday_run", ["evals/check_friday_run.py"], "cold"),
```

with:

```python
    ("check_friday_run", ["evals/check_friday_run.py"], "cold"),
    ("check_accept_run", ["evals/check_accept_run.py"], "cold"),
```


- [ ] **Step 5: Run it, each mutation, and A's ledger guard with all of its**

```bash
.venv/bin/python evals/check_accept_run.py
for m in no-citation-check no-gate-recheck ledger-defers no-override-needed overwrite-target no-rollback slice1-records; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_accept_run.py --mutate $m | tail -1
done
.venv/bin/python evals/check_feeds_ledger.py | tail -1
for m in unsorted allow-reseen escape-inbox overwrite-pin skip-coverage accept-allowed newline-run-id accept-eval-run; do
  PYTHONPYCACHEPREFIX=/tmp/fc08-mut-l-$m .venv/bin/python evals/check_feeds_ledger.py --mutate $m | tail -1
done
.venv/bin/python evals/check_review_gate.py | tail -1
git status --short
```

Expected:
- `check_accept_run`: `HELD`, 14 checks, and seven mutations detected;
- `check_feeds_ledger`: `HELD`, 20 checks, and eight mutations detected;
- `check_review_gate`: `HELD`;
- `git status` shows only the files this task changed. **No `data/feeds/runs/`**: if one appears, a guard wrote into the checkout, and that is a defect to fix before committing.

- [ ] **Step 6: Commit**

```bash
git add tools/accept_run.py evals/check_accept_run.py governance/proposals.py evals/check_feeds_ledger.py tools/check_all.py
git commit -m "Slice 2 C1: accept_run end to end -- validate everything, copy, write the ledger last; live advisories get their own list"
```

---

### Task 6: the resolver in the extractor's prompt, and the one planned republish

**This is the only C1 task that changes the published page.** STOP before Step 4 and get the owner's go.

**Files:**
- Modify: `agents/extract_advisory.py` (`SYSTEM_PROMPT`)
- Rebuild: `site/threat-intel/index.html`; then `site/PUBLISHED` through the publish procedure

- [ ] **Step 1: The prompt change (spec section 4: the resolver named, exact matches only, suggestions labelled)**

In `agents/extract_advisory.py` (edit `t2-extractor-prompt`), replace:

```python
- When a result says its doctrine is authored as another id, prefer that id.
```

with:

```python
- When a result says its doctrine is authored as another id, prefer that id.
- For each actor the document names (a person or an organisation, never a category), call knowledge_centre_resolve_actor with the name as the document gives it. Only a reply starting "Resolved:" is an identity: note it in extraction_notes as "name -> actor_id". A reply listing similar names is a suggestion for a human, not a resolution: if you mention it, label it a suggestion, and never treat a suggested actor_id as the actor's identity.
```


- [ ] **Step 2: Rebuild the page, and see exactly one word change**

```bash
.venv/bin/python tools/build_walkthrough.py
git diff --word-diff site/threat-intel/index.html | grep -o '\[-[^]]*-\]{+[^}]*+}'
```

Expected: `[-do not name-]{+name+}`, and nothing else. Anything more means the page's other inputs have moved; STOP and report.

- [ ] **Step 3: Run the walkthrough guards cold**

```bash
.venv/bin/python evals/check_walkthrough.py | tail -1
.venv/bin/python tools/build_walkthrough.py --check
.venv/bin/python evals/check_published_walkthrough.py --cold | tail -1
```

Expected:
- `check_walkthrough`: `HELD`;
- `build_walkthrough --check`: a fresh build;
- `check_published_walkthrough --cold`: **FAIL**, "the committed page changed since it was published". That is the republish obligation, and it refuses every commit until Step 5.

- [ ] **Step 4: STOP: the owner's go to republish**

Tell the owner:
- the one-word diff;
- that no commit can land until the republish is committed in both repositories.

Do not publish without the go.

- [ ] **Step 5: Republish by CLAUDE.md's procedure, exactly**

Follow steps 0 to 7 of "The publish procedure, on the owner's go" in `CLAUDE.md`:
- fetch the shared portfolio first;
- step 3 (the Track 2 merge) is **not** needed; it was first-publish only;
- step 6 commits `site/PUBLISHED` **together with** `agents/extract_advisory.py` and the rebuilt `site/threat-intel/index.html`, using the message:

  `Slice 2 C1: the extractor names the resolver; republish the walkthrough (one flag)`

- step 7 pushes only on the owner's word.

---

### Task 7: CLAUDE.md

- [ ] **Step 1: Add the C1 entry after B's section**, and fix the file map rows for `tools/accept_run.py` ("In A it records DROPS only") and `agents/orchestrate_feeds.py` ("triage-only in B"):

```markdown
## Slice 2: extraction, the Friday run and accept_run (sub-project C1, built <DATE>)

Plan: `docs/superpowers/plans/<DATE>-slice2-c1-extraction-and-acceptance.md`.

| File | What it holds |
|---|---|
| `schemas/citation_match.py` (C1) | `document_texts` / `PageIndex.from_document`: THE loader for a PDF or a pinned HTML page, by suffix; extractor, propose_link, the gate and check_citations all use it |
| `feeds/extraction.py` | the agent REQUESTS, code EXTRACTS: one request per relevant item, at most 3 per run; the document chosen by rule (the ONE linked PDF on the source's `document_hosts`, else the page; several = refused); advisory ids allocated when an extraction starts, never reused |
| `agents/orchestrate_feeds.py` (C1) | two modes: EVAL (B's four tools, B's prompt bytes) and LIVE (plus feeds_extract, prompt = B's bytes + an appended section); the budget pinned here; a live server gets FEEDS_CATALOGUE blank |
| `tools/friday_run.py` | one live run: the session, then slice 1's extract per request while spend + US$1 <= US$5, then reconciliation and report.md on EVERY run |
| `feeds/reconcile.py`, `feeds/report.py`, `feeds/runs.py` | status (REFUSED, FAILED, RECONCILIATION_FAILED, UNFINISHED, NOTHING_NEW, COMPLETE); the report; which runs are pending (eval runs never) |
| `tools/accept_run.py` (C1) | accept / drop / defer per item; validates everything first (schema, citations on the pinned document, the review gate's own re-check); COPIES to data/advisories, data/feeds/records, data/proposals, data/telemetry, data/feeds/runs/<run>/; the live-feed list data/feeds/advisory_list.json; the ledger last |

**Accepted live records are NOT in data/records/ and live advisories are NOT in evals/golden/advisory_list.json** -- measured 2026-09-28: either one refuses every commit (check_citation_repair and actor_resolution pin data/records; the current digest batch pins the golden list by sha256). The gate reads both advisory lists.
**Every guard that calls accept_run passes temporary data paths**: without them A's ledger guard wrote data/feeds/runs/ into the checkout.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Slice 2 C1: CLAUDE.md -- extraction, the Friday run and accept_run"
```

---

### Task 8: STOP: seed the ledger with the back-catalogue (decision 3)

This writes the tracked ledger, so it needs the owner's go. Skip this task if the owner chose (c). For (b), see the note at the end of this task.

- [ ] **Step 1: Dry run, then report the count**

```bash
.venv/bin/python tools/accept_run.py --seed-catalogue --dry-run
```

Expected: `DRY RUN: would record 60 catalogue item(s) as drops under catalogue:<sha12>`.

- [ ] **Step 2: STOP: the owner's go**

- [ ] **Step 3: Seed, check, commit**

```bash
.venv/bin/python tools/accept_run.py --seed-catalogue
.venv/bin/python tools/check_all.py --cold | tail -1
git add data/feeds/seen.json
git commit -m "Slice 2 C1: seed the ledger with the 60 back-catalogue items as drops (owner decision 3)"
```

For (b): `--seed-catalogue` seeds every catalogue item. Filtering to the not-relevant ones is a one-line change to `seed_catalogue`, made and guarded before this step.

---

### Task 9: STOP: the first manual dry run

**Cost: capped at US$5.00 by the run's own rule** (with the overshoot noted above). Expected US$2 to US$3.50. Wall clock about 15 to 25 minutes (three extractions at about 4 to 5 minutes each).

- [ ] **Step 1: Preconditions**
  - `main` holds Tasks 1 to 8, or the run is on the C1 branch (manual runs do not check the branch; C2's scheduled runs do).
  - Task 6 is published.
  - `.venv/bin/python tools/check_all.py` passes in full.

- [ ] **Step 2: STOP: the owner's go, with the cost above**

- [ ] **Step 3: Run it**

```bash
unset ANTHROPIC_API_KEY FEEDS_CATALOGUE FEEDS_CATALOGUE_BATCH
claude auth status | grep -o '"authMethod": *"[^"]*"'     # must not be api_key
.venv/bin/python tools/friday_run.py --plan
.venv/bin/python tools/friday_run.py
```

Expected: one line, `feeds-YYYY-MM-DD-xxxxxx: <STATUS> -- inbox/<run>/report.md`. Exit 0 for COMPLETE, NOTHING_NEW or UNFINISHED.

- [ ] **Step 4: Read the report, do not only count it**

Report to the owner:
- the status, and every loud line;
- each source's status, listed and new counts;
- every verdict, with its reason;
- the extraction table: advisory id, status, proposals, resolver calls (resolved), record actors resolvable, cost;
- the reconciliation table: every session's `calls`, `unterminated`, `duplicated` and `from transcript`;
- the cost against the ceiling, and **each extraction's cost against its US$1.00 cap: the overshoot measurement**;
- whether any event carries `source: transcript`. That confirms, or not, that the SDK stream carries the CLI's own `tool_result`.

Name what is still open:
- this is one run;
- the resolution rate is per run.

- [ ] **Step 5: STOP: the owner decides the run's items**

Accept, drop or defer each item with `tools/accept_run.py <run_id>` (the interactive form), or leave the run pending.
- **Accept:** commit the listed files, then review the proposals with `tools/review.py`. That is definition-of-done item 7, and C2 Task 8 becomes a second acceptance.
- **Leave it pending:** C2's scheduled preflight will refuse on it until it is accepted, or expires 14 days after the run's date.

Claude renders the report and recommends; the owner decides.

---

## Definition of done for sub-project C1

Each item is traced to the spec (sections 1, 2 and 5, and section 6's definition of done).

- **Spec DoD 2, for `feeds_extract` (Task 2).** The tool enforces:
  - only after a relevant verdict;
  - one request per item and at most 3 per run;
  - the document chosen by rule;
  - writes only into the run's inbox.

  Guarded by `check_feeds_extract`.
- **Spec DoD 4, the code half (Tasks 3 and 4).** The orchestrator run reconciles every listed item and every tool call in code, and reports whatever was skipped as UNFINISHED. "`terminal_check` has run live at least three times" is measured by Task 9's run, where each session counts (one orchestrator plus up to three extractions), and C2's runs.
- **Spec DoD 5 (Task 5).** `accept_run` is the only way live results enter tracked data:
  - it validates everything and refuses the whole run on any failure;
  - it updates the ledger only on acceptance;
  - it refuses a failed reconciliation without a recorded override.
- **Spec DoD 7, the tooling (Tasks 5 and 9).** The first accepted run and its review are the owner's, in Task 9 or C2 Task 8.
- **Spec DoD 8 (Task 6).** The walkthrough still builds and is current after one planned republish.
- **Five new cold guards' worth of mutations, 34 in all:**
  - `check_document_pages` 4;
  - `check_feeds_extract` 6;
  - `check_feeds_orchestrator` 11, B's 6 among them;
  - `check_friday_run` 6;
  - `check_accept_run` 7.

  A's `check_feeds_server` (8) and `check_feeds_ledger` (8) still hold after the edits.
- **Not in C1:** the schedule, the auth preflight, the notification, back-pressure and the first launchd Friday. Those are C2.
