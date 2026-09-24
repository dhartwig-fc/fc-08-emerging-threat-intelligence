"""
Desk digests: one Markdown file per desk per batch.

What a desk reads, for each advisory routed to it (governance/routing.py):
  - why it was routed (which typology, or "suggested by the extraction agent");
  - APPROVED links -- taken from the decision log, the governed record of what the
    owner approved, each quoted from the first citation of the first proposal the
    decision cites. Measured 2026-09-24: the owner approved ADV-2026-0013::SAN001,
    which the advisory's merged record does not carry (it came from a later run's
    proposals). Building "approved" from the record would have hidden it.
  - APPROVED EMERGENT candidates under their own heading;
  - AWAITING REVIEW -- governed typologies the record asserts that have no
    standing decision.
Rejected links never appear. Undecided emergent entries do not appear.

Deterministic: nothing reads the clock; the only dates are the batch id and the
decision dates, which are data. The same inputs give the same bytes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from governance.proposals import ROOT, link_key
from governance.routing import desks_in_order, route

RECORDS_DIR = ROOT / "data" / "records_merged"
DIGESTS_DIR = ROOT / "data" / "digests"
NO_ADVISORIES = "No advisory in this batch routes to this desk."


def _visible(decision) -> bool:
    return decision.decision == "approve"


def _quote(decision, proposals_by_id) -> Optional[Tuple[int, str]]:
    for pid in decision.proposal_ids:
        p = proposals_by_id.get(pid)
        if p is not None and p.citations:
            page, quote = p.citations[0]
            return page, " ".join(str(quote).split())
    return None


def _cite(decision, proposals_by_id) -> str:
    q = _quote(decision, proposals_by_id)
    return (' -- p%d: "%s"' % q) if q else " -- (quote not found in the proposal queue)"


def render_desk(desk: str, batch_id: str, entries: List[tuple], n_records: int, library: dict, routing: dict,
                standing: dict, proposals_by_id: dict, advisories: dict) -> str:
    titles = routing["desk_titles"]
    out = ["# %s -- digest, batch %s" % (titles[desk], batch_id), "",
           "Built from %d advisory records. Approvals are the owner's, from data/review_decisions.jsonl; "
           "routing is data/desk_routing.json." % n_records,
           "A family desk receives an advisory only when it carries a typology of that family; %s also take "
           "the extraction agent's own suggestion, and say so." % ", ".join(
               titles[d] for d in routing["suggestion_only_desks"]),
           ""]
    if not entries:
        return "\n".join(out + [NO_ADVISORIES, ""])
    for rec, reasons in entries:
        aid = rec["advisory_id"]
        a = advisories.get(aid, {})
        out += ["## %s -- %s" % (aid, a.get("title") or rec.get("source", {}).get("title", "(untitled)")), ""]
        if a.get("publisher"):
            out += ["Publisher: %s" % a["publisher"], ""]
        out += ["Routed here because: %s." % "; ".join(reasons), ""]
        mine = [d for d in standing.values() if d.advisory_id == aid]
        approved = sorted((d for d in mine if _visible(d) and d.kind == "governed"), key=lambda d: d.link_key)
        emergent = sorted((d for d in mine if _visible(d) and d.kind == "emergent"), key=lambda d: d.link_key)
        decided = {d.link_key for d in mine}
        awaiting = sorted({t["typology_id"] for t in rec.get("typologies", [])
                           if t.get("typology_id") and link_key(aid, t["typology_id"], None) not in decided})
        out += ["### Approved links", ""]
        out += (["- **%s %s**%s (approved %s)" % (d.typology_id, library.get(d.typology_id, {}).get("label", "?"),
                                                 _cite(d, proposals_by_id), d.decided_at[:10]) for d in approved]
                or ["- none yet"])
        out.append("")
        if emergent:
            out += ["### Approved emergent candidates", ""]
            out += ["- **%s**%s (approved %s)" % (d.emergent_label, _cite(d, proposals_by_id), d.decided_at[:10])
                    for d in emergent]
            out.append("")
        out += ["### Awaiting review", ""]
        out += (["- %s %s -- asserted by the pipeline, not yet decided"
                 % (tid, library.get(tid, {}).get("label", "?")) for tid in awaiting] or ["- nothing"])
        out.append("")
    return "\n".join(out)


def build_batch(batch_id: str, records: List[dict], library: dict, routing: dict, standing: dict,
                proposals_by_id: dict, advisories: dict) -> Dict[str, str]:
    """desk -> Markdown for every desk, in desk order."""
    by_desk: Dict[str, List[tuple]] = {d: [] for d in desks_in_order(routing)}
    for rec in sorted(records, key=lambda r: r["advisory_id"]):
        for desk, reasons in route(rec, library, routing).items():
            by_desk[desk].append((rec, reasons))
    return {desk: render_desk(desk, batch_id, entries, len(records), library, routing, standing,
                              proposals_by_id, advisories)
            for desk, entries in by_desk.items()}
