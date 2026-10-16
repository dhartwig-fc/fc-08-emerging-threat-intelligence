# Known-Typology Loop K3a (Flag Agent + FLAG Review) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For an approved governed advisory link, `agents/compare_flags.py ADV::TYP` compares the advisory's indicators with the typology's indicators and queues each genuinely new one as a flag proposal; the owner approves or rejects it in `tools/review.py` as a `FLAG` link, rebuilt into `data/approved_flag_links.json`.

**Architecture:** The agent mirrors `agents/draft_doctrine.py` (read-only Knowledge Centre tools, deny-all callback, structured output, code-enforced rules, refuse-if-exists). Its `new` verdicts are written as ordinary queue lines in `data/proposals/flags-<ADV>-<TYP>.jsonl` carrying an extra `flag` field, so the existing review gate groups them into links -- a fourth kind, `flag` -- and its existing "no reviewable link" refusal already guarantees a FLAG decision names a queued flag. `governance/decisions.py` stays the only writer and rebuilds a fourth approvals file.

**Tech Stack:** Python 3, `claude_agent_sdk`, pydantic; fc-08 guard scripts (`checks()` generators, `--mutate`), `tools/check_all.py`. Run as `.venv/bin/python`.

**Spec:** fc-10's `fc-10-intelligence-repository-layer/docs/superpowers/specs/2026-10-16-known-typology-k3-red-flags-design.md` (§1 K3-D1, §4, §5, §9 settled calls). This repository, branch `sdd/known-typology-k3a` from `origin/main` (`b6e7105`).

## Rulings this plan makes

- **K3a-R1 -- flags ride the queue.** A `new` verdict is a queue line (`data/proposals/flags-<ADV>-<TYP>.jsonl`) with the existing queue-line fields plus `flag`; the review gate groups it like any proposal. No second "is it queued" check is written: `decisions.apply` already refuses a key absent from the queue.
- **K3a-R2 -- the comparison list is `indicators` from `data/typologies.json`** (the library the Knowledge Centre server reads), matched verbatim as stored (spec §9: the import already normalised it).
- **K3a-R3 -- ids.** A flag proposal's `proposal_id` = the first 16 hex of sha256(`link_key + "\n" + normalised text`); the link key = `<ADV>::FLAG[<TYP>:<sha8>]`, `sha8` = the first 8 hex of sha256 of the normalised text (lower-cased, whitespace collapsed).
- **K3a-R4 -- the record** is read from `data/records/<ADV>.json` or `data/feeds/records/<ADV>.json` (exactly one must exist, as fc-10's `fc08_evidence` requires).

## Global Constraints

- The agent has NO write tool: `tools=[]`, `allowed_tools` = the three Knowledge Centre lookups, `can_use_tool` denies all.
- `matches` must name a typology indicator verbatim; `new` text is one line, ≤ 200 characters, no markdown (`**`, backtick, `|`, leading `#`), and cites ONE index into that indicator's own `citations`.
- Refused before any model call: the link is not in `data/approved_links.json`; the record is missing or has no indicators; the queue file or manifest already exists.
- A refused answer writes nothing.
- fc-08 rules: stage explicitly, never `git commit -a`; a new `evals/check_*.py` is registered in `tools/check_all.py` GUARDS (`cold`) and `evals/check_mutation_anchors.py` EXEMPT in the same commit; mutations rebind module-level names; a `--mutate` run passes when it prints `HELD: the probe detects the defect` (exit 0). No Co-Authored-By trailer. Owner pushes.
- No new dependency.

## Review Focus

1. **The model names an indicator that isn't the typology's** -- expected: whole answer refused, nothing written. Test: Task 1 check `"a match naming text the typology does not list is refused"`; mutation `match-any`.
2. **A `new` flag cites a quote the indicator doesn't carry** -- expected: refused. Test: Task 1 `"a citation index outside the indicator's citations is refused"`; mutation `cite-any`.
3. **Run twice for one link** -- expected: the second refused before any model call. Test: Task 2 `"a second run for the same link is refused"`; mutation `overwrite`.
4. **Run on a link the owner never approved** -- expected: refused. Test: Task 2 `"an unapproved link is refused before any session"`; mutation `unapproved`.
5. **A FLAG decision for a flag not in the queue** -- expected: refused, nothing written. Test: Task 3 `"a FLAG decision with no queued flag is refused"`.

---

### Task 1: the answer schema and the rules code enforces

**Files:**
- Create: `schemas/flag_comparison.py`, `evals/check_compare_flags.py` (pure checks only in this task)
- Modify: `tools/check_all.py` (GUARDS, beside `check_draft_doctrine`), `evals/check_mutation_anchors.py` (EXEMPT)

**Interfaces:**
- Produces in `schemas/flag_comparison.py`: pydantic `Verdict` (`indicator_index: int ≥0`, `verdict: Literal["matches","new"]`, `matched_indicator: Optional[str]`, `flag_text: Optional[str]` ≤200, `citation_index: Optional[int] ≥0`), `FlagComparison` (`link_key: str` pattern `^ADV-\d{4}-\d{4}::[A-Z]{2,6}\d{3}[A-Z]?$`, `verdicts: List[Verdict]` min 1); `normalise(text) -> str`; `flag_sha8(text) -> str`; `indicator_problems(answer, typology_indicators) -> list[str]` (a `matches` naming text not in the list); `citation_problems(answer, record) -> list[str]` (a `new` whose index is outside `record["indicators"][i]["citations"]`); `problems(answer, link_key, record, typology_indicators) -> list[str]` = link key mismatch + every indicator answered exactly once + `new` without text or index + text problems (reuse `schemas.doctrine_draft.text_problems` plus the 200 limit) + `indicator_problems` + `citation_problems`.
- `evals/check_compare_flags.py`: `MUTATIONS = ("match-any", "cite-any", "write-tool", "overwrite", "unapproved")`, `checks()` = `checks_pure()` + (Task 2) `checks_session()`; `main` as `check_draft_doctrine`'s.

- [ ] **Step 1: Guard first.** `checks_pure()` over a synthetic record (two indicators, the first with two citations) and indicators `["Front company with nominee directors", "Shared address with a designated party"]`, yielding:
  - `"an answer matching a listed indicator and proposing one cited flag passes"` -- `problems(...) == []`
  - `"a match naming text the typology does not list is refused"`
  - `"a citation index outside the indicator's citations is refused"` (index 5 on the first indicator)
  - `"an indicator left unanswered is refused"` and `"an indicator answered twice is refused"`
  - `"a flag of two lines, bold or a pipe is refused"` (three cases)
  - `"a flag over 200 characters is refused"`
  - `"the flag key ignores case and spacing"` -- `flag_sha8("Front  Company") == flag_sha8("front company")`, 8 hex
  Mutations in `main`: `match-any` rebinds `fc.indicator_problems = lambda *a: []`; `cite-any` rebinds `fc.citation_problems = lambda *a: []`. Register in `check_all.py` GUARDS: `("check_compare_flags", ["evals/check_compare_flags.py"], "cold"),` and in EXEMPT: `"check_compare_flags.py": "--mutate rebinds compare_flags and flag_comparison functions in memory",`.
- [ ] **Step 2: Run** `.venv/bin/python evals/check_compare_flags.py; echo rc=$?` → `ModuleNotFoundError: schemas.flag_comparison`, rc != 0.
- [ ] **Step 3: Implement** `schemas/flag_comparison.py` to the Interfaces.
- [ ] **Step 4: Run** → every pure check PASS, `HELD`, rc 0. `--mutate match-any` and `--mutate cite-any` → `HELD: the probe detects the defect`.
- [ ] **Step 5: Commit** (pre-commit runs every guard) `Stage566 K3a: the flag comparison schema and the rules code enforces`.

---

### Task 2: the agent

**Files:**
- Create: `agents/compare_flags.py`
- Modify: `evals/check_compare_flags.py` (`checks_session()`, three more mutations)

**Interfaces:**
- Consumes: Task 1 (`FlagComparison`, `problems`, `normalise`, `flag_sha8`).
- Produces: `COMPARE_TOOLS` (the three `mcp__<SERVER_KEY>__knowledge_centre_*` lookups, as `draft_doctrine.DRAFT_TOOLS`); `QUEUE_DIR = ROOT / "data" / "proposals"`; `_refuse_unapproved(link_key)`, `_refuse_existing(*paths)`; `load_record(advisory_id) -> (path, record)`; `load_indicators(typology_id) -> list[str]` from `agents.extract_advisory.LIBRARY_PATH`; `agent_options(model, max_budget_usd, max_turns)`; `async compare(link_key, model, max_budget_usd, max_turns, out_dir=None) -> Path` (the queue file); `main(argv)` with `--model claude-sonnet-5`, `--max-budget-usd 0.50`, `--max-turns 20`.
- Writes per `new` verdict ONE queue line: the existing queue-line keys exactly as the extractor writes them (copy one line of `data/proposals/*.jsonl` and keep every key; `typology_id` null, no emergent label, no typology proposal), `proposal_id` per K3a-R3, `advisory_id`, `citations: [<the cited {page, printed_folio, paragraph, quote}>]`, plus `flag: {"typology_id": TYP, "text": <flag_text>, "sha8": ...}`; and the manifest `flags-<ADV>-<TYP>.manifest.json` `{link_key, record, record_sha256, model, prompt_sha256, cost_usd, num_turns, verdicts: [...]}` (matches included). No `new` verdict → an empty queue file is NOT written; only the manifest.

- [ ] **Step 1: Guard first.** `checks_session()` runs `compare()` with a stub client (the `check_draft_doctrine.checks_session` pattern: patch the module's `ClaudeSDKClient` to a fake yielding a `ResultMessage` with a canned `structured_output`), into a temp `out_dir`, yielding:
  - `"an approved link with a valid answer writes one queue line per new flag and a manifest"` -- queue lines carry `flag.sha8`, `typology_id` null, the cited quote; the manifest lists every verdict
  - `"an unapproved link is refused before any session"` (the stub records that it was never entered)
  - `"a second run for the same link is refused"`
  - `"a refused answer writes nothing"` (canned answer with a bad citation)
  - `"the agent can call no write tool"` -- `COMPARE_TOOLS` holds exactly the three lookups and `agent_options(...).tools == []`
  Mutations: `write-tool` appends `knowledge_centre_propose_link` to `cf.COMPARE_TOOLS`; `overwrite` rebinds `cf._refuse_existing = lambda *p: None`; `unapproved` rebinds `cf._refuse_unapproved = lambda k: None`.
- [ ] **Step 2: Run** → `ModuleNotFoundError: agents.compare_flags`.
- [ ] **Step 3: Implement** `agents/compare_flags.py`. The system prompt: compare each advisory indicator with the typology's indicators; `matches` names one verbatim; `new` states the flag in one plain line and cites one citation index of that indicator; a person decides.
- [ ] **Step 4: Run** → every check PASS; each of the five mutations → `HELD: the probe detects the defect`.
- [ ] **Step 5: Commit** `Stage566 K3a: the flag agent -- read-only, every new flag cites the advisory's own quote`.

---

### Task 3: the FLAG link kind in the review gate

**Files:**
- Modify: `governance/proposals.py` (`Proposal`/`Link` gain `flag: Optional[dict]`; `kind` returns `"flag"` first when set; `flag_key(advisory_id, typology_id, sha8) -> str`; `Proposal.link_key` uses it for a flag), `tools/review.py` (LINE accepts `FLAG[<TYP>:<sha8>]`; `--approved-flags`; `_finish` passes it), `governance/decisions.py` (`APPROVED_FLAGS = ROOT / "data" / "approved_flag_links.json"`; `rebuild` returns four texts; `write_approved` / `check_approved` take `flags_path`; `_rows` for `"flag"` emits `{link_key, advisory_id, typology_id, flag_text, quote, page, decided_at, note}`), `evals/check_review_gate.py` (`names` tuple, paths, the real-files snapshot, new checks), `evals/check_compare_flags.py` (one check), `data/approved_flag_links.json` (generated, `"approved": []`)

**Interfaces:**
- Consumes: Task 2's queue lines.
- Produces: `gp.flag_key(...)`, `gd.APPROVED_FLAGS`, `gd.write_approved(decisions, links_path, emergent_path, proposals_path, flags_path)`, `gd.check_approved(..., flags_path)`.

- [ ] **Step 1: Guard first.** In `evals/check_review_gate.py`:
  - `"a FLAG decision rebuilds into approved_flag_links.json with its text and quote"` -- a temp queue with one flag line, decision `ADV-2026-0028 FLAG[SAN004:<sha8>]: approve -- new and specific` → the file holds that row
  - `"a FLAG decision with no queued flag is refused"` -- an unknown sha8 → `GateRefusal`, no file changed
  - `"the decision line reads a FLAG key in any case"` -- `parse_decisions("adv-2026-0028 flag[san004:ABCD1234]: approve")` gives `ADV-2026-0028::FLAG[SAN004:abcd1234]`
  and `names` gains `gd.APPROVED_FLAGS.name`. In `evals/check_compare_flags.py`: `"the queued line groups into a flag link"` -- `governance.proposals.group` over a session's queue line yields one link of kind `flag` keyed `ADV::FLAG[TYP:sha8]`.
- [ ] **Step 2: Run** → fails (no `APPROVED_FLAGS`, no `flag` kind).
- [ ] **Step 3: Implement** per Files/Interfaces; regenerate the approvals files through `tools/review.py`'s rebuild so `data/approved_flag_links.json` exists with `"approved": []`.
- [ ] **Step 4: Run** `.venv/bin/python evals/check_review_gate.py; .venv/bin/python evals/check_compare_flags.py; .venv/bin/python tools/check_all.py` → all HELD / PASS; each existing `check_review_gate --mutate` still `HELD: the probe detects the defect`.
- [ ] **Step 5: Commit** `Stage566 K3a: the FLAG link kind -- reviewed in review.py, rebuilt into approved_flag_links.json`.

---

### Task 4: docs, CI, land

- [ ] **Step 1:** fc-08 `CLAUDE.md`: a short K3a entry -- the command, the queue file, the FLAG decision line, that a match is a note and only `new` flags are reviewed, and that fc-10 absorbs `approved_flag_links.json` from K3b. Commit.
- [ ] **Step 2:** The owner pushes `sdd/known-typology-k3a`; fc-08 CI must conclude `success`; then `git merge-base --is-ancestor origin/main <head>` and `git push origin <head>:main`. If main moved, merge it, re-run `tools/check_all.py`, return to the push.
- [ ] **Step 3:** Memory `stage566-known-typology-loop.md`: K3a landed; next K3b (fc-10 absorbs flags) and the owner's first real flag run.
