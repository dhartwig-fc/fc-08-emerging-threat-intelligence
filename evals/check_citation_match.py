"""
Pin the shared citation matcher's ARTEFACT tier: what it tolerates and what it must still refuse.

Usage:
    python evals/check_citation_match.py
    python evals/check_citation_match.py --mutate no-artefact     # tier removed; true quotes MUST be refused
    python evals/check_citation_match.py --mutate ignore-digits   # digit rule removed; a wrong number MUST pass
    python evals/check_citation_match.py --mutate no-floor        # 10-letter floor removed; a short quote MUST pass
    python evals/check_citation_match.py --mutate no-letters      # letters rule removed; a paraphrase MUST pass
    python evals/check_citation_match.py --mutate empty           # empty-quote refusal removed; "" MUST pass
    python evals/check_citation_match.py --mutate substring-digits  # digit runs matched as substrings; a truncated number MUST pass
    python evals/check_citation_match.py --mutate ascii-letters   # letters form a-z only; a changed accented name MUST pass
    python evals/check_citation_match.py --mutate keeps-digits    # letters form keeps digits; a glued footnote MUST be refused
    python evals/check_citation_match.py --mutate no-nfc          # accents not composed; a decomposed "Müller" MUST match "Muller"
    python evals/check_citation_match.py --mutate ellipsis-unordered  # fragments matched anywhere; an out-of-order quote MUST pass
    python evals/check_citation_match.py --mutate ellipsis-short  # 10-letter fragment floor removed; "... goods" MUST pass

WHY. schemas/citation_match.py is the ONE rule for "is this quote on this page", shared
by the MCP server (propose_link refuses), the review gate (re-checks) and
evals/check_citations.py. A 2026-09-25 review found that 18 of the 43 citations
check_citations called "missing" are in the PDF on exactly one page (13 on the CITED
page): pypdf leaves footnote markers glued to words ("reporting19.") or standing
between sentences ("margins. 5 in its trade"), and line-break hyphens ("re- selling").
The same defect was refusing true quotes in all three callers.

The fix loosens a governance check, so this guard pins BOTH sides: the three artefact
shapes pass (also around an accented word), and a paraphrase (a different word), a wrong
number ($480,000 against a page reading $48,000), a TRUNCATED number ($48,000 against
$480,000; 30 against 300), a changed non-ASCII letter (Möller against Müller), a short
letters-only coincidence and an empty quote do not -- and a page whose accent is
DECOMPOSED ("u" + U+0308) does not match a plain "Muller", because the letters form is
NFC-composed first (added 2026-09-25; without it the combining mark was deleted).

The ELLIPSIS tier (2026-09-25, owner's decision after 12 of the 25 remaining "missing"
citations proved to be ellipsis quotations whose every fragment is on the cited page) is
pinned the same way: an ellipsis quote passes only with every fragment >= 10 letters and
on the page IN ORDER (out of order, a short fragment, or a fragment not on the page is
refused). A page-spanning tier was added and removed the same day -- it matched none of
the real page-spanning quotes -- so its checks are gone with it.

Fix round 1 (2026-09-25) closed two holes in the rule as first written: digit runs were
matched as SUBSTRINGS, so a truncated number passed ("48" is inside "480"); and the
letters form was [^a-z], which deleted every non-ASCII letter, so a changed accented or
non-Latin name passed. Each "witness" check below proves its refusal case differs ONLY
in the thing under test, so the refusal is the rule's and not a coincidence of wording.

COLD. Synthetic pages only (PageIndex over two strings); no PDF, no records.

NOT A VACUOUS PASS. Each --mutate rewrites the matcher's SOURCE text in memory (no
file on disk changes) and loads the result as a separate module; at least one check
must then fail. A mutation whose target text is not found in the source is itself a
failure, so a refactor cannot silently turn a mutation into a no-op.
"""

from __future__ import annotations

import argparse
import re
import sys
import types
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MATCHER = ROOT / "schemas" / "citation_match.py"

# name -> (exact text in the matcher's source, replacement)
MUTATIONS = {
    "no-artefact": ("    return (len(letters_q) >= ARTEFACT_MIN_LETTERS",
                    "    return False and (len(letters_q) >= ARTEFACT_MIN_LETTERS"),
    "ignore-digits": ("and all(re.search(r\"(?<!\\d)%s(?!\\d)\" % re.escape(d), tight_page) for d in digits_q)",
                      "and True"),
    "substring-digits": ("all(re.search(r\"(?<!\\d)%s(?!\\d)\" % re.escape(d), tight_page) for d in digits_q)",
                         "all(d in tight_page for d in digits_q)"),
    "ascii-letters": ('return re.sub(r"[\\W\\d_]", "", unicodedata', 'return re.sub(r"[^a-z]", "", unicodedata'),
    "keeps-digits": ('return re.sub(r"[\\W\\d_]", "", unicodedata', 'return re.sub(r"[\\W_]", "", unicodedata'),
    "no-nfc": ('unicodedata.normalize("NFC", normed))', 'normed)'),
    "ellipsis-unordered": ("at = letters_page.find(lf, pos)", "at = letters_page.find(lf)"),
    "ellipsis-short": ("        if len(lf) < ARTEFACT_MIN_LETTERS:\n            return False", "        pass"),
    "no-floor": ("len(letters_q) >= ARTEFACT_MIN_LETTERS", "len(letters_q) >= 1"),
    "no-letters": ("and letters_q in letters_page", "and True"),
    "empty": ("        if not tq:\n            return Located(MISSING)", "        pass"),
}

PAGE_1 = ("The institution continued to trade without reporting19. The bank then processed the "
          "transfers. Firms with low profit margins. 5 in its trade with the region were flagged. "
          "The bank failed to file reports without delay. It recorded an invoice of $48,000 for "
          "goods shipped. Evidence of collus ion was found.")
PAGE_2 = ("Several companies were engaged in re- selling goods through third countries. A payment "
          "of $480,000 was wired offshore. Some 300 shipments were declared at the border. The "
          "director Hans Müller signed the contracts. The Société Générale19. branch opened accounts.")
# A page whose accent is DECOMPOSED: "u" followed by U+0308 COMBINING DIAERESIS, as some PDF
# extractors emit it. The combining mark is not a letter to the [\W\d_] rule, so without NFC
# composition it is deleted and the page's letters read "hansmuller" -- a different name.
PAGE_3 = "The partner Hans Mu\u0308ller approved the loans."


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
    index = cm.PageIndex([PAGE_1, PAGE_2, PAGE_3])
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
    case("a truncated number is refused ($48,000 quoted, page reads $480,000)", 2,
         "A payment of $48,000 was wired offshore",
         lambda h: (not h.ok and h.status != artefact, "not ok"))
    case("a truncated count is refused (30 quoted, page reads 300)", 2,
         "Some 30 shipments were declared at the border",
         lambda h: (not h.ok and h.status != artefact, "not ok"))
    case("a changed accented letter is refused (Möller quoted, page reads Müller)", 2,
         "The director Hans Möller signed the contracts",
         lambda h: (not h.ok and h.status != artefact, "not ok"))
    case("a glued footnote beside accented words is still tolerated", 2,
         "The Société Générale branch opened accounts",
         lambda h: (h.ok and h.status == artefact, "ok, artefact"))
    case("a plain name is refused against a DECOMPOSED accent (Muller quoted, page reads Mu+U+0308ller)",
         3, "Hans Muller",
         lambda h: (not h.ok and h.status != artefact, "not ok"))
    case("a composed quote of a DECOMPOSED accent is tolerated (Müller quoted, page reads Mu+U+0308ller)",
         3, "Hans M\u00fcller approved the loans",
         lambda h: (h.ok and h.status == artefact, "ok, artefact"))

    # WITNESSES. A refusal is only the rule's if the quote matches the page in every other
    # respect. These use their own letter forms, not the matcher's, so a matcher bug
    # cannot make its own witness agree with it.
    uni = lambda t: re.sub(r"[\W\d_]", "", cm.norm(t))
    asc = lambda t: re.sub(r"[^a-z]", "", cm.norm(t))
    for label, page_text, quote in (
            ("wrong number ($480,000 vs $48,000)", PAGE_1, "an invoice of $480,000 for goods"),
            ("truncated number ($48,000 vs $480,000)", PAGE_2, "A payment of $48,000 was wired offshore"),
            ("truncated count (30 vs 300)", PAGE_2, "Some 30 shipments were declared at the border")):
        lq = uni(quote)
        out.append((lq in uni(page_text), "the %s witness differs ONLY in its digits" % label,
                    "letters-only %r is on the page, so only the digit rule can refuse it" % lq))
    q = "The director Hans Möller signed the contracts"
    out.append((asc(q) in asc(PAGE_2) and uni(q) not in uni(PAGE_2),
                "the Möller witness differs ONLY in a non-ASCII letter",
                "a-z form %r IS on the page and the Unicode form is not, so only the letters form "
                "decides it" % asc(q)))
    raw = lambda t: re.sub(r"[\W\d_]", "", cm.norm(t))  # no composition: the pre-2026-09-25 form
    nfc = lambda t: re.sub(r"[\W\d_]", "", unicodedata.normalize("NFC", cm.norm(t)))
    q = "Hans Muller"
    out.append((raw(q) in raw(PAGE_3) and nfc(q) not in nfc(PAGE_3),
                "the decomposed-accent witness differs ONLY in the composition of one letter",
                "uncomposed form %r IS on the page and the composed form is not, so only NFC "
                "decides it" % raw(q)))

    # ELLIPSIS: every fragment on the cited page, in order, each >= 10 letters.
    ellipsis = getattr(cm, "ELLIPSIS", "ellipsis")
    case("an ellipsis quote whose fragments are on the page in order is ELLIPSIS", 1,
         "The institution continued to trade ... The bank failed to file reports without delay",
         lambda h: (h.ok and h.status == ellipsis, "ok, ellipsis"))
    case("a Unicode ellipsis (U+2026) is split the same way", 1,
         "The bank then processed the transfers\u2026 an invoice of $48,000 for goods shipped",
         lambda h: (h.ok and h.status == ellipsis, "ok, ellipsis"))
    case("ellipsis fragments OUT OF ORDER are refused", 1,
         "The bank failed to file reports without delay ... The institution continued to trade",
         lambda h: (not h.ok, "not ok"))
    case("an ellipsis fragment under 10 letters is refused", 1,
         "The bank failed to file reports ... goods",
         lambda h: (not h.ok, "not ok"))
    case("an ellipsis fragment not on the page is refused", 1,
         "The institution continued to trade ... The regulator imposed a large fine",
         lambda h: (not h.ok, "not ok"))
    case("an ellipsis quote on exactly one OTHER page is OFF_PAGE there", 2,
         "The institution continued to trade ... The bank failed to file reports without delay",
         lambda h: (h.status == cm.OFF_PAGE and h.found_on == (1,), "off_page, found_on=(1,)"))

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
