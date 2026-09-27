"""
Write the draft triage labels once: evals/feeds/labels.json, from the drafter's notes (slice 2 B, Task 6).

Usage:
    python tools/write_feeds_labels.py --show KEY                      # print an item and its pinned pages
    python tools/write_feeds_labels.py --drafts FILE --drafted-on YYYY-MM-DD

FILE is JSON Lines, one {"key", "label", "reason"} per scored catalogue item. The tool validates every
line against the catalogue (each scored key exactly once; relevant | not_relevant; a reason of 1..300
characters) and writes labels.json in canonical form with the RUBRIC below and its sha256. It refuses
if labels.json exists: the drafts are frozen before the first repeat, and the owner's later decisions
live in evals/owner_decisions/, never in this file.

The drafter is Claude in the implementing session, reading each item with --show, never the triage
agent and never its output: the drafts must be written and committed before any repeat runs.
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
from feeds.triage import REASON_MAX, VERDICTS, page_texts  # noqa: E402

EVAL_DIR = ROOT / "evals" / "feeds"
CATALOGUE = EVAL_DIR / "catalogue.json"
LABELS = EVAL_DIR / "labels.json"
DOCS = EVAL_DIR / "docs"
SCHEMA = "fc08-triage-labels/1"

RUBRIC = """Label the publication as pinned: the page feeds_fetch pinned for the item, which for FinCEN and OFSI is the landing page (the advisory itself is a linked PDF that is not fetched), read together with the item's title and summary.
relevant: the publication describes methods, red flags or cases of financial crime that a typology could hold -- a money-laundering, fraud, sanctions-evasion, terrorist-financing, proliferation-financing or corruption technique; indicators an analyst could screen for; or an enforcement, penalty or settlement case that says what was done. A FinCEN advisory is relevant when its landing page names such a subject. A translation of a relevant advisory is relevant (whether to accept a duplicate is accept_run's question, not triage's). A rescinded advisory is labelled by its content, and the reason says it was rescinded.
not_relevant: a bare designation or delisting list, a licence or general licence, a notice of a regulatory, procedural or website change, an event or webinar listing, or guidance that restates obligations without describing a method, red flag or case.
An OFAC recent action that combines designations with anything relevant (an enforcement action, a settlement, an advisory or alert) is relevant.
When the pinned text leaves the question open, the label is relevant, and the reason says what was missing (the spec's asymmetry: when in doubt, keep it)."""


def show(key: str) -> int:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    item = next((it for it in catalogue["items"] if it["key"] == key), None)
    if item is None:
        print("no scored catalogue item %s" % key)
        return 1
    print("%s | %s | %s\n%s\nsummary: %s\n" % (item["key"], item["published"], item["title"], item["url"],
                                               item["summary"] or "-"))
    doc = item["document"]
    for n, text in enumerate(page_texts(DOCS / ("%s.%s" % (doc["sha256"], doc["ext"]))), 1):
        print("=== PAGE %d ===\n%s\n" % (n, text.strip()))
    return 0


def write(drafts: Path, drafted_on: str) -> int:
    if LABELS.exists():
        print("REFUSED: %s exists; the drafts are frozen" % LABELS.relative_to(ROOT))
        return 1
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", drafted_on):
        print("REFUSED: --drafted-on %r is not YYYY-MM-DD" % drafted_on)
        return 1
    catalogue_raw = CATALOGUE.read_bytes()
    keys = {it["key"] for it in json.loads(catalogue_raw)["items"]}
    labels, problems = {}, []
    for n, line in enumerate(drafts.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except ValueError as exc:
            problems.append("line %d: not JSON (%s)" % (n, exc))
            continue
        if not isinstance(d, dict):
            problems.append("line %d: not a JSON object" % n)
            continue
        if not isinstance(d.get("reason"), str):
            problems.append("line %d: %r needs a reason that is a string" % (n, d.get("key")))
            continue
        reason = d["reason"].strip()
        if not isinstance(d.get("key"), str) or d["key"] not in keys:
            problems.append("line %d: %r is not a scored catalogue item" % (n, d.get("key")))
        elif d["key"] in labels:
            problems.append("line %d: %s is labelled twice" % (n, d["key"]))
        elif d.get("label") not in VERDICTS or not 1 <= len(reason) <= REASON_MAX:
            problems.append("line %d: %s needs relevant | not_relevant and a reason of 1..%d characters"
                            % (n, d["key"], REASON_MAX))
        else:
            labels[d["key"]] = {"label": d["label"], "reason": reason}
    missing = sorted(keys - set(labels))
    if missing:
        problems.append("unlabelled: %s" % ", ".join(missing))
    if problems:
        print("REFUSED, nothing written:\n  " + "\n  ".join(problems))
        return 1
    doc = {"schema": SCHEMA, "catalogue_sha256": hashlib.sha256(catalogue_raw).hexdigest(), "rubric": RUBRIC,
           "rubric_sha256": hashlib.sha256(RUBRIC.encode("utf-8")).hexdigest(), "drafted_by": "claude-in-session",
           "drafted_on": drafted_on, "labels": labels}
    LABELS.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    rel = sum(1 for v in labels.values() if v["label"] == "relevant")
    print("WROTE %s: %d labels, %d relevant, %d not_relevant" % (LABELS.relative_to(ROOT), len(labels), rel,
                                                                len(labels) - rel))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Write the draft triage labels once")
    ap.add_argument("--show", metavar="KEY")
    ap.add_argument("--drafts", type=Path)
    ap.add_argument("--drafted-on")
    args = ap.parse_args(argv)
    if args.show:
        return show(args.show)
    if not (args.drafts and args.drafted_on):
        ap.error("--drafts and --drafted-on, or --show")
    return write(args.drafts, args.drafted_on)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
