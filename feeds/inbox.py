"""
One run's working folder, inbox/<run_id>/ (gitignored): the only place a feeds run writes.

  items.json          per source: when it was listed, the pinned listing, its status, and the NEW items
  listings/<source>.* the raw listing bytes the adapter parsed
  docs/<sha256>.<ext> each fetched document, named by its own hash

A pinned file is immutable: writing different bytes to an existing path is refused. Every path is
resolved and must stay inside the run's folder.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import date
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
INBOX_ROOT = ROOT / "inbox"
ITEMS = "items.json"
RUN_ID = re.compile(r"^feeds-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}$")


def mint_run_id(day: date) -> str:
    return "feeds-%s-%s" % (day.isoformat(), secrets.token_hex(3))


def run_dir(run_id: str, root: Path = INBOX_ROOT) -> Path:
    if not RUN_ID.match(run_id or ""):
        raise ValueError("run id %r is not feeds-YYYY-MM-DD-xxxxxx" % run_id)
    return Path(root) / run_id


def load(run_id: str, root: Path = INBOX_ROOT) -> dict:
    path = run_dir(run_id, root) / ITEMS
    if not path.exists():
        return {"run_id": run_id, "sources": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save(run_id: str, state: dict, root: Path = INBOX_ROOT) -> None:
    folder = run_dir(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (".%s.tmp" % ITEMS)
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, folder / ITEMS)


def write_file(run_id: str, rel: str, data: bytes, root: Path = INBOX_ROOT) -> str:
    folder = run_dir(run_id, root).resolve()
    target = (folder / rel).resolve()
    if folder not in target.parents:
        raise ValueError("%r is outside the run's inbox" % rel)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("%s is pinned; refusing to overwrite it with different bytes" % rel)
        return rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel


def items(state: dict) -> List[dict]:
    return [it for name in sorted(state["sources"]) for it in state["sources"][name].get("items", [])]


def find_item(state: dict, key: str) -> Optional[dict]:
    return next((it for it in items(state) if it["key"] == key), None)
