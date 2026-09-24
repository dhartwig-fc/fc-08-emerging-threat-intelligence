"""
Build the owner label-pass dispute set from evidence already on disk.

Usage:
    python tools/build_label_disputes.py              # writes data/label_disputes/*.json

WHY. The golden labels are Claude-drafted and Claude-reviewed, and every label
records that in `label_status`. An owner pass is what turns the scores into a
statement about the agent rather than about Claude's reading habits. Until
2026-09-24 that pass was "re-read twenty labels", which is why it had not
happened. This reduces it to specific decisions, each carrying its evidence.

TWO DIRECTIONS, and they are not equally covered:

  add     A reviewer addition the golden label does not contain, taken from the
          merged records. The label may be TOO SMALL. Checked on all 20
          advisories, because the reviewer ran on all 20.

  strike  A label entry the ADV-2026-0004 triage judged THIN or UNSUPPORTED on
          the mechanism test. The label may be TOO LARGE. Checked on ONE
          advisory only.

So an advisory with no dispute here is UNCHALLENGED, not CONFIRMED. The page
that presents these says so, and this file is where to extend "strike" when
more labels are triaged.

DETERMINISTIC: the same inputs produce byte-identical files, so a regenerated
set shows only real changes in review.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "label_disputes"

TRIAGE = ROOT / "evals" / "traces" / "TRIAGE_ADV-2026-0004_LABEL.md"
# (advisory, typology, verdict) -- the triage's non-SUPPORTED entries.
STRIKE_CANDIDATES = (
    ("ADV-2026-0004", "TBML001", "UNSUPPORTED"),
    ("ADV-2026-0004", "SAN008", "UNSUPPORTED"),
    ("ADV-2026-0004", "TBML004", "THIN"),
    ("ADV-2026-0004", "SAN001", "THIN"),
)


def _library() -> dict:
    return {t["typology_id"]: t for t in
            json.loads((ROOT / "data" / "typologies.json").read_text(encoding="utf-8"))["typologies"]}


def _advisories() -> dict:
    d = json.loads((ROOT / "evals" / "golden" / "advisory_list.json").read_text(encoding="utf-8"))
    return {a["advisory_id"]: a for a in (d["advisories"] if isinstance(d, dict) else d)}


def _golden(aid: str) -> dict:
    return json.loads((ROOT / "evals" / "golden" / ("%s.json" % aid)).read_text(encoding="utf-8"))


def _triage_judgement(tid: str) -> str:
    """The '- Judgement:' paragraph of a typology's section in the triage."""
    text = TRIAGE.read_text(encoding="utf-8")
    m = re.search(r"^### %s .*?$(.*?)(?=^### |^## )" % re.escape(tid), text, re.S | re.M)
    if not m:
        raise SystemExit("triage has no section for %s -- the strike list and the triage disagree" % tid)
    j = re.search(r"^- Judgement:\s*(.*?)(?=^- |\Z)", m.group(1), re.S | re.M)
    if not j:
        raise SystemExit("triage section for %s has no Judgement line" % tid)
    # The page renders plain text, so markdown emphasis would reach the owner as
    # literal asterisks -- the defect fc-10 shipped to its public doctrine pages.
    plain = re.sub(r"\*\*|`", "", j.group(1))
    return re.sub(r"\s+", " ", plain).strip()


def build() -> list:
    lib, adv = _library(), _advisories()
    out = []

    for p in sorted((ROOT / "data" / "records_merged").glob("ADV-*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        aid = rec["advisory_id"]
        gold = {t["typology_id"] for t in _golden(aid)["typologies"] if t.get("typology_id")}
        for t in rec["typologies"]:
            tid = t.get("typology_id")
            if t.get("added_by") != "reviewer" or not tid or tid in gold:
                continue
            out.append({
                "direction": "add",
                "advisory_id": aid,
                "typology_id": tid,
                "question": "Should the %s label carry %s %s?" % (aid, tid, lib[tid]["label"]),
                "evidence": [{"page": c["page"], "quote": c["quote"]} for c in t["citations"]],
                "argument": t["review_justification"],
                "argument_source": "additive reviewer, merged under schema 1.4.0",
                "confidence": t["confidence"],
            })

    for aid, tid, verdict in STRIKE_CANDIDATES:
        g = [t for t in _golden(aid)["typologies"] if t.get("typology_id") == tid]
        if not g:
            raise SystemExit("%s no longer carries %s -- remove it from STRIKE_CANDIDATES" % (aid, tid))
        out.append({
            "direction": "strike",
            "advisory_id": aid,
            "typology_id": tid,
            "question": "Should the %s label keep %s %s?" % (aid, tid, lib[tid]["label"]),
            "evidence": [{"page": c["page"], "quote": c["quote"]} for c in g[0]["citations"]],
            # The judgement usually opens with its own verdict; do not say it twice.
            "argument": (lambda j: j if j.upper().startswith(verdict) else
                         "%s. %s" % (verdict, j))(_triage_judgement(tid)),
            "argument_source": "evals/traces/TRIAGE_ADV-2026-0004_LABEL.md",
            "confidence": g[0].get("confidence"),
        })

    out.sort(key=lambda d: (d["advisory_id"], d["direction"], d["typology_id"]))
    for i, d in enumerate(out):
        t = lib[d["typology_id"]]
        a = adv[d["advisory_id"]]
        d.update({
            "id": "%s__%s__%s" % (d["advisory_id"], d["typology_id"], d["direction"]),
            "order": i,
            "advisory_title": a["title"],
            "publisher": a.get("publisher"),
            "typology_label": t["label"],
            "family": t.get("family"),
            "doctrine_summary": t.get("summary", ""),
        })
    return out


def main() -> int:
    disputes = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for d in disputes:
        (OUT / ("%s.json" % d["id"])).write_text(json.dumps(d, indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8")
    adds = sum(1 for d in disputes if d["direction"] == "add")
    print("wrote %d disputes to %s (%d add, %d strike) across %d advisories"
          % (len(disputes), OUT, adds, len(disputes) - adds, len({d["advisory_id"] for d in disputes})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
