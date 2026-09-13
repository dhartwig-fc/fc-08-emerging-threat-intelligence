# Document shape across the twenty — and why the per-section rule is not worth building

Measured 2026-09-13 to unblock ranked fix 3, *"document-shape rule per section,
not per document"*. `CLAUDE.md` deliberately carried that item as a warning
rather than an instruction, because two findings pointed different ways: hybrid
shape explained ADV-2026-0009 and explicitly did not explain ADV-2026-0017. The
instruction was to count how many of the twenty are hybrid before touching the
prompt again.

**The count supports the diagnosis and the follow-through kills the fix.**

## Method

Page text extracted from all 20 PDFs with `pypdf`. Per page, a line counts as an
indicator item if it opens with a bullet glyph or a numbered marker; a page is
**bullet-dense** at five or more such lines. A document is classified:

| shape | test |
|---|---|
| INDICATOR-LIST | bullet-dense pages >= 40% of the document |
| HYBRID | a red-flag/indicator heading appears AND some pages are bullet-dense, but under 40% |
| NARRATIVE | no indicator heading, or no bullet-dense pages |

Then the question the shape is a proxy for: **do the missed typologies actually
cite the bullet-dense pages?**

## The count

| shape | documents |
|---|---|
| **HYBRID** | **14 of 20** |
| NARRATIVE | 3 of 20 |
| INDICATOR-LIST | 3 of 20 |

| advisory | pages | dense | frac | shape | misses citing a dense page |
|---|---|---|---|---|---|
| ADV-2026-0001 | 66 | 5 | 0.08 | HYBRID | 0 of 4 |
| ADV-2026-0002 | 10 | 0 | 0.00 | NARRATIVE | 0 of 2 |
| ADV-2026-0003 | 53 | 0 | 0.00 | NARRATIVE | 0 of 12 |
| ADV-2026-0004 | 190 | 90 | 0.47 | INDICATOR-LIST | **12 of 17** |
| ADV-2026-0005 | 24 | 1 | 0.04 | HYBRID | 0 of 3 |
| ADV-2026-0006 | 70 | 5 | 0.07 | HYBRID | 1 of 7 |
| ADV-2026-0007 | 72 | 15 | 0.21 | HYBRID | 2 of 7 |
| ADV-2026-0008 | 76 | 12 | 0.16 | HYBRID | 4 of 11 |
| ADV-2026-0009 | 13 | 8 | 0.62 | INDICATOR-LIST | **5 of 6** |
| ADV-2026-0010 | 18 | 5 | 0.28 | HYBRID | 0 of 8 |
| ADV-2026-0011 | 15 | 9 | 0.60 | INDICATOR-LIST | 4 of 8 |
| ADV-2026-0012 | 35 | 3 | 0.09 | HYBRID | 2 of 4 |
| ADV-2026-0013 | 6 | 0 | 0.00 | NARRATIVE | 0 of 7 |
| ADV-2026-0014 | 29 | 3 | 0.10 | HYBRID | 2 of 8 |
| ADV-2026-0015 | 15 | 5 | 0.33 | HYBRID | **7 of 8** |
| ADV-2026-0016 | 7 | 2 | 0.29 | HYBRID | **7 of 7** |
| ADV-2026-0017 | 8 | 1 | 0.12 | HYBRID | 0 of 5 |
| ADV-2026-0018 | 30 | 11 | 0.37 | HYBRID | 2 of 3 |
| ADV-2026-0019 | 100 | 1 | 0.01 | HYBRID | 0 of 13 |
| ADV-2026-0020 | 83 | 2 | 0.02 | HYBRID | 0 of 4 |

## What it says

**The binary question is wrong for 14 of 20, as suspected.** The rule adopted in
`a5abcc9` asks the agent whether this is an indicator-list document. Six
documents answer cleanly. The other fourteen are both things at once, and the
agent is being asked a question its document does not answer. That much of the
case for a per-section rule holds.

**But only 48 of 144 misses — 0.33 — cite a bullet-dense page.** That is the
ceiling on what ANY shape-based fix can reach, and it is a third.

**And the third is concentrated, not spread.** The distribution is bimodal:

| nearly all misses in indicator sections | nearly none |
|---|---|
| ADV-2026-0016 — 7 of 7 | ADV-2026-0003 — 0 of 12 |
| ADV-2026-0015 — 7 of 8 | ADV-2026-0019 — 0 of 13 |
| ADV-2026-0009 — 5 of 6 | ADV-2026-0010 — 0 of 8 |
| ADV-2026-0004 — 12 of 17 | ADV-2026-0013 — 0 of 7 |

In eight documents a per-section rule would change nothing whatsoever.

## Decision: item 3 is CLOSED, measured and not worth doing as a prompt change

Two-thirds of the recall gap sits in narrative prose that no shape rule reaches,
and the reachable third is four documents. A prompt sentence aimed at it would
buy a fraction of a third — smaller than the twin fix, which itself only removed
a false positive.

**Where the finding does point:** those four documents are where a
*section-aware reviewer pass* would pay — not a prompt sentence but a step that
walks an indicator list and asks what each bullet evidences. That is the
additive mechanism the full baseline already argued for, and this measurement
says where to aim it first. It belongs in week 4, not in the prompt.

The rule shipped in `a5abcc9` STAYS. It is incomplete rather than wrong, it cost
nothing, and it measurably tightened ADV-2026-0013's variance to zero.

## Corrections to earlier claims of mine

**ADV-2026-0013 is not an indicator-list document.** It has zero
bullet-formatted lines — flowing prose about OFAC designations and enforcement
actions. The per-document table in `FULL_BASELINE_2026-09-12.md` labelled it
indicator-list, and ADV-2026-0002 likewise. Both were assigned from the
publisher and the document's reputation rather than its content. The shapes in
that table were assumptions typeset as a measurement; these are the measured
ones.

**ADV-2026-0016 is HYBRID, not indicator-list.** Two of its seven pages are
bullet-dense. That sharpens the original trace: the agent was not failing to
treat an indicator-list document as one — it was being asked to classify a
document that is genuinely both.

## What this instrument cannot see

- **It counts bullet FORMATTING, not indicators.** A document presenting its red
  flags as prose is invisible to it, and ADV-2026-0013 is exactly that case. So
  "NARRATIVE" here means narrative *formatting*, never absence of indicators.
- **Extraction is imperfect.** Thirteen documents have between one and six pages
  under 200 characters, and `pypdf` reported skipping form content on one
  (`Exceeded 5000 form XObject invocations`). Pages that failed to extract cannot
  be bullet-dense, so the dense counts are floors.
- Consequently **0.33 is a floor on the true share, not a point estimate.** It
  would have to be wrong by a factor of two to change the decision, and the
  bimodal distribution — eight documents at exactly zero — is not an artefact
  extraction error would produce.

## Reproduce

Inputs: `data/advisories/` (gitignored, hashed in
`evals/golden/advisory_list.json`), the 20 golden labels, the 20 predicted
records. Extraction of all 920 pages takes about a minute.

A line is an indicator item when it matches
`^\s*(?:[bullet-glyph]|\(?\d{1,2}[\.\)])\s+\S`, where the glyph class is
`• ● ▪ – — - * ·`; a page is dense at five or more. A miss "cites a dense page"
when any citation on a golden typology absent from the predicted record names a
page in that set.
