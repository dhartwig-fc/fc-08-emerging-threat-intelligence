# CLAUDE.md · fc-08-emerging-threat-intelligence

Project memory for Claude Code. Read `PLAN.md` for the full six-week plan.

## What this repo is now

Home of NEXUS Track 2 · Threat Intelligence · Slice 1 ("intel extraction"). An agentic pipeline that ingests regulator and industry advisories, extracts a governed `AdvisoryRecord`, resolves it against the Knowledge Centre through MCP tools, flags emergent typologies and routes desk digests, with every fact cited to page and paragraph.

The pre-existing folders (`analytics-opportunities/`, `intelligence/`, `roadmap/`, `threats/`) are the domain content this slice feeds. Do not restructure them.

## Stack and versions (verified 10 Sep 2026)

- Python 3.14 in `.venv` (activate with `. .venv/bin/activate`)
- `claude-agent-sdk` 0.2.x, `mcp` 2.2.x (**MCPServer**, not FastMCP; client results are snake_case: `init.server_info`, `init.protocol_version`, annotations `read_only_hint`), `pydantic` 2.13, `pypdf` 6
- The Agent SDK drives the `claude` CLI, whose login is SEPARATE from the desktop app. Check `claude auth status` first. fatf-gafi.org blocks curl; fetch advisories through a real browser
- **Auth: use `claude setup-token`, not an API key** (corrected 2026-09-12). Week 1 hit an expired OAuth session and put `ANTHROPIC_API_KEY` in `~/.bash_profile`; that routed every SDK run at pay-as-you-go credits, and on 2026-09-12 five runs died on "Credit balance is too low". `claude setup-token` issues a long-lived token against the Claude subscription, which is what a headless pipeline wants. **`ANTHROPIC_API_KEY` takes PRECEDENCE over the stored session**, so while it is exported, `claude auth status` reports `authMethod: api_key` and the token is ignored — read `authMethod`, not `loggedIn`. Batch scripts must `unset ANTHROPIC_API_KEY`. `/login` is a slash command inside a session; the shell-level command is `claude auth login`
- macOS, Bash 3.2. No `declare -A`, no `mapfile`. Full-file replacements only, never partial snippets or edit-in-place instructions

## Layout

```
PLAN.md                            six-week plan and definition of done
schemas/advisory.py                AdvisoryRecord contract (schema 1.2.0; read SCHEMA_VERSION, not this line) — the treaty
mcp_server/knowledge_centre_server.py   Knowledge Centre as MCP tools (read-only + propose)
agents/extract_advisory.py         single-advisory extraction agent, grounded on the MCP server since week 2
evals/golden/                      week-3 golden set: advisory_list.json (20, hashed) + hand labels as they are written
evals/search_probes.py             12 phrases the search tool must resolve; run after any library or scorer change
tools/fetch_fatf_via_chrome.js     fetches fatf-gafi.org PDFs, which refuse every non-browser client
data/typologies.json               GOVERNED export of fc-10's doctrine library (57 typologies); never hand-edit
tools/import_fc10_doctrine.py      regenerates it from fc-10's indexes/doctrine_library.json; deterministic, provenance = fc-10 commit + sha256
data/advisories/                   source PDFs (gitignored)
data/records/                      validated AdvisoryRecord JSON (gitignored)
data/proposals.jsonl               review queue written by the MCP server (gitignored)
evals/example_record.json          golden record proving the schema
evals/validate_record.py           validator for any record
evals/check_citations.py           proves every citation quote exists on the PDF page it names
evals/score.py                     scores predicted records against the golden set (P/R/F1 per field)
evals/check_tool_surface.py        proves the agent cannot reach Bash/Write/Read; run with --live --mutate
evals/search_aliases_probe.py       guards SEARCH_ALIASES: direction pair fixed, emergent guard intact; --mutate
evals/search_recall.py              search measured against the golden set's real advisory sentences, not hand-written probes
evals/probe_prompt_variant.py       A/B a prompt change without editing the agent; INVERTED 2026-09-12, now builds the pre-adoption prompt
evals/traces/                       where recall goes: the full baseline, three traced mechanisms, and the ADV-2026-0004 label triage
tools/batch_remaining.sh           extracts every advisory with no record; resumable and idempotent, shortest first
evals/review_ADV-2026-0001.md      week-1 review: what the first real run got wrong and why
setup.sh                           bootstrap + smoke tests
```

## Non-negotiable rules

1. `schemas/advisory.py` is the contract. Change it deliberately, bump `SCHEMA_VERSION`, update `evals/example_record.json` in the same commit.
2. Governance lives in tools and schemas, not prompts. The agent must never name a `typology_id` that a `knowledge_centre_*` tool did not return. **And the agent has NO built-in tools** — `tools=[]` in `agent_options`, which emits `--tools ""`. `allowed_tools` is not this: it gates whether a call PROMPTS, not whether the tool exists, and until 2026-09-12 the agent held Bash and Write and ran a shell command mid-extraction. What refused the file write was a hook on one operator's machine, which is not this pipeline's governance. Guarded by `evals/check_tool_surface.py`, mutation-verified both directions.
3. No citation, no fact. Every typology, actor and indicator carries at least one `Citation` with page and verbatim quote.
4. Nothing writes to the Knowledge Centre. `knowledge_centre_propose_link` appends to a review queue; a human approves.
5. Evaluate before improving. Build the golden set before touching prompt wording.
6. Keep single-file deliverables copy-and-paste ready. Reliability over cleverness.

## Commands

```bash
. .venv/bin/activate
python evals/validate_record.py evals/example_record.json
python agents/extract_advisory.py data/advisories/<file>.pdf --advisory-id ADV-2026-0001
python evals/validate_record.py data/records/ADV-2026-0001.json
claude mcp add knowledge-centre -- "$PWD/.venv/bin/python" "$PWD/mcp_server/knowledge_centre_server.py"
```

## Status

- [x] Week 0: repo scaffolded, schema validates, MCP server imports on mcp 2.2.0
- [x] Week 1 (2026-09-10): FATF TBML 2020 extracted twice; schema argued with and bumped to 1.1.0 (PDF page index + printed_folio, published_on_precision, ActorType.CATEGORY). Review and numbers in `evals/review_ADV-2026-0001.md`; citation checker in `evals/check_citations.py`. Committed as 6841abd.
- [~] Week 2 (started 2026-09-10): MCP server registered (`claude mcp get knowledge-centre` shows Connected) and driven over stdio by a client; fixture replaced by the governed fc-10 export (schema 1.2.0 widens typology_id to allow TBML002U). Agent wired via `mcp_servers` with `strict_mcp_config=True` (the folder's `claude mcp add` registration otherwise loads too and causes permission denials); library removed from the prompt; `_refuse_unknown_ids` guards in code. Tool-grounded run: 7 library ids + 5 emergent, 12 proposals, $1.14, 49 turns. Citation page/folio SWAPPED in 15 of 21 under tool load: prompt advice does not hold; structural fix deferred to the golden set. Week 2 DONE, committed as 98a7d6e + 971aa34. Search tool rewritten (stemmed IDF + label bonus + floor 0.25); `evals/search_probes.py` went 8-of-12 missing to 12-of-12, mutation-verified. Run it after ANY change to the library or the scorer. ALSO run `evals/search_recall.py`, which measures the tool against the golden set's 413 real advisory citations -- the 12 hand-written probes are short phrases and hid a length bug for a day. Search rewritten again 2026-09-11: the score is now length-invariant (max of query-normalised and label-normalised, label needing 2 terms), top-5 recall 0.351 -> 0.496 with the emergent guard still 12/12.
- [x] Week 3 (2026-09-10 to 09-12): twenty advisories selected from Source Matrix tiers 1-2, every URL verified, all downloaded to `data/advisories/` (gitignored, 920 pages, all born-digital), listed with hashes in `evals/golden/advisory_list.json`. All 20 labelled 2026-09-11 (3 in-session, 17 by subagents), every one validating and every citation on its page; ALL are drafts pending owner review. Schema 1.3.0 raised the extraction_notes cap to 4000 because reviewer notes on long reports hit the old 1000. Read `evals/golden/README.md` "State of the set" before scoring: emergent labels are NOT normalised (the same technique is named three ways), so an exact-string scorer will understate emergent recall. `evals/score.py` written and mutation-verified: governed ids exact, emergent by token containment >= 0.60 (owner decision; 1.00 would score paraphrases 0.000). **That threshold is now measured and should move to 0.50** -- the "0.50 collapses 2Rivers DMCC into 2Rivers PTE" justification was a SYNTHETIC example, and on the real 20-advisory data 0.50 causes zero entity merges, verified pair by pair. 0.40 does cause a real merge. See `evals/traces/EMERGENT_AUDIT_2026-09-12.md`, actors alias-aware, zero-against-zero reports n/a not 1.000. Self-score of the golden set is 1.000 on all four fields. FULL-SET BASELINE RAN 2026-09-12 (see below). Extraction is FREE on the subscription token (`claude setup-token`), so the remaining work is time, not money -- the "~$23" framing is void. NOT YET: resolve_actor tool, and the owner review of the labels, which is the one thing here code cannot do. fatf-gafi.org needs a real browser: `tools/fetch_fatf_via_chrome.js` (cached playwright module + installed Chrome, stealth headless) works; the Playwright MCP servers drop on downloads. **SETTLED 2026-09-12 with eight runs of the five advisories: the search fix changed NOTHING measurable, and the claim that the tool was half the recall gap is FALSIFIED.** Four pre-fix runs (the original baseline + 3 repeats in a worktree at `6d19027^`, validated at top-5 recall 0.351) against four post-fix runs (the rerun + 3 repeats, 0.496). Every field's band OVERLAPS:

  | F1 | pre-fix min-max (mean) | post-fix min-max (mean) |
  |---|---|---|
  | typologies | 0.538-0.610 (0.576) | 0.538-0.578 (0.560) |
  | emergent | 0.385-0.600 (0.438) | 0.385-0.571 (0.478) |
  | actors | 0.738-0.814 (0.777) | 0.764-0.810 (0.785) |
  | jurisdictions | 0.900-0.908 (0.905) | 0.906-0.923 (0.914) |

  Typology recall: 0.418 mean pre, 0.409 post. **The first baseline's 0.610 was the TOP of its band**, so the -0.031 "decline" seen on 2026-09-12 was one band's maximum against another's middle -- never a signal.

  **Why the ceiling lift did not translate, and what it means for week 4.** `search_recall.py` queries the tool with the GOLDEN LABEL'S OWN QUOTE; the agent writes its own query. Raising the tool 41% relative on ideal queries bought zero extraction recall, so the search ceiling was NOT the binding constraint. Do not plan week 4 against "better search"; measure WHERE recall is lost first -- query formulation, the decision to assert, or the indicator-list document shape are the candidates.

  **And a single-run score is not a measurement.** Observed range across three IDENTICAL repeats: emergent F1 **0.215**, typologies 0.071, actors 0.076, jurisdictions 0.008. The first baseline quoted all four to three decimals from one run each; only jurisdictions was safe to read that way. Emergent is bimodal (0.385/0.571/0.385) because whether a paraphrase clears the 0.60 containment threshold is close to a coin flip on an unnormalised vocabulary. **Report a band, or run the repeats.** Records kept in `data/repeats/rep{1,2,3}` and `prefix_rep{1,2,3}` (gitignored); the pre-fix arm is reproducible with a worktree at `6d19027^` plus `67ba833` on top, and VALIDATE it with `search_recall.py` before spending runs -- an A/B whose two arms are the same code measures nothing.
- **FULL-SET BASELINE, 2026-09-12 — and the six-advisory figures it supersedes.** All 20 extracted
  (`tools/batch_remaining.sh`, resumable, skips completed records), all validating, zero failed runs.

  | field | precision | recall | F1 |
  |---|---|---|---|
  | typologies | 0.889 | 0.357 | **0.510** |
  | emergent | 0.441 | 0.136 | **0.208** |
  | actors | 0.701 | 0.684 | 0.692 |
  | jurisdictions | 0.843 | 0.644 | 0.730 |

  **The six-advisory partial was optimistic on EVERY field** — typologies F1 0.578, actors 0.780,
  jurisdictions 0.908, emergent 0.571 with precision 1.000. Do not quote those again; they appear
  in earlier commits and in the 11-12 Sep journal entry as the numbers of the day.

  Per-document typology recall spans 0.14 to 0.78, median 0.33. **Document length does not predict
  it** (long >=53p mean 0.361, short 0.385) and neither does publisher (FATF spans 0.15 to 0.78).
  The agent asserts 4.5 governed typologies per document (sd 1.7, range 1-8) against golden's 11.2
  (range 5-20); correlation between what a document contains and what it asserts is +0.22.

- **THREE MECHANISMS behind the recall gap, each traced and verified 2026-09-12/13.** Full evidence
  in `evals/traces/`. This replaces "the recall gap is concentrated in indicator lists" as the
  working explanation.

  1. **Twin resolution — the most valuable, because it double-counts.** SAN006 is asserted in 0 of
     10 runs of ADV-2026-0017 while its cross-family twin TBML010 is asserted in 8 of 10. The
     prompt says *"Two typologies can share a label; choose by family"*. SAN002/PAT008 share the
     literal label "Shadow Fleet" and resolve correctly 10 of 10. SAN006 "Trade Based Sanctions
     Evasion" and TBML010 "Sanctions Evasion Through Trade" are the same concept reordered, so the
     rule NEVER FIRES. One wrong decision yields a false negative AND a false positive together, so
     it inflates the measured gap twice. **Fix belongs in the tool, not the prompt** (rule 2): the
     library should declare twin pairs and `propose_link` should enforce family. A rule whose
     predicate is string equality is fc-10's guardrail-3 defect in a new place.
  2. **Hybrid document shape.** ADV-2026-0009 is a narrative body (pp.1-7) plus a ten-bullet
     red-flag appendix (pp.8-9); every run folds the appendix into the body's single theme and four
     of six misses cite only the appendix. **The document-shape rule adopted in `a5abcc9` asks a
     BINARY question that a hybrid defeats** — it needs to apply per SECTION. Note this does NOT
     generalise: on ADV-2026-0017 three of five misses cite narrative pages.
  3. **Emergent splits in two.** Precision 0.441 is ~63% artefact (threshold, see above; 2 of the
     19 false positives are the agent being RIGHT where the label is incomplete). Recall 0.136 is
     ~99% real: **10 of 20 records propose ZERO emergent labels** and 44 of 56 sampled false
     negatives were never proposed at all. No threshold recovers those.

  **The assertion budget is NOT a quota.** ADV-2026-0009 asserts 1-2 of 7 golden, yet issued 6-19
  searches per run and across 10 runs retrieved 6 of the 7 golden ids at least once. SAN008 came
  back at a perfect 1.00, was confirmed with `get_typology`, and was asserted in 0 of 10 runs.

  **Label inflation is real and small.** Triage of ADV-2026-0004 (20 governed typologies, the
  highest in the set): 16 SUPPORTED, 2 THIN, 2 UNSUPPORTED, 64 of 64 citations on-page. Correcting
  the denominator moves that document 0.15 -> 0.17-0.19. The agent's 3 hits there land on the most
  strongly evidenced typologies and miss all four flagged weak — where it commits, it commits well.
  Still TRIAGE, not review: Claude assessing labels Claude drafted.

  **Cross-document:** TBML001 Over Invoicing is defective at both ends — unreachable by vocabulary
  on ADV-2026-0016, wrongly applied by the labeller on ADV-2026-0004.

- [ ] Week 4: fetcher / extractor / classifier / reviewer subagents. **DO NOT plan this against better retrieval.** Measured three ways on 2026-09-12: the search fix lifted top-5 recall 41% relative and moved extraction recall by nothing; typologies were retrieved, confirmed with `get_typology`, and then not asserted; and the agent asserts the same handful whether the document holds 5 golden typologies or 20. Build against the three mechanisms below, in that order. And note precision 0.889 is this pipeline's best property -- an assertion budget IS a precision strategy, so a reviewer that justifies each extra assertion beats simply asserting more
- [ ] Week 5: hooks, telemetry, `review.py` gate, desk digests
- [ ] Week 6: publish slice 1 on `future-capabilities.html`, tag `fc08-threatintel-slice1-v1.0.0`

## Journal

Engineering journal lives in `~/fc_vision_notes_dhartwig` (2026 entries). Filenames describe what happened that day. First entry to write: the mcp 1.x → 2.x rename hit on day one and how it was handled.

## Related repos

- `fc-10-repo`: governed platform, consumer of this slice's output via the MCP contract
- `dan-hartwig-portfolio/projects/nexus/`: public NEXUS site where slice 1 is published in week 6
