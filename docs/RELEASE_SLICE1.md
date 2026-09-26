# Slice 1 release audit — `fc08-threatintel-slice1-v1.0.0`

Measured 2026-09-26 on `main` at `56fe64e`, by running each check below in the working checkout
(with the gitignored advisory PDFs present). The tag is created on the commit that adds this file.
Every figure here was measured for this audit; none is copied from earlier notes. Where a box holds
with a caveat, the caveat is stated, not rounded away.

The eight boxes are PLAN.md §5, verbatim.

| # | Box | How it was checked | Measured | Verdict |
|---|---|---|---|---|
| 1 | `AdvisoryRecord` schema versioned at 1.x and used unchanged by all agents and tools | Every record in `data/records/`, `data/records_merged/` and `evals/golden/` validated with `schemas.advisory.AdvisoryRecord`; importers of the schema listed | `SCHEMA_VERSION = "1.4.0"`. 60 of 60 records validate (extractor 20, merged 20, golden 20), 0 invalid. One definition, imported by the extractor, the merge, the repair, the label pass, the citation check, the validator and the scorer | **Holds.** The schema moved 1.0.0 → 1.4.0 inside 1.x during the slice, every bump additive; stored records keep the version they were written under (extractor 1.2.0/1.3.0, golden 1.3.0, merged 1.4.0) and all validate under 1.4.0 |
| 2 | Knowledge Centre MCP server with list, get, search, propose and resolve tools | `knowledge_centre_server.mcp.list_tools()`; `evals/check_tool_surface.py` | `get_typology`, `list_typologies`, `propose_link`, `resolve_actor`, `search_typologies` (all `knowledge_centre_`-prefixed). The surface guard HOLDS: the server's tools equal the agent's lists, and the four read tools are exactly the read-only-annotated ones | **Holds.** `resolve_actor` resolves on exact matches only; similar names come back as labelled suggestions, never identity |
| 3 | 20-advisory golden set with published precision and recall | Count of `evals/golden/ADV-*.json`; the live walkthrough's score section | 20 golden labels. Precision, recall and F1 for four fields, extraction-only and extraction + reviewer, are published on the live walkthrough (section 9) and computed from the golden set at build time | **Holds**, with the caveat the page states: the labels were drafted and reviewed by Claude, and the owner has decided the 15 disputed entries, not yet the rest; the scores are single full-set runs |
| 4 | Reviewer agent rejects uncited facts; zero uncited facts in the final batch | Items without a citation in `data/records_merged/`; the schema's citation constraint; `evals/check_citations.py --all` | 546 items (typologies, actors, indicators), 0 uncited; the schema requires at least one citation on each item kind, so an uncited fact cannot validate; `propose_link` refuses a quote not on its page. `citations: 713 checked, 12 verified by attestation, 0 known defects pinned, 0 new, 0 fixed` | **Holds.** 12 of the 713 citations are true quotes the matcher cannot place (page breaks, list bullets, one dropped accent), attested by the owner in `evals/attested_citations.json`, not machine-verified |
| 5 | Human review gate is the only write path to the library | Writers of the approvals and the typology library; `evals/check_review_gate.py`; the agent's write allowlist | The agent's only write is `propose_link`, into its own run's queue file (`evals/check_tool_surface.py`, `evals/check_proposal_contract.py`). Approvals are written only by `governance/decisions.py`, reached only through `tools/review.py` (the `check_review_gate.py` writer scan HOLDS). The typology library itself is written only by `tools/import_fc10_doctrine.py`, a human-run import of fc-10's governed doctrine | **Holds** |
| 6 | Telemetry emitted for every tool call | `evals/check_telemetry.py`; the one telemetry file | The guard HOLDS (offline, mutation-verified). The one run with telemetry, `adv-2026-0013-extractor-69eeab7b41`, has 28 tool-call events for 28 distinct tool calls, none duplicated, none missing an id, plus 7 permission decisions | **Holds, with a measurement gap.** That run started 2026-09-24 16:57; the per-run reconciliation against the SDK's own list of calls (`terminal_check`) was added at 18:40 the same day, so it is proven offline but has not yet run on a live extraction. Runs before week 5 have no telemetry |
| 7 | Desk digests generated for at least three desks | `data/digests/CURRENT`; desk files carrying advisories | Current batch `slice1-2026-09-25`: 7 of 7 desks receive advisories; `build_digests --current --check` matches its pinned inputs | **Holds.** Digests are built on demand, not delivered to a desk |
| 8 | `future-capabilities.html` updated and release tagged | The live portfolio; `git tag` | Live since 2026-09-26: Track 2 shows "Built · slice 1" and links the walkthrough, which is byte-identical to fc-08's committed page (sha256 in `site/PUBLISHED`). The tag `fc08-threatintel-slice1-v1.0.0` is created on the commit carrying this audit | **Holds** once the tag exists |

## What the release does not claim

- The extraction agent does not yet call `resolve_actor`; no `entity_key` links to the resolved-entity substrate exist.
- The corpus is 20 fixed advisories; nothing ingests new publications automatically, and nothing flows into detection.
- Approved emergent candidates are not doctrine.
- Scores are single runs with no bands of their own.

## Parked and known, carried into slice 2

- Section 6 of the walkthrough pairs two register entries to record categories by first word; the pairing is correct today but unguarded.
- The walkthrough's resolver sentence is a tripwire: a new extraction's queue file on disk makes the page builder refuse, blocking every commit until that sentence is reworded.
- `RESOLVER_ADDED` is a date typed into the builder, verified against git where history exists.
- Per-run `terminal_check` has not yet run live (box 6).
