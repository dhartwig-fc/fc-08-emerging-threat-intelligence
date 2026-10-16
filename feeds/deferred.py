"""
Items the owner DEFERRED in an accepted Friday run: the record a later run carries them forward from.

A defer is not a decision. tools/accept_run.py writes accept and drop to the decisions ledger (feeds/ledger.py)
and a defer only to that run's data/feeds/runs/<run_id>/accepted.json, so until 2026-10-16 a deferred item came
back only while its source still LISTED it. OFAC's recent-actions page shows ten actions; Tren de Aragua (20260930) and Sinaloa
(20260929), deferred on 2026-10-11, had fallen off it by 2026-10-16 and were lost without a word.

deferred_items() reads every accepted run's deferred keys, takes each item as its run's items.json recorded it
(the same fields feeds_list_new writes, without the fetched document), and tags it with the run that last
deferred it. It does not consult the ledger: the caller drops anything decided since, because the ledger it
reads is the caller's (the feeds server's, swapped for a temporary one by its guards).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "data" / "feeds" / "runs"
ITEM_FIELDS = ("key", "source", "item_id", "title", "url", "published", "summary")


def deferred_items(runs_dir: Path = RUNS_DIR) -> Dict[str, dict]:
    """key -> the deferred item, with carried_from naming the latest accepted run that deferred it.

    Runs are ordered by their decision date, then by run id. A deferred key missing from its own run's
    items.json is a corrupt record and raises: carrying forward a key with no url would be a silent loss."""
    runs = []
    for run in sorted(Path(runs_dir).iterdir()) if Path(runs_dir).is_dir() else []:
        acc_path = run / "accepted.json"
        if not acc_path.is_file():
            continue
        acc = json.loads(acc_path.read_text(encoding="utf-8"))
        if acc.get("deferred"):
            runs.append((acc.get("decided_on", ""), run.name, run, acc["deferred"]))
    out: Dict[str, dict] = {}
    for _, name, run, keys in sorted(runs):
        state = json.loads((run / "items.json").read_text(encoding="utf-8"))
        listed = {it["key"]: it for block in state["sources"].values() for it in block.get("items", [])}
        for key in keys:
            it = listed.get(key)
            if it is None:
                raise ValueError("%s: deferred item %s is not in its items.json" % (name, key))
            out[key] = dict({f: it.get(f, "") for f in ITEM_FIELDS}, carried_from=name)
    return out
