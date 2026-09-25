"""
Pin the shared citation matcher's ARTEFACT tier: what it tolerates and what it must still refuse.

Usage:
    python evals/check_citation_match.py
    python evals/check_citation_match.py --mutate no-artefact     # tier removed; true quotes MUST be refused
    python evals/check_citation_match.py --mutate ignore-digits   # digit rule removed; a wrong number MUST pass
    python evals/check_citation_match.py --mutate no-floor        # 10-letter floor removed; a short quote MUST pass
    python evals/check_citation_match.py --mutate no-letters      # letters rule removed; a paraphrase MUST pass
    python evals/check_citation_match.py --mutate empty           # empty-quote refusal removed; "" MUST pass

WHY. schemas/citation_match.py is the ONE rule for "is this quote on this page", shared
by the MCP server (propose_link refuses), the review gate (re-checks) and
evals/check_citations.py. A 2026-09-25 review found that 18 of the 43 citations
check_citations called "missing" are in the PDF on exactly one page (13 on the CITED
page): pypdf leaves footnote markers glued to words ("reporting19.") or standing
between sentences ("margins. 5 in its trade"), and line-break hyphens ("re- selling").
The same defect was refusing true quotes in all three callers.

The fix loosens a governance check, so this guard pins BOTH sides: the three artefact
shapes pass, and a paraphrase (a different word), a wrong number ($480,000 against a
page reading $48,000), a short letters-only coincidence and an empty quote do not.

COLD. Synthetic pages only (PageIndex over two strings); no PDF, no records.

NOT A VACUOUS PASS. Each --mutate rewrites the matcher's SOURCE text in memory (no
file on disk changes) and loads the result as a separate module; at least one check
must then fail. A mutation whose target text is not found in the source is itself a
failure, so a refactor cannot silently turn a mutation into a no-op.
"""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MATCHER = ROOT / "schemas" / "citation_match.py"

# name -> (exact text in the matcher's source, replacement)
MUTATIONS = {
    "no-artefact": ("    return (len(letters_q) >= ARTEFACT_MIN_LETTERS",
                    "    return False and (len(letters_q) >= ARTEFACT_MIN_LETTERS"),
    "ignore-digits": ("and all(d in tight_page for d in digits_q)", "and True"),
    "no-floor": ("len(letters_q) >= ARTEFACT_MIN_LETTERS", "len(letters_q) >= 1"),
    "no-letters": ("and letters_q in letters_page", "and True"),
    "empty": ("        if not tq:\n            return Located(MISSING)", "        pass"),
}

PAGE_1 = ("The institution continued to trade without reporting19. The bank then processed the "
          "transfers. Firms with low profit margins. 5 in its trade with the region were flagged. "
          "The bank failed to file reports without delay. It recorded an invoice of $48,000 for "
          "goods shipped. Evidence of collus ion was found.")
PAGE_2 = "Several companies were engaged in re- selling goods through third countries."


def load_matcher(mutation):
    if mutation is None:
        from schemas import citation_match
        return citation_match
    src = MATCHER.read_text(encoding="utf-8")
    old, new = MUTATIONS[mutation]
    if src.count(old) != 1:
        raise SystemExit("MUTATION DOES NOT APPLY: %r occurs %d times in %s -- the guard must be "
                         "updated with the matcher" % (old, src.count(old), MATCHER.relative_to(ROOT)))
    name = "citation_match_mutated_%s" % mutation.replace("-", "_")
    mod = types.ModuleType(name)
    mod.__file__ = str(MATCHER)
    sys.modules[name] = mod  # dataclasses resolves the defining module through sys.modules
    exec(compile(src.replace(old, new), "%s[%s]" % (MATCHER, mutation), "exec"), mod.__dict__)
    return mod


def checks(cm) -> list:
    artefact = getattr(cm, "ARTEFACT", "artefact")
    index = cm.PageIndex([PAGE_1, PAGE_2])
    out = []

    def case(label, page, quote, want):
        hit = index.locate(page, quote)
        ok, expect = want(hit)
        out.append((ok, label, "p%d %r -> %s%s; expected %s"
                    % (page, quote, hit.status, " found_on=%s" % (hit.found_on,) if hit.found_on else "",
                       expect)))

    case("glued footnote marker is tolerated", 1, "without reporting. The bank",
         lambda h: (h.ok and h.status == artefact, "ok, artefact"))
    case("standalone footnote marker is tolerated", 1, "low profit margins in its trade with",
         lambda h: (h.ok and h.status == artefact, "ok, artefact"))
    case("line-break hyphen is tolerated", 2, "engaged in reselling goods",
         lambda h: (h.ok and h.status == artefact, "ok, artefact"))
    case("an exact quote is still EXACT", 1, "The bank failed to file reports",
         lambda h: (h.status == cm.EXACT, "exact"))
    case("a pypdf spacing split is still SPACING", 1, "Evidence of collusion was found",
         lambda h: (h.status == cm.SPACING, "spacing"))
    case("a paraphrase (one word changed) is MISSING", 1, "The bank failed to submit reports without delay",
         lambda h: (h.status == cm.MISSING, "missing"))
    case("a wrong number is refused", 1, "an invoice of $480,000 for goods",
         lambda h: (not h.ok and h.status != artefact, "not ok"))
    case("an artefact match on another page is OFF_PAGE", 1, "engaged in reselling goods",
         lambda h: (h.status == cm.OFF_PAGE and h.found_on == (2,), "off_page, found_on=(2,)"))
    case("a quote under 10 letters is never ARTEFACT", 2, "resell",
         lambda h: (h.status != artefact and not h.ok, "not ok, not artefact"))
    case("an empty quote is MISSING", 1, "",
         lambda h: (h.status == cm.MISSING, "missing"))

    # The wrong-number check is only worth something if the LETTERS match: otherwise it
    # passes because the words differ, and the digit rule is never what refuses it.
    lq = "".join(ch for ch in cm.norm("an invoice of $480,000 for goods") if "a" <= ch <= "z")
    lp = "".join(ch for ch in cm.norm(PAGE_1) if "a" <= ch <= "z")
    out.append((lq in lp, "the wrong-number witness differs ONLY in its digits",
                "letters-only %r is on page 1, so only the digit rule can refuse it" % lq))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the citation matcher's ARTEFACT tier")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)

    cm = load_matcher(args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)

    failures = 0
    for ok, label, detail in checks(cm):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1

    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)"
                        % (failures, "" if failures == 1 else "s") if failures
                        else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED",
                                   failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
