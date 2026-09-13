# Single agent versus multi-agent: the honest comparison

Week 4's deliverable, as `PLAN.md` words it: *"an honest comparison of single
versus multi-agent."*

The honest version is that **one extra agent was built instead of four, and three
of the four the plan specified were not built because measurement had removed the
problems they addressed.** What follows is what each would have done, what the
evidence said about it, and what the one that was built actually bought.

## What the plan asked for

> Split the pipeline into four roles: **fetcher** (PDF to pages plus hash),
> **extractor** (record), **classifier** (typology resolution through MCP),
> **reviewer** (checks citations exist in the text and flags emergent
> candidates). Implement as subagents under one orchestrator.

The plan was written in week 0, before anything about this pipeline had been
measured. By the time week 4 began, three weeks of measurement had changed what
the problem was.

## Station by station

### fetcher — NOT BUILT, and it should not be an agent

`pdf_to_pages()` is twelve lines of `pypdf` plus a sha256. It is deterministic,
it works, and it has never failed in 90+ runs. Wrapping it in a model call adds
latency, cost and a failure mode and buys nothing.

This is not a close call, and there is direct evidence from the same week. Three
subagents launched on 2026-09-12 to supervise batch work died on the session
limit **having produced nothing at all**. Everything shares one quota meter —
this session, each agent's reasoning, every extraction — so an agent supervising
deterministic work spends tokens competing with the work it supervises. The
fourteen remaining extractions were then completed by a plain resumable bash
script, first time.

### classifier — NOT BUILT, because retrieval is not the constraint

A separate classifier station exists to do typology resolution well. Measured
three ways, resolution is not where recall goes:

| measurement | result |
|---|---|
| search length-invariance fix, 8 runs either side | tool top-5 recall 0.351 → 0.496; extraction recall **unchanged**, bands overlapping |
| trace, SAN006 on ADV-2026-0016 | retrieved at rank 3, confirmed with `get_typology`, then **not asserted** |
| full set, 20 advisories | the agent asserts ~4.5 typologies whether the document holds 5 or 20 (correlation +0.22) |

A station that resolves typologies better cannot help an agent that already
retrieved the answer and declined to use it.

### reviewer — BUILT, but not the reviewer specified

The plan's reviewer *"must reject any fact whose quote is not found verbatim in
the page text"*. `evals/check_citations.py` already does exactly that,
mechanically, and all 624 citations in the golden set pass it. Building it would
duplicate a passing guard.

Worse, it would SUBTRACT, and subtraction was the problem. Every mechanism built
in weeks 1-3 removes or refuses: `tools=[]` removes capability, `propose_link`
refuses an unjustified twin, the search floor refuses a weak match,
`_refuse_unknown_ids` raises. That is why precision stood at 0.889 and recall at
0.357. A fifth refusal would not have moved the number week 4 existed to move.

So the reviewer built asks the opposite question — *what did the extraction
miss?* — under a justification burden, and merges its additions under schema
1.4.0 with the reasoning attached.

### orchestrator — NOT BUILT

Two stages in a fixed order need a shell loop, not an orchestrator. There is no
routing decision to make.

## What the one extra agent bought

All 20 advisories, extraction-only against extraction + reviewer merged:

| field | single agent | two stages | change |
|---|---|---|---|
| typologies | P 0.889 · R 0.357 · **F1 0.510** | P 0.853 · R 0.545 · **F1 0.665** | **+0.155** |
| emergent | P 0.647 · R 0.200 · F1 0.306 | P 0.571 · R 0.255 · **F1 0.352** | +0.046 |
| actors | 0.692 | 0.692 | — |
| jurisdictions | 0.730 | 0.730 | — |

Acceptance was on bands, not a single run: three repeats across the four
documents where misses concentrate gave F1 0.349 → 0.514-0.553, no overlap.

Actors and jurisdictions are unchanged because the reviewer is scoped to
typologies. That is a limit, not an oversight — actors already run at recall
0.684 and were never the gap.

## What it cost

| stage | runs | mean cost | mean turns | mean duration |
|---|---|---|---|---|
| extraction | 14 | $0.73 | 33.9 | 270 s |
| reviewer | 27 | $0.48 | 29.1 | 159 s |

**The second stage costs about two-thirds of the first and takes about 60% of the
time.** So the two-stage pipeline is roughly 1.65x the cost of one agent for
+0.155 F1 on its primary field. On the Claude subscription the marginal money
cost is zero and the real currency is wall clock and quota.

Worth noting the extractor got CHEAPER during week 4 for an unrelated reason:
removing its built-in tool surface (`tools=[]`) took one advisory from 33 turns
and $0.75 to 16 turns and $0.24. An agent that can see thirty tools spends turns
considering them.

## The verdict

**One agent with good tools beat a swarm — and then one carefully chosen second
agent beat one agent.** `PLAN.md`'s own Learn section anticipated the first half:
*"When one agent with good tools beats a swarm."*

The distinction that matters is not how many agents but **whether each one
addresses a measured constraint**. Three of the four planned stations addressed
problems that measurement had ruled out; the fourth addressed a real one but in
the wrong direction. Building all four would have cost roughly four times the
tokens to move the number by approximately nothing, and it would have looked like
progress.

## What would justify more agents

Stated so the decision can be revisited on evidence rather than taste:

- **A routing decision a model must make.** If advisories arrived from mixed
  sources needing different handling, a classifier choosing the path would earn
  its place. Today the path is fixed.
- **A genuinely parallel workload with independent failure.** The reviewer and
  extractor are sequential by construction: the reviewer needs the record.
- **A second opinion whose disagreement is informative.** An adversarial reviewer
  from a different model family would break the correlation that makes
  Claude-drafted, Claude-reviewed labels the standing caveat on every figure
  here. That is the strongest remaining case for another agent, and it is about
  independence rather than throughput.

## Caveat

Sixteen of the twenty reviewer runs are SINGLE runs; only the four concentrated
documents carry bands. The cost figures come from 14 extraction runs and 27
reviewer runs recorded during week 4, not from a full 20 x 2 matrix.
