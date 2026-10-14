#!/usr/bin/env python3
"""The doctrine drafting agent (Stage565 S3): a draft has the five curated headings in order, every statement is
one line citing evidence the proposal actually holds, and the agent can read the Knowledge Centre and write
nothing else. Usage: .venv/bin/python evals/check_draft_doctrine.py [--mutate LABEL]"""
from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas import doctrine_draft as ddr  # noqa: E402

MUTATIONS = ("cite-any", "multiline")
MUTATION = None

PROPOSAL = {
    "proposal_id": "TP-2026-001", "working_name": "Underground banking via alternative banking platforms",
    "family": "sanctions", "stage": "corroborating", "summary": "Underground banking",
    "evidence": [{"advisory_id": "ADV-2026-0003", "publisher": "FATF",
                  "quotes": ["Underground banking is one tool often used by professional money launderers."],
                  "citations": [{"page": 4,
                                 "quote": "Underground banking is one tool often used by professional money launderers."}]}],
}
LINE = "Professional launderers use underground banking to move value outside the regulated system."


def good(**edit):
    d = {"proposal_id": "TP-2026-001", "title": "Underground banking via alternative banking platforms",
         "sections": [{"heading": h, "statements": [
             {"kind": "paragraph", "text": LINE, "citations": [{"advisory_id": "ADV-2026-0003", "page": 4}]},
             {"kind": "bullet", "text": LINE, "citations": [{"advisory_id": "ADV-2026-0003", "page": 4}]}]}
             for h in ddr.CURATED]}
    d.update(edit)
    return d


def _with_statement(**fields):
    d = good()
    d["sections"][0]["statements"][0].update(fields)
    return d


def checks_pure():
    draft = ddr.DoctrineDraft.model_validate(good())
    yield ddr.problems(draft, PROPOSAL) == [], "a draft citing the evidence it holds passes", ""
    md = ddr.render(draft)
    heads = re.findall(r"^## (.+)$", md, re.M)
    yield heads == list(ddr.CURATED), "the rendered draft has the five curated headings, in order", heads
    body = [l for l in md.splitlines() if l and not l.startswith("#")]
    yield bool(body) and all(ddr.CITED_LINE.search(l) for l in body), \
        "every rendered statement line ends with its citation", body[0] if body else "no lines"
    bad = ddr.DoctrineDraft.model_validate(_with_statement(citations=[{"advisory_id": "ADV-2026-0099", "page": 4}]))
    p = ddr.problems(bad, PROPOSAL)
    yield any("ADV-2026-0099 p.4" in x for x in p), "a citation to an advisory the proposal lacks is refused", p
    bad = ddr.DoctrineDraft.model_validate(_with_statement(citations=[{"advisory_id": "ADV-2026-0003", "page": 9}]))
    p = ddr.problems(bad, PROPOSAL)
    yield any("ADV-2026-0003 p.9" in x for x in p), "a citation to a page the evidence does not hold is refused", p
    for name, text in (("a second line", LINE + "\nmore"), ("bold", "**" + LINE), ("inline code", "`x` " + LINE),
                       ("a pipe", LINE + " | x")):
        p = ddr.problems(ddr.DoctrineDraft.model_validate(_with_statement(text=text)), PROPOSAL)
        yield bool(p), "a statement carrying %s is refused" % name, p
    swapped = good()
    swapped["sections"][0], swapped["sections"][1] = swapped["sections"][1], swapped["sections"][0]
    p = ddr.problems(ddr.DoctrineDraft.model_validate(swapped), PROPOSAL)
    yield any("order" in x for x in p), "sections out of the curated order are refused", p
    p = ddr.problems(ddr.DoctrineDraft.model_validate(good(proposal_id="TP-2026-002")), PROPOSAL)
    yield any("TP-2026-002" in x for x in p), "a draft for another proposal is refused", p
    no_pages = copy.deepcopy(PROPOSAL)
    no_pages["evidence"][0].pop("citations")
    yield ddr.allowed_citations(no_pages) == set(), "an import without pages allows no citation", ""


def checks():
    yield from checks_pure()


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the doctrine drafting agent")
    ap.add_argument("--mutate", choices=MUTATIONS)
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if MUTATION == "cite-any":
        ddr.citation_problems = lambda draft, proposal: []
    elif MUTATION == "multiline":
        ddr.text_problems = lambda text: []
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect" if failures else "NOTHING PROVED"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
