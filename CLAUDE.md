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
- [~] Week 3 (started 2026-09-10): twenty advisories selected from Source Matrix tiers 1-2, every URL verified, all downloaded to `data/advisories/` (gitignored, 920 pages, all born-digital), listed with hashes in `evals/golden/advisory_list.json`. All 20 labelled 2026-09-11 (3 in-session, 17 by subagents), every one validating and every citation on its page; ALL are drafts pending owner review. Schema 1.3.0 raised the extraction_notes cap to 4000 because reviewer notes on long reports hit the old 1000. Read `evals/golden/README.md` "State of the set" before scoring: emergent labels are NOT normalised (the same technique is named three ways), so an exact-string scorer will understate emergent recall. `evals/score.py` written and mutation-verified: governed ids exact, emergent by token containment >= 0.60 (owner decision; 1.00 would score paraphrases 0.000 and 0.50 collapses 2Rivers DMCC into 2Rivers PTE), actors alias-aware, zero-against-zero reports n/a not 1.000. Self-score of the golden set is 1.000 on all four fields. NOT YET: a real scored run (needs 20 extractions, ~$23 and ~2.5h), resolve_actor tool, owner review of the labels. fatf-gafi.org needs a real browser: `tools/fetch_fatf_via_chrome.js` (cached playwright module + installed Chrome, stealth headless) works; the Playwright MCP servers drop on downloads. **A/B on the search fix RAN 2026-09-12 and found no improvement**: five advisories re-extracted, typology recall 0.455 -> 0.436, emergent 0.450 -> 0.400, jurisdictions unchanged. Whole movement across five advisories is four items (+TBML005, -BA005, -SAN006, +2 spurious), which is inside the run-to-run variance week 1 measured, so this DOES NOT distinguish "the fix did not help" from noise -- three repeats per advisory would. Note why a ceiling lift need not translate: `search_recall.py` queries the tool with the GOLDEN LABEL'S OWN QUOTE, while at runtime the agent writes its own query, so 0.496 is optimistic about the queries actually made. Extraction is now FREE on the subscription token, so repeats cost only time.
- [ ] Week 4: fetcher / extractor / classifier / reviewer subagents
- [ ] Week 5: hooks, telemetry, `review.py` gate, desk digests
- [ ] Week 6: publish slice 1 on `future-capabilities.html`, tag `fc08-threatintel-slice1-v1.0.0`

## Journal

Engineering journal lives in `~/fc_vision_notes_dhartwig` (2026 entries). Filenames describe what happened that day. First entry to write: the mcp 1.x → 2.x rename hit on day one and how it was handled.

## Related repos

- `fc-10-repo`: governed platform, consumer of this slice's output via the MCP contract
- `dan-hartwig-portfolio/projects/nexus/`: public NEXUS site where slice 1 is published in week 6
