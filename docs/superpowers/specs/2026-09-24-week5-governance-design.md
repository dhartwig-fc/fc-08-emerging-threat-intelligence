# Week 5 design: governance, provenance and digest routing

Date: 2026-09-24. Status: approved section by section in chat; awaiting owner
review of this written form before a plan is written.

PLAN.md's week 5 asks for four things: a telemetry hook, a `review.py` gate over
`data/proposals.jsonl`, deterministic desk digests, and a `can_use_tool` write
allowlist. Its deliverable: *provenance on every fact, a human gate before every
write, telemetry for every decision and desk-routed digests.*

This design was written after measuring the repository, and the measurements
changed three of the four items. They are recorded first because they are the
reason the design differs from the plan.

## What was measured, 2026-09-24

| Item | Measured | Consequence |
|---|---|---|
| Review queue | 383 proposals, 0 reviewed, 219 distinct links, one proposed 11 times, from every run including test repeats and both A/B arms. **No proposal carries a citation or names its run.** `data/proposals.jsonl` is gitignored, so all 383 exist on one machine. | The plan's gate "shows the rationale and citations"; there are no citations to show. The proposal contract is fixed before a gate is built. |
| Telemetry | No hooks anywhere. The portfolio's telemetry events are `{stage, status, timestamp, message, payload}`. | The plan's fields (agent, tool, latency, outcome) go in `payload`. |
| Desks | `suggested_desks` is the agent's own call and is broad: sanctions on 17 of 20 advisories, correspondent on 15. | Routing on suggestions sends nearly everything everywhere. Family-backed routing is the rule. |
| Write permission | The agent has no built-in tools (`tools=[]`). All four Knowledge Centre tools are in `allowed_tools`, which pre-approves them. | A `can_use_tool` callback would never be consulted. As specified, item 4 would pass while checking nothing. |

## Decisions taken in the design conversation

1. The 383 existing proposals are frozen as history and not reviewed. The gate reviews only proposals made under the new contract.
2. `review.py` is the only writer of approvals. It accepts decisions interactively or from a pasted list; both go through one function.
3. A quote is checked when the agent proposes (`propose_link` refuses) and again when the gate loads it.
4. Approved emergent proposals go to their own file, never into the links file.
5. One decision per link, not per proposal; a decided link returns only with new evidence.
6. Decisions are an append-only log; the approvals files are rebuilt from it (option 1 of 3; per-row status and SQLite rejected).
7. `network` typologies route to FIU liaison.

## Build order

Three sub-projects, each with its own plan, in this order:

- **A. Proposal contract and review gate** (Sections 1 and 2). The week's deliverable is "a human gate before every write", and today's queue cannot be reviewed.
- **B. Telemetry and the write allowlist** (Section 3). Both change `agent_options`, so they are one change.
- **C. Desk digests** (Section 4). Reads what A and B produce.

---

## Section 1: the proposal contract

### Run identity comes from the run, not the agent

`mcp_servers()` passes the server six more environment values:

| Variable | Value |
|---|---|
| `NEXUS_RUN_ID` | a fresh id per run |
| `NEXUS_STAGE` | `extractor` or `reviewer` |
| `NEXUS_ADVISORY_ID` | the advisory this run is extracting |
| `NEXUS_PDF_PATH`, `NEXUS_PDF_SHA256` | the source document and its hash |
| `NEXUS_PROPOSALS_PATH` | data/proposals/<run_id>.jsonl |

The agent cannot set these. `propose_link` still takes `advisory_id` from the
agent and **refuses a mismatch** with `NEXUS_ADVISORY_ID`: today nothing stops a
run on one advisory proposing links for another. The additive reviewer
(`agents/review_advisory.py`) inherits `agent_options`, so it gets the same
server with `NEXUS_STAGE=reviewer`.

### Citations are required and verified

`ProposeLinkInput` gains `citations: list[{page, quote}]`, at least one.

The server loads the PDF once per process, refusing if its sha256 differs from
`NEXUS_PDF_SHA256`, and refuses any quote that is not on the page it names. The
match is the existing one: exact after normalisation, or exact with whitespace
removed (pypdf splits words on born-digital FATF PDFs). Never fuzzy on meaning.
The refusal names the page and asks the agent to re-quote, so the agent can
correct and resubmit.

### Shared matching code

The normalise-and-match logic moves out of `evals/check_citations.py` into one
module, `schemas/citation_match.py`, imported by the server, `review.py` and
`check_citations.py`. One rule, three callers.

### The proposal line

```
{schema: "proposal/2", proposal_id, proposed_at, run_id, stage, advisory_id,
 document_sha256, typology_id | emergent_label, rationale, confidence,
 citations: [{page, quote}]}
```

- `proposal_id` is the sha256 of the line's canonical content minus
  `proposal_id` and `proposed_at`, so an identical proposal repeated has the same id.
- `status` is removed. Proposals are immutable once written; decisions live in
  the decision log.

### The legacy queue

Copied byte-identical to a tracked `data/proposals_legacy_2026-09-10_to_13.jsonl`
before anything else changes. `data/proposals.jsonl` is never written again and
never truncated.

**Amended while planning, 2026-09-24: one queue file per run.** The server
writes to `data/proposals/<run_id>.jsonl` (the runner sets
`NEXUS_PROPOSALS_PATH`), and those files are TRACKED. A single shared
`data/proposals.jsonl` is gitignored, so every `proposal/2` line a decision cites
would have existed on one machine -- the trap `data/records/` was in until
`e0dbfb6`. Per-run files are also never appended to by two processes at once,
and pair with the per-run telemetry file in Section 3. `review.py` reads
`data/proposals/*.jsonl` and reports any line that is not `proposal/2`.

### Guard

`evals/check_proposal_contract.py`, mutation-verified. Each refusal is exercised
by breaking the rule it guards: missing citation, quote on the wrong page,
invented quote, advisory mismatch, PDF hash mismatch. The guard also asserts that
a correct proposal is ACCEPTED, so it cannot pass by refusing everything.

---

## Section 2: `review.py`, the gate

### Grouping

A **link** is `(advisory_id, typology_id)` or `(advisory_id, EMERGENT:label)`.
Each link collects every `proposal/2` line behind it.

### Re-check before display

Each proposal is re-verified when loaded: every quote against its PDF page, the
document hash against `evals/golden/advisory_list.json`, the typology id against
the library. A failing proposal is **quarantined**: listed with the reason, never
approvable. A link with no clean proposal is not presented.

### The card

Advisory title; typology label, family and doctrine summary; every distinct quote
with its page (duplicates across runs collapsed with a count); each rationale;
which runs and stages proposed it; and a flag saying whether the golden label
holds or lacks the link. The flag is context, never a rule.

### Two input modes, one writer

- `review.py`: interactive. approve / reject / skip / quit, optional note.
- `review.py --decisions <file>`: a pasted list, one line per link, e.g.
  `ADV-2026-0002 BA008: approve -- note`. A page may produce this list later; no
  page is built in week 5.

Both call one function, which refuses: an unknown link, a quarantined link, a
link decided twice in one list, and overturning a decided link ("a change of
mind needs its own dated record").

### The decision log

`data/review_decisions.jsonl`, tracked, append-only:

```
{decided_at, link_key, kind: governed|emergent, advisory_id, typology_id,
 emergent_label, decision: approve|reject, note, proposal_ids[], run_ids[],
 quotes_seen_sha256[]}
```

`advisory_id`, `typology_id` and `emergent_label` were added while planning, so the approvals files are rebuilt from the log without parsing link keys.

### Later proposals for a decided link

Recorded against the decision and not shown again, **unless** a proposal carries
a quote whose hash is not in `quotes_seen_sha256`. Then the link returns marked
**new evidence**, with the earlier decision shown. Deciding it appends a new
dated line; the old line is never edited.

### Derived files

Every `review.py` run ends by rebuilding, deterministically from the log:

- `data/approved_links.json`: approved governed links
- `data/approved_emergent.json`: approved emergent candidates

`review.py --check` rebuilds in memory and fails if the committed files differ.
The guard also asserts no other file in the repository writes either path.

---

## Section 3: telemetry and the write allowlist

### Telemetry

- A `PreToolUse` hook records the start time per `tool_use_id`. `PostToolUse` and
  `PostToolUseFailure` hooks write one event per call:

  ```
  {stage: "FC08_TOOL_CALL", status, timestamp, message,
   payload: {run_id, agent: extractor|reviewer, advisory_id, tool,
             latency_ms, outcome}}
  ```

- `status` is `SUCCESS`, `FAILURE` (the tool raised) or `REFUSED` (the tool ran
  and returned a governed refusal, such as the twin rule or the citation check).
  A refusal is the governance working and must not read as a success.
- `RUN_STARTED` and `RUN_COMPLETED` events per run, the latter carrying cost,
  turns and whether the structured output validated.
- Every `can_use_tool` decision is an event (`PERMISSION_ALLOWED` /
  `PERMISSION_DENIED`).
- Written to `data/telemetry/<run_id>.jsonl`, **tracked**, so every run a
  proposal names is traceable from a clone.
- Hooks are supplied in code; `setting_sources=[]` still excludes the machine's.

### The write allowlist

- `knowledge_centre_propose_link` leaves `allowed_tools`. The three read-only
  tools stay pre-approved.
- `can_use_tool` decides every other tool. It **allows** a tool on
  `WRITE_ALLOWLIST` (`propose_link` only) and only when the Section 1 run identity
  is present; it **denies** everything else with a reason.
- **Proven by trying.** `evals/check_tool_surface.py --live` gains a probe: a
  test-only MCP server offers `knowledge_centre_write_typology`, and the prompt
  instructs the agent to call it. Pass requires the call denied, a
  `PERMISSION_DENIED` event written, and the tool's body never run (it drops a
  marker file if executed). Mutation: a callback that allows everything must fail
  the probe.

### Risk, probed first

The Python SDK may accept `can_use_tool`, and possibly hooks, only with a
streamed prompt; `extract()` passes a plain string. Sub-project B's first task is
a minimal probe that settles this. If streaming is required, the prompt is sent
as a one-message stream, and the week 2-4 guards are re-run to show nothing else
moved.

---

## Section 4: desk digests

### Routing table

`data/desk_routing.json`, data rather than code:

| Family | Desk |
|---|---|
| `tbml` | `trade_desk` |
| `sanctions` | `sanctions_desk` |
| `correspondent_banking` | `correspondent_desk` |
| `capital_markets` | `markets_desk` |
| `network` | `fiu_liaison` |

### Rule

An advisory reaches:

- a **family desk** only when it carries at least one governed typology of that
  family. A suggestion alone is not enough (measured: sanctions suggested on 17,
  backed on 11).
- **fraud_desk, fiu_liaison, general_intel** when `suggested_desks` names them,
  since no family points at fraud or general intel and the suggestion is the only
  evidence. The digest states this on the page. (fiu_liaison is reachable both
  ways.)

### Content

One Markdown file per desk per batch: `data/digests/<batch_id>/<desk>.md`.

The source is the batch's records (`data/records_merged/` for slice 1), not the
proposal queue: a record's typologies are what the pipeline asserted. Each
typology is looked up in the decision log by its link key:

- **approved**: listed under the advisory with its strongest quote and page;
- **no decision yet**: listed in a separate **awaiting review** section;
- **rejected**: omitted.

Per advisory the digest also states why it was routed (which typology, or
"suggested by the agent"). Approved emergent candidates appear under their own
heading. Records made before `proposal/2` have no decisions, so their links all
read as awaiting review, which is true.

Deterministic: sorted, no timestamps beyond `batch_id`, byte-identical on
re-run.

### Guard

`evals/check_digest_routing.py`, mutation-verified: a sanctions typology routes
to the sanctions desk and a sanctions suggestion alone does not; every desk in the
`Desk` enum is reachable; every family in `data/typologies.json` appears in the
routing table, so a new family cannot route nowhere; a re-run is byte-identical.

---

## Acceptance for week 5

- Every `proposal/2` proposal carries a run id and at least one verified quote.
- `review.py` is the only writer of `approved_links.json` and
  `approved_emergent.json`, and `--check` proves the files match the log.
- A telemetry event exists for every tool call and every permission decision in
  a live run, and a refusal is recorded as `REFUSED`.
- A write tool not on the allowlist is denied in a live probe, and the probe
  fails when the callback is mutated to allow.
- Digests generated for at least three desks (PLAN.md's definition of done).

## Out of scope

- A review page. `--decisions` makes one possible; building it is not week 5.
- Reviewing the 383 legacy proposals.
- Anything consuming `approved_links.json` inside fc-10. The file is the
  governed hand-off; fc-10 reading it is slice 2.
- Re-running the full 20-advisory batch. Sub-projects are verified on targeted
  runs; a full batch under the new contract is a separate decision (quota).
