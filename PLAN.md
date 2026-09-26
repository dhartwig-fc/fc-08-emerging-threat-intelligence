# NEXUS Track 2 · Threat Intelligence · Slice 1: Intel Extraction

**Six-week agentic AI learning plan · Claude Agent SDK + MCP · Python**

| Field | Value |
|---|---|
| Owner | Dan Hartwig |
| Start | September 2026 |
| Budget | ~10 hrs/week · 6 weeks · ~3 hrs learning, ~7 hrs building |
| Stack | Python 3.11+, Claude Agent SDK, MCP Python SDK (FastMCP), Pydantic v2 |
| Target | `future-capabilities.html` gains **Threat Intelligence (Built · slice 1)** alongside SAR Drafter |
| Home repo | `fc-08-emerging-threat-intelligence` (decided 10 Sep 2026). FC10 stays the governed platform consumer; the MCP server contract is the interface between them |

---

## 1. What "intel extraction" means here

Question ↓ Capability ↓ Intelligence Produced ↓ Investigator Outcome

**Question.** A FATF report, an OFAC designation or an NCA alert lands. Which typologies in our library does it touch, which actors and indicators does it name and which desk needs to know?

**Capability.** An agentic pipeline that ingests the advisory, extracts a governed `AdvisoryRecord`, resolves it against the Knowledge Centre through MCP tools, flags anything emergent and routes a digest, with every fact cited to page and paragraph.

**Intelligence Produced.** Advisory pinned to typology IDs, actor and entity intel, candidate emergent typologies, a desk-routed digest and telemetry for every agent decision.

**Investigator Outcome.** Live doctrine. The Knowledge Centre stops being the "static half" and starts being refreshed by the world.

This is Track 2 on the roadmap: *"a threat-intelligence layer that pins live advisories and actors to the typology library."* Slice 1 covers all four named components at minimum depth: advisory overlay, actor/entity intel, emergent-typology loop and digest routing.

---

## 2. Design principles carried over from FC10

- Products are metadata-driven, canonical, deterministic, governed and evidence-based.
- Governance lives in tools and schemas, never in prompts alone.
- Nothing writes to the Knowledge Centre without passing the schema and a human review gate.
- Every extracted fact carries a citation. No citation, no fact.
- The schema (`schemas/advisory.py`) is the contract. Version it. Change it deliberately.

---

## 3. Repository layout

```
nexus-intel-extraction/
├── PLAN.md                          this document
├── requirements.txt
├── setup.sh                         macOS Bash 3.2 safe bootstrap
├── schemas/
│   └── advisory.py                  week 1 · AdvisoryRecord contract
├── mcp_server/
│   └── knowledge_centre_server.py   week 2 · Knowledge Centre as MCP tools
├── agents/
│   └── extract_advisory.py          week 1 · single-advisory extraction agent
├── data/
│   ├── typologies.json              fixture library (swap for FC10 export in week 2)
│   ├── advisories/                  source PDFs (gitignored)
│   ├── records/                     validated AdvisoryRecord JSON output
│   └── proposals.jsonl              review queue written by the MCP server
└── evals/
    ├── example_record.json          golden record proving the schema
    └── validate_record.py           schema validator for any record
```

---

## 4. Week-by-week

### Week 1 · Pre-flight: the agent loop and the contract

**Learn (3 hrs).** Claude Agent SDK fundamentals: `query()`, `ClaudeAgentOptions`, `output_format` with a JSON schema, `ResultMessage.structured_output`. Pydantic v2 validators. How structured output turns a model into a component you can test.

**Build (7 hrs).**
1. Run `bash setup.sh`. Confirm the smoke tests pass.
2. Download one FATF report into `data/advisories/` (the 2020 TBML Trends report is ideal because TBML001 already exists in your runtime).
3. Run `python agents/extract_advisory.py data/advisories/<file>.pdf --advisory-id ADV-2026-0001`.
4. Read the output record line by line against the PDF. Fix the schema where reality disagrees with it.
5. Validate with `python evals/validate_record.py data/records/ADV-2026-0001.json`.

**Deliverable.** A validated `AdvisoryRecord` for one real advisory and a schema you have argued with.

**Decision made.** Home is `fc-08-emerging-threat-intelligence`. Place this tree at the repo root so `setup.sh` and the `claude mcp add` path resolve without edits.

**Analogy.** This is the immigration desk before the border opens: define exactly what papers a traveller must carry before letting anyone through.

---

### Week 2 · First MCP server: the Knowledge Centre as treaties

**Learn (3 hrs).** MCP concepts: tools, resources, stdio transport, tool annotations. FastMCP decorator pattern. How Claude Code and the Agent SDK discover and call MCP servers. Why tool descriptions are the real prompt.

**Build (7 hrs).**
1. Register the server: `claude mcp add knowledge-centre -- "$PWD/.venv/bin/python" "$PWD/mcp_server/knowledge_centre_server.py"`.
2. Replace `data/typologies.json` with a real export of the Knowledge Centre families and IDs from FC10.
3. In `agents/extract_advisory.py`, pass the server via `mcp_servers` and add the four `knowledge_centre_*` tools to `allowed_tools`. Remove the pasted library from the prompt: the agent must look typologies up.
4. Re-run week 1's advisory. Diff the two records. Note where tool-grounded extraction changed the result.
5. Inspect `data/proposals.jsonl`. This is your review queue.

**Deliverable.** An agent that cannot name a typology the library does not contain.

**Analogy.** A diplomat can only act through signed treaties. The agent can only act through the tools you expose. Governance is in the treaty text.

---

### Week 3 · Entity and actor extraction plus the eval harness

**Learn (3 hrs).** Extraction versus resolution. Precision and recall for structured extraction. Evaluation-driven development: build the test set before improving the prompt.

**Build (7 hrs).**
1. Hand-label 20 advisories (mix of FATF, OFAC/OFSI, NCA, industry). Each label is a minimal `AdvisoryRecord` with the actors and typologies you expect. Store under `evals/golden/`.
2. Write `evals/score.py`: for each golden record, run extraction, compare typology IDs and actor names (case-insensitive, alias-aware) and report precision, recall and F1 per field.
3. Add a small resolved-entity fixture (10 entities with aliases) and a `knowledge_centre_resolve_actor` tool. Measure how many extracted actors resolve.
4. Attack the failure modes: hallucinated entities, over-linking, duplicate actors under different spellings. Fix through schema constraints and tool design before touching prompt wording.

**Deliverable.** A scored baseline. A number you can improve.

**Analogy.** Clinical trial discipline. No claim of effectiveness without a control set and a measured outcome.

---

### Week 4 · Multi-agent orchestration and the emergent-typology loop

**Learn (3 hrs).** Orchestration patterns: sequential, parallel, orchestrator-worker, handoff. Subagents in the Agent SDK (`agents` option, `AgentDefinition`). When one agent with good tools beats a swarm.

**Build (7 hrs).**
1. Split the pipeline into four roles: **fetcher** (PDF to pages plus hash), **extractor** (record), **classifier** (typology resolution through MCP), **reviewer** (checks citations exist in the text and flags emergent candidates).
2. Implement as subagents under one orchestrator. The reviewer must reject any fact whose quote is not found verbatim in the page text.
3. Run the 20-advisory batch end to end. Produce `data/emergent_candidates.json`.
4. Re-score with `evals/score.py`. Keep the multi-agent version only if it beats week 3's baseline.

**Deliverable.** A batch run producing a candidate list for the typology library and an honest comparison of single versus multi-agent.

**Analogy.** Mission control. Separate stations with narrow responsibilities, one flight director, and a go/no-go poll before anything commits.

---

### Week 5 · Governance, provenance and digest routing

**Learn (3 hrs).** Agent SDK hooks (`PreToolUse`, `PostToolUse`), `can_use_tool` permission callbacks, tracing and telemetry. Human-in-the-loop patterns.

**Build (7 hrs).**
1. Add a `PostToolUse` hook that writes a telemetry event for every tool call in the same shape as the Enterprise Telemetry page (stage, agent, tool, latency, outcome).
2. Build `review.py`: a CLI that walks `data/proposals.jsonl`, shows the rationale and citations and lets a human approve or reject. Approved links move to `data/approved_links.json`. This is the only path into the Knowledge Centre.
3. Implement digest routing as a deterministic rule over `suggested_desks` and typology family. Emit one Markdown digest per desk per batch.
4. Add a `can_use_tool` callback that denies any write tool not on the allowlist. Prove it by trying.

**Deliverable.** Provenance on every fact, a human gate before every write, telemetry for every decision and desk-routed digests.

**Analogy.** Airline black box plus a two-pilot rule. Nothing leaves the flight deck without a record and a second signature.

---

### Week 6 · Landing: publish the slice

**Learn (2 hrs).** Writing up agentic systems for a non-engineering audience. What a bank's model risk function will ask.

**Build (8 hrs).**
1. Update `future-capabilities.html`: add **Threat Intelligence (Built · slice 1)** mirroring the SAR Drafter entry and listing the four components at their delivered depth.
2. Build a walkthrough page: one advisory from PDF to pinned typology with cited sources, screenshots of the review gate and the desk digest.
3. Tag the release in the home repo, for example `fc08-threatintel-slice1-v1.0.0`.
4. Write the engineering-journal entry in `fc_vision_notes`: what broke, what surprised you, what slice 2 should change.
5. Post one LinkedIn-length summary using the Question ↓ Capability ↓ Intelligence Produced ↓ Investigator Outcome structure.

**Deliverable.** A public, governed, shipped capability with a score, a walkthrough and a release tag.

---

## 5. Definition of done for slice 1

Ticked 2026-09-26 from the measurements in `docs/RELEASE_SLICE1.md` (box 6 holds with a stated measurement gap).

- [x] `AdvisoryRecord` schema versioned at 1.x and used unchanged by all agents and tools
- [x] Knowledge Centre MCP server with list, get, search, propose and resolve tools
- [x] 20-advisory golden set with published precision and recall
- [x] Reviewer agent rejects uncited facts; zero uncited facts in the final batch
- [x] Human review gate is the only write path to the library
- [x] Telemetry emitted for every tool call
- [x] Desk digests generated for at least three desks
- [x] `future-capabilities.html` updated and release tagged

---

## 6. Weekly rhythm

| Slot | Hours | Use |
|---|---|---|
| Two weekday evenings | 2 × 1.5 | Learning block plus small build step |
| One weekend block | 5 | Main build and eval run |
| Friday 30 min | 0.5 | Journal entry in `fc_vision_notes`, update this plan |
| Sunday 30 min | 0.5 | Re-plan next week from what broke |

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| PDF text extraction is poor on scanned advisories | Week 1 uses born-digital FATF PDFs; add OCR only if slice 2 needs it |
| Agent invents typology IDs | Week 2 removes the library from the prompt; IDs must come from tools |
| Scope creep into Track 1 Copilot | Slice 1 stops at the review gate; context packages belong to Track 1 |
| Eval set too small to trust | 20 is the floor; grow to 50 in slice 2 |
| Cost drift on batch runs | Set `max_budget_usd` per run in `ClaudeAgentOptions`; log cost in telemetry |

---

## 8. Slice 2 candidates (not this plan)

Live feed ingestion (RSS, OFAC/OFSI JSON, NCA alerts), embedding-based typology search, resolved-entity graph linkage to the FC10 substrate, scheduled batch runs and a Knowledge Centre UI overlay showing "advisories pinned to this typology".
