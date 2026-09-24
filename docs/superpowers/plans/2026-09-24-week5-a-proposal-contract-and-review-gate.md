# Week 5 sub-project A: proposal contract and review gate — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every proposal the agents make names its run and carries quotes verified against the PDF, and `tools/review.py` is the only thing that can turn a proposal into an approved link.

**Architecture:** The runner tells the MCP server who the run is through environment variables; `propose_link` refuses anything it cannot trace or verify and writes one tracked queue file per run. A `governance/` package loads, re-checks and groups proposals into links, records decisions in an append-only log, and rebuilds the approvals files from that log. `tools/review.py` is a thin CLI over it.

**Tech Stack:** Python 3.14 in `.venv/`, pydantic 2, pypdf, MCP Python SDK 2.x, claude-agent-sdk 0.2.x. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-week5-governance-design.md`, Sections 1 and 2.

## Global Constraints

- Repository: `~/fc-08-emerging-threat-intelligence`. Run every Python command as `.venv/bin/python` from the repo root. Bash `cd` does not persist between tool calls in this environment; `cd` inside each command.
- No new dependencies. There is NO pytest here: guards are scripts under `evals/` that print `PASS`/`FAIL` per check, end `HELD (0 failures)`, and take `--mutate` to prove they can fail. Follow `evals/check_added_by.py`.
- Mutation runs use their own bytecode cache: `PYTHONPYCACHEPREFIX=/tmp/fc08-mut-<label>`.
- Never write into `data/records/` or `data/records_merged/` (tracked evidence behind every published figure). The live extraction in Task 4 passes `--out` to a scratch path.
- Never delete evidence. The legacy queue is copied before anything changes and never truncated.
- Never create `.bak`, `_backup`, `_before_*` files inside the repo. Git is the safety net.
- Commits go to fc-08 `main` (this repo's practice), with NO `Co-Authored-By` trailer. Do not push; the owner pushes on request.
- Guards that need a source PDF (gitignored, in `data/advisories/`) exit 2 with a message when it is absent. They never report HELD over checks they did not run.
- The owner's decisions are the owner's. Nothing in this plan approves or rejects a real link.

## Two changes from the spec, made while planning

Both are written into the spec by Task 2.

1. **One tracked queue file per run, not one shared `data/proposals.jsonl`.** The spec kept the live queue at `data/proposals.jsonl`, which is gitignored — so every `proposal/2` line a decision cites would exist on one machine, the trap `data/records/` was in until `e0dbfb6`. Per-run files under `data/proposals/<run_id>.jsonl` are tracked, never appended to by two processes at once, and pair with the per-run telemetry file sub-project B adds. `data/proposals.jsonl` becomes legacy-only and is never written again.
2. **A decision line also carries `advisory_id`, `typology_id` and `emergent_label`,** so the approvals files are rebuilt from the log without parsing link keys back apart.

## File structure

| Path | Status | Responsibility |
|---|---|---|
| `schemas/citation_match.py` | create | THE rule for "is this quote on this page", plus the file hash. Imported by the server, the gate and `check_citations.py` |
| `evals/check_citations.py` | modify | uses `citation_match`; output byte-identical |
| `agents/run_identity.py` | create | `RunIdentity`: run id, stage, advisory, PDF and hash, and the env the server receives |
| `mcp_server/knowledge_centre_server.py` | modify | `propose_link` requires citations and a run identity, verifies quotes, writes `proposal/2` |
| `agents/extract_advisory.py` | modify | builds a `RunIdentity` per run; `agent_options` takes it |
| `agents/review_advisory.py` | modify | same, stage `reviewer` |
| `evals/check_tool_surface.py`, `evals/check_twin_pairs.py` | modify | follow the new signatures and contract |
| `evals/check_proposal_contract.py` | create | guard for Section 1 |
| `governance/__init__.py` | create | empty package marker |
| `governance/proposals.py` | create | load the queue, re-check, quarantine, group into links |
| `governance/decisions.py` | create | the decision log, `apply`, `rebuild`, `check_approved` |
| `governance/card.py` | create | renders one link for a human |
| `tools/review.py` | create | CLI: interactive, `--decisions`, `--list`, `--check` |
| `evals/check_review_gate.py` | create | guard for Section 2, grown across Tasks 5-7 |
| `data/proposals_legacy_2026-09-10_to_13.jsonl` | create | the 383 legacy proposals, byte-identical, tracked |
| `data/proposals/<run_id>.jsonl` | created by runs | tracked queue, one file per run |
| `data/review_decisions.jsonl`, `data/approved_links.json`, `data/approved_emergent.json` | created by `review.py` | tracked |

---

### Task 1: One citation rule, shared

**Files:**
- Create: `schemas/citation_match.py`
- Modify: `evals/check_citations.py` (imports and the whole `main`)

**Interfaces:**
- Produces: `norm(s: str) -> str`; `file_sha256(path) -> str`; `EXACT, SPACING, OFF_PAGE, MISSING: str`; `Located(status: str, found_on: tuple[int, ...])` with `.ok -> bool`; `PageIndex(page_texts: Sequence[str])` with `PageIndex.from_pdf(path) -> PageIndex`, `len(index)`, `index.locate(page: int, quote: str) -> Located`. `page` is the 1-based PDF page index.

- [ ] **Step 1: Record today's `check_citations.py` output for all 20 golden labels (the characterisation baseline)**

```bash
cd ~/fc-08-emerging-threat-intelligence && mkdir -p /tmp/fc08-cc-before && .venv/bin/python - <<'PY'
import json, subprocess, pathlib
L = json.load(open("evals/golden/advisory_list.json"))["advisories"]
for a in L:
    pdf = "data/advisories/" + pathlib.Path(a["file"]).name
    r = subprocess.run([".venv/bin/python", "evals/check_citations.py",
                        "evals/golden/%s.json" % a["advisory_id"], pdf], capture_output=True, text=True)
    pathlib.Path("/tmp/fc08-cc-before/%s.txt" % a["advisory_id"]).write_text(
        r.stdout + r.stderr + "\nEXIT %d\n" % r.returncode)
print("baseline written for", len(L))
PY
```
Expected: `baseline written for 20`.

- [ ] **Step 2: Create `schemas/citation_match.py`**

```python
"""
One rule for "is this quote on this page", shared by every caller.

Until week 5 this lived inside evals/check_citations.py, and the review gate and
the MCP server would each have needed it too. Three copies of a matching rule
drift, and a quote one of them accepts and another refuses is a governance
defect nobody can see. So there is one rule and three callers:
mcp_server/knowledge_centre_server.py (refuses at proposal time),
governance/proposals.py (re-checks at review time) and evals/check_citations.py.

The match is deliberately NOT fuzzy on meaning. Two tiers only:
  exact    the normalised quote is a substring of the normalised page;
  spacing  the same with ALL whitespace removed, because pypdf splits words on
           born-digital FATF PDFs ("collus ion", "t o believe"). An honest quote
           whose only difference is the extractor's spacing is not a fabrication.
Anything else is off_page (right words, wrong page) or missing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Sequence, Tuple

EXACT, SPACING, OFF_PAGE, MISSING = "exact", "spacing", "off_page", "missing"


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("­", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Located:
    status: str
    found_on: Tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in (EXACT, SPACING)


class PageIndex:
    """Normalised page text for one document, indexed by 1-based PDF page."""

    def __init__(self, page_texts: Sequence[str]):
        self.pages = [norm(t or "") for t in page_texts]
        self.tight = [p.replace(" ", "") for p in self.pages]
        self.tight_all = "".join(self.tight)

    @classmethod
    def from_pdf(cls, path) -> "PageIndex":
        from pypdf import PdfReader
        return cls([p.extract_text() or "" for p in PdfReader(str(path)).pages])

    def __len__(self) -> int:
        return len(self.pages)

    def locate(self, page: int, quote: str) -> Located:
        q = norm(quote)
        tq = q.replace(" ", "")
        i = page - 1
        in_range = 0 <= i < len(self.pages)
        if in_range and q in self.pages[i]:
            return Located(EXACT)
        if in_range and tq in self.tight[i]:
            return Located(SPACING)
        if tq in self.tight_all:
            return Located(OFF_PAGE, tuple(n + 1 for n, p in enumerate(self.tight) if tq in p))
        return Located(MISSING)
```

- [ ] **Step 3: Rewrite `evals/check_citations.py` to use it.** Keep the module docstring and the `if __name__ == "__main__":` block exactly as they are. Replace everything between them (from `from __future__ import annotations` onwards, up to but not including `if __name__`) with:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import EXACT, OFF_PAGE, SPACING, PageIndex  # noqa: E402


def main(record_path: str, pdf_path: str) -> int:
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    # The matching rule lives in schemas/citation_match.py, shared with the MCP
    # server and the review gate, so all three accept and refuse the same quotes.
    index = PageIndex.from_pdf(pdf_path)

    checked = 0
    exact = 0
    spacing = 0
    off_page = 0
    missing = 0
    for section in ("typologies", "actors", "indicators"):
        for item in record.get(section, []):
            label = item.get("label") or item.get("name") or item.get("description", "")[:60]
            for c in item.get("citations", []):
                checked += 1
                hit = index.locate(c["page"], c["quote"])
                if hit.status == EXACT:
                    exact += 1
                    status = "OK       "
                elif hit.status == SPACING:
                    spacing += 1
                    status = "OK-SPACING"
                elif hit.status == OFF_PAGE:
                    off_page += 1
                    status = "OFF-PAGE  (found on %s)" % list(hit.found_on)
                else:
                    missing += 1
                    status = "MISSING  "
                print("%s p%-3d %-10s %s" % (status, c["page"], section[:10], label[:60]))
                if not hit.ok:
                    print("           quote: %r" % c["quote"][:140])

    print()
    print("citations checked: %d | exact on page: %d | on page modulo pypdf spacing: %d | "
          "right quote wrong page: %d | not in document: %d"
          % (checked, exact, spacing, off_page, missing))
    if checked == 0:
        print("FAIL: no citations examined; a record with nothing to check is not a pass")
        return 1
    return 0 if missing == 0 and off_page == 0 else 1


```

- [ ] **Step 4: Re-run the 20 and require byte-identical output**

```bash
cd ~/fc-08-emerging-threat-intelligence && rm -rf /tmp/fc08-cc-after && mkdir -p /tmp/fc08-cc-after && .venv/bin/python - <<'PY'
import json, subprocess, pathlib
L = json.load(open("evals/golden/advisory_list.json"))["advisories"]
for a in L:
    pdf = "data/advisories/" + pathlib.Path(a["file"]).name
    r = subprocess.run([".venv/bin/python", "evals/check_citations.py",
                        "evals/golden/%s.json" % a["advisory_id"], pdf], capture_output=True, text=True)
    pathlib.Path("/tmp/fc08-cc-after/%s.txt" % a["advisory_id"]).write_text(
        r.stdout + r.stderr + "\nEXIT %d\n" % r.returncode)
PY
diff -r /tmp/fc08-cc-before /tmp/fc08-cc-after && echo "IDENTICAL on all 20"
```
Expected: `IDENTICAL on all 20`. Any diff means the extraction changed behaviour — fix the code, never the baseline.

- [ ] **Step 5: Prove the comparison can fail**

```bash
cd ~/fc-08-emerging-threat-intelligence && cp schemas/citation_match.py /tmp/fc08-citation_match.py \
 && sed -i '' 's/            return Located(SPACING)/            return Located(MISSING)/' schemas/citation_match.py \
 && grep -c "return Located(MISSING)" schemas/citation_match.py
```
Expected: `2` (the planted line plus the real final return). Now re-run Step 4's command with `PYTHONPYCACHEPREFIX=/tmp/fc08-mut-cc` prefixed to the `.venv/bin/python -` call. Expected: `diff` prints differences (several golden labels carry OK-SPACING citations) and `IDENTICAL` is NOT printed. Restore and confirm:

```bash
cd ~/fc-08-emerging-threat-intelligence && cp /tmp/fc08-citation_match.py schemas/citation_match.py && grep -c "return Located(MISSING)" schemas/citation_match.py
```
Expected: `1`. Re-run Step 4 and see `IDENTICAL on all 20`.

- [ ] **Step 6: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add schemas/citation_match.py evals/check_citations.py && git commit -m "Week 5 A1: one citation rule, shared -- schemas/citation_match.py

check_citations.py now imports the rule instead of owning it, so the MCP
server and the review gate can use the same one. Characterised on all 20
golden labels: output byte-identical before and after; a planted change
to the spacing tier made the comparison fail."
```

---

### Task 2: Preserve the legacy queue and record the two spec changes

**Files:**
- Create: `data/proposals_legacy_2026-09-10_to_13.jsonl`
- Modify: `docs/superpowers/specs/2026-09-24-week5-governance-design.md`

**Interfaces:** Produces the tracked legacy file. Nothing reads it in code; `governance/proposals.py` names it only to report it.

- [ ] **Step 1: Copy and verify**

```bash
cd ~/fc-08-emerging-threat-intelligence && cp -p data/proposals.jsonl data/proposals_legacy_2026-09-10_to_13.jsonl && shasum -a 256 data/proposals.jsonl data/proposals_legacy_2026-09-10_to_13.jsonl && wc -l < data/proposals_legacy_2026-09-10_to_13.jsonl
```
Expected: two identical hashes; `383`.

- [ ] **Step 2: Confirm the new paths are not gitignored**

```bash
cd ~/fc-08-emerging-threat-intelligence && for p in data/proposals_legacy_2026-09-10_to_13.jsonl data/proposals/x.jsonl data/review_decisions.jsonl data/approved_links.json data/approved_emergent.json; do git check-ignore -q "$p" && echo "IGNORED $p" || echo "trackable $p"; done
```
Expected: five `trackable` lines. If any says IGNORED, add a `!<path>` exception to `.gitignore` directly under the rule that catches it, with a one-line comment saying why, and re-run.

- [ ] **Step 3: Amend the spec.** In `docs/superpowers/specs/2026-09-24-week5-governance-design.md`:

(a) In `### Run identity comes from the run, not the agent`, add this row to the end of the table: `| NEXUS_PROPOSALS_PATH | data/proposals/<run_id>.jsonl |`.

(b) Replace the paragraph under `### The legacy queue` with:

```markdown
Copied byte-identical to a tracked `data/proposals_legacy_2026-09-10_to_13.jsonl`
before anything else changes. `data/proposals.jsonl` is never written again and
never truncated.

**Amended while planning, 2026-09-24: one queue file per run.** The server
writes to `data/proposals/<run_id>.jsonl` (the runner sets
`NEXUS_PROPOSALS_PATH`), and those files are TRACKED. A single shared
`data/proposals.jsonl` is gitignored, so every `proposal/2` line a decision cites
would have existed on one machine -- the trap `data/records/` was in until
`e0dbfb6`. Per-run files are also never appended to by two processes at once,
and pair with the per-run telemetry file in Section 3. `review.py` reads
`data/proposals/*.jsonl` and reports any line that is not `proposal/2`.
```

(c) In `### The decision log`, replace the code block with the one below, and add the sentence after it:

```
{decided_at, link_key, kind: governed|emergent, advisory_id, typology_id,
 emergent_label, decision: approve|reject, note, proposal_ids[], run_ids[],
 quotes_seen_sha256[]}
```

`advisory_id`, `typology_id` and `emergent_label` were added while planning, so the approvals files are rebuilt from the log without parsing link keys.

- [ ] **Step 4: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add data/proposals_legacy_2026-09-10_to_13.jsonl docs/superpowers/specs/2026-09-24-week5-governance-design.md && git commit -m "Week 5 A2: freeze the 383 legacy proposals as tracked history

data/proposals.jsonl was gitignored, so the only copy of every proposal
made 2026-09-10 to 13 lived on one machine. Copied byte-identical (sha256
checked) to a tracked file; the original is left in place.

Spec amended: one tracked queue file per run under data/proposals/, and
decision lines carry advisory and typology so the approvals files are
rebuilt without parsing keys."
```

---

### Task 3: The proposal contract in `propose_link`

**Files:**
- Create: `agents/run_identity.py`, `evals/check_proposal_contract.py`
- Modify: `mcp_server/knowledge_centre_server.py` (import block ~l.17-32; constants ~l.34-37; `ProposeLinkInput` ~l.81-92; `propose_link` ~l.424-468), `evals/check_twin_pairs.py` (setup ~l.55-62; the four `propose_link` calls ~l.123-155; `main`)

**Interfaces:**
- Consumes: `schemas.citation_match.PageIndex`, `file_sha256` (Task 1).
- Produces:
  - `agents.run_identity.RunIdentity(run_id: str, stage: str, advisory_id: str, pdf_path: Path, pdf_sha256: str)`, frozen; `RunIdentity.new(stage, advisory_id, pdf_path) -> RunIdentity`; `.queue_path -> Path`; `.env() -> dict[str, str]` (six keys). Module constants `STAGES = ("extractor", "reviewer")`, `QUEUE_DIR`.
  - Server: `RUN_ENV: tuple[str, ...]` (five keys); `_run_context() -> dict | None`; `_refuse_for_run(params, run) -> str | None`; `_refuse_citations(params, run) -> str | None`; `ProposedCitation(page: int, quote: str)`; `ProposeLinkInput.citations: list[ProposedCitation]` (1-5). Accepted replies start `Accepted`, refusals start `Rejected:`.
  - Queue line: `{"proposal_id", "proposed_at", "schema": "proposal/2", "run_id", "stage", "advisory_id", "document_sha256", "typology_id", "emergent_label", "rationale", "confidence", "citations": [{"page", "quote"}]}`.

- [ ] **Step 1: Write the failing guard `evals/check_proposal_contract.py`**

```python
"""
Pin the proposal contract: every proposal names its run and its quotes are real.

Usage:
    python evals/check_proposal_contract.py
    python evals/check_proposal_contract.py --mutate citations   # quote check removed; refusals MUST stop
    python evals/check_proposal_contract.py --mutate run         # advisory check removed; refusal MUST stop

WHY. Measured 2026-09-24: 383 proposals in the review queue, not one carrying a
citation or the run that made it. A reviewer shown such a proposal can read the
agent's reasoning but cannot check it, so approving it approves an assertion.
Since week 5 the runner tells the server who the run is (agents/run_identity.py)
and propose_link refuses: no run identity, an advisory other than the run's, a
document whose hash is not the run's, and any quote not on the page it names.

NOT A VACUOUS PASS. It also requires a correct proposal to be ACCEPTED -- a
server that refused everything would satisfy every refusal check.

NEEDS the ADV-2026-0002 PDF in data/advisories/ (gitignored). Without it this
exits 2 and says so; it never reports HELD over checks it did not run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADVISORY = "ADV-2026-0002"
OTHER_ADVISORY = "ADV-2026-0013"
QUEUE = Path(tempfile.mkdtemp(prefix="fc08_contract_")) / "queue.jsonl"
# Redirect the queue BEFORE importing the server: a guard never writes the real one.
os.environ["NEXUS_PROPOSALS_PATH"] = str(QUEUE)

from mcp_server import knowledge_centre_server as kc  # noqa: E402

_LIST = {a["advisory_id"]: a for a in
         json.loads((ROOT / "evals" / "golden" / "advisory_list.json").read_text(encoding="utf-8"))["advisories"]}
PDF = ROOT / "data" / "advisories" / Path(_LIST[ADVISORY]["file"]).name
SHA = _LIST[ADVISORY]["sha256"]


def _run_env(**override) -> None:
    env = {"NEXUS_RUN_ID": "probe-contract", "NEXUS_STAGE": "extractor", "NEXUS_ADVISORY_ID": ADVISORY,
           "NEXUS_PDF_PATH": str(PDF), "NEXUS_PDF_SHA256": SHA}
    env.update(override)
    for k in kc.RUN_ENV:
        os.environ.pop(k, None)
    for k, v in env.items():
        if v is not None:
            os.environ[k] = v


def _witness() -> tuple:
    """An untwinned typology from the golden label, with a citation known to be on its page."""
    g = json.loads((ROOT / "evals" / "golden" / ("%s.json" % ADVISORY)).read_text(encoding="utf-8"))
    for t in g["typologies"]:
        if t.get("typology_id") and t["typology_id"] not in kc.TYPOLOGY_TWINS:
            c = t["citations"][0]
            return t["typology_id"], {"page": c["page"], "quote": c["quote"]}
    raise SystemExit("no untwinned typology in the %s golden label -- the witness is gone" % ADVISORY)


def _propose(**kw) -> str:
    fn = getattr(kc.propose_link, "fn", kc.propose_link)
    return asyncio.run(fn(kc.ProposeLinkInput(**kw)))


def _schema_refuses(**kw) -> bool:
    try:
        kc.ProposeLinkInput(**kw)
        return False
    except Exception:
        return True


def _lines() -> list:
    if not QUEUE.exists():
        return []
    return [json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]


def checks() -> list:
    out = []
    tid, cite = _witness()
    base = dict(advisory_id=ADVISORY, typology_id=tid, confidence="medium", citations=[cite],
                rationale="The advisory describes this technique on page %d." % cite["page"])

    _run_env()
    got = _propose(**base)
    out.append((got.startswith("Accepted") and len(_lines()) == 1,
                "a correct proposal is ACCEPTED and written", got[:110]))
    first = (_lines() or [{}])[0]
    out.append((first.get("schema") == "proposal/2" and first.get("run_id") == "probe-contract"
                and first.get("stage") == "extractor" and first.get("document_sha256") == SHA
                and first.get("citations") == [cite],
                "the line carries schema, run id, stage, document hash and citations",
                "keys: %s" % sorted(first)))

    _propose(**base)
    ids = [line["proposal_id"] for line in _lines()]
    out.append((len(ids) == 2 and ids[0] == ids[1],
                "the same proposal twice has the same proposal_id", str(ids)))

    out.append((_schema_refuses(**{**base, "citations": []}),
                "a proposal with NO citation is refused", "citations has min_length=1"))

    wrong_page = cite["page"] + 1 if cite["page"] < 10 else cite["page"] - 1
    got = _propose(**{**base, "citations": [{"page": wrong_page, "quote": cite["quote"]}]})
    out.append((got.startswith("Rejected") and ("page %d" % cite["page"]) in got,
                "a quote on the WRONG page is refused, and the refusal names the right page", got[:140]))

    invented = {"page": cite["page"], "quote": "This sentence was written by the guard and is in no advisory."}
    got = _propose(**{**base, "citations": [invented]})
    out.append((got.startswith("Rejected") and "not in the document" in got,
                "an INVENTED quote is refused", got[:120]))

    _run_env(NEXUS_ADVISORY_ID=OTHER_ADVISORY)
    got = _propose(**base)
    out.append((got.startswith("Rejected") and OTHER_ADVISORY in got,
                "a proposal for an advisory other than the run's is refused", got[:120]))

    _run_env(NEXUS_PDF_SHA256="0" * 64)
    got = _propose(**base)
    out.append((got.startswith("Rejected") and "hash" in got,
                "a document whose hash is not the run's is refused", got[:120]))

    _run_env(NEXUS_RUN_ID=None)
    got = _propose(**base)
    out.append((got.startswith("Rejected") and "run identity" in got,
                "a server started WITHOUT a run identity refuses", got[:120]))

    _run_env()
    got = _propose(advisory_id=ADVISORY, emergent_label="Guard witness emergent technique",
                   confidence="low", citations=[cite],
                   rationale="Emergent witness: the guard proposes a label the library does not hold.")
    out.append((got.startswith("Accepted"), "an emergent proposal with a verified quote is accepted", got[:110]))

    out.append((len(_lines()) == 3,
                "refusals wrote NOTHING to the queue",
                "%d lines; expected 3 (two identical proposals and one emergent)" % len(_lines())))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the proposal contract")
    ap.add_argument("--mutate", choices=("citations", "run"),
                    help="remove one refusal; the checks that depend on it MUST fail")
    args = ap.parse_args(argv)

    if not PDF.exists():
        print("CANNOT RUN: %s is not on this machine (data/advisories/ is gitignored).\n"
              "Nothing was checked; this is not a pass." % PDF.relative_to(ROOT))
        return 2

    if args.mutate == "citations":
        kc._refuse_citations = lambda params, run: None
        print("MUTATED: the quote and document-hash check is removed.\n")
    elif args.mutate == "run":
        kc._refuse_for_run = lambda params, run: None
        print("MUTATED: the advisory-must-match-the-run check is removed.\n")

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

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_proposal_contract.py`
Expected: an error — `AttributeError: ... has no attribute 'RUN_ENV'` or a pydantic error that `citations` is not a permitted field. Either proves the contract is not there yet.

- [ ] **Step 3: Create `agents/run_identity.py`**

```python
"""
Who a run is -- told to the MCP server by the runner, never by the agent.

propose_link used to record whatever advisory_id the agent passed and nothing
else about where a proposal came from. Measured 2026-09-24: 383 proposals, none
naming its run, so a reviewer could not trace one to a record or a document.
The runner now builds one of these per run and hands the server its env(); the
agent cannot set or change any of it.
"""

from __future__ import annotations

import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import file_sha256  # noqa: E402

STAGES = ("extractor", "reviewer")
QUEUE_DIR = ROOT / "data" / "proposals"


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    stage: str
    advisory_id: str
    pdf_path: Path
    pdf_sha256: str

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError("stage must be one of %s, got %r" % (STAGES, self.stage))

    @classmethod
    def new(cls, stage: str, advisory_id: str, pdf_path: Path) -> "RunIdentity":
        pdf_path = Path(pdf_path).resolve()
        run_id = "%s-%s-%s" % (advisory_id.lower(), stage, secrets.token_hex(5))
        return cls(run_id, stage, advisory_id, pdf_path, file_sha256(pdf_path))

    @property
    def queue_path(self) -> Path:
        # One tracked file per run: never appended to by two processes, and in
        # every clone. See the spec's amended Section 1.
        return QUEUE_DIR / ("%s.jsonl" % self.run_id)

    def env(self) -> dict:
        return {
            "NEXUS_RUN_ID": self.run_id,
            "NEXUS_STAGE": self.stage,
            "NEXUS_ADVISORY_ID": self.advisory_id,
            "NEXUS_PDF_PATH": str(self.pdf_path),
            "NEXUS_PDF_SHA256": self.pdf_sha256,
            "NEXUS_PROPOSALS_PATH": str(self.queue_path),
        }
```

- [ ] **Step 4: Change the server's imports and module constants.** In `mcp_server/knowledge_centre_server.py`, replace the import block from `import json` through `from pydantic import BaseModel, ConfigDict, Field` with:

```python
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

try:
    # MCP Python SDK 2.x: FastMCP was renamed to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field
```

Replace the two lines `TYPOLOGY_PATH = …` and `PROPOSALS_PATH = …` with:

```python
TYPOLOGY_PATH = Path(os.environ.get("NEXUS_TYPOLOGY_PATH", ROOT / "data" / "typologies.json"))

# The server is launched as a script, so the repo root is not on sys.path.
sys.path.insert(0, str(ROOT))
from schemas.citation_match import PageIndex, file_sha256  # noqa: E402

# Set by the RUNNER (agents/run_identity.py), never by the agent. Read at call
# time, not import time, so a guard can vary them between calls.
RUN_ENV = ("NEXUS_RUN_ID", "NEXUS_STAGE", "NEXUS_ADVISORY_ID", "NEXUS_PDF_PATH", "NEXUS_PDF_SHA256")
```

- [ ] **Step 5: Add the citation model and field.** Directly above `class ProposeLinkInput`, add:

```python
class ProposedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(..., ge=1, description="PDF page index: the n in the '=== PAGE n ===' marker")
    quote: str = Field(..., min_length=10, max_length=600, description="Verbatim text from that page")
```

and add as the last field of `ProposeLinkInput`, after `confidence`:

```python
    citations: List[ProposedCitation] = Field(
        ..., min_length=1, max_length=5,
        description="The page and verbatim quote this link rests on -- the same citations as the record entry. "
                    "A quote that is not on the page it names is refused.",
    )
```

- [ ] **Step 6: Replace `propose_link` with the governed version.** Replace from the line `@mcp.tool(` that precedes `name="knowledge_centre_propose_link",` down to (not including) `if __name__ == "__main__":` with:

```python
def _run_context() -> Optional[dict]:
    ctx = {k: os.environ.get(k, "") for k in RUN_ENV}
    return ctx if all(ctx.values()) else None


def _proposals_path() -> Path:
    return Path(os.environ.get("NEXUS_PROPOSALS_PATH", ROOT / "data" / "proposals.jsonl"))


@lru_cache(maxsize=4)
def _page_index(pdf_path: str, expected_sha: str) -> PageIndex:
    if file_sha256(pdf_path) != expected_sha:
        raise ValueError("document hash mismatch: %s is not the document this run was started on" % pdf_path)
    return PageIndex.from_pdf(pdf_path)


def _refuse_for_run(params: "ProposeLinkInput", run: dict) -> Optional[str]:
    if params.advisory_id != run["NEXUS_ADVISORY_ID"]:
        return ("Rejected: this run is extracting %s; a proposal for %s cannot come from it."
                % (run["NEXUS_ADVISORY_ID"], params.advisory_id))
    return None


def _refuse_citations(params: "ProposeLinkInput", run: dict) -> Optional[str]:
    try:
        index = _page_index(run["NEXUS_PDF_PATH"], run["NEXUS_PDF_SHA256"])
    except (OSError, ValueError) as exc:
        return "Rejected: %s" % exc
    bad = []
    for c in params.citations:
        hit = index.locate(c.page, c.quote)
        if hit.ok:
            continue
        where = (" It appears on page %s." % ", ".join(str(n) for n in hit.found_on)) if hit.found_on \
            else " It is not in the document."
        bad.append("page %d: %r.%s" % (c.page, c.quote[:80], where))
    if bad:
        return ("Rejected: %d citation%s not found on the page named. Quote the page text verbatim, with the "
                "page number from its '=== PAGE n ===' marker, and propose again. %s"
                % (len(bad), "" if len(bad) == 1 else "s", " | ".join(bad[:3])))
    return None


@mcp.tool(
    name="knowledge_centre_propose_link",
    annotations={"title": "Propose advisory link", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def propose_link(params: ProposeLinkInput) -> str:
    """
    Propose that an advisory be pinned to a typology, or propose an emergent typology.

    This never writes to the library. It appends to this run's review queue; a
    human decides in tools/review.py. Exactly one of typology_id or
    emergent_label must be given, and every proposal carries the citations it
    rests on, each verified against the page it names.
    """
    # GOVERNANCE: a proposal nobody can trace to a run and a document cannot be
    # reviewed. The runner supplies the identity; without it, nothing is written.
    run = _run_context()
    if run is None:
        return ("Rejected: this server was started without a run identity (%s). A proposal that cannot be "
                "traced to a run and a document cannot be reviewed." % ", ".join(RUN_ENV))
    if bool(params.typology_id) == bool(params.emergent_label):
        return "Rejected: provide exactly one of typology_id or emergent_label."
    refusal = _refuse_for_run(params, run)
    if refusal:
        return refusal
    if params.typology_id and not any(r["typology_id"] == params.typology_id for r in _typologies()):
        return "Rejected: %s is not in the library. Use emergent_label if this is new." % params.typology_id

    # GOVERNANCE, not advice. A twinned code may not be pinned without the
    # rationale naming the twin it was chosen over. The refusal is what makes the
    # reason exist: trace one on ADV-2026-0016 found a typology retrieved,
    # confirmed and then dropped with no record anywhere of why.
    twin = TYPOLOGY_TWINS.get(params.typology_id or "")
    if twin and twin["twin"] not in (params.rationale or ""):
        return ("Rejected: %s has a cross-family twin, %s. These carry the same technique under "
                "two codes, so the choice has to be recorded. %s Name %s in the rationale and say "
                "why this family fits the advisory's framing, then propose again."
                % (params.typology_id, twin["twin"], twin["note"], twin["twin"]))

    # GOVERNANCE: the quote is checked where it is made, so the agent can correct
    # it, and again by the review gate, because the queue is a file.
    refusal = _refuse_citations(params, run)
    if refusal:
        return refusal

    body = {
        "schema": "proposal/2",
        "run_id": run["NEXUS_RUN_ID"],
        "stage": run["NEXUS_STAGE"],
        "advisory_id": params.advisory_id,
        "document_sha256": run["NEXUS_PDF_SHA256"],
        "typology_id": params.typology_id,
        "emergent_label": params.emergent_label,
        "rationale": params.rationale,
        "confidence": params.confidence,
        "citations": [{"page": c.page, "quote": c.quote} for c in params.citations],
    }
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    record = {"proposal_id": hashlib.sha256(canonical).hexdigest()[:16],
              "proposed_at": datetime.now(timezone.utc).isoformat(), **body}
    path = _proposals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return "Accepted into review queue: %s -> %s (proposal %s)" % (
        params.advisory_id,
        params.typology_id or "EMERGENT(%s)" % params.emergent_label,
        record["proposal_id"],
    )


```

- [ ] **Step 7: Run the guard, then both mutations**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_proposal_contract.py; echo "exit=$?"
PYTHONPYCACHEPREFIX=/tmp/fc08-mut-cit .venv/bin/python evals/check_proposal_contract.py --mutate citations; echo "exit=$?"
PYTHONPYCACHEPREFIX=/tmp/fc08-mut-run .venv/bin/python evals/check_proposal_contract.py --mutate run; echo "exit=$?"
```
Expected: first run 11 PASS, `HELD (0 failures)`, exit 0. `--mutate citations`: the wrong-page, invented, hash and "wrote NOTHING" checks FAIL; ends `HELD: the probe detects the defect when the rule is removed`, exit 0. `--mutate run`: the advisory-mismatch and "wrote NOTHING" checks FAIL; same ending, exit 0.

- [ ] **Step 8: Move `evals/check_twin_pairs.py` to the new contract.** It calls `propose_link` with no citations and no run identity, so it would now fail for the wrong reason. Replace:

```python
# Redirect the review queue BEFORE importing the server: propose_link appends to
# it, and a guard must never write into the real queue a human reviews.
_TMP_QUEUE = Path(tempfile.gettempdir()) / "fc08_twin_probe_queue.jsonl"
os.environ["NEXUS_PROPOSALS_PATH"] = str(_TMP_QUEUE)

from mcp_server import knowledge_centre_server as kc  # noqa: E402

ADVISORY = "ADV-2026-0017"
```

with:

```python
ADVISORY = "ADV-2026-0017"

# Redirect the review queue BEFORE importing the server: propose_link appends to
# it, and a guard must never write into the real queue a human reviews.
_TMP_QUEUE = Path(tempfile.gettempdir()) / "fc08_twin_probe_queue.jsonl"
os.environ["NEXUS_PROPOSALS_PATH"] = str(_TMP_QUEUE)

# Since week 5 propose_link refuses a proposal it cannot trace to a run and a
# document, and verifies every quote. Give it a real identity and a real quote,
# so a refusal seen here is the TWIN rule and not the contract.
_ENTRY = {a["advisory_id"]: a for a in json.loads(
    (ROOT / "evals" / "golden" / "advisory_list.json").read_text(encoding="utf-8"))["advisories"]}[ADVISORY]
PDF = ROOT / "data" / "advisories" / Path(_ENTRY["file"]).name
os.environ.update({"NEXUS_RUN_ID": "probe-twin-pairs", "NEXUS_STAGE": "extractor",
                   "NEXUS_ADVISORY_ID": ADVISORY, "NEXUS_PDF_PATH": str(PDF),
                   "NEXUS_PDF_SHA256": _ENTRY["sha256"]})
_GOLD = json.loads((ROOT / "evals" / "golden" / ("%s.json" % ADVISORY)).read_text(encoding="utf-8"))
CITE = [{"page": c["page"], "quote": c["quote"]} for c in
        next(t for t in _GOLD["typologies"] if t.get("typology_id") == "SAN006")["citations"][:1]]

from mcp_server import knowledge_centre_server as kc  # noqa: E402
```

If `import json` is not already in the file's import block, add it. Add `citations=CITE,` to each of the four `_call(kc.propose_link, kc.ProposeLinkInput, …)` calls (the `bad`, `good`, `untwinned` and `ok` calls), directly after the `confidence=…` keyword. Then, in `main()`, directly after `args = ap.parse_args(argv)`, add:

```python
    if not PDF.exists():
        print("CANNOT RUN: %s is not on this machine (data/advisories/ is gitignored).\n"
              "Nothing was checked; this is not a pass." % PDF.relative_to(ROOT))
        return 2
```

- [ ] **Step 9: Run the twin guard both ways**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_twin_pairs.py; echo "exit=$?"
PYTHONPYCACHEPREFIX=/tmp/fc08-mut-twin .venv/bin/python evals/check_twin_pairs.py --mutate; echo "exit=$?"
```
Expected: `HELD (0 failures)` exit 0; the mutate run reports its twin checks failing and ends `HELD: …`, exit 0, as before this task.

- [ ] **Step 10: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add agents/run_identity.py mcp_server/knowledge_centre_server.py evals/check_proposal_contract.py evals/check_twin_pairs.py && git commit -m "Week 5 A3: propose_link requires a run identity and verified quotes

The runner now tells the server who the run is; propose_link refuses a
proposal with no run identity, for another advisory, over a document
whose hash is not the run's, or quoting text not on the page it names.
Accepted proposals are written as proposal/2 lines carrying run, stage,
document hash and citations.

evals/check_proposal_contract.py: 11 checks, including that a correct
proposal is ACCEPTED; mutation-verified two ways. check_twin_pairs.py
moved to the new contract with a real identity and quote, so a refusal
it sees is the twin rule."
```

---

### Task 4: Every run carries its identity

**Files:**
- Modify: `agents/extract_advisory.py` (imports ~l.40-48; `PROPOSALS_PATH` l.57; `SYSTEM_PROMPT` last bullet; `sha256_of` l.98-103; `mcp_servers` l.136-144; `agent_options` l.147-183; `extract` l.191-235)
- Modify: `agents/review_advisory.py` (imports l.73; `REVIEWER_PROMPT` propose bullet l.129; `review` l.155-159)
- Modify: `evals/check_tool_surface.py` (import l.45; `static_checks`; `live_probe`)

**Interfaces:**
- Consumes: `RunIdentity`, `QUEUE_DIR` (Task 3).
- Produces: `mcp_servers(run: RunIdentity) -> dict`; `agent_options(model: str, max_budget_usd: float, max_turns: int, run: RunIdentity) -> ClaudeAgentOptions`; `extract(...)` telemetry gains `run_id` and `queue_path`.

- [ ] **Step 1: Add the failing static checks to `evals/check_tool_surface.py`.** Replace line 45 (`from agents.extract_advisory import KC_TOOLS, SERVER_KEY, agent_options  # noqa: E402`) with:

```python
from agents.extract_advisory import KC_TOOLS, SERVER_KEY, agent_options  # noqa: E402
from agents.run_identity import QUEUE_DIR, RunIdentity  # noqa: E402

# A fixed identity for the guard's own runs. The bait never calls propose_link,
# so the hash is never checked; the env must still be complete.
PROBE_RUN = RunIdentity(run_id="probe-tool-surface", stage="extractor", advisory_id="ADV-2026-0001",
                        pdf_path=ROOT / "data" / "advisories" / "fatf-tbml-2020.pdf", pdf_sha256="0" * 64)
```

In `static_checks()`, change `o = agent_options("claude-sonnet-5", 1.0, 3)` to `o = agent_options("claude-sonnet-5", 1.0, 3, PROBE_RUN)`, and add before `return out`:

```python
    env = o.mcp_servers[SERVER_KEY]["env"]
    missing = [k for k in ("NEXUS_RUN_ID", "NEXUS_STAGE", "NEXUS_ADVISORY_ID", "NEXUS_PDF_PATH",
                           "NEXUS_PDF_SHA256", "NEXUS_PROPOSALS_PATH") if not env.get(k)]
    out.append((not missing, "the MCP server is started with the run's identity",
                "missing: %s" % missing if missing else "all six values present"))
    out.append((Path(env.get("NEXUS_PROPOSALS_PATH", "")).parent == QUEUE_DIR,
                "proposals go to the run's own tracked file under data/proposals/",
                env.get("NEXUS_PROPOSALS_PATH", "")))
```

In `live_probe`, change `o = agent_options("claude-sonnet-5", 1.0, 6)` to `o = agent_options("claude-sonnet-5", 1.0, 6, PROBE_RUN)`.

- [ ] **Step 2: Run the static checks and watch them fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_tool_surface.py`
Expected: `TypeError: agent_options() takes 3 positional arguments but 4 were given`.

- [ ] **Step 3: Change `agents/extract_advisory.py`.**

(a) After `from schemas.advisory import AdvisoryRecord  # noqa: E402` add:

```python
from agents.run_identity import RunIdentity  # noqa: E402
from schemas.citation_match import file_sha256  # noqa: E402
```

(b) Delete the line `PROPOSALS_PATH = ROOT / "data" / "proposals.jsonl"`.

(c) Replace the whole `def sha256_of(path: Path) -> str:` function with:

```python
def sha256_of(path: Path) -> str:
    return file_sha256(path)
```

(d) In `SYSTEM_PROMPT`, replace the last bullet (the one starting `- Before you finish, call knowledge_centre_propose_link once per typology`) with:

```
- Before you finish, call knowledge_centre_propose_link once per typology in your record: with typology_id for a library match, with emergent_label for an emergent one. Pass the same citations as the record entry (page and verbatim quote); a quote that is not on the page it names is refused, and the refusal says where it is. Cite page numbers in the rationale.
```

(e) Replace `mcp_servers` with:

```python
def mcp_servers(run: RunIdentity) -> dict:
    return {
        SERVER_KEY: {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(SERVER_PATH)],
            # The run's identity reaches the server here and only here. The agent
            # cannot set or change it (week 5, agents/run_identity.py).
            "env": {"NEXUS_TYPOLOGY_PATH": str(LIBRARY_PATH), **run.env()},
        }
    }
```

(f) Change `def agent_options(model: str, max_budget_usd: float, max_turns: int) -> ClaudeAgentOptions:` to `def agent_options(model: str, max_budget_usd: float, max_turns: int, run: RunIdentity) -> ClaudeAgentOptions:`, and inside it `mcp_servers=mcp_servers(),` to `mcp_servers=mcp_servers(run),`.

(g) In `extract()`, replace these two lines:

```python
    proposals_before = _count_lines(PROPOSALS_PATH)

    options = agent_options(model, max_budget_usd, max_turns)
```

with:

```python
    run = RunIdentity.new("extractor", advisory_id, path)
    options = agent_options(model, max_budget_usd, max_turns, run)
```

and replace `        "proposals_written": _count_lines(PROPOSALS_PATH) - proposals_before,` with:

```python
        "run_id": run.run_id,
        "queue_path": str(run.queue_path.relative_to(ROOT)),
        "proposals_written": _count_lines(run.queue_path),
```

- [ ] **Step 4: Change `agents/review_advisory.py`.**

(a) After `from agents.extract_advisory import agent_options, library_ids, pdf_to_pages  # noqa: E402` add `from agents.run_identity import RunIdentity  # noqa: E402`.

(b) In `REVIEWER_PROMPT`, replace `- Call knowledge_centre_propose_link once per addition before you finish.` with `- Call knowledge_centre_propose_link once per addition before you finish, passing the addition's citations (page and verbatim quote). A quote that is not on the page it names is refused.`

(c) In `review()`, replace `        agent_options(model, max_budget_usd, max_turns),` with `        agent_options(model, max_budget_usd, max_turns, RunIdentity.new("reviewer", record["advisory_id"], pdf)),`.

- [ ] **Step 5: Run every static guard**

```bash
cd ~/fc-08-emerging-threat-intelligence && for g in check_tool_surface check_added_by check_twin_pairs check_emergent_threshold check_proposal_contract; do printf "%-26s" $g; .venv/bin/python evals/$g.py > /tmp/fc08-g.out 2>&1; echo "exit=$? $(tail -1 /tmp/fc08-g.out)"; done; grep -rn "PROPOSALS_PATH" agents/ || echo "no stale PROPOSALS_PATH in agents/"
```
Expected: five lines `exit=0 HELD (0 failures)`; then `no stale PROPOSALS_PATH in agents/`.

- [ ] **Step 6: One live extraction under the new contract.** ADV-2026-0013 is the shortest advisory (6 pages). Check auth first. The record goes to scratch, never `data/records/`.

```bash
cd ~/fc-08-emerging-threat-intelligence && unset ANTHROPIC_API_KEY && claude auth status | grep -i -E "loggedIn|authMethod"
```
Expected: `loggedIn: true`. If not, stop and tell the owner — only they can log in.

```bash
cd ~/fc-08-emerging-threat-intelligence && unset ANTHROPIC_API_KEY && F=$(.venv/bin/python -c "import json;print([a['file'] for a in json.load(open('evals/golden/advisory_list.json'))['advisories'] if a['advisory_id']=='ADV-2026-0013'][0])") && .venv/bin/python agents/extract_advisory.py "data/advisories/$F" --advisory-id ADV-2026-0013 --out /tmp/fc08-live-0013.json; echo "exit=$?"
```
Expected: exit 0; a `Telemetry:` line with `run_id`, `queue_path` under `data/proposals/`, and `proposals_written` of at least 1.

- [ ] **Step 7: Verify what the live run wrote**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python - <<'PY'
import json, glob, sys
sys.path.insert(0, ".")
from schemas.citation_match import PageIndex
files = sorted(glob.glob("data/proposals/adv-2026-0013-extractor-*.jsonl"))
lines = [json.loads(l) for f in files for l in open(f) if l.strip()]
L = {a["advisory_id"]: a for a in json.load(open("evals/golden/advisory_list.json"))["advisories"]}
idx = PageIndex.from_pdf("data/advisories/" + L["ADV-2026-0013"]["file"].split("/")[-1])
bad = [(l["proposal_id"], c["page"]) for l in lines for c in l["citations"] if not idx.locate(c["page"], c["quote"]).ok]
print("files", len(files), "| lines", len(lines), "| all proposal/2", all(l["schema"] == "proposal/2" for l in lines),
      "| every line cited", all(l["citations"] for l in lines), "| unverifiable quotes", bad)
PY
```
Expected: `files 1`, `lines` at least 1, `all proposal/2 True`, `every line cited True`, `unverifiable quotes []`. Note the line count for the commit message.

- [ ] **Step 8: Commit, including the run's queue file as the first `proposal/2` evidence.** Replace `<N>` with the line count from Step 7 before running.

```bash
cd ~/fc-08-emerging-threat-intelligence && git add agents/extract_advisory.py agents/review_advisory.py evals/check_tool_surface.py data/proposals/ && git commit -m "Week 5 A4: every extraction and review run carries its identity

agent_options takes a RunIdentity; the MCP server is started with the
run id, stage, advisory and document hash, and writes to the run's own
tracked queue file. Prompts now ask for citations on each proposal; the
server enforces it. check_tool_surface pins the six env values.

Live on ADV-2026-0013: <N> proposal/2 lines, every one cited, every
quote re-verified on its page. Queue file committed as the first
evidence under the new contract."
```

---

### Task 5: The gate's view of the queue — load, re-check, group

**Files:**
- Create: `governance/__init__.py` (empty), `governance/proposals.py`, `evals/check_review_gate.py`

**Interfaces:**
- Consumes: `schemas.citation_match.PageIndex`, `norm`, `file_sha256`.
- Produces (in `governance/proposals.py`): constants `ROOT, QUEUE_DIR, LEGACY_QUEUE, ADVISORY_LIST, ADVISORIES_DIR, LIBRARY, SCHEMA`; `quote_hash(page: int, quote: str) -> str`; `link_key(advisory_id: str, typology_id: str | None, emergent_label: str | None) -> str` (governed `"ADV-…::TID"`, emergent `"ADV-…::EMERGENT[<label lowercased, whitespace collapsed>]"`); frozen dataclass `Proposal` (fields as the queue line, `citations: tuple[tuple[int, str], ...]`; `.kind`, `.link_key`; `Proposal.from_line(d)`); frozen dataclass `Quarantined(proposal, reason)`; dataclass `Link(key, advisory_id, typology_id, emergent_label, proposals)` with `.kind`, `.quotes() -> list[tuple[int, str, int]]`, `.quote_hashes() -> frozenset[str]`, `.proposal_ids`, `.run_ids`, `.stages`; `load_queue(queue_dir=QUEUE_DIR) -> tuple[list[Proposal], list[str]]`; `recheck(proposals, advisory_list=ADVISORY_LIST, advisories_dir=ADVISORIES_DIR, library=LIBRARY) -> tuple[list[Proposal], list[Quarantined]]`; `group(proposals) -> dict[str, Link]`; `quarantined_links(quarantined, links) -> dict[str, str]`.

- [ ] **Step 1: Write the failing guard `evals/check_review_gate.py` (queue section)**

```python
"""
Pin the review gate: what reaches a human, and what a decision can and cannot do.

Usage:
    python evals/check_review_gate.py
    python evals/check_review_gate.py --mutate quarantine   # re-check disabled; tampered proposal MUST surface
    python evals/check_review_gate.py --mutate overturn     # decided links reopen; overturn MUST go through
    python evals/check_review_gate.py --mutate evidence     # new quotes ignored; new evidence MUST stay hidden

Builds a throwaway queue from REAL quotes in the ADV-2026-0002 golden label, plus
one tampered proposal and one legacy line, and drives governance/ against it.
Nothing here touches data/proposals/, the decision log or the approvals files.

NEEDS the ADV-2026-0002 PDF in data/advisories/ (gitignored). Without it this
exits 2 and says so.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import proposals as gp  # noqa: E402

ADVISORY = "ADV-2026-0002"
_LIST = {a["advisory_id"]: a for a in json.loads(gp.ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
PDF = gp.ADVISORIES_DIR / Path(_LIST[ADVISORY]["file"]).name
SHA = _LIST[ADVISORY]["sha256"]
WORK = Path(tempfile.mkdtemp(prefix="fc08_gate_"))
QUEUE_DIR = WORK / "proposals"


def _gold_citations() -> list:
    """(typology_id, page, quote) for every citation in the golden label, in order."""
    g = json.loads((ROOT / "evals" / "golden" / ("%s.json" % ADVISORY)).read_text(encoding="utf-8"))
    return [(t["typology_id"], c["page"], c["quote"]) for t in g["typologies"] if t.get("typology_id")
            for c in t["citations"]]


def _line(run_id: str, pid: str, typology_id, emergent_label, page: int, quote: str) -> dict:
    return {"schema": "proposal/2", "proposal_id": pid, "proposed_at": "2026-09-24T12:00:00+00:00",
            "run_id": run_id, "stage": "extractor", "advisory_id": ADVISORY, "document_sha256": SHA,
            "typology_id": typology_id, "emergent_label": emergent_label,
            "rationale": "Guard fixture rationale for %s." % (typology_id or emergent_label),
            "confidence": "medium", "citations": [{"page": page, "quote": quote}]}


def build_fixture() -> dict:
    """Write the throwaway queue. Returns the witness keys the checks refer to."""
    cites = _gold_citations()
    a_tid, a_page, a_quote = cites[0]
    # A different typology for the tampered proposal, so quarantine is visible per link.
    t_tid = next(t for t, _, _ in cites if t != a_tid)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    rows_1 = [
        _line("run-one", "p-a1", a_tid, None, a_page, a_quote),
        _line("run-one", "p-e1", None, "Guard  Witness emergent technique", a_page, a_quote),
        _line("run-one", "p-t1", t_tid, None, a_page, a_quote + " FABRICATED BY THE GUARD"),
        {"advisory_id": ADVISORY, "typology_id": a_tid, "status": "pending_review"},  # legacy shape
    ]
    rows_2 = [_line("run-two", "p-a2", a_tid, None, a_page, a_quote)]  # same link, same quote, second run
    (QUEUE_DIR / "run-one.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_1), encoding="utf-8")
    (QUEUE_DIR / "run-two.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_2), encoding="utf-8")
    new_quote = next((p, q) for t, p, q in cites if (p, q) != (a_page, a_quote))
    return {"a_key": gp.link_key(ADVISORY, a_tid, None), "t_key": gp.link_key(ADVISORY, t_tid, None),
            "e_key": gp.link_key(ADVISORY, None, "guard witness emergent technique"),
            "a_tid": a_tid, "new_quote": new_quote}


def queue_checks(w: dict) -> list:
    out = []
    proposals, skipped = gp.load_queue(QUEUE_DIR)
    out.append((len(proposals) == 4 and len(skipped) == 1,
                "load_queue reads proposal/2 lines and REPORTS the legacy line it skips",
                "%d proposals, skipped: %s" % (len(proposals), skipped)))
    clean, quarantined = gp.recheck(proposals)
    out.append(([q.proposal.proposal_id for q in quarantined] == ["p-t1"],
                "re-check QUARANTINES exactly the tampered proposal",
                "; ".join("%s: %s" % (q.proposal.proposal_id, q.reason) for q in quarantined) or "none"))
    out.append((any("page" in q.reason for q in quarantined),
                "the quarantine reason names the page", quarantined[0].reason if quarantined else "none"))
    links = gp.group(clean)
    out.append((sorted(links) == sorted([w["a_key"], w["e_key"]]),
                "clean proposals group into one link per advisory+typology or emergent label",
                str(sorted(links))))
    a = links.get(w["a_key"])
    out.append((a is not None and a.run_ids == ("run-one", "run-two") and len(a.quotes()) == 1
                and a.quotes()[0][2] == 2,
                "a link collects every run; the repeated quote is shown ONCE with a count of 2",
                "runs %s, quotes %s" % (a.run_ids, a.quotes()) if a else "missing"))
    out.append((links.get(w["e_key"]) is not None and links[w["e_key"]].kind == "emergent",
                "emergent labels are matched case- and space-insensitively and kept as emergent",
                str(sorted(links))[:120]))
    q_links = gp.quarantined_links(quarantined, links)
    out.append((list(q_links) == [w["t_key"]],
                "a link with NO clean proposal is reported as quarantined, not presented",
                str(q_links)))
    return out


def all_checks() -> list:
    w = build_fixture()
    return queue_checks(w)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the review gate")
    ap.add_argument("--mutate", choices=("quarantine", "overturn", "evidence"),
                    help="remove one gate rule; the checks that depend on it MUST fail")
    args = ap.parse_args(argv)

    if not PDF.exists():
        print("CANNOT RUN: %s is not on this machine (data/advisories/ is gitignored).\n"
              "Nothing was checked; this is not a pass." % PDF.relative_to(ROOT))
        return 2

    if args.mutate == "quarantine":
        gp.recheck = lambda proposals, *a, **k: (list(proposals), [])
        print("MUTATED: the review-time re-check is removed.\n")

    failures = 0
    for ok, label, detail in all_checks():
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

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_review_gate.py`
Expected: `ModuleNotFoundError: No module named 'governance'`.

- [ ] **Step 3: Create `governance/__init__.py`** as an empty file, and `governance/proposals.py`:

```python
"""
The review gate's view of the proposal queue: load, re-check, group.

Proposals are written by the MCP server (propose_link) into one tracked file per
run under data/proposals/. The server already verified every quote. This module
verifies them AGAIN, because the queue is a plain file and anything could have
changed it since -- a proposal that fails is quarantined: shown with its reason,
never approvable.

A LINK is what a human decides: one advisory + one typology (or one emergent
label), collecting every proposal behind it from every run. One decision per
link, not per proposal -- measured 2026-09-24, one legacy link was proposed 11
times.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import PageIndex, file_sha256, norm  # noqa: E402

QUEUE_DIR = ROOT / "data" / "proposals"
LEGACY_QUEUE = ROOT / "data" / "proposals_legacy_2026-09-10_to_13.jsonl"
ADVISORY_LIST = ROOT / "evals" / "golden" / "advisory_list.json"
ADVISORIES_DIR = ROOT / "data" / "advisories"
LIBRARY = ROOT / "data" / "typologies.json"
SCHEMA = "proposal/2"


def quote_hash(page: int, quote: str) -> str:
    return hashlib.sha256(("%d|%s" % (page, norm(quote))).encode("utf-8")).hexdigest()[:16]


def link_key(advisory_id: str, typology_id: Optional[str], emergent_label: Optional[str]) -> str:
    if typology_id:
        return "%s::%s" % (advisory_id, typology_id)
    return "%s::EMERGENT[%s]" % (advisory_id, " ".join((emergent_label or "").split()).lower())


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    proposed_at: str
    run_id: str
    stage: str
    advisory_id: str
    document_sha256: str
    typology_id: Optional[str]
    emergent_label: Optional[str]
    rationale: str
    confidence: str
    citations: Tuple[Tuple[int, str], ...]

    @classmethod
    def from_line(cls, d: dict) -> "Proposal":
        return cls(proposal_id=d["proposal_id"], proposed_at=d["proposed_at"], run_id=d["run_id"],
                   stage=d["stage"], advisory_id=d["advisory_id"], document_sha256=d["document_sha256"],
                   typology_id=d.get("typology_id"), emergent_label=d.get("emergent_label"),
                   rationale=d["rationale"], confidence=d["confidence"],
                   citations=tuple((int(c["page"]), c["quote"]) for c in d["citations"]))

    @property
    def kind(self) -> str:
        return "governed" if self.typology_id else "emergent"

    @property
    def link_key(self) -> str:
        return link_key(self.advisory_id, self.typology_id, self.emergent_label)


@dataclass(frozen=True)
class Quarantined:
    proposal: Proposal
    reason: str


@dataclass
class Link:
    key: str
    advisory_id: str
    typology_id: Optional[str]
    emergent_label: Optional[str]
    proposals: List[Proposal] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "governed" if self.typology_id else "emergent"

    def quotes(self) -> List[Tuple[int, str, int]]:
        """Distinct quotes in page order, each with how many proposals carried it."""
        seen: Dict[str, list] = {}
        for p in self.proposals:
            for page, q in p.citations:
                h = quote_hash(page, q)
                if h in seen:
                    seen[h][2] += 1
                else:
                    seen[h] = [page, q, 1]
        return sorted((tuple(v) for v in seen.values()), key=lambda t: (t[0], t[1]))

    def quote_hashes(self) -> frozenset:
        return frozenset(quote_hash(pg, q) for p in self.proposals for pg, q in p.citations)

    @property
    def proposal_ids(self) -> Tuple[str, ...]:
        return tuple(sorted({p.proposal_id for p in self.proposals}))

    @property
    def run_ids(self) -> Tuple[str, ...]:
        return tuple(sorted({p.run_id for p in self.proposals}))

    @property
    def stages(self) -> Tuple[str, ...]:
        return tuple(sorted({p.stage for p in self.proposals}))


def load_queue(queue_dir: Path = QUEUE_DIR) -> Tuple[List[Proposal], List[str]]:
    """Every proposal/2 line under queue_dir, and one note per line skipped -- none vanish silently."""
    proposals: List[Proposal] = []
    skipped: List[str] = []
    for path in (sorted(queue_dir.glob("*.jsonl")) if queue_dir.exists() else []):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                skipped.append("%s:%d is not JSON" % (path.name, n))
                continue
            if d.get("schema") != SCHEMA:
                skipped.append("%s:%d has schema %r, not %s" % (path.name, n, d.get("schema"), SCHEMA))
                continue
            try:
                proposals.append(Proposal.from_line(d))
            except (KeyError, TypeError, ValueError) as exc:
                skipped.append("%s:%d is malformed (%s)" % (path.name, n, exc))
    return proposals, skipped


def _advisories(path: Path) -> Dict[str, dict]:
    return {a["advisory_id"]: a for a in json.loads(path.read_text(encoding="utf-8"))["advisories"]}


def _library_ids(path: Path) -> frozenset:
    return frozenset(t["typology_id"] for t in json.loads(path.read_text(encoding="utf-8"))["typologies"])


def recheck(proposals, advisory_list: Path = ADVISORY_LIST, advisories_dir: Path = ADVISORIES_DIR,
            library: Path = LIBRARY) -> Tuple[List[Proposal], List[Quarantined]]:
    """Split proposals into clean and quarantined. A quarantined proposal can never be approved."""
    advisories = _advisories(advisory_list)
    known = _library_ids(library)
    indexes: Dict[str, Optional[PageIndex]] = {}
    clean: List[Proposal] = []
    quarantined: List[Quarantined] = []

    def index_for(a: dict) -> Optional[PageIndex]:
        aid = a["advisory_id"]
        if aid not in indexes:
            pdf = advisories_dir / Path(a["file"]).name
            ok = pdf.exists() and file_sha256(pdf) == a["sha256"]
            indexes[aid] = PageIndex.from_pdf(pdf) if ok else None
        return indexes[aid]

    for p in proposals:
        a = advisories.get(p.advisory_id)
        reason = None
        if a is None:
            reason = "advisory %s is not in the advisory list" % p.advisory_id
        elif p.document_sha256 != a["sha256"]:
            reason = ("document hash %s... is not the advisory list's %s..."
                      % (p.document_sha256[:12], a["sha256"][:12]))
        elif p.typology_id and p.typology_id not in known:
            reason = "%s is not in the library" % p.typology_id
        elif not p.citations:
            reason = "no citations"
        else:
            index = index_for(a)
            if index is None:
                reason = ("the source PDF for %s is missing or does not match its hash on this machine; "
                          "its quotes cannot be re-checked" % p.advisory_id)
            else:
                bad = [(pg, q) for pg, q in p.citations if not index.locate(pg, q).ok]
                if bad:
                    reason = "quote not on page %d: %r" % (bad[0][0], bad[0][1][:70])
        if reason:
            quarantined.append(Quarantined(p, reason))
        else:
            clean.append(p)
    return clean, quarantined


def group(proposals) -> Dict[str, Link]:
    links: Dict[str, Link] = {}
    for p in sorted(proposals, key=lambda p: (p.link_key, p.proposed_at, p.proposal_id)):
        link = links.get(p.link_key)
        if link is None:
            link = links[p.link_key] = Link(p.link_key, p.advisory_id, p.typology_id, p.emergent_label)
        link.proposals.append(p)
    return dict(sorted(links.items()))


def quarantined_links(quarantined, links: Dict[str, Link]) -> Dict[str, str]:
    """Link keys whose EVERY proposal was quarantined, with the first reason."""
    out: Dict[str, str] = {}
    for q in quarantined:
        key = q.proposal.link_key
        if key not in links and key not in out:
            out[key] = q.reason
    return dict(sorted(out.items()))
```

- [ ] **Step 4: Run the guard and the quarantine mutation**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_review_gate.py; echo "exit=$?"
PYTHONPYCACHEPREFIX=/tmp/fc08-mut-q .venv/bin/python evals/check_review_gate.py --mutate quarantine; echo "exit=$?"
```
Expected: 7 PASS, `HELD (0 failures)`, exit 0; the mutation fails the quarantine, grouping and quarantined-link checks and ends `HELD: the probe detects the defect when the rule is removed`, exit 0.

- [ ] **Step 5: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add governance/__init__.py governance/proposals.py evals/check_review_gate.py && git commit -m "Week 5 A5: the gate's view of the queue -- load, re-check, group

governance/proposals.py reads proposal/2 lines from data/proposals/,
reports every line it skips, re-verifies each quote against its PDF
(quarantining failures, which can never be approved), and groups what is
clean into one link per advisory+typology or emergent label.

evals/check_review_gate.py drives it over a throwaway queue built from
real ADV-2026-0002 golden quotes plus a tampered proposal; 7 checks,
mutation-verified by removing the re-check."
```

---

### Task 6: Decisions — the log, the refusals, the rebuilt approvals

**Files:**
- Create: `governance/decisions.py`
- Modify: `evals/check_review_gate.py` (import; add `decision_checks`; extend `all_checks` and the mutations)

**Interfaces:**
- Consumes: `governance.proposals.ROOT`, `Link` (Task 5).
- Produces: constants `LOG, APPROVED_LINKS, APPROVED_EMERGENT`; `OPEN, DECIDED, NEW_EVIDENCE`; `DECISIONS = ("approve", "reject")`; `class GateRefusal(Exception)`; frozen dataclass `Decision(decided_at, link_key, kind, advisory_id, typology_id, emergent_label, decision, note, proposal_ids: tuple, run_ids: tuple, quotes_seen_sha256: tuple)` with `.to_line() -> str` and `Decision.from_line(d)`; `load_log(path=LOG) -> list[Decision]`; `latest(decisions) -> dict[str, Decision]`; `state(link, prior) -> str`; `apply(requests: list[tuple[str, str, str]], links, quarantined: dict[str, str], log_path=LOG, now: str | None = None) -> list[Decision]`; `rebuild(decisions) -> tuple[str, str]`; `write_approved(decisions, links_path=APPROVED_LINKS, emergent_path=APPROVED_EMERGENT) -> None`; `check_approved(decisions, links_path=APPROVED_LINKS, emergent_path=APPROVED_EMERGENT) -> list[str]`.

- [ ] **Step 1: Add the failing decision checks to `evals/check_review_gate.py`.** After `from governance import proposals as gp  # noqa: E402` add `from governance import decisions as gd  # noqa: E402`. Add this function after `queue_checks`:

```python
def decision_checks(w: dict) -> list:
    out = []
    log = WORK / "review_decisions.jsonl"
    links_path, emergent_path = WORK / "approved_links.json", WORK / "approved_emergent.json"
    proposals, _ = gp.load_queue(QUEUE_DIR)
    clean, quarantined = gp.recheck(proposals)
    links = gp.group(clean)
    q_links = gp.quarantined_links(quarantined, links)

    def refused(requests) -> str:
        """The refusal message, or '' if apply accepted. Flags a refusal that wrote anyway."""
        before = log.read_text(encoding="utf-8") if log.exists() else ""
        try:
            gd.apply(requests, links, q_links, log_path=log, now="2026-09-24T13:00:00+00:00")
        except gd.GateRefusal as exc:
            after = log.read_text(encoding="utf-8") if log.exists() else ""
            return str(exc) if before == after else "REFUSED BUT WROTE: %s" % exc
        return ""

    a_link = links.get(w["a_key"])
    out.append((a_link is not None and gd.state(a_link, None) == gd.OPEN, "an undecided link is OPEN", ""))

    made = gd.apply([(w["a_key"], "approve", "fixture approve"), (w["e_key"], "reject", "")],
                    links, q_links, log_path=log, now="2026-09-24T13:00:00+00:00")
    rows = gd.load_log(log)
    out.append((len(made) == 2 and len(rows) == 2 and rows[0].run_ids == ("run-one", "run-two")
                and rows[0].advisory_id == ADVISORY and rows[0].typology_id == w["a_tid"],
                "apply appends one line per decision, carrying runs, advisory and typology",
                "%d lines" % len(rows)))

    gd.write_approved(gd.load_log(log), links_path, emergent_path)
    approved = json.loads(links_path.read_text(encoding="utf-8"))["approved"]
    emergent = json.loads(emergent_path.read_text(encoding="utf-8"))["approved"]
    out.append(([r["link_key"] for r in approved] == [w["a_key"]] and emergent == [],
                "approvals are rebuilt from the log; a REJECTED emergent is in neither file",
                "links %s, emergent %s" % ([r["link_key"] for r in approved], emergent)))

    msg = refused([(w["a_key"], "reject", "change of mind")])
    out.append(("change of mind" in msg and "REFUSED BUT WROTE" not in msg,
                "overturning a decided link is REFUSED and writes nothing", msg[:120]))

    msg = refused([(w["t_key"], "approve", "")])
    out.append(("quarantined" in msg, "a quarantined link cannot be approved", msg[:120]))

    msg = refused([("ADV-2026-0002::NOPE999", "approve", "")])
    out.append(("no reviewable link" in msg, "an unknown link is refused", msg[:120]))

    lines_before = len(gd.load_log(log))
    msg = refused([(w["e_key"], "approve", ""), (w["e_key"], "approve", "")])
    out.append(("twice" in msg and len(gd.load_log(log)) == lines_before,
                "a link decided twice in one list is refused, and NOTHING from that list is written",
                msg[:120]))

    # New evidence: a third run proposes the approved link with a quote not seen before.
    page, quote = w["new_quote"]
    third = QUEUE_DIR / "run-three.jsonl"
    third.write_text(json.dumps(_line("run-three", "p-a3", w["a_tid"], None, page, quote)) + "\n",
                     encoding="utf-8")
    clean3, quarantined3 = gp.recheck(gp.load_queue(QUEUE_DIR)[0])
    links3 = gp.group(clean3)
    prior = gd.latest(gd.load_log(log))
    now_state = gd.state(links3[w["a_key"]], prior.get(w["a_key"]))
    out.append((now_state == gd.NEW_EVIDENCE,
                "a decided link RETURNS when a later run brings a quote not seen before", now_state))
    try:
        gd.apply([(w["a_key"], "reject", "new evidence changes it")], links3,
                 gp.quarantined_links(quarantined3, links3), log_path=log, now="2026-09-24T14:00:00+00:00")
    except gd.GateRefusal as exc:
        out.append((False, "deciding new evidence is accepted", str(exc)[:120]))
    rows = gd.load_log(log)
    out.append((len(rows) == 3 and rows[0].decision == "approve" and rows[-1].decision == "reject",
                "deciding new evidence APPENDS a line; the earlier line is untouched",
                [r.decision for r in rows]))
    third.unlink()

    gd.write_approved(gd.load_log(log), links_path, emergent_path)
    out.append((gd.check_approved(gd.load_log(log), links_path, emergent_path) == [],
                "check_approved passes on files rebuilt from the log", ""))
    links_path.write_text(links_path.read_text(encoding="utf-8").replace("[]", '[{"hand": "edit"}]'),
                          encoding="utf-8")
    problems = gd.check_approved(gd.load_log(log), links_path, emergent_path)
    out.append((bool(problems), "a HAND-EDITED approvals file is caught", "; ".join(problems)[:120]))
    out.append((gd.rebuild(gd.load_log(log)) == gd.rebuild(gd.load_log(log)), "rebuild is deterministic", ""))
    return out
```

Replace `all_checks` with:

```python
def all_checks() -> list:
    w = build_fixture()
    return queue_checks(w) + decision_checks(w)
```

In `main`, directly after the `quarantine` mutation branch, add:

```python
    elif args.mutate == "overturn":
        gd.state = lambda link, prior: gd.OPEN
        print("MUTATED: every link reads as OPEN, so a decided link can be overturned.\n")
    elif args.mutate == "evidence":
        gp.Link.quote_hashes = lambda self: frozenset()
        print("MUTATED: a link's quotes are ignored when deciding whether it has new evidence.\n")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_review_gate.py`
Expected: `ImportError: cannot import name 'decisions' from 'governance'`.

- [ ] **Step 3: Create `governance/decisions.py`**

```python
"""
The review gate's record: an append-only decision log, and the approvals rebuilt from it.

data/review_decisions.jsonl is the evidence. The two approvals files are DERIVED
from it, deterministically, every time -- so an approvals file can never say
something the log does not, and a hand edit is caught by check_approved. Nothing
else in the repository writes either file; evals/check_review_gate.py enforces it.

Refusals (GateRefusal), with NOTHING written -- the whole list is checked first:
  - the same link twice in one list;
  - a link that is not reviewable (unknown, or every proposal quarantined);
  - a link already decided with no new evidence: a change of mind needs its own
    dated record. A later run bringing a quote not seen before reopens the link;
    deciding it APPENDS, and the earlier line is never edited.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from governance.proposals import ROOT, Link

LOG = ROOT / "data" / "review_decisions.jsonl"
APPROVED_LINKS = ROOT / "data" / "approved_links.json"
APPROVED_EMERGENT = ROOT / "data" / "approved_emergent.json"
OPEN, DECIDED, NEW_EVIDENCE = "open", "decided", "new_evidence"
DECISIONS = ("approve", "reject")


class GateRefusal(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    decided_at: str
    link_key: str
    kind: str
    advisory_id: str
    typology_id: Optional[str]
    emergent_label: Optional[str]
    decision: str
    note: str
    proposal_ids: Tuple[str, ...]
    run_ids: Tuple[str, ...]
    quotes_seen_sha256: Tuple[str, ...]

    def to_line(self) -> str:
        d = asdict(self)
        for k in ("proposal_ids", "run_ids", "quotes_seen_sha256"):
            d[k] = list(d[k])
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_line(cls, d: dict) -> "Decision":
        return cls(**{**d, "proposal_ids": tuple(d["proposal_ids"]), "run_ids": tuple(d["run_ids"]),
                      "quotes_seen_sha256": tuple(d["quotes_seen_sha256"])})


def load_log(path: Path = LOG) -> List[Decision]:
    if not path.exists():
        return []
    return [Decision.from_line(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def latest(decisions) -> Dict[str, Decision]:
    """The standing decision per link: the log is append-only, so the last line wins."""
    out: Dict[str, Decision] = {}
    for d in decisions:
        out[d.link_key] = d
    return out


def state(link: Link, prior: Optional[Decision]) -> str:
    if prior is None:
        return OPEN
    return NEW_EVIDENCE if link.quote_hashes() - set(prior.quotes_seen_sha256) else DECIDED


def apply(requests, links: Dict[str, Link], quarantined: Dict[str, str], log_path: Path = LOG,
          now: Optional[str] = None) -> List[Decision]:
    """Check every (link_key, decision, note) request, then append them all -- or refuse and write nothing."""
    requests = list(requests)
    twice = sorted(k for k, n in Counter(k for k, _, _ in requests).items() if n > 1)
    if twice:
        raise GateRefusal("%s is decided twice in one list" % ", ".join(twice))
    prior = latest(load_log(log_path))
    stamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: List[Decision] = []
    for key, decision, note in requests:
        if decision not in DECISIONS:
            raise GateRefusal("%s: a decision is approve or reject, not %r" % (key, decision))
        if key not in links:
            if key in quarantined:
                raise GateRefusal("%s is quarantined and cannot be decided: %s" % (key, quarantined[key]))
            raise GateRefusal("no reviewable link %s" % key)
        link = links[key]
        if state(link, prior.get(key)) == DECIDED:
            p = prior[key]
            raise GateRefusal("%s was already decided (%s, %s) and no new evidence has arrived -- "
                              "a change of mind needs its own dated record" % (key, p.decision, p.decided_at[:10]))
        out.append(Decision(decided_at=stamp, link_key=key, kind=link.kind, advisory_id=link.advisory_id,
                            typology_id=link.typology_id, emergent_label=link.emergent_label,
                            decision=decision, note=(note or "").strip(), proposal_ids=link.proposal_ids,
                            run_ids=link.run_ids, quotes_seen_sha256=tuple(sorted(link.quote_hashes()))))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        for d in out:
            fh.write(d.to_line() + "\n")
    return out


def _rows(decisions, kind: str) -> list:
    rows = []
    for d in sorted(latest(decisions).values(), key=lambda d: d.link_key):
        if d.decision != "approve" or d.kind != kind:
            continue
        row = {"link_key": d.link_key, "advisory_id": d.advisory_id, "decided_at": d.decided_at,
               "note": d.note, "run_ids": list(d.run_ids), "proposal_ids": list(d.proposal_ids)}
        if kind == "governed":
            row["typology_id"] = d.typology_id
        else:
            row["emergent_label"] = d.emergent_label
        rows.append(row)
    return rows


def rebuild(decisions) -> Tuple[str, str]:
    """(links file text, emergent file text), byte-identical for the same log."""
    def dump(rows) -> str:
        return json.dumps({"generated_from": "data/review_decisions.jsonl", "approved": rows},
                          indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    decisions = list(decisions)
    return dump(_rows(decisions, "governed")), dump(_rows(decisions, "emergent"))


def write_approved(decisions, links_path: Path = APPROVED_LINKS, emergent_path: Path = APPROVED_EMERGENT) -> None:
    links_text, emergent_text = rebuild(decisions)
    links_path.parent.mkdir(parents=True, exist_ok=True)
    links_path.write_text(links_text, encoding="utf-8")
    emergent_path.write_text(emergent_text, encoding="utf-8")


def check_approved(decisions, links_path: Path = APPROVED_LINKS,
                   emergent_path: Path = APPROVED_EMERGENT) -> List[str]:
    """Problems, empty when the files are exactly what the log rebuilds to."""
    decisions = list(decisions)
    if not decisions and not links_path.exists() and not emergent_path.exists():
        return []
    problems = []
    for path, want in zip((links_path, emergent_path), rebuild(decisions)):
        if not path.exists():
            problems.append("%s is missing; rebuild with tools/review.py" % path.name)
        elif path.read_text(encoding="utf-8") != want:
            problems.append("%s does not match what the decision log rebuilds to" % path.name)
    return problems
```

- [ ] **Step 4: Run the guard and all three mutations**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_review_gate.py; echo "exit=$?"
for m in quarantine overturn evidence; do printf "%-11s" $m; PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_review_gate.py --mutate $m | tail -1; done
```
Expected: 19 PASS, `HELD (0 failures)`, exit 0. Each mutation ends `HELD: the probe detects the defect when the rule is removed`: `overturn` must fail "overturning a decided link is REFUSED"; `evidence` must fail "a decided link RETURNS…". If any mutation prints `NOTHING PROVED`, the check that should trip is not asserting what it claims — fix the check, never the mutation.

- [ ] **Step 5: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add governance/decisions.py evals/check_review_gate.py && git commit -m "Week 5 A6: decisions -- an append-only log, and approvals rebuilt from it

governance/decisions.py: one decision per link; refuses a link twice in
one list, an unknown or quarantined link, and overturning a decided link
without new evidence -- checking the whole list before writing any of
it. The approvals files are rebuilt from the log deterministically;
check_approved catches a hand edit.

check_review_gate.py: 19 checks, mutation-verified three ways
(re-check removed, overturn allowed, new evidence ignored)."
```

---

### Task 7: `tools/review.py` — the only writer

**Files:**
- Create: `governance/card.py`, `tools/review.py`
- Modify: `evals/check_review_gate.py` (import `subprocess`; add `cli_checks`; extend `all_checks`)

**Interfaces:**
- Consumes: everything in `governance.proposals` and `governance.decisions`.
- Produces: `governance.card.render(link, prior, advisories: dict, library: dict, golden_ids: set) -> str`; `tools/review.py` with `parse_decisions(text: str) -> list[tuple[str, str, str]]` and flags `--decisions FILE`, `--list`, `--check` (mutually exclusive; none = interactive), plus path overrides `--queue-dir`, `--log`, `--approved-links`, `--approved-emergent` defaulting to the `governance` constants. Decision-list lines: `ADV-2026-0002 BA008: approve -- note` or `ADV-2026-0002 EMERGENT[label]: reject -- note`; lines not starting `ADV-` are ignored.

- [ ] **Step 1: Add the failing CLI checks to `evals/check_review_gate.py`.** Add `import subprocess` to the imports, then this function after `decision_checks`:

```python
def cli_checks(w: dict) -> list:
    out = []
    cli = WORK / "cli"
    cli.mkdir(exist_ok=True)
    paths = ["--queue-dir", str(QUEUE_DIR), "--log", str(cli / "log.jsonl"),
             "--approved-links", str(cli / "links.json"), "--approved-emergent", str(cli / "emergent.json")]

    def run(*args, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "tools" / "review.py"), *args, *paths],
                              input=stdin, capture_output=True, text=True, cwd=ROOT)

    r = run("--list")
    out.append((r.returncode == 0 and w["a_key"] in r.stdout and "quarantined links: 1" in r.stdout
                and "skipped lines: 1" in r.stdout,
                "--list shows open links, the quarantined link and the skipped line", r.stdout[-200:]))

    decisions = cli / "decisions.txt"
    decisions.write_text("FC08 review decisions\n%s %s: approve -- from a pasted list\n"
                         % (ADVISORY, w["a_tid"]), encoding="utf-8")
    r = run("--decisions", str(decisions))
    links = json.loads((cli / "links.json").read_text(encoding="utf-8"))["approved"] \
        if (cli / "links.json").exists() else []
    out.append((r.returncode == 0 and [x["link_key"] for x in links] == [w["a_key"]],
                "--decisions applies a pasted list and rebuilds the approvals", (r.stdout + r.stderr)[-160:]))

    r = run("--decisions", str(decisions))
    out.append((r.returncode != 0 and "change of mind" in (r.stdout + r.stderr),
                "the same list again is REFUSED, exit non-zero", (r.stdout + r.stderr)[-120:]))

    r = run("--check")
    out.append((r.returncode == 0, "--check passes on files the CLI wrote", r.stdout[-100:]))
    (cli / "links.json").write_text("{}\n", encoding="utf-8")
    r = run("--check")
    out.append((r.returncode != 0, "--check FAILS on a hand-edited approvals file", r.stdout[-100:]))

    # Interactive: the only open link left in THIS log is the emergent one (A is
    # approved above, T is quarantined), so the first card is the emergent link.
    r = run(stdin="r\nno mechanism on the page\nq\n")
    log_file = cli / "log.jsonl"
    log = [json.loads(x) for x in log_file.read_text(encoding="utf-8").splitlines()] if log_file.exists() else []
    out.append((r.returncode == 0 and bool(log) and log[-1]["link_key"] == w["e_key"]
                and log[-1]["decision"] == "reject" and log[-1]["note"] == "no mechanism on the page",
                "interactive mode records a decision with its note through the same writer",
                (r.stdout + r.stderr)[-160:]))

    writers = []
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith((".venv/", "evals/")) or rel == "governance/decisions.py":
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        if "approved_links.json" in text or "approved_emergent.json" in text:
            writers.append(rel)
    out.append((writers == [], "NOTHING outside governance/decisions.py names the approvals files",
                "found in: %s" % writers if writers else "only the gate"))
    return out
```

Replace `all_checks` with:

```python
def all_checks() -> list:
    w = build_fixture()
    return queue_checks(w) + decision_checks(w) + cli_checks(w)
```

The CLI uses its own log under `WORK/cli`, so the decisions `decision_checks` made do not carry over.

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_review_gate.py`
Expected: the first 19 checks PASS; the CLI checks FAIL because `tools/review.py` does not exist, and the run ends `REFUSED (n failures)`. Two CLI checks pass vacuously at this point (the hand-edited `--check` one, since any non-zero exit satisfies it, and the no-writer scan) — they become meaningful once the CLI exists and the checks before them pass.

- [ ] **Step 3: Create `governance/card.py`**

```python
"""One link, rendered for a human deciding it. Plain text: it has to read in a terminal."""

from __future__ import annotations

import textwrap
from typing import Optional

from governance.decisions import Decision
from governance.proposals import Link


def _wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(" ".join(text.split()), width=96, initial_indent=indent, subsequent_indent=indent)


def render(link: Link, prior: Optional[Decision], advisories: dict, library: dict, golden_ids: set) -> str:
    a = advisories.get(link.advisory_id, {})
    lines = ["=" * 100, "%s  %s" % (link.advisory_id, a.get("title", "(title not in the advisory list)"))]
    if link.kind == "governed":
        t = library.get(link.typology_id, {})
        lines.append("PROPOSED LINK  %s  %s  [%s]" % (link.typology_id, t.get("label", "?"), t.get("family", "?")))
        if t.get("summary"):
            lines.append(_wrap(t["summary"]))
        held = link.typology_id in golden_ids
        lines.append("  golden label %s this link (context only, never a rule)" % ("HOLDS" if held else "LACKS"))
    else:
        lines.append("PROPOSED EMERGENT TYPOLOGY  %r" % link.emergent_label)
        lines.append("  not in the library; approving makes it a candidate for doctrine, not a link")
    if prior is not None:
        lines.append("  NEW EVIDENCE: previously %s on %s%s" % (
            prior.decision.upper(), prior.decided_at[:10], (" -- %s" % prior.note) if prior.note else ""))
    lines.append("QUOTES")
    for page, quote, count in link.quotes():
        lines.append("  p%-3d %s" % (page, "(x%d)" % count if count > 1 else ""))
        lines.append(_wrap("“%s”" % quote, "        "))
    rationales = sorted({p.rationale for p in link.proposals})
    lines.append("RATIONALE%s" % ("S" if len(rationales) > 1 else ""))
    for r in rationales:
        lines.append(_wrap(r))
    lines.append("FROM  %d proposal%s, runs: %s, stages: %s" % (
        len(link.proposals), "" if len(link.proposals) == 1 else "s", ", ".join(link.run_ids),
        ", ".join(link.stages)))
    return "\n".join(lines)
```

- [ ] **Step 4: Create `tools/review.py`**

```python
"""
The review gate: the ONLY way a proposal becomes an approved link.

Usage:
    python tools/review.py                      # step through open links: approve / reject / skip / quit
    python tools/review.py --list               # what is open, decided, new evidence, quarantined, skipped
    python tools/review.py --decisions FILE     # apply a pasted list (e.g. from a phone)
    python tools/review.py --check              # fail if the approvals files differ from the log

A decisions file holds one line per link; anything not starting "ADV-" is ignored:
    ADV-2026-0002 BA008: approve -- note
    ADV-2026-0002 EMERGENT[shadow fleet ship-to-ship transfer]: reject -- note

Both deciding modes go through governance.decisions.apply, which refuses an
unknown or quarantined link, a link twice in one list, and overturning a decided
link. Every decision is followed by rebuilding the approvals files from the
decision log, so the two can never disagree.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import card  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance import proposals as gp  # noqa: E402

LINE = re.compile(r"^(ADV-\d{4}-\d{4})\s+(?:([A-Z]{2,6}\d{3}[A-Z]?)|EMERGENT\[(.+?)\]):\s*(approve|reject)"
                  r"\s*(?:--\s*(.*))?$", re.I)


def parse_decisions(text: str) -> list:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("ADV-"):
            continue
        m = LINE.match(line)
        if not m:
            raise SystemExit("cannot read decision line: %r" % line)
        aid, tid, label, decision, note = m.groups()
        out.append((gp.link_key(aid, tid.upper() if tid else None, label), decision.lower(), (note or "").strip()))
    return out


def _load(args):
    proposals, skipped = gp.load_queue(args.queue_dir)
    clean, quarantined = gp.recheck(proposals)
    links = gp.group(clean)
    return links, gp.quarantined_links(quarantined, links), quarantined, skipped


def _context():
    advisories = {a["advisory_id"]: a for a in
                  json.loads(gp.ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    library = {t["typology_id"]: t for t in json.loads(gp.LIBRARY.read_text(encoding="utf-8"))["typologies"]}
    golden = {}
    for aid in advisories:
        path = ROOT / "evals" / "golden" / ("%s.json" % aid)
        if path.exists():
            golden[aid] = {t.get("typology_id") for t in json.loads(path.read_text(encoding="utf-8"))["typologies"]}
    return advisories, library, golden


def _finish(args) -> None:
    gd.write_approved(gd.load_log(args.log), args.approved_links, args.approved_emergent)


def cmd_list(args) -> int:
    links, q_links, quarantined, skipped = _load(args)
    prior = gd.latest(gd.load_log(args.log))
    by_state = {gd.OPEN: [], gd.NEW_EVIDENCE: [], gd.DECIDED: []}
    for key, link in links.items():
        by_state[gd.state(link, prior.get(key))].append(key)
    for name in (gd.OPEN, gd.NEW_EVIDENCE, gd.DECIDED):
        print("%s: %d" % (name.replace("_", " "), len(by_state[name])))
        for key in by_state[name]:
            print("  %s" % key)
    print("quarantined links: %d" % len(q_links))
    for key, reason in q_links.items():
        print("  %s -- %s" % (key, reason))
    print("quarantined proposals: %d | skipped lines: %d" % (len(quarantined), len(skipped)))
    for note in skipped:
        print("  skipped %s" % note)
    if gp.LEGACY_QUEUE.exists():
        print("legacy queue (frozen, never reviewed): %s" % gp.LEGACY_QUEUE.relative_to(ROOT))
    return 0


def cmd_decisions(args) -> int:
    links, q_links, _, _ = _load(args)
    requests = parse_decisions(args.decisions.read_text(encoding="utf-8"))
    try:
        made = gd.apply(requests, links, q_links, log_path=args.log)
    except gd.GateRefusal as exc:
        print("REFUSED, nothing written: %s" % exc, file=sys.stderr)
        return 1
    _finish(args)
    print("recorded %d decision%s; approvals rebuilt" % (len(made), "" if len(made) == 1 else "s"))
    return 0


def cmd_check(args) -> int:
    problems = gd.check_approved(gd.load_log(args.log), args.approved_links, args.approved_emergent)
    for p in problems:
        print("FAIL  %s" % p)
    print("approvals match the decision log" if not problems else "approvals DO NOT match the decision log")
    return 1 if problems else 0


def cmd_interactive(args) -> int:
    links, q_links, _, skipped = _load(args)
    advisories, library, golden = _context()
    prior = gd.latest(gd.load_log(args.log))
    todo = [k for k, link in links.items() if gd.state(link, prior.get(k)) != gd.DECIDED]
    print("%d link%s to review (%d quarantined, %d lines skipped)" % (
        len(todo), "" if len(todo) == 1 else "s", len(q_links), len(skipped)))
    decided = 0
    for key in todo:
        link = links[key]
        print(card.render(link, prior.get(key), advisories, library, golden.get(link.advisory_id, set())))
        while True:
            try:
                choice = input("[a]pprove  [r]eject  [s]kip  [q]uit > ").strip().lower()
            except EOFError:
                choice = "q"
            if choice in ("a", "r", "s", "q"):
                break
        if choice == "q":
            break
        if choice == "s":
            continue
        try:
            note = input("note (optional) > ").strip()
        except EOFError:
            note = ""
        try:
            gd.apply([(key, "approve" if choice == "a" else "reject", note)], links, q_links, log_path=args.log)
        except gd.GateRefusal as exc:
            print("REFUSED: %s" % exc)
            continue
        decided += 1
        _finish(args)  # after every decision, so quitting never leaves the files behind the log
    print("recorded %d decision%s" % (decided, "" if decided == 1 else "s"))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="The review gate")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--decisions", type=Path, help="apply a pasted list of decisions")
    mode.add_argument("--list", action="store_true", help="summarise the queue; decide nothing")
    mode.add_argument("--check", action="store_true", help="fail if the approvals files differ from the log")
    ap.add_argument("--queue-dir", type=Path, default=gp.QUEUE_DIR)
    ap.add_argument("--log", type=Path, default=gd.LOG)
    ap.add_argument("--approved-links", type=Path, default=gd.APPROVED_LINKS)
    ap.add_argument("--approved-emergent", type=Path, default=gd.APPROVED_EMERGENT)
    args = ap.parse_args(argv)
    if args.list:
        return cmd_list(args)
    if args.check:
        return cmd_check(args)
    if args.decisions:
        return cmd_decisions(args)
    return cmd_interactive(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run the guard and all three mutations**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_review_gate.py; echo "exit=$?"
for m in quarantine overturn evidence; do printf "%-11s" $m; PYTHONPYCACHEPREFIX=/tmp/fc08-mut-$m .venv/bin/python evals/check_review_gate.py --mutate $m | tail -1; done
```
Expected: 26 PASS, `HELD (0 failures)`, exit 0; every mutation ends `HELD: the probe detects the defect when the rule is removed`.

- [ ] **Step 6: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add governance/card.py tools/review.py evals/check_review_gate.py && git commit -m "Week 5 A7: tools/review.py -- the only writer of approvals

Interactive (approve/reject/skip/quit with a note), --decisions for a
pasted list, --list, and --check. Both deciding modes go through
governance.decisions.apply and rebuild the approvals after every
decision. The guard now proves the CLI end to end, and that nothing
outside governance/decisions.py names either approvals file.

check_review_gate.py: 26 checks, mutation-verified three ways."
```

---

### Task 8: Run the gate on the real queue, and write it down

**Files:**
- Modify: `CLAUDE.md` (Layout block; the week 5 line)

**Interfaces:** none new.

- [ ] **Step 1: Run the gate read-only on the real queue**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python tools/review.py --list; echo "exit=$?"; .venv/bin/python tools/review.py --check; echo "exit=$?"
```
Expected: `--list` shows the Task 4 run's links as open, `quarantined links: 0`, `skipped lines: 0`, and names the legacy file; exit 0. `--check` prints `approvals match the decision log` (no log and no files yet), exit 0. Do NOT decide anything: the first real decisions are the owner's.

- [ ] **Step 2: Run every guard one last time**

```bash
cd ~/fc-08-emerging-threat-intelligence && for g in check_tool_surface check_added_by check_twin_pairs check_emergent_threshold check_proposal_contract check_review_gate; do printf "%-26s" $g; .venv/bin/python evals/$g.py > /tmp/fc08-g.out 2>&1; echo "exit=$? $(tail -1 /tmp/fc08-g.out)"; done
```
Expected: six lines `exit=0 HELD (0 failures)`.

- [ ] **Step 3: Update `CLAUDE.md`.** In the `## Layout` code block, directly after the `tools/apply_label_decisions.py` line, add:

```
schemas/citation_match.py          THE quote-on-page rule, shared by the MCP server, the review gate and check_citations.py
agents/run_identity.py             who a run is; the runner hands it to the MCP server, never the agent
data/proposals/                    the review queue: one tracked proposal/2 file per run (week 5)
data/proposals_legacy_2026-09-10_to_13.jsonl   the 383 pre-week-5 proposals, frozen, never reviewed
governance/                        the review gate: proposals.py (load, re-check, group), decisions.py (log, refusals, rebuild), card.py
tools/review.py                    THE ONLY writer of approvals: interactive, --decisions, --list, --check
data/review_decisions.jsonl        append-only decision log (tracked); the two approvals files are rebuilt from it
evals/check_proposal_contract.py   pins the proposal contract; --mutate citations|run
evals/check_review_gate.py         pins the gate end to end; --mutate quarantine|overturn|evidence
```

Replace the line `- [ ] Week 5: hooks, telemetry, `review.py` gate, desk digests` with:

```
- [~] **Week 5** (started 2026-09-24): spec `docs/superpowers/specs/2026-09-24-week5-governance-design.md`.
  **Sub-project A DONE** (plan `docs/superpowers/plans/2026-09-24-week5-a-proposal-contract-and-review-gate.md`):
  every proposal names its run and carries quotes verified at proposal time and again at review; one
  tracked queue file per run; `tools/review.py` is the only writer of approvals, rebuilt from an
  append-only decision log. The 383 legacy proposals are frozen, not reviewed -- they carry no quotes and
  no run. NEXT: sub-project B (telemetry + the write allowlist; probe first whether `can_use_tool` needs a
  streamed prompt), then C (desk digests).
```

- [ ] **Step 4: Commit.** Replace `<N>` with the open-link count from Step 1.

```bash
cd ~/fc-08-emerging-threat-intelligence && git add CLAUDE.md && git commit -m "CLAUDE.md: week 5 sub-project A landed -- the proposal contract and the review gate

Layout gains the new modules, queue, log and guards. Real queue checked
read-only: <N> open links from the ADV-2026-0013 run, 0 quarantined, 0
skipped; no decisions taken -- the first are the owner's."
```

---

## Self-review against the spec

| Spec requirement (Sections 1-2) | Task |
|---|---|
| Run identity from env; the agent cannot set it; advisory mismatch refused | 3 (server), 4 (runners) |
| Citations required, verified against the page at proposal time; refusal names the page | 3 |
| One shared matching module, three callers | 1 (module and `check_citations`), 3 (server), 5 (gate) |
| `proposal/2` line; `proposal_id` stable for identical content; no `status` | 3 |
| Legacy queue copied byte-identical, tracked, nothing deleted | 2 |
| Guard exercising each refusal, and a correct proposal accepted | 3 |
| Links grouped by advisory+typology or emergent label | 5 |
| Re-check at load; quarantine with reason; never approvable | 5, 6 |
| Card content | 7 (`governance/card.py`) |
| Interactive and `--decisions`, one writer, the four refusals | 6, 7 |
| Append-only decision log with the stated fields | 6 |
| New evidence reopens a link; deciding it appends | 6 |
| Approvals rebuilt from the log; `--check`; no other writer | 6, 7 |
| Emergent approvals in their own file | 6 |
