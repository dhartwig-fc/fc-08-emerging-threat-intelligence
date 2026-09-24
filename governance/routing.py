"""
Which desks an advisory reaches, and why -- decided from data/desk_routing.json.

Measured 2026-09-24: the extraction agent's own suggested_desks is too broad to
route on (sanctions desk suggested on 17 of 20 advisories, backed by a sanctions
typology on 11). So a FAMILY desk receives an advisory only when the record
carries a governed typology of that family, and the reason names it. The desks no
family points at (fraud, general intel) and FIU liaison also take the agent's
suggestion, and the reason says it was a suggestion, so a reader can weigh it.

The table is data (guardrail 3's rule, carried over from fc-10): code names a
family in order to look it up, never to decide what a desk receives.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from governance.proposals import ROOT

ROUTING = ROOT / "data" / "desk_routing.json"
SUGGESTED = "suggested by the extraction agent"


def load_routing(path: Path = ROUTING) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def desks_in_order(routing: dict) -> List[str]:
    return list(routing["desk_titles"])


def route(record: dict, library: Dict[str, dict], routing: dict) -> Dict[str, List[str]]:
    """desk -> sorted reasons, in desk order. An advisory reaching no desk returns {}."""
    reasons: Dict[str, set] = {}
    for t in record.get("typologies", []):
        tid = t.get("typology_id")
        if not tid or tid not in library:
            continue
        family = library[tid].get("family")
        desk = routing["family_desks"].get(family)
        if desk:
            reasons.setdefault(desk, set()).add("%s %s (%s)" % (tid, library[tid].get("label", "?"), family))
    for desk in record.get("suggested_desks", []):
        if desk in routing["suggestion_only_desks"]:
            reasons.setdefault(desk, set()).add(SUGGESTED)
    return {d: sorted(reasons[d]) for d in desks_in_order(routing) if d in reasons}
