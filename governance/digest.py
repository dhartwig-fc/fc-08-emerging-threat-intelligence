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
desk's plate. A desk sees the advisory's WHOLE picture only when every reason it
was routed is the agent's suggestion: then it has no family of its own. A desk
with any family reason (FIU liaison via a network typology) stays scoped to its
families even if the agent also suggested it -- the suggestion is the signal
routing distrusts, so it must not widen what a desk is shown. Other desks'
approvals are named on a scoped desk, never quoted there.

Decisions change ROUTES, not only what a desk quotes. An owner-approved governed
link routes its advisory to that link's family desk even when the merged record
does not carry the typology (the SAN001 case), and the reason says so ("owner-
approved, not in the record") -- otherwise scoping display by family would have
scoped delivery the same way, and an approval whose family the record lacks
would reach no desk at all. A REJECTED typology stops routing: the reviewer
reproduced a record whose only trade typology the owner had rejected reaching
the trade desk "because" of that very typology, with nothing approved and
nothing awaiting beneath it.

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
APPROVED_NOT_IN_RECORD = "owner-approved, not in the record"


def _visible(decision) -> bool:
    return decision.decision == "approve"


def _rejected(decision) -> bool:
    """One place for "the owner refused this link", so routing and display cannot disagree about it."""
    return decision.decision == "reject"


def _in_scope(typology_id, desk: str, reasons, library: dict, routing: dict) -> bool:
    """True when desk should see typology_id's approved/awaiting entry.

    A desk whose EVERY reason is the agent's suggestion has no family of its own
    and sees everything. Any family reason scopes the desk to its families, even
    alongside a suggestion -- otherwise FIU liaison, reached by a network typology
    and also suggested, would quote sanctions approvals on the strength of the
    signal routing refuses to trust. library.get(typology_id) may be missing (an
    unknown or emergent id), in which case it is never in scope for a family desk.
    """
    if all(r == SUGGESTED for r in reasons):
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
           "This batch covers %d advisory records; %d reach this desk. Approvals are the owner's, from the "
           "decision log (tools/review.py); routing is data/desk_routing.json." % (n_records, len(entries)),
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


def _routing_view(rec: dict, standing: dict) -> Tuple[dict, List[str]]:
    """(rec without its owner-rejected typologies, the approved typology ids rec lacks).

    Used for routing only, never for display. A rejected typology must not route:
    the owner refused the link, so it cannot be the reason a desk receives the
    advisory. An approval whose family the record does not carry (the SAN001
    case) must still route the advisory to that family's desk, or family-scoped
    display would also mean family-scoped delivery -- the approval would reach
    no desk at all.
    """
    aid = rec["advisory_id"]
    mine = [d for d in standing.values() if d.advisory_id == aid and d.kind == "governed"]
    refused = {d.typology_id for d in mine if _rejected(d)}
    have = {t.get("typology_id") for t in rec.get("typologies", [])}
    extra = sorted({d.typology_id for d in mine if _visible(d) and d.typology_id not in have})
    view = dict(rec, typologies=[t for t in rec.get("typologies", []) if t.get("typology_id") not in refused])
    return view, extra


def _routes(rec: dict, standing: dict, library: dict, routing: dict) -> Dict[str, List[str]]:
    """desk -> sorted reasons, in desk order, for one record under the standing decisions.

    route() still decides every desk, including an approval-added one's (routed
    alone, so the table stays the only rule); only the reason is relabelled here,
    because "the owner approved it, the record does not carry it" is a digest
    fact routing.py knows nothing about. Record typologies keep route()'s wording.
    """
    view, extra = _routing_view(rec, standing)
    reasons = {desk: set(r) for desk, r in route(view, library, routing).items()}
    for tid in extra:
        for desk in route({"typologies": [{"typology_id": tid}]}, library, routing):
            reasons.setdefault(desk, set()).add("%s %s (%s; %s)" % (
                tid, library[tid].get("label", "?"), library[tid].get("family"), APPROVED_NOT_IN_RECORD))
    return {d: sorted(reasons[d]) for d in desks_in_order(routing) if d in reasons}


def build_batch(batch_id: str, records: List[dict], library: dict, routing: dict, standing: dict,
                proposals_by_id: dict, advisories: dict) -> Dict[str, str]:
    """desk -> Markdown for every desk, in desk order."""
    by_desk: Dict[str, List[tuple]] = {d: [] for d in desks_in_order(routing)}
    for rec in sorted(records, key=lambda r: r["advisory_id"]):
        for desk, reasons in _routes(rec, standing, library, routing).items():
            by_desk[desk].append((rec, reasons))
    return {desk: render_desk(desk, batch_id, entries, len(records), library, routing, standing,
                              proposals_by_id, advisories)
            for desk, entries in by_desk.items()}
