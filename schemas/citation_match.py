"""
One rule for "is this quote on this page", shared by every caller.

Until week 5 this lived inside evals/check_citations.py, and the review gate and
the MCP server would each have needed it too. Three copies of a matching rule
drift, and a quote one of them accepts and another refuses is a governance
defect nobody can see. So there is one rule and three callers:
mcp_server/knowledge_centre_server.py (refuses at proposal time),
governance/proposals.py (re-checks at review time) and evals/check_citations.py.

The match is deliberately NOT fuzzy on meaning. Three ok tiers, tried in order:
  exact    the normalised quote is a substring of the normalised page;
  spacing  the same with ALL whitespace removed, because pypdf splits words on
           born-digital FATF PDFs ("collus ion", "t o believe"). An honest quote
           whose only difference is the extractor's spacing is not a fabrication.
  artefact the quote's LETTERS (a-z only, after norm) are a substring of the page's
           letters, every maximal digit run in the quote occurs in the page's
           whitespace-free text, and the quote has at least ARTEFACT_MIN_LETTERS
           letters. It tolerates what pypdf leaves in running text: footnote
           markers glued to a word ("reporting19.") or standing between sentences
           ("margins. 5 in its trade"), line-break hyphens ("re- selling" for
           "reselling"), and punctuation. It does NOT tolerate a different word
           (the letters must match in order, contiguously) or a different number
           (the quote's digit runs must be on the page: "$480,000" is refused on a
           page reading "$48,000"). Residual: a digit run that happens to occur
           elsewhere on the same page satisfies the digit rule. Short quotes are
           excluded because a few letters match by coincidence. Added 2026-09-25
           because a review measured 18 of the 43 citations check_citations
           called "missing" as present in the PDF on exactly one page (13 on the
           cited page), missed only because of these artefacts -- and this rule
           is shared, so the same defect was refusing true quotes in the MCP
           server and the review gate too.
Anything else is off_page (right words, wrong page -- by the spacing rule over the
whole document first, then by the artefact rule page by page) or missing.

norm() is NOT loosened to do this: governance/proposals.quote_hash keys every
recorded decision on norm(), so changing it would orphan the decision log. The
artefact tier derives its letters-only and digit forms FROM norm() instead.

An EMPTY quote is missing. The empty string is a substring of every page, so
until the final week-5 review a quote of "" located as an exact match -- a
citation that cites nothing, verified.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Sequence, Tuple

EXACT, SPACING, ARTEFACT, OFF_PAGE, MISSING = "exact", "spacing", "artefact", "off_page", "missing"

# A letters-only match shorter than this is too ambiguous to call the same text.
ARTEFACT_MIN_LETTERS = 10


def norm(s: str) -> str:
    # Replace curly quotes that may appear in PDF text
    s = s.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xad", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _letters(normed: str) -> str:
    """The a-z letters of already-normalised text: drops digits, spaces, hyphens, punctuation."""
    return re.sub(r"[^a-z]", "", normed)


def _artefact_holds(letters_q: str, digits_q, letters_page: str, tight_page: str) -> bool:
    """The ARTEFACT rule for one page: same letters in order, every digit run present, long enough."""
    return (len(letters_q) >= ARTEFACT_MIN_LETTERS
            and letters_q in letters_page
            and all(d in tight_page for d in digits_q))


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
        return self.status in (EXACT, SPACING, ARTEFACT)


class PageIndex:
    """Normalised page text for one document, indexed by 1-based PDF page."""

    def __init__(self, page_texts: Sequence[str]):
        self.pages = [norm(t or "") for t in page_texts]
        self.tight = [p.replace(" ", "") for p in self.pages]
        self.tight_all = "".join(self.tight)
        self.letters = [_letters(p) for p in self.pages]

    @classmethod
    def from_pdf(cls, path) -> "PageIndex":
        from pypdf import PdfReader
        return cls([p.extract_text() or "" for p in PdfReader(str(path)).pages])

    def __len__(self) -> int:
        return len(self.pages)

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
        if tq in self.tight_all:
            return Located(OFF_PAGE, tuple(n + 1 for n, p in enumerate(self.tight) if tq in p))
        found = tuple(n + 1 for n in range(len(self.pages))
                      if _artefact_holds(lq, dq, self.letters[n], self.tight[n]))
        if found:
            return Located(OFF_PAGE, found)
        return Located(MISSING)
