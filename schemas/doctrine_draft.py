"""A doctrine draft (Stage565 S3, spec §6): structure the model returns, rules code enforces, markdown code writes.

The Knowledge Centre curates five headings and renders paragraphs, one-line bullets and nothing else (fc-10
CLAUDE.md, 'Doctrine coverage'); fc-10's record-draft re-checks with its own doctrine_rules. Every statement
cites the proposal's evidence by advisory and page -- the pages come from fc-10's export (S3 plan R10).
"""
from __future__ import annotations

import re
from typing import List, Literal

from pydantic import BaseModel, Field

CURATED = ("Purpose", "Intelligence Question", "Detection Rules", "Risk Drivers", "Investigation Actions")
CITED_LINE = re.compile(r"\((ADV-\d{4}-\d{4} p\.\d+)(; ADV-\d{4}-\d{4} p\.\d+)*\)$")


class Citation(BaseModel):
    advisory_id: str = Field(..., pattern=r"^ADV-\d{4}-\d{4}$")
    page: int = Field(..., ge=1)


class Statement(BaseModel):
    kind: Literal["paragraph", "bullet"]
    text: str = Field(..., min_length=10, max_length=600)
    citations: List[Citation] = Field(..., min_length=1)


class Section(BaseModel):
    heading: Literal["Purpose", "Intelligence Question", "Detection Rules", "Risk Drivers", "Investigation Actions"]
    statements: List[Statement] = Field(..., min_length=1)


class DoctrineDraft(BaseModel):
    proposal_id: str = Field(..., pattern=r"^TP-\d{4}-\d{3}$")
    title: str = Field(..., min_length=3, max_length=120)
    sections: List[Section] = Field(..., min_length=5, max_length=5)


def allowed_citations(proposal):
    return {(e["advisory_id"], c["page"]) for e in proposal.get("evidence", [])
            for c in e.get("citations", []) if c.get("page")}


def text_problems(text):
    out = []
    if "\n" in text or "\r" in text:
        out.append("more than one physical line")
    for mark, name in (("**", "bold"), ("`", "inline code"), ("|", "a pipe")):
        if mark in text:
            out.append("%s (rendered literally)" % name)
    if text.lstrip().startswith("#"):
        out.append("a heading marker")
    return out


def citation_problems(draft, proposal):
    allowed = allowed_citations(proposal)
    return ["%s: cites %s p.%d, which the proposal's evidence does not hold" % (s.text[:40], c.advisory_id, c.page)
            for sec in draft.sections for s in sec.statements for c in s.citations
            if (c.advisory_id, c.page) not in allowed]


def problems(draft, proposal):
    out = []
    if draft.proposal_id != proposal["proposal_id"]:
        out.append("the draft is for %s, not %s" % (draft.proposal_id, proposal["proposal_id"]))
    if tuple(s.heading for s in draft.sections) != CURATED:
        out.append("sections are not in the curated order %s" % ", ".join(CURATED))
    for sec in draft.sections:
        for s in sec.statements:
            out += ["%s: %s" % (sec.heading, p) for p in text_problems(s.text)]
    out += ["title: %s" % p for p in text_problems(draft.title)]
    return out + citation_problems(draft, proposal)


def _cites(s):
    return "(%s)" % "; ".join("%s p.%d" % (c.advisory_id, c.page) for c in s.citations)


def render(draft):
    lines = ["# %s %s" % (draft.proposal_id, draft.title), ""]
    for sec in draft.sections:
        lines += ["## %s" % sec.heading, ""]
        for i, s in enumerate(sec.statements):
            if s.kind == "bullet":
                lines.append("- %s %s" % (s.text, _cites(s)))
                nxt = sec.statements[i + 1].kind if i + 1 < len(sec.statements) else None
                if nxt != "bullet":
                    lines.append("")
            else:
                lines += ["%s %s" % (s.text, _cites(s)), ""]
    return "\n".join(lines).rstrip("\n") + "\n"
