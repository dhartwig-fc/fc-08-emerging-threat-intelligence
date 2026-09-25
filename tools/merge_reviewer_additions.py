"""
Merge the additive reviewer's additions into records, under schema 1.4.0.

Usage:
    python tools/merge_reviewer_additions.py                 # all 20, to data/records_merged/
    python tools/merge_reviewer_additions.py --advisory ADV-2026-0016
    python tools/merge_reviewer_additions.py --in-place      # overwrite data/records/

NON-DESTRUCTIVE BY DEFAULT, and that is not timidity. The extraction-only record
is the evidence for every baseline figure this project has published: F1 0.510,
recall 0.357, the per-document table, the bands the reviewer was accepted
against. Overwriting it in place would leave those numbers unreproducible from
the tree that claims them. `--in-place` exists for when the merged record IS the
pipeline's output; until that decision is taken, both live side by side.

WHAT THE MERGE PRESERVES, because the schema now refuses to let it be dropped.
Each addition arrives as `added_by="reviewer"` carrying its `review_justification`
-- the doctrine quote and the mechanism argument that earned it. Schema 1.4.0
refuses a reviewer entry without one, so a merge that lost the reasoning cannot
validate. That is the guard doing the work rather than this script remembering.

`where_found` HAS NO FIELD IN THE CONTRACT and is prepended to the justification
rather than discarded. "Red flag 7, page 4" is how a curator finds the claim in
the document; losing it to a schema gap would be exactly the kind of quiet
provenance loss the separate-files arrangement existed to avoid.

DEDUPLICATION. The reviewer already refuses to re-propose a governed id the
record holds -- enforced in `review_advisory.py`, not asked for in its prompt.
Emergent additions carry no id, so they are deduplicated here on the normalised
label, using the scorer's own tokeniser rather than a second definition of
"the same string".

THE OWNER'S CITATION REPAIR (2026-09-25). When
evals/owner_decisions/citation_repair_2026-09-25.json exists, each merged record is
passed through tools/apply_citation_repair.repair() before it is validated and
written, so regenerating data/records_merged reproduces the repaired, committed files
byte for byte (tools/apply_citation_repair.py --check proves it). The repair is for
the MERGED output only: --in-place writes data/records, the extractor's evidence,
which the decision leaves untouched with its defects, so --in-place is REFUSED while
the evidence file exists.

A REFUSED REPAIR REFUSES THE WHOLE RUN. repair() names each citation by advisory,
item, page and quote hash, and refuses rather than guesses when a row no longer
matches. So re-extracting an advisory that has evidence rows, or changing its
reviewer additions, makes the merge refuse until the evidence is rebuilt -- and it
then writes NOTHING, not the other nineteen records: a batch half repaired and half
not is a state no evidence file describes. (A record that merely fails schema
validation is skipped and reported, as before.)

"Rebuilt" is a procedure, not a flag: (1) write a NEW dated evidence file under evals/owner_decisions/ from the then-current
baseline (--build-evidence refuses to overwrite an existing one, because an owner
decision's evidence is never rewritten); (2) change the code that names the evidence file
-- REPAIR_EVIDENCE in tools/merge_reviewer_additions.py and EVIDENCE in
tools/apply_citation_repair.py -- in the same commit; (3) update
evals/check_citation_repair.py, whose pins describe this repair. There is no in-place
rebuild of citation_repair_2026-09-25.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.advisory import SCHEMA_VERSION, AdvisoryRecord  # noqa: E402

_spec = importlib.util.spec_from_file_location("fc08_score", ROOT / "evals" / "score.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

# Where each advisory's additions live: the four band documents were run three
# times, and repeat 1 is the one every published figure was scored on.
ADDITION_DIRS = ("rep1", "rest")


def additions_for(advisory_id: str) -> tuple:
    for sub in ADDITION_DIRS:
        p = ROOT / "data" / "reviewed" / sub / ("%s.additions.json" % advisory_id)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("additions", []), sub
    return [], None


def merge(record: dict, additions: list) -> tuple:
    """Return (merged record dict, kept, skipped_duplicate)."""
    out = json.loads(json.dumps(record))
    out["schema_version"] = SCHEMA_VERSION

    have_ids = {t.get("typology_id") for t in out["typologies"] if t.get("typology_id")}
    have_labels = {frozenset(sc.tokens(t["label"])) for t in out["typologies"]}

    kept, dup = 0, 0
    for a in additions:
        tid = a.get("typology_id")
        if tid and tid in have_ids:
            dup += 1
            continue
        if not tid and frozenset(sc.tokens(a["label"])) in have_labels:
            dup += 1
            continue

        why = a.get("doctrine_justification") or ""
        where = a.get("where_found")
        if where:
            # No field for it in the contract; it is provenance a curator needs.
            why = "Found in %s. %s" % (where, why)

        entry = {
            "family": a["family"],
            "typology_id": tid,
            "label": a["label"],
            "emergent": bool(a.get("emergent", not tid)),
            "confidence": a["confidence"],
            "citations": a["citations"],
            "added_by": "reviewer",
            "review_justification": why,
        }
        out["typologies"].append(entry)
        if tid:
            have_ids.add(tid)
        have_labels.add(frozenset(sc.tokens(a["label"])))
        kept += 1

    if kept:
        note = ("Merged %d reviewer addition(s) under schema %s; each carries its "
                "review_justification. Extraction-only record retained at data/records/."
                % (kept, SCHEMA_VERSION))
        existing = out.get("extraction_notes") or ""
        joined = (existing + " " + note).strip() if existing else note
        # The cap is 4000 and reviewer notes on long reports already sit near it.
        # Losing a typology to a notes overflow would be absurd, so the note is
        # dropped rather than the merge, and the drop is visible in the output.
        out["extraction_notes"] = joined if len(joined) <= 4000 else existing
    return out, kept, dup


ARCHIVE = ROOT / "data" / "records_extraction_only"
REPAIR_EVIDENCE = ROOT / "evals" / "owner_decisions" / "citation_repair_2026-09-25.json"


def _repair_tool():
    """tools/apply_citation_repair.py, loaded by path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("fc08_apply_citation_repair",
                                                  ROOT / "tools" / "apply_citation_repair.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def archive_extraction_records() -> bool:
    """Copy the extraction-only records aside before --in-place overwrites them.

    PRESERVE FIRST, THEN ACT. Three facts make this non-negotiable rather than
    cautious, all measured 2026-09-13:

      1. data/records/ is NOT tracked in git. It exists on one machine.
      2. Extraction is NOT deterministic. Three identical re-runs of
         ADV-2026-0016 produced THREE different typology sets, so re-running
         does not recover a record -- it produces a different one.
      3. Every published figure depends on exactly these records: typologies
         F1 0.510, recall 0.357, the per-document table, the reviewer's
         acceptance bands, evals/score_report.json, the journal, the slice-1
         page.

    So a plain overwrite destroys the only copy of the evidence behind every
    number this project has published. fc-10 met the same shape of decision in
    its priority 1, where deleting an 'orphaned' product page would have
    destroyed the last surviving record of a run; the resolution there was to
    preserve first and then act, and it is the resolution here.

    Refuses rather than overwriting an existing archive: a second --in-place run
    would otherwise archive the ALREADY-MERGED records over the originals, which
    is the destruction this function exists to prevent, one step removed.
    """
    src = ROOT / "data" / "records"
    if ARCHIVE.exists() and any(ARCHIVE.glob("ADV-2026-*.json")):
        print("REFUSED: %s already holds archived records.\n"
              "  A second --in-place would archive the MERGED records over the extraction-only\n"
              "  originals, which is the loss this archive exists to prevent. Move or delete the\n"
              "  existing archive deliberately if you mean to re-archive." % ARCHIVE, file=sys.stderr)
        return False
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob("ADV-2026-*.json")):
        (ARCHIVE / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        n += 1
    print("archived %d extraction-only records to %s" % (n, ARCHIVE))
    return True


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Merge reviewer additions into records")
    ap.add_argument("--advisory", default=None, help="One advisory id; default is all")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "records_merged")
    ap.add_argument("--in-place", action="store_true",
                    help="Make the merged set the pipeline output at data/records/. The "
                         "extraction-only records are ARCHIVED first, to data/records_extraction_only/; "
                         "it refuses rather than overwrite an archive that already exists.")
    args = ap.parse_args(argv)

    src = sorted((ROOT / "data" / "records").glob("ADV-2026-*.json"))
    src = [p for p in src if "schema-" not in p.name and "week1" not in p.name]
    if args.advisory:
        src = [p for p in src if p.stem == args.advisory]
        if not src:
            print("No record for %s" % args.advisory, file=sys.stderr)
            return 2

    repair_evidence = None
    if REPAIR_EVIDENCE.exists():
        if args.in_place:
            print("REFUSED: --in-place would write the owner's citation repair (%s) into data/records,\n"
                  "  the extractor's evidence, which that decision leaves untouched. The repair is for\n"
                  "  the merged output only." % REPAIR_EVIDENCE.relative_to(ROOT), file=sys.stderr)
            return 2
        repair_evidence = json.loads(REPAIR_EVIDENCE.read_text(encoding="utf-8"))
        repair_tool = _repair_tool()

    out_dir = (ROOT / "data" / "records") if args.in_place else args.out_dir
    if args.in_place and not archive_extraction_records():
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    total_kept = total_dup = failed = 0
    no_additions, refused, pending = [], [], []
    for p in src:
        record = json.loads(p.read_text(encoding="utf-8"))
        aid = record["advisory_id"]
        adds, sub = additions_for(aid)
        if not adds:
            no_additions.append(aid)
        merged, kept, dup = merge(record, adds)
        if repair_evidence is not None:
            try:
                merged = repair_tool.repair(merged, repair_evidence)
            except repair_tool.RepairError as exc:
                refused.append((aid, str(exc)))
                continue
        try:
            AdvisoryRecord.model_validate(merged)
        except Exception as exc:
            print("  %s FAILED validation after merge: %s" % (aid, str(exc)[:300]), file=sys.stderr)
            failed += 1
            continue
        pending.append((aid, merged, kept, dup, sub))

    if refused:
        # Nothing is written: a batch half repaired and half not matches no evidence file.
        print("REFUSED, nothing written: the owner's citation repair (%s) does not match %d merged "
              "record(s) -- rebuild the evidence before regenerating:"
              % (str(REPAIR_EVIDENCE).replace(str(ROOT) + "/", ""), len(refused)), file=sys.stderr)
        for aid, msg in refused:
            print("  %s: %s" % (aid, msg[:300]), file=sys.stderr)
        return 2

    for aid, merged, kept, dup, sub in pending:
        (out_dir / ("%s.json" % aid)).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        total_kept += kept
        total_dup += dup
        print("  %s  +%d reviewer (%s)%s" % (aid, kept, sub or "no additions file",
                                             "  [%d duplicate skipped]" % dup if dup else ""))

    print("\nmerged into %s" % out_dir)
    print("  %d additions kept, %d duplicates skipped, %d records failed validation"
          % (total_kept, total_dup, failed))
    if no_additions:
        print("  no additions file for: %s" % ", ".join(no_additions))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
