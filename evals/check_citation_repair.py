"""
Pin the owner's citation repair of 2026-09-25 against the committed records.

Usage:
    python evals/check_citation_repair.py
    python evals/check_citation_repair.py --mutate keep-uncited       # repair keeps an uncited item; MUST fail
    python evals/check_citation_repair.py --mutate repage-ambiguous   # repair re-pages a 2+-page quote; MUST fail

WHAT IT REPLAYS. The evidence file evals/owner_decisions/citation_repair_2026-09-25.json
against data/records_merged (the repaired, published batch) and data/records (the
extractor's evidence, which the repair must leave alone). Both are tracked, so this runs
COLD: no PDF, and NOT data/reviewed/ (gitignored). The one proof that needs the
reviewer's additions -- that regenerating the merge reproduces records_merged byte for
byte -- is tools/apply_citation_repair.py --check, a separate check_all entry of class
needs-reviewed.

HOW data/records IS PROVED UNCHANGED. The evidence pins the sha256 of every
data/records/*.json as it was when the repair was built; this compares today's files
against that pin. Chosen over `git diff HEAD` (sees only uncommitted edits, so a
committed rewrite would pass) and over `git show <commit>:...` (CI checks out with
depth 1, so the pre-repair commit is not there). A pin in the evidence catches a
committed AND an uncommitted change, in any clone.

WHAT IT PINS (measured 2026-09-25, when the evidence was built from the 91-defect
baseline): 80 re_page -- 75 quotes found on exactly one other page, and 5
"page_break_start" rows moving a page-break quote from the page it ends on to the page it
starts on -- 4 remove, 7 citations attested in place, 2 removed items (ADV-2026-0004's two
indicators). The evidence's "decision" must be the owner's text verbatim. Every entry of
evals/attested_citations.json must be accounted for by the evidence: 7 attested in place
plus the 5 start-page re-pages, each attested at its NEW page.

HOW A REMOVED ITEM IS PROVED PRESENT BEFORE THE REPAIR, cold. An item the extractor
wrote (added_by null; both of the 2) must be in data/records with EVERY one of its
citations a "remove" row of the evidence -- it existed, and the repair is what took it
away. The two reviewer-added typologies are not in data/records by construction; for
those the evidence names them as reviewer items and at least one remove row cites them,
and their presence in the pre-repair merge is proved by apply_citation_repair --check.

THE REPLAY. data/records + no reviewer additions is the cold-available input, and the
repair acts per item, so repair(data/records record) must equal records_merged with
its reviewer-added typologies set aside -- for every section of every advisory. The
evidence rows it cannot use are exactly the rows on reviewer-added items, and the check
asserts that too, so the restriction cannot quietly swallow a row. Both mutations break
repair() itself, and this is the check they must fail.

THE ATTESTED SET IS TIED TO THIS REPAIR. Every entry of evals/attested_citations.json must
be accounted for by this evidence (attested in place, or a start-page re-page), and the
file must match the evidence's sha256 pin byte for byte. So a FUTURE attestation -- or any
edit to an entry's reason or evidence -- fails this guard until the guard is updated for
it (a new dated evidence file, or a deliberate change to these checks).

--merged-dir / --evidence / --attested (hidden; not for interactive use) point the checks
at a temporary COPY of the merged records, the evidence or the attestations, so the RED half of each check
can be watched without writing the real tree -- the same arrangement as
check_citations.py --records-dir. data/records has no such switch: nothing here may
write it, and its check is proved red through a copy of the evidence's pin instead.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("fc08_apply_citation_repair",
                                              ROOT / "tools" / "apply_citation_repair.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

MERGED = tool.MERGED
EVIDENCE = tool.EVIDENCE
ATTESTED = tool.ATTESTED
# The owner's decision string, restated here on purpose: a change to the tool's constant must
# show as a failure, not travel silently into a rebuilt evidence file.
VERBATIM = ("owner chose (a): re-page quotes found on exactly one other page; remove missing or "
            "ambiguous-page citations; remove facts left uncited")
RECORDS = tool.RECORDS
SECTIONS = tool.SECTIONS
RECORD_NAME = re.compile(r"^ADV-\d{4}-\d{4}\.json$")

EXPECT = {"re_page": 80, "page_break_start": 5, "remove": 4, "attested_in_place": 7, "removed_items": 2,
          "by_section": {"typologies": 0, "actors": 0, "indicators": 2}}
PBS = tool.PAGE_BREAK_START


def _load_dir(d: Path) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(d.glob("ADV-*.json")) if RECORD_NAME.match(p.name)}


def _cites(record: dict) -> set:
    """(section, item, page, quote_sha256) for every citation of a record."""
    return {(s, tool.label_for(i), c["page"], tool.quote_sha256(c["quote"]))
            for s in SECTIONS for i in record.get(s, []) for c in i["citations"]}


def checks() -> list:
    out = []
    ev = tool.load_evidence(EVIDENCE)
    rows, removed = ev["citations"], ev["removed_items"]
    merged, records = _load_dir(MERGED), _load_dir(RECORDS)

    # 1. The counts the owner decided on.
    acts = [r["action"] for r in rows]
    by = {s: sum(1 for r in removed if r["section"] == s) for s in SECTIONS}
    in_place = ev.get("attested_in_place", [])
    got = {"re_page": acts.count("re_page"), "page_break_start": sum(1 for r in rows if r["reason"] == PBS),
           "remove": acts.count("remove"), "attested_in_place": len(in_place),
           "removed_items": len(removed), "by_section": by}
    out.append((got == EXPECT, "the evidence holds 80 re_page (5 page_break_start), 4 remove, 7 attested in "
                "place, 2 removed items (2 indicators, no typology or actor)", json.dumps(got)))
    out.append((ev.get("decision") == tool.DECISION == VERBATIM,
                "the evidence's decision is the owner's text verbatim", repr(ev.get("decision"))[:120]))

    # 2. Each row's action follows from where the quote was found -- the rule, not just the count.
    attested = {tool._cc.attestation_identity(e) for e in tool._cc.load_attestations(ATTESTED)[0]}
    def ident(r, page):
        return (r["advisory_id"], r["section"], r["item"], page, r["quote_sha256"])
    wrong = [r for r in rows
             if not ((r["action"] == "re_page" and r["reason"] != PBS and len(r["found_on"]) == 1
                      and r["to_page"] == r["found_on"][0] and r["to_page"] != r["page"])
                     or (r["action"] == "re_page" and r["reason"] == PBS and r["found_on"] == []
                         and r["to_page"] == r["page"] - 1 and ident(r, r["to_page"]) in attested)
                     or (r["action"] == "remove" and len(r["found_on"]) != 1 and "to_page" not in r))]
    out.append((rows and not wrong, "re_page iff the quote was found on exactly one other page, to that page, "
                "or it is a page_break_start row moved to the page before and attested there; remove otherwise",
                "%d rows, %d break the rule%s" % (len(rows), len(wrong),
                ": %s p%d" % (wrong[0]["advisory_id"], wrong[0]["page"]) if wrong else "")))

    # 2b. Every attestation is accounted for by the evidence, and nothing else is exempt.
    accounted = {ident(r, r["page"]) for r in in_place} | {ident(r, r["to_page"]) for r in rows if r["reason"] == PBS}
    out.append((attested and accounted == attested,
                "every entry of evals/attested_citations.json is attested in place or a start-page re-page, "
                "and nothing else is", "%d attested, %d accounted for, differ: %s"
                % (len(attested), len(accounted), sorted(attested ^ accounted)[:2])))

    # 2c. The attestation file is byte-for-byte the one the repair was built on: a changed reason,
    # evidence excerpt or note is a change to what the owner attested, and must be re-decided.
    now_sha = tool._sha_file(ATTESTED) if ATTESTED.exists() else None
    out.append((now_sha is not None and now_sha == ev.get("attested_citations_sha256"),
                "evals/attested_citations.json is byte-identical to the evidence's sha256 pin",
                "pinned %s, now %s" % (str(ev.get("attested_citations_sha256"))[:16], str(now_sha)[:16])))

    # 3. data/records is exactly what the repair was built on.
    now = tool.records_pin()
    moved = sorted(n for n in set(now) | set(ev["data_records_sha256"]) if now.get(n) != ev["data_records_sha256"].get(n))
    out.append((now and not moved, "data/records is byte-identical to the evidence's pin (the repair never "
                "touched the extractor's evidence)", "%d files pinned; moved: %s" % (len(now), moved or "none")))

    # 4. Every removed item is gone from the published batch.
    still = [r for r in removed
             if any(tool.label_for(i) == r["item"] for i in merged.get(r["advisory_id"], {}).get(r["section"], []))]
    out.append((removed and not still, "every removed item is absent from data/records_merged",
                "%d removed, %d still present%s" % (len(removed), len(still),
                                                   ": %s %r" % (still[0]["advisory_id"], still[0]["item"]) if still else "")))

    # 5. ...and was there before the repair: the repair removed it, it was not missing already.
    remove_keys = {(r["advisory_id"], r["section"], r["item"], r["page"], r["quote_sha256"])
                   for r in rows if r["action"] == "remove"}
    bad, n_extractor, n_reviewer = [], 0, 0
    for r in removed:
        aid = r["advisory_id"]
        src = [i for i in records.get(aid, {}).get(r["section"], []) if tool.label_for(i) == r["item"]]
        if r["added_by"] is None:
            n_extractor += 1
            if len(src) != 1 or not all((aid, r["section"], r["item"], c["page"], tool.quote_sha256(c["quote"]))
                                        in remove_keys for c in src[0]["citations"]):
                bad.append(r)
        else:
            n_reviewer += 1
            cited = any(k[0] == aid and k[1] == r["section"] and k[2] == r["item"] for k in remove_keys)
            if src or r["added_by"] != "reviewer" or r["section"] != "typologies" or not cited:
                bad.append(r)
    out.append((removed and not bad,
                "every removed item existed before the repair: an extractor item is in data/records with every "
                "citation a remove row; a reviewer item is named by a remove row (its merge is proved by "
                "apply_citation_repair --check)",
                "%d extractor, %d reviewer, %d unproved%s" % (n_extractor, n_reviewer, len(bad),
                                                            ": %s %r" % (bad[0]["advisory_id"], bad[0]["item"]) if bad else "")))

    # 6. Every re-paged citation sits at its new page, once, without the folio of the old one.
    bad = []
    for r in (r for r in rows if r["action"] == "re_page"):
        items = [i for i in merged.get(r["advisory_id"], {}).get(r["section"], []) if tool.label_for(i) == r["item"]]
        at_new = [c for i in items for c in i["citations"]
                  if c["page"] == r["to_page"] and tool.quote_sha256(c["quote"]) == r["quote_sha256"]]
        at_old = [c for i in items for c in i["citations"]
                  if c["page"] == r["page"] and tool.quote_sha256(c["quote"]) == r["quote_sha256"]]
        if len(at_new) != 1 or at_old or "printed_folio" in at_new[0]:
            bad.append(r)
    n = acts.count("re_page")
    out.append((n and not bad, "every re-paged citation is in data/records_merged exactly once at its to_page, "
                "not at its old page, and carries no printed_folio",
                "%d re-paged, %d wrong%s" % (n, len(bad), ": %s %r p%d" % (bad[0]["advisory_id"], bad[0]["item"][:40],
                                                                            bad[0]["page"]) if bad else "")))

    # 7. Every removed citation is gone, and nothing published is uncited.
    live = {(aid,) + k for aid, rec in merged.items() for k in _cites(rec)}
    back = sorted(k for k in remove_keys if k in live)
    uncited = [(aid, s, tool.label_for(i)) for aid, rec in merged.items() for s in SECTIONS
               for i in rec.get(s, []) if not i["citations"]]
    n_items = sum(len(rec.get(s, [])) for rec in merged.values() for s in SECTIONS)
    out.append((n_items and not back and not uncited,
                "no removed citation remains in data/records_merged, and none of its items is uncited",
                "%d items examined; %d removed citations remain; %d uncited" % (n_items, len(back), len(uncited))))

    # 8. The replay: repair(data/records) == records_merged minus its reviewer-added typologies.
    diffs, skipped_bad, used, skipped = [], [], 0, 0
    for aid, rec in sorted(records.items()):
        have = {(s, tool.label_for(i)) for s in SECTIONS for i in rec.get(s, [])}
        mine = [r for r in rows if r["advisory_id"] == aid and (r["section"], r["item"]) in have]
        for r in rows:
            if r["advisory_id"] == aid and (r["section"], r["item"]) not in have:
                skipped += 1
                reviewer_now = any(tool.label_for(i) == r["item"] and i.get("added_by") == "reviewer"
                                   for i in merged.get(aid, {}).get(r["section"], []))
                reviewer_gone = any(x["advisory_id"] == aid and x["section"] == r["section"]
                                    and x["item"] == r["item"] and x["added_by"] == "reviewer" for x in removed)
                if not (reviewer_now or reviewer_gone):
                    skipped_bad.append(r)
        used += len(mine)
        sub = {"citations": mine,
               "removed_items": [x for x in removed if x["advisory_id"] == aid and x["added_by"] is None]}
        try:
            replay = tool.repair(rec, sub)
        except tool.RepairError as exc:
            diffs.append("%s: repair refused: %s" % (aid, str(exc)[:120]))
            continue
        pub = merged.get(aid)
        if pub is None:
            diffs.append("%s: not in data/records_merged" % aid)
            continue
        for s in SECTIONS:
            expect = [i for i in pub.get(s, []) if i.get("added_by") != "reviewer"]
            if replay.get(s, []) != expect:
                diffs.append("%s %s: the replay differs from the published record" % (aid, s))
    out.append((used and not diffs and not skipped_bad and len(records) == len(merged),
                "replaying the evidence over data/records reproduces every section of data/records_merged "
                "(reviewer-added typologies aside), and every row it cannot replay is on a reviewer-added item",
                "%d records, %d rows replayed, %d on reviewer items; %s" % (
                    len(records), used, skipped,
                    "; ".join(diffs[:2] + ["unexplained skip: %s %r" % (r["advisory_id"], r["item"])
                                           for r in skipped_bad[:1]]) or "identical")))
    return out


def main(argv: list) -> int:
    global MERGED, EVIDENCE, ATTESTED
    ap = argparse.ArgumentParser(description="Pin the owner's 2026-09-25 citation repair")
    ap.add_argument("--mutate", choices=("keep-uncited", "repage-ambiguous"),
                    help="break repair(); checks MUST fail")
    ap.add_argument("--merged-dir", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--evidence", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--attested", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    MERGED = args.merged_dir or MERGED
    EVIDENCE = args.evidence or EVIDENCE
    ATTESTED = args.attested or ATTESTED
    if args.mutate:
        tool._MUTATE = args.mutate
        print("MUTATED: %s\n" % {
            "keep-uncited": "repair() leaves an item with no citation in place.",
            "repage-ambiguous": "repair() re-pages a quote found on 2+ pages to the first of them."}[args.mutate])
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
