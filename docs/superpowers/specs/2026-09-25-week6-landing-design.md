# Week 6 design: landing slice 1

Date: 2026-09-25. Status: approved section by section in chat; awaiting owner
review of this written form before a plan is written.

PLAN.md's week 6 asks for five things: a Threat Intelligence entry on
`future-capabilities.html` mirroring the SAR Drafter, a walkthrough page, a
release tag, an engineering-journal entry and a LinkedIn-length summary. Its
deliverable: *a public, governed, shipped capability with a score, a walkthrough
and a release tag.* Week 5 also deferred four items here.

The measurements below changed the shape of all five.

## What was measured, 2026-09-25

| Item | Measured | Consequence |
|---|---|---|
| Definition of done (PLAN.md §5) | One clause is unbuilt: the server has list, get, search and propose tools, and no **resolve** tool. Two boxes are unmeasured: "zero uncited facts in the final batch" and "golden set with **published** precision and recall" (no score is published anywhere). | `resolve_actor` is built this week, and every box is measured before the tag. |
| Actors in the golden set | 158: 70 category, 52 organisation, 19 network, 17 person. All are real parties named in public government publications; none is an fc-10 entity (fc-10's estate is synthetic by rule). | Resolving against fc-10's `entity_key` would score near 0 by construction. Resolution is cross-advisory identity, with `entity_key` as an empty seam. |
| Automation | fc-08 has no CI, no `core.hooksPath` and nothing in `.git/hooks`. | "Run `--check` automatically" means building the mechanism. |
| Repository visibility | fc-08 is PUBLIC on GitHub. The advisory PDFs are gitignored (third-party publications). | Guards that re-find quotes on PDF pages cannot run cold. A committed draft is already published, so the LinkedIn draft does not live here. |
| Portfolio pages | `future-capabilities.html` and `walkthrough.html` are hand-edited prose with no publisher and no gate. The SAR drafter's line links a GENERATED page (`runtime-demo/sar_drafts.html`) that has both. | Prose stays hand-edited; anything quoting generated content gets a publisher and a staleness gate. |
| The walked advisory | ADV-2026-0013, the OFAC/BIS/DOJ Tri-Seal note on third-party intermediaries: 6 pages, a US government work, the only advisory with owner decisions (5 approvals). Run `f617bd3b00` proposed the approved links; run `69eeab7b41` has telemetry. | One advisory, two runs, each named where it is used. |
| Journal | `~/fc_vision_notes_dhartwig` holds the FC08 entries (latest `06-development-journals/2026-09-13_FC08_TRACING_THE_RECALL_GAP.md`). The `Cowork HB` checkout of the same repo stops in June. | The entry goes in the `~` checkout. |
| Tags | fc-08 has none. | `fc08-threatintel-slice1-v1.0.0` is its first. |

## Decisions taken in the design conversation

1. Three sub-projects, hardening first, then publish, then release.
2. `resolve_actor` is built in sub-project 1, so every definition-of-done box can be audited before publish.
3. It resolves against a governed register of the named actors, with `entity_key` as a seam left empty until a real substrate link exists.
4. The walkthrough is generated in fc-08, published by a script, and gated both ways.
5. Checks run automatically in two places: a local pre-commit hook runs everything, and CI runs the guards that work cold and names the rest as NOT RUN.

## Build order

- **Sub-project 1. Hardening and `resolve_actor`** (Sections 1 to 5). The published digest must come from a batch that can be re-checked, and the published actor section needs the register.
- **Sub-project 2. The publish** (Sections 6 to 10). Reads what sub-project 1 produces.
- **Sub-project 3. The release** (Sections 11 to 14). Runs after sub-project 2 is live, so the tag marks the published state.

Each sub-project gets its own plan.

---

## Sub-project 1: hardening and `resolve_actor`

### Section 1: a batch pins its inputs

`tools/build_digests.py` writes `data/digests/<batch_id>/manifest.json` beside the desk files:

```json
{
  "batch_id": "slice1-2026-09-24",
  "decision_log": {"lines": 5, "sha256": "<sha256 of those lines, bytes as stored>"},
  "records":   {"ADV-2026-0001.json": "<sha256>", "...": "..."},
  "proposals": {"adv-2026-0013-extractor-f617bd3b00.jsonl": "<sha256>", "...": "..."}
}
```

The manifest names inputs by role and filename only, never by path. That matters because of
`check_review_gate`'s writer scan, which requires that nothing outside `governance/decisions.py` names
the decision log's file (a ruling from week 5's sub-project C).

`--check` does three things in order:

1. **It reads the first `lines` lines of the decision log.** Their hash must equal the pinned hash. The log is append-only, so that prefix never changes. If it has changed, the log was edited, and the check fails naming it.
2. **It compares every pinned record and queue file with its hash.** If one has moved, it prints `inputs moved since this batch: <file>` and exits 1. That tells you to cut a new batch, not that something is broken.
3. **It rebuilds from the pinned log prefix and the current records and queue**, then compares the result with the committed desk files. A difference here, with inputs unchanged, prints `same inputs, different output: <desk>`. That is a defect in the renderer.

A new record or queue file that did not exist when the batch was built is not an input to it and is
ignored by `--check`.

**The existing batch `slice1-2026-09-24` gets its manifest back-filled.** A back-fill mode writes a manifest
only when a fresh build from the current inputs matches the committed desk files byte for byte. It refuses
otherwise. Measured on 2026-09-25, the inputs are unchanged since the batch was built.

### Section 2: a batch is never overwritten

`build_digests` without `--check` refuses when `data/digests/<batch_id>/` already exists, exit 2, saying so.
A new state needs a new batch id. There is no `--force`: a committed batch is evidence (guardrail 5 in the
estate's terms).

### Section 3: the server binds its queue path

`propose_link` derives the queue path as `data/proposals/<NEXUS_RUN_ID>.jsonl` and refuses when
`NEXUS_PROPOSALS_PATH` resolves to anything else. The refusal names both paths by filename. The environment
variable stays, because `RunIdentity.env()` sets it and a mismatch is exactly what should be caught, but it
can no longer redirect a write. `check_proposal_contract` gains a check that a mismatched path is refused
and writes nothing, and that check must be watched failing against the current code first.

### Section 4: the checks run automatically

**`tools/check_all.py`** is one list, each entry being a command and a class:

| Class | Meaning | Examples |
|---|---|---|
| `cold` | runs from a fresh clone | candidates, to be confirmed by running each in a fresh clone: `check_digest_routing`, `check_emergent_threshold`, `check_added_by`, `check_actor_resolution`, `build_digests --check`, `actor_resolution --check` |
| `needs-pdfs` | re-finds quotes on gitignored PDF pages | candidates: `check_review_gate`, `review.py --check`, `check_citations`, `check_proposal_contract`, `check_telemetry`, `check_tool_surface` (static), `check_twin_pairs` |
| `needs-portfolio` | reads the portfolio checkout (added in Section 9) | `check_published_walkthrough` |

- `--cold` runs the `cold` entries and prints every other entry as `NOT RUN (<class>): <name>`.
- The default runs everything and fails if a `needs-pdfs` input is missing, rather than skipping it.
- It exits non-zero on any failure.
- Each guard's class is MEASURED, not read from its source: run it in a fresh clone (no gitignored files). It is `cold` only if it passes there.

**Every `evals/check_*.py` must appear in the list.** The runner globs them and fails if one is unlisted. A
new guard therefore cannot be silently left out. The same filename-convention lesson as fc-10's 429E applies:
the glob and the list are compared both ways.

**`scripts/hooks/pre-commit`** runs `python tools/check_all.py`. It is set up once per clone with
`git config core.hooksPath scripts/hooks`, written into `setup.sh` and CLAUDE.md. No `--no-verify`, ever.

**`.github/workflows/checks.yml`** runs `pip install -r requirements.txt` and then `python tools/check_all.py --cold` on
every push and pull request. The log shows each NOT RUN line, so a green run says exactly what it did not cover.

### Section 5: `resolve_actor`

> **Amended 2026-09-25, before the plan, on measurement.** This section first had the tool resolve on
> containment >= `DEFAULT_ACTOR_THRESHOLD` (0.60), importing the scorer's constant so the two could not drift.
> Measured over the extractor's 105 named actors against a register built from the golden labels: 72 resolve
> on an exact name or alias, 5 more only through containment, 28 not at all. **Four of the five containment
> resolutions were wrong**: "Iran" and "Islamic Republic of Iran" to Islamic Republic of Iran Shipping Lines,
> "Syria" to the Iran-Syria oil procurement network, "Company X" to National Iranian Oil Company. Only ISIL was
> right. Register pairs at >= 0.60 are mostly different parties too: National Iranian Oil vs National Iranian
> Tanker Company (0.75), GCM Exchange vs Berelian Exchange (0.80), the Orekhov and Grinin procurement networks
> (0.67). And one EXACT alias merge was wrong: IRGC and IRGC-Qods Force, two actors in ADV-2026-0010's own
> label, collapse through a shared alias.
>
> Containment divides by the SHORTER name. That suits scoring (is this the actor I labelled in THIS advisory,
> among a handful) and fails identity (a one-word "Iran" is wholly contained in every name carrying it). Scoring
> and identity share the normaliser, not the threshold. Owner decision 2026-09-25: option (a) of three.

**Shared normalising code.** `norm`, `tokens`, `containment` and the `_STOP` list move from `evals/score.py` to
`schemas/actor_match.py`, and `score.py` imports them (its existing callers keep working through `sc.norm`,
`sc.tokens`, `sc.containment`). The server must not import from `evals/`, and there must be one normaliser. The
scorer's thresholds stay in `score.py`: they are scoring constants, and the resolver uses neither. The golden
set's self-score must still be 1.000 on all four fields after the move.

**The register.** `tools/build_actor_register.py` builds `data/actor_register.json` (tracked) from the golden
labels' named actors: `organisation`, `person` and `network`, with categories excluded.

```json
{
  "actor_id": "ACT-0001",
  "name": "AO PKK Milandr",
  "actor_type": "organisation",
  "aliases": ["Milandr"],
  "named_in": [{"advisory_id": "ADV-2026-0013", "name_as_labelled": "AO PKK Milandr"}],
  "entity_key": null
}
```

- Entries merge **only on an exact normalised name or alias match, and only across advisories**. Measured: three
  real merges (Sinaloa cartel in 0004 and 0011; National Iranian Oil Company in 0010 and 0012; IRGC-Qods Force in
  0010 and 0012).
- **Two actors from the same advisory never merge**, even on an exact alias: the label counted them as two. The
  pair goes to `data/actor_register_candidates.json` with reason `same advisory`.
- Pairs with containment >= 0.60 and no exact match also go to the candidates file, with their score and reason
  `similar names`. They are never merged automatically. Two names being one party is an identity claim, and
  identity claims are the owner's (the same rule as fc-10's `shared_id_declarations.json`).
- Ids are assigned in a deterministic order (by first advisory id, then name) so a rebuild is byte-identical.
  `--check` proves it.

**The tool.** `knowledge_centre_resolve_actor(name: str, actor_type: str | None)` is read-only.

- `resolved`: an exact normalised match to exactly one entry's name or alias. It returns `actor_id`, the
  register name and the spelling that matched.
- `ambiguous`: an exact match to more than one entry. It lists them and resolves none.
- `unresolved`: no exact match. It returns up to three **suggestions** with containment >= 0.60 and their scores,
  labelled as suggestions a human must confirm. A suggestion is never a resolution.
- A `category` never resolves, and the tool says so.
- It is added to `READ_ONLY_TOOLS`. `check_tool_surface`'s expected surface gains it, and a check asserts it is
  pre-approved and read-only.

**The measurement.** `evals/actor_resolution.py` resolves every actor in the **extractor's** records
(`data/records/`), not the labels, so building the register from the labels is not circular. It reports:

- named actors resolved / named actors, overall and per advisory (measured before the build: 72 of 105);
- how many unresolved actors carry a suggestion, and each suggestion, so a reader can see what containment
  would have claimed;
- categories, counted separately and never in the denominator.

`--check` compares the report with a committed `evals/actor_resolution.json`.

**Guard: `evals/check_actor_resolution.py`**, over the real register and records, with mutations:
- `--mutate containment`: suggestions count as resolutions. Must be caught by a check that "Iran" in
  ADV-2026-0012's record does NOT resolve to Islamic Republic of Iran Shipping Lines.
- `--mutate same-advisory`: the builder merges exact matches within one advisory. Must be caught by a check that
  IRGC and IRGC-Qods Force are separate entries.
- `--mutate category`: a category may resolve. Must be caught.

Non-vacuous checks: at least one real cross-advisory merge exists (three are expected), at least one `ambiguous` or
`same advisory` case is exercised, and the resolved count is above zero. It must not pass by finding nothing.

No live model runs are needed for sub-project 1.

---

## Sub-project 2: the publish

### Section 6: the page

`tools/build_walkthrough.py` renders `site/threat-intel/index.html` (tracked) from committed inputs only. It
has ten sections:

1. **Question**: Question ↓ Capability ↓ Intelligence Produced ↓ Investigator Outcome, for this advisory.
2. **Source**: title, publisher, date, URL, page count and the PDF's sha256, which every later citation is pinned to.
3. **Extraction**: each typology in the record with its page and verbatim quote.
4. **Grounding**: each `propose_link` from run `f617bd3b00`, with the quote re-found on its page when proposed.
5. **Review gate**: the card `governance/card.py` renders for each decided link, and the 5 decision lines, rendered from the tool's own output. There are no screenshots: a PNG of a terminal cannot be re-checked.
6. **Actors**: each named actor resolved to its `ACT-` id or shown unresolved with any suggestion labelled as one, and each category shown as not resolvable. The `entity_key` seam is shown empty, with the reason: the estate the platform resolves against is synthetic, and a real designation will never name a synthetic party.
7. **Digest**: the sanctions desk's ADV-2026-0013 block from batch `slice1-2026-09-24`, stating the decision-log line count it was pinned to.
8. **Telemetry**: tool calls, terminal outcomes and the reconcile verdict for run `69eeab7b41`.
9. **Score**: the 20-advisory precision, recall and F1 as bands from the repeats, never one run's figure. This is where the golden set's score is published.
10. **Limits**: what slice 1 does not do, stated plainly.

It carries the NEXUS shield and wordmark, uses `walkthrough.html`'s colour tokens, has a dark mode, and works
at phone width. `--check` proves the committed page equals a fresh build. Every number on the page comes from
an input file; none is typed into the builder.

### Section 7: the boundary

`governance/publish_boundary.py` refuses a page containing any of these:
- absolute or home paths (`/Users/`, `~/`, a drive letter);
- repo-internal names (`.jsonl`, `review_decisions`, `data/`, `.superpowers`, `.venv`);
- email addresses.

It returns the offending substrings. It is fc-08's own module: importing fc-10's `internal_references` would
make a public repository depend on a sibling checkout.

It is mutation-verified by planting a reference into an INPUT that survives into the page, not into the built
file. fc-10 learned that a publisher which rebuilds overwrites a plant made in its output, and the guard then
passes honestly. A second mutation makes the publisher skip the boundary call, and must be caught.

### Section 8: the publisher

`tools/publish_walkthrough.py`:
1. rebuilds;
2. requires `build_walkthrough --check` to pass;
3. runs the boundary;
4. copies to `<portfolio>/projects/nexus/threat-intel/index.html`.

The portfolio root comes from `NEXUS_PORTFOLIO` (default `~/Cowork HB/dan-hartwig-portfolio`) and must already
exist. The publisher creates only `projects/nexus/threat-intel/`. It never commits or pushes the portfolio.

### Section 9: the staleness gate

`evals/check_published_walkthrough.py` asks whether the published copy is byte-identical to the committed
build. It is class `needs-portfolio` in `check_all`. It must be watched failing against a published copy with
one byte changed.

### Section 10: `future-capabilities.html`

It is hand-edited prose, with no generated content:
- The note line: threat intel **built** (slice 1).
- The Track 2 header: `Built · slice 1`, as the SAR drafter's pill.
- The "In build, week 4 of 6" callout is rewritten to what was delivered, with a link to `threat-intel/`.
- The four pieces at their delivered depth:
  - advisory overlay: built;
  - actor intel: a register and resolution, with the `entity_key` seam named as open;
  - emergent loop: candidates and owner approval;
  - digest: 7 desks.

Every number in the edit must appear on the walkthrough page.

**Nothing reaches the public site without the owner's go on the day.** The sequence:
1. Build, check and commit in fc-08.
2. Publish into the portfolio working tree.
3. Show the rendered page in the browser pane, at phone and desktop widths.
4. Push the portfolio only when told.

---

## Sub-project 3: the release

### Section 11: the definition-of-done audit

`docs/RELEASE_SLICE1.md` in fc-08 has one row per box in PLAN.md §5: the box, the command that proves it,
and the output at the commit to be tagged. "Zero uncited facts in the final batch" is measured with
`check_citations` over all 20 records.

A failing box is recorded as failing and brought to the owner before any tag. The record is never
adjusted to make a box pass. PLAN.md's boxes are ticked only from this evidence.

### Section 12: the tag

An annotated `fc08-threatintel-slice1-v1.0.0` on fc-08 `main`, at the commit carrying `RELEASE_SLICE1.md`.
Its message summarises the audit. It is created locally and pushed only on the owner's go. Once pushed, it
is never moved.

### Section 13: the journal entry

`~/fc_vision_notes_dhartwig/06-development-journals/<date>_FC08_SLICE1_LANDING.md`: what broke, what
surprised, what slice 2 should change. It is drawn from the record (CLAUDE.md, the specs, the ledgers), not
memory:

- the search fix that measured as no change;
- a single-run score not being a measurement;
- the stdio envelope that read a refusal as success;
- SAN001 approved but absent from its record;
- the checks the reviews found vacuous.

It is written on a branch and merged into `main`, which is protected. It is pushed on the owner's go.

### Section 14: the LinkedIn draft

About 1,300 characters in the Question ↓ Capability ↓ Intelligence Produced ↓ Investigator Outcome structure,
linking the live walkthrough. Every number in it must appear in `RELEASE_SLICE1.md`.

It is saved to the vault at `Cowork HB/02 Projects/NEXUS/`, **not to fc-08**: the repository is public, so a
draft committed there is already published. It is also given in chat to paste. It is never posted by Claude.

---

## Acceptance for week 6

- `python tools/check_all.py` passes on the owner's machine, and `--cold` passes on CI naming every NOT RUN guard.
- `build_digests --check` reports matches for `slice1-2026-09-24`, and still does after a further decision is appended (proved in the guard with a temporary log).
- `propose_link` refuses a queue path that is not `data/proposals/<run_id>.jsonl`.
- `resolve_actor` is on the server, read-only, with a committed resolution rate over the extractor's records.
- The walkthrough is live on the portfolio, byte-identical to fc-08's committed build, and its staleness gate passes.
- `future-capabilities.html` shows Threat Intelligence `Built · slice 1`.
- `RELEASE_SLICE1.md` shows every definition-of-done box with its evidence, and the tag exists.
- The journal entry is merged, and the LinkedIn draft is in the vault.

## Out of scope

- Linking any register actor to an fc-10 `entity_key`. The seam exists; the link needs a real substrate.
- Owner decisions on the register candidates, which the owner takes separately.
- Re-running extraction with `resolve_actor` available to the agent. The tool is on the server; changing the prompt to use it is slice 2.
- The 31 orphaned TBML001 pages and any other portfolio tidying.
- Showing undecided emergent candidates in digests (deferred in week 5, still deferred).
