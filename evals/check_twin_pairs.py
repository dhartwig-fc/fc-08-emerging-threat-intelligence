"""
Guard the cross-family twin relation: declared in the tool results, and enforced
by a refusal in propose_link.

Usage:
    python evals/check_twin_pairs.py
    python evals/check_twin_pairs.py --mutate    # empty the map; the refusal MUST stop firing

WHY THIS EXISTS. The system prompt said "Two typologies can share a label; choose
by family". Measured 2026-09-13 over ten runs of ADV-2026-0017:

    SAN002 / PAT008    both labelled "Shadow Fleet"      chosen correctly 10 of 10
    SAN006 / TBML010   "Trade Based Sanctions Evasion"
                       vs "Sanctions Evasion Through
                       Trade" -- same concept reordered   SAN006  0 of 10
                                                          TBML010 8 of 10

The rule fired for the pair that did not need it and was silent on the pair that
did, because its predicate was string equality. One wrong choice scores as a
false negative AND a false positive, so it inflated the measured recall gap
twice. That is fc-10's guardrail-3 defect in a new place: correct English,
wrong test, satisfied by the thing it exists to prevent.

WHAT THE FIX IS. The relation is data (`_TWIN_PAIRS`), surfaced in every
search_typologies line and in get_typology's record, and propose_link REFUSES a
twinned link whose rationale does not name the twin. Declaration alone would
still be advice; the refusal is the governance, and it also forces the reason to
exist -- trace one on ADV-2026-0016 found a typology retrieved, confirmed with
get_typology and then dropped with no record anywhere of why.

WHAT THIS DOES NOT DO. It cannot adjudicate framing. The tool never sees the
document, so it cannot know whether an advisory is "framed as sanctions". It can
only guarantee the agent knew the twin existed and recorded a reason. Deciding
whether that reason is sound is the reviewer's job, in week 5.

NOT A VACUOUS PASS. The empirical basis is checked, not assumed: no golden label
carries both members of a pair, so refusing an unjustified choice cannot
contradict the set. And --mutate empties the map, which must stop the refusal
firing -- a guard never seen to fail is decoration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADVISORY = "ADV-2026-0017"

# Redirect the review queue BEFORE importing the server: propose_link appends to
# it, and a guard must never write into the real queue a human reviews.
_TMP_QUEUE = Path(tempfile.gettempdir()) / "fc08_twin_probe_queue.jsonl"
os.environ["NEXUS_PROPOSALS_PATH"] = str(_TMP_QUEUE)

# Since week 5 propose_link refuses a proposal it cannot trace to a run and a
# document, and verifies every quote. Give it a real identity and a real quote,
# so a refusal seen here is the TWIN rule and not the contract.
_ENTRY = {a["advisory_id"]: a for a in json.loads(
    (ROOT / "evals" / "golden" / "advisory_list.json").read_text(encoding="utf-8"))["advisories"]}[ADVISORY]
PDF = ROOT / "data" / "advisories" / Path(_ENTRY["file"]).name
os.environ.update({"NEXUS_RUN_ID": "probe-twin-pairs", "NEXUS_STAGE": "extractor",
                   "NEXUS_ADVISORY_ID": ADVISORY, "NEXUS_PDF_PATH": str(PDF),
                   "NEXUS_PDF_SHA256": _ENTRY["sha256"]})
_GOLD = json.loads((ROOT / "evals" / "golden" / ("%s.json" % ADVISORY)).read_text(encoding="utf-8"))
CITE = [{"page": c["page"], "quote": c["quote"]} for c in
        next(t for t in _GOLD["typologies"] if t.get("typology_id") == "SAN006")["citations"][:1]]

from mcp_server import knowledge_centre_server as kc  # noqa: E402


def _call(tool, model, **kw):
    """Invoke an MCP tool function with its pydantic input model.

    The model is passed explicitly: the server uses `from __future__ import
    annotations`, so reading it off __annotations__ yields the string "str" and
    fails confusingly.
    """
    fn = getattr(tool, "fn", tool)
    return asyncio.run(fn(model(**kw)))


def checks() -> list:
    out = []
    lib = {t["typology_id"]: t for t in kc._typologies()}

    out.append((bool(kc.TYPOLOGY_TWINS), "the twin map is not empty",
                "%d codes across %d pairs" % (len(kc.TYPOLOGY_TWINS), len(kc._TWIN_PAIRS))))

    unknown = [c for c in kc.TYPOLOGY_TWINS if c not in lib]
    out.append((not unknown, "every twinned code is in the library",
                "unknown: %s" % unknown if unknown else "all present"))

    def fam(i):
        for p in ("TBML", "SAN", "CMI", "PAT", "FND", "BA", "CM"):
            if i.startswith(p):
                return p
        return "?"
    same = [(a, b) for a, b, _, _ in kc._TWIN_PAIRS if fam(a) == fam(b)]
    out.append((not same, "every pair is CROSS-family",
                "same-family pairs: %s" % same if same else "a same-family pair is not a twin, it is a duplicate"))

    sym = all(kc.TYPOLOGY_TWINS.get(v["twin"], {}).get("twin") == k
              for k, v in kc.TYPOLOGY_TWINS.items())
    out.append((sym, "the relation is symmetric",
                "declaring one direction only would leave the other code silent"))

    # The empirical basis for refusing an unjustified choice.
    both = []
    for p in sorted((ROOT / "evals" / "golden").glob("ADV-*.json")):
        ids = {t["typology_id"] for t in json.loads(p.read_text(encoding="utf-8"))["typologies"]
               if t.get("typology_id")}
        for a, b, _, _ in kc._TWIN_PAIRS:
            if a in ids and b in ids:
                both.append((p.stem, a, b))
    out.append((not both, "no golden label carries BOTH members of a pair",
                "found %s" % both if both else "so requiring one justified choice cannot contradict the set"))

    # Declared where the agent is looking.
    res = _call(kc.search_typologies, kc.SearchTypologiesInput, query="sanctions evasion through trade mispricing", limit=10)
    declared = "TWIN of" in res
    out.append((declared, "search_typologies DECLARES the twin in its results",
                next((l for l in res.splitlines() if "TWIN of" in l), res.splitlines()[0])[:96]))

    got = _call(kc.get_typology, kc.GetTypologyInput, typology_id="SAN006")
    has_twin = '"twin"' in got and "TBML010" in got
    out.append((has_twin, "get_typology attaches the twin to the doctrine record",
                "SAN006's record names TBML010 and the convention"))

    # The refusal, both ways round.
    bad = _call(kc.propose_link, kc.ProposeLinkInput, advisory_id=ADVISORY, typology_id="SAN006",
                rationale="The alert describes sanctioned goods moving through third countries.",
                confidence="medium", citations=CITE)
    out.append((bad.startswith("Rejected"), "propose_link REFUSES a twinned link with no twin named",
                bad[:104]))

    good = _call(kc.propose_link, kc.ProposeLinkInput, advisory_id=ADVISORY, typology_id="SAN006",
                 rationale="Chosen over its twin TBML010 because the alert is framed as sanctions "
                           "and export-control evasion, so the sanctions family applies.",
                 confidence="medium", citations=CITE)
    out.append((good.startswith("Accepted"), "propose_link ACCEPTS it once the twin is named",
                good[:104]))

    untwinned = _call(kc.propose_link, kc.ProposeLinkInput, advisory_id=ADVISORY, typology_id="SAN004",
                      rationale="Front companies named on page 3.", confidence="low", citations=CITE)
    out.append((untwinned.startswith("Accepted"), "an UNTWINNED code is unaffected",
                "SAN004 has no twin and must not be caught by the refusal"))

    # A rejected candidate must STAY rejected. BA008 is in 13 of the 20 golden
    # labels -- more than any other typology -- so twinning it by mistake would
    # demand a meaningless CM004 justification on the most common link in the
    # set, and a refusal that cannot be satisfied honestly gets answered by
    # dropping the claim (measured, df8d4aa). This check exists because that
    # mistake WAS made, on label overlap, before anyone read the doctrine.
    for (a, b), why in kc._REJECTED_TWIN_CANDIDATES.items():
        out.append((a not in kc.TYPOLOGY_TWINS and b not in kc.TYPOLOGY_TWINS,
                    "%s/%s stays OUT of the twin map" % (a, b), why))

    ok = _call(kc.propose_link, kc.ProposeLinkInput, advisory_id=ADVISORY, typology_id="BA008",
               rationale="Chain of transfers through intermediaries severing the audit trail, p.4.",
               confidence="medium", citations=CITE)
    out.append((ok.startswith("Accepted"),
                "propose_link ACCEPTS BA008 with no twin named",
                "the most-used typology in the golden set must not carry a spurious requirement"))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Guard the twin relation")
    ap.add_argument("--mutate", action="store_true",
                    help="empty TYPOLOGY_TWINS; the declaration and refusal MUST stop")
    args = ap.parse_args(argv)

    if not PDF.exists():
        print("CANNOT RUN: %s is not on this machine (data/advisories/ is gitignored).\n"
              "Nothing was checked; this is not a pass." % PDF.relative_to(ROOT))
        return 2

    if args.mutate:
        kc.TYPOLOGY_TWINS = {}
        kc._TWIN_PAIRS = ()
        print("MUTATED: twin map emptied. The declaration and refusal checks must fail,\n"
              "         or this probe proves nothing about the fix.\n")

    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1

    if _TMP_QUEUE.exists():
        _TMP_QUEUE.unlink()

    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the relation is removed" if failures
                        else "NOTHING PROVED: it passed with the relation gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED",
                                   failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
