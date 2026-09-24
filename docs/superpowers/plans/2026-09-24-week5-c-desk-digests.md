# Week 5 sub-project C: desk digests — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One deterministic Markdown digest per desk per batch, routed by typology family from a data table, showing each routed advisory's owner-approved links (quoted from the proposal the owner decided on) apart from what still awaits review.

**Architecture:** `data/desk_routing.json` holds the routing table and desk titles (data, not code). `governance/routing.py` decides which desks an advisory reaches and why. `governance/digest.py` renders one desk's digest from records, the decision log and the proposal queue. `tools/build_digests.py` writes a batch and `--check`s a committed one. Nothing reads the clock: the same inputs give the same bytes.

**Tech Stack:** Python 3.14 in `.venv/`; stdlib only on top of the existing `governance/` package. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-week5-governance-design.md`, Section 4 — amended by Task 3 of this plan (see "One change from the spec" below).

## Global Constraints

- Repository: `~/fc-08-emerging-threat-intelligence`, branch `main`. Bash `cd` does not persist between tool calls: start commands with `cd ~/fc-08-emerging-threat-intelligence && `. Python is `.venv/bin/python`.
- No new dependencies. No pytest: guards are scripts under `evals/` printing `PASS`/`FAIL` per check, ending `HELD (0 failures)`, with `--mutate` to prove they can fail. Follow `evals/check_added_by.py`.
- Mutation runs use their own bytecode cache: `PYTHONPYCACHEPREFIX=/tmp/fc08-mut-<label>`.
- Routing table (spec Section 4, owner decision 2026-09-24): `tbml -> trade_desk`, `sanctions -> sanctions_desk`, `correspondent_banking -> correspondent_desk`, `capital_markets -> markets_desk`, `network -> fiu_liaison`. `fraud_desk`, `fiu_liaison`, `general_intel` also take the agent's own `suggested_desks`.
- A family desk receives an advisory ONLY when it carries a governed typology of that family; a suggestion alone is not enough.
- Rejected links never appear. Undecided emergent entries do not appear; approved emergent candidates appear under their own heading.
- Deterministic: sorted everywhere; no timestamps except the batch id and the decision dates that are themselves data; a rebuild is byte-identical.
- No live model runs. Never run `tools/review.py` except `--list`/`--check`; the owner decides links.
- Never write into `data/records/`, `data/records_merged/`, `data/proposals.jsonl`, `data/review_decisions.jsonl`.
- Never create `.bak`/`_backup`/`_before_*` files. Commits on fc-08 `main`, no `Co-Authored-By` trailer, not pushed by the implementer.

## One change from the spec, made while planning

Measured 2026-09-24: the owner approved `ADV-2026-0013::SAN001`, but `data/records_merged/ADV-2026-0013.json` does not carry SAN001 — it came from the week 5 live run's proposals. The spec built each advisory's digest from its record's typologies and looked each up in the decision log, so an owner-approved link absent from the record would appear in NO digest. So: **the Approved section comes from the decision log** (the governed record of approval), each quoted from the first citation of the first proposal the decision cites; **Awaiting review comes from the record** (typologies the pipeline asserted with no standing decision). Routing still uses the record's typologies. Task 3 writes this into the spec.

---

## File structure

| Path | Status | Responsibility |
|---|---|---|
| `data/desk_routing.json` | create | the routing table, the suggestion-only desks, the desk titles (in `Desk` enum order) |
| `governance/routing.py` | create | `load_routing`, `desks_in_order`, `route(record, library, routing)` |
| `governance/digest.py` | create | render one desk's digest; `build_batch` |
| `tools/build_digests.py` | create | CLI: write `data/digests/<batch_id>/<desk>.md`, or `--check` them |
| `evals/check_digest_routing.py` | create | guard for routing and digests, grown across Tasks 1-2 |
| `data/digests/slice1-2026-09-24/*.md` | created by Task 3 | the first committed batch |
| `docs/superpowers/specs/2026-09-24-week5-governance-design.md`, `CLAUDE.md` | modify (Task 3) | the amendment; layout and week 5 status |

---

### Task 1: The routing table and the rule

**Files:**
- Create: `data/desk_routing.json`, `governance/routing.py`, `evals/check_digest_routing.py`

**Interfaces:**
- Consumes: `schemas.advisory.Desk` (enum; values `trade_desk, sanctions_desk, correspondent_desk, markets_desk, fraud_desk, fiu_liaison, general_intel`); `governance.proposals.ROOT`.
- Produces: `governance.routing.ROUTING: Path`; `SUGGESTED = "suggested by the extraction agent"`; `load_routing(path=ROUTING) -> dict` with keys `family_desks: dict[str, str]`, `suggestion_only_desks: list[str]`, `desk_titles: dict[str, str]`; `desks_in_order(routing) -> list[str]`; `route(record: dict, library: dict[str, dict], routing: dict) -> dict[str, list[str]]` (desk -> sorted reasons; desks in `desks_in_order` order; `{}` when nothing routes).

- [ ] **Step 1: Write the failing guard `evals/check_digest_routing.py`**

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_digest_routing.py`
Expected: `ImportError: cannot import name 'routing' from 'governance'`.

- [ ] **Step 3: Create `data/desk_routing.json`**

```json
{
  "note": "Desk routing for digests. Data, not code: a family desk receives an advisory only when it carries a governed typology of that family; the suggestion-only desks also take the extraction agent's suggested_desks. network -> fiu_liaison was an owner decision on 2026-09-24. desk_titles lists every Desk in schemas.advisory enum order.",
  "family_desks": {
    "tbml": "trade_desk",
    "sanctions": "sanctions_desk",
    "correspondent_banking": "correspondent_desk",
    "capital_markets": "markets_desk",
    "network": "fiu_liaison"
  },
  "suggestion_only_desks": ["fraud_desk", "fiu_liaison", "general_intel"],
  "desk_titles": {
    "trade_desk": "Trade desk",
    "sanctions_desk": "Sanctions desk",
    "correspondent_desk": "Correspondent banking desk",
    "markets_desk": "Markets desk",
    "fraud_desk": "Fraud desk",
    "fiu_liaison": "FIU liaison",
    "general_intel": "General intelligence"
  }
}
```

- [ ] **Step 4: Create `governance/routing.py`**

```python
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
```

- [ ] **Step 5: Run the guard and its mutation**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_digest_routing.py; echo "exit=$?"
PYTHONPYCACHEPREFIX=/tmp/fc08-mut-dig-sugg .venv/bin/python evals/check_digest_routing.py --mutate suggestion; echo "exit=$?"
```
Expected: 9 PASS, `HELD (0 failures)`, exit 0. The mutation fails the "family desk SUGGESTED without a typology … does NOT receive" check and ends `HELD: the probe detects the defect when the rule is removed`, exit 0.

- [ ] **Step 6: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add data/desk_routing.json governance/routing.py evals/check_digest_routing.py && git commit -m "Week 5 C1: desk routing -- a family desk needs a typology of its family

data/desk_routing.json holds the table (network -> FIU liaison, owner
decision 2026-09-24) and the desk titles; governance/routing.py routes
an advisory and names why. A family desk suggested by the agent without
a typology of its family does not receive the advisory; fraud, FIU
liaison and general intel also take the suggestion, and say so.

evals/check_digest_routing.py: 9 checks incl. every family routed and
every desk reachable; mutation-verified."
```

---

### Task 2: The digest and the batch builder

**Files:**
- Create: `governance/digest.py`, `tools/build_digests.py`
- Modify: `evals/check_digest_routing.py` (imports; add `decision`, `digest_checks`, `real_checks`; extend `all_checks`; add a mutation)

**Interfaces:**
- Consumes: `governance.routing` (Task 1); `governance.proposals`: `ROOT`, `ADVISORY_LIST`, `LIBRARY`, `link_key(advisory_id, typology_id, emergent_label) -> str`, `load_queue(queue_dir=QUEUE_DIR) -> (proposals, skipped)` (each proposal has `.proposal_id` and `.citations: tuple[tuple[int, str], ...]`); `governance.decisions`: `load_log()`, `latest(decisions) -> dict[link_key, Decision]`, `Decision` (dataclass; fields `decided_at, link_key, kind, advisory_id, typology_id, emergent_label, decision, note, proposal_ids, run_ids, quotes_seen_sha256`).
- Produces: `governance.digest.RECORDS_DIR`, `DIGESTS_DIR`, `NO_ADVISORIES`; `_visible(decision) -> bool`; `render_desk(desk, batch_id, entries, n_records, library, routing, standing, proposals_by_id, advisories) -> str`; `build_batch(batch_id, records, library, routing, standing, proposals_by_id, advisories) -> dict[str, str]` (desk -> Markdown for all seven desks, in desk order); `tools/build_digests.py`: `build(batch_id, records_dir=RECORDS_DIR) -> dict[str, str]`; CLI `--batch-id ID [--records-dir DIR] [--out-dir DIR] [--check]`.

- [ ] **Step 1: Add the failing digest checks to `evals/check_digest_routing.py`.** Add `import dataclasses` and `from types import SimpleNamespace` to the imports, and after `from governance import routing as gr  # noqa: E402` add:

```python
from governance import decisions as gd  # noqa: E402
from governance import digest as dg  # noqa: E402
from governance.proposals import link_key  # noqa: E402
```

Add after `routing_checks`:

```python
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
    out.append((("**%s " % SAN) in san and 'p3: "a sanctioned party routed goods via a hub"' in san,
                "an approved link appears under Approved, quoted from the proposal the owner decided on", san[:160]))
    out.append(("REJECTED QUOTE" not in san and ("**%s " % TBML) not in san,
                "a rejected link never appears", ""))
    out.append((("**%s " % NET) in san and "the network quote for the absent link" in san,
                "an approved link the record does NOT carry still appears (the SAN001 case)", ""))
    out.append(("### Approved emergent candidates" in san and "Guard witness technique" in san,
                "an approved emergent candidate appears under its own heading", ""))

    extra = next(t for t, v in sorted(LIBRARY.items()) if v.get("family") == "sanctions" and t != SAN)
    undecided = record(aid, [SAN, TBML, NET, extra])
    san2 = dg.build_batch("guard-batch", [undecided], LIBRARY, routing, standing, props, advisories)["sanctions_desk"]
    awaiting = san2.split("### Awaiting review", 1)[1] if "### Awaiting review" in san2 else ""
    out.append((extra in awaiting and SAN not in awaiting and TBML not in awaiting and NET not in awaiting,
                "an asserted typology with no decision is listed under Awaiting review; decided ones are not",
                awaiting[:120]))

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
    batch = build_digests.build("guard-real")
    routed = [d for d, text in batch.items() if dg.NO_ADVISORIES not in text]
    out.append((len(routed) >= 3,
                "on the real records, at least three desks receive advisories (PLAN.md definition of done)",
                "desks with advisories: %s" % routed))
    san = batch.get("sanctions_desk", "")
    block = san.split("## ADV-2026-0013", 1)[1].split("\n## ", 1)[0] if "## ADV-2026-0013" in san else ""
    approved = block.split("### Approved links", 1)[1].split("###", 1)[0] if "### Approved links" in block else ""
    out.append(("SAN001" in approved and "SAN003" in approved,
                "the owner's ADV-2026-0013 approvals appear on the sanctions desk, SAN001 included", approved[:200]))
    return out
```

Replace `all_checks` with:

```python
def all_checks(routing: dict) -> list:
    return routing_checks(routing) + digest_checks(routing) + real_checks()
```

Change the `--mutate` choices to `("suggestion", "rejected")` and add after the `suggestion` branch:

```python
    elif args.mutate == "rejected":
        dg._visible = lambda d: True
        print("MUTATED: rejected links are shown as approved.\n")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_digest_routing.py`
Expected: `ImportError: cannot import name 'digest' from 'governance'`.

- [ ] **Step 3: Create `governance/digest.py`**

```python
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
```

- [ ] **Step 4: Create `tools/build_digests.py`**

```python
"""
Build (or check) one batch of desk digests.

Usage:
    python tools/build_digests.py --batch-id slice1-2026-09-24            # write data/digests/<batch_id>/<desk>.md
    python tools/build_digests.py --batch-id slice1-2026-09-24 --check    # fail if the committed files differ

A batch is a SNAPSHOT: the records, the decision log and the proposal queue as
they stood when it was built. A later decision does not change a committed batch;
build a new batch id for the new state. --check proves a committed batch still
matches what its inputs rebuild to -- it will fail after new decisions, which is
the signal to cut a new batch, not to edit the old one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance.digest import DIGESTS_DIR, NO_ADVISORIES, RECORDS_DIR, build_batch  # noqa: E402
from governance.proposals import ADVISORY_LIST, LIBRARY, load_queue  # noqa: E402
from governance.routing import load_routing  # noqa: E402

BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def build(batch_id: str, records_dir: Path = RECORDS_DIR) -> dict:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(records_dir.glob("ADV-*.json"))]
    library = {t["typology_id"]: t for t in json.loads(LIBRARY.read_text(encoding="utf-8"))["typologies"]}
    advisories = {a["advisory_id"]: a for a in json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    proposals, _ = load_queue()
    return build_batch(batch_id, records, library, load_routing(), gd.latest(gd.load_log()),
                       {p.proposal_id: p for p in proposals}, advisories)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build or check a batch of desk digests")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--records-dir", type=Path, default=RECORDS_DIR)
    ap.add_argument("--out-dir", type=Path, default=DIGESTS_DIR)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if not BATCH_ID.match(args.batch_id):
        print("batch id must match %s" % BATCH_ID.pattern, file=sys.stderr)
        return 2

    batch = build(args.batch_id, args.records_dir)
    folder = args.out_dir / args.batch_id
    if args.check:
        problems = []
        for desk, text in batch.items():
            path = folder / ("%s.md" % desk)
            if not path.exists():
                problems.append("%s is missing" % path.name)
            elif path.read_text(encoding="utf-8") != text:
                problems.append("%s differs from a fresh build" % path.name)
        extra = sorted(p.name for p in folder.glob("*.md") if p.stem not in batch) if folder.exists() else []
        problems += ["%s is not a desk in this batch" % n for n in extra]
        for p in problems:
            print("FAIL  %s" % p)
        print("batch %s matches a fresh build" % args.batch_id if not problems
              else "batch %s does NOT match a fresh build" % args.batch_id)
        return 1 if problems else 0

    folder.mkdir(parents=True, exist_ok=True)
    for desk, text in batch.items():
        (folder / ("%s.md" % desk)).write_text(text, encoding="utf-8")
    routed = sum(1 for t in batch.values() if NO_ADVISORIES not in t)
    print("wrote %d digests to %s (%d desks receive advisories)" % (len(batch), folder, routed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run the guard and both mutations**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python evals/check_digest_routing.py; echo "exit=$?"
for m in suggestion rejected; do printf "%-11s" $m; PYTHONPYCACHEPREFIX=/tmp/fc08-mut-dig-$m .venv/bin/python evals/check_digest_routing.py --mutate $m | tail -1; done
git status --short data/ | head
```
Expected: 18 PASS, `HELD (0 failures)`, exit 0. Each mutation ends `HELD: the probe detects the defect when the rule is removed`; `rejected` must fail "a rejected link never appears". `git status` shows nothing under `data/` (the guard builds in memory). If a real-data check fails, report the actual desks and section text — do not weaken it.

- [ ] **Step 6: Commit**

```bash
cd ~/fc-08-emerging-threat-intelligence && git add governance/digest.py tools/build_digests.py evals/check_digest_routing.py && git commit -m "Week 5 C2: desk digests -- approvals from the log, awaiting review from the record

governance/digest.py renders one digest per desk: why each advisory was
routed, the owner's approved links quoted from the proposal they decided
on, approved emergent candidates, and what the pipeline asserted that is
still undecided. Rejected links never appear. Approvals come from the
decision log because the owner approved ADV-2026-0013::SAN001, which the
merged record does not carry. tools/build_digests.py writes a batch and
--check proves a committed one still rebuilds identically.

check_digest_routing.py: 18 checks incl. the SAN001 case on the real
data and >= 3 desks receiving advisories; mutation-verified two ways."
```

---

### Task 3: The first batch, and the record

**Files:**
- Create (by the builder): `data/digests/slice1-2026-09-24/*.md` (seven files)
- Modify: `docs/superpowers/specs/2026-09-24-week5-governance-design.md` (Section 4), `CLAUDE.md` (Layout; week 5 entry)

**Interfaces:** none new.

- [ ] **Step 1: Build and check the batch**

```bash
cd ~/fc-08-emerging-threat-intelligence && .venv/bin/python tools/build_digests.py --batch-id slice1-2026-09-24; echo "exit=$?"
.venv/bin/python tools/build_digests.py --batch-id slice1-2026-09-24 --check; echo "exit=$?"
ls data/digests/slice1-2026-09-24/ && grep -c "^## ADV-" data/digests/slice1-2026-09-24/*.md
sed -n '/## ADV-2026-0013/,/### Awaiting review/p' data/digests/slice1-2026-09-24/sanctions_desk.md
```
Expected: `wrote 7 digests … (N desks receive advisories)` with N >= 3; `--check` prints `batch slice1-2026-09-24 matches a fresh build`, exit 0; seven `.md` files; the ADV-2026-0013 block on the sanctions desk lists SAN001, SAN003, SAN004 and SAN007 under Approved links, each with a page and quote. Record N and the per-desk advisory counts for the commit message.

- [ ] **Step 2: Amend the spec.** In `docs/superpowers/specs/2026-09-24-week5-governance-design.md`, Section 4, directly after the paragraph under `### Content`, append:

```markdown
**Amended while planning, 2026-09-24: approvals come from the decision log.**
Measured: the owner approved `ADV-2026-0013::SAN001`, which
`data/records_merged/ADV-2026-0013.json` does not carry -- it came from the week 5
live run's proposals. Looking decisions up per record typology would have put an
owner-approved link in no digest. So the Approved section is built from the
decision log (the governed record of approval), each link quoted from the first
citation of the first proposal the decision cites; Awaiting review stays built
from the record; routing still uses the record's typologies. Desk titles live in
`data/desk_routing.json` with the table. Every desk gets a file each batch, saying
so when nothing routes to it. A batch is a snapshot: `tools/build_digests.py
--check` fails after later decisions, which means cut a new batch id, never edit
the old one.
```

- [ ] **Step 3: Update `CLAUDE.md`.** In the `## Layout` block, after the `evals/check_telemetry.py` line, add:

```
data/desk_routing.json             desk routing as DATA: family -> desk (network -> FIU liaison), suggestion-only desks, desk titles
governance/routing.py              which desks an advisory reaches and why; a family desk needs a typology of its family
governance/digest.py               one Markdown digest per desk: approvals from the decision log, awaiting review from the record
tools/build_digests.py             writes data/digests/<batch_id>/<desk>.md; --check proves a committed batch rebuilds identically
data/digests/                      committed digest batches (snapshots; a new state is a new batch id)
evals/check_digest_routing.py      routing + digests, incl. the SAN001 case on real data; --mutate suggestion|rejected
```

In the week 5 entry, replace the line `  NEXT: sub-project C (desk digests; `network` routes to FIU liaison), then week 6.` with (replacing `<N>` with Step 1's count):

```
  **Sub-project C DONE** (plan `docs/superpowers/plans/2026-09-24-week5-c-desk-digests.md`): one
  digest per desk per batch, routed by typology family from `data/desk_routing.json` (a suggestion
  alone never reaches a family desk). First batch `data/digests/slice1-2026-09-24/`: <N> of 7 desks
  receive advisories. Planning found that building "approved" from the records would have hidden an
  owner approval the record does not carry (ADV-2026-0013::SAN001), so approvals come from the
  decision log. **Week 5's four PLAN.md items are delivered**: provenance on every proposal, a human
  gate before every write, telemetry for every decision, desk-routed digests. NEXT: week 6 (publish
  slice 1, tag `fc08-threatintel-slice1-v1.0.0`), with the items deferred to it above.
```

And change the week 5 line's box from `- [~] **Week 5**` to `- [x] **Week 5**`.

- [ ] **Step 4: Run every guard once**

```bash
cd ~/fc-08-emerging-threat-intelligence && for g in check_digest_routing check_tool_surface check_telemetry check_added_by check_twin_pairs check_emergent_threshold check_proposal_contract check_review_gate; do printf "%-26s" $g; .venv/bin/python evals/$g.py > /tmp/fc08-g.out 2>&1; echo "exit=$? $(tail -1 /tmp/fc08-g.out)"; done; .venv/bin/python tools/review.py --check | tail -1
```
Expected: eight `exit=0 HELD (0 failures)`; the `--check` line reports the approvals match the log.

- [ ] **Step 5: Commit.** Replace `<N>` and `<per-desk counts>` with Step 1's numbers.

```bash
cd ~/fc-08-emerging-threat-intelligence && git add data/digests/slice1-2026-09-24/ docs/superpowers/specs/2026-09-24-week5-governance-design.md CLAUDE.md && git status --short && git commit -m "Week 5 C3: the first digest batch, and week 5 closed

data/digests/slice1-2026-09-24/: seven desk digests, <N> receiving
advisories (<per-desk counts>). --check: the batch matches a fresh build.
Spec Section 4 amended: approvals come from the decision log (the
ADV-2026-0013::SAN001 case). CLAUDE.md records sub-project C and marks
week 5 done."
```

---

## Self-review against the spec

| Spec requirement (Section 4) | Task |
|---|---|
| Routing table as data; network -> FIU liaison | 1 |
| Family desk only with a typology of its family; suggestion alone not enough | 1 |
| fraud / FIU liaison / general intel take suggestions, and the digest says so | 1 (reason text), 2 (header) |
| One Markdown file per desk per batch under `data/digests/<batch_id>/` | 2, 3 |
| Why each advisory was routed | 2 |
| Approved links with a quote and page; awaiting review separate; rejected never | 2 (approvals from the log, amended) |
| Approved emergent candidates under their own heading | 2 |
| Deterministic, byte-identical rebuild | 2 (guard), 3 (`--check`) |
| Guard: routing both ways, every desk reachable, every family routed, rebuild identical; mutation-verified | 1, 2 |
| At least three desks (PLAN.md definition of done) | 2 (real-data check), 3 |
