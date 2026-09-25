"""
Pin desk routing and the digests built on it.

Usage:
    python evals/check_digest_routing.py
    python evals/check_digest_routing.py --mutate suggestion   # family desks take suggestions; checks MUST fail
    python evals/check_digest_routing.py --mutate rejected     # rejections neither hide nor unroute; MUST fail
    python evals/check_digest_routing.py --mutate scope        # every desk sees every family; MUST fail

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
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import routing as gr  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance import digest as dg  # noqa: E402
from governance.proposals import QUEUE_DIR, link_key, load_queue  # noqa: E402
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


def decision(**kw):
    """A Decision with every field defaulted, so the guard survives new fields."""
    base = {f.name: (() if f.name in ("proposal_ids", "run_ids", "quotes_seen_sha256") else "")
            for f in dataclasses.fields(gd.Decision)}
    base.update(kw)
    return gd.Decision(**base)


def digest_checks(routing: dict) -> list:
    out = []
    aid = "ADV-X-9"
    when = "2026-09-24T10:00:00+00:00"
    rec = record(aid, [SAN, TBML], desks=["general_intel"])
    approved = decision(decided_at=when, link_key=link_key(aid, SAN, None), kind="governed", advisory_id=aid,
                        typology_id=SAN, decision="approve", proposal_ids=("p-ok",))
    rejected = decision(decided_at=when, link_key=link_key(aid, TBML, None), kind="governed", advisory_id=aid,
                        typology_id=TBML, decision="reject", proposal_ids=("p-rej",))
    # Approved but NOT in the record: the SAN001 shape measured on ADV-2026-0013.
    absent = decision(decided_at=when, link_key=link_key(aid, NET, None), kind="governed", advisory_id=aid,
                      typology_id=NET, decision="approve", proposal_ids=("p-abs",))
    emergent = decision(decided_at=when, link_key=link_key(aid, None, "Guard witness technique"), kind="emergent",
                        advisory_id=aid, emergent_label="Guard witness technique", decision="approve",
                        proposal_ids=("p-em",))
    standing = {d.link_key: d for d in (approved, rejected, absent, emergent)}
    props = {"p-ok": SimpleNamespace(citations=((3, "a sanctioned party routed goods via a hub"),)),
             "p-rej": SimpleNamespace(citations=((4, "REJECTED QUOTE MUST NOT APPEAR"),)),
             "p-abs": SimpleNamespace(citations=((5, "the network quote for the absent link"),)),
             "p-em": SimpleNamespace(citations=((6, "the emergent quote"),))}
    advisories = {aid: {"title": "Guard advisory", "publisher": "Guard"}}

    batch = dg.build_batch("guard-batch", [rec], LIBRARY, routing, standing, props, advisories)
    san = batch["sanctions_desk"]
    fiu = batch["fiu_liaison"]
    gen = batch["general_intel"]
    trade = batch["trade_desk"]
    out.append((("**%s " % SAN) in san and 'p3: "a sanctioned party routed goods via a hub"' in san,
                "an approved link appears under Approved, quoted from the proposal the owner decided on", san[:160]))
    # Checked on EVERY desk: family scoping hides an out-of-scope typology for a reason that has
    # nothing to do with rejection, and a rejection now unroutes the advisory from its family desk,
    # so the one desk a rejected link could still surface on is a suggestion-routed one.
    out.append((all("REJECTED QUOTE" not in text and ("**%s " % TBML) not in text for text in batch.values()),
                "a rejected link never appears, on any desk", ""))
    # The reviewer's reproduction: TBML is this record's ONLY trade typology, and the owner rejected it.
    # Routing on it anyway put the advisory on the trade desk "because" of a link the owner refused.
    out.append((("## %s " % aid) not in trade and TBML not in trade,
                "an advisory whose only trade typology was rejected does not reach the trade desk at all",
                trade[:200]))
    label = "Routed here because: %s %s (%s; owner-approved, not in the record)" % (
        NET, LIBRARY[NET]["label"], LIBRARY[NET]["family"])
    out.append((("**%s " % NET) in fiu and "the network quote for the absent link" in fiu and label in fiu,
                "an approved link the record does NOT carry still appears (the SAN001 case), and the "
                "reason says the route came from the owner's approval, not the record", label))
    out.append(("### Approved emergent candidates" in san and "Guard witness technique" in san,
                "an approved emergent candidate appears under its own heading", ""))

    elsewhere = (san.split("also approved on this advisory, for other desks", 1)[1]
                if "also approved on this advisory, for other desks" in san else "")
    out.append((("**%s " % NET) not in san and "the network quote for the absent link" not in san
                and NET in elsewhere,
                "a family desk quotes only its own family's approvals; other desks' approvals are named, not quoted",
                elsewhere[:120]))
    out.append((("**%s " % SAN) in gen and ("**%s " % NET) in gen,
                "a desk reached by the agent's suggestion sees the whole advisory", gen[:200]))

    extra = next(t for t, v in sorted(LIBRARY.items()) if v.get("family") == "sanctions" and t != SAN)
    undecided = record(aid, [SAN, TBML, NET, extra])
    san2 = dg.build_batch("guard-batch", [undecided], LIBRARY, routing, standing, props, advisories)["sanctions_desk"]
    awaiting = san2.split("### Awaiting review", 1)[1] if "### Awaiting review" in san2 else ""
    out.append((extra in awaiting and SAN not in awaiting and TBML not in awaiting and NET not in awaiting,
                "an asserted typology with no decision is listed under Awaiting review; decided ones are not",
                awaiting[:120]))

    # The check above runs on the sanctions desk, where TBML is out of family scope anyway, so it
    # passed with rejections counted as undecided. This one runs where the rejected link IS in scope:
    # the trade desk, reached through a DIFFERENT, undecided trade typology.
    tbml2 = next(t for t, v in sorted(LIBRARY.items()) if v.get("family") == "tbml" and t != TBML)
    trade2 = dg.build_batch("guard-batch", [record(aid, [TBML, tbml2])], LIBRARY, routing, standing, props,
                            advisories)["trade_desk"]
    awaiting2 = trade2.split("### Awaiting review", 1)[1] if "### Awaiting review" in trade2 else ""
    out.append((tbml2 in awaiting2 and TBML not in awaiting2 and TBML not in trade2,
                "on the rejected link's own family desk, Awaiting review lists the undecided typology; the "
                "rejected one appears nowhere -- not awaiting, not approved, not as a reason", awaiting2[:160]))

    # A desk with ANY family reason is scoped to its families, even when the agent also suggested it:
    # the suggestion is the signal routing distrusts, so it must not widen what the desk is shown.
    fiu3 = dg.build_batch("guard-batch", [record(aid, [NET], desks=["fiu_liaison"])], LIBRARY, routing, standing,
                          props, advisories)["fiu_liaison"]
    out.append((("**%s " % NET) in fiu3 and ("**%s " % SAN) not in fiu3,
                "a desk reached by a family typology AND the agent's suggestion quotes only its own family",
                fiu3[:200]))

    out.append((dg.NO_ADVISORIES in batch["markets_desk"],
                "a desk nothing routes to still gets a file that says so", batch["markets_desk"][-80:]))
    again = dg.build_batch("guard-batch", [rec], LIBRARY, routing, standing, props, advisories)
    out.append((batch == again and list(batch) == gr.desks_in_order(routing),
                "a rebuild is byte-identical, with one digest per desk in desk order", str(list(batch))))
    return out


def real_checks() -> list:
    out = []
    sys.path.insert(0, str(ROOT / "tools"))
    import build_digests  # noqa: E402
    records, queue = build_digests._current_inputs(dg.RECORDS_DIR, QUEUE_DIR)
    batch, _ = build_digests.build("guard-real", records, queue, gd.LOG)
    routed = [d for d, text in batch.items() if dg.NO_ADVISORIES not in text]
    out.append((len(routed) >= 3,
                "on the real records, at least three desks receive advisories (PLAN.md definition of done)",
                "desks with advisories: %s" % routed))
    san = batch.get("sanctions_desk", "")
    block = san.split("## ADV-2026-0013", 1)[1].split("\n## ", 1)[0] if "## ADV-2026-0013" in san else ""
    approved = block.split("### Approved links", 1)[1].split("###", 1)[0] if "### Approved links" in block else ""
    out.append(("SAN001" in approved and "SAN003" in approved,
                "the owner's ADV-2026-0013 approvals appear on the sanctions desk, SAN001 included", approved[:200]))

    corr = batch.get("correspondent_desk", "")
    corr_block = (corr.split("## ADV-2026-0013", 1)[1].split("\n## ", 1)[0]
                 if "## ADV-2026-0013" in corr else "")
    out.append(("**BA005 " not in block and "**BA005 " in corr_block,
                "BA005 is not quoted on the sanctions desk but is on the correspondent desk",
                "sanctions block: %s | correspondent block: %s" % (block[:120], corr_block[:120])))

    # Invariants over the whole real batch, not one witness advisory. Scoping and routing now both
    # take decisions into account, so the failure to fear is an approval or a record falling between
    # desks -- present in the data, shown on no desk.
    records = sorted(p.stem for p in dg.RECORDS_DIR.glob("ADV-*.json"))
    standing = gd.latest(gd.load_log())
    proposals, _ = load_queue()
    props = {p.proposal_id: p for p in proposals}

    def blocks(aid):
        return [text.split("## %s " % aid, 1)[1].split("\n## ", 1)[0] for text in batch.values()
                if "## %s " % aid in text]

    approved = [d for d in sorted(standing.values(), key=lambda d: d.link_key)
                if d.decision == "approve" and d.advisory_id in records]
    lost = [d.link_key for d in approved
            if not any(("**%s" % (d.typology_id or d.emergent_label)) in b and dg._cite(d, props) in b
                       for b in blocks(d.advisory_id))]
    out.append((approved and not lost,
                "every standing approval for an advisory in the batch is quoted on at least one desk",
                "%d approvals; not quoted anywhere: %s" % (len(approved), lost)))
    unrouted = [aid for aid in records if not blocks(aid)]
    out.append((records and not unrouted, "every record in the batch reaches at least one desk",
                "%d records; reaching no desk: %s" % (len(records), unrouted)))
    return out


def all_checks(routing: dict) -> list:
    return routing_checks(routing) + digest_checks(routing) + real_checks()


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin desk routing and digests")
    ap.add_argument("--mutate", choices=("suggestion", "rejected", "scope"), help="break one rule; checks MUST fail")
    args = ap.parse_args(argv)

    routing = gr.load_routing()
    if args.mutate == "suggestion":
        routing = dict(routing, suggestion_only_desks=[d.value for d in Desk])
        print("MUTATED: every desk accepts the agent's suggestion.\n")
    elif args.mutate == "rejected":
        dg._visible = lambda d: True
        dg._rejected = lambda d: False
        print("MUTATED: rejected links are shown as approved, and still route their advisory.\n")
    elif args.mutate == "scope":
        dg._in_scope = lambda *a, **k: True
        print("MUTATED: desk scoping is off; every desk sees every family's approvals.\n")

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
