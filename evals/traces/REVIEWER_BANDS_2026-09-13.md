# The additive reviewer: acceptance bands

Twelve runs, three repeats across the four documents where the 2026-09-13 shape
count found misses concentrate in indicator sections. Zero failures.

`PLAN.md`'s test, unchanged: *keep the multi-agent version only if it beats week
3's baseline.* Amended once on this week's evidence — **"beats" means bands**,
because a single run has misled three times in three days.

## Result: it beats it

| | tp | fp | precision | recall | F1 |
|---|---|---|---|---|---|
| extraction alone | 11 | 3 | 0.786 | 0.224 | **0.349** |
| + reviewer, rep1 | 20 | 4 | 0.833 | 0.408 | **0.548** |
| + reviewer, rep2 | 21 | 6 | 0.778 | 0.429 | **0.553** |
| + reviewer, rep3 | 19 | 6 | 0.760 | 0.388 | **0.514** |

**The bands separate.** F1 0.349 against 0.514-0.553, no overlap. Recall 0.224
against 0.388-0.429, nearly doubled.

**Precision holds.** 0.760-0.833 against a 0.786 baseline — one repeat above, two
slightly below, the band straddling it rather than clearing it either way. This
is the first mechanism built that CAN spend precision, and on this evidence it
spends very little.

Every document improved, in every repeat:

| advisory | gold | extraction | + reviewer (3 reps) | mean lift |
|---|---|---|---|---|
| ADV-2026-0016 | 10 | 0.30 | 0.60 / 0.50 / 0.60 | +0.27 |
| ADV-2026-0009 | 7 | 0.14 | 0.43 / 0.43 / 0.43 | +0.29 |
| ADV-2026-0015 | 12 | 0.33 | 0.50 / 0.50 / 0.42 | +0.14 |
| ADV-2026-0004 | 20 | 0.15 | 0.25 / 0.35 / 0.25 | +0.13 |

ADV-2026-0004 is the one worth noting: 190 pages of FATF/Egmont report, a
completely different reading task from a 7-page alert, and the case least
expected to transfer. It transferred, at the smallest lift of the four.

## What it found that nothing else could

**SAN006 on ADV-2026-0016.** Missed in 13 of 13 extractions. Unreached by the
search length fix. Unrecovered by the twin fix, which removed its false-positive
substitute TBML010 without producing the right answer. The reviewer found it, and
its justification names the same red flag the TBML001 trace showed the search
tool could not reach from the word "overpays":

> SAN006 doctrine: *"…manipulating the trade transaction itself — mispricing an
> invoice… Large price deviation from benchmark (over/under-pricing)"*. Red flag
> 4 describes exactly this mechanism: *"A customer that significantly overpays
> for a Common High Priority list item"*.

It got there by reading doctrine and matching mechanisms, not by retrieving on
vocabulary. That is the difference between this mechanism and everything built
before it.

**ADV-2026-0009** is the document that asserted ONE typology of seven — the
extreme case traced overnight, where the agent searched 6 to 19 times per run and
committed to almost nothing. The reviewer added PAT002 and PAT010, both correct,
in all three repeats identically.

## The cost, stated

**34 additions, 27 correct, 7 spurious. Additions run at precision 0.794**,
below the pipeline's 0.889. The combined figure survives because it adds far more
right answers than wrong ones, not because the additions are clean.

| spurious addition | frequency | reading |
|---|---|---|
| ADV-2026-0015 SAN004 | 2 of 3 runs | **consistent** — a reasoned misjudgment, not noise |
| ADV-2026-0009 TBML004 | 2 of 3 runs | **consistent** |
| ADV-2026-0016 PAT002 | 1 of 3 | variance |
| ADV-2026-0004 TBML002U | 1 of 3 | variance |
| ADV-2026-0004 TBML006 | 1 of 3 | variance |

The two consistent ones are the ones to read before iterating. A repeated wrong
answer usually means the doctrine and the document genuinely resemble each other,
which is a labelling question as much as an agent one — and both documents'
labels are still Claude-drafted and Claude-reviewed pending the owner pass.

## The boundary on this result

**Measured on the four documents where misses concentrate, chosen deliberately.**
The shape count found eight documents with ZERO misses in indicator sections. The
reviewer's value there is untested and should be expected to be much smaller: its
prompt points it at indicator sections, and those documents have none that matter.

A full-set number needs the remaining sixteen. Until that exists, this result
says the mechanism works where it was aimed — not that it lifts the pipeline.

## Design notes that earned their place

- **Governance inherited, not redeclared.** Options come from
  `extract_advisory.agent_options` with only the prompt and output schema
  replaced. A second entry point rebuilding its own options is a second place for
  the tool surface to drift, and it drifted once unnoticed already (`67ba833`).
- **Two refusals in code, not in the prompt**: an id the library does not hold,
  and a re-proposal of something the record already claims. The prompt asks for
  both; asking is advice.
- **It does not write the record.** Additions go to their own file, so what the
  extractor said and what the reviewer added stay distinguishable. Merging them
  needs a schema field and a version bump, which is a decision for adoption, not
  for a probe.
- **"Returning zero additions is a valid and useful answer"** is in the prompt
  because restraint has to be available to a mechanism whose failure mode is
  over-assertion.


---

# Full set: all twenty, and the prediction that was wrong

The remaining sixteen ran one repeat each — the bands already settled
repeatability on the four. This measured REACH.

| all 20 | precision | recall | F1 |
|---|---|---|---|
| extraction alone | 0.889 | 0.357 | **0.510** |
| + reviewer | 0.853 | **0.545** | **0.665** |

**Recall +0.19, F1 +0.155, precision −0.036.** A trade, and a good one, but a
trade. 53 additions, 42 correct, 11 spurious by the scorer's reckoning.

## Where the cost falls — not where I predicted

| group | additions | precision OF ADDITIONS | F1 effect |
|---|---|---|---|
| the 7 others | 19 | **0.947** | 0.485 → 0.712 |
| the 4 concentrated | 10 | **0.900** | 0.349 → 0.548 |
| the 9 with ZERO indicator misses | 24 | **0.625** | 0.592 → 0.682 |

I predicted the nine zero-concentration documents would yield little, and said
silence there would be the mechanism behaving correctly. **They produced the most
additions at the worst precision** — and still improved F1, because the recall
gain outweighed the cost.

**The shape count predicted where the EXTRACTION's misses were. It did not
predict where the REVIEWER would succeed.** Those are different questions and I
conflated them when proposing to aim it. The seven documents the shape count did
not flag were the reviewer's strongest ground, at 0.947.

**Consequence: run it everywhere.** The targeting theory does not survive its own
measurement; the mechanism does.

## The spurious additions are mostly not spurious

ADV-2026-0002 added five, four scored wrong — the worst document in the set — so
they were read individually rather than accepted from the scorer.

**9 of its 10 citations verify on the exact page named.** The single failure is a
pypdf artefact (`"significant m ismatches"`), the same class of false negative
`check_citations.py` already carries a spacing-tolerant tier for.

| addition | cited evidence | read |
|---|---|---|
| PAT005 Shared/Mass Registration Address | *"registered at an address that is likely to be a mass registration address"* | defensible; doctrine is "entities connected through a shared address" |
| BA008 Layering | *"Incoming wire transfers… split and forwarded to non-related multiple accounts"* | defensible; doctrine is a chain of transfers severing the audit trail |
| BA006 Dormant Reactivation | *"A trade entity has unexplained periods of dormancy"* | defensible; mechanism matches, object is an entity not an account |
| TBML004 Phantom Shipping | *"Trade or customs documents… missing, appear to be counterfeits"* | defensible; doctrine names a missing or forged shipping record |

**So the likelier reading is that the LABEL is incomplete.** ADV-2026-0002 is a
ten-page FATF risk-indicator paper listing dozens of indicators across four
sections, and its label carries nine typologies.

**This inverts the label question.** The ADV-2026-0004 triage asked *are these 20
too many* and found 16 supported. This asks *are these 9 too few* — and on the
evidence quoted, they are.

**Which means the full-set number understates the reviewer in both directions.**
If a share of the 11 spurious additions are correct-but-unlabelled, its precision
is better than 0.792 AND the recall denominator is too small, so the recall gain
is understated too.

**The standing caveat applies and is not a formality.** This is Claude judging
Claude's additions against Claude's labels — the correlation every label records
in `label_status` and the owner pass exists to break. These are not ruled
correct. They are well-cited, doctrine-matched, and they belong on the owner's
adjudication list rather than in a spurious column.

## What is now known about the labels, from two directions

| document | question | finding |
|---|---|---|
| ADV-2026-0004 | 20 typologies — too many? | 16 SUPPORTED, 2 THIN, 2 UNSUPPORTED |
| ADV-2026-0002 | 9 typologies — too few? | 4 defensible additions the label lacks |

Both found by measurement rather than by re-reading twenty labels, which is what
makes the owner pass cheap: it is now a short list of specific disputes.

## Caveat on the numbers

Sixteen of the twenty are SINGLE runs. Only the four concentrated documents have
bands. The full-set figure is therefore a point estimate with known variance only
on a fifth of the set.
