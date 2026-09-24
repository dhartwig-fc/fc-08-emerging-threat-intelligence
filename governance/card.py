"""One link, rendered for a human deciding it. Plain text: it has to read in a terminal."""

from __future__ import annotations

import textwrap
from typing import Optional

from governance.decisions import Decision
from governance.proposals import Link


def _wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(" ".join(text.split()), width=96, initial_indent=indent, subsequent_indent=indent)


def render(link: Link, prior: Optional[Decision], advisories: dict, library: dict, golden_ids: set) -> str:
    a = advisories.get(link.advisory_id, {})
    lines = ["=" * 100, "%s  %s" % (link.advisory_id, a.get("title", "(title not in the advisory list)"))]
    if link.kind == "governed":
        t = library.get(link.typology_id, {})
        lines.append("PROPOSED LINK  %s  %s  [%s]" % (link.typology_id, t.get("label", "?"), t.get("family", "?")))
        if t.get("summary"):
            lines.append(_wrap(t["summary"]))
        held = link.typology_id in golden_ids
        lines.append("  golden label %s this link (context only, never a rule)" % ("HOLDS" if held else "LACKS"))
    else:
        lines.append("PROPOSED EMERGENT TYPOLOGY  %r" % link.emergent_label)
        lines.append("  not in the library; approving makes it a candidate for doctrine, not a link")
    if prior is not None:
        lines.append("  NEW EVIDENCE: previously %s on %s%s" % (
            prior.decision.upper(), prior.decided_at[:10], (" -- %s" % prior.note) if prior.note else ""))
    lines.append("QUOTES")
    for page, quote, count in link.quotes():
        lines.append("  p%-3d %s" % (page, "(x%d)" % count if count > 1 else ""))
        lines.append(_wrap("“%s”" % quote, "        "))
    rationales = sorted({p.rationale for p in link.proposals})
    lines.append("RATIONALE%s" % ("S" if len(rationales) > 1 else ""))
    for r in rationales:
        lines.append(_wrap(r))
    lines.append("FROM  %d proposal%s, runs: %s, stages: %s" % (
        len(link.proposals), "" if len(link.proposals) == 1 else "s", ", ".join(link.run_ids),
        ", ".join(link.stages)))
    return "\n".join(lines)
