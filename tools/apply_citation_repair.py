"""
Apply the owner's citation-repair decision of 2026-09-25 to data/records_merged.

Usage:
    python tools/apply_citation_repair.py --build-evidence   # once: write the evidence file
    python tools/apply_citation_repair.py --apply            # repair data/records_merged in place
    python tools/apply_citation_repair.py --check            # prove records_merged == repair(merge(...))

THE DECISION. evals/check_citations.py --all found 118 citations in the published
merged records whose quote is not on the page they name. The shared matcher then gained
an ARTEFACT tier (footnote markers, line-break hyphens): 18 of the 118 were true quotes
it could not see, and the corrected set is 103 (evals/known_citation_defects.json). The
owner's choice (a), re-applied to the corrected set:
  off_page, found on exactly ONE other page      -> RE-PAGE to that page
  missing, or off_page found on 2+ pages         -> REMOVE the citation
  a typology / actor / indicator left uncited    -> REMOVE the item
"No citation, no fact." The counts are the evidence file's, measured when it was built;
evals/check_citation_repair.py pins them. A first attempt on the uncorrected 118 removed
31 items, most of them true facts, and was reset before it was pushed. data/records -- the extractor's own output, the evidence for
every published extraction figure -- is never touched; it still holds its defects.

EVIDENCE FIRST, THEN ACT, the house pattern of tools/apply_label_decisions.py.
--build-evidence writes evals/owner_decisions/citation_repair_2026-09-25.json from the
frozen baseline and the pre-repair merged records: one row per citation (identity,
action, the pages the quote WAS found on, why) and one row per removed item. Quotes are
named by sha256, never by text. It refuses to overwrite an existing evidence file and
refuses to build from an empty baseline (that is what the baseline looks like AFTER the
repair, when there is nothing left to decide).

THE OWNER'S WORDS AND THE IMPLEMENTER'S ARE KEPT APART. The evidence's "decision" is the
owner's text verbatim (DECISION below). Everything this tool decided in carrying it out
goes in "implementation_notes" (IMPLEMENTATION_NOTES), so nobody reads an implementation
choice as something the owner ruled on.

A RE-PAGED CITATION LOSES ITS printed_folio -- an implementation note, not the owner's
ruling. The folio is the number printed on the page the extractor cited, which is the
wrong page -- ADV-2026-0001's page 26 carried folio "24" and its quote is on page 28.
Keeping it would leave a citation saying page 28, folio 24. The folio is not recomputed
(that would be a new claim nobody checked); it is dropped, and the evidence row records
the value dropped.

IDENTITY is the one check_citations uses -- advisory_id, section, item label (by
check_citations' own _label_for, imported, not restated), page, quote_sha256 -- so this
tool and the guard that produced the baseline cannot disagree about which citation is
meant.

repair(record, evidence) is PURE and refuses (RepairError) rather than guessing:
  - an evidence citation not found EXACTLY once in the record
  - a removed item that still has a citation after the repair
  - an item left uncited that the evidence does not list as removed
  - a listed removed item not present exactly once
  - a recorded dropped printed_folio that is not the one the record carries
So --apply on already-repaired records refuses cleanly: the re-paged citations are no
longer on their old pages and the removed ones are gone, so the evidence no longer
matches, and nothing is written.

tools/merge_reviewer_additions.py applies repair() after merging whenever the evidence
file exists, so regenerating data/records_merged from data/records + the reviewer's
additions reproduces the repaired files byte for byte. --check proves exactly that. It
reads data/reviewed/ (gitignored), so it cannot run in a fresh clone; the cold guard is
evals/check_citation_repair.py, which replays the evidence without it.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "evals" / "owner_decisions" / "citation_repair_2026-09-25.json"
BASELINE = ROOT / "evals" / "known_citation_defects.json"
MERGED = ROOT / "data" / "records_merged"
RECORDS = ROOT / "data" / "records"
SECTIONS = ("typologies", "actors", "indicators")

# The owner's text, VERBATIM. Nothing the implementer decided belongs in this string.
DECISION = ("owner chose (a): re-page quotes found on exactly one other page; remove missing or "
            "ambiguous-page citations; remove facts left uncited")
IMPLEMENTATION_NOTES = [
    "printed_folio: a re-paged citation's printed_folio named the printed page number of the OLD, wrong "
    "page; it is dropped, not recomputed, and the row records the value dropped as printed_folio_dropped.",
    "applied to data/records_merged only (and by tools/merge_reviewer_additions.py on regeneration); "
    "data/records, the extractor's evidence, is untouched and pinned by data_records_sha256.",
    "the defect set is evals/known_citation_defects.json as corrected by the matcher's ARTEFACT tier "
    "(118 -> 103, 2026-09-25); a first attempt on the uncorrected 118 was reset before it was pushed.",
]
REJECTED = ["(b) remove all 118: 87 facts incl. ADV-2026-0001's seven TBML typologies",
            "(c) remove only the 43 missing"]

_spec = importlib.util.spec_from_file_location("fc08_check_citations", ROOT / "evals" / "check_citations.py")
_cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cc)
label_for = _cc._label_for
quote_sha256 = _cc._quote_sha256

# Set only by evals/check_citation_repair.py, in-process, to prove its checks bite.
#   keep-uncited      an item left with no citation stays in the record
#   repage-ambiguous  a quote found on 2+ pages is re-paged to the first, not removed
_MUTATE = None


class RepairError(ValueError):
    pass


def dump(record: dict) -> str:
    """The exact bytes merge_reviewer_additions writes, so --check can compare byte for byte."""
    return json.dumps(record, indent=2) + "\n"


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records_pin() -> dict:
    """sha256 of every data/records/*.json: the extractor evidence the repair was built on."""
    return {p.name: _sha_file(p) for p in sorted(RECORDS.glob("*.json"))}


def load_evidence(path: Path = EVIDENCE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# repair: pure
# ---------------------------------------------------------------------------

def _action(row: dict) -> tuple:
    """(action, to_page) for one evidence row, with the mutation hook."""
    if (_MUTATE == "repage-ambiguous" and row["action"] == "remove" and len(row["found_on"]) >= 2):
        return "re_page", row["found_on"][0]
    return row["action"], row.get("to_page")


def repair(record: dict, evidence: dict) -> dict:
    """The record with this advisory's evidence applied. Raises RepairError, never guesses."""
    out = copy.deepcopy(record)
    aid = out["advisory_id"]
    rows = [r for r in evidence["citations"] if r["advisory_id"] == aid]
    removed = [r for r in evidence["removed_items"] if r["advisory_id"] == aid]

    # Locate every row against the UNREPAIRED record first: a re-page applied before the
    # next row is located could make that row's identity match twice.
    located = []
    for row in rows:
        hits = [(item, i)
                for item in out.get(row["section"], []) if label_for(item) == row["item"]
                for i, c in enumerate(item["citations"])
                if c["page"] == row["page"] and quote_sha256(c["quote"]) == row["quote_sha256"]]
        if len(hits) != 1:
            raise RepairError("%s %s %r p%d %s: found %d times, expected exactly 1 -- the evidence does "
                              "not match this record (already repaired?)"
                              % (aid, row["section"], row["item"][:50], row["page"], row["quote_sha256"][:12],
                                 len(hits)))
        located.append((row, hits[0]))

    drop = set()
    for row, (item, i) in located:
        action, to_page = _action(row)
        c = item["citations"][i]
        if action == "re_page":
            if c.get("printed_folio") != row.get("printed_folio_dropped"):
                raise RepairError("%s %r p%d: record carries printed_folio %r, evidence recorded %r"
                                  % (aid, row["item"][:50], row["page"], c.get("printed_folio"),
                                     row.get("printed_folio_dropped")))
            c["page"] = to_page
            c.pop("printed_folio", None)
        elif action == "remove":
            drop.add((id(item), i))
        else:
            raise RepairError("unknown action %r" % action)

    listed = {(r["section"], r["item"]) for r in removed}
    for section in SECTIONS:
        kept = []
        for item in out.get(section, []):
            item["citations"] = [c for i, c in enumerate(item["citations"]) if (id(item), i) not in drop]
            key = (section, label_for(item))
            if key in listed:
                if item["citations"]:
                    raise RepairError("%s %s %r is listed as removed but still has %d citation(s)"
                                      % (aid, section, key[1][:50], len(item["citations"])))
                if _MUTATE != "keep-uncited":
                    continue
            elif not item["citations"]:
                raise RepairError("%s %s %r would be left uncited without being listed as removed"
                                  % (aid, section, key[1][:50]))
            kept.append(item)
        present = [label_for(i) for i in out.get(section, [])]
        for s, label in listed:
            if s == section and present.count(label) != 1:
                raise RepairError("%s %s %r is listed as removed but is present %d times"
                                  % (aid, section, label[:50], present.count(label)))
        if section in out:
            out[section] = kept
    return out


# ---------------------------------------------------------------------------
# --build-evidence
# ---------------------------------------------------------------------------

def _reason(d: dict) -> str:
    if d["kind"] == "missing":
        return "missing: the quote is on no page of the document"
    if len(d["found_on"]) == 1:
        return "off_page: not on p%d; found on exactly one page, p%d" % (d["page"], d["found_on"][0])
    return "off_page, ambiguous: not on p%d; found on %d pages" % (d["page"], len(d["found_on"]))


def build_evidence() -> dict:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["defects"]
    if not baseline:
        raise SystemExit("REFUSED: %s is empty -- the evidence is built from the PRE-repair baseline"
                         % BASELINE.relative_to(ROOT))
    records = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(MERGED.glob("ADV-*.json"))}

    folio = {}
    for aid, rec in records.items():
        for section in SECTIONS:
            for item in rec.get(section, []):
                for c in item["citations"]:
                    folio[(aid, section, label_for(item), c["page"], quote_sha256(c["quote"]))] = c.get("printed_folio")

    rows = []
    for d in baseline:
        row = {k: d[k] for k in ("advisory_id", "section", "item", "page", "quote_sha256")}
        row["found_on"] = list(d["found_on"])
        if d["kind"] == "off_page" and len(d["found_on"]) == 1:
            row["action"] = "re_page"
            row["to_page"] = d["found_on"][0]
            f = folio.get(_cc._sort_key(d))
            if f is not None:
                row["printed_folio_dropped"] = f
        else:
            row["action"] = "remove"
        row["reason"] = _reason(d)
        rows.append(row)
    rows.sort(key=_cc._sort_key)

    # Which items does removing the "remove" rows leave with no citation at all?
    gone = {_cc._sort_key(r) for r in rows if r["action"] == "remove"}
    removed_items = []
    for aid, rec in records.items():
        for section in SECTIONS:
            for item in rec.get(section, []):
                label = label_for(item)
                if all((aid, section, label, c["page"], quote_sha256(c["quote"])) in gone
                       for c in item["citations"]):
                    removed_items.append({"advisory_id": aid, "section": section, "item": label,
                                          "typology_id": item.get("typology_id"),
                                          "added_by": item.get("added_by")})
    removed_items.sort(key=lambda r: (r["advisory_id"], r["section"], r["item"]))

    return {
        "decided": "2026-09-25",
        "decision": DECISION,
        "implementation_notes": IMPLEMENTATION_NOTES,
        "rejected": REJECTED,
        "data_records_sha256": records_pin(),
        "citations": rows,
        "removed_items": removed_items,
    }


def _counts(ev: dict) -> str:
    acts = [r["action"] for r in ev["citations"]]
    by = {}
    for r in ev["removed_items"]:
        by[r["section"]] = by.get(r["section"], 0) + 1
    return ("%d re_page, %d remove, %d removed items (%s)"
            % (acts.count("re_page"), acts.count("remove"), len(ev["removed_items"]),
               ", ".join("%d %s" % (by[s], s) for s in SECTIONS if s in by)))


# ---------------------------------------------------------------------------
# --apply / --check
# ---------------------------------------------------------------------------

def apply_all() -> int:
    from schemas.advisory import AdvisoryRecord
    evidence = load_evidence()
    out = {}
    for p in sorted(MERGED.glob("ADV-*.json")):
        try:
            fixed = repair(json.loads(p.read_text(encoding="utf-8")), evidence)
            AdvisoryRecord.model_validate(fixed)
        except (RepairError, ValueError) as exc:
            print("REFUSED, nothing written: %s\n  %s" % (p.name, str(exc)[:400]), file=sys.stderr)
            return 2
        out[p] = dump(fixed)
    for p, text in out.items():
        p.write_text(text, encoding="utf-8")
    print("repaired %d records in %s: %s" % (len(out), MERGED.relative_to(ROOT), _counts(evidence)))
    return 0


def check(merged_dir: Path = MERGED) -> int:
    with tempfile.TemporaryDirectory(prefix="fc08_repair_check_") as tmp:
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "merge_reviewer_additions.py"),
                            "--out-dir", tmp], capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            print("FAIL: the merge did not run\n%s" % (r.stdout + r.stderr)[-600:])
            return 1
        fresh = {p.name: p.read_bytes() for p in Path(tmp).glob("ADV-*.json")}
    committed = {p.name: p.read_bytes() for p in merged_dir.glob("ADV-*.json")}
    bad = sorted(n for n in set(fresh) | set(committed) if fresh.get(n) != committed.get(n))
    for n in bad:
        print("differs: %s" % n)
    if not committed:
        print("FAIL: no records examined")
        return 1
    print("%s: %d records, repair(merge(data/records + reviewer additions)) %s data/records_merged"
          % ("MATCHES" if not bad else "FAIL", len(committed), "==" if not bad else "!="))
    return 1 if bad else 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Apply the owner's 2026-09-25 citation-repair decision")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build-evidence", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--check", action="store_true")
    # Hidden: compare against a COPY of the merged records, so --check's red half can be
    # watched without writing the real tree. Not for interactive use.
    ap.add_argument("--merged-dir", type=Path, default=MERGED, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.build_evidence:
        if EVIDENCE.exists():
            print("REFUSED: %s exists -- an owner decision's evidence is never overwritten"
                  % EVIDENCE.relative_to(ROOT), file=sys.stderr)
            return 2
        ev = build_evidence()
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(ev, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote %s: %s" % (EVIDENCE.relative_to(ROOT), _counts(ev)))
        return 0
    if a.apply:
        return apply_all()
    return check(a.merged_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
