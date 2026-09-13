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
evals/check_twin_pairs.py           guards the cross-family twin relation and the propose_link refusal; --mutate
evals/check_emergent_threshold.py   pins emergent at 0.50 and proves 0.40 is a real floor; --mutate
evals/search_recall.py              search measured against the golden set's real advisory sentences, not hand-written probes
evals/probe_prompt_variant.py       A/B a prompt change without editing the agent; INVERTED 2026-09-12, now builds the pre-adoption prompt
evals/traces/                       where recall goes: the full baseline, three traced mechanisms, the label triage, the document-shape count and the reviewer's acceptance bands
tools/batch_remaining.sh           extracts every advisory with no record; resumable and idempotent, shortest first
tools/build_emergent_candidates.py  the week-4 deliverable: every emergent entry with its evidence and near neighbours
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
- [x] Week 3 (2026-09-10 to 09-12): twenty advisories selected from Source Matrix tiers 1-2, every URL verified, all downloaded to `data/advisories/` (gitignored, 920 pages, all born-digital), listed with hashes in `evals/golden/advisory_list.json`. All 20 labelled 2026-09-11 (3 in-session, 17 by subagents), every one validating and every citation on its page; ALL are drafts pending owner review. Schema 1.3.0 raised the extraction_notes cap to 4000 because reviewer notes on long reports hit the old 1000. Read `evals/golden/README.md` "State of the set" before scoring: emergent labels are NOT normalised (the same technique is named three ways), so an exact-string scorer will understate emergent recall. `evals/score.py` written and mutation-verified: governed ids exact, emergent by token containment **>= 0.50 since 2026-09-13** (was 0.60; 1.00 would score paraphrases 0.000), actors alias-aware at 0.60. **The two thresholds are separate constants and were being conflated.** The 0.60 emergent value was defended by "0.50 collapses 2Rivers DMCC into 2Rivers PTE" -- a REAL pair, both companies in ADV-2026-0017's label, scoring exactly 0.50 -- but they are ACTORS, matched under the ACTOR threshold. An actor case was holding up the emergent constant. (An earlier note in this file called that example synthetic; it is not, and the correction matters because it is exactly why DEFAULT_ACTOR_THRESHOLD must STAY at 0.60.) Measured on the full 20, emergent 0.60 -> 0.50 credits 7 further matches, every one read pair by pair and every one a genuine restatement, and merges nothing: F1 0.208 -> 0.306, precision 0.441 -> 0.647. **0.40 is a real floor**, merging "Professional Intermediary Gatekeeper Complicity" with "Trusts and legal arrangements interposed" at 0.43 on ADV-2026-0004 -- different mechanisms sharing legal vocabulary. Pinned by `evals/check_emergent_threshold.py`, mutation-verified. See `evals/traces/EMERGENT_AUDIT_2026-09-12.md`, actors alias-aware, zero-against-zero reports n/a not 1.000. Self-score of the golden set is 1.000 on all four fields. FULL-SET BASELINE RAN 2026-09-12 (see below). Extraction is FREE on the subscription token (`claude setup-token`), so the remaining work is time, not money -- the "~$23" framing is void. NOT YET: resolve_actor tool, and the owner review of the labels, which is the one thing here code cannot do. fatf-gafi.org needs a real browser: `tools/fetch_fatf_via_chrome.js` (cached playwright module + installed Chrome, stealth headless) works; the Playwright MCP servers drop on downloads. **SETTLED 2026-09-12 with eight runs of the five advisories: the search fix changed NOTHING measurable, and the claim that the tool was half the recall gap is FALSIFIED.** Four pre-fix runs (the original baseline + 3 repeats in a worktree at `6d19027^`, validated at top-5 recall 0.351) against four post-fix runs (the rerun + 3 repeats, 0.496). Every field's band OVERLAPS:

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
  4. **Owner label pass.** Gates every published figure. `evals/traces/TRIAGE_ADV-2026-0004_LABEL.md`
     is a four-decision list: TBML001 and SAN008 to strike or keep, TBML004 and SAN001 to judge thin.

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

- [ ] Week 4 remaining: a schema field + version bump if the reviewer's additions are to merge into records,
  and the honest single-vs-multi comparison. Sixteen of the twenty are SINGLE runs;
  only the four concentrated documents have bands. **DO NOT plan the rest against better retrieval.** Measured three ways on 2026-09-12: the search fix lifted top-5 recall 41% relative and moved extraction recall by nothing; typologies were retrieved, confirmed with `get_typology`, and then not asserted; and the agent asserts the same handful whether the document holds 5 golden typologies or 20. Build against the three mechanisms below, in that order. And note precision 0.889 is this pipeline's best property -- an assertion budget IS a precision strategy, so a reviewer that justifies each extra assertion beats simply asserting more
- [ ] Week 5: hooks, telemetry, `review.py` gate, desk digests
- [ ] Week 6: publish slice 1 on `future-capabilities.html`, tag `fc08-threatintel-slice1-v1.0.0`

## Journal

Engineering journal lives in `~/fc_vision_notes_dhartwig` (2026 entries). Filenames describe what happened that day. First entry to write: the mcp 1.x → 2.x rename hit on day one and how it was handled.

## Related repos

- `fc-10-repo`: governed platform, consumer of this slice's output via the MCP contract
- `dan-hartwig-portfolio/projects/nexus/`: public NEXUS site where slice 1 is published in week 6
