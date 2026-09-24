"""
Apply the owner's label-pass decisions to the golden set.

Usage:
    python tools/apply_label_decisions.py <decisions> --date 2026-09-24 [--dry-run]

<decisions> is either the text the label-pass page copies ("Copy my decisions"),
one line per dispute:

    ADV-2026-0002 BA008 add: Leave out -- homonym, not correspondent banking

or a JSON list of the page's database documents ({advisory_id, typology_id,
direction, decision, note}). Either way the decisions are written first to
evals/owner_decisions/label_pass_<date>.json, the tracked evidence of what the
owner decided, and only then applied.

WHAT EACH DECISION DOES

  add    + accept   the reviewer's entry is copied from data/records_merged into
                    the golden label, citations and all. Its reviewer-only
                    fields are dropped: a golden label is not a merged record.
  strike + accept   the entry is removed from the golden label.
  reject / unsure / undecided
                    no change to the label. Recorded, and unsure/undecided are
                    reported as still open.

Every advisory with at least one decision gets its label_status in
advisory_list.json amended to say how many disputed entries the owner decided;
the evidence file says which. The label's own extraction_notes are left alone --
they are capped at 4000 characters and describe the labelling, not the pass. The owner
decided the disputed entries, not the whole label, so the status never claims
the label is owner-reviewed outright.

REFUSES, writing nothing, when any label it would write fails the schema, when
a decision names a dispute that does not exist in
data/label_disputes, names one twice, adds an id the label already carries, or
strikes one it does not. The last two are what a second run of the same
decisions looks like, so applying twice is refused rather than silently doubled.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden"
DISPUTES = ROOT / "data" / "label_disputes"
MERGED = ROOT / "data" / "records_merged"
EVIDENCE = ROOT / "evals" / "owner_decisions"

# The page's button wording, per direction, back to the stored decision value.
CHOICES = {
    "add to label": "accept", "leave out": "reject",
    "strike": "accept", "keep": "reject",
    "unsure": "unsure", "(not decided)": None,
    "accept": "accept", "reject": "reject",
}
LINE = re.compile(r"^(ADV-\d{4}-\d{4})\s+(\S+)\s+(add|strike):\s*(.*?)(?:\s+--\s+(.*))?$")


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def parse(text: str) -> list:
    text = text.strip()
    if text.startswith("["):
        rows = json.loads(text)
        return [{"advisory_id": r["advisory_id"], "typology_id": r["typology_id"],
                 "direction": r["direction"], "decision": r.get("decision"),
                 "note": (r.get("note") or "").strip(),
                 "decided_at": r.get("decided_at")} for r in rows]
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not line.startswith("ADV-"):
            continue  # the header line, blank lines, chat chatter around a paste
        m = LINE.match(line)
        if not m:
            raise SystemExit("cannot read decision line: %r" % line)
        aid, tid, direction, choice, note = m.groups()
        key = choice.strip().lower()
        if key not in CHOICES:
            raise SystemExit("unknown choice %r on line: %r" % (choice, line))
        out.append({"advisory_id": aid, "typology_id": tid, "direction": direction,
                    "decision": CHOICES[key], "note": (note or "").strip()})
    return out


def _check(decisions: list) -> dict:
    disputes = {p.stem for p in DISPUTES.glob("*.json")}
    seen = {}
    for d in decisions:
        did = "%s__%s__%s" % (d["advisory_id"], d["typology_id"], d["direction"])
        if did not in disputes:
            raise SystemExit("no such dispute: %s -- decisions must answer data/label_disputes" % did)
        if did in seen:
            raise SystemExit("dispute decided twice: %s" % did)
        seen[did] = d
    return seen


def apply(decisions: list, date: str, dry_run: bool) -> int:
    by_id = _check(decisions)
    golden = {}
    changes = {}  # advisory -> [(verb, typology, direction)]
    for did, d in sorted(by_id.items()):
        aid, tid = d["advisory_id"], d["typology_id"]
        g = golden.setdefault(aid, json.loads((GOLDEN / ("%s.json" % aid)).read_text(encoding="utf-8")))
        held = [t.get("typology_id") for t in g["typologies"]]
        changes.setdefault(aid, [])
        if d["decision"] != "accept":
            changes[aid].append((d["decision"] or "undecided", tid, d["direction"]))
            continue
        if d["direction"] == "add":
            if tid in held:
                raise SystemExit("%s already carries %s -- were these decisions applied before?" % (aid, tid))
            rec = json.loads((MERGED / ("%s.json" % aid)).read_text(encoding="utf-8"))
            src = [t for t in rec["typologies"]
                   if t.get("typology_id") == tid and t.get("added_by") == "reviewer"]
            if len(src) != 1:
                raise SystemExit("%s: expected one reviewer entry for %s in records_merged, found %d"
                                 % (aid, tid, len(src)))
            entry = {k: v for k, v in src[0].items() if k not in ("added_by", "review_justification")}
            g["typologies"].append(entry)
            changes[aid].append(("added", tid, "add"))
        else:
            if tid not in held:
                raise SystemExit("%s does not carry %s -- were these decisions applied before?" % (aid, tid))
            g["typologies"] = [t for t in g["typologies"] if t.get("typology_id") != tid]
            changes[aid].append(("struck", tid, "strike"))

    listing_path = GOLDEN / "advisory_list.json"
    listing = json.loads(listing_path.read_text(encoding="utf-8"))
    rows = listing["advisories"] if isinstance(listing, dict) else listing
    # A rejected ADD leaves an entry out; a rejected STRIKE keeps one in. Both
    # leave the label as it was, so the summary says which, not "rejected".
    words = {("added", "add"): "added", ("struck", "strike"): "struck",
             ("reject", "add"): "declined to add", ("reject", "strike"): "kept",
             ("unsure", "add"): "left open (unsure) on adding",
             ("unsure", "strike"): "left open (unsure) on striking",
             ("undecided", "add"): "made no decision on adding",
             ("undecided", "strike"): "made no decision on striking"}
    for row in rows:
        aid = row["advisory_id"]
        if aid not in changes:
            continue
        c = changes[aid]
        n_acc = sum(1 for v, _, _ in c if v in ("added", "struck"))
        n_rej = sum(1 for v, _, _ in c if v == "reject")
        base = row["label_status"].replace("; awaiting owner review", "")
        row["label_status"] = ("%s; owner-decided %s on %d disputed entr%s (%d changed, %d left as labelled, "
                               "%d open); the rest of the label awaits owner review"
                               % (base, date, len(c), "y" if len(c) == 1 else "ies",
                                  n_acc, n_rej, len(c) - n_acc - n_rej))

    evidence = {
        "date": date,
        "what": "Owner decisions on the label-pass disputes (data/label_disputes). "
                "Covers the disputed entries only; unchallenged entries are not confirmed by this file.",
        "decisions": [dict(by_id[k], id=k) for k in sorted(by_id)],
    }
    for aid in sorted(changes):
        print("%s  %s" % (aid, "; ".join("%s %s" % (words[(v, d)], tid) for v, tid, d in changes[aid])))
    open_ = sorted(k for k, d in by_id.items() if d["decision"] in (None, "unsure"))
    print("%d decisions: %d applied to labels, %d open%s"
          % (len(by_id), sum(1 for d in by_id.values() if d["decision"] == "accept"), len(open_),
             (" (" + ", ".join(open_) + ")") if open_ else ""))
    # Validate before writing, so a label the schema would reject is never
    # written. The first real run appended a provenance sentence to
    # extraction_notes and pushed ADV-2026-0018 past its 4000-character cap;
    # only a separate validate_record.py run caught it.
    sys.path.insert(0, str(ROOT))
    from schemas.advisory import AdvisoryRecord
    for aid, g in sorted(golden.items()):
        try:
            AdvisoryRecord.model_validate(g)
        except ValueError as exc:
            raise SystemExit("%s would no longer validate -- nothing written:\n%s" % (aid, exc))
    if dry_run:
        print("dry run: nothing written")
        return 0
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / ("label_pass_%s.json" % date)).write_text(_dump(evidence), encoding="utf-8")
    for aid, g in golden.items():
        (GOLDEN / ("%s.json" % aid)).write_text(_dump(g), encoding="utf-8")
    listing_path.write_text(_dump(listing), encoding="utf-8")
    print("wrote evidence, %d golden labels and advisory_list.json" % len(golden))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Apply the owner's label-pass decisions to the golden set")
    ap.add_argument("decisions", type=Path)
    ap.add_argument("--date", required=True, help="the day the owner decided, YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return apply(parse(a.decisions.read_text(encoding="utf-8")), a.date, a.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
