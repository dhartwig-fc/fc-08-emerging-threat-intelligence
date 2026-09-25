"""
Build (or check) one batch of desk digests.

Usage:
    python tools/build_digests.py --batch-id slice1-2026-09-24            # write data/digests/<batch_id>/
    python tools/build_digests.py --batch-id slice1-2026-09-24 --check    # prove the committed batch
    python tools/build_digests.py --batch-id slice1-2026-09-24 --backfill-manifest
    python tools/build_digests.py --current --check                        # check the batch data/digests/CURRENT names

data/digests/CURRENT names the batch the guards check, one id and a newline. It is data,
not a string in tools/check_all.py: cutting a new batch is one tracked edit beside the
batch, and the guard list does not change.

A batch is a SNAPSHOT. manifest.json pins what it was built from: the decision log's
first N lines (count and hash), the hash of every record and queue file, and the hash of
the typology library, advisory list and routing table it read (the "config" section --
build_batch() reads all three, and any of them moving after a batch changes what a fresh
build renders just as surely as a moved record does). The log is append-only, so --check
rebuilds from exactly those N lines however many decisions land later, and says which of
three things went wrong when it fails:

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
from governance.routing import ROUTING, load_routing  # noqa: E402

BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
MANIFEST = "manifest.json"
CURRENT = DIGESTS_DIR / "CURRENT"
_MUTATE = None  # set only by evals/check_digest_batch.py through --_mutate


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_paths(routing_path: Path) -> dict:
    """Filename -> path for the governed inputs build_batch() reads besides records/queue/log.

    Keyed by filename, not path, so a temp copy of the routing table under a different
    directory but the same basename is still recognised as the same pinned input.
    """
    return {LIBRARY.name: LIBRARY, ADVISORY_LIST.name: ADVISORY_LIST, routing_path.name: routing_path}


def build(batch_id: str, record_paths, queue_paths, log_path: Path, log_lines=None,
         routing_path: Path = ROUTING):
    """(desk -> Markdown, manifest) from exactly these inputs and the first log_lines of the log."""
    lines, log_sha, decisions = gd.log_prefix(log_lines, log_path)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in record_paths]
    library = {t["typology_id"]: t for t in json.loads(LIBRARY.read_text(encoding="utf-8"))["typologies"]}
    advisories = {a["advisory_id"]: a for a in json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    proposals, _ = load_queue_files(queue_paths)
    routing = load_routing(routing_path)
    batch = build_batch(batch_id, records, library, routing, gd.latest(decisions),
                        {p.proposal_id: p for p in proposals}, advisories)
    manifest = {
        "batch_id": batch_id,
        "decision_log": {"lines": lines, "sha256": log_sha},
        "records": {p.name: _sha(p) for p in record_paths},
        "proposals": {p.name: _sha(p) for p in queue_paths},
        "config": {name: _sha(p) for name, p in _config_paths(routing_path).items()},
    }
    return batch, manifest


def _current_inputs(records_dir: Path, queue_dir: Path):
    return (sorted(records_dir.glob("ADV-*.json")),
            sorted(queue_dir.glob("*.jsonl")) if queue_dir.exists() else [])


def _manifest_text(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def check(batch_id: str, out_dir: Path, records_dir: Path, queue_dir: Path, log_path: Path,
         routing_path: Path = ROUTING) -> list:
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
    config_paths = _config_paths(routing_path)
    moved += [name for name, want in sorted(m.get("config", {}).items())
              if name not in config_paths or not config_paths[name].exists()
              or _sha(config_paths[name]) != want]
    if moved:
        return ["inputs moved since this batch: %s" % n for n in moved]

    rebuild_from = None if _MUTATE == "prefix" else pinned["lines"]
    batch, rebuilt = build(batch_id, [records_dir / n for n in sorted(m["records"])],
                           [queue_dir / n for n in sorted(m["proposals"])], log_path, rebuild_from,
                           routing_path)
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
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--batch-id")
    which.add_argument("--current", action="store_true",
                       help="with --check: the batch named in data/digests/CURRENT")
    ap.add_argument("--records-dir", type=Path, default=RECORDS_DIR)
    ap.add_argument("--queue-dir", type=Path, default=QUEUE_DIR)
    ap.add_argument("--log", type=Path, default=gd.LOG)
    ap.add_argument("--out-dir", type=Path, default=DIGESTS_DIR)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--backfill-manifest", action="store_true")
    ap.add_argument("--_mutate", choices=("prefix", "overwrite"), help=argparse.SUPPRESS)
    ap.add_argument("--routing", type=Path, default=ROUTING, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    _MUTATE = args._mutate
    if _MUTATE == "overwrite" and args.out_dir.resolve() == DIGESTS_DIR.resolve():
        # The mutation exists to prove the guard catches an overwrite -- over TEMP copies.
        # Pointed at the real tree it would rewrite committed evidence.
        print("REFUSED: the overwrite mutation never runs against %s; give --out-dir a temporary directory"
              % DIGESTS_DIR.relative_to(ROOT), file=sys.stderr)
        return 2
    if args.current:
        if not args.check:
            print("--current is only for --check: a new batch is built under an id you name", file=sys.stderr)
            return 2
        if args.out_dir.resolve() != DIGESTS_DIR.resolve():
            print("--current reads %s and checks that tree only; name --batch-id with --out-dir"
                  % CURRENT.relative_to(ROOT), file=sys.stderr)
            return 2
        if not CURRENT.exists():
            print("%s is missing: no current batch is named" % CURRENT.relative_to(ROOT), file=sys.stderr)
            return 2
        text = CURRENT.read_text(encoding="utf-8")
        args.batch_id = text[:-1] if text.endswith("\n") else text
        if not BATCH_ID.fullmatch(args.batch_id):
            print("%s holds %r, which is not a batch id (must match %s)"
                  % (CURRENT.relative_to(ROOT), text, BATCH_ID.pattern), file=sys.stderr)
            return 2
    if not BATCH_ID.match(args.batch_id):
        print("batch id must match %s" % BATCH_ID.pattern, file=sys.stderr)
        return 2
    folder = args.out_dir / args.batch_id

    if args.check:
        problems = check(args.batch_id, args.out_dir, args.records_dir, args.queue_dir, args.log, args.routing)
        for p in problems:
            print("FAIL  %s" % p)
        print("batch %s matches a fresh build from its pinned inputs" % args.batch_id if not problems
              else "batch %s does NOT match" % args.batch_id)
        return 1 if problems else 0

    records, queue = _current_inputs(args.records_dir, args.queue_dir)
    batch, manifest = build(args.batch_id, records, queue, args.log, routing_path=args.routing)

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
