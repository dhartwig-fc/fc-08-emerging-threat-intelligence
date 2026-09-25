"""
Build (or check) the governed actor register from the golden labels.

Usage:
    python tools/build_actor_register.py           # write data/actor_register.json + _candidates.json
    python tools/build_actor_register.py --check   # fail if either differs from a fresh build

Identity is the owner's, so the builder merges only what needs no judgement:
  - an actor matching exactly ONE existing entry from OTHER advisories, on an exact
    normalised name or alias, merges into it;
  - matching NONE starts a new entry;
  - matching TWO OR MORE starts its own entry and is listed `ambiguous`. Measured: ADV-2026-0012
    labels IRGC-Qods Force with "IRGC" and "Islamic Revolutionary Guard Corps" as aliases,
    matching both of ADV-2026-0010's separate entries; merging into either would make the
    other answer to the wrong name;
  - two actors from the SAME advisory never merge -- the label counted them as two
    (`same advisory`);
  - different entries whose spellings reach containment >= SUGGEST_MIN are listed
    `similar names` with their score. Measured, most such pairs are different parties
    (National Iranian Oil vs Tanker Company, GCM vs Berelian Exchange).
Categories are classes, not parties, and are left out. Advisories are read in id order
and actors in label order, so ids are stable and a rebuild is byte-identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.actor_match import SUGGEST_MIN, containment, norm, tokens, variants_of  # noqa: E402

GOLDEN = ROOT / "evals" / "golden"
REGISTER = ROOT / "data" / "actor_register.json"
CANDIDATES = ROOT / "data" / "actor_register_candidates.json"


def load_labels(golden: Path = GOLDEN) -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(golden.glob("ADV-*.json"))]


def load_register(path: Path = REGISTER) -> list:
    return json.loads(path.read_text(encoding="utf-8"))["actors"]


def _aliases(name: str, spellings) -> list:
    """Every spelling other than the name, one per normalised form, sorted."""
    seen, out = {norm(name)}, []
    for v in sorted(spellings, key=lambda s: (norm(s), s)):
        if norm(v) not in seen:
            seen.add(norm(v))
            out.append(v)
    return out


def build_register(labels, merge_same_advisory: bool = False, merge_ambiguous: bool = False):
    entries, candidates, spellings = [], [], {}   # spellings: actor_id -> every spelling seen
    for label in sorted(labels, key=lambda r: r["advisory_id"]):
        aid = label["advisory_id"]
        for actor in label.get("actors", []):
            if actor.get("actor_type") == "category":
                continue
            mine = variants_of(actor)
            keys = {norm(v) for v in mine}
            hits = [e for e in entries if {norm(v) for v in spellings[e["actor_id"]]} & keys]
            same = [e for e in hits if any(n["advisory_id"] == aid for n in e["named_in"])]
            other = [e for e in hits if e not in same]
            for e in same:
                candidates.append({"reason": "same advisory", "advisory_id": aid, "actor": actor["name"],
                                   "entries": [e["actor_id"]], "score": None})
            if merge_same_advisory and same and not other:
                other, same = same, []
            if len(other) > 1 and not merge_ambiguous:
                candidates.append({"reason": "ambiguous", "advisory_id": aid, "actor": actor["name"],
                                   "entries": [e["actor_id"] for e in other], "score": None})
            if other and not same and (len(other) == 1 or merge_ambiguous):
                target = other[0]
                target["named_in"].append({"advisory_id": aid, "name_as_labelled": actor["name"]})
                spellings[target["actor_id"]].extend(mine)
                continue
            actor_id = "ACT-%04d" % (len(entries) + 1)
            entries.append({"actor_id": actor_id, "name": actor["name"], "actor_type": actor.get("actor_type"),
                            "aliases": [], "named_in": [{"advisory_id": aid, "name_as_labelled": actor["name"]}],
                            "entity_key": None})
            spellings[actor_id] = list(mine)
    for e in entries:
        e["aliases"] = _aliases(e["name"], spellings[e["actor_id"]])
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            s = max(containment(tokens(x), tokens(y))
                    for x in [a["name"]] + a["aliases"] for y in [b["name"]] + b["aliases"])
            if s >= SUGGEST_MIN:
                candidates.append({"reason": "similar names", "advisory_id": None,
                                   "actor": "%s / %s" % (a["name"], b["name"]),
                                   "entries": [a["actor_id"], b["actor_id"]], "score": round(s, 2)})
    return entries, candidates


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render(labels) -> tuple:
    entries, candidates = build_register(labels)
    note = ("Built from the golden labels by tools/build_actor_register.py. Merges only on exact normalised "
            "matches across advisories; everything needing judgement is in the candidates file. "
            "entity_key is empty: the estate it would link to is synthetic.")
    return (_dump({"note": note, "actors": entries}),
            _dump({"note": "For the owner to decide. Nothing here is merged.", "candidates": candidates}))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build or check the actor register")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    reg, cand = render(load_labels())
    if args.check:
        bad = [p.name for p, t in ((REGISTER, reg), (CANDIDATES, cand))
               if not p.exists() or p.read_text(encoding="utf-8") != t]
        for n in bad:
            print("FAIL  %s differs from a fresh build" % n)
        print("register matches a fresh build" if not bad else "register does NOT match a fresh build")
        return 1 if bad else 0
    REGISTER.write_text(reg, encoding="utf-8")
    CANDIDATES.write_text(cand, encoding="utf-8")
    entries = json.loads(reg)["actors"]
    reasons = {}
    for c in json.loads(cand)["candidates"]:
        reasons[c["reason"]] = reasons.get(c["reason"], 0) + 1
    print("wrote %d register entries (%d merged across advisories); candidates %s"
          % (len(entries), sum(1 for e in entries if len(e["named_in"]) > 1), reasons))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
