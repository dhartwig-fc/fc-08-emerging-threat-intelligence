# Known-Typology Loop K4b (Scan Page Surface) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fc-08 imports fc-10's advisory impact export one way, and the public scan page's "Next" box becomes a data-driven "Now: the advisory acts inside NEXUS" block (BUILT, with SAN006's real corroboration and RR-6) plus a "Next" strip that stays NOT BUILT.

**Architecture:** `tools/import_fc10_impact.py` copies fc-10's `indexes/advisory_impact.json` to `data/advisory_impact.json`, pinning sha256 and fc-10's commit, exactly like `import_fc10_proposals.py`. `build_scan_demo.inputs()` reads that import; a pure `impact_view()` reduces it to what the page shows; the JS renders it. The scan guard reads the import ITSELF and compares, so a builder that misreads the file cannot pass.

**Tech Stack:** Python 3 stdlib; fc-08's guard scripts (`checks()` generators, `--mutate`), `tools/check_all.py`. No new dependency.

**Spec:** fc-10's `fc-10-intelligence-repository-layer/docs/superpowers/specs/2026-10-15-known-typology-k4-surfaces-design.md` (§3 rule 2, §5, §6 fc-08, §7, §8 K4b), on fc-10 main `bbc34e2e`. This repository: branch `sdd/known-typology-k4b` from `origin/main` (`ade28fc`). fc-10 is read from the worktree `~/nexus-code/.worktrees/known-typology-loop` (call it `$FC10WT`), detached at fc-10's `origin/main`.

## Rulings this plan makes

- **K4b-R1 -- the BUILT badge is data.** Today the Next box's NOT BUILT is static HTML (`tools/build_scan_demo.py:523`). The Now block's badge renders from `payload["impact"]["built"]`, so `check_scan_demo` can pin it to the import (spec §6).
- **K4b-R2 -- a missing import is an empty import.** `inputs()` reads `data/advisory_impact.json` when present and `{"typologies": {}}` when not; the page then shows "Not yet absorbed in NEXUS" and no badge (spec §5.2). The committed import's presence is `check_impact_import`'s job, not the builder's.
- **K4b-R3 -- the diagram label is static copy.** The two-paths box becomes "Absorbed into NEXUS / Corroborate + re-review" unconditionally; on the committed page the guard forces `built` true (the import holds SAN006), so label and badge cannot disagree there.
- **K4b-R4 -- no fc-10 commit in K4b.** This plan lives in fc-08 and lands with K4b; marking the spec's §8 K4b row delivered rides the next fc-10 change. fc-10's warm currency test is mutation-verified from here (Task 1) without committing in fc-10.

## Global Constraints

- One way: fc-08 reads fc-10's file and never writes fc-10.
- No hand-typed claims in the Now block: every id, name, date and count comes from `data/advisory_impact.json`; the `FC10` constant (Global Metals Ltd / `SAN006-TRD001`) stays only as a cross-check (spec §3 rule 2).
- With no SAN006 corroboration in the import: both cards read "Not yet absorbed in NEXUS" and no BUILT badge (spec §5.2).
- `<absorbed date>` is the latest `absorbed_at` across all corroborations; `<N>` their count (spec §5.2).
- fc-08 rules: stage explicitly, never `git commit -a`; a new `evals/check_*.py` is registered in `tools/check_all.py` GUARDS and `evals/check_mutation_anchors.py` EXEMPT in the SAME commit; mutations rebind only module-level names. No Co-Authored-By trailer. Run Python as `.venv/bin/python`.
- A scan page change is published (`tools/publish_scan_demo.py`) and committed in the portfolio BEFORE the fc-08 commit, or the pre-commit staleness gate refuses.
- The owner pushes fc-08 and the portfolio.

## Review Focus

1. **fc-08's import goes stale after a `close` in fc-10** -- expected: fc-10's warm currency test fails naming the re-import command. Test: Task 1 Step 6 (planted wrong sha256 → FAIL, restore → PASS).
2. **An export whose re-review has no corroboration for its typology** -- expected: refused, nothing written. Test: Task 1 check `"convert refuses an orphan re-review"` and mutation `orphan-rereview`.
3. **The page claims BUILT from an empty import** -- expected: the scan guard fails. Test: Task 2 mutation `built-without-import`.
4. **The page shows a re-review that is not the import's** -- expected: the scan guard fails. Test: Task 2 mutation `wrong-rereview`.
5. **RR-6 closes and fc-08 re-imports** -- expected: the Now card reads "closed <date> · <outcome>" and the totals move, with no code change. Test: Task 2 check `"impact_view shows a closed re-review as closed"`.

---

### Task 1: the one-way import and its guard

**Files:**
- Create: `tools/import_fc10_impact.py`, `evals/check_impact_import.py`, `data/advisory_impact.json` (generated)
- Modify: `tools/check_all.py` (GUARDS, beside `check_proposals_import`), `evals/check_mutation_anchors.py` (EXEMPT, beside `check_proposals_import.py`)

**Interfaces:**
- Produces: `import_fc10_impact.OUT = ROOT / "data" / "advisory_impact.json"`; `RR_ID = re.compile(r"^RR-\d+$")`; `convert(path: Path) -> dict` returning `{"version": "fc10-<short commit>", "source": {"repository": "fc-10-intelligence-repository-layer", "file": "indexes/advisory_impact.json", "sha256": <64 hex of the raw bytes>, "event_count": <export head.event_count>}, "note": ..., "typologies": {TYP: {"corroborations": [... sorted by advisory_id], "rereviews": [... sorted by int(id[3:])]}}}`; refuses with `SystemExit` naming the offenders: `"not re-review ids: [...]"`, `"re-reviews with no corroboration: [TYP, ...]"`. `main(argv) -> int` (wrong usage → 2, missing file → 2).
- `check_impact_import.problems(doc: dict) -> list[str]`.

- [ ] **Step 1: Write the guard** `evals/check_impact_import.py`, modelled on `evals/check_proposals_import.py` (same docstring shape, `MUTATIONS`, `checks()` generator of `(ok, name, detail)`, argparse `--mutate`, COLD; it imports `import_fc10_impact as imp` via `sys.path.insert(0, ROOT / "tools")`). `_synthetic()` returns an export with two typologies, re-review ids out of order (`RR-2` listed before `RR-1`), and one closed re-review. `problems(doc)` flags: an id not matching `RR_ID`; a typology with re-reviews and no corroborations; a corroboration with no quotes; `source.sha256` not 64 hex; `source.event_count` not an int. `checks()` yields:
  - `"the committed import is well formed"` -- `problems(committed) == []` and `committed["typologies"]` non-empty (pass-by-nothing refused)
  - `"convert produces a well-formed import"` -- over `_synthetic()`
  - `"convert sorts re-reviews by number"` -- the synthetic typology's ids come out `["RR-1", "RR-2"]`
  - `"convert is independent of export order"` -- converting a copy with every list reversed gives equal `typologies`
  - `"convert refuses an orphan re-review"` -- a synthetic typology with re-reviews and no corroborations raises `SystemExit`

  `MUTATIONS = ("bad-rr-id", "orphan-rereview", "hash-drift", "not-deterministic")`: `bad-rr-id` sets a synthetic id to `"RR-x"` before converting; `orphan-rereview` empties one typology's corroborations in the converted dict (so `problems` sees it); `hash-drift` sets `out["source"]["sha256"] = "x"`; `not-deterministic` reverses the second conversion's re-review list.

- [ ] **Step 2: Run** `.venv/bin/python evals/check_impact_import.py; echo rc=$?` → Expected: `ModuleNotFoundError: No module named 'import_fc10_impact'`, rc != 0.

- [ ] **Step 3: Implement** `tools/import_fc10_impact.py` to the Interfaces, mirroring `import_fc10_proposals.py` (same `_commit`, same write with `indent=2, ensure_ascii=False, sort_keys=True`). Summary line: `"Wrote advisory_impact.json: <T> typologies, <C> corroborations, <R> re-reviews from <version> (<sha12>)"`. Note: `"Governed export from fc-10's advisory impact ledger. Regenerate with tools/import_fc10_impact.py; never hand-edit."`

- [ ] **Step 4: Import from fc-10 main and run the guard:**

```bash
FC10WT=~/nexus-code/.worktrees/known-typology-loop; git -C $FC10WT fetch -q && git -C $FC10WT status --short | wc -l && git -C $FC10WT checkout -q --detach origin/main && cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python tools/import_fc10_impact.py $FC10WT/fc-10-intelligence-repository-layer/indexes/advisory_impact.json && .venv/bin/python evals/check_impact_import.py; echo rc=$?
```

Expected: the status count is `0` (refuse to detach a dirty worktree); `Wrote advisory_impact.json: 6 typologies, 6 corroborations, 6 re-reviews from fc10-bbc34e2 (...)`; every check ok; rc 0.

- [ ] **Step 5: Mutations** -- each MUST fail:

```bash
for m in bad-rr-id orphan-rereview hash-drift not-deterministic; do .venv/bin/python evals/check_impact_import.py --mutate $m >/dev/null 2>&1; echo "$m rc=$?"; done
```

Expected: every rc != 0.

- [ ] **Step 6: Mutation-verify fc-10's warm currency test** (spec §6; the K4a ledger carried it):

```bash
cd $FC10WT/fc-10-intelligence-repository-layer && python3 -m pytest -q -p no:cacheprovider tests/advisory_impact/test_fc08_impact_import_is_current.py; echo pass-rc=$?
```

Expected: 1 passed. Then copy fc-08's `data/advisory_impact.json` aside, set its `source.sha256` to 64 zeros, re-run → 1 FAILED with "fc-08's advisory impact import is stale"; restore the copy and sha-check it → 1 passed. Ledger both outputs. Nothing is committed in fc-10 (K4b-R4).

- [ ] **Step 7: Register and commit.** `tools/check_all.py` GUARDS gains `("check_impact_import", ["evals/check_impact_import.py"], "cold"),`; `evals/check_mutation_anchors.py` EXEMPT gains `"check_impact_import.py": "--mutate perturbs a synthetic export or the converted dict in memory",`.

```bash
cd ~/fc-08-emerging-threat-intelligence && git add tools/import_fc10_impact.py evals/check_impact_import.py data/advisory_impact.json tools/check_all.py evals/check_mutation_anchors.py docs/superpowers/plans/2026-10-16-known-typology-k4b.md && git commit -m "Stage566 K4b: import fc-10's advisory impact export one way, pinned; its guard"
```

Expected: the pre-commit hook runs every guard, one more than before, and passes.

---

### Task 2: the Now/Next blocks, the diagram label, and the scan guard

**Files:**
- Modify: `tools/build_scan_demo.py` (constant, `inputs()`, new `impact_view()`, `payload()`, the `<section class="next">` HTML, its JS, `two_paths_svg()`), `evals/check_scan_demo.py` (truth, checks, two mutations, docstring), `site/scan-demo/index.html` (rebuilt), `site/SCAN_PUBLISHED` (republished)
- Portfolio: `projects/nexus/threat-intel/scan.html`

**Interfaces:**
- Consumes: Task 1's `data/advisory_impact.json` shape.
- Produces: `build_scan_demo.IMPACT_IMPORT = ROOT / "data" / "advisory_impact.json"`; `inputs()["impact"]` (the parsed import, or `{"typologies": {}}` when absent -- K4b-R2); `impact_view(impact: dict) -> dict` with keys `built: bool` (a corroboration for `CORROBORATES[0]` exists), `absorbed_on: str` (latest `absorbed_at[:10]` across all corroborations, `""` when none), `corroborations: int`, `typologies: int` (with ≥1 corroboration), `rereviews: int`, `open: int`, `doctrine: dict | None` (the `CORROBORATES[0]` corroboration whose `advisory_id == ADVISORY`, else its first; fields `advisory_id, publisher, decided_at, quotes`), `rereview: dict | None` (the first `CORROBORATES[0]` re-review; fields `id, subject, case_id, status, outcome, raised_at, closed_at`); `payload()["impact"] = impact_view(inp["impact"])`.

- [ ] **Step 1: Write the guard additions** in `evals/check_scan_demo.py`. `_truth()` reads `data/advisory_impact.json` itself with `json.loads` (never through `bs.inputs()`), into `T["impact"]`. New checks in `checks()`:
  - `"the Now block is BUILT exactly when the import holds a SAN006 corroboration"` -- `P["impact"]["built"] == bool(<truth SAN006 corroborations>)`, and that is `True` for the committed import
  - `"the Now block's re-review is the import's"` -- `P["impact"]["rereview"]` equals the truth's first SAN006 re-review on all seven fields
  - `"the Now block's totals are the import's"` -- `corroborations`, `typologies`, `rereviews`, `open`, `absorbed_on` each equal values computed here from the truth
  - `"the declared FC10 case is the import's SAN006 re-review"` -- `bs.FC10["subject"]` and `["case_id"]` equal the truth's SAN006 re-review `subject` and `case_id`
  - `"impact_view shows a closed re-review as closed"` -- `bs.impact_view` over a deep copy of the truth with the SAN006 re-review set to `status="closed", outcome="unchanged", closed_at="2026-10-20T09:00:00"` returns that status and `open` one lower
  - `"an empty import builds no BUILT claim"` -- `bs.impact_view({"typologies": {}})` has `built False`, `doctrine None`, `rereview None`

  Append to `MUTATIONS`: `"built-without-import"` (`_mutated_inputs`: `inp["impact"] = {"typologies": {}}`) and `"wrong-rereview"` (the SAN006 re-review's `subject = "Someone Else Ltd"`). Add both to the docstring's usage list, and to WHAT IT CHECKS the line `impact       the Now block equals data/advisory_impact.json, read here; BUILT only with a SAN006 corroboration`.

- [ ] **Step 2: Run** `.venv/bin/python evals/check_scan_demo.py; echo rc=$?` → Expected: the new checks fail (`KeyError: 'impact'` from the payload), rc != 0.

- [ ] **Step 3: Implement the builder.** `IMPACT_IMPORT` beside `PROPOSALS_IMPORT`; `inputs()["impact"]` per K4b-R2; `impact_view()` per Interfaces; `payload()["impact"]`. Replace the whole `<section class="next" ...>...</section>` (spec §5.2 copy is fixed) with:

```html
<section class="next" aria-label="Now: the advisory acts inside NEXUS">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px"><h2>Now: the advisory acts inside NEXUS</h2><span id="nowBadge"></span></div>
<p class="sub" style="color:var(--muted)" id="nowSub"></p>
<div class="grid2" style="gap:14px">
<div class="dash" id="nowDoctrine"></div>
<div class="dash" id="nowCase"></div>
</div>
<p class="note" id="nowTotals"></p>
</section>

<section class="card" aria-label="Next capability">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px"><h2>Next</h2><span class="nb">NOT BUILT</span></div>
<ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--fg-2)">
<li><b>New red flags:</b> an agent compares the advisory with the typology's red flags; a person approves genuinely new ones.</li>
<li><b>Cases on the desk:</b> re-review the queue cases of the typology, not only its product.</li>
</ul>
</section>
```

  The JS replacing the `nextDoctrine`/`nextCase` lines renders from `P.impact`, every value through `esc`, dates as `15 Oct 2026` from the first 10 characters:
  - `nowBadge`: `<span class="built">BUILT</span>` when `built`, else empty
  - `nowSub`: when built, `"On <absorbed_on> the owner absorbed <corroborations> approved advisory links. Each corroborates its typology and puts its product up for re-review. Nothing reopens a case or edits doctrine on its own."`; else `"Not yet absorbed in NEXUS."`
  - `nowDoctrine`: header `<advisory_id> → <SAN006> doctrine`; bold `Corroborated`; each quote with `(p. N)`; `<publisher> · approved <decided_at date>`; link to `F.doctrine_page`. Or `Not yet absorbed in NEXUS`
  - `nowCase`: header `<SAN006> → product re-review`; bold `<id> · <subject> (<case_id>)`; `requested <raised_at date> · open` or `· closed <closed_at date> · <outcome>`; link to `F.case_page`. Or `Not yet absorbed in NEXUS`
  - `nowTotals`: `"Across NEXUS: <typologies> typologies corroborated · <rereviews> re-reviews (<open> open)"`, empty when not built

  In `two_paths_svg()`, `_fig_box(60, 384, 260, "Routed to its desk", "Next: corroborate, re-review")` becomes `_fig_box(60, 384, 260, "Absorbed into NEXUS", "Corroborate + re-review")`, and the docstring's last sentence says the known path is absorbed (K4b-R3).

- [ ] **Step 4: Rebuild and run:** `.venv/bin/python tools/build_scan_demo.py && .venv/bin/python evals/check_scan_demo.py; echo rc=$?` → Expected: every check ok, rc 0. Then:

```bash
for m in built-without-import wrong-rereview; do .venv/bin/python evals/check_scan_demo.py --mutate $m >/dev/null 2>&1; echo "$m rc=$?"; done; .venv/bin/python tools/build_scan_demo.py --check
```

Expected: both rc != 0; `HOLDS: site/scan-demo/index.html is a fresh build`.

- [ ] **Step 5: Look at it.** Start `fc08-site` from `~/nexus-code/.claude/launch.json` and open `http://localhost:8790/scan-demo/index.html`. At desktop and at 375px width: the Now block shows BUILT, the ADV-2026-0026 quote, `RR-6 · Global Metals Ltd (SAN006-TRD001)`, `requested 15 Oct 2026 · open`, and `6 typologies corroborated · 6 re-reviews (6 open)`; the Next strip shows NOT BUILT; the two-paths diagram reads "Absorbed into NEXUS"; at 375px `document.documentElement.scrollWidth == innerWidth`. Screenshot both widths.

- [ ] **Step 6: Publish, then commit both repositories** (the staleness gate forces this order):

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python tools/publish_scan_demo.py --portfolio ~/"Cowork HB/dan-hartwig-portfolio" && cmp ~/"Cowork HB/dan-hartwig-portfolio/projects/nexus/threat-intel/scan.html" site/scan-demo/index.html && git -C ~/"Cowork HB/dan-hartwig-portfolio" add projects/nexus/threat-intel/scan.html && git -C ~/"Cowork HB/dan-hartwig-portfolio" commit -m "Scan demo: Now -- the advisory acts inside NEXUS, BUILT from fc-10's advisory impact ledger (fc-08 Stage566 K4b)"
git add tools/build_scan_demo.py evals/check_scan_demo.py site/scan-demo/index.html site/SCAN_PUBLISHED && git commit -m "Stage566 K4b: the scan page's Now block is BUILT from the imported advisory impact export; Next stays NOT BUILT"
```

Expected: `cmp` silent; the fc-08 pre-commit hook passes every guard.

---

### Task 3: land and go live

- [ ] **Step 1:** The owner pushes `sdd/known-typology-k4b` (fc-08) and the portfolio. fc-08's CI run on the head must conclude `success`.
- [ ] **Step 2:** `git fetch origin && git merge-base --is-ancestor origin/main <head>` must succeed; then `git push origin <head>:main`. If main moved: merge it, re-run Task 2 Step 4's checks, return to Step 1.
- [ ] **Step 3:** Live check: `curl -s https://dhartwig-fc.github.io/dan-hartwig-portfolio/projects/nexus/threat-intel/scan.html | grep -c "Now: the advisory acts inside NEXUS"` → 1, once GitHub Pages has built the portfolio commit.
- [ ] **Step 4:** Update memory `stage566-known-typology-loop.md`: K4b landed (fc-08 main sha, portfolio sha); the scan diagram's "flip it when K4 lands" note is done; after any `close` or `absorb` the full rule is four steps (rebuild and republish the KC pages with the fc-10 manifest, re-import in fc-08, republish the scan page).
