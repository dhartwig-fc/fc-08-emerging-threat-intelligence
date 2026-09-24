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

A desk sees only its own family's approved/awaiting entries -- measured, the
sanctions desk had been quoting BA005 (correspondent_banking) under a shared
advisory, exactly the cross-topic noise the routing table exists to keep off a
desk's plate. A desk reached only through the agent's suggestion has no family
of its own, so it sees the advisory's whole picture instead; other desks'
approvals are still named on a scoped desk, never quoted there. An owner-approved
governed link also routes its own advisory to that link's family desk even when
the merged record does not carry the typology (the SAN001 case) -- otherwise
scoping display by family would have scoped delivery the same way, and an
approval whose family the record lacks would reach no desk at all.

Deterministic: nothing reads the clock; the only dates are the batch id and the
decision dates, which are data. The same inputs give the same bytes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from governance.proposals import ROOT, link_key
from governance.routing import SUGGESTED, desks_in_order, route

RECORDS_DIR = ROOT / "data" / "records_merged"
DIGESTS_DIR = ROOT / "data" / "digests"
NO_ADVISORIES = "No advisory in this batch routes to this desk."


def _visible(decision) -> bool:
    return decision.decision == "approve"


def _in_scope(typology_id, desk: str, reasons, library: dict, routing: dict) -> bool:
    """True when desk should see typology_id's approved/awaiting entry.

    A desk reached only by the agent's suggestion (SUGGESTED in reasons) has no
    family of its own and sees everything; a family desk sees only its own
    family's typologies -- library.get(typology_id) may be missing (an unknown
    or emergent id), in which case it is never in scope for a family desk.
    """
    if SUGGESTED in reasons:
        return True
    family = library.get(typology_id, {}).get("family")
    return routing["family_desks"].get(family) == desk


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
           "Built from %d advisory records. Approvals are the owner's, from the decision log "
           "(tools/review.py); routing is data/desk_routing.json." % n_records,
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
        approved_all = sorted((d for d in mine if _visible(d) and d.kind == "governed"), key=lambda d: d.link_key)
        approved = [d for d in approved_all if _in_scope(d.typology_id, desk, reasons, library, routing)]
        elsewhere = sorted({d.typology_id for d in approved_all if d not in approved})
        emergent = sorted((d for d in mine if _visible(d) and d.kind == "emergent"), key=lambda d: d.link_key)
        decided = {d.link_key for d in mine}
        awaiting = sorted({t["typology_id"] for t in rec.get("typologies", [])
                           if t.get("typology_id") and link_key(aid, t["typology_id"], None) not in decided
                           and _in_scope(t["typology_id"], desk, reasons, library, routing)})
        out += ["### Approved links", ""]
        out += (["- **%s %s**%s (approved %s)" % (d.typology_id, library.get(d.typology_id, {}).get("label", "?"),
                                                 _cite(d, proposals_by_id), d.decided_at[:10]) for d in approved]
                or ["- none yet"])
        if elsewhere:
            out.append("- also approved on this advisory, for other desks: %s"
                       % ", ".join("%s %s" % (tid, library.get(tid, {}).get("label", "?")) for tid in elsewhere))
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


def _routing_view(rec: dict, standing: dict) -> dict:
    """rec, plus one typology_id per owner-approved governed decision the record lacks.

    Used for route() only, never for display: an approval whose family the
    record does not carry (the SAN001 case) must still route the advisory to
    that family's desk, or family-scoped display would also mean family-scoped
    delivery -- the approval would reach no desk at all.
    """
    aid = rec["advisory_id"]
    have = {t.get("typology_id") for t in rec.get("typologies", [])}
    extra = sorted({d.typology_id for d in standing.values()
                    if d.advisory_id == aid and d.kind == "governed" and _visible(d)
                    and d.typology_id not in have})
    if not extra:
        return rec
    view = dict(rec)
    view["typologies"] = list(rec.get("typologies", [])) + [{"typology_id": tid} for tid in extra]
    return view


def build_batch(batch_id: str, records: List[dict], library: dict, routing: dict, standing: dict,
                proposals_by_id: dict, advisories: dict) -> Dict[str, str]:
    """desk -> Markdown for every desk, in desk order."""
    by_desk: Dict[str, List[tuple]] = {d: [] for d in desks_in_order(routing)}
    for rec in sorted(records, key=lambda r: r["advisory_id"]):
        for desk, reasons in route(_routing_view(rec, standing), library, routing).items():
            by_desk[desk].append((rec, reasons))
    return {desk: render_desk(desk, batch_id, entries, len(records), library, routing, standing,
                              proposals_by_id, advisories)
            for desk, entries in by_desk.items()}
