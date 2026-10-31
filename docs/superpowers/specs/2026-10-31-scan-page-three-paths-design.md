# The scan page explains the three paths (design)

Date: 2026-10-31. Owner decisions taken the same day: the mechanics live on the scan page, not on a new page;
the walkthrough keeps its pinned evidence and gains a dated banner and a link.

## Why

The owner's "From Advisory to Typology" mechanics document (a private claude.ai artifact, 2026-10-30) explains the
system better than the published demo does, and the demo has fallen behind the system:

- `scan.html` "After a person decides: two paths" predates Stage566 K3. There are THREE paths after a person decides:
  a notice that confirms a known typology (A), a new warning sign for a known typology (B), and a method NEXUS does
  not have (C). Path B is missing from the published page.
- The page shows the RESULTS of path A (the "Now" cards) but not its steps: absorb, product re-review, queue
  re-review, close, publish.
- Nothing on the site answers "what does each path change?", in particular that no detection code changes on paths A
  or B and that Python changes only at Build on path C, by engineers.
- The walkthrough (`threat-intel/index.html`) is pinned at the 2026-09-27 snapshot. Its section 10, "What this slice
  does not do yet", describes slice 1 (ingestion "being built", nothing flowing into NEXUS). Every statement is dated
  and true of that date, but a visitor reads it as the system's state today.

## What changes

### Scan page (`tools/build_scan_demo.py`, published by `tools/publish_scan_demo.py`)

1. **"After a person decides: three paths"** (anchor `#paths`) replaces the two-path figure. `three_paths_svg()`
   replaces `two_paths_svg()`, drawn with the existing `_fig_box`/`_fig_open` helpers and the existing classes.
2. **The steps of each path.** A `PATHS` constant beside `PIPELINE`, one entry per path: name, one-line question,
   and steps `{n, name, actor (AGENT|PERSON|NEXUS), built, evidence, what}`, in `PIPELINE`'s shape and checked the
   same way (a step claiming BUILT names files that must exist).
   - A: Absorb, Product re-review, Queue re-review, Close, Publish.
   - B: Compare the warning signs, Review the flag, Absorb the flag, Write it into doctrine.
   - C: `PIPELINE` itself (Spot, Decide, Propose, Define, Build, Live), retitled "Path C". The existing six-step figure
     stays and is not duplicated.
   Path C's evidence files are the existing ones. A and B's evidence names fc-08 files only (fc-10 is another
   repository): the imported `data/advisory_impact.json` and the tools that write or read it
   (`tools/import_fc10_impact.py`, `agents/compare_flags.py`, `tools/review.py`). A step fc-08 cannot evidence from
   its own tree says "recorded in NEXUS" and claims no BUILT badge of its own.
3. **Live figures per path, from data already imported.** A: corroborations, typologies, product re-reviews open and
   closed (`impact_view`). B: flags approved and in doctrine; zero reads "built, not yet used", never a blank. C: the
   pipeline counts already shown. No figure is typed into the builder.
   The fc-10 export does not carry queue re-reviews, so path A's queue step states the rule without a count.
4. **"What each path changes"**, a table with one row per path. Columns: what is recorded, where, who decides, does
   detection code change, does a case reopen. Answers: A and B change no detection code and reopen no case (a
   re-review is raised and a person closes it); C changes code only at Build, by engineers, and NEXUS refuses "live"
   without a passed release.
5. **Limits.** The existing "Next: NOT BUILT" section becomes "Known limits and what is next": the document's
   known limits and "why it can be trusted" points, as data in the builder, then the existing NOT BUILT list.

All wording lives in `PATHS`/table constants, not in `build()`'s markup, as `PIPELINE`'s does now.

### Walkthrough (`tools/build_walkthrough.py`, published by `tools/publish_walkthrough.py`)

6. A banner under the title: "Pinned at the snapshot of 2026-09-27. The scan page shows how the system runs now:
   the three paths →" linking `scan.html#paths`. The date is read from `site/walkthrough_snapshot.json`, not typed.
7. Section 10's heading becomes "What this slice did not do yet, at the snapshot of <date>". The body is unchanged.
   No re-snapshot.

## Guards (each mutation-verified, one mutation per clause)

`evals/check_scan_demo.py` gains:
- the page has an element with id `paths` and exactly three path headings, A, B and C, in that order;
- every step of every path is rendered, and a BUILT badge appears only where every evidence file exists;
- each path figure on the page equals its source (`impact_view`, the pipeline counts);
- the "What each path changes" table has one row per path, and paths A and B read "No" for detection code.

`evals/check_walkthrough.py` gains: the banner is present, carries the snapshot's date, and links `scan.html#paths`.

Mutations: drop path B; claim BUILT for a step whose evidence file is missing; change one path figure; remove the
`paths` id; change the banner's date. Each must turn exactly its clause red.

## Publishing and order

1. fc-10's absorb of 2026-10-30 lands, and fc-08 re-imports the impact export (`tools/import_fc10_impact.py`), so
   path A's figures include it.
2. Build both pages; run them in node (the scan page's replay is JavaScript) and render them at 375 px and desktop.
3. Republish both into the portfolio (owner's go), commit the portfolio, then commit fc-08 with `site/PUBLISHED`
   and `site/SCAN_PUBLISHED`. The pre-commit staleness gates refuse any other order.

## Out of scope

A separate how-it-works page; a link from the NEXUS landing page; publishing the claude.ai artifact itself (it stays
private). The walkthrough's corpus snapshot is not retaken.
