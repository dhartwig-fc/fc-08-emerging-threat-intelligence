# First full-set baseline, and the constraint it exposes

20 of 20 advisories extracted 2026-09-12, all validating against schema 1.3.0,
zero failed runs. Previous baselines covered six and said so on their own front
page; this is the first number that describes the whole golden set.

## The baseline

| field | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|
| typologies | 80 | 10 | 144 | 0.889 | 0.357 | 0.510 |
| emergent | 15 | 19 | 95 | 0.441 | 0.136 | 0.208 |
| actors | 108 | 46 | 50 | 0.701 | 0.684 | 0.692 |
| jurisdictions | 188 | 35 | 104 | 0.843 | 0.644 | 0.730 |

**The six-advisory partial was optimistic on every field**, and materially so:

| field F1 | six-advisory partial | full 20 |
|---|---|---|
| typologies | 0.578 | **0.510** |
| emergent | 0.571 | **0.208** |
| actors | 0.780 | **0.692** |
| jurisdictions | 0.908 | **0.730** |

Emergent collapsed hardest: precision 1.000 -> 0.441. The scorer's own
"these numbers describe that subset only" warning was doing real work.

## The finding: a near-fixed assertion budget

Typology recall ranges 0.14 to 0.78 across the twenty, median 0.33. Two
hypotheses died and one survived.

**Document length does not predict recall.** Long documents (>=53 pages, n=8)
mean 0.361; short (<53p, n=12) mean 0.385. Effectively identical.

**Publisher does not predict it either.** FATF documents span 0.15 to 0.78.

**What does predict it is the golden count, because the agent asserts a roughly
constant number of typologies whatever the document contains:**

| | min | max | mean | sd |
|---|---|---|---|---|
| golden typologies per document | 5 | 20 | 11.2 | 3.6 |
| **asserted by the agent** | 1 | 8 | **4.5** | **1.7** |

    correlation, golden count vs asserted count : +0.22
    correlation, pages      vs asserted count : +0.26
    correlation, golden count vs recall        : -0.33

An agent scaling its output to the document would show a strong positive
correlation between what the document contains and what it asserts. It shows
almost none. Recall is therefore largely the denominator moving while the
numerator stays put, and the fit is direct: at precision 0.889, predicted
recall is 0.889 x asserted / golden. For ADV-2026-0002 (9 golden, 8 asserted)
that gives 0.79 against an actual 0.78; for ADV-2026-0004 (20 golden, 5
asserted) 0.22 against an actual 0.15.

**So the binding constraint on typology recall is how many items the agent is
willing to commit to, not what it can find.** That subsumes both mechanisms
traced earlier today: the prompt's "prefer fewer, well-cited items" was one
expression of the budget (removing it moved recall +0.03 and tightened variance),
and the TBML001 vocabulary gap explains individual misses within the budget
rather than the budget itself.

## The alternative explanation, which is not ruled out

The labels may be over-generous, especially on long reports. ADV-2026-0004
carries **20 governed typologies** out of a 57-typology library for a single
document; ADV-2026-0019 carries 17. If a meaningful share of those are not
genuinely evidenced, part of this "gap" is label inflation rather than agent
suppression.

The two explanations are separable and the measurement is already on the backlog:
**an owner review of one high-count label.** Take ADV-2026-0004 and judge whether
all 20 are supported on the mechanism test. The labels are Claude-drafted and
Claude-reviewed, `label_status` says so, and today's trace of ADV-2026-0016
already found its SAN006 citations to be 85-92 characters, cut mid-sentence, one
of them pure boilerplate. Label quality is not uniform.

Until that review happens, the honest statement is: **recall is limited by an
assertion budget, whose correct size is unknown because the target it is
measured against has not been independently validated.**

## What this says about week 4

Do not build the subagent pipeline to improve retrieval. Retrieval is not the
constraint — measured three ways today: the search fix lifted top-5 recall 41%
relative and moved extraction recall by nothing; one traced typology was
retrieved, confirmed by `get_typology`, and then dropped; and the agent asserts
the same handful of typologies whether the document holds 5 or 20.

The question week 4 should answer is what sets the budget, and whether a reviewer
pass that asks "what else does this document evidence?" raises it without costing
the 0.889 precision that is currently the pipeline's best property.

## Provenance

Extractions: `tools/batch_remaining.sh` (resumable, skips completed records).
Records are gitignored; the score report is reproducible with
`python evals/score.py`. Costs ran on the Claude subscription token, so the
notional figures in the run log are not money spent.
