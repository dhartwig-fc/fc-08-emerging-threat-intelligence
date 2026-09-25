# Week 6 sub-project 1: hardening and resolve_actor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a committed digest batch re-checkable for ever, bind the proposal queue to its run, run every guard automatically (locally and cold on CI), and add a read-only `resolve_actor` tool that decides actor identity on exact matches only.

**Architecture:** A batch writes a `manifest.json` pinning the decision-log prefix and the hash of every input; `--check` rebuilds from exactly those inputs. The MCP server derives its queue file from the run id. `tools/check_all.py` is the single list of guards, each classed by measurement; a tracked pre-commit hook and a GitHub Actions workflow call it. A governed actor register (built from the golden labels, merging only on exact cross-advisory matches) backs a pure resolver in `schemas/actor_match.py`, exposed as an MCP tool and measured over the extractor's records.

**Tech Stack:** Python 3.14 (`.venv`), stdlib, `mcp` FastMCP server, `claude-agent-sdk` (options only; no live runs), pydantic 2. Guards are scripts ending `HELD (0 failures)`, not pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-week6-landing-design.md`, Sections 1-5 (Section 5 as amended 2026-09-25).

## Global Constraints

- Repository `~/fc-08-emerging-threat-intelligence`, branch `main`. Run Python as `.venv/bin/python`.
- NO live model runs. `evals/check_tool_surface.py --live` is never run in this plan.
- Never run `tools/review.py` except `--check`. Never append to the real decision log.
- Only `governance/decisions.py` (and `evals/check_review_gate.py`) may contain the decision log's or an approvals file's FILENAME, in any `.py` or `.sh`; `check_review_gate`'s writer scan enforces it. Use `gd.LOG` for the path and name it by role in prose.
- A guard never writes the real `data/` tree: redirect to `tempfile.mkdtemp()` directories.
- Guard style: each check is `(ok: bool, label: str, detail: str)`; output ends `HELD (0 failures)` / `REFUSED (n failures)`; under `--mutate X` it prints `HELD: the probe detects the defect when the rule is removed` and exits 0 when checks fail, or `NOTHING PROVED: it passed with the rule gone` and exits 1 when none do.
- Every new or changed guard check is watched FAILING (against current code, or under its mutation) before it is watched passing. Record red and green in the report.
- Mutation runs use their own bytecode cache: `PYTHONPYCACHEPREFIX=/tmp/mut-<label> .venv/bin/python ...`.
- No `.bak` / `_backup` / `_before_*` files. No `--no-verify`. No file over 50 MB.
- Commit messages start `Week 6.1:`. NO `Co-Authored-By` trailer. Do not push.
- Identity is the owner's: the register never merges on a similarity score; a suggestion is never a resolution.
- `data/records/` holds week-1 variant files (`ADV-2026-0001.schema-1.0.0.json`, ...). Anything reading extractor records selects `^ADV-\d{4}-\d{4}\.json$` exactly.

---

## File structure

| File | Responsibility |
|---|---|
| `governance/decisions.py` (modify) | `log_prefix(n, path)`: the first n lines of the log, their hash, their decisions |
| `governance/proposals.py` (modify) | `load_queue_files(paths)`; `load_queue` delegates to it |
| `tools/build_digests.py` (rewrite) | build from explicit inputs, write `manifest.json`, refuse overwrite, three-stage `--check`, `--backfill-manifest` |
| `evals/check_digest_batch.py` (create) | guard for the manifest, overwrite refusal and check diagnostics |
| `mcp_server/knowledge_centre_server.py` (modify) | `QUEUE_DIR`; queue path derived from run id; `knowledge_centre_resolve_actor` tool |
| `evals/check_proposal_contract.py` (modify) | redirect via `kc.QUEUE_DIR`; check a mismatched queue path is refused |
| `schemas/actor_match.py` (create) | `norm`, `tokens`, `containment`, `SUGGEST_MIN`, `variants_of`, `resolve` |
| `evals/score.py` (modify) | import the normaliser from `schemas/actor_match.py` |
| `tools/build_actor_register.py` (create) | build/check `data/actor_register.json` and `data/actor_register_candidates.json` |
| `agents/permissions.py`, `agents/extract_advisory.py` (modify) | the new read-only tool in `READ_ONLY_TOOLS` and `KC_TOOLS` |
| `evals/check_tool_surface.py` (modify) | "three" becomes "four" reads; server tool list must equal `KC_TOOLS` |
| `evals/actor_resolution.py` (create) | the resolution report; `--check` against `evals/actor_resolution.json` |
| `evals/check_actor_resolution.py` (create) | guard, mutations `containment`, `ambiguous`, `same-advisory`, `category` |
| `tools/check_all.py` (create) | the one list of guards with measured classes; `--cold`, `--list` |
| `scripts/hooks/pre-commit` (create) | runs `tools/check_all.py` |
| `.github/workflows/checks.yml` (create) | runs `tools/check_all.py --cold` |
| `setup.sh`, `CLAUDE.md` (modify) | hooks setup line; week-6.1 state |

---

### Task 1: a digest batch pins its inputs and is never overwritten

**Files:**
- Modify: `governance/decisions.py` (add `log_prefix` after `load_log_checked`; add `import hashlib`)
- Modify: `governance/proposals.py:145-165` (`load_queue_files`)
- Rewrite: `tools/build_digests.py`
- Create: `evals/check_digest_batch.py`
- Create: `data/digests/slice1-2026-09-24/manifest.json` (back-filled)

**Interfaces:**
- Produces: `gd.log_prefix(n: Optional[int] = None, path: Path = LOG) -> Tuple[int, str, List[Decision]]` (lines, sha256 hex, decisions); raises `ValueError` when `n` exceeds the log's line count.
- Produces: `gp.load_queue_files(paths) -> Tuple[List[Proposal], List[str]]`.
- Produces: `tools/build_digests.py` functions `build(batch_id, record_paths, queue_paths, log_path, log_lines=None) -> Tuple[Dict[str, str], dict]` (desk texts, manifest) and `check(batch_id, out_dir, records_dir, queue_dir, log_path) -> List[str]` (problems). CLI: `--batch-id` (required), `--records-dir`, `--queue-dir`, `--log`, `--out-dir`, `--check` | `--backfill-manifest`. Sub-project 2 reads `manifest.json` key `decision_log.lines`.

- [ ] **Step 1: Add `log_prefix` to `governance/decisions.py`**

Add `import hashlib` to the imports, and insert after `load_log_checked`:

```python
def log_prefix(n: Optional[int] = None, path: Path = LOG) -> Tuple[int, str, List[Decision]]:
    """(lines, sha256, decisions) for the first n lines of the log, all of it when n is None.

    The log is append-only, so a prefix is an immutable snapshot: a digest batch pins
    (lines, sha256) and rebuilds from exactly the decisions it saw, however many are
    appended later. Lines are counted and hashed as stored bytes, blank lines included.
    """
    raw = path.read_bytes().splitlines(keepends=True) if path.exists() else []
    if n is None:
        n = len(raw)
    if n > len(raw):
        raise ValueError("the log has %d lines; %d were pinned, so lines were removed" % (len(raw), n))
    prefix = b"".join(raw[:n])
    decisions = [Decision.from_line(json.loads(line)) for line in prefix.decode("utf-8").splitlines()
                 if line.strip()]
    return n, hashlib.sha256(prefix).hexdigest(), decisions
```

- [ ] **Step 2: Add `load_queue_files` to `governance/proposals.py`**

Replace `load_queue` with:

```python
def load_queue_files(paths) -> Tuple[List[Proposal], List[str]]:
    """Every proposal/2 line in the given files, in the order given, and one note per line skipped."""
    proposals: List[Proposal] = []
    skipped: List[str] = []
    for path in paths:
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
                proposals.append(Proposal.from_line(d, source_file=path.name))
            except (KeyError, TypeError, ValueError) as exc:
                skipped.append("%s:%d is malformed (%s)" % (path.name, n, exc))
    return proposals, skipped


def load_queue(queue_dir: Path = QUEUE_DIR) -> Tuple[List[Proposal], List[str]]:
    """Every proposal/2 line under queue_dir, and one note per line skipped -- none vanish silently."""
    return load_queue_files(sorted(queue_dir.glob("*.jsonl")) if queue_dir.exists() else [])
```

Run: `.venv/bin/python evals/check_review_gate.py | tail -1` — Expected: `HELD (0 failures)` (behaviour unchanged).

- [ ] **Step 3: Write the failing guard `evals/check_digest_batch.py`**

```python
"""
Pin the digest batch contract: a batch records the inputs it was built from, can be
re-checked after any number of later decisions, and is never overwritten.

Usage:
    python evals/check_digest_batch.py
    python evals/check_digest_batch.py --mutate prefix      # --check reads the WHOLE log; checks MUST fail
    python evals/check_digest_batch.py --mutate overwrite   # an existing batch may be rewritten; MUST fail

WHY. Week 5's first batch could not be re-verified once a new decision landed: --check
rebuilt from the whole log, so any later decision made a correct batch look broken, and
a broken renderer looked the same as a moved world. The manifest separates the two.

OFFLINE. Everything runs over COPIES of the real records, queue and decision log in a
temporary directory; the real data/ tree is never written. No model, no PDF.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance.digest import RECORDS_DIR  # noqa: E402
from governance.proposals import QUEUE_DIR  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="fc08_batch_"))
MUTATION = None


def _cli(*args) -> subprocess.CompletedProcess:
    extra = ["--_mutate", MUTATION] if MUTATION else []
    return subprocess.run([sys.executable, str(ROOT / "tools" / "build_digests.py")] + list(args) + extra,
                          capture_output=True, text=True, cwd=ROOT)


def _copy_inputs(name: str) -> dict:
    base = WORK / name
    shutil.copytree(RECORDS_DIR, base / "records")
    shutil.copytree(QUEUE_DIR, base / "proposals")
    shutil.copy(gd.LOG, base / "log.jsonl")
    return {"--records-dir": base / "records", "--queue-dir": base / "proposals",
            "--log": base / "log.jsonl", "--out-dir": base / "digests"}


def _args(paths: dict) -> list:
    return [x for k, v in paths.items() for x in (k, str(v))]


def checks() -> list:
    out = []
    p = _copy_inputs("a")
    r = _cli("--batch-id", "guard-a", *_args(p))
    manifest = p["--out-dir"] / "guard-a" / "manifest.json"
    out.append((r.returncode == 0 and manifest.exists(), "a build writes manifest.json beside the desk files",
                (r.stdout + r.stderr).strip()[-160:]))
    m = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    lines, sha, _ = gd.log_prefix(None, p["--log"])
    out.append((m.get("decision_log") == {"lines": lines, "sha256": sha},
                "the manifest pins the decision log's line count and hash", str(m.get("decision_log"))))
    out.append((len(m.get("records", {})) == 20 and len(m.get("proposals", {})) >= 1,
                "the manifest hashes every record and every queue file it read",
                "%d records, %d queue files" % (len(m.get("records", {})), len(m.get("proposals", {})))))
    text = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
    out.append((bool(text) and gd.LOG.name not in text and "/" not in "".join(m.get("records", {})),
                "the manifest names inputs by role and filename, never the log's filename or a path", text[:80]))

    r = _cli("--batch-id", "guard-a", "--check", *_args(p))
    out.append((r.returncode == 0, "a fresh batch --check matches", r.stdout.strip()[-120:]))

    # A LATER decision reversing the last link. The batch must still match: it reads its pinned prefix.
    later = json.loads(p["--log"].read_text(encoding="utf-8").splitlines()[-1])
    later["decided_at"] = "2099-01-01T00:00:00+00:00"
    later["decision"] = "reject" if later["decision"] == "approve" else "approve"
    with open(p["--log"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(later, sort_keys=True) + "\n")
    r = _cli("--batch-id", "guard-a", "--check", *_args(p))
    out.append((r.returncode == 0,
                "after a LATER decision reverses a link, the batch still matches (it reads its pinned prefix)",
                r.stdout.strip()[-160:]))

    r = _cli("--batch-id", "guard-a", *_args(p))
    out.append((r.returncode == 2 and "exists" in (r.stdout + r.stderr),
                "building an existing batch id is REFUSED, exit 2", (r.stdout + r.stderr).strip()[-160:]))

    rec = sorted(p["--records-dir"].glob("ADV-*.json"))[0]
    rec.write_text(rec.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    r = _cli("--batch-id", "guard-a", "--check", *_args(p))
    out.append((r.returncode == 1 and ("inputs moved since this batch: %s" % rec.name) in r.stdout,
                "a changed record reads as INPUTS MOVED, naming the file", r.stdout.strip()[-160:]))

    q = _copy_inputs("b")
    _cli("--batch-id", "guard-b", *_args(q))
    desk = sorted((q["--out-dir"] / "guard-b").glob("*.md"))[0]
    desk.write_text(desk.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    r = _cli("--batch-id", "guard-b", "--check", *_args(q))
    out.append((r.returncode == 1 and ("same inputs, different output: %s" % desk.stem) in r.stdout,
                "a changed desk file with unchanged inputs reads as SAME INPUTS, DIFFERENT OUTPUT",
                r.stdout.strip()[-160:]))

    s = _copy_inputs("c")
    _cli("--batch-id", "guard-c", *_args(s))
    kept = s["--log"].read_text(encoding="utf-8").splitlines(keepends=True)[:-1]
    s["--log"].write_text("".join(kept), encoding="utf-8")
    r = _cli("--batch-id", "guard-c", "--check", *_args(s))
    out.append((r.returncode == 1 and "decision log" in r.stdout,
                "a log with a pinned line REMOVED fails, naming the decision log", r.stdout.strip()[-160:]))

    real = ROOT / "data" / "digests" / "slice1-2026-09-24" / "manifest.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_digests.py"), "--batch-id",
                        "slice1-2026-09-24", "--check"], capture_output=True, text=True, cwd=ROOT)
    out.append((real.exists() and r.returncode == 0,
                "the committed batch slice1-2026-09-24 has a manifest and matches", r.stdout.strip()[-160:]))
    return out


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the digest batch contract")
    ap.add_argument("--mutate", choices=("prefix", "overwrite"), help="break one rule; checks MUST fail")
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if MUTATION:
        print("MUTATED: %s\n" % {"prefix": "--check rebuilds from the whole log, not the pinned prefix.",
                                 "overwrite": "an existing batch id may be rebuilt over."}[MUTATION])
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if MUTATION:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

The mutations live in the builder's subprocess, so `build_digests.py` accepts a hidden `--_mutate` argument (Step 5), `help=argparse.SUPPRESS`, existing only for this guard. The last check reads the REAL committed batch; that is a read, not a write.

- [ ] **Step 4: Run the guard to watch it fail**

Run: `.venv/bin/python evals/check_digest_batch.py`
Expected: REFUSED — the first check fails (`--queue-dir`/`--log` are unknown arguments; no manifest).

- [ ] **Step 5: Rewrite `tools/build_digests.py`**

```python
"""
Build (or check) one batch of desk digests.

Usage:
    python tools/build_digests.py --batch-id slice1-2026-09-24            # write data/digests/<batch_id>/
    python tools/build_digests.py --batch-id slice1-2026-09-24 --check    # prove the committed batch
    python tools/build_digests.py --batch-id slice1-2026-09-24 --backfill-manifest

A batch is a SNAPSHOT. manifest.json pins what it was built from: the decision log's
first N lines (count and hash) and the hash of every record and queue file. The log is
append-only, so --check rebuilds from exactly those N lines however many decisions land
later, and says which of three things went wrong when it fails:

  the decision log ...                     a pinned log line was edited or removed
  inputs moved since this batch: <file>    a pinned record or queue file changed --
                                           cut a new batch; the old one is still true
  same inputs, different output: <desk>    the renderer changed -- a defect

A batch is never overwritten (exit 2): a committed batch is evidence. A record or queue
file added after the batch is not one of its inputs and is ignored.

--backfill-manifest writes a manifest for a batch built before manifests existed, and
only when a fresh build from today's inputs reproduces its desk files byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance.digest import DIGESTS_DIR, NO_ADVISORIES, RECORDS_DIR, build_batch  # noqa: E402
from governance.proposals import ADVISORY_LIST, LIBRARY, QUEUE_DIR, load_queue_files  # noqa: E402
from governance.routing import load_routing  # noqa: E402

BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
MANIFEST = "manifest.json"
_MUTATE = None  # set only by evals/check_digest_batch.py through --_mutate


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(batch_id: str, record_paths, queue_paths, log_path: Path, log_lines=None):
    """(desk -> Markdown, manifest) from exactly these inputs and the first log_lines of the log."""
    lines, log_sha, decisions = gd.log_prefix(log_lines, log_path)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in record_paths]
    library = {t["typology_id"]: t for t in json.loads(LIBRARY.read_text(encoding="utf-8"))["typologies"]}
    advisories = {a["advisory_id"]: a for a in json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    proposals, _ = load_queue_files(queue_paths)
    batch = build_batch(batch_id, records, library, load_routing(), gd.latest(decisions),
                        {p.proposal_id: p for p in proposals}, advisories)
    manifest = {
        "batch_id": batch_id,
        "decision_log": {"lines": lines, "sha256": log_sha},
        "records": {p.name: _sha(p) for p in record_paths},
        "proposals": {p.name: _sha(p) for p in queue_paths},
    }
    return batch, manifest


def _current_inputs(records_dir: Path, queue_dir: Path):
    return (sorted(records_dir.glob("ADV-*.json")),
            sorted(queue_dir.glob("*.jsonl")) if queue_dir.exists() else [])


def _manifest_text(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def check(batch_id: str, out_dir: Path, records_dir: Path, queue_dir: Path, log_path: Path) -> list:
    folder = out_dir / batch_id
    mpath = folder / MANIFEST
    if not mpath.exists():
        return ["%s has no %s: it cannot say what it was built from" % (batch_id, MANIFEST)]
    m = json.loads(mpath.read_text(encoding="utf-8"))
    pinned = m["decision_log"]
    try:
        lines, sha, _ = gd.log_prefix(pinned["lines"], log_path)
    except ValueError as exc:
        return ["the decision log no longer holds this batch's lines: %s" % exc]
    if sha != pinned["sha256"]:
        return ["the decision log's first %d lines were edited since this batch was built" % lines]

    moved = [name for name, want in sorted(m["records"].items())
             if not (records_dir / name).exists() or _sha(records_dir / name) != want]
    moved += [name for name, want in sorted(m["proposals"].items())
              if not (queue_dir / name).exists() or _sha(queue_dir / name) != want]
    if moved:
        return ["inputs moved since this batch: %s" % n for n in moved]

    rebuild_from = None if _MUTATE == "prefix" else pinned["lines"]
    batch, rebuilt = build(batch_id, [records_dir / n for n in sorted(m["records"])],
                           [queue_dir / n for n in sorted(m["proposals"])], log_path, rebuild_from)
    problems = []
    for desk, text in batch.items():
        path = folder / ("%s.md" % desk)
        if not path.exists():
            problems.append("same inputs, different output: %s is missing" % desk)
        elif path.read_text(encoding="utf-8") != text:
            problems.append("same inputs, different output: %s" % desk)
    problems += ["%s is not a desk in this batch" % p.name for p in sorted(folder.glob("*.md")) if p.stem not in batch]
    if rebuilt != m and _MUTATE != "prefix":
        problems.append("same inputs, different output: %s" % MANIFEST)
    return problems


def main(argv: list) -> int:
    global _MUTATE
    ap = argparse.ArgumentParser(description="Build or check a batch of desk digests")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--records-dir", type=Path, default=RECORDS_DIR)
    ap.add_argument("--queue-dir", type=Path, default=QUEUE_DIR)
    ap.add_argument("--log", type=Path, default=gd.LOG)
    ap.add_argument("--out-dir", type=Path, default=DIGESTS_DIR)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--backfill-manifest", action="store_true")
    ap.add_argument("--_mutate", choices=("prefix", "overwrite"), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    _MUTATE = args._mutate
    if not BATCH_ID.match(args.batch_id):
        print("batch id must match %s" % BATCH_ID.pattern, file=sys.stderr)
        return 2
    folder = args.out_dir / args.batch_id

    if args.check:
        problems = check(args.batch_id, args.out_dir, args.records_dir, args.queue_dir, args.log)
        for p in problems:
            print("FAIL  %s" % p)
        print("batch %s matches a fresh build from its pinned inputs" % args.batch_id if not problems
              else "batch %s does NOT match" % args.batch_id)
        return 1 if problems else 0

    records, queue = _current_inputs(args.records_dir, args.queue_dir)
    batch, manifest = build(args.batch_id, records, queue, args.log)

    if args.backfill_manifest:
        if (folder / MANIFEST).exists():
            print("%s already has a manifest; nothing to back-fill" % args.batch_id, file=sys.stderr)
            return 2
        differs = [d for d, t in batch.items() if not (folder / ("%s.md" % d)).exists()
                   or (folder / ("%s.md" % d)).read_text(encoding="utf-8") != t]
        if differs:
            print("REFUSED: today's inputs do not reproduce %s (%s); its inputs are unknown, so no manifest "
                  "can honestly be written" % (args.batch_id, ", ".join(differs)), file=sys.stderr)
            return 1
        (folder / MANIFEST).write_text(_manifest_text(manifest), encoding="utf-8")
        print("back-filled %s/%s (decision log: %d lines)" % (args.batch_id, MANIFEST, manifest["decision_log"]["lines"]))
        return 0

    if folder.exists() and _MUTATE != "overwrite":
        print("REFUSED: batch %s already exists. A committed batch is evidence; build a new batch id for "
              "the new state." % args.batch_id, file=sys.stderr)
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    for desk, text in batch.items():
        (folder / ("%s.md" % desk)).write_text(text, encoding="utf-8")
    (folder / MANIFEST).write_text(_manifest_text(manifest), encoding="utf-8")
    routed = sum(1 for t in batch.values() if NO_ADVISORIES not in t)
    print("wrote %d digests and %s to %s (%d desks receive advisories)" % (len(batch), MANIFEST, folder, routed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 6: Back-fill the committed batch**

Run: `.venv/bin/python tools/build_digests.py --batch-id slice1-2026-09-24 --backfill-manifest`
Expected: `back-filled slice1-2026-09-24/manifest.json (decision log: 5 lines)`. If it REFUSES, stop and report: the spec measured the inputs unchanged, so a refusal is a finding, not something to work around.

Run: `.venv/bin/python tools/build_digests.py --batch-id slice1-2026-09-24 --check`
Expected: `batch slice1-2026-09-24 matches a fresh build from its pinned inputs`, exit 0.

- [ ] **Step 7: Run the guard, its mutations, and the neighbours**

Run: `.venv/bin/python evals/check_digest_batch.py` — Expected: `HELD (0 failures)`, 11 checks.
Run: `PYTHONPYCACHEPREFIX=/tmp/mut-prefix .venv/bin/python evals/check_digest_batch.py --mutate prefix` — Expected: the "LATER decision" check FAILS; `HELD: the probe detects...`.
Run: `PYTHONPYCACHEPREFIX=/tmp/mut-overwrite .venv/bin/python evals/check_digest_batch.py --mutate overwrite` — Expected: the "REFUSED, exit 2" check FAILS; `HELD: the probe detects...`.
Run: `.venv/bin/python evals/check_digest_routing.py | tail -1` and `.venv/bin/python evals/check_review_gate.py | tail -1` — Expected: `HELD (0 failures)` each. The writer scan must not flag `tools/build_digests.py` or the new guard.
Run: `git status --short` — Expected: only this task's files; under `data/digests/` only the new `manifest.json`.

- [ ] **Step 8: Commit**

```bash
git add governance/decisions.py governance/proposals.py tools/build_digests.py evals/check_digest_batch.py data/digests/slice1-2026-09-24/manifest.json
git commit -m "Week 6.1: a digest batch pins its inputs, re-checks after later decisions, and is never overwritten"
```

---

### Task 2: the server binds its queue path to the run

**Files:**
- Modify: `mcp_server/knowledge_centre_server.py:45-52` (constants), `:457-458` (`_proposals_path`), `propose_link`
- Modify: `evals/check_proposal_contract.py` (redirect via `kc.QUEUE_DIR`, new check, mutation `queue`)

**Interfaces:**
- Produces: `kc.QUEUE_DIR: Path` (module constant, default `ROOT / "data" / "proposals"`), `kc.RUN_ID_PATTERN`, `kc._refuse_queue(run: dict) -> Optional[str]`.

Plan ruling: the spec says the server "derives `data/proposals/<NEXUS_RUN_ID>.jsonl`". A guard must never write the real queue, so the queue DIRECTORY is a module constant a guard may repoint inside its own process, exactly as guards repoint `telemetry.TELEMETRY_DIR`. The environment can no longer choose the file. A live run is a separate process that never sees a guard's reassignment.

- [ ] **Step 1: Write the failing check in `evals/check_proposal_contract.py`**

Replace the redirect block at the top with:

```python
QUEUE_DIR = Path(tempfile.mkdtemp(prefix="fc08_contract_"))
RUN_ID = "probe-contract"
QUEUE = QUEUE_DIR / ("%s.jsonl" % RUN_ID)
# Redirect the queue BEFORE any proposal: a guard never writes the real one. The
# server owns the directory (a module constant, repointed here in-process); the
# file name is the run id.
os.environ["NEXUS_PROPOSALS_PATH"] = str(QUEUE)

from mcp_server import knowledge_centre_server as kc  # noqa: E402

kc.QUEUE_DIR = QUEUE_DIR
```

In `_run_env`, use `"NEXUS_RUN_ID": RUN_ID`. In `checks()`, immediately before the final "refusals wrote NOTHING to the queue" check, add:

```python
    stray = QUEUE_DIR / "elsewhere.jsonl"
    _run_env()
    os.environ["NEXUS_PROPOSALS_PATH"] = str(stray)
    got = _propose(**base)
    os.environ["NEXUS_PROPOSALS_PATH"] = str(QUEUE)
    out.append((got.startswith("Rejected") and "probe-contract.jsonl" in got and not stray.exists(),
                "a queue path that is not <queue dir>/<run_id>.jsonl is REFUSED, and nothing is written there",
                got[:160]))
```

Add `"queue"` to the `--mutate` choices, with:

```python
    elif args.mutate == "queue":
        kc._refuse_queue = lambda run: None
        kc._proposals_path = lambda run: Path(run[kc.QUEUE_ENV])
        print("MUTATED: the queue path is taken from the environment again.\n")
```

Run: `.venv/bin/python evals/check_proposal_contract.py`
Expected: REFUSED — the new check fails (today the server writes `elsewhere.jsonl`).

- [ ] **Step 2: Bind the path in the server**

Replace the `QUEUE_ENV` comment and constant with:

```python
# The queue path is part of the run identity too, with no default: a runner
# that supplies the five identity keys but not this one must not fall back to
# the retired data/proposals.jsonl. Since week 6 it can no longer CHOOSE the
# file: the server derives <QUEUE_DIR>/<run_id>.jsonl and refuses any other,
# so the environment cannot redirect a governed write.
QUEUE_ENV = "NEXUS_PROPOSALS_PATH"
QUEUE_DIR = ROOT / "data" / "proposals"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
```

Replace `_proposals_path` with:

```python
def _proposals_path(run: dict) -> Path:
    return QUEUE_DIR / ("%s.jsonl" % run["NEXUS_RUN_ID"])


def _refuse_queue(run: dict) -> Optional[str]:
    if not RUN_ID_PATTERN.match(run["NEXUS_RUN_ID"]):
        return "Rejected: run id %r is not a safe file name." % run["NEXUS_RUN_ID"]
    want = _proposals_path(run)
    if Path(run[QUEUE_ENV]).resolve() != want.resolve():
        return ("Rejected: this run's queue is %s, but the runner named %s. A proposal is written only to "
                "its own run's queue." % (want.name, Path(run[QUEUE_ENV]).name))
    return None
```

Add `import re` if absent. In `propose_link`, directly after the `if run is None:` refusal block:

```python
    refusal = _refuse_queue(run)
    if refusal:
        return refusal
```

- [ ] **Step 3: Run the guard, its mutations, and the neighbours**

Run: `.venv/bin/python evals/check_proposal_contract.py` — Expected: `HELD (0 failures)`.
Run: `PYTHONPYCACHEPREFIX=/tmp/mut-queue .venv/bin/python evals/check_proposal_contract.py --mutate queue` — Expected: the new check FAILS; `HELD: the probe detects...`.
Run: `.venv/bin/python evals/check_proposal_contract.py --mutate citations | tail -1` and `... --mutate run | tail -1` — Expected: `HELD: the probe detects...` each.
Run: `.venv/bin/python evals/check_tool_surface.py | tail -1` and `.venv/bin/python evals/check_telemetry.py | tail -1` — Expected: `HELD (0 failures)` each (`RunIdentity.queue_path` is unchanged, so `check_tool_surface`'s queue-directory check still holds).
Run: `ls data/proposals/` — Expected: the same two files as before.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/knowledge_centre_server.py evals/check_proposal_contract.py
git commit -m "Week 6.1: propose_link writes only to its own run's queue file"
```

---

### Task 3: one normaliser, shared by the scorer and the resolver

**Files:**
- Create: `schemas/actor_match.py`
- Modify: `evals/score.py` (remove `_STOP`, `norm`, `tokens`, `containment`; import them)

**Interfaces:**
- Produces: `schemas.actor_match.norm(text) -> str`, `tokens(text) -> frozenset`, `containment(a, b) -> float`, `variants_of(actor: dict) -> List[str]`, `SUGGEST_MIN = 0.60`. Task 5 adds `resolve`.
- `evals/score.py` keeps exposing `sc.norm`, `sc.tokens`, `sc.containment` by import, so `check_emergent_threshold.py`, `tools/merge_reviewer_additions.py` and `tools/build_emergent_candidates.py` are untouched.

- [ ] **Step 1: Record the baseline**

Run: `.venv/bin/python evals/score.py --predicted evals/golden > /tmp/score_self_before.txt; tail -8 /tmp/score_self_before.txt`
Run: `.venv/bin/python evals/score.py > /tmp/score_before.txt; tail -8 /tmp/score_before.txt`
Expected: the self-score shows 1.000 on typologies, emergent, actors and jurisdictions. Keep both files for Step 4.

- [ ] **Step 2: Create `schemas/actor_match.py`**

The file, top to bottom: this docstring; `from __future__ import annotations`; `import re`; `from typing import List`; then `_STOP` (with its comment about corporate suffixes), `norm`, `tokens` and `containment` moved from `evals/score.py` VERBATIM; then `SUGGEST_MIN` and `variants_of`.

```python
"""
Name normalising and matching shared by the scorer (evals/score.py) and the actor
resolver (knowledge_centre_resolve_actor). One normaliser, two questions:

  scoring   is this the actor I labelled in THIS advisory? Containment over the shorter
            token set is right there -- the candidates are a handful from one document.
  identity  which party is this, across every advisory? Containment is WRONG there, and
            measured so: "Iran" is wholly contained in "Islamic Republic of Iran Shipping
            Lines". So the resolver resolves on an EXACT normalised name or alias only;
            containment >= SUGGEST_MIN produces suggestions for a human, never a resolution.

The scorer's thresholds stay in evals/score.py: they are scoring constants.
"""
```

```python
# Containment at or above this is shown to a human as a SUGGESTION. It is not an
# identity threshold: measured 2026-09-25, four of five containment-only matches at
# this level named the wrong party.
SUGGEST_MIN = 0.60


def variants_of(actor: dict) -> List[str]:
    """Every spelling an actor answers to: its name, then its aliases, blanks dropped."""
    return [v for v in [actor.get("name", "")] + list(actor.get("aliases") or []) if v and norm(v)]
```

- [ ] **Step 3: Import it in `evals/score.py`**

Delete the moved definitions (and `import re` if nothing else in `score.py` uses it). If `score.py` has no `ROOT`/`sys.path` setup, add `ROOT = Path(__file__).resolve().parent.parent` and `sys.path.insert(0, str(ROOT))` after the imports. Then:

```python
from schemas.actor_match import containment, norm, tokens  # noqa: E402,F401  (re-exported: sc.norm etc.)
```

- [ ] **Step 4: Prove nothing moved**

Run: `.venv/bin/python evals/score.py --predicted evals/golden | diff /tmp/score_self_before.txt - && echo SAME`
Run: `.venv/bin/python evals/score.py | diff /tmp/score_before.txt - && echo SAME`
Expected: `SAME` twice.
Run: `.venv/bin/python evals/check_emergent_threshold.py | tail -1` — Expected: `HELD (0 failures)`.
Run: `grep -n "def norm\|def tokens\|def containment\|_STOP = " evals/score.py` — Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add schemas/actor_match.py evals/score.py
git commit -m "Week 6.1: move the name normaliser to schemas/actor_match.py, shared by scorer and resolver"
```

---

### Task 4: the actor register

**Files:**
- Create: `tools/build_actor_register.py`
- Create: `data/actor_register.json`, `data/actor_register_candidates.json`

**Interfaces:**
- Consumes: `schemas.actor_match.norm`, `tokens`, `containment`, `variants_of`, `SUGGEST_MIN`.
- Produces: `build_register(labels: List[dict], merge_same_advisory: bool = False, merge_ambiguous: bool = False) -> Tuple[List[dict], List[dict]]` (entries, candidates); the flags exist only for Task 6's mutations. `load_labels(golden=GOLDEN) -> List[dict]`, `load_register(path=REGISTER) -> List[dict]`, `REGISTER`, `CANDIDATES`.
- Entry: `{"actor_id", "name", "actor_type", "aliases", "named_in": [{"advisory_id", "name_as_labelled"}], "entity_key": null}`; `aliases` is every OTHER spelling, one per normalised form, sorted.
- Candidate: `{"reason": "ambiguous" | "same advisory" | "similar names", "advisory_id", "actor", "entries": [actor_id...], "score"}`.

- [ ] **Step 1: Write `tools/build_actor_register.py`**

```python
"""
Build (or check) the governed actor register from the golden labels.

Usage:
    python tools/build_actor_register.py           # write data/actor_register.json + _candidates.json
    python tools/build_actor_register.py --check   # fail if either differs from a fresh build

Identity is the owner's, so the builder merges only what needs no judgement:
  - an actor matching exactly ONE existing entry from OTHER advisories, on an exact
    normalised name or alias, merges into it;
  - matching NONE starts a new entry;
  - matching TWO OR MORE starts its own entry and is listed `ambiguous`. Measured: ADV-2026-0012
    labels IRGC-Qods Force with "IRGC" and "Islamic Revolutionary Guard Corps" as aliases,
    matching both of ADV-2026-0010's separate entries; merging into either would make the
    other answer to the wrong name;
  - two actors from the SAME advisory never merge -- the label counted them as two
    (`same advisory`);
  - different entries whose spellings reach containment >= SUGGEST_MIN are listed
    `similar names` with their score. Measured, most such pairs are different parties
    (National Iranian Oil vs Tanker Company, GCM vs Berelian Exchange).
Categories are classes, not parties, and are left out. Advisories are read in id order
and actors in label order, so ids are stable and a rebuild is byte-identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.actor_match import SUGGEST_MIN, containment, norm, tokens, variants_of  # noqa: E402

GOLDEN = ROOT / "evals" / "golden"
REGISTER = ROOT / "data" / "actor_register.json"
CANDIDATES = ROOT / "data" / "actor_register_candidates.json"


def load_labels(golden: Path = GOLDEN) -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(golden.glob("ADV-*.json"))]


def load_register(path: Path = REGISTER) -> list:
    return json.loads(path.read_text(encoding="utf-8"))["actors"]


def _aliases(name: str, spellings) -> list:
    """Every spelling other than the name, one per normalised form, sorted."""
    seen, out = {norm(name)}, []
    for v in sorted(spellings, key=lambda s: (norm(s), s)):
        if norm(v) not in seen:
            seen.add(norm(v))
            out.append(v)
    return out


def build_register(labels, merge_same_advisory: bool = False, merge_ambiguous: bool = False):
    entries, candidates, spellings = [], [], {}   # spellings: actor_id -> every spelling seen
    for label in sorted(labels, key=lambda r: r["advisory_id"]):
        aid = label["advisory_id"]
        for actor in label.get("actors", []):
            if actor.get("actor_type") == "category":
                continue
            mine = variants_of(actor)
            keys = {norm(v) for v in mine}
            hits = [e for e in entries if {norm(v) for v in spellings[e["actor_id"]]} & keys]
            same = [e for e in hits if any(n["advisory_id"] == aid for n in e["named_in"])]
            other = [e for e in hits if e not in same]
            for e in same:
                candidates.append({"reason": "same advisory", "advisory_id": aid, "actor": actor["name"],
                                   "entries": [e["actor_id"]], "score": None})
            if merge_same_advisory and same and not other:
                other, same = same, []
            if len(other) > 1 and not merge_ambiguous:
                candidates.append({"reason": "ambiguous", "advisory_id": aid, "actor": actor["name"],
                                   "entries": [e["actor_id"] for e in other], "score": None})
            if other and not same and (len(other) == 1 or merge_ambiguous):
                target = other[0]
                target["named_in"].append({"advisory_id": aid, "name_as_labelled": actor["name"]})
                spellings[target["actor_id"]].extend(mine)
                continue
            actor_id = "ACT-%04d" % (len(entries) + 1)
            entries.append({"actor_id": actor_id, "name": actor["name"], "actor_type": actor.get("actor_type"),
                            "aliases": [], "named_in": [{"advisory_id": aid, "name_as_labelled": actor["name"]}],
                            "entity_key": None})
            spellings[actor_id] = list(mine)
    for e in entries:
        e["aliases"] = _aliases(e["name"], spellings[e["actor_id"]])
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            s = max(containment(tokens(x), tokens(y))
                    for x in [a["name"]] + a["aliases"] for y in [b["name"]] + b["aliases"])
            if s >= SUGGEST_MIN:
                candidates.append({"reason": "similar names", "advisory_id": None,
                                   "actor": "%s / %s" % (a["name"], b["name"]),
                                   "entries": [a["actor_id"], b["actor_id"]], "score": round(s, 2)})
    return entries, candidates


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render(labels) -> tuple:
    entries, candidates = build_register(labels)
    note = ("Built from the golden labels by tools/build_actor_register.py. Merges only on exact normalised "
            "matches across advisories; everything needing judgement is in the candidates file. "
            "entity_key is empty: the estate it would link to is synthetic.")
    return (_dump({"note": note, "actors": entries}),
            _dump({"note": "For the owner to decide. Nothing here is merged.", "candidates": candidates}))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build or check the actor register")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    reg, cand = render(load_labels())
    if args.check:
        bad = [p.name for p, t in ((REGISTER, reg), (CANDIDATES, cand))
               if not p.exists() or p.read_text(encoding="utf-8") != t]
        for n in bad:
            print("FAIL  %s differs from a fresh build" % n)
        print("register matches a fresh build" if not bad else "register does NOT match a fresh build")
        return 1 if bad else 0
    REGISTER.write_text(reg, encoding="utf-8")
    CANDIDATES.write_text(cand, encoding="utf-8")
    entries = json.loads(reg)["actors"]
    reasons = {}
    for c in json.loads(cand)["candidates"]:
        reasons[c["reason"]] = reasons.get(c["reason"], 0) + 1
    print("wrote %d register entries (%d merged across advisories); candidates %s"
          % (len(entries), sum(1 for e in entries if len(e["named_in"]) > 1), reasons))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Build and read the numbers**

Run: `.venv/bin/python tools/build_actor_register.py`
Expected: `wrote 86 register entries (2 merged across advisories); candidates {...}` with exactly one `ambiguous` and no `same advisory`. These are the spec's simulated numbers; if they differ, stop and report the difference rather than changing the rules.

Run: `.venv/bin/python -c "import json;d=json.load(open('data/actor_register.json'))['actors'];print([(e['name'],[n['advisory_id'] for n in e['named_in']]) for e in d if len(e['named_in'])>1])"`
Expected: Sinaloa cartel (0004, 0011) and National Iranian Oil Company (0010, 0012).

- [ ] **Step 3: Prove determinism**

Run: `for s in 1 2 3; do PYTHONHASHSEED=$s .venv/bin/python tools/build_actor_register.py --check; done`
Expected: `register matches a fresh build` three times.

- [ ] **Step 4: Commit**

```bash
git add tools/build_actor_register.py data/actor_register.json data/actor_register_candidates.json
git commit -m "Week 6.1: the actor register, merging only on exact cross-advisory matches"
```

---

### Task 5: `resolve` and the `knowledge_centre_resolve_actor` tool

**Files:**
- Modify: `schemas/actor_match.py` (add `resolve`)
- Modify: `mcp_server/knowledge_centre_server.py` (input model, register loader, tool)
- Modify: `agents/extract_advisory.py:61-66` (`KC_TOOLS`)
- Modify: `agents/permissions.py:41-45` (`READ_ONLY_TOOLS`); "three read-only" → "four read-only" in its docstring and comments
- Modify: `evals/check_tool_surface.py` (labels "three" → "four"; two new static checks)

**Interfaces:**
- Consumes: the register entry shape (Task 4).
- Produces: `schemas.actor_match.resolve(names, actor_type, register, allow_category=False, suggestions_resolve=False) -> dict`, one of:
  - `{"status": "resolved", "actor_id", "name", "matched"}`
  - `{"status": "ambiguous", "entries": [{"actor_id", "name"}, ...]}`
  - `{"status": "unresolved", "suggestions": [{"actor_id", "name", "score"}, ...]}` (at most 3; score desc, then actor_id)
  - `{"status": "category"}`
  The two flags exist only for Task 6's mutations.
- Produces: MCP tool `knowledge_centre_resolve_actor(name, actor_type=None)`, read-only.

- [ ] **Step 1: Add the new static checks to `evals/check_tool_surface.py` (they will pass today)**

In `static_checks()`, change the three labels that say "three read-only" to "four read-only", and append:

```python
    from mcp_server import knowledge_centre_server as kc
    listed = asyncio.run(kc.mcp.list_tools())
    names = sorted(t.name for t in listed)
    out.append((names == sorted(KC_TOOLS),
                "the server's tools are exactly KC_TOOLS: a tool added to the server is added to the lists",
                str(names)))
    ro = sorted("mcp__%s__%s" % (SERVER_KEY, t.name) for t in listed
                if t.annotations is not None and getattr(t.annotations, "readOnlyHint", False))
    out.append((ro == sorted(READ_ONLY_TOOLS), "the tools annotated readOnlyHint are exactly READ_ONLY_TOOLS",
                str(ro)))
```

If `kc.mcp.list_tools()` has a different name or shape on the installed `mcp` version, find the listing call the server's own SDK exposes (read `mcp_server/knowledge_centre_server.py:25-35` for which class it uses) and use it; report what you used.

Run: `.venv/bin/python evals/check_tool_surface.py | tail -1` — Expected: `HELD (0 failures)` (four tools, lists agree).

- [ ] **Step 2: Add `resolve` to `schemas/actor_match.py`**

```python
def resolve(names, actor_type, register, allow_category: bool = False, suggestions_resolve: bool = False) -> dict:
    """Which register entry these spellings name, decided on EXACT normalised matches only.

    Two entries matching is `ambiguous`, never a guess. No exact match is `unresolved`, with
    up to three containment suggestions a human must confirm. A category is a class of
    actor, not a party, and never resolves.
    """
    if actor_type == "category" and not allow_category:
        return {"status": "category"}
    keys = {norm(n) for n in names if norm(n)}
    exact = []
    for e in register:
        hit = next((s for s in [e["name"]] + list(e.get("aliases") or []) if norm(s) in keys), None)
        if hit is not None:
            exact.append((e, hit))
    if len(exact) == 1:
        e, hit = exact[0]
        return {"status": "resolved", "actor_id": e["actor_id"], "name": e["name"], "matched": hit}
    if len(exact) > 1:
        return {"status": "ambiguous", "entries": [{"actor_id": e["actor_id"], "name": e["name"]} for e, _ in exact]}
    scored = []
    for e in register:
        spellings = [e["name"]] + list(e.get("aliases") or [])
        s = max((containment(tokens(a), tokens(b)) for a in names for b in spellings), default=0.0)
        if s >= SUGGEST_MIN:
            scored.append((s, e))
    scored.sort(key=lambda p: (-p[0], p[1]["actor_id"]))
    suggestions = [{"actor_id": e["actor_id"], "name": e["name"], "score": round(s, 2)} for s, e in scored[:3]]
    if suggestions_resolve and suggestions:
        top = suggestions[0]
        return {"status": "resolved", "actor_id": top["actor_id"], "name": top["name"], "matched": None}
    return {"status": "unresolved", "suggestions": suggestions}
```

- [ ] **Step 3: Add the tool to the server, then watch the surface guard FAIL**

After `SearchTypologiesInput`:

```python
class ResolveActorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200, description="The actor's name as the document gives it")
    actor_type: Optional[str] = Field(
        None, pattern=r"^(person|organisation|vessel|wallet|jurisdiction|network|category|unknown)$",
        description="The ActorType you would record. A category never resolves.")
```

Beside the library loaders:

```python
ACTOR_REGISTER_PATH = ROOT / "data" / "actor_register.json"


def _register() -> List[dict]:
    with open(ACTOR_REGISTER_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)["actors"]
```

Beside the other `schemas` imports: `from schemas.actor_match import resolve as resolve_names  # noqa: E402`. After `search_typologies`:

```python
@mcp.tool(
    name="knowledge_centre_resolve_actor",
    annotations={"title": "Resolve actor", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def resolve_actor(params: ResolveActorInput) -> str:
    """
    Say which party in the governed actor register a name refers to.

    Resolves only on an exact match to a registered name or alias. When two parties
    answer to the name it says so and resolves neither. When nothing matches exactly it
    may list similar names: those are suggestions for a human, NOT a resolution -- do not
    record a suggested actor_id as the actor's identity. A category never resolves.
    """
    got = resolve_names([params.name], params.actor_type, _register())
    if got["status"] == "category":
        return "Not resolvable: a category is a class of actor, not a named party."
    if got["status"] == "resolved":
        return "Resolved: %s -> %s %s (matched %r)" % (params.name, got["actor_id"], got["name"], got["matched"])
    if got["status"] == "ambiguous":
        return "Ambiguous: %r names more than one registered party: %s. Resolved to none." % (
            params.name, "; ".join("%s %s" % (e["actor_id"], e["name"]) for e in got["entries"]))
    if not got["suggestions"]:
        return "Unresolved: %r is not in the actor register." % params.name
    return "Unresolved: %r is not in the actor register. Similar names (suggestions only, not identity): %s" % (
        params.name, "; ".join("%s %s (%.2f)" % (s["actor_id"], s["name"], s["score"]) for s in got["suggestions"]))
```

Run: `.venv/bin/python evals/check_tool_surface.py`
Expected: REFUSED — "the server's tools are exactly KC_TOOLS" and "readOnlyHint ... exactly READ_ONLY_TOOLS" FAIL: a tool on the server that the lists do not name. Record this red.

- [ ] **Step 4: Add the tool to the lists**

`agents/extract_advisory.py` `KC_TOOLS`: insert `"knowledge_centre_resolve_actor",` before `"knowledge_centre_propose_link",`.
`agents/permissions.py` `READ_ONLY_TOOLS`: append `"knowledge_centre_resolve_actor",` after `"knowledge_centre_search_typologies",`; change "three read-only tools" to "four read-only tools" in the docstring and comments.

Do NOT change `SYSTEM_PROMPT`: using the tool during extraction is slice 2 (spec, Out of scope).

- [ ] **Step 5: Run the surface guards and probe the tool**

Run: `.venv/bin/python evals/check_tool_surface.py | tail -1` — Expected: `HELD (0 failures)`. Never pass `--live`.
Run: `.venv/bin/python evals/check_telemetry.py | tail -1` — Expected: `HELD (0 failures)`.
Run:

```bash
.venv/bin/python -c "
import asyncio, sys; sys.path.insert(0, '.')
from mcp_server import knowledge_centre_server as kc
f = getattr(kc.resolve_actor, 'fn', kc.resolve_actor)
for n, t in (('Milandr', None), ('Iran', None), ('IRGC', None), ('Iranian UAV entities', 'category')):
    print(asyncio.run(f(kc.ResolveActorInput(name=n, actor_type=t))))
"
```

Expected: Milandr → `Resolved: ... AO PKK Milandr`; Iran → `Unresolved` (with or without suggestions, never resolved); IRGC → `Ambiguous`; the category → `Not resolvable`. Paste all four lines in the report.

- [ ] **Step 6: Commit**

```bash
git add schemas/actor_match.py mcp_server/knowledge_centre_server.py agents/permissions.py agents/extract_advisory.py evals/check_tool_surface.py
git commit -m "Week 6.1: knowledge_centre_resolve_actor, read-only, resolving on exact matches only"
```

---

### Task 6: the resolution measurement and its guard

**Files:**
- Create: `evals/actor_resolution.py`, `evals/actor_resolution.json`
- Create: `evals/check_actor_resolution.py`

**Interfaces:**
- Consumes: `resolve`, `variants_of` (Tasks 3, 5); `build_register`, `load_labels`, `load_register` (Task 4).
- Produces: `evals.actor_resolution.load_records(records_dir=RECORDS) -> List[dict]` (selects `^ADV-\d{4}-\d{4}\.json$`) and `report(records, register, **resolve_flags) -> dict` with keys `named`, `resolved`, `ambiguous`, `unresolved`, `unresolved_with_suggestions`, `categories`, `per_advisory` ({advisory_id: {"named", "resolved"}}), `ambiguous_actors` ([{advisory_id, name, entries}]), `suggestions` ([{advisory_id, name, suggestions}]). Sub-project 2 reads the committed JSON.

- [ ] **Step 1: Write `evals/actor_resolution.py`**

```python
"""
How many of the extractor's named actors resolve to the governed register.

Usage:
    python evals/actor_resolution.py            # print the summary and write evals/actor_resolution.json
    python evals/actor_resolution.py --check    # fail if the committed report differs from a fresh one

The register is built from the golden LABELS; this reads the EXTRACTOR's records
(data/records/), so the measurement is not circular. Categories are counted apart and
never in the denominator: a class of actor cannot name a party. Suggestions are listed
so a reader can see what a similarity rule WOULD have claimed -- measured 2026-09-25,
mostly wrongly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.actor_match import resolve, variants_of  # noqa: E402
from tools.build_actor_register import load_register  # noqa: E402

RECORDS = ROOT / "data" / "records"
REPORT = ROOT / "evals" / "actor_resolution.json"
RECORD_NAME = re.compile(r"^ADV-\d{4}-\d{4}\.json$")


def load_records(records_dir: Path = RECORDS) -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(records_dir.iterdir())
            if RECORD_NAME.match(p.name)]


def report(records, register, **flags) -> dict:
    out = {"named": 0, "resolved": 0, "ambiguous": 0, "unresolved": 0, "unresolved_with_suggestions": 0,
           "categories": 0, "per_advisory": {}, "ambiguous_actors": [], "suggestions": []}
    for rec in sorted(records, key=lambda r: r["advisory_id"]):
        aid = rec["advisory_id"]
        per = out["per_advisory"].setdefault(aid, {"named": 0, "resolved": 0})
        for a in rec.get("actors", []):
            got = resolve(variants_of(a), a.get("actor_type"), register, **flags)
            if got["status"] == "category":
                out["categories"] += 1
                continue
            out["named"] += 1
            per["named"] += 1
            if got["status"] == "resolved":
                out["resolved"] += 1
                per["resolved"] += 1
            elif got["status"] == "ambiguous":
                out["ambiguous"] += 1
                out["ambiguous_actors"].append({"advisory_id": aid, "name": a["name"],
                                                "entries": [e["actor_id"] for e in got["entries"]]})
            else:
                out["unresolved"] += 1
                if got["suggestions"]:
                    out["unresolved_with_suggestions"] += 1
                    out["suggestions"].append({"advisory_id": aid, "name": a["name"],
                                               "suggestions": got["suggestions"]})
    return out


def _text(rep: dict) -> str:
    return json.dumps(rep, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Actor resolution over the extractor's records")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    rep = report(load_records(), load_register())
    if args.check:
        same = REPORT.exists() and REPORT.read_text(encoding="utf-8") == _text(rep)
        print("actor resolution matches the committed report" if same
              else "FAIL  actor resolution differs from the committed report")
        return 0 if same else 1
    REPORT.write_text(_text(rep), encoding="utf-8")
    print("named actors resolved: %d / %d (ambiguous %d, unresolved %d, of which %d have suggestions); "
          "categories %d, not counted" % (rep["resolved"], rep["named"], rep["ambiguous"], rep["unresolved"],
                                          rep["unresolved_with_suggestions"], rep["categories"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Produce the report**

Run: `.venv/bin/python evals/actor_resolution.py`
Expected: `named actors resolved: R / 105 ...; categories 55, not counted`, with R near 72 (the pre-plan flat-register figure; the ambiguous rule can move a few from resolved to ambiguous). Paste the line in the report. `named` must be 105 and `categories` 55: otherwise the record selection is wrong.

Run: `.venv/bin/python evals/actor_resolution.py --check` — Expected: matches, exit 0.

- [ ] **Step 3: Write `evals/check_actor_resolution.py`**

```python
"""
Pin actor identity: exact matches resolve, similar names only suggest, the builder never
guesses between two parties, and a category never resolves.

Usage:
    python evals/check_actor_resolution.py
    python evals/check_actor_resolution.py --mutate containment    # suggestions resolve; MUST fail
    python evals/check_actor_resolution.py --mutate ambiguous      # builder merges into the first match; MUST fail
    python evals/check_actor_resolution.py --mutate same-advisory  # builder merges within one advisory; MUST fail
    python evals/check_actor_resolution.py --mutate category       # a category may resolve; MUST fail

WHY. Measured 2026-09-25 against the extractor's records: of five actors a containment
rule at 0.60 would have resolved, four were wrong -- "Iran" and "Islamic Republic of Iran"
to Islamic Republic of Iran Shipping Lines, "Syria" to the Iran-Syria oil procurement
network, "Company X" to National Iranian Oil Company.

OFFLINE. The REAL labels and records; the register is rebuilt in memory so the builder
mutations take effect. No model, no PDF.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evals.actor_resolution import load_records, report  # noqa: E402
from schemas.actor_match import resolve  # noqa: E402
from tools.build_actor_register import build_register, load_labels  # noqa: E402

FLAGS = {"resolve": {}, "build": {}}


def checks() -> list:
    out = []
    entries, candidates = build_register(load_labels(), **FLAGS["build"])
    by_name = {e["name"]: e for e in entries}

    merged = [e for e in entries if len({n["advisory_id"] for n in e["named_in"]}) > 1]
    out.append((len(merged) >= 1, "at least one real cross-advisory merge exists (not vacuous)",
                "; ".join("%s %s" % (e["name"], [n["advisory_id"] for n in e["named_in"]]) for e in merged)))

    got = resolve(["Iran"], "jurisdiction", entries, **FLAGS["resolve"])
    out.append((got["status"] != "resolved",
                '"Iran" does NOT resolve (containment would name Islamic Republic of Iran Shipping Lines)', str(got)))
    got = resolve(["Syria"], "jurisdiction", entries, **FLAGS["resolve"])
    out.append((got["status"] != "resolved", '"Syria" does NOT resolve', str(got)))

    got = resolve(["Milandr"], "organisation", entries, **FLAGS["resolve"])
    out.append((got["status"] == "resolved" and got["name"] == "AO PKK Milandr",
                "an exact ALIAS resolves: Milandr -> AO PKK Milandr (not vacuous)", str(got)))

    irgc = by_name.get("Islamic Revolutionary Guard Corps", {})
    out.append(([n["advisory_id"] for n in irgc.get("named_in", [])] == ["ADV-2026-0010"],
                "the IRGC entry holds ADV-2026-0010 only: 0012's conflated IRGC-Qods Force was not merged into it",
                str(irgc.get("named_in"))))
    amb = [c for c in candidates if c["reason"] == "ambiguous" and c["advisory_id"] == "ADV-2026-0012"]
    out.append((len(amb) == 1, "the candidates list ADV-2026-0012's IRGC-Qods Force as ambiguous", str(amb)))
    got = resolve(["IRGC"], "organisation", entries, **FLAGS["resolve"])
    out.append((got["status"] == "ambiguous", '"IRGC" is AMBIGUOUS while the 0012 label conflates two parties',
                str(got)))

    witness = [{"advisory_id": "ADV-9999-0001", "actors": [
        {"name": "Alpha Trading LLC", "actor_type": "organisation", "aliases": ["Alpha"]},
        {"name": "Alpha Shipping LLC", "actor_type": "organisation", "aliases": ["Alpha"]}]}]
    w_entries, w_cand = build_register(witness, **FLAGS["build"])
    out.append((len(w_entries) == 2 and any(c["reason"] == "same advisory" for c in w_cand),
                "two actors of ONE advisory sharing an alias stay two entries, listed 'same advisory'",
                "%d entries, reasons %s" % (len(w_entries), sorted({c["reason"] for c in w_cand}))))

    got = resolve(["AO PKK Milandr"], "category", entries, **FLAGS["resolve"])
    out.append((got["status"] == "category", "a category never resolves, even on an exact name", str(got)))

    rep = report(load_records(), entries, **FLAGS["resolve"])
    out.append((rep["named"] == 105 and rep["categories"] == 55 and rep["resolved"] > 0,
                "the measurement reads 105 named actors and 55 categories, and resolves some",
                "named %d, categories %d, resolved %d" % (rep["named"], rep["categories"], rep["resolved"])))
    wrong = [s["name"] for s in rep["suggestions"] if s["name"] in ("Iran", "Syria", "Company X")]
    out.append((len(wrong) >= 1, "known wrong containment matches appear as SUGGESTIONS, not resolutions", str(wrong)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin actor identity")
    ap.add_argument("--mutate", choices=("containment", "ambiguous", "same-advisory", "category"))
    args = ap.parse_args(argv)
    if args.mutate == "containment":
        FLAGS["resolve"] = {"suggestions_resolve": True}
    elif args.mutate == "category":
        FLAGS["resolve"] = {"allow_category": True}
    elif args.mutate == "ambiguous":
        FLAGS["build"] = {"merge_ambiguous": True}
    elif args.mutate == "same-advisory":
        FLAGS["build"] = {"merge_same_advisory": True}
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

Measure two assumptions before relying on them, and if either is false adjust the CHECK (never the rules) and say so in the report: (1) "Iran", "Syria" or "Company X" appear among the report's `suggestions` (the pre-plan measurement found all three as containment-only matches); (2) the actor types passed in the direct `resolve` calls do not matter unless they are `category`.

- [ ] **Step 4: Run it, then every mutation**

Run: `.venv/bin/python evals/check_actor_resolution.py` — Expected: `HELD (0 failures)`, 11 checks.
Run, each with its own cache: `PYTHONPYCACHEPREFIX=/tmp/mut-<m> .venv/bin/python evals/check_actor_resolution.py --mutate <m>` for `containment`, `ambiguous`, `same-advisory`, `category`.
Expected: each prints `HELD: the probe detects the defect...`. Record which checks fail under each: `containment` must fail an Iran/Syria check; `ambiguous` the IRGC checks; `same-advisory` the witness; `category` the category check.

- [ ] **Step 5: Commit**

```bash
git add evals/actor_resolution.py evals/actor_resolution.json evals/check_actor_resolution.py
git commit -m "Week 6.1: measure actor resolution over the extractor's records, and guard identity"
```

---

### Task 7: every guard runs automatically

**Files:**
- Create: `tools/check_all.py`
- Create: `scripts/hooks/pre-commit` (executable)
- Create: `.github/workflows/checks.yml`
- Modify: `setup.sh` (hooks line), `CLAUDE.md` (week-6.1 state and one correction)

**Interfaces:**
- Consumes: every guard and `--check` from Tasks 1-6.
- Produces: `tools/check_all.py` with `GUARDS: List[Tuple[str, List[str], str]]` (name, argv after the interpreter, class) and `CLASSES = ("cold", "needs-pdfs", "needs-portfolio")`; CLI `--cold`, `--list`. Sub-project 2 adds a `needs-portfolio` entry.

- [ ] **Step 1: Measure each guard's class in a fresh clone**

```bash
rm -rf /tmp/fc08_cold && git clone -q . /tmp/fc08_cold
cd /tmp/fc08_cold && python3 -m venv .venv && .venv/bin/pip -q install -r requirements.txt
for g in evals/check_*.py; do .venv/bin/python "$g" >"/tmp/fc08_cold_$(basename "$g").txt" 2>&1; echo "$? $g"; done
for c in "tools/build_digests.py --batch-id slice1-2026-09-24 --check" "tools/build_actor_register.py --check" "evals/actor_resolution.py --check" "tools/review.py --check"; do .venv/bin/python $c >/dev/null 2>&1; echo "$? $c"; done
cd - >/dev/null
```

The clone is taken from the committed HEAD, so commit Tasks 1-6 first (they are). A guard is `cold` only if it exits 0 there. Record the table (command, cold exit code, and for each non-zero the first line of the reason from its `/tmp/fc08_cold_*.txt`) in the report.

Expected `cold`: `check_digest_routing`, `check_digest_batch`, `check_emergent_threshold`, `check_added_by`, `check_actor_resolution`, `build_digests --check`, `build_actor_register --check`, `actor_resolution --check`. Expected `needs-pdfs`: `check_review_gate`, `check_citations`, `check_proposal_contract`, `check_telemetry`, `check_tool_surface`, `check_twin_pairs`, `review.py --check`. The MEASUREMENT decides. Where it disagrees, use the measurement and say so. A guard failing cold for a reason other than the PDFs gets a class named for the real reason (add it to `CLASSES`), and the report says what it is.

`check_citations.py` may need arguments: read its usage docstring and give it the argv that checks every record in the governed set; report the argv chosen. Delete `/tmp/fc08_cold` afterwards.

- [ ] **Step 2: Write `tools/check_all.py`**

```python
"""
Run every guard, the way the pre-commit hook and CI do.

Usage:
    python tools/check_all.py           # everything; needs the gitignored PDFs
    python tools/check_all.py --cold    # only guards proved to pass in a fresh clone
    python tools/check_all.py --list    # the table, no runs

Each guard's CLASS was measured by running it in a fresh clone (week 6.1), not read
from its source:
  cold             passes from a fresh clone
  needs-pdfs       re-finds quotes on data/advisories/*.pdf, which is gitignored
  needs-portfolio  reads the portfolio checkout (sub-project 2)
--cold prints every other guard as NOT RUN, so a green CI run says what it did not cover.

Every evals/check_*.py must be in GUARDS, and every GUARDS entry must exist: a new
guard cannot be silently left out, and a deleted one cannot linger as a name.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GUARDS = [
    # (name, argv after the interpreter, class) -- classes from the fresh-clone measurement
    ("check_digest_routing", ["evals/check_digest_routing.py"], "cold"),
    ("check_digest_batch", ["evals/check_digest_batch.py"], "cold"),
    ("check_emergent_threshold", ["evals/check_emergent_threshold.py"], "cold"),
    ("check_added_by", ["evals/check_added_by.py"], "cold"),
    ("check_actor_resolution", ["evals/check_actor_resolution.py"], "cold"),
    ("build_digests --check", ["tools/build_digests.py", "--batch-id", "slice1-2026-09-24", "--check"], "cold"),
    ("build_actor_register --check", ["tools/build_actor_register.py", "--check"], "cold"),
    ("actor_resolution --check", ["evals/actor_resolution.py", "--check"], "cold"),
    ("check_review_gate", ["evals/check_review_gate.py"], "needs-pdfs"),
    ("check_proposal_contract", ["evals/check_proposal_contract.py"], "needs-pdfs"),
    ("check_telemetry", ["evals/check_telemetry.py"], "needs-pdfs"),
    ("check_tool_surface", ["evals/check_tool_surface.py"], "needs-pdfs"),
    ("check_twin_pairs", ["evals/check_twin_pairs.py"], "needs-pdfs"),
    ("check_citations", ["evals/check_citations.py"], "needs-pdfs"),
    ("review.py --check", ["tools/review.py", "--check"], "needs-pdfs"),
]
CLASSES = ("cold", "needs-pdfs", "needs-portfolio")


def coverage_problems() -> list:
    listed = {Path(argv[0]).name for _, argv, _ in GUARDS if argv[0].startswith("evals/check_")}
    present = {p.name for p in (ROOT / "evals").glob("check_*.py")}
    out = ["%s is a guard but is not in check_all's list" % n for n in sorted(present - listed)]
    out += ["check_all lists %s, which does not exist" % n for n in sorted(listed - present)]
    out += ["%s has unknown class %r" % (n, c) for n, _, c in GUARDS if c not in CLASSES]
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Run every guard")
    ap.add_argument("--cold", action="store_true", help="only guards proved to pass in a fresh clone")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    problems = coverage_problems()
    for p in problems:
        print("FAIL  %s" % p)
    if args.list:
        for name, _, cls in GUARDS:
            print("%-16s %s" % (cls, name))
        return 1 if problems else 0

    failed, not_run = list(problems), []
    for name, cmd, cls in GUARDS:
        if args.cold and cls != "cold":
            not_run.append("NOT RUN (%s): %s" % (cls, name))
            continue
        r = subprocess.run([sys.executable] + cmd, cwd=ROOT, capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        print("%-4s %-30s %s" % ("ok" if r.returncode == 0 else "FAIL", name, tail[:90]))
        if r.returncode != 0:
            failed.append(name)
    for line in not_run:
        print(line)
    print("\n%s: %d run, %d not run, %d failed" % ("PASS" if not failed else "FAIL",
                                                  len(GUARDS) - len(not_run), len(not_run), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Replace the classes (and `check_citations`'s argv) with the Step 1 measurement.

- [ ] **Step 3: Watch the coverage rule fail, then pass**

Run: `touch evals/check_zz_probe.py; .venv/bin/python tools/check_all.py --list; echo "exit $?"; rm evals/check_zz_probe.py`
Expected: `FAIL  check_zz_probe.py is a guard but is not in check_all's list`, exit 1.
Run: `.venv/bin/python tools/check_all.py` — Expected: `PASS: 15 run, 0 not run, 0 failed` (the count follows the list).
Run: `.venv/bin/python tools/check_all.py --cold` — Expected: `PASS`, and one `NOT RUN (needs-pdfs): <name>` line per `needs-pdfs` guard.

- [ ] **Step 4: The hook**

Create `scripts/hooks/pre-commit`:

```bash
#!/bin/bash
# fc-08 pre-commit: every guard, on the machine that holds the PDFs.
# Enable once per clone:  git config core.hooksPath scripts/hooks
# Never bypass with --no-verify: if a guard is red, the commit is not ready.
set -eu
cd "$(git rev-parse --show-toplevel)"
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" tools/check_all.py
```

Run: `chmod +x scripts/hooks/pre-commit && git config core.hooksPath scripts/hooks`

Verify it EXECUTES by breaking what it guards (a hook that is configured can still be dead):

```bash
HEAD_BEFORE=$(git rev-parse HEAD)
cp data/actor_register.json /tmp/fc08_reg.json
echo " " >> data/actor_register.json
git add data/actor_register.json
git commit -m "probe: must be refused"; echo "exit $?"
cp /tmp/fc08_reg.json data/actor_register.json && git reset -q data/actor_register.json
test "$(git rev-parse HEAD)" = "$HEAD_BEFORE" && echo "HEAD unchanged"
git status --short data/actor_register.json
```

Expected: the commit is REFUSED (non-zero exit, `build_actor_register --check` FAIL in the output), `HEAD unchanged`, and the last command prints nothing.

In `setup.sh`, after the `python -m pip install -r requirements.txt` line, add:

```bash
git config core.hooksPath scripts/hooks
```

- [ ] **Step 5: CI**

Create `.github/workflows/checks.yml`:

```yaml
name: checks
on:
  push:
  pull_request:
jobs:
  cold:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - run: pip install -r requirements.txt
      # The advisory PDFs are third-party publications and are not in the repository,
      # so guards that re-find quotes on their pages cannot run here. check_all prints
      # each one as NOT RUN; a green run is a statement about the cold guards only.
      - run: python tools/check_all.py --cold
```

The Step 1 fresh-clone measurement is the local proof of what this runner does. Its first real run waits for the owner's push.

- [ ] **Step 6: CLAUDE.md**

In `CLAUDE.md`'s build-state list, after the week-5 entry, add:

```markdown
- [~] **Week 6** (from 2026-09-25): spec `docs/superpowers/specs/2026-09-25-week6-landing-design.md`. Sub-project 1 DONE: a digest batch pins its inputs (`manifest.json`; `--check` survives later decisions and separates "inputs moved" from "same inputs, different output"; a batch is never overwritten); `propose_link` writes only `data/proposals/<run_id>.jsonl`; `knowledge_centre_resolve_actor` resolves on EXACT matches only against `data/actor_register.json` (similar names are suggestions, never identity -- measured, 4 of 5 containment matches named the wrong party); `tools/check_all.py` runs every guard, from `scripts/hooks/pre-commit` (enable per clone: `git config core.hooksPath scripts/hooks`) and cold on CI. NEXT: sub-project 2, the publish.
```

Also correct the imprecision parked in week 5 C: find "a suggestion-routed desk sees the whole advisory" and replace it with "a desk sees the whole advisory only when every reason it was routed is the agent's suggestion".

- [ ] **Step 7: Final run and commit**

Run: `.venv/bin/python tools/check_all.py` — Expected: `PASS`.
Run: `git status --short` — Expected: only this task's files.

```bash
git add tools/check_all.py scripts/hooks/pre-commit .github/workflows/checks.yml setup.sh CLAUDE.md
git commit -m "Week 6.1: every guard runs from one list, in a pre-commit hook and cold on CI"
```

This commit runs the hook itself, and must pass it.
