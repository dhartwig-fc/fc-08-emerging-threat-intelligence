"""
One rule for "is this quote on this page", shared by every caller.

Until week 5 this lived inside evals/check_citations.py, and the review gate and
the MCP server would each have needed it too. Three copies of a matching rule
drift, and a quote one of them accepts and another refuses is a governance
defect nobody can see. So there is one rule and three callers:
mcp_server/knowledge_centre_server.py (refuses at proposal time),
governance/proposals.py (re-checks at review time) and evals/check_citations.py.

The match is deliberately NOT fuzzy on meaning. Five ok tiers, tried in order:
  exact    the normalised quote is a substring of the normalised page;
  spacing  the same with ALL whitespace removed, because pypdf splits words on
           born-digital FATF PDFs ("collus ion", "t o believe"). An honest quote
           whose only difference is the extractor's spacing is not a fabrication.
  artefact the quote's LETTERS (Unicode letters, after norm; digits, punctuation
           and symbols dropped) are a substring of the page's letters, every
           maximal digit run in the quote occurs as a WHOLE number in the page's
           whitespace-free text (no digit either side of it), and the quote has at
           least ARTEFACT_MIN_LETTERS letters. It tolerates what pypdf leaves in
           running text: footnote markers glued to a word ("reporting19.") or
           standing between sentences ("margins. 5 in its trade"), line-break
           hyphens ("re- selling" for "reselling"), list-bullet glyphs, and
           punctuation. It does NOT tolerate a different word, accented or
           non-Latin letters included (the letters must match in order,
           contiguously, after NFC composition so a decomposed accent is still
           a letter), or a different number ("$480,000" is refused on a page
           reading "$48,000", and so is the truncation the other way round).
           Short quotes are excluded because a few letters match by coincidence.
           RESIDUALS, stated because they are real and the rule cannot see them:
             - a quoted number that occurs ELSEWHERE on the same page as a whole
               number satisfies the digit rule;
             - a quote that DROPS a number, or a trailing digit group, from the
               page's text passes -- to this rule it is indistinguishable from a
               footnote marker being dropped;
             - a line-break-hyphen fusion that forms a different word passes
               ("re- sign" on the page, "resign" in the quote);
             - a dropped minus sign passes (the sign is punctuation, not a digit).
           Added 2026-09-25
           because a review measured 18 of the 43 citations check_citations
           called "missing" as present in the PDF on exactly one page (13 on the
           cited page), missed only because of these artefacts -- and this rule
           is shared, so the same defect was refusing true quotes in the MCP
           server and the review gate too.
  ellipsis the quote contains "..." or "…" (added 2026-09-25, owner's decision). It is split
           there into fragments (stripped; an empty fragment, from a leading or trailing
           ellipsis, is dropped), and it holds when there are at least two, EVERY one
           has >= ARTEFACT_MIN_LETTERS letters, and each matches the cited page by the
           ARTEFACT rule (same letters, every digit run a whole number on the page) at a
           letters-form position AFTER the previous fragment's match -- in order, not
           overlapping. It tolerates a quotation with omissions. It does NOT tolerate
           fragments out of order, a fragment that is not on the page, or a short
           fragment ("not ... guilty": a few letters match anywhere).
  spans    the quote runs over a page break (added 2026-09-25, same decision). It holds on
           cited page p when the quote's letters split into a prefix of >= 10 letters
           that ENDS page p and a remainder (>= 1 letter) that BEGINS page p+1, each page
           first stripped of RUNNING lines at that edge -- normalised lines found on at
           least half the document's pages (and at least 2), i.e. running headers and
           footers -- and every digit run in the quote is a whole number on p or p+1.
           It does NOT tolerate a prefix from the middle of page p, a continuation on
           any page but p+1, or a quote cited at p+1. A header that carries its page
           number ("CRIMES | 29") is a different line on every page, so it is not a
           running line and still blocks the join.
           Why both: of the 25 citations still "missing" after the artefact tier, 12
           were ellipsis quotations with every fragment verbatim on the cited page and 5
           ran over a page break -- true quotes, and rule (a) of the owner's citation
           repair would have removed three golden-key typologies over them.
           MEASURED on the real 717: ellipsis accepts all 12 (the 10-letter floor excludes
           none). spans, as specified here, accepts NONE of the 5: one next page opens
           with a letterless page-number line ("| 23") that is not a running line, so
           trimming stops before the running title lines behind it; one document's
           header carries its page number and alternates sides, so neither form reaches
           half the pages; three quotes are cited at p+1, the page they END on. The rule
           stands as decided; widening it is a separate decision.
Anything else is off_page (right words, wrong page -- by the spacing rule over the
whole document first, then by the artefact rule page by page, then by the ellipsis rule
when it holds on exactly ONE other page) or missing.

norm() is NOT loosened to do this: governance/proposals.quote_hash keys every
recorded decision on norm(), so changing it would orphan the decision log. The
artefact tier derives its letters-only and digit forms FROM norm() instead.

An EMPTY quote is missing. The empty string is a substring of every page, so
until the final week-5 review a quote of "" located as an exact match -- a
citation that cites nothing, verified.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Sequence, Tuple

EXACT, SPACING, ARTEFACT, OFF_PAGE, MISSING = "exact", "spacing", "artefact", "off_page", "missing"
ELLIPSIS, SPANS = "ellipsis", "spans"
_ELLIPSIS_MARK = re.compile(r"\.\.\.|\u2026")

# A letters-only match shorter than this is too ambiguous to call the same text.
ARTEFACT_MIN_LETTERS = 10


def norm(s: str) -> str:
    # Replace curly quotes that may appear in PDF text
    s = s.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xad", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _letters(normed: str) -> str:
    """The letters of already-normalised text, Unicode letters included.

    Drops digits, spaces, hyphens, punctuation, underscores and non-letter symbols
    (the private-use bullet glyph pypdf emits for list markers). It was [^a-z] until
    fix round 1, which deleted every non-ASCII letter: "Hans Möller" matched a page
    reading "Hans Müller", and a swapped Cyrillic name matched anything.

    The text is NFC-composed first. A page that encodes "ü" as "u" + U+0308 (a combining
    diaeresis, which is not a letter) otherwise loses the mark here and reads "Muller", so
    a quote of a DIFFERENT name matched it -- and the true composed quote "Müller" did not.
    Added 2026-09-25; unobserved in the corpus, and the 717 real citations locate the same.
    """
    return re.sub(r"[\W\d_]", "", unicodedata.normalize("NFC", normed))


def _artefact_holds(letters_q: str, digits_q, letters_page: str, tight_page: str) -> bool:
    """The ARTEFACT rule for one page: same letters in order, every digit run present, long enough.

    A digit run must occur as a WHOLE number on the page (no digit either side). As a plain
    substring test, until fix round 1, a truncated number passed: "48" is inside "480", so
    "$48,000" was accepted against a page reading "$480,000", and "30" against "300".
    """
    return (len(letters_q) >= ARTEFACT_MIN_LETTERS
            and letters_q in letters_page
            and all(re.search(r"(?<!\d)%s(?!\d)" % re.escape(d), tight_page) for d in digits_q))


def _digits_whole(digits, tight_page: str) -> bool:
    return all(re.search(r"(?<!\d)%s(?!\d)" % re.escape(d), tight_page) for d in digits)


def _fragments(normed: str) -> list:
    """The ellipsis fragments of a normalised quote; empty ones (a leading or trailing mark) dropped."""
    return [f.strip() for f in _ELLIPSIS_MARK.split(normed) if f.strip()]


def _ellipsis_holds(frags, letters_page: str, tight_page: str) -> bool:
    """The ELLIPSIS rule for one page. frags: [(letters, digit runs)] per fragment, in quote order."""
    if len(frags) < 2:
        return False
    pos = 0
    for lf, df in frags:
        if len(lf) < ARTEFACT_MIN_LETTERS:
            return False
        at = letters_page.find(lf, pos)
        if at < 0 or not _digits_whole(df, tight_page):
            return False
        pos = at + len(lf)
    return True


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Located:
    status: str
    found_on: Tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in (EXACT, SPACING, ARTEFACT, ELLIPSIS, SPANS)


class PageIndex:
    """Normalised page text for one document, indexed by 1-based PDF page."""

    def __init__(self, page_texts: Sequence[str]):
        raw = [t or "" for t in page_texts]
        self.pages = [norm(t) for t in raw]
        self.tight = [p.replace(" ", "") for p in self.pages]
        self.tight_all = "".join(self.tight)
        self.letters = [_letters(p) for p in self.pages]
        # SPANS: each page's normalised lines, and the RUNNING lines (headers, footers) --
        # those on at least half the pages, and at least two. Plain strings work too: a
        # string's lines are str.splitlines().
        lines = [[norm(l) for l in t.splitlines()] for t in raw]
        seen = Counter(l for ls in lines for l in set(ls) if l)
        floor = max(2, math.ceil(len(raw) / 2))
        self.running = frozenset(l for l, n in seen.items() if n >= floor)

        def trim_end(ls):
            ls = list(ls)
            while ls and (not ls[-1] or ls[-1] in self.running):
                ls.pop()
            return ls

        def trim_start(ls):
            return list(reversed(trim_end(list(reversed(ls)))))

        self.end_letters = [_letters(" ".join(trim_end(ls))) for ls in lines]
        self.start_letters = [_letters(" ".join(trim_start(ls))) for ls in lines]

    @classmethod
    def from_pdf(cls, path) -> "PageIndex":
        from pypdf import PdfReader
        return cls([p.extract_text() or "" for p in PdfReader(str(path)).pages])

    def __len__(self) -> int:
        return len(self.pages)

    def _spans_holds(self, i: int, letters_q: str, digits_q) -> bool:
        """The SPANS rule: letters_q = prefix (ends page i) + remainder (begins page i+1)."""
        if not 0 <= i < len(self.pages) - 1:
            return False
        end, start = self.end_letters[i], self.start_letters[i + 1]
        if not any(end.endswith(letters_q[:k]) and start.startswith(letters_q[k:])
                   for k in range(ARTEFACT_MIN_LETTERS, len(letters_q))):
            return False
        return all(_digits_whole([d], self.tight[i]) or _digits_whole([d], self.tight[i + 1])
                   for d in digits_q)

    def locate(self, page: int, quote: str) -> Located:
        q = norm(quote)
        tq = q.replace(" ", "")
        if not tq:
            return Located(MISSING)
        i = page - 1
        in_range = 0 <= i < len(self.pages)
        if in_range and q in self.pages[i]:
            return Located(EXACT)
        if in_range and tq in self.tight[i]:
            return Located(SPACING)
        lq, dq = _letters(q), re.findall(r"\d+", q)
        if in_range and _artefact_holds(lq, dq, self.letters[i], self.tight[i]):
            return Located(ARTEFACT)
        frags = [(_letters(f), re.findall(r"\d+", f)) for f in _fragments(q)]
        if in_range and _ellipsis_holds(frags, self.letters[i], self.tight[i]):
            return Located(ELLIPSIS)
        if in_range and self._spans_holds(i, lq, dq):
            return Located(SPANS)
        if tq in self.tight_all:
            return Located(OFF_PAGE, tuple(n + 1 for n, p in enumerate(self.tight) if tq in p))
        found = tuple(n + 1 for n in range(len(self.pages))
                      if _artefact_holds(lq, dq, self.letters[n], self.tight[n]))
        if found:
            return Located(OFF_PAGE, found)
        found = tuple(n + 1 for n in range(len(self.pages))
                      if _ellipsis_holds(frags, self.letters[n], self.tight[n]))
        if len(found) == 1:
            return Located(OFF_PAGE, found)
        return Located(MISSING)
