# Slice 2 · Sub-project D: Operation and Release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close slice 2. Run two more live Fridays, measure them, audit the definition of done, and tag `fc08-threatintel-slice2-v1.0.0`.

**Architecture:** D builds no new pipeline. It adds one read-only measurement tool, a release audit document and a tag. Everything else is operating the Friday run that already exists.

**Tech Stack:** Python stdlib. Checks follow the repo's `evals/check_*.py` pattern, wired into `check_all`.

**Spec:** `docs/superpowers/specs/2026-09-26-slice2-live-intelligence-design.md`, §6 (D) and the Definition of done (items 1–8).

## Global Constraints
- Owner gates:
  - any portfolio update happens only on the owner's go (spec §6);
  - pushing the tag is the owner's step;
  - moving `~/fc-08-schedule` is the owner's step.
- Commit from the full clone `~/fc-08-emerging-threat-intelligence`. Stage files explicitly; never `git commit -a`; never commit from a linked worktree. The hook guards make nested commits.
- No run may exceed the US$5 ceiling.
- No live run's output enters tracked data except through `tools/accept_run.py`.
- fc-10's telemetry page reads `data/advisories/adv-<yyyy>-<nnnn>-*.html` and their `<title>`. Do not rename that directory or that filename pattern, and keep the `<title>` element. A break there fails quietly on the public page.

## Audit (2026-10-21) — where the definition of done stands

All checks run against origin/main `80ecaec`, plus the live schedule clone's inbox.

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Adapters, cold snapshot guards, loud "layout changed" | MET | `feeds/sources.py`; `tests/fixtures/feeds/*`; `feeds/report.py:142`; `evals/check_feeds_server.py`, `evals/check_friday_run.py:816` |
| 2 | `feeds` MCP server and its invariants | MET | Exercised by `evals/check_feeds_server.py` (newness, allowlist, inbox-only, extraction after a verdict) |
| 3 | Triage eval band over 3 repeats, owner decisions | MET | `evals/feeds/score.json`: recall 0.926–0.963 (mean 0.951), precision 0.962–1.0, 60 items, 9 owner-decided. Caveat: OFAC has n=3 relevant items, so its per-source recall (0.667) is not a stable band |
| 4 | Reconciles every item and tool call; terminal check live ≥ 3 | MET | The reconciliation is clean on the 10-02, 10-11 and 10-16 live runs |
| 5 | `accept_run` is the only write path; ledger written on acceptance only | MET (code and check) | `tools/accept_run.py`, `evals/check_accept_run.py`. Acceptances: 10-11 (ADV-2026-0026) and 10-16 (ADV-2026-0027 to 0029) |
| 6 | launchd weekly on Fridays, preflight, notification, back-pressure, ≤ US$5 | NEEDS-FRIDAY | `uk.fc08.friday-run` is loaded; max spend so far is US$1.96; the refusal path has been shown. The "weekly" claim needs scheduled Friday runs, and the runs so far include manual Wed/Sun ones |
| 7 | ≥ 1 accepted live run reviewed through `tools/review.py` | MET | 10-11 and 10-16, with review rows in `data/review_decisions.jsonl` |
| 8 | Walkthrough builds and is current; resolver sentence computed | AT RELEASE | `tools/build_walkthrough.py` (`_resolver_runs`, `--repin`), `evals/check_walkthrough.py`. Rebuild at release |

**Measured so far** (4 completed runs: 09-30, 10-02, 10-11, 10-16):
- Cost per run: 1.015 / 1.955 / 0.422 / 1.648 US$ (mean 1.26).
- Live resolution rate: 4 of 122 resolver calls, 3.3%.
- Items per source: ofsi 8, fincen 0, ofac 19.
- Live triage kept: 10 of 26.

## Review Focus
1. **Resolution rate is the weakest number (3.3%).** The note must report it plainly, not average it away. It is the clearest slice-3 lead.
2. **FinCEN produced 0 new items** across all runs. Confirm this is quiet publishing and not a silent adapter failure: its listing is fetched and parsed, and a layout change would say so.
3. **UNFINISHED on accepted runs.** Both accepted runs read UNFINISHED because one item has no verdict. The release audit must state what UNFINISHED means and why it is acceptable, or name it as a defect.
4. **Only scheduled Fridays count toward item 6's "weekly" claim**, not manual reruns.
5. **OFAC per-source recall rests on n=3.** Say so wherever the band is quoted.

---

### Task 1: Owner readiness before Friday 23 Oct (09:00)

- [ ] **Step 1:** Decide whether `~/fc-08-schedule` moves to origin/main before Friday. It is at `85846ec`, 6 commits behind, so it lacks the Stage566 K3a–K3c flag-agent work and the scan-demo fix. The owner's move, as before:
  - `git -C ~/fc-08-schedule fetch origin`
  - `git -C ~/fc-08-schedule checkout --detach origin/main`
  - then a `launchctl start uk.fc08.friday-run` smoke test the owner watches.
- [ ] **Step 2:** If it moves, run `evals/check_all` from that clone once (cold) and record the result in the run log.

### Task 2: The measurement tool

**Files:**
- Create: `tools/measure_slice2.py`
- Create: `evals/check_measure_slice2.py` (wire it into `check_all`)
- Fixtures: `tests/fixtures/measure/` holds 3 synthetic run directories (a completed live run, a refused run and a manual run).

**Interfaces:**
- Produces: `measure(inbox: Path, *, live_only: bool = True) -> dict` with:
  - `runs: [{run_id, date, weekday, scheduled, status, spent_usd, items_new: {source: int}, triage_kept, triage_total, resolver_calls, resolved}]`
  - `totals: {runs, cost_mean_usd, cost_max_usd, resolution_rate, items_by_source, triage_kept_ratio}`
  - `band: {recall_min, recall_mean, recall_max, precision_min, precision_mean, precision_max}`, read from `evals/feeds/score.json`
- CLI: `python3 -m tools.measure_slice2 --inbox <path> [--markdown]` prints the measurement note's tables.
- Definitions, verbatim in the docstring:
  - cost per run = `run.json.spent_usd`;
  - live resolution rate = resolved ÷ resolver calls, both summed across live runs;
  - items per source = new items per source;
  - the triage band is the committed back-catalogue band. Live kept/total is reported as observed, never as a band, because live items have no ground truth.
- Exclusions: REFUSED runs, runs with `spent_usd == 0`, and rehearsal checkouts. Manual runs are kept but flagged `scheduled: false`.

- [ ] **Step 1: Write the failing checks** in `evals/check_measure_slice2.py`:
  - the fixture totals are exact;
  - a refused run is excluded;
  - a manual run is flagged and kept;
  - the band is read from `score.json` and not recomputed;
  - non-vacuity: at least 2 runs are measured.
- [ ] **Step 2:** Run `python3 evals/check_measure_slice2.py`. Expected: FAIL (the module doesn't exist yet).
- [ ] **Step 3:** Implement `tools/measure_slice2.py`. Read-only; stdlib; it never writes to the inbox.
- [ ] **Step 4:** Run the check again. Expected: PASS. Then mutate twice (drop the refused-run exclusion; sum the rates instead of the counts) and confirm each turns the check red.
- [ ] **Step 5:** Run it once, read-only, against `~/fc-08-schedule/inbox`. The figures must match the audit above: mean 1.26, 4 of 122, ofsi 8 / fincen 0 / ofac 19.
- [ ] **Step 6:** Commit "Slice 2 D: read-only measurement of the live Fridays".

### Task 3: Friday 23 Oct, operate and measure

- [ ] **Step 1:** The scheduled run fires at 09:00. Read its report; accept with `tools/accept_run.py`; review with `tools/review.py`, as on 10-16.
- [ ] **Step 2:** Run `measure_slice2 --markdown` and paste the output into the draft `docs/MEASURE_SLICE2.md` (Task 5), dated.
- [ ] **Step 3:** Check the FinCEN listing was fetched and parsed (Review Focus 2). Record the answer.

### Task 4: Friday 30 Oct, operate and measure

- [ ] **Step 1:** As Task 3, for 30 Oct.

### Task 5: Measurement note and release audit (after 30 Oct)

**Files:**
- Create: `docs/MEASURE_SLICE2.md`, holding the four measures with their definitions, per-run tables and Review Focus 1–5 answered.
- Create: `docs/RELEASE_SLICE2.md`, following `docs/RELEASE_SLICE1.md`. It contains:
  - the DoD table (items 1–8, re-checked on the release commit);
  - "What the release does not claim": live triage has no ground truth; the OFAC band rests on n=3; the resolution rate;
  - "Parked and known, carried into slice 3": the spec's out-of-scope list, plus anything Tasks 3–4 found.

- [ ] **Step 1:** Rebuild the walkthrough: `tools/build_walkthrough.py --repin`. Confirm `evals/check_walkthrough.py` passes and that the resolver sentence is computed from the committed queues (item 8).
- [ ] **Step 2:** Run `evals/check_all` cold from a fresh clone of the release commit.
- [ ] **Step 3:** Write both documents. Commit "Slice 2 D: measurement note and release audit".
- [ ] **Step 4:** The owner lands it on main; the owner tags `fc08-threatintel-slice2-v1.0.0` on that commit and pushes the tag.
- [ ] **Step 5:** Write a journal entry in `fc_vision_notes`, after the tag.
- [ ] **Step 6:** Portfolio: only on the owner's explicit go.
