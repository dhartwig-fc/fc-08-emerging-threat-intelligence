"""The flag agent's answer (Stage566 K3a, fc-10 K3 design §4): one verdict per advisory indicator, rules code enforces.

A `matches` verdict names one of the typology's imported indicators -- verbatim after normalise(), or the whole
answer is refused. A `new` verdict is one plain line (the Knowledge Centre renders one-line bullets and nothing else)
citing ONE quote already in that indicator's own citations, which tools/review.py's gate has page-checked. Nothing
unverified enters.
"""
from __future__ import annotations

import hashlib
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from schemas.doctrine_draft import text_problems

FLAG_MAX = 200
LINK_KEY = r"^ADV-\d{4}-\d{4}::[A-Z]{2,6}\d{3}[A-Z]?$"


class Verdict(BaseModel):
    indicator_index: int = Field(..., ge=0)
    verdict: Literal["matches", "new"]
    matched_indicator: Optional[str] = None
    flag_text: Optional[str] = None
    citation_index: Optional[int] = Field(None, ge=0)


class FlagComparison(BaseModel):
    link_key: str = Field(..., pattern=LINK_KEY)
    verdicts: List[Verdict] = Field(..., min_length=1)


def normalise(text: str) -> str:
    """Lower-case, whitespace collapsed: the K3 design's normalisation for both the match and the key."""
    return " ".join(text.split()).lower()


def flag_sha8(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()[:8]


def indicator_problems(answer: FlagComparison, typology_indicators: list) -> list:
    listed = {normalise(t) for t in typology_indicators}
    return ["indicator %d: %r is not one of the typology's indicators" % (v.indicator_index, v.matched_indicator)
            for v in answer.verdicts
            if v.verdict == "matches" and normalise(v.matched_indicator or "") not in listed]


def citation_problems(answer: FlagComparison, record: dict) -> list:
    indicators = record.get("indicators") or []
    out = []
    for v in answer.verdicts:
        if v.verdict != "new" or v.indicator_index >= len(indicators):
            continue
        held = indicators[v.indicator_index].get("citations") or []
        if v.citation_index is None or v.citation_index >= len(held):
            out.append("indicator %d: citation %s is not one of its %d citations"
                       % (v.indicator_index, v.citation_index, len(held)))
    return out


def _shape_problems(answer: FlagComparison, link_key: str, record: dict) -> list:
    out = [] if answer.link_key == link_key else ["answer is for %s, not %s" % (answer.link_key, link_key)]
    count = len(record.get("indicators") or [])
    seen = {}
    for v in answer.verdicts:
        if v.indicator_index >= count:
            out.append("no indicator %d in the record (it has %d)" % (v.indicator_index, count))
        seen[v.indicator_index] = seen.get(v.indicator_index, 0) + 1
        if v.verdict == "new":
            text = v.flag_text or ""
            if not text.strip():
                out.append("indicator %d: a new flag with no text" % v.indicator_index)
            if len(text) > FLAG_MAX:
                out.append("indicator %d: flag longer than %d characters" % (v.indicator_index, FLAG_MAX))
            out += ["indicator %d: flag has %s" % (v.indicator_index, p) for p in text_problems(text)]
    out += ["indicator %d answered more than once" % i for i, n in sorted(seen.items()) if n > 1]
    out += ["indicator %d unanswered" % i for i in range(count) if i not in seen]
    return out


def problems(answer: FlagComparison, link_key: str, record: dict, typology_indicators: list) -> list:
    return (_shape_problems(answer, link_key, record) + indicator_problems(answer, typology_indicators)
            + citation_problems(answer, record))
