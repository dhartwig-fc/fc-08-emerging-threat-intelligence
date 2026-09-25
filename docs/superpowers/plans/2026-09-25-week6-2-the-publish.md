# Week 6 sub-project 2: the publish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A walkthrough page for ADV-2026-0013, generated in fc-08 from committed inputs only, with a boundary check, a publisher, a staleness gate, and the Track 2 edit to the portfolio's `future-capabilities.html` prepared on a local branch.

**Architecture:** `tools/build_walkthrough.py` renders `site/threat-intel/index.html` from the governed files (record, proposals, decision-log prefix pinned by the current digest batch, actor-resolution rows, digest block, telemetry, live-computed scores); `--check` proves the committed page equals a fresh build. `governance/publish_boundary.py` refuses internal references. `tools/publish_walkthrough.py` rebuilds, checks, runs the boundary and copies to `<portfolio>/projects/nexus/threat-intel/index.html`, recording what it published in `site/PUBLISHED`. `evals/check_published_walkthrough.py` has a cold half (the committed page is what was last published, or nothing was ever published) and a portfolio half.

**Tech Stack:** Python 3.14 (`.venv`), stdlib (`html`, `hashlib`, `json`), existing fc-08 modules. No new dependencies. Guards are scripts ending `HELD (0 failures)`.

**Spec:** `docs/superpowers/specs/2026-09-25-week6-landing-design.md`, Sections 6-10.

## Global Constraints

- Repository `~/fc-08-emerging-threat-intelligence`, branch `main`, Python `.venv/bin/python`. The pre-commit hook is LIVE (`tools/check_all.py` on every commit, several minutes); never `--no-verify`.
- **OVERNIGHT RUN: nothing is pushed, in any repository.** The publisher is NEVER run against the real portfolio in this plan; it is tested against temporary portfolio directories only. The portfolio edit in Task 6 is committed on a LOCAL branch `fc08-slice1-publish` and not pushed. The owner publishes and pushes on the day.
- NO live model runs. Never run `tools/review.py` except `--check`. Never write `data/records/`, `data/records_merged/`, the decision log, `data/proposals/`, `data/telemetry/`, `data/digests/`.
- Only `governance/decisions.py` and `evals/check_review_gate.py` may contain the decision log's or approvals files' FILENAMES in a `.py`/`.sh` (writer scan). Reference them through `gd.LOG.name` etc.
- The page is built from COMMITTED inputs only: no PDF, no gitignored file, no clock, no git call. The same inputs give the same bytes.
- Every number on the page comes from an input file or is computed from one at build time; none is typed into the builder.
- The page carries the NEXUS shield and wordmark (markup and colour tokens copied from the portfolio's `projects/nexus/walkthrough.html`), defines colour tokens on `:root`, works at 375px width with a 16px side gutter and no horizontal scroll, and escapes every data value with `html.escape`.
- Guard style: `(ok, label, detail)` checks; `HELD (0 failures)` / `REFUSED (n failures)`; `--mutate X` prints `HELD: the probe detects the defect when the rule is removed` when checks fail. Watch every new check FAIL before it passes. Mutation runs use `PYTHONPYCACHEPREFIX=/tmp/mut-<label>`.
- Commits start `Week 6.2:`. NO `Co-Authored-By` trailer.
- No `.bak`/`_backup`/`_before_*` files. No file over 50 MB.

## Plan rulings (recorded; the spec is amended by Task 6)

1. **Scores are single full-set runs, computed at build time, and say so.** The spec's "bands from the repeats" cannot come from committed inputs: the repeat records are gitignored and bands exist only for 4-5 advisories, in prose. `evals/score_report.json` is also stale (pre label pass). The page computes the four fields' P/R/F1 for extraction (`data/records`) and extraction + reviewer (`data/records_merged`) against `evals/golden`, labels them single runs, and links the committed trace `evals/traces/FULL_BASELINE_2026-09-12.md` on GitHub for run-to-run variation.
2. **The staleness gate compares the committed page with what was published.** A tracked `site/PUBLISHED` holds the sha256 of the page last published (written only by the publisher). Absent = never published = nothing to be stale (pass, saying so). Present = the committed page's sha256 must equal it (cold), and the portfolio's copy must equal the committed page (needs-portfolio). A rule that failed whenever the portfolio lacked the page would block every fc-08 commit until the first publish.
3. **The page's advisory is ADV-2026-0013; its record is `data/records_merged/ADV-2026-0013.json`** (the published batch); the grounding and review sections use run `adv-2026-0013-extractor-f617bd3b00` (the run the owner decided); telemetry uses `adv-2026-0013-extractor-69eeab7b41` (the run with telemetry). Each section names its run.
4. **The review cards are rendered with `governance.card.render(link, None, …)`**, i.e. as the owner saw them at review time, from the queue file of run f617bd3b00, without re-verifying quotes (no PDF at build).

---

## File structure

| File | Responsibility |
|---|---|
| `governance/publish_boundary.py` | `violations(text) -> List[str]`: internal references a public page must not carry |
| `evals/check_publish_boundary.py` | guard: each forbidden class caught, a clean page passes |
| `evals/score.py` (modify) | expose `score_dirs(...) -> dict`, the dict `main` writes |
| `tools/build_walkthrough.py` | render `site/threat-intel/index.html`; `--check` |
| `site/threat-intel/index.html` | the committed page |
| `evals/check_walkthrough.py` | guard: the page is a projection of its inputs |
| `tools/publish_walkthrough.py` | rebuild, check, boundary, copy, write `site/PUBLISHED` |
| `evals/check_published_walkthrough.py` | staleness gate: cold half + portfolio half |
| `evals/check_publisher.py` | guard for the publisher, temporary portfolios only |
| `tools/check_all.py` (modify) | new guards and their measured classes |
| `CLAUDE.md`, spec (modify) | status, rulings |
| portfolio `projects/nexus/future-capabilities.html` | Track 2 edit, local branch `fc08-slice1-publish` |

---

### Task 1: the publish boundary

**Files:** Create `governance/publish_boundary.py`, `evals/check_publish_boundary.py`; Modify `tools/check_all.py`.

**Interfaces:**
- Produces: `publish_boundary.violations(text: str) -> List[str]` — sorted, de-duplicated offending substrings; empty when clean. Module attributes `FORBIDDEN_LITERALS`, `_PATH_PATTERNS`, `_EMAIL` (the guard's mutations replace them).

- [ ] **Step 1: Write the guard `evals/check_publish_boundary.py`**

```python
"""
Pin the public-page boundary: a page leaving this repository must not name local
paths, internal files, or people's addresses.

Usage:
    python evals/check_publish_boundary.py
    python evals/check_publish_boundary.py --mutate no-paths      # absolute/home paths pass; MUST fail
    python evals/check_publish_boundary.py --mutate no-internal   # internal names pass; MUST fail
    python evals/check_publish_boundary.py --mutate no-email      # addresses pass; MUST fail

WHY. fc-10 shipped pages across the public boundary for weeks with the check run
only when a human remembered (its CLAUDE.md, 2026-09-10). This is fc-08's own
check -- importing fc-10's would make a public repository depend on a sibling.

OFFLINE. Synthetic strings only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402

CLEAN = "<p>ADV-2026-0013 was approved on 2026-09-24; see github.com/example/repo/blob/main/evals/traces/X.md</p>"
CASES = [
    ("an absolute macOS path", "<p>built at /Users/someone/fc-08/site</p>", "/Users/"),
    ("a home-relative path", "<p>see ~/fc-08-emerging-threat-intelligence</p>", "~/"),
    ("a Windows drive path", "<p>C:\\work\\fc08</p>", "C:\\"),
    ("a queue file", "<p>adv-2026-0013-extractor-f617bd3b00.jsonl</p>", ".jsonl"),
    ("the decision log's filename", "<p>%s</p>" % gd.LOG.name, gd.LOG.name),
    ("an approvals file's filename", "<p>%s</p>" % gd.APPROVED_LINKS.name, gd.APPROVED_LINKS.name),
    ("a data/ path", "<p>data/desk_routing.json</p>", "data/"),
    ("the SDD workspace", "<p>.superpowers/sdd</p>", ".superpowers"),
    ("the virtualenv", "<p>.venv/bin/python</p>", ".venv"),
    ("an email address", "<p>contact someone@example.com</p>", "someone@example.com"),
]


def checks() -> list:
    out = [(pb.violations(CLEAN) == [], "a clean page passes (a GitHub URL and ids are not violations)",
            str(pb.violations(CLEAN)))]
    for label, text, token in CASES:
        got = pb.violations(text)
        out.append((any(token in v for v in got), "refused: %s" % label, str(got)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the publish boundary")
    ap.add_argument("--mutate", choices=("no-paths", "no-internal", "no-email"))
    args = ap.parse_args(argv)
    if args.mutate == "no-paths":
        pb._PATH_PATTERNS = ()
    elif args.mutate == "no-internal":
        pb.FORBIDDEN_LITERALS = ()
    elif args.mutate == "no-email":
        pb._EMAIL = None
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Run it — expect an ImportError (RED).** `.venv/bin/python evals/check_publish_boundary.py`

- [ ] **Step 3: Write `governance/publish_boundary.py`**

```python
"""
What a page leaving this repository must not carry.

A public page may name advisory ids, run ids, typology ids, dates and public URLs.
It must not name a local path (it leaks a machine), an internal file (it points a
reader at something they cannot open and tells them how the governance is stored),
or anyone's email address. violations() returns every offending substring; a
publisher refuses a page with any.
"""

from __future__ import annotations

import re
from typing import List, Optional, Pattern, Tuple

from governance import decisions as gd

FORBIDDEN_LITERALS: Tuple[str, ...] = (
    ".jsonl", "data/", ".superpowers", ".venv",
    gd.LOG.name, gd.APPROVED_LINKS.name, gd.APPROVED_EMERGENT.name,
)
_PATH_PATTERNS: Tuple[Pattern, ...] = (
    re.compile(r"/Users/[^\s\"'<]*"),
    re.compile(r"/home/[^\s\"'<]*"),
    re.compile(r"~/[^\s\"'<]*"),
    re.compile(r"\b[A-Za-z]:\\[^\s\"'<]*"),
)
_EMAIL: Optional[Pattern] = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def violations(text: str) -> List[str]:
    found = set()
    for lit in FORBIDDEN_LITERALS:
        if lit and lit in text:
            found.add(lit)
    for pat in _PATH_PATTERNS:
        found.update(m.group(0) for m in pat.finditer(text))
    if _EMAIL is not None:
        found.update(m.group(0) for m in _EMAIL.finditer(text))
    return sorted(found)
```

- [ ] **Step 4:** Run the guard (GREEN) and each mutation (each must print `HELD: the probe detects…`). Add `("check_publish_boundary", ["evals/check_publish_boundary.py"], "cold")` to `tools/check_all.py` GUARDS. Run `.venv/bin/python evals/check_review_gate.py | tail -1` — the writer scan must stay `HELD` (the module names the log only through `gd.LOG.name`).

- [ ] **Step 5: Commit** `git add governance/publish_boundary.py evals/check_publish_boundary.py tools/check_all.py && git commit -m "Week 6.2: the publish boundary -- no local paths, internal files or addresses on a public page"`

---

### Task 2: scores as a function

**Files:** Modify `evals/score.py`.

**Interfaces:**
- Produces: `evals.score.score_dirs(golden_dir: Path, predicted_dir: Path, emergent_threshold: float = DEFAULT_EMERGENT_THRESHOLD, actor_threshold: float = DEFAULT_ACTOR_THRESHOLD) -> dict`, returning exactly the dict `main` writes with `--json` (keys `golden_dir`, `predicted_dir`, `emergent_threshold`, `actor_threshold`, `scored`, `not_scored_no_prediction`, `ignored_no_golden`, `totals`, `per_advisory`). `main` calls it.

- [ ] **Step 1:** record baselines BEFORE editing: `.venv/bin/python evals/score.py > /tmp/s1.txt; .venv/bin/python evals/score.py --predicted data/records_merged > /tmp/s2.txt; .venv/bin/python evals/score.py --predicted evals/golden > /tmp/s3.txt; .venv/bin/python evals/score.py --json /tmp/s4.json > /dev/null`.
- [ ] **Step 2:** move the part of `main` that loads golden/predicted and computes the report into `score_dirs`; `main` parses args, calls it, prints and writes exactly as before. No behaviour change.
- [ ] **Step 3:** prove it: the three stdout captures `diff` identical, and a fresh `--json` equals `/tmp/s4.json`. `evals/check_emergent_threshold.py` HELD.
- [ ] **Step 4: Commit** `git add evals/score.py && git commit -m "Week 6.2: score_dirs -- the scorer's report as a function, output unchanged"`

---

### Task 3: the page builder, sections 1-5

**Files:** Create `tools/build_walkthrough.py`, `site/threat-intel/index.html`, `evals/check_walkthrough.py`; Modify `tools/check_all.py`.

**Interfaces:**
- Consumes: `publish_boundary.violations` (Task 1).
- Produces: `tools/build_walkthrough.py` with `ROOT`, `OUT = ROOT / "site" / "threat-intel" / "index.html"`, `ADVISORY = "ADV-2026-0013"`, `DECIDED_RUN = "adv-2026-0013-extractor-f617bd3b00"`, `TELEMETRY_RUN = "adv-2026-0013-extractor-69eeab7b41"`, `inputs() -> dict` (every input loaded once), `build(inp: dict) -> str` (the page), CLI `--check` (exit 1, "the committed page differs from a fresh build", when it does). Sections are functions `section_question(inp)`, `section_source(inp)`, `section_extraction(inp)`, `section_grounding(inp)`, `section_review(inp)` (this task) and `section_actors`, `section_digest`, `section_telemetry`, `section_score`, `section_limits` (Task 4), each returning an HTML string whose `<section>` has a stable `id`: `question`, `source`, `extraction`, `grounding`, `review`, `actors`, `digest`, `telemetry`, `score`, `limits`.

**Inputs (`inputs()` loads exactly these, nothing else):**
- `evals/golden/advisory_list.json` → the ADV-2026-0013 entry (title, publisher, published_on, url, pages, sha256).
- `data/records_merged/ADV-2026-0013.json` → the record (typologies with `added_by`, citations; actors; indicators; summary).
- `data/typologies.json` → labels and families.
- `data/proposals/<DECIDED_RUN>.jsonl` via `governance.proposals.load_queue_files` → proposals; `governance.proposals.group` → links.
- `data/digests/CURRENT` → batch id; `data/digests/<batch>/manifest.json` → `decision_log.lines`; `governance.decisions.log_prefix(lines)` → decisions; keep those with `advisory_id == ADVISORY`.
- `evals/golden/ADV-2026-0013.json` → golden typology ids (the card's context line).
- Task 4 adds `evals/actor_resolution.json`, `data/digests/<batch>/sanctions_desk.md`, `data/telemetry/<TELEMETRY_RUN>.jsonl`, `evals/attested_citations.json`, and `evals.score.score_dirs`.
Paths go through the modules' own constants where they exist (the log only via `log_prefix`, never a literal of its filename).

**Sections (this task):**
1. `question` — Question ↓ Capability ↓ Intelligence Produced ↓ Investigator Outcome, for this advisory. Prose; every count shown (typologies asserted, links approved, desks reached) is computed from the inputs.
2. `source` — title, publisher, published date, URL (a link), page count, and the document sha256, with one line saying every citation below is pinned to that hash.
3. `extraction` — one row per typology in the record: id (or "emergent"), label, family, who asserted it (`extractor` when `added_by` is absent or "extractor", else `reviewer`), and each citation as `p<page>` + the verbatim quote in a `<blockquote>`.
4. `grounding` — the proposals of `DECIDED_RUN`: typology, confidence, citations, and a line stating the quote was located on its page by `propose_link` before the proposal was written (the contract; do not claim a re-check at build).
5. `review` — for each link of `DECIDED_RUN`, the card text from `governance.card.render(link, None, advisories, library, golden_ids)` in a `<pre>` (escaped), then that link's decision line(s) from the pinned log prefix: date, decision, the owner's note. State the decision-log line count the page was built from.

**Page shell:** `<!doctype html>`, `<html lang="en">`, `<meta charset="utf-8">`, `<meta name="viewport" content="width=device-width,initial-scale=1">`, `<title>Threat Intelligence Walkthrough</title>`, a `<style>` with the `:root` tokens copied from the portfolio's `projects/nexus/walkthrough.html` (`--bg0 --bg1 --panel --edge --ink --ink2 --ink3 --acc --gold --good --crit --sans --mono --maxw`), a `@media (prefers-color-scheme: light)` block redefining them for a light background, `body{background:var(--bg0);color:var(--ink)}`, `.wrap{max-width:var(--maxw);margin:0 auto;padding:32px 16px 72px}`, `pre{white-space:pre-wrap;overflow-wrap:anywhere}`, wrapping `blockquote` and table styles (no horizontal page scroll at 375px), then the brand block (the shield `<svg>` and `NE<span class="x">X</span>US` wordmark copied from the portfolio walkthrough, kicker "Threat Intelligence · Slice 1"), a back link `<a href="../future-capabilities.html">`, and the sections. No external scripts or fonts.

**Guard `evals/check_walkthrough.py` (cold) — this task's checks:**
- `build_walkthrough.py --check` passes.
- Two consecutive builds are byte-identical, and a build in a subprocess under a different `PYTHONHASHSEED` is byte-identical.
- The five section ids exist exactly once.
- `publish_boundary.violations(page) == []`.
- Every typology id in the record appears in `#extraction`; every citation's quote (escaped) appears in `#extraction`.
- The number of decision lines in `#review` equals the ADVISORY decisions in the pinned log prefix (5 today), and each decided link's typology id appears there.
- `DECIDED_RUN` appears in `#grounding` and `#review`.
- Mutations: `--mutate drop-citation` (the builder skips each typology's last citation) fails the citation check; `--mutate unpinned-log` (the builder reads the whole log, not the pinned prefix) fails a check that builds against a TEMP copy of the decision log with one synthetic extra ADVISORY decision appended, passed through a hidden `--log` argument that `inputs()` accepts (default `governance.decisions.LOG`) — the correct builder's page is unchanged by the extra line; the mutated builder's is not. Never write the real log.

- [ ] **Step 1:** write `evals/check_walkthrough.py` with this task's checks; run it — RED (no builder).
- [ ] **Step 2:** write `tools/build_walkthrough.py`: the shell and sections 1-5 (the page ends after `review`; Task 4 adds 6-10).
- [ ] **Step 3:** build the page, `--check`, guard GREEN, both mutations HELD.
- [ ] **Step 4:** add `("check_walkthrough", ["evals/check_walkthrough.py"], "cold")` and `("build_walkthrough --check", ["tools/build_walkthrough.py", "--check"], "cold")` to GUARDS (cold: tracked files only; confirm by reasoning, no PDF or gitignored read).
- [ ] **Step 5: Commit** `git add tools/build_walkthrough.py site/threat-intel/index.html evals/check_walkthrough.py tools/check_all.py && git commit -m "Week 6.2: the walkthrough page, sections 1-5 -- source, extraction, grounding, review, each from its governed file"`

---

### Task 4: the page builder, sections 6-10

**Files:** Modify `tools/build_walkthrough.py`, `site/threat-intel/index.html`, `evals/check_walkthrough.py`.

**Interfaces:** Consumes Task 3's `inputs()`/`build()`; Task 2's `score_dirs`.

**Sections:**
6. `actors` — the rows of `evals/actor_resolution.json` with `advisory_id == ADVISORY`: name, status, the `ACT-` id and matched spelling when resolved, the entries when ambiguous. Then the record's `category` actors, each "not resolvable: a class of actor, not a named party". Then the `entity_key` seam, shown EMPTY, with the reason: the platform's resolved-entity estate is synthetic demonstration data, and a real designation will never name a synthetic party. Say plainly that the unresolved named actors include the note's own publishers (OFAC, BIS, DOJ), which the extractor records as actors.
7. `digest` — the `## ADV-2026-0013` block cut from `data/digests/<CURRENT>/sanctions_desk.md` (its heading up to the next `## ` or end), escaped preformatted text, with a line naming the batch id and its pinned decision-log line count. The cut excludes the desk file's header (which names `data/…` and would cross the boundary).
8. `telemetry` — from `data/telemetry/<TELEMETRY_RUN>.jsonl`: tool-call events per tool and per terminal status, permission events, and the `RUN_COMPLETED` payload's turns, duration, cost and `validated`. Name the run; state that its proposals are separate from the decided run's and remain undecided.
9. `score` — `score_dirs(evals/golden, data/records)` ("extraction only") and `score_dirs(evals/golden, data/records_merged)` ("extraction + reviewer"): P, R, F1 for typologies, emergent, actors, jurisdictions, to 3 decimals. Labelled single full-set runs, with the link `https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence/blob/main/evals/traces/FULL_BASELINE_2026-09-12.md` for measured run-to-run variation (plan ruling 1).
10. `limits` — plainly: the extractor does not yet call `resolve_actor` (slice 2); no `entity_key` links are made; digests are built on demand, not delivered; approved emergent candidates are not yet doctrine; N citations are owner-attested because the matcher cannot place them (N read from `evals/attested_citations.json`); the scores are single runs.

**Guard additions (`evals/check_walkthrough.py`):**
- Section ids 6-10 exist once each.
- Every ADVISORY actor row's name appears in `#actors`, with its `ACT-` id when resolved.
- The block in `#digest` equals (escaped) the cut from the desk file; the batch id shown equals `data/digests/CURRENT`.
- Telemetry counts shown equal counts recomputed from the file.
- The eight F1 values shown equal `score_dirs` recomputed at check time.
- The attested count in `#limits` equals `len(attested)` in `evals/attested_citations.json`.
- Boundary clean; `--check` passes; determinism across two hash seeds.
- Mutation `--mutate typed-score` (the builder prints a fixed 0.700 for merged typology F1) fails the score check.

- [ ] **Step 1:** add the checks — RED. **Step 2:** implement sections 6-10. **Step 3:** rebuild, `--check`, guard GREEN, all mutations HELD. **Step 4: Commit** `git add tools/build_walkthrough.py site/threat-intel/index.html evals/check_walkthrough.py && git commit -m "Week 6.2: the walkthrough page, sections 6-10 -- actors, digest, telemetry, score, limits"`

---

### Task 5: the publisher and the staleness gate

**Files:** Create `tools/publish_walkthrough.py`, `evals/check_published_walkthrough.py`, `evals/check_publisher.py`; Modify `tools/check_all.py`.

**Interfaces:**
- Produces: `tools/publish_walkthrough.py` — `PUBLISHED = ROOT / "site" / "PUBLISHED"`, `DEST_REL`, `publish(portfolio: Path) -> int`; CLI `--portfolio PATH` (default `NEXUS_PORTFOLIO` env var or `~/Cowork HB/dan-hartwig-portfolio`, expanded). `evals/check_published_walkthrough.py` — `gate(page_path: Path, published_path: Path, portfolio: Optional[Path]) -> List[str]` (problems) plus CLI `--cold` and `--portfolio PATH`.

- [ ] **Step 1: Write `tools/publish_walkthrough.py`**

```python
"""
Publish the threat-intelligence walkthrough to the portfolio working tree.

Usage:
    python tools/publish_walkthrough.py --portfolio <path>

Steps, and each one refuses rather than guessing:
  1. rebuild the page in memory and require it to equal the committed
     site/threat-intel/index.html (commit first; never publish an uncommitted page);
  2. run the publish boundary on it;
  3. require <portfolio>/projects/nexus/ to exist (a wrong root is the typo that matters);
  4. write <portfolio>/projects/nexus/threat-intel/index.html (creating threat-intel/ only);
  5. write site/PUBLISHED with the page's sha256, which the staleness gate reads.
It never commits or pushes either repository.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_walkthrough as bw  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402

PUBLISHED = ROOT / "site" / "PUBLISHED"
DEST_REL = Path("projects") / "nexus" / "threat-intel" / "index.html"
DEFAULT_PORTFOLIO = os.environ.get("NEXUS_PORTFOLIO", "~/Cowork HB/dan-hartwig-portfolio")


def publish(portfolio: Path) -> int:
    page = bw.build(bw.inputs())
    if not bw.OUT.exists() or bw.OUT.read_text(encoding="utf-8") != page:
        print("REFUSED: the committed page differs from a fresh build; rebuild and commit it first", file=sys.stderr)
        return 1
    bad = pb.violations(page)
    if bad:
        print("REFUSED: the page crosses the publish boundary: %s" % ", ".join(bad), file=sys.stderr)
        return 1
    nexus = portfolio / "projects" / "nexus"
    if not nexus.is_dir():
        print("REFUSED: %s has no projects/nexus/ -- is this the portfolio root?" % portfolio.name, file=sys.stderr)
        return 2
    dest = portfolio / DEST_REL
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    PUBLISHED.write_text(hashlib.sha256(page.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")
    print("published %s (%d bytes); recorded in site/PUBLISHED" % (DEST_REL.as_posix(), len(page.encode("utf-8"))))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Publish the walkthrough to the portfolio working tree")
    ap.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
    args = ap.parse_args(argv)
    return publish(Path(os.path.expanduser(args.portfolio)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Write `evals/check_published_walkthrough.py`** — `gate(page_path, published_path, portfolio)`:
  - Cold half: `published_path` absent → no problems, message `never published: nothing to be stale`. Present → sha256 of `page_path` must equal its contents, else problem `the committed page changed since it was published: republish it`.
  - Portfolio half (when `portfolio` is not None): if `published_path` is absent → nothing to compare (message `never published`); else `<portfolio>/projects/nexus/threat-intel/index.html` must exist and be byte-identical to `page_path`, else `the published copy differs from the committed page`.
  - CLI: `--cold` runs the cold half only; without it, a missing portfolio root exits 2 (`NOT RUN: no portfolio checkout at <name>`) — check_all classes it `needs-portfolio`.
  - GUARDS: `("check_published_walkthrough --cold", ["evals/check_published_walkthrough.py", "--cold"], "cold")` and `("check_published_walkthrough", ["evals/check_published_walkthrough.py"], "needs-portfolio")`. Update check_all's docstring line for `needs-portfolio`.
- [ ] **Step 3: Write `evals/check_publisher.py` (cold)** — against TEMP portfolios only (`tempfile.mkdtemp()` with `projects/nexus/` created), with `publish_walkthrough.PUBLISHED` redirected to a temp file so the real `site/PUBLISHED` is never written:
  - a publish writes the page byte-identical to the committed one and records its sha;
  - `gate()` with the temp portfolio and temp PUBLISHED passes after it, and FAILS after one byte of the temp published copy changes, and FAILS (cold half) when the temp PUBLISHED holds a different sha;
  - a root without `projects/nexus/` is refused (return 2) and nothing is written;
  - a boundary violation is refused: patch `bw.inputs` to return the real inputs with the advisory title prefixed `/Users/x `, and patch `bw.OUT` to a temp file holding `bw.build` of those inputs, so the committed-equals-fresh step passes and the BOUNDARY is what refuses (a plant must reach the page through an input: fc-10 learned a plant in the output is overwritten by the rebuild);
  - `--mutate skip-boundary` (the publisher skips `pb.violations`) fails the refusal check.
  - GUARDS: `("check_publisher", ["evals/check_publisher.py"], "cold")`.
- [ ] **Step 4:** confirm `site/PUBLISHED` does NOT exist in the repo, the gate's cold half says `never published`, and the full `tools/check_all.py` PASSES.
- [ ] **Step 5: Commit** `git add tools/publish_walkthrough.py evals/check_published_walkthrough.py evals/check_publisher.py tools/check_all.py && git commit -m "Week 6.2: the publisher and its staleness gate -- tested against temporary portfolios only"`

**NEVER in this plan:** `tools/publish_walkthrough.py` against the real portfolio.

---

### Task 6: the portfolio edit (local branch) and the record

**Files:** Portfolio `~/Cowork HB/dan-hartwig-portfolio/projects/nexus/future-capabilities.html` on a NEW local branch `fc08-slice1-publish`; fc-08 `CLAUDE.md`; fc-08 spec.

- [ ] **Step 1: Portfolio branch.** `git -C "$HOME/Cowork HB/dan-hartwig-portfolio" status -sb` must show a clean `main` equal to `origin/main`; if not, STOP and report. `git -C … switch -c fc08-slice1-publish`.
- [ ] **Step 2: Edit `future-capabilities.html`** (hand-edited prose; match its existing markup and classes):
  - the intro note (`… threat intel <b>in build</b> (week 4 of 6) …`) → `threat intel <b>built</b> (slice 1)`;
  - the Track 2 header `Track 2 · Threat Intelligence · In build` → `Track 2 · Threat Intelligence` followed by the SAR drafter's pill markup `<span class="pill built">Built · slice 1</span>` (read how that pill is used on the page and match it);
  - the "In build — slice 1, week 4 of 6" callout → a "Built — slice 1" callout stating what was delivered, ending with `<a href="threat-intel/index.html" style="color:var(--blue)">See the walkthrough →</a>` (the SAR drafter's link style);
  - the four pieces at delivered depth: advisory overlay built; actor intel — a governed register with exact-match resolution, the `entity_key` seam open; emergent loop — candidates and owner approval; intel digest — seven desks.
  - EVERY number in the edited block must appear on `site/threat-intel/index.html`: extract the digit-bearing tokens from the edited block with a short script and check each against the page text; record the output in the report.
- [ ] **Step 3:** commit on the branch (no trailer): `git -C … commit -am "NEXUS: Threat Intelligence built (slice 1) -- future capabilities, pending the walkthrough publish"`. Do NOT push. Then `git -C … switch main`, leaving the portfolio on `main` as found.
- [ ] **Step 4: fc-08 CLAUDE.md** — the week-6 entry gains: sub-project 2 BUILT, NOT published; the portfolio edit is on local branch `fc08-slice1-publish`; the publish procedure on the owner's go: `python tools/publish_walkthrough.py`, commit `site/PUBLISHED`, merge the portfolio branch, push both. File-map rows for the new files.
- [ ] **Step 5: Spec** — under Section 9 add verbatim: "Amended 2026-09-25 (plan ruling): the gate compares the committed page with a tracked site/PUBLISHED hash written by the publisher; before the first publish it passes with 'never published'. Section 6 item 9 is amended too: the scores are single full-set runs computed at build time, labelled so, with the committed trace linked for run-to-run variation -- the repeat records behind the bands are gitignored."
- [ ] **Step 6: Commit (fc-08)** `git add CLAUDE.md docs/superpowers/specs/2026-09-25-week6-landing-design.md && git commit -m "Week 6.2: record the built-not-published state and the plan's two rulings"`. Do not push.
