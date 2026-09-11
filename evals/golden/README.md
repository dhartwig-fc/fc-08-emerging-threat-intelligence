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
- **Whether an indicator is a typology depends on the shape of the document.**
  Restated 2026-09-11 after review; the first wording was written with long
  narrative reports in mind and did not transfer.
  - In a **narrative report**, a red flag mentioned once in passing is not a
    typology. Label what the report is about.
  - In an **indicator-list document** — a red alert, a FATF risk-indicator
    paper, a FinCEN red-flag section — the indicators ARE the content. Each
    indicator, or each group of related indicators, may carry a typology, and
    a single bullet is sufficient evidence. Declining to label them would mean
    labelling almost nothing in the documents whose whole purpose is the list.
  - Confidence still carries the weight. One bullet supports a typology at
    `low` or `medium`; `high` needs the document to develop the technique.

  Why it was restated: 6 of 10 governed typologies in ADV-2026-0013 and 8 of 12
  in ADV-2026-0015 rest on a single indicator bullet, so the old rule condemned
  most of two labels. Worse, a labeller following it strictly on ADV-2026-0016
  omitted three typologies the alert's own numbered flags describe, and said so
  in its notes. A rule that makes the careful labeller produce the thinner
  label is the wrong rule.

## State of the set (2026-09-11)

ALL TWENTY REVIEWED label by label, 2026-09-11. Every label validates against
schema 1.3.0, and all 820 citations resolve to the page they name (a handful
match only after pypdf's mid-word spacing is normalised, which the checker
reports separately). Three were drafted in-session, seventeen by subagents
working from this README and the first three as exemplars, then every one was
reviewed against its PDF: each typology checked against the doctrine it claims
and each quote checked against the claim attached to it.

**They remain Claude's work, reviewed by Claude.** The review found and fixed
real defects, but it cannot break the correlation between the labeller and the
thing being measured. An owner pass is still what makes a published score a
statement about the agent rather than about Claude's reading habits.

What the review changed, across the twenty: four mappings removed on the
mechanism test (a quote naming the doctrine's words while describing something
else), four citations replaced or extended where the label was right and the
span proved nothing, three typologies added that the documents name and the
labels had missed, and one disagreement BETWEEN labels resolved.

What the set contains after review: 224 governed typology mentions across 37 of the
library's 57 typologies, 110 emergent labels, 158 actors.

| Family | Exercised | Never appears |
|---|---|---|
| sanctions | 10 of 10 | - |
| tbml | 10 of 12 | TBML002 (borrows TBML001's doctrine), TBML011 |
| correspondent_banking | 9 of 10 | BA006 |
| network | 7 of 15 | the five FND foundation pipes, PAT004, PAT006, PAT008 |
| capital_markets | **1 of 10** | everything but CM002 |

Regenerate these numbers after any label changes; the re-check moved every
one of them, and the earlier table wrongly said BA010 never appeared.

`extraction_notes` on two labels now sits at the 4000-character cap. Trim
before appending, or raise the cap deliberately with a schema bump.

Two coverage facts worth knowing before scoring. The five FND entries are
foundation capabilities rather than typologies an advisory describes, so
their absence is correct.

**Capital markets cannot be scored at all, and that is a finding rather than
a gap in the set.** One document carries the family, and reviewing it on
2026-09-11 reduced it from three typologies to one. The reason is structural:
the library's CM family covers MARKET ABUSE -- insider dealing, spoofing, wash
trading, front running -- while the only capital-markets advisory available
covers MONEY LAUNDERING THROUGH markets. They are different subjects sharing a
vocabulary, which is why seven of that label's fourteen entries are emergent.
Slice 2 needs a market-abuse document (an FCA Market Watch issue, a market
abuse enforcement notice) before any CM number means anything.

**The emergent labels are not normalised, and this constrains the scorer.**
110 emergent labels, almost all distinct strings. Only one string recurs verbatim
across advisories, yet clustering finds the same technique named three ways
(Black Market Peso Exchange in 0001, 0003 and 0008), and twice more for
hawala and for cargo blending. An exact-string scorer will therefore score
emergent recall near zero and report a defect that is in the labels, not the
agent. Either normalise the emergent vocabulary across the set first, or
score emergent matches on token overlap and say so in the published number.

Genuine Knowledge Centre gaps the set surfaces, each described by more than
one publisher: Black Market Peso Exchange and mirror-swap value transfer,
informal value transfer through hawala, blending or relabelling cargo to
disguise sanctioned origin, false end-user and end-use declarations, and
professional enablers as a class.

## First baseline, 2026-09-11

Six of the twenty have a predicted record: ADV-2026-0001 from week 2, plus the
five shortest run after the review. $2.59 and 144 turns for the five.
`evals/score_report.json` holds the full breakdown.

| field | precision | recall | F1 |
|---|---|---|---|
| typologies | 0.926 | 0.455 | 0.610 |
| emergent | 0.900 | 0.450 | 0.600 |
| actors | 0.821 | 0.762 | 0.790 |
| jurisdictions | 0.915 | 0.900 | 0.908 |

Read it as: what the agent says is nearly always right, and it says less than
half of what is there. Actors and jurisdictions, which are named on the page,
it finds. Typologies, which require mapping a described technique onto a
governed id, it does not.

**The most useful result is a false positive.** On ADV-2026-0013 the agent
labelled TBML002U Under Invoicing, citing "underestimating the purchase price
of merchandise by more than five times the actual amount". That is the exact
quote, on the exact typology, that the review REMOVED from the golden label,
because understating a price to evade export licensing is not the doctrine's
value transfer to an importer. The agent made the same mechanism error the
first draft of the label made.

Had the label not been reviewed, this would have scored as a true positive and
the shared blind spot would have been invisible. It is direct evidence for the
warning at the top of this section: labeller and agent share failure modes, and
only review separates them.

**One false positive is arguably the agent being right.** On ADV-2026-0002 it
labelled BA004 Circular Funds Flow for "Payments are routed in a circle - funds
are sent out from one country and received back in the same country". The
golden label carries TBML006 Circular Trade for that same sentence, and its own
notes record the choice as contestable ("TBML006 low over BA004... trade-entity
framing"). Funds circulating with no goods described fits BA004's doctrine at
least as well. The scorer counts it against the agent; a reviewer might not.

**The recall gap is concentrated in indicator lists.** The typologies most
often missed are the single-bullet ones the restated rule admits: PAT005,
SAN005, SAN001 across both red alerts. The agent appears to read indicator
lists as context rather than as content, which is the same judgement the
original strict rule made and the review overturned.

## Rules

- Never edit `advisory_list.json` by hand to change a hash or a date. Re-fetch
  the document and rebuild the entry.
- A label is written against the PDF, page by page, not against a record the
  agent produced. Reading the agent's output first is how a golden set learns
  the agent's mistakes.
- Twenty is the floor. Grow it in slice 2; never shrink it.
