# Regulatory scan demo — design (2026-10-14)

## Intent (owner)
A public, interactive demonstration of the NEXUS agentic intel model scanning the regulatory landscape, built
on what is real (the tracked Friday runs and ADV-2026-0026) plus a clearly labelled next-capability panel.
A new standalone page beside the slice-1 walkthrough, cross-linked. No cost figures. More commentary on the
agents and the technology behind the scan. Design agreed on the Design canvas (two iterations) before build.

## Audience and success
Portfolio visitors (hiring managers, FinCrime practitioners): lands in 60-90 seconds, rewards digging. Success:
every figure traces to a tracked fc-08 artefact or the agents' own constants; guardrails and the owner gate are
visible; the weak typology recall is shown; nothing claims NEXUS acts on advisories today.

## Page
1. Headline from the run's counts. Coverage (live from `feeds.sources.SOURCES`, manual FATF, not-yet from
   `SourceType`), the agents card, measured quality.
2. Replay of `feeds-2026-10-11-e7ad24`: listings, then each notice (verdict, reason, quote, disposition), then
   extraction (citations checked) and owner review, each step naming the agent or code acting.
3. Under the hood: six stages coloured agent / code / person; MCP tool lists; doctrine grounding; schedule.
4. ADV-2026-0026: quoted indicators, desks, owner decisions (SAN006 approved, emergent rejected).
5. NOT BUILT: SAN006 doctrine corroboration ("Trading party owned by / linked to a designated party", checked
   to be one SAN006 lists) and re-review of NEXUS's SAN006 case, Global Metals Ltd (SAN006-TRD001).

## Governance
`tools/build_scan_demo.py` (deterministic, `--check`), `tools/publish_scan_demo.py` (fresh-build, boundary and
root refusals; `site/SCAN_PUBLISHED`), `evals/check_scan_demo.py` (independent reader, 12 mutations),
`evals/check_published_scan_demo.py` (staleness gate). All registered in `tools/check_all.py` and
`evals/check_mutation_anchors.py`.

## Known gaps, recorded not fixed
- The run's report.md and accepted.json disagree about two notices; shown, not resolved.
- ~~The walkthrough page does not yet link back to the scan page.~~ Closed 2026-10-14 (f62b985): it does, and
  `check_scan_demo` fails if either page stops linking to the other.
