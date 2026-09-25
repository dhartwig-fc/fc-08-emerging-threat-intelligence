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
    (`same advisory`). Decided against a SNAPSHOT of the register as it stood before
    the advisory: two actors of one advisory are BOTH blocked from merging if they
    share an exact key with each other, or if their snapshot hits share an entry --
    checked pairwise, so the rule cannot depend on which actor is labelled first;
  - different entries whose spellings reach containment >= SUGGEST_MIN are listed
    `similar names` with their score. Measured, most such pairs are different parties
    (National Iranian Oil vs Tanker Company, GCM vs Berelian Exchange).
Categories are classes, not parties, and are left out. Advisories are read in id order
and actors in label order, so the file lists entries in creation order and a rebuild is
byte-identical.

An id is derived from CONTENT, not position: "ACT-" + the first 10 hex of
sha256("<advisory that created the entry>|<norm(name as first labelled)>"). A positional
counter renumbered every later actor whenever one was inserted or split in an early
advisory; a content id changes only for the entry whose own creating label changed. Two
entries deriving one id raise rather than silently collide.
"""

from __future__ import annotations

import argparse
import hashlib
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


def actor_id_for(advisory_id: str, name: str) -> str:
    """The id of the entry created by `name` as first labelled in `advisory_id`."""
    return "ACT-" + hashlib.sha256(("%s|%s" % (advisory_id, norm(name))).encode("utf-8")).hexdigest()[:10]


def _aliases(name: str, spellings) -> list:
    """Every spelling other than the name, one per normalised form, sorted."""
    seen, out = {norm(name)}, []
    for v in sorted(spellings, key=lambda s: (norm(s), s)):
        if norm(v) not in seen:
            seen.add(norm(v))
            out.append(v)
    return out


def build_register(labels, merge_same_advisory: bool = False, merge_ambiguous: bool = False,
                   positional_ids: bool = False):
    entries, candidates, spellings = [], [], {}   # spellings: actor_id -> every spelling seen

    def new_id(aid: str, name: str) -> str:
        if positional_ids:
            # Mutation handle: the pre-fix positional counter, which renumbers every
            # later entry when an early advisory gains or splits an actor.
            return "ACT-%04d" % (len(entries) + 1)
        actor_id = actor_id_for(aid, name)
        if actor_id in spellings:
            raise ValueError("two register entries derive the id %s (%s, %r)" % (actor_id, aid, name))
        return actor_id

    for label in sorted(labels, key=lambda r: r["advisory_id"]):
        aid = label["advisory_id"]
        named = [a for a in label.get("actors", []) if a.get("actor_type") != "category"]

        if merge_same_advisory:
            # Mutation handle: the pre-fix sequential behaviour, with NO same-advisory
            # check at all -- each actor is matched against the LIVE register as it
            # grows within this advisory, so a constructed pair sharing an alias
            # merges into one entry rather than being blocked.
            for actor in named:
                mine = variants_of(actor)
                keys = {norm(v) for v in mine}
                hits = [e for e in entries if {norm(v) for v in spellings[e["actor_id"]]} & keys]
                if len(hits) > 1 and not merge_ambiguous:
                    candidates.append({"reason": "ambiguous", "advisory_id": aid, "actor": actor["name"],
                                       "entries": [e["actor_id"] for e in hits], "score": None})
                if hits and (len(hits) == 1 or merge_ambiguous):
                    target = hits[0]
                    target["named_in"].append({"advisory_id": aid, "name_as_labelled": actor["name"]})
                    spellings[target["actor_id"]].extend(mine)
                    continue
                actor_id = new_id(aid, actor["name"])
                entries.append({"actor_id": actor_id, "name": actor["name"], "actor_type": actor.get("actor_type"),
                                "aliases": [], "named_in": [{"advisory_id": aid, "name_as_labelled": actor["name"]}],
                                "entity_key": None})
                spellings[actor_id] = list(mine)
            continue

        # Decide this whole advisory against a SNAPSHOT of the register as it stood
        # before it, so which actor is labelled first cannot change what gets caught.
        snapshot = [(e["actor_id"], frozenset(norm(v) for v in spellings[e["actor_id"]])) for e in entries]
        variants = [variants_of(actor) for actor in named]
        actor_keys = [frozenset(norm(v) for v in mine) for mine in variants]
        actor_hits = [[eid for eid, ekeys in snapshot if ekeys & keys] for keys in actor_keys]

        blocked = set()
        for i in range(len(named)):
            for j in range(i + 1, len(named)):
                shared_hits = sorted(set(actor_hits[i]) & set(actor_hits[j]))
                if (actor_keys[i] & actor_keys[j]) or shared_hits:
                    blocked.update((i, j))
                    candidates.append({"reason": "same advisory", "advisory_id": aid,
                                       "actor": "%s / %s" % (named[i]["name"], named[j]["name"]),
                                       "entries": shared_hits, "score": None})

        for i, actor in enumerate(named):
            mine = variants[i]
            hits = [] if i in blocked else actor_hits[i]
            if len(hits) > 1:
                if merge_ambiguous:
                    target = next(e for e in entries if e["actor_id"] == hits[0])
                    target["named_in"].append({"advisory_id": aid, "name_as_labelled": actor["name"]})
                    spellings[target["actor_id"]].extend(mine)
                    continue
                candidates.append({"reason": "ambiguous", "advisory_id": aid, "actor": actor["name"],
                                   "entries": hits, "score": None})
            elif len(hits) == 1:
                target = next(e for e in entries if e["actor_id"] == hits[0])
                target["named_in"].append({"advisory_id": aid, "name_as_labelled": actor["name"]})
                spellings[target["actor_id"]].extend(mine)
                continue
            actor_id = new_id(aid, actor["name"])
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
