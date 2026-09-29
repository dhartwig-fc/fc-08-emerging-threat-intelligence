"""
Which feeds runs are waiting for a person (slice 2 C): back-pressure, expiry, and the eval marker, in ONE place.

A run folder under inbox/ is exactly one of:
  eval               items.json carries "eval": true (evals/run_feeds_triage.py, slice 2 B). NEVER pending:
                     B's 18 eval runs share the production inbox, and a Friday must not wait on them.
  accepted           tools/accept_run.py wrote accepted.json into it.
  nothing_to_decide  no items.json (refused or failed before listing), or no item listed as new.
  pending            listed at least one new item and has not been accepted.
inbox/expired/<run_id>/ holds runs `accept_run --expire` moved aside; nothing here counts them.

A pending run BLOCKS the next Friday while it is younger than EXPIRE_DAYS (spec section 5); from then on it is
expirable and does not block. A run's age is from the date in its id, never a file time.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import List, Tuple

from feeds import inbox

EXPIRE_DAYS = 14
EXPIRED = "expired"
ACCEPTED = "accepted.json"
EVAL, ACCEPTED_STATE, NOTHING, PENDING = "eval", "accepted", "nothing_to_decide", "pending"


def run_date(run_id: str) -> date:
    return date.fromisoformat(run_id[len("feeds-"):len("feeds-") + 10])


def classify(run_id: str, root: Path = inbox.INBOX_ROOT) -> str:
    folder = inbox.run_dir(run_id, root)
    if not (folder / inbox.ITEMS).exists():
        return NOTHING
    state = inbox.load(run_id, root)
    if state.get("eval"):
        return EVAL
    if (folder / ACCEPTED).exists():
        return ACCEPTED_STATE
    return PENDING if inbox.items(state) else NOTHING


def run_ids(root: Path = inbox.INBOX_ROOT) -> List[str]:
    root = Path(root)
    return sorted(p.name for p in root.iterdir() if p.is_dir() and inbox.RUN_ID.fullmatch(p.name)) \
        if root.exists() else []


def pending(root: Path = inbox.INBOX_ROOT, today: date = None) -> List[Tuple[str, int]]:
    """(run id, age in days) of every pending production run, oldest first."""
    today = today or date.today()
    return [(r, (today - run_date(r)).days) for r in run_ids(root) if classify(r, root) == PENDING]


def blocking(root: Path = inbox.INBOX_ROOT, today: date = None) -> List[Tuple[str, int]]:
    return [(r, age) for r, age in pending(root, today) if age < EXPIRE_DAYS]


def expirable(root: Path = inbox.INBOX_ROOT, today: date = None) -> List[Tuple[str, int]]:
    return [(r, age) for r, age in pending(root, today) if age >= EXPIRE_DAYS]


def expire(run_id: str, root: Path = inbox.INBOX_ROOT, today: date = None) -> Path:
    """Move a pending run of at least EXPIRE_DAYS to inbox/expired/<run_id>/. Moved, never deleted, and the
    ledger is not touched, so its items are listed again next Friday. Raises ValueError otherwise."""
    today = today or date.today()
    state = classify(run_id, root)
    if state != PENDING:
        raise ValueError("run %s is %s, not pending; only a pending run expires" % (run_id, state))
    age = (today - run_date(run_id)).days
    if age < EXPIRE_DAYS:
        raise ValueError("run %s is %d day(s) old; a run expires at %d" % (run_id, age, EXPIRE_DAYS))
    target = Path(root) / EXPIRED / run_id
    if target.exists():
        raise ValueError("%s already exists" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(inbox.run_dir(run_id, root), target)
    return target


def mark_accepted(run_id: str, record: dict, root: Path = inbox.INBOX_ROOT) -> None:
    """Write inbox/<run_id>/accepted.json ATOMICALLY. classify() below decides ACCEPTED_STATE purely by
    whether this file EXISTS -- it never validates its content -- so a crash part-way through a direct write
    would leave a truncated marker that classify() still reads as accepted, and the run would never come
    back for a decision even though nothing valid was ever recorded. Write the body to a temp file in the
    same directory first; only once it is complete, hard-link it into place (os.link raises if the target
    already exists, so this can never overwrite a marker either, closing the same window a bare exists-check
    leaves open); then always remove the temp file. A crash during the write leaves the temp file only, and
    the run still classifies as PENDING."""
    path = inbox.run_dir(run_id, root) / ACCEPTED
    if path.exists():
        raise ValueError("run %s was already accepted" % run_id)
    body = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tmp_path = path.with_name(".%s.tmp-%d" % (path.name, os.getpid()))
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(body)
        os.link(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
