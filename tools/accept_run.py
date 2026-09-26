"""
Decide the items of one feeds run: the ONLY way a live result enters tracked data.

Sub-project A builds the skeleton. It validates a run's decisions and records DROPS in the
seen-items ledger. Accepting an item also moves its record, queue file and document into the
tracked folders and gives it an advisory id (spec section 2); that path is sub-project C, and until
it exists an "accept" is refused, so the ledger can never say an item was accepted when nothing moved.

Usage:
    python tools/accept_run.py RUN_ID --decisions FILE [--dry-run]

FILE is JSON, {"<item key>": "accept" | "drop"}, with one entry for every item the run listed as
new, and nothing else. Any problem refuses the whole run; nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import inbox, ledger  # noqa: E402

ACCEPT_NOT_BUILT = ("accepting an item moves its record, queue file and document into tracked data, and that "
                    "path is built in sub-project C; this skeleton records drops only")


def plan(run_id: str, decisions: dict, *, inbox_root: Path = inbox.INBOX_ROOT,
         seen_path: Path = ledger.SEEN_PATH) -> list:
    """Validate everything and return the ledger entries to write. Raises ValueError on any problem."""
    if not (inbox.run_dir(run_id, inbox_root) / inbox.ITEMS).exists():
        raise ValueError("run %s has no %s in the inbox" % (run_id, inbox.ITEMS))
    if not isinstance(decisions, dict):
        raise ValueError("the decisions file must be a JSON object of item key -> decision")
    listed = {it["key"]: it for it in inbox.items(inbox.load(run_id, inbox_root))}
    missing, extra = sorted(set(listed) - set(decisions)), sorted(set(decisions) - set(listed))
    if missing or extra:
        raise ValueError("the decisions must cover every listed item exactly: missing %s, not listed %s"
                         % (missing, extra))
    bad = sorted(k for k, v in decisions.items() if v not in ledger.DECISIONS)
    if bad:
        raise ValueError("these decisions are not accept or drop: %s" % bad)
    accepted = sorted(k for k, v in decisions.items() if v == "accept")
    if accepted:
        raise ValueError("%s (accept requested for %s)" % (ACCEPT_NOT_BUILT, accepted))
    seen = ledger.load(seen_path)
    already = sorted(k for k, it in listed.items() if (it["source"], it["item_id"]) in seen)
    if already:
        raise ValueError("already decided in an earlier run: %s" % already)
    return [{"source": listed[k]["source"], "item_id": listed[k]["item_id"], "decision": decisions[k]}
            for k in sorted(listed)]


def main(argv: list, *, inbox_root: Path = inbox.INBOX_ROOT, seen_path: Path = ledger.SEEN_PATH,
         today: date = None) -> int:
    ap = argparse.ArgumentParser(description="Decide the items of one feeds run")
    ap.add_argument("run_id")
    ap.add_argument("--decisions", required=True, type=Path, help="JSON: item key -> accept | drop")
    ap.add_argument("--dry-run", action="store_true", help="validate and say what would be written")
    args = ap.parse_args(argv)
    try:
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        entries = plan(args.run_id, decisions, inbox_root=inbox_root, seen_path=seen_path)
    except (ValueError, OSError) as exc:
        print("REFUSED: %s" % exc)
        return 1
    if args.dry_run:
        print("DRY RUN: would record %d decision(s) for run %s" % (len(entries), args.run_id))
        return 0
    ledger.record_decisions(args.run_id, (today or date.today()).isoformat(), entries, path=seen_path)
    print("RECORDED: %d decision(s) for run %s in %s" % (len(entries), args.run_id, seen_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
