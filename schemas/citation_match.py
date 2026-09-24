"""
One rule for "is this quote on this page", shared by every caller.

Until week 5 this lived inside evals/check_citations.py, and the review gate and
the MCP server would each have needed it too. Three copies of a matching rule
drift, and a quote one of them accepts and another refuses is a governance
defect nobody can see. So there is one rule and three callers:
mcp_server/knowledge_centre_server.py (refuses at proposal time),
governance/proposals.py (re-checks at review time) and evals/check_citations.py.

The match is deliberately NOT fuzzy on meaning. Two tiers only:
  exact    the normalised quote is a substring of the normalised page;
  spacing  the same with ALL whitespace removed, because pypdf splits words on
           born-digital FATF PDFs ("collus ion", "t o believe"). An honest quote
           whose only difference is the extractor's spacing is not a fabrication.
Anything else is off_page (right words, wrong page) or missing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Sequence, Tuple

EXACT, SPACING, OFF_PAGE, MISSING = "exact", "spacing", "off_page", "missing"


def norm(s: str) -> str:
    # Replace curly quotes that may appear in PDF text
    s = s.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xad", "")
    return re.sub(r"\s+", " ", s).strip().lower()


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
        return self.status in (EXACT, SPACING)


class PageIndex:
    """Normalised page text for one document, indexed by 1-based PDF page."""

    def __init__(self, page_texts: Sequence[str]):
        self.pages = [norm(t or "") for t in page_texts]
        self.tight = [p.replace(" ", "") for p in self.pages]
        self.tight_all = "".join(self.tight)

    @classmethod
    def from_pdf(cls, path) -> "PageIndex":
        from pypdf import PdfReader
        return cls([p.extract_text() or "" for p in PdfReader(str(path)).pages])

    def __len__(self) -> int:
        return len(self.pages)

    def locate(self, page: int, quote: str) -> Located:
        q = norm(quote)
        tq = q.replace(" ", "")
        i = page - 1
        in_range = 0 <= i < len(self.pages)
        if in_range and q in self.pages[i]:
            return Located(EXACT)
        if in_range and tq in self.tight[i]:
            return Located(SPACING)
        if tq in self.tight_all:
            return Located(OFF_PAGE, tuple(n + 1 for n, p in enumerate(self.tight) if tq in p))
        return Located(MISSING)
