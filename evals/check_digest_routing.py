"""
Pin desk routing and the digests built on it.

Usage:
    python evals/check_digest_routing.py
    python evals/check_digest_routing.py --mutate suggestion   # family desks take suggestions; checks MUST fail

WHY. Measured 2026-09-24: the extraction agent's own suggested_desks named the
sanctions desk on 17 of 20 advisories and the correspondent desk on 15, so
routing on suggestions would send nearly everything everywhere. A family desk
therefore receives an advisory only when it carries a governed typology of that
family (data/desk_routing.json); fraud_desk, fiu_liaison and general_intel also
take the agent's suggestion, and the digest says so.

OFFLINE. Synthetic records over the REAL library drive the REAL routing table and
the real functions. No model, no PDF.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import routing as gr  # noqa: E402
from schemas.advisory import Desk  # noqa: E402

LIBRARY = {t["typology_id"]: t for t in
           json.loads((ROOT / "data" / "typologies.json").read_text(encoding="utf-8"))["typologies"]}
SAN = next(t for t, v in sorted(LIBRARY.items()) if v.get("family") == "sanctions")
NET = next(t for t, v in sorted(LIBRARY.items()) if v.get("family") == "network")
TBML = next(t for t, v in sorted(LIBRARY.items()) if v.get("family") == "tbml")


def record(aid: str, typology_ids=(), desks=(), emergent=()) -> dict:
    typs = [{"typology_id": t, "label": LIBRARY[t]["label"], "family": LIBRARY[t]["family"], "emergent": False,
             "confidence": "medium", "citations": [{"page": 1, "quote": "q"}]} for t in typology_ids]
    typs += [{"typology_id": None, "label": e, "family": None, "emergent": True, "confidence": "low",
              "citations": [{"page": 1, "quote": "q"}]} for e in emergent]
    return {"advisory_id": aid, "typologies": typs, "suggested_desks": list(desks)}


def routing_checks(routing: dict) -> list:
    out = []
    families = {v.get("family") for v in LIBRARY.values()}
    out.append((families <= set(routing["family_desks"]),
                "every family in the library has a desk in the routing table",
                "missing: %s" % sorted(families - set(routing["family_desks"]))))
    enum = [d.value for d in Desk]
    named = set(routing["family_desks"].values()) | set(routing["suggestion_only_desks"])
    out.append((named <= set(enum) and list(routing["desk_titles"]) == enum,
                "every desk the table names is a Desk value, and desk_titles lists all seven in enum order",
                str(list(routing["desk_titles"]))))
    out.append((set(enum) <= named, "every Desk is reachable by some route",
                "unreachable: %s" % sorted(set(enum) - named)))

    got = gr.route(record("ADV-X-1", [SAN]), LIBRARY, routing)
    out.append(("sanctions_desk" in got and SAN in " ".join(got["sanctions_desk"]),
                "a sanctions typology routes to the sanctions desk, naming the typology", str(got)))

    got = gr.route(record("ADV-X-2", [TBML], desks=["sanctions_desk", "correspondent_desk"]), LIBRARY, routing)
    out.append(("sanctions_desk" not in got and "correspondent_desk" not in got and "trade_desk" in got,
                "a family desk SUGGESTED without a typology of its family does NOT receive the advisory", str(got)))

    got = gr.route(record("ADV-X-3", [], desks=["fraud_desk", "general_intel"]), LIBRARY, routing)
    out.append((got.get("fraud_desk") == [gr.SUGGESTED] and "general_intel" in got,
                "fraud_desk and general_intel take the agent's suggestion, and the reason says so", str(got)))

    got = gr.route(record("ADV-X-4", [NET]), LIBRARY, routing)
    out.append(("fiu_liaison" in got, "a network typology routes to FIU liaison (owner decision 2026-09-24)",
                str(got)))

    got = gr.route(record("ADV-X-5", [], emergent=["Some new technique"]), LIBRARY, routing)
    out.append((got == {}, "an emergent entry routes nowhere by family", str(got)))

    got = gr.route(record("ADV-X-6", [SAN, TBML, NET], desks=["general_intel"]), LIBRARY, routing)
    out.append((list(got) == [d for d in gr.desks_in_order(routing) if d in got],
                "desks come back in enum order, so every build orders them the same way", str(list(got))))
    return out


def all_checks(routing: dict) -> list:
    return routing_checks(routing)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin desk routing and digests")
    ap.add_argument("--mutate", choices=("suggestion",), help="break one rule; checks MUST fail")
    args = ap.parse_args(argv)

    routing = gr.load_routing()
    if args.mutate == "suggestion":
        routing = dict(routing, suggestion_only_desks=[d.value for d in Desk])
        print("MUTATED: every desk accepts the agent's suggestion.\n")

    failures = 0
    for ok, label, detail in all_checks(routing):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
