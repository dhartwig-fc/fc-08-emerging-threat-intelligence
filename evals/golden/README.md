# Golden set

Week 3 of slice 1. Twenty advisories, hand-labelled, scored by `evals/score.py`
(week 3 step 2). This is the control set: no claim that the extraction agent
improved is admissible without a number from here.

## What is in this folder

- `advisory_list.json`: the twenty advisories, chosen from the publishers in
  `intelligence/Source_Matrix.md` tiers 1 and 2, every URL verified against
  the publisher on the build date, with sha256, page count and a stated date
  precision. This is selection provenance, not labels.
- `<advisory_id>.json`: one golden label per advisory, written by hand. Absent
  until labelled; `label_status` in the list flips when one exists.

The PDFs themselves live in `data/advisories/` and are gitignored. The hashes
here are how a clone proves it has the same documents.

## What a golden label is

A minimal `AdvisoryRecord`, validated by `evals/validate_record.py`, holding
only what the scorer compares:

- `typologies`: the governed ids the advisory actually touches, plus emergent
  labels for what it describes that the library does not hold. Each with one
  citation, page index as in the schema.
- `actors`: named parties and actor classes, with aliases the text uses.
- `jurisdictions`: the ISO codes the document names as case or risk locations.

Indicators are not scored in slice 1; leave them empty in a golden label.

## How the twenty were chosen

The Source Matrix names publishers, not publications. Two of its sixteen
source files name a specific document (EU-SOCTA 2025, FATF Annual Report
2024-25); the rest describe a publisher's output. So the list was built from
each tier 1 and 2 publisher's own catalogue, choosing documents that:

- describe typologies, actors or indicators, rather than policy or guidance,
  with one deliberate exception (Wolfsberg, the plan's "industry" slot);
- are born-digital PDFs that pypdf extracts cleanly (all twenty do: 920 pages,
  13 near-empty, none scanned);
- between them stress every governed family: TBML, sanctions, network
  intelligence, correspondent banking, capital markets; and include documents
  whose subject the library does not hold at all, so "emergent" is tested.

Tier 3 (BIS, OECD, WEF, UN, Geopolitical Monitor) is strategic foresight and
is out of scope for extraction.

## Labelling conventions (owner decisions, applied to all twenty)

- **Twins across families.** The library holds sanctions/TBML pairs (SAN006
  Trade Based Sanctions Evasion and TBML010 Sanctions Evasion Through Trade;
  SAN007 and TBML007 Dual Use Goods; SAN002 and PAT008 Shadow Fleet). An
  advisory framed as sanctions or export-control evasion labels the
  **sanctions** twin. Decided 2026-09-10 on ADV-2026-0013.
- **Actors are threat actors.** Named evaders, their networks and actor
  classes. Enforcement bodies, task forces and regulators are not actors.
- **A victim state is not a jurisdiction.** Jurisdictions are where the risk
  or the case sits, not who was harmed.
- **Indicators are not typologies.** A red flag the advisory lists is a
  typology only when the advisory is about that behaviour, not when it
  mentions it once.

## Rules

- Never edit `advisory_list.json` by hand to change a hash or a date. Re-fetch
  the document and rebuild the entry.
- A label is written against the PDF, page by page, not against a record the
  agent produced. Reading the agent's output first is how a golden set learns
  the agent's mistakes.
- Twenty is the floor. Grow it in slice 2; never shrink it.
