"""
Name normalising and matching shared by the scorer (evals/score.py) and the actor
resolver (knowledge_centre_resolve_actor). One normaliser, two questions:

  scoring   is this the actor I labelled in THIS advisory? Containment over the shorter
            token set is right there -- the candidates are a handful from one document.
  identity  which party is this, across every advisory? Containment is WRONG there, and
            measured so: "Iran" is wholly contained in "Islamic Republic of Iran Shipping
            Lines". So the resolver resolves on an EXACT normalised name or alias only;
            containment >= SUGGEST_MIN produces suggestions for a human, never a resolution.

The scorer's thresholds stay in evals/score.py: they are scoring constants.
"""

from __future__ import annotations

import re
from typing import List

# Dropped before token comparison: grammatical words only.
#
# Corporate suffixes are DELIBERATELY NOT dropped, and this was measured. An
# earlier version stripped ltd/llc/dmcc/pte and friends so that "2Rivers DMCC"
# would match a bare "2Rivers". It also made "2Rivers DMCC" and "2Rivers PTE"
# score 1.00 — two different companies on the blue side of the shadow fleet
# network (ADV-2026-0017), scored as one actor. Keeping the suffix as a token
# separates them (0.50, below threshold) while containment still matches the
# bare short form (1.00) and survives Ltd/Limited spelling drift (0.67).
_STOP = frozenset(
    "the and of a an to in for by with on or as is are that this these those their its from at "
    "into through via use used using such other another one two both all any each more most".split()
)


def norm(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("&", " and ").replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> frozenset:
    return frozenset(w for w in norm(text).split() if w not in _STOP and len(w) > 2)


def containment(a: frozenset, b: frozenset) -> float:
    """Overlap over the SHORTER set, so a long restatement still matches a short one."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# Containment at or above this is shown to a human as a SUGGESTION. It is not an
# identity threshold: measured 2026-09-25, four of five containment-only matches at
# this level named the wrong party.
SUGGEST_MIN = 0.60


def variants_of(actor: dict) -> List[str]:
    """Every spelling an actor answers to: its name, then its aliases, blanks dropped."""
    return [v for v in [actor.get("name", "")] + list(actor.get("aliases") or []) if v and norm(v)]


def resolve(names, actor_type, register, allow_category: bool = False, suggestions_resolve: bool = False) -> dict:
    """Which register entry these spellings name, decided on EXACT normalised matches only.

    Two entries matching is `ambiguous`, never a guess. No exact match is `unresolved`, with
    up to three containment suggestions a human must confirm. A category is a class of
    actor, not a party, and never resolves.
    """
    if actor_type == "category" and not allow_category:
        return {"status": "category"}
    keys = {norm(n) for n in names if norm(n)}
    exact = []
    for e in register:
        hit = next((s for s in [e["name"]] + list(e.get("aliases") or []) if norm(s) in keys), None)
        if hit is not None:
            exact.append((e, hit))
    if len(exact) == 1:
        e, hit = exact[0]
        return {"status": "resolved", "actor_id": e["actor_id"], "name": e["name"], "matched": hit}
    if len(exact) > 1:
        return {"status": "ambiguous", "entries": [{"actor_id": e["actor_id"], "name": e["name"]} for e, _ in exact]}
    scored = []
    for e in register:
        spellings = [e["name"]] + list(e.get("aliases") or [])
        s = max((containment(tokens(a), tokens(b)) for a in names for b in spellings), default=0.0)
        if s >= SUGGEST_MIN:
            scored.append((s, e))
    # Ties keep REGISTER order (creation order): a stable sort on score alone. Ids are
    # content hashes since week 6.1, so breaking ties on the id would order them at random.
    scored.sort(key=lambda p: -p[0])
    suggestions = [{"actor_id": e["actor_id"], "name": e["name"], "score": round(s, 2)} for s, e in scored[:3]]
    if suggestions_resolve and suggestions:
        top = suggestions[0]
        return {"status": "resolved", "actor_id": top["actor_id"], "name": top["name"], "matched": None}
    return {"status": "unresolved", "suggestions": suggestions}
