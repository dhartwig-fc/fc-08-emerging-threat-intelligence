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
schemas/advisory.py                AdvisoryRecord contract (read SCHEMA_VERSION, not this line) — the treaty
mcp_server/knowledge_centre_server.py   Knowledge Centre as MCP tools (read-only + propose)
agents/extract_advisory.py         single-advisory extraction agent, grounded on the MCP server since week 2
evals/golden/                      week-3 golden set: advisory_list.json (20, hashed) + hand labels as they are written
evals/search_probes.py             12 phrases the search tool must resolve; run after any library or scorer change
tools/fetch_fatf_via_chrome.js     fetches fatf-gafi.org PDFs, which refuse every non-browser client
data/typologies.json               GOVERNED export of fc-10's doctrine library (57 typologies); never hand-edit
tools/import_fc10_doctrine.py      regenerates it from fc-10's indexes/doctrine_library.json; deterministic, provenance = fc-10 commit + sha256
data/advisories/                   source PDFs (gitignored)
data/records/                      extraction-only AdvisoryRecords -- TRACKED since e0dbfb6, the evidence behind every published figure
data/records_merged/               extraction + reviewer additions under schema 1.4.0; the pipeline's output (tracked)
data/label_disputes/               the 15 owner label-pass disputes, built by tools/build_label_disputes.py (tracked)
data/proposals.jsonl               RETIRED: never written since week 5 (gitignored); frozen copy at data/proposals_legacy_2026-09-10_to_13.jsonl
evals/example_record.json          golden record proving the schema
evals/validate_record.py           validator for any record
evals/check_citations.py           proves every citation quote exists on the PDF page it names
evals/score.py                     scores predicted records against the golden set (P/R/F1 per field)
evals/check_tool_surface.py        proves the agent cannot reach Bash/Write/Read, and (live write probe) that a write tool off the allowlist is denied and never runs, and that runner, gate and server share one QUEUE_DIR; --live --mutate, --live --mutate-allowlist, --mutate-queue (static)
evals/search_aliases_probe.py       guards SEARCH_ALIASES: direction pair fixed, emergent guard intact; --mutate
evals/check_twin_pairs.py           guards the cross-family twin relation and the propose_link refusal; --mutate
evals/check_added_by.py             pins schema 1.4.0's added_by / review_justification pair; --mutate
evals/check_emergent_threshold.py   pins emergent at 0.50 and proves 0.40 is a real floor; --mutate
evals/search_recall.py              search measured against the golden set's real advisory sentences, not hand-written probes
evals/probe_prompt_variant.py       A/B a prompt change without editing the agent; INVERTED 2026-09-12, now builds the pre-adoption prompt
evals/traces/                       where recall goes and what was built about it: the full baseline, three traced mechanisms, the label triage, the shape count, the reviewer's bands and the single-vs-multi comparison
tools/batch_remaining.sh           extracts every advisory with no record; resumable and idempotent, shortest first
tools/build_emergent_candidates.py  the week-4 deliverable: every emergent entry with its evidence and near neighbours
tools/merge_reviewer_additions.py   merges reviewer additions into records under schema 1.4.0; non-destructive by default
tools/build_label_disputes.py      builds the owner label-pass disputes from evidence on disk; deterministic
tools/apply_label_decisions.py     applies owner decisions to evals/golden/; validates before writing, refuses to overturn a decided dispute
schemas/citation_match.py          THE quote-on-page rule, shared by the MCP server, the review gate and check_citations.py
evals/check_citation_match.py      pins the matcher's ARTEFACT and ELLIPSIS tiers cold: footnote digits, line-break hyphens and in-order ellipsis fragments pass; different words or numbers, decomposed accents, out-of-order or short fragments do not; --mutate no-artefact|ignore-digits|no-floor|no-letters|empty|substring-digits|ascii-letters|keeps-digits|no-nfc|ellipsis-unordered|ellipsis-short
agents/run_identity.py             who a run is; the runner hands it to the MCP server, never the agent
data/proposals/                    the review queue: one tracked proposal/2 file per run (week 5)
data/proposals_legacy_2026-09-10_to_13.jsonl   the 383 pre-week-5 proposals, frozen, never reviewed
governance/                        the review gate: proposals.py (load, re-check, group), decisions.py (log, refusals, rebuild), card.py
tools/review.py                    THE ONLY writer of approvals: interactive, --decisions, --list, --check
data/review_decisions.jsonl        append-only decision log (tracked); the two approvals files are rebuilt from it
evals/check_proposal_contract.py   pins the proposal contract; --mutate citations|run|queue
evals/check_review_gate.py         pins the gate end to end; --mutate quarantine|overturn|evidence|contract
agents/telemetry.py                one terminal telemetry event per tool call (Post hooks); RUN_STARTED/RUN_COMPLETED
agents/permissions.py              THE write allowlist (propose_link only) and the can_use_tool callback that records every decision
data/telemetry/                    one tracked {stage,status,timestamp,message,payload} file per run
evals/check_telemetry.py           offline: hooks + callback driven with the SDK's measured input shapes; --mutate refusal|allowlist|terminal
data/desk_routing.json             desk routing as DATA: family -> desk (network -> FIU liaison), suggestion-only desks, desk titles
governance/routing.py              which desks an advisory reaches and why; a family desk needs a typology of its family
governance/digest.py               one Markdown digest per desk: approvals from the decision log, awaiting review from the record
tools/build_digests.py             writes data/digests/<batch_id>/<desk>.md; --check proves a committed batch rebuilds identically; --current --check checks the batch CURRENT names
data/digests/                      committed digest batches (snapshots; a new state is a new batch id)
data/digests/CURRENT               the batch id the guards check, one line: cutting a new batch edits this, never check_all's list
evals/check_digest_batch.py        pins the batch contract: manifest, pinned log prefix, never overwritten, a file added later ignored; --mutate prefix|overwrite
evals/check_digest_routing.py      routing + digests, incl. the SAN001 case on real data; --mutate suggestion|rejected|scope
schemas/actor_match.py             THE name normaliser and exact-match resolver, shared by evals/score.py and resolve_actor
tools/build_actor_register.py      builds the actor register from the golden labels; merges only on exact cross-advisory matches; ids derived from content, never position; --check
data/actor_register.json           the governed actor register (tracked, built, never hand-edited)
data/actor_register_candidates.json what the builder would not decide, for the owner: ambiguous, same advisory, similar names
evals/actor_resolution.py          how many of the EXTRACTOR's named actors resolve, with one row per actor; writes evals/actor_resolution.json; --check
evals/actor_resolution.json        the committed resolution report: counts plus one row per named actor (read the numbers there, not here)
evals/check_actor_resolution.py    pins actor identity (exact only, never guess, stable ids) and calls the MCP tool itself; --mutate containment|ambiguous|same-advisory|category|positional|tool
evals/known_citation_defects.json  the citation-defect baseline check_citations --all diffs against; held 118 -> 103 -> 91, emptied 2026-09-25 by the owner's citation repair
evals/attested_citations.json      the 12 owner-attested citations: true quotes the matcher cannot place (page break, ellipsis across pages, dropped accent, bullet glyph), by full identity; read by check_citations only
evals/check_attestations.py        pins attestation cold: one citation by full identity; stale, still-needed, duplicated, malformed entries refused; --mutate cover-anything|no-stale|no-still-needed|no-dup
evals/owner_decisions/citation_repair_2026-09-25.json  the citation-repair evidence: the owner's decision verbatim + dated rulings, every re-paged / removed citation by quote hash, the attested-in-place list, the removed items, sha256 pins of data/records and the attestations
tools/apply_citation_repair.py     applies that decision to data/records_merged (--build-evidence, --apply, --check); merge_reviewer_additions applies it too, refuses --in-place, and writes nothing if any record refuses
evals/check_citation_repair.py     cold replay of the repair against data/records and data/records_merged; --mutate keep-uncited|repage-ambiguous
tools/check_all.py                 runs every guard from one list, classed cold|needs-pdfs|needs-portfolio|needs-reviewed; --cold (CI), --list
scripts/hooks/pre-commit           runs tools/check_all.py on every commit; enable per clone: git config core.hooksPath scripts/hooks
.github/workflows/checks.yml       CI: tools/check_all.py --cold on every push and PR; guards needing the PDFs print NOT RUN
schemas/proposal_contract.py       THE proposal contract (schema, stages, quote bounds, proposal_id), shared by the MCP server and the gate
evals/owner_decisions/             dated evidence of what the owner decided about the golden labels
agents/review_advisory.py          the additive reviewer: what did the extraction miss, justified against doctrine
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
- [x] Week 3 (2026-09-10 to 09-12): twenty advisories selected from Source Matrix tiers 1-2, every URL verified, all downloaded to `data/advisories/` (gitignored, 920 pages, all born-digital), listed with hashes in `evals/golden/advisory_list.json`. All 20 labelled 2026-09-11 (3 in-session, 17 by subagents), every one validating and every citation on its page; ALL are drafts pending owner review (the 15 DISPUTED entries were owner-decided 2026-09-24 -- see the label pass entry below; the rest still await review). Schema 1.3.0 raised the extraction_notes cap to 4000 because reviewer notes on long reports hit the old 1000. Read `evals/golden/README.md` "State of the set" before scoring: emergent labels are NOT normalised (the same technique is named three ways), so an exact-string scorer will understate emergent recall. `evals/score.py` written and mutation-verified: governed ids exact, emergent by token containment **>= 0.50 since 2026-09-13** (was 0.60; 1.00 would score paraphrases 0.000), actors alias-aware at 0.60. **The two thresholds are separate constants and were being conflated.** The 0.60 emergent value was defended by "0.50 collapses 2Rivers DMCC into 2Rivers PTE" -- a REAL pair, both companies in ADV-2026-0017's label, scoring exactly 0.50 -- but they are ACTORS, matched under the ACTOR threshold. An actor case was holding up the emergent constant. (An earlier note in this file called that example synthetic; it is not, and the correction matters because it is exactly why DEFAULT_ACTOR_THRESHOLD must STAY at 0.60.) Measured on the full 20, emergent 0.60 -> 0.50 credits 7 further matches, every one read pair by pair and every one a genuine restatement, and merges nothing: F1 0.208 -> 0.306, precision 0.441 -> 0.647. **0.40 is a real floor**, merging "Professional Intermediary Gatekeeper Complicity" with "Trusts and legal arrangements interposed" at 0.43 on ADV-2026-0004 -- different mechanisms sharing legal vocabulary. Pinned by `evals/check_emergent_threshold.py`, mutation-verified. See `evals/traces/EMERGENT_AUDIT_2026-09-12.md`, actors alias-aware, zero-against-zero reports n/a not 1.000. Self-score of the golden set is 1.000 on all four fields. FULL-SET BASELINE RAN 2026-09-12 (see below). Extraction is FREE on the subscription token (`claude setup-token`), so the remaining work is time, not money -- the "~$23" framing is void. resolve_actor now exists (`knowledge_centre_resolve_actor`, week 6 -- see the Week 6 entry below). NOT YET: an owner review of the UNDISPUTED label entries, which is the one thing here code cannot do. fatf-gafi.org needs a real browser: `tools/fetch_fatf_via_chrome.js` (cached playwright module + installed Chrome, stealth headless) works; the Playwright MCP servers drop on downloads. **SETTLED 2026-09-12 with eight runs of the five advisories: the search fix changed NOTHING measurable, and the claim that the tool was half the recall gap is FALSIFIED.** Four pre-fix runs (the original baseline + 3 repeats in a worktree at `6d19027^`, validated at top-5 recall 0.351) against four post-fix runs (the rerun + 3 repeats, 0.496). Every field's band OVERLAPS:

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
  | emergent | 0.647 | 0.200 | **0.306** | (at threshold 0.50; was 0.441/0.136/0.208 at 0.60)
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
     it inflates the measured gap twice. A rule whose predicate is string equality is fc-10's
     guardrail-3 defect in a new place: correct English, wrong test, satisfied by the pair that
     does not need it.

     **FIXED 2026-09-13 in `df8d4aa`, and it only half worked — read this before planning against
     it.** `_TWIN_PAIRS` in the MCP server declares the relation as data, surfaced in every
     `search_typologies` line, attached to the `get_typology` record, and **enforced by a refusal**:
     `propose_link` rejects a twinned link whose rationale does not name the twin. Measured over
     three runs of ADV-2026-0017 against the prior ten:

     | | old | after the fix |
     |---|---|---|
     | SAN006 asserted | 0 of 10 | **0 of 3** |
     | TBML010 asserted | **8 of 10** | **0 of 3** |
     | recall | 0.25–0.38 (mean 0.325) | **0.38 / 0.38 / 0.38** |

     So it removed the false positive and collapsed the variance — the old runs alternated because
     TBML010 sometimes displaced a correct answer — and **did not produce the right twin.** Faced
     with a choice it could not justify, the agent DROPS the claim rather than reconsidering which
     twin fits. **A refusal suppresses; it does not redirect.** That is the same shape as "prefer
     fewer, well-cited items": making the agent assert less is easy, making it assert correctly
     more is the work, and every governance mechanism built so far is subtractive.

     Which suggests the SAN006 miss was never primarily a twin problem — the substitution was a
     symptom, and removing the wrong option exposed the real gap. Where the agent DID have the
     reasoning it complied, and the reasoning is now on the record in the review queue: SAN002's
     rationale reads *"TWIN of PAT008 (network family); this advisory is issued by NCA/OFSI/FCDO
     explicitly to address sanctions evasion … so the sanctions-family twin SAN002 is the correct
     fit per the stated convention."* That is worth more than the 0.05 recall it moved, because
     week 5's reviewer can audit it.

     **THE FOURTH PAIR WAS NOT A PAIR — ruled 2026-09-13, and it was my error.** `BA008` and
     `CM004` are both labelled "Layering" and I added them to the map on that overlap without
     reading the doctrine. BA008 (correspondent banking) is *"the classic middle stage of money
     laundering: funds pushed through a chain of transfers to sever the audit trail"*; CM004
     (capital markets) is *"ORDER-BOOK layering — staggering non-bona-fide orders to fake depth,
     then cancelling"*. **A homonym, not a twin**: the three real pairs are one technique under two
     codes, this is two techniques under one word. Declaring it was actively harmful, not merely
     wrong — **BA008 appears in 13 of the 20 golden labels, more than any other typology**, so every
     BA008 link would have demanded a meaningless CM004 justification, and a refusal that cannot be
     satisfied honestly gets answered by dropping the claim. Removed, and recorded in
     `_REJECTED_TWIN_CANDIDATES` so the same shortcut cannot re-add it. **LABEL OVERLAP PROPOSES;
     DOCTRINE DECIDES.** Guarded by `evals/check_twin_pairs.py` (10 checks, mutation-verified, and it
     redirects `NEXUS_PROPOSALS_PATH` so it never writes into the real review queue). What the tool
     CANNOT do: adjudicate framing. It never sees the document, so it guarantees only that the agent
     knew the twin existed and recorded a reason.
  2. **Hybrid document shape — real, and smaller than it looked.** ADV-2026-0009 is a narrative
     body (pp.1-7) plus a ten-bullet red-flag appendix (pp.8-9); every run folds the appendix into
     the body's single theme and four of six misses cite only the appendix. The `a5abcc9` rule asks
     a BINARY question that a hybrid defeats. **Counted across the set 2026-09-13: 14 of 20 are
     hybrid, but only 0.33 of misses cite an indicator page, bimodally.** So the mechanism is real
     and caps at a third — see item 3 below, now closed against a per-section prompt rule.
     `SHAPE_COUNT_2026-09-13.md` also CORRECTS the shape labels in the per-document table of
     `FULL_BASELINE_2026-09-12.md`: ADV-2026-0013 and ADV-2026-0002 are NARRATIVE (0013 has zero
     bullet-formatted lines), and ADV-2026-0016 is HYBRID, not indicator-list. Those labels had been
     assigned from the publisher rather than the content.
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

- **RANKED FIXES from the three mechanisms, state as of 2026-09-13.**
  1. ~~Twin pairs into the tool.~~ **DONE, `df8d4aa`** — removed the false positive, did not
     recover the false negative. See mechanism 1 above. Open: an owner ruling on BA008/CM004.
  2. ~~Emergent threshold 0.60 → 0.50.~~ **DONE 2026-09-13.** F1 0.208 → 0.306, precision 0.441 →
     0.647; typologies, actors and jurisdictions unchanged. It fixes PRECISION only — recall moved
     0.136 → 0.200 and the rest of that gap is real, since 10 of 20 records propose no emergent
     technique at all. The threshold is now pinned with the two facts that justify it, so a future
     change has to argue with evidence. **The actor threshold deliberately did NOT move.**
  3. ~~Document-shape rule per section.~~ **CLOSED 2026-09-13 — measured, and NOT worth doing as a
     prompt change.** The measurement this item was blocked on came back against it. 14 of 20
     documents are HYBRID (a red-flag section inside a narrative body), so the binary question the
     `a5abcc9` rule asks is indeed wrong for most of the set — but **only 48 of 144 misses (0.33)
     cite a bullet-dense page at all**, and the third is bimodal, not spread: ADV-2026-0016 7 of 7,
     0015 7 of 8, 0009 5 of 6, 0004 12 of 17, against EIGHT documents at exactly zero. Two-thirds of
     the gap is in narrative prose no shape rule reaches. Where it does point: those four documents
     are where a SECTION-AWARE REVIEWER PASS would pay — a step that walks an indicator list and
     asks what each bullet evidences, which is week 4, not the prompt. The `a5abcc9` rule STAYS:
     incomplete rather than wrong, cost nothing, tightened ADV-2026-0013's variance to zero.
     Evidence and instrument limits: `evals/traces/SHAPE_COUNT_2026-09-13.md`.
  4. ~~**Owner label pass.**~~ **DONE 2026-09-24** -- all four ADV-2026-0004 entries KEPT, against the
     triage's UNSUPPORTED on TBML001 and SAN008. See the label pass entry below.

- [~] Week 4 (started 2026-09-13): **built the ADDITIVE reviewer only, not the four stations PLAN.md lists,
  and it PASSES its acceptance test.** The fetcher is deterministic Python already working; the classifier is a
  retrieval role and retrieval is not the constraint; and the reviewer PLAN.md specifies ("reject any fact whose
  quote is not in the page text") duplicates `check_citations.py`, which all 624 citations already pass. The
  measured defect is the other one — a quote that exists is not a quote that supports — and the measured gap is
  recall. `agents/review_advisory.py` is a second pass that asks what the extraction MISSED, under a burden:
  every addition must quote the doctrine's own words and say how the evidence matches THAT mechanism.
  Twelve runs, three repeats over the four concentrated documents:

  | | tp | fp | P | R | F1 |
  |---|---|---|---|---|---|
  | extraction alone | 11 | 3 | 0.786 | 0.224 | **0.349** |
  | + reviewer (3 reps) | 19-21 | 4-6 | 0.760-0.833 | 0.388-0.429 | **0.514-0.553** |

  Bands SEPARATE on F1 and recall; precision straddles the baseline rather than clearing it. It found SAN006 on
  ADV-2026-0016 — missed in 13 of 13 extractions, unreached by the search fix, unrecovered by the twin fix — by
  reading doctrine and matching mechanisms rather than retrieving on vocabulary. **Cost: additions run at
  precision 0.794**, below the pipeline's 0.889; this is the first mechanism built that CAN spend precision.
  BOUNDARY: measured only where misses concentrate. Eight documents have ZERO misses in indicator sections and
  the reviewer's value there is untested. `evals/traces/REVIEWER_BANDS_2026-09-13.md`.

  **FULL SET, all 20, 2026-09-13: extraction P 0.889 R 0.357 F1 0.510 -> + reviewer P 0.853 R 0.545
  F1 0.665.** Recall +0.19, F1 +0.155, precision -0.036. 53 additions, 42 correct. **RUN IT EVERYWHERE:
  my targeting theory did not survive its own measurement.** The nine documents the shape count said had
  ZERO indicator misses produced the MOST additions (24) at the WORST precision (0.625) and still improved
  F1; the seven it did not flag were the strongest ground (19 additions at 0.947). The shape count predicted
  where the EXTRACTION missed, not where the REVIEWER succeeds — different questions, conflated when I
  proposed aiming it.

  **AND THE SPURIOUS ADDITIONS ARE MOSTLY NOT SPURIOUS.** ADV-2026-0002's four scored-wrong additions were
  read individually: 9 of 10 citations verify on the page named, and PAT005, BA008, BA006 and TBML004 are
  each doctrine-matched to a quoted indicator. Its label carries 9 typologies for a ten-page FATF
  risk-indicator paper. **The label is likely INCOMPLETE**, which inverts the ADV-2026-0004 triage question
  and means the full-set number understates the reviewer in BOTH directions. Claude judging Claude's
  additions against Claude's labels — for the owner's list, not ruled correct.

  **`data/emergent_candidates.json` DONE 2026-09-13** — 50 candidates, 50 DISTINCT label strings, across 15
  advisories (34 from extraction, 16 from the reviewer), 23 carrying near neighbours. It SUGGESTS adjacency
  and does not assert identity, because automatic clustering was built and REJECTED: at the scorer's 0.50
  threshold it merged four distinct techniques on the words "money laundering", and at the best threshold
  tested only one of six multi-member clusters was unambiguously right. **The scorer's threshold was
  validated for matching one predicted label against one golden label — a different task from clustering
  arbitrary labels**, and in a corpus where every label names a laundering technique the domain vocabulary
  discriminates nothing. The signal survives anyway: "Underground Banking" appears across FOUR advisories
  under four different names, which is exactly what a curator needs.

  **SCHEMA 1.4.0, 2026-09-13: `added_by` + `review_justification` on TypologyReference.** `added_by`
  defaults to `extractor`, so all 20 existing records validate unchanged and a pre-1.4.0 record means what it
  always meant. The VALIDATOR PAIR is the point: a reviewer addition MUST carry its justification, and an
  extractor entry may NOT carry one. The 0016 trace found SAN006 retrieved, confirmed and dropped with no
  record of why — rule 3 governs what ENTERS a record and nothing governed the reasoning; an addition
  arriving without its reason is that defect pointing the other way. Writing the example record caught a
  flaw in the field's own description: an EMERGENT entry has no doctrine to quote, so the description now
  covers both cases. Pinned by `evals/check_added_by.py`, mutation-verified.

  **MERGE STEP DONE 2026-09-13.** `tools/merge_reviewer_additions.py` writes additions into records under
  1.4.0: all 20 merged, 68 additions, zero validation failures, zero duplicates. **This is the pipeline's
  real output number** — typologies P 0.853 R 0.545 **F1 0.665** against extraction-only 0.889/0.357/0.510,
  and emergent 0.306 -> **0.352**, which the band runs had not isolated. Provenance intact: 192 typologies,
  68 `added_by=reviewer`, ZERO missing a justification — the schema refusing it, not the script remembering.
  `where_found` has no field in the contract and is prepended to the justification rather than dropped.
  **NON-DESTRUCTIVE BY DEFAULT**: `data/records/` is the evidence for every published baseline figure, so
  merged records go to `data/records_merged/` and `--in-place` waits on a decision that the merged record IS
  the pipeline's output.

  **THE `--in-place` DECISION, TAKEN 2026-09-13: preserve first, then act.** Three measured facts settled
  it. `data/records/` is NOT tracked in git — it exists on one machine. Extraction is NOT deterministic —
  three identical re-runs of ADV-2026-0016 gave THREE different typology sets, so re-running does not
  recover a record, it produces a different one. And every published figure depends on exactly those
  records: F1 0.510, recall 0.357, the per-document table, the acceptance bands, `score_report.json`, the
  journal, the slice-1 page. A plain overwrite destroys the only copy of the evidence behind every number
  this project has published — fc-10's priority 1 in a new place, where deleting an 'orphaned' page would
  have destroyed the last record of a run and the answer was preserve first.

  So `--in-place` ARCHIVES to `data/records_extraction_only/` before overwriting, and REFUSES if that
  archive already holds records — a second run would otherwise archive the MERGED records over the
  originals, which is the loss the archive exists to prevent, one step removed. Verified on a throwaway
  copy: first run archives 22 and merges, second exits 2. **The flag has not been run for real**; two-stage
  is the standing arrangement — `data/records/` is extraction output, `data/records_merged/` is pipeline
  output, and anything downstream should say which it reads.

  **SINGLE VS MULTI, written 2026-09-13: `evals/traces/SINGLE_VS_MULTI_2026-09-13.md`.** One extra agent
  instead of four. The fetcher should not be an agent (deterministic, and three supervising subagents died
  on the quota meter producing nothing while a bash script finished the job first time); the classifier
  targets retrieval, ruled out three ways; the specified reviewer duplicates a passing guard AND subtracts.
  Cost measured: extraction 14 runs mean $0.73 / 33.9 turns / 270s, reviewer 27 runs mean $0.48 / 29.1
  turns / 159s — so two stages are ~1.65x one agent for +0.155 F1. **The test is not how many agents but
  whether each addresses a MEASURED constraint.** What would justify more: a routing decision a model must
  make, a genuinely parallel workload, or an adversarial reviewer from a DIFFERENT model family — the last
  is the strongest remaining case, and it is about independence rather than throughput.

- [x] **Week 4 COMPLETE** (2026-09-13): additive reviewer, acceptance bands, full-set run, emergent
  candidates, schema 1.4.0, the merge step, the --in-place decision, and the single-vs-multi write-up. Sixteen of the twenty are SINGLE runs;
  only the four concentrated documents have bands. **DO NOT plan the rest against better retrieval.** Measured three ways on 2026-09-12: the search fix lifted top-5 recall 41% relative and moved extraction recall by nothing; typologies were retrieved, confirmed with `get_typology`, and then not asserted; and the agent asserts the same handful whether the document holds 5 golden typologies or 20. Build against the three mechanisms below, in that order. And note precision 0.889 is this pipeline's best property -- an assertion budget IS a precision strategy, so a reviewer that justifies each extra assertion beats simply asserting more
- [x] **OWNER LABEL PASS, CLOSED 2026-09-24** (`b1d8ffa`, `500d320`). 15 disputes across 7 advisories,
  built from evidence by `tools/build_label_disputes.py` into `data/label_disputes/`. 11 are ADD (a reviewer
  addition the label lacks; checked on all 20) and 4 are STRIKE (ADV-2026-0004's triage; checked on ONE
  advisory). **All 11 additions ACCEPTED; all 4 strikes REJECTED** -- ADV-2026-0004 keeps TBML001, SAN008,
  TBML004 and SAN001. Evidence, with the page's own timestamps:
  `evals/owner_decisions/label_pass_2026-09-24.json`. `label_status` in `advisory_list.json` says how many
  DISPUTED entries the owner decided and never that a label is owner-reviewed outright: **the 13 advisories
  with no dispute are UNCHALLENGED, not confirmed**, and strike-direction triage still covers one advisory.

  Typologies F1 against the corrected key:

  | | before the pass | after |
  |---|---|---|
  | extraction only (`data/records`) | 0.510 | 0.492 |
  | extraction + reviewer (`data/records_merged`) | 0.665 | **0.704** |

  **The key changed, so these are not the same measurement as week 4's.** 0.510 / 0.665 stay the week-4
  result against the week-4 key; quote the new pair only as "against the owner-corrected key". And the
  merged figure rose PARTLY BY CONSTRUCTION: every accepted addition came from the reviewer being scored.
  What it does show is 11 of 11 reviewer additions survived owner adjudication. The extraction-only score
  fell because the key grew and the extractor misses the new entries too.

  **How it nearly recorded nothing.** The first adjudication page loaded its disputes FROM its database, and
  in the owner's view `claude.use("db")` resolved null -- so it rendered no cards, the owner saw an empty page,
  and the decisions collection stayed empty while the pass was reported done. Version 2 embeds the disputes
  in the page and, where the database is absent, keeps choices on the device with a "Copy my decisions"
  button. **A page that collects decisions must render its content without its database**, and a read of the
  decisions collection is the only evidence the pass happened. The page saved 14 of 15; the fifteenth
  (ADV-2026-0005 BA006) was given in chat.

  **`tools/apply_label_decisions.py`, and two defects its first runs found in itself.** The first run
  appended a provenance sentence to `extraction_notes` and pushed ADV-2026-0018 past the 4000-character cap;
  only a separate `validate_record.py` run caught it. The tool now validates every label before writing
  anything (mutation-verified: a planted overlong note is refused with nothing written) and leaves
  `extraction_notes` alone. The second run, for the one late decision, would have OVERWRITTEN the day's
  evidence file with one decision; it now folds a run into the day's record, may settle an open dispute,
  and refuses to overturn a decided one ("a change of mind needs its own dated record"). A fresh run from
  `2fbe1d9` reproduced the applied labels byte for byte.

  **Do not re-run `build_label_disputes.py` to "refresh" the set.** It rebuilds from the CURRENT golden,
  so accepted additions vanish from it and the record of what the owner was asked is lost. The committed
  disputes are the question; the owner_decisions file is the answer. Extend it for new triage, do not
  regenerate over it.

- [x] **Week 5** (started 2026-09-24): spec `docs/superpowers/specs/2026-09-24-week5-governance-design.md`.
  **Sub-project A DONE** (plan `docs/superpowers/plans/2026-09-24-week5-a-proposal-contract-and-review-gate.md`):
  every proposal names its run and carries quotes verified at proposal time and again at review; one
  tracked queue file per run; `tools/review.py` is the only writer of approvals, rebuilt from an
  append-only decision log. The 383 legacy proposals are frozen, not reviewed -- they carry no quotes and
  no run. `.venv/bin/python tools/review.py --check` proves the approvals and the log agree, and that every
  logged decision cites real queue proposals for its own link.

  **Built subagent-per-task with a review after each, and the final whole-branch review earned its seat.**
  It found three Important gaps every per-task review had passed: the review-time re-check did not
  re-assert the proposal contract (an EMPTY quote matched every page, and a line naming neither a typology
  nor an emergent label became an approvable `EMERGENT[]` link); nothing checked that the log held only
  decisions the gate made (a hand-written approval with `proposal_ids: []` passed `--check`); and
  `--queue-dir` + `--log` overridden with the approvals paths left at default rebuilt the REAL approvals
  files from a scratch log. All fixed (`7c231b2`..`be365a7`): `schemas/proposal_contract.py` is now the one
  definition of `proposal_id`, stages and quote bounds, shared by server and gate; the four record paths
  are overridden together or not at all. Guards: `check_proposal_contract.py` 12 checks,
  `check_review_gate.py` 57, every rule mutation-verified (`--mutate contract` added).

  **First decisions through the gate, 2026-09-24 (`332eaab`).** The live ADV-2026-0013 run
  (`adv-2026-0013-extractor-f617bd3b00`) proposed 5 links, every quote verified; the owner approved all
  five (SAN003, SAN007, SAN004; SAN001 and BA005 at medium, each on a single red-flag bullet).
  `approved_links.json` now holds 5, `approved_emergent.json` 0. **The log has no `decided_by` field, so
  every line in it is the owner's by construction:** Claude renders the cards and recommends, the owner
  confirms, and only then is `--decisions` run. Never apply a decision the owner has not confirmed in chat.

  **Parked, deliberately:** the server bounds quote length on the raw string and the gate after strip (a
  padded short quote is quarantined at review, never approved); the writer-scan self-test was never seen
  failing inside the guard. **Deferred to B:** the server binding its queue path to
  `data/proposals/<run_id>.jsonl`; reviewer runs' telemetry lacking `run_id`; nothing runs
  `review.py --check` automatically.

  **Sub-project B DONE, pushed 2026-09-24 (`b0ff55d`)** (plan
  `docs/superpowers/plans/2026-09-24-week5-b-telemetry-and-write-allowlist.md`). Probed first, from SDK
  source and two live Haiku runs: a plain string prompt already runs the SDK's control protocol, so no
  streaming change; a DENIED call fires no Post hook, so the permission callback records that call's
  terminal event; Post hooks carry `duration_ms`. `allowed_tools` now pre-approves ONLY the three
  read-only tools -- pre-approving a tool shadows the callback entirely, which is why propose_link was
  moved out. Every other MCP tool reaches `can_use_tool`, which allows `propose_link` only, with a
  complete run identity; the CLI's own StructuredOutput tool is auto-allowed.

  Every run writes `data/telemetry/<run_id>.jsonl` built to leave exactly one terminal event per tool
  call; a governed refusal reads REFUSED. Whether a given run DID is recorded, not assumed:
  `RUN_COMPLETED.terminal_check` carries `telemetry.reconcile()` over every ToolUseBlock id the runner
  saw -- `unterminated` and `duplicated` lists, on success and failure alike, never raised.

  **The live probe earned its place on its first run.** At `ea5c54b` it FAILED its REFUSED check (that
  commit's message overclaims): a structured-output MCP tool's refusal reaches PostToolUse as a
  JSON-encoded string, '{"result":"Rejected: ..."}', which the offline shapes had not included.
  `57a505d` decoded it -- and the final whole-branch review then found that fix OVER-REACHED, decoding the
  tool's own data too, so every `get_typology` success recorded an empty outcome. `190abf9` decodes the
  transport envelope ONCE and never a string inside it; witnesses pin both, plus a mid-string "Rejected:"
  that must read SUCCESS. The same review made the static check ASK the installed callback (deny a write,
  allow propose_link) and read the built argv, instead of checking only that a callback exists.
  Guards: `check_telemetry.py` 21 checks, `--mutate refusal|allowlist|terminal`;
  `check_tool_surface.py` 14 static checks, plus `--live` (Bash probe + write probe) and
  `--live --mutate-allowlist`, which must breach.

  Of the three items deferred to B above, B closed one: reviewer runs' telemetry now carries `run_id`
  (B3, `09c0dee`). The other two are **deferred to week 6**: the server binding its
  queue path to `data/proposals/<run_id>.jsonl`, and nothing running `review.py --check`
  automatically. **Parked from B:** whether the CLI skips `can_use_tool` for an MCP tool annotated
  `readOnlyHint` (unprobed; a PreToolUse deny-by-name hook would close the class); a run killed by
  KeyboardInterrupt/CancelledError writes RUN_STARTED only; `reconcile()` on a corrupt telemetry line
  would mask the run's real exception; per-run reconciliation is verified offline only -- the next live
  extraction's `terminal_check` is its first real measurement.

  **Sub-project C DONE** (plan `docs/superpowers/plans/2026-09-24-week5-c-desk-digests.md`): one
  digest per desk per batch, routed by typology family from `data/desk_routing.json` (a suggestion
  alone never reaches a family desk). First batch `data/digests/slice1-2026-09-24/`: 7 of 7 desks
  receive advisories. Planning found that building "approved" from the records would have hidden an
  owner approval the record does not carry (ADV-2026-0013::SAN001), so approvals come from the
  decision log. Content is scoped by desk (a family desk quotes only its own family's links and names the rest; a desk sees the whole advisory only when every reason it was routed is the agent's suggestion), and an approval routes its advisory to its family desk -- unscoped, the sanctions desk had been quoting BA005. Deferred to week 6: nothing runs `build_digests --check`, and a committed batch cannot be re-checked after later decisions (pin the log length a batch was built from). **Week 5's four PLAN.md items are delivered**: provenance on every new-contract proposal, a human
  gate before every write, telemetry for every decision, desk-routed digests. NEXT: week 6 (publish
  slice 1, tag `fc08-threatintel-slice1-v1.0.0`), with the items deferred to it above.
- [~] **Week 6** (from 2026-09-25): spec `docs/superpowers/specs/2026-09-25-week6-landing-design.md`. Sub-project 1 DONE: a digest batch pins its inputs (`manifest.json`; `--check` survives later decisions and separates "inputs moved" from "same inputs, different output"; a batch is never overwritten); `propose_link` writes only `data/proposals/<run_id>.jsonl`; `knowledge_centre_resolve_actor` resolves on EXACT matches only against `data/actor_register.json` (similar names are suggestions, never identity -- measured, 4 of 5 containment matches named the wrong party); `tools/check_all.py` runs every guard, from `scripts/hooks/pre-commit` (enable per clone: `git config core.hooksPath scripts/hooks`) and cold on CI. Record citations were never re-verified after week 1: 118 of 717 in data/records_merged cited the wrong page or text the matcher could not find. Owner decision 2026-09-25 (evals/owner_decisions/citation_repair_2026-09-25.json): the shared matcher (`schemas/citation_match.py`) first gained an ARTEFACT tier (footnote markers, line-break hyphens, NFC-composed letters) and an ELLIPSIS tier (fragments on the page in order), re-measuring the set 118 -> 103 -> 91; a page-spanning tier was tried and dropped, because every tolerance also loosens `propose_link`'s gate. 12 true quotes the matcher cannot place are owner-attested (evals/attested_citations.json). Then in data/records_merged 80 citations were re-paged (75 found on exactly one other page + 5 page-break quotes moved to the page the quote starts on), 4 removed, and the 2 facts left uncited removed (ADV-2026-0004's two indicators); data/records (the extractor's evidence) is untouched. The citation baseline is empty (check_citations --all: 713 checked, 12 verified by attestation, 0 pinned); the current digest batch is slice1-2026-09-25; merged F1 unchanged, typologies 0.704 -> 0.704 (actors 0.692, jurisdictions 0.730, emergent 0.352 -- only unscored indicators were removed). NEXT: sub-project 2, the publish.
- [ ] Week 6: publish slice 1 on `future-capabilities.html`, tag `fc08-threatintel-slice1-v1.0.0`

## Journal

Engineering journal lives in `~/fc_vision_notes_dhartwig` (2026 entries). Filenames describe what happened that day. First entry to write: the mcp 1.x → 2.x rename hit on day one and how it was handled.

## Related repos

- `fc-10-repo`: governed platform, consumer of this slice's output via the MCP contract
- `dan-hartwig-portfolio/projects/nexus/`: public NEXUS site where slice 1 is published in week 6
