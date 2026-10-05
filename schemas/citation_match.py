"""
One rule for "is this quote on this page", shared by every caller.

Until week 5 this lived inside evals/check_citations.py, and the review gate and
the MCP server would each have needed it too. Three copies of a matching rule
drift, and a quote one of them accepts and another refuses is a governance
defect nobody can see. So there is one rule and three callers:
mcp_server/knowledge_centre_server.py (refuses at proposal time),
governance/proposals.py (re-checks at review time) and evals/check_citations.py.

The match is deliberately NOT fuzzy on meaning. Four ok tiers, tried in order:
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
           has >= ELLIPSIS_MIN_FRAGMENT_LETTERS (20) letters, and each matches the cited
           page by the ARTEFACT rule (same letters, every digit run a whole number on the
           page) at a letters-form position AFTER the previous fragment's match ends -- in
           order, not overlapping -- and no more than ELLIPSIS_MAX_GAP_LETTERS (600)
           letters after it. It tolerates a quotation with omissions. It does NOT
           tolerate fragments out of order or overlapping, a fragment that is not on the
           page, a short fragment ("not ... guilty": a few letters match anywhere), or
           fragments spliced from far apart on the page. The floor and the gap bound
           were tightened by a controller ruling after review (first written as 10
           letters, unbounded): this rule also gates propose_link, and an unbounded
           ellipsis lets a proposal splice two unrelated sentences of one page into a
           claim the page never makes. Measured on the 12 real ellipsis quotes: shortest
           fragment 21 letters, widest gap 560 -- all still pass.
           Why: of the 25 citations still "missing" after the artefact tier, 12 were
           ellipsis quotations with every fragment verbatim on the cited page -- true
           quotes, and rule (a) of the owner's citation repair would have removed
           three golden-key typologies over them. Measured on the real 717: it accepts
           all 12. Off the cited page, an ellipsis quote is OFF_PAGE only when it holds
           on exactly ONE other page; on two or more it is MISSING.
  NO PAGE-SPANNING TIER. One was added on 2026-09-25 and removed the same day: it
           matched none of the 5 real quotes that run over a page break (page-number
           lines, alternating headers, footnote blocks and quotes cited at the page
           they end on all defeated it), and every tolerance added here also loosens
           propose_link's gate. The owner chose to stop widening this shared rule:
           true quotes the matcher cannot place are ATTESTED instead
           (evals/attested_citations.json, read by evals/check_citations.py only).
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
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

EXACT, SPACING, ARTEFACT, OFF_PAGE, MISSING = "exact", "spacing", "artefact", "off_page", "missing"
ELLIPSIS = "ellipsis"
_ELLIPSIS_MARK = re.compile(r"\.\.\.|\u2026")

# A letters-only match shorter than this is too ambiguous to call the same text.
ARTEFACT_MIN_LETTERS = 10
# ELLIPSIS: each fragment at least this many letters, and at most this many letters of page
# between one fragment's end and the next fragment's start. Measured on the 12 real ellipsis
# quotes (2026-09-25): shortest fragment 21 letters, widest gap 560.
ELLIPSIS_MIN_FRAGMENT_LETTERS = 20
ELLIPSIS_MAX_GAP_LETTERS = 600


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
    """The ELLIPSIS rule for one page. frags: [(letters, digit runs)] per fragment, in quote order.

    Every fragment is placed after the previous one ends (in order, not overlapping), no more
    than ELLIPSIS_MAX_GAP_LETTERS after it. The search tries every occurrence of a fragment,
    not only the first: with a gap bound, a later occurrence of an earlier fragment can be
    the one close enough to the next. For a fragment after the first, later occurrences only
    widen the gap, so the search stops at the first one past the bound.
    """
    if len(frags) < 2:
        return False
    for lf, _ in frags:
        if len(lf) < ELLIPSIS_MIN_FRAGMENT_LETTERS:
            return False
    if not all(_digits_whole(df, tight_page) for _, df in frags):
        return False

    def fits(k: int, pos: int) -> bool:
        if k == len(frags):
            return True
        lf = frags[k][0]
        at = letters_page.find(lf, pos)
        while at >= 0:
            if k and at - pos > ELLIPSIS_MAX_GAP_LETTERS:
                return False
            if fits(k + 1, at + len(lf)):
                return True
            at = letters_page.find(lf, at + 1)
        return False

    return fits(0, 0)


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


DOCUMENT_SUFFIXES = (".pdf", ".html", ".htm")


def document_texts(path) -> List[str]:
    """The raw text of each page of a pinned document: pypdf for a .pdf, schemas/html_pages for .html/.htm.

    By SUFFIX, never by sniffing, so the choice is visible in the file name every caller already holds
    (feeds/inbox.py names a pinned file <sha256>.pdf or <sha256>.html from its content type). Anything
    else is refused: a document that cannot be paged cannot carry a citation.
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        return [p.extract_text() or "" for p in PdfReader(str(path)).pages]
    if suffix in (".html", ".htm"):
        from schemas.html_pages import html_pages
        return html_pages(Path(path).read_bytes())
    raise ValueError("%s is neither a PDF nor an HTML document (%s)" % (path, ", ".join(DOCUMENT_SUFFIXES)))


@dataclass(frozen=True)
class Located:
    status: str
    found_on: Tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in (EXACT, SPACING, ARTEFACT, ELLIPSIS)


class PageIndex:
    """Normalised page text for one document, indexed by 1-based PDF page."""

    def __init__(self, page_texts: Sequence[str]):
        self.pages = [norm(t or "") for t in page_texts]
        self.tight = [p.replace(" ", "") for p in self.pages]
        self.tight_all = "".join(self.tight)
        self.letters = [_letters(p) for p in self.pages]
        self.cased = [_norm_cased(t or "") for t in page_texts]  # the pages in their own case, for quote_reply only

    @classmethod
    def from_pdf(cls, path) -> "PageIndex":
        from pypdf import PdfReader
        return cls([p.extract_text() or "" for p in PdfReader(str(path)).pages])

    @classmethod
    def from_html(cls, raw: bytes) -> "PageIndex":
        """Pages of a pinned HTML document, by schemas/html_pages.py's fixed rule (slice 2)."""
        from schemas.html_pages import html_pages
        return cls(html_pages(raw))

    @classmethod
    def from_document(cls, path) -> "PageIndex":
        """A pinned document's pages, chosen by its kind (slice 2 C). THE loader for every caller that
        re-finds a quote -- the extractor's prompt, propose_link, the review gate, check_citations -- so a
        live feed's HTML advisory is paged by the same rule everywhere, and a PDF exactly as before."""
        return cls(document_texts(path))

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
        frags = [(_letters(f), re.findall(r"\d+", f)) for f in _fragments(q)]
        if in_range and _ellipsis_holds(frags, self.letters[i], self.tight[i]):
            return Located(ELLIPSIS)
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


# ---------------------------------------------------------------------------
# Asking the rule a question: "is THIS quote on THIS page, and if not, where does it part company?"
# (slice 2 C2, 2026-10-02). Every live extraction to that date was refused at acceptance for quotes the
# matcher could not place, because OFAC SDN entries embed each name's original script and the extractor
# dropped or mistranscribed it. The extractor now asks the same rule BEFORE it finishes -- the MCP tool
# knowledge_centre_check_quote -- and the one repair turn after it names the same answers. Both come from
# quote_reply below, and quote_reply decides ok / wrong page / not found by PageIndex.locate and nothing
# else, so the tool, the repair turn, propose_link, the review gate and accept_run cannot disagree about a
# quote. Only the "where it diverges" detail is new, and it never changes a verdict.
# ---------------------------------------------------------------------------

# How much of the page, and of the quote, a "not found" reply shows either side of the divergence.
DIVERGENCE_SNIPPET = 60
# A shared opening shorter than this is coincidence (a few letters occur anywhere), not a place where a
# quote left the page's text: the reply then says no real opening matches instead of pointing at noise.
DIVERGENCE_MIN_PREFIX = 8

VERBATIM, WRONG_PAGE, NOT_FOUND = "verbatim", "wrong_page", "not_found"


def _norm_cased(s: str) -> str:
    """norm() without the lower-casing: the same collapse of quotes, dashes, soft hyphens and whitespace,
    kept in the page's own case so a divergence shown to the agent can be copied as written."""
    s = s.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xad", "")
    return re.sub(r"\s+", " ", s).strip()


def _longest_prefix_in(q: str, page: str) -> Tuple[int, int]:
    """(k, position): the longest k such that q[:k] occurs in page, and where. A prefix that occurs makes every
    shorter one occur, so a binary search finds the longest."""
    lo, hi = 0, len(q)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if q[:mid] in page:
            lo = mid
        else:
            hi = mid - 1
    return lo, (page.find(q[:lo]) if lo else -1)


def divergence(index: "PageIndex", page: int, quote: str) -> dict:
    """Where the quote's opening stops agreeing with the document: the page it agrees with longest (the cited
    page wins a tie), how many characters agree, and what each side says next.
    {"chars": K, "page": N, "page_reads": "...", "quote_has": "..."}; page is 0 and the texts empty when
    no real opening (DIVERGENCE_MIN_PREFIX characters) is anywhere in the document."""
    q = norm(quote)
    cited = page - 1
    order = ([cited] if 0 <= cited < len(index.pages) else []) + [i for i in range(len(index.pages)) if i != cited]
    best = (0, -1, -1)
    for i in order:
        k, pos = _longest_prefix_in(q, index.pages[i])
        if k > best[0]:
            best = (k, i, pos)
    k, i, pos = best
    if k < DIVERGENCE_MIN_PREFIX:
        return {"chars": k, "page": 0, "page_reads": "", "quote_has": ""}
    # Cased text only when the case-fold kept every character in place; otherwise the lower-cased text.
    page_text = index.cased[i] if len(index.cased[i]) == len(index.pages[i]) else index.pages[i]
    qc = _norm_cased(quote)
    quote_text = qc if len(qc) == len(q) else q
    return {"chars": k, "page": i + 1,
            "page_reads": page_text[pos + k: pos + k + DIVERGENCE_SNIPPET].strip(),
            "quote_has": quote_text[k: k + DIVERGENCE_SNIPPET].strip()}


def quote_check(index: "PageIndex", page: int, quote: str) -> dict:
    """One quote against one document, by the shared rule: {"status": VERBATIM | WRONG_PAGE | NOT_FOUND,
    "pages": the cited page (verbatim) or the pages the quote IS on (wrong_page), "page_count": N, and for
    NOT_FOUND "divergence": divergence(...)}."""
    hit = index.locate(page, quote)
    if hit.ok:
        return {"status": VERBATIM, "pages": (page,), "page_count": len(index)}
    if hit.status == OFF_PAGE:
        return {"status": WRONG_PAGE, "pages": tuple(hit.found_on), "page_count": len(index)}
    return {"status": NOT_FOUND, "pages": (), "page_count": len(index), "divergence": divergence(index, page, quote)}


def quote_reply(index: "PageIndex", page: int, quote: str) -> str:
    """The sentence the agent reads: knowledge_centre_check_quote's reply, and each line of the repair turn.

      Verbatim: on page N.
      Wrong page: the quote is on page(s) M, not N.
      Not found: the longest matching prefix is K characters; the page then reads '...' where the quote has '...'.

    Short on purpose: never a whole page, only the DIVERGENCE_SNIPPET characters either side of where the
    quote and the page part company."""
    got = quote_check(index, page, quote)
    if got["status"] == VERBATIM:
        return "Verbatim: on page %d." % page
    if got["status"] == WRONG_PAGE:
        return "Wrong page: the quote is on page(s) %s, not %d." % (", ".join(str(n) for n in got["pages"]), page)
    d, lead = got["divergence"], ""
    if not 1 <= page <= got["page_count"]:
        lead = "page %d does not exist (the document has %d page(s)); " % (page, got["page_count"])
    if not d["page"]:
        return ("Not found: %sno real opening of the quote is anywhere in the document (the longest matching prefix "
                "is %d characters). Copy the text exactly from one page." % (lead, d["chars"]))
    return ("Not found: %sthe longest matching prefix is %d characters, on page %d; the page then reads '%s' where "
            "the quote has '%s'." % (lead, d["chars"], d["page"], d["page_reads"], d["quote_has"]))
