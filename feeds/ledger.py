"""
The seen-items ledger, data/feeds/seen.json: every listed item a person has already decided.

"New" means "not in this file", so the agent can never declare an item new or old. The file is
tracked, and tools/accept_run.py is its only writer (evals/check_feeds_ledger.py scans for any
other). A run that is never accepted leaves the file untouched, so its items are listed again the
next Friday. record_decisions() refuses the WHOLE call on any problem, so a partial write cannot
happen, and writes a canonical form (sorted, fixed layout), so the same decisions give the same
bytes whatever order they arrive in.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SEEN_PATH = ROOT / "data" / "feeds" / "seen.json"
SCHEMA = "fc08-seen-items/1"
DECISIONS = ("accept", "drop")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Key = Tuple[str, str]


def load(path: Path = SEEN_PATH) -> Dict[Key, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError("%s: schema %r, expected %r" % (path, data.get("schema"), SCHEMA))
    out: Dict[Key, dict] = {}
    for entry in data["items"]:
        key = (entry["source"], entry["item_id"])
        if key in out:
            raise ValueError("%s: %s:%s is recorded twice" % (path, key[0], key[1]))
        out[key] = entry
    return out


def dump(entries: Iterable[dict]) -> str:
    """The canonical bytes of the ledger holding these entries."""
    items = sorted(entries, key=lambda e: (e["source"], e["item_id"]))
    return json.dumps({"schema": SCHEMA, "items": items}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def record_decisions(run_id: str, decided_on: str, decisions: List[dict], path: Path = SEEN_PATH) -> List[dict]:
    if not DAY.match(decided_on):
        raise ValueError("decided_on %r is not YYYY-MM-DD" % decided_on)
    seen = load(path)
    new: Dict[Key, dict] = {}
    for d in decisions:
        key = (d["source"], d["item_id"])
        if d["decision"] not in DECISIONS:
            raise ValueError("%s:%s: decision %r is not one of %s" % (key[0], key[1], d["decision"], DECISIONS))
        if key in seen:
            raise ValueError("%s:%s was already decided, in run %s" % (key[0], key[1], seen[key]["first_seen_run"]))
        if key in new:
            raise ValueError("%s:%s is decided twice in one call" % key)
        new[key] = {"source": key[0], "item_id": key[1], "decision": d["decision"],
                    "first_seen_run": run_id, "decided_on": decided_on}
    tmp = Path(path).with_name("." + Path(path).name + ".tmp")
    tmp.write_text(dump(list(seen.values()) + list(new.values())), encoding="utf-8")
    os.replace(tmp, path)
    return list(new.values())
