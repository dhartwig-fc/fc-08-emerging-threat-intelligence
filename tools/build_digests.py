"""
Build (or check) one batch of desk digests.

Usage:
    python tools/build_digests.py --batch-id slice1-2026-09-24            # write data/digests/<batch_id>/<desk>.md
    python tools/build_digests.py --batch-id slice1-2026-09-24 --check    # fail if the committed files differ

A batch is a SNAPSHOT: the records, the decision log and the proposal queue as
they stood when it was built. A later decision does not change a committed batch;
build a new batch id for the new state. --check proves a committed batch still
matches what its inputs rebuild to -- it will fail after new decisions, which is
the signal to cut a new batch, not to edit the old one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance.digest import DIGESTS_DIR, NO_ADVISORIES, RECORDS_DIR, build_batch  # noqa: E402
from governance.proposals import ADVISORY_LIST, LIBRARY, load_queue  # noqa: E402
from governance.routing import load_routing  # noqa: E402

BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def build(batch_id: str, records_dir: Path = RECORDS_DIR) -> dict:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(records_dir.glob("ADV-*.json"))]
    library = {t["typology_id"]: t for t in json.loads(LIBRARY.read_text(encoding="utf-8"))["typologies"]}
    advisories = {a["advisory_id"]: a for a in json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    proposals, _ = load_queue()
    return build_batch(batch_id, records, library, load_routing(), gd.latest(gd.load_log()),
                       {p.proposal_id: p for p in proposals}, advisories)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build or check a batch of desk digests")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--records-dir", type=Path, default=RECORDS_DIR)
    ap.add_argument("--out-dir", type=Path, default=DIGESTS_DIR)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if not BATCH_ID.match(args.batch_id):
        print("batch id must match %s" % BATCH_ID.pattern, file=sys.stderr)
        return 2

    batch = build(args.batch_id, args.records_dir)
    folder = args.out_dir / args.batch_id
    if args.check:
        problems = []
        for desk, text in batch.items():
            path = folder / ("%s.md" % desk)
            if not path.exists():
                problems.append("%s is missing" % path.name)
            elif path.read_text(encoding="utf-8") != text:
                problems.append("%s differs from a fresh build" % path.name)
        extra = sorted(p.name for p in folder.glob("*.md") if p.stem not in batch) if folder.exists() else []
        problems += ["%s is not a desk in this batch" % n for n in extra]
        for p in problems:
            print("FAIL  %s" % p)
        print("batch %s matches a fresh build" % args.batch_id if not problems
              else "batch %s does NOT match a fresh build" % args.batch_id)
        return 1 if problems else 0

    folder.mkdir(parents=True, exist_ok=True)
    for desk, text in batch.items():
        (folder / ("%s.md" % desk)).write_text(text, encoding="utf-8")
    routed = sum(1 for t in batch.values() if NO_ADVISORIES not in t)
    print("wrote %d digests to %s (%d desks receive advisories)" % (len(batch), folder, routed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
