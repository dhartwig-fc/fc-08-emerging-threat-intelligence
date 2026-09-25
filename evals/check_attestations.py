"""
Pin citation ATTESTATION: what an owner's attestation covers, and when it must be refused.

Usage:
    python evals/check_attestations.py
    python evals/check_attestations.py --mutate cover-anything    # an attestation covers advisory+item only; MUST fail
    python evals/check_attestations.py --mutate no-stale          # stale attestations accepted; MUST fail
    python evals/check_attestations.py --mutate no-still-needed   # a citation the matcher places may stay attested; MUST fail
    python evals/check_attestations.py --mutate no-dup            # a duplicated entry accepted; MUST fail

WHY. The owner chose (2026-09-25) to stop widening the shared matcher in
schemas/citation_match -- every tolerance there also loosens propose_link's gate and the
review gate -- and to ATTEST instead the true quotes it cannot place (a quote that runs
over a page break, an ellipsis whose fragment crosses a page, a dropped accent, a list
bullet pypdf extracts as a letter). evals/attested_citations.json holds them;
evals/check_citations.py --all counts an attested citation as verified-by-attestation,
not as a defect, and refuses the list when an entry is stale, no longer needed, or
duplicated. An attestation is an exemption from a governance check, so this guard pins
how NARROW it is: one citation, by its full identity (advisory, section, item, page,
quote sha256), and nothing else.

TIED TO ONE REPAIR, for now. evals/check_citation_repair.py requires every entry of the
list to be accounted for by the 2026-09-25 repair's evidence and the file to match that
evidence's sha256 pin, so a future attestation needs that guard updated as well as this
list.

COLD. The logic is exercised over synthetic pages (PageIndex over strings) and synthetic
records, through the same functions check_citations --all calls. The committed list, if
there is one, is checked cold for its schema and that every identity exists in the
tracked data/records_merged. Whether each attested quote STILL fails the matcher needs
the PDFs, so that half is check_citations --all (needs-pdfs), which refuses a list whose
entry the matcher now places.

NOT A VACUOUS PASS. The covering checks assert the attested citation was examined; each
--mutate switches one refusal off in-process (check_citations._MUTATE) and at least one
check must then fail.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import PageIndex  # noqa: E402

_spec = importlib.util.spec_from_file_location("fc08_check_citations_for_attest", ROOT / "evals" / "check_citations.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

MUTATIONS = ("cover-anything", "no-stale", "no-still-needed", "no-dup")

PAGES = ["The bank failed to file reports without delay. Several transfers were routed offshore.",
         "The regulator opened an inquiry into the trade finance desk."]
AID = "ADV-9999-0001"
ON_PAGE = "The bank failed to file reports without delay"          # the matcher places it (p1)
UNPLACED = "a quote the matcher cannot place on any page at all"    # stands in for a page-break quote
OTHER = "another unplaceable quote with different words entirely"   # same item and page, different hash


def _sha(q: str) -> str:
    return hashlib.sha256(q.encode("utf-8")).hexdigest()


def _record() -> dict:
    return {"advisory_id": AID, "typologies": [], "actors": [], "indicators": [
        {"description": "Reports filed late", "citations": [
            {"page": 1, "quote": ON_PAGE},
            {"page": 1, "quote": UNPLACED},
            {"page": 1, "quote": OTHER},
            {"page": 2, "quote": UNPLACED},
        ]}]}


def _entry(page: int, quote: str, **over) -> dict:
    e = {"advisory_id": AID, "section": "indicators", "item": "Reports filed late", "page": page,
         "quote_sha256": _sha(quote), "reason": "page_break",
         "evidence": "p1 ends '...' and p2 begins '...' (synthetic)", "attested_by": "owner",
         "attested_on": "2026-09-25"}
    e.update(over)
    return e


def _run(attested: list):
    checked = cc.check_record_citations(AID, _record(), PageIndex(PAGES))
    return checked, cc.apply_attestations(checked, attested)


def _load(entries: list):
    with tempfile.TemporaryDirectory(prefix="fc08_attest_") as tmp:
        p = Path(tmp) / "attested.json"
        p.write_text(json.dumps({"note": "synthetic", "attested": entries}), encoding="utf-8")
        return cc.load_attestations(p)


def _key(d: dict) -> tuple:
    return (d["page"], d["quote_sha256"])


def checks() -> list:
    out = []

    def check(label, fn):
        try:
            ok, detail = fn()
        except Exception as exc:  # a missing function or a crash is a failure, stated
            ok, detail = False, "%s: %s" % (type(exc).__name__, str(exc)[:200])
        out.append((ok, label, detail))

    def covers():
        checked, (defects, n, problems) = _run([_entry(1, UNPLACED)])
        keys = {_key(d) for d in defects}
        return (len(checked) == 4 and n == 1 and (1, _sha(UNPLACED)) not in keys and not problems,
                "%d citations examined; %d attested; defects %s; problems %s" % (len(checked), n, sorted(keys), problems))
    check("an attested citation the matcher refuses is verified-by-attestation, not a defect", covers)

    def other_hash():
        _, (defects, n, _) = _run([_entry(1, UNPLACED)])
        keys = {_key(d) for d in defects}
        return ((1, _sha(OTHER)) in keys, "defects %s" % sorted(keys))
    check("a quote with a DIFFERENT hash on the same item and page is not covered", other_hash)

    def other_page():
        _, (defects, n, _) = _run([_entry(1, UNPLACED)])
        keys = {_key(d) for d in defects}
        return ((2, _sha(UNPLACED)) in keys, "defects %s" % sorted(keys))
    check("the same quote cited on a DIFFERENT page is not covered", other_page)

    def stale():
        _, (_, _, problems) = _run([_entry(1, "a quote no record holds")])
        return (any("stale attestation" in p for p in problems), "problems %s" % problems)
    check("an attestation that matches no citation is refused as stale", stale)

    def still_needed():
        _, (_, _, problems) = _run([_entry(1, ON_PAGE)])
        return (any("no longer needed" in p for p in problems), "problems %s" % problems)
    check("an attestation of a citation the matcher places is refused (no longer needed)", still_needed)

    def dup():
        _, problems = _load([_entry(1, UNPLACED), _entry(1, UNPLACED)])
        return (any("appears twice" in p for p in problems), "problems %s" % problems)
    check("an attestation that appears twice is refused", dup)

    def schema():
        bad = [_entry(1, UNPLACED, reason="looked fine to me"),
               _entry(1, OTHER, evidence="x" * 301),
               _entry(2, UNPLACED, attested_by="implementer")]
        _, problems = _load(bad)
        return (len(problems) >= 3, "problems %s" % problems)
    check("an entry with an unknown reason, evidence over 300 characters, or not attested by the owner "
          "is refused", schema)

    def committed_list():
        path = cc.ATTESTED_PATH
        if not path.exists():
            return True, "%s is not committed (0 entries); nothing to check yet" % path.relative_to(ROOT)
        entries, problems = cc.load_attestations(path)
        merged = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                  for p in sorted((ROOT / "data" / "records_merged").glob("ADV-*.json"))}
        have = {(aid, s, cc._label_for(i), c["page"], cc._quote_sha256(c["quote"]))
                for aid, r in merged.items() for s in ("typologies", "actors", "indicators")
                for i in r.get(s, []) for c in i["citations"]}
        absent = [e for e in entries if cc.attestation_identity(e) not in have]
        return (entries and not problems and not absent,
                "%d entries; schema problems %s; absent from data/records_merged: %s"
                % (len(entries), problems, [cc.attestation_identity(e)[:3] for e in absent][:3]))
    check("the committed list (if any) is well formed and every identity is a citation in data/records_merged",
          committed_list)
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin citation attestation")
    ap.add_argument("--mutate", choices=MUTATIONS, help="switch one refusal off; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        cc._MUTATE = args.mutate
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the refusal off"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
