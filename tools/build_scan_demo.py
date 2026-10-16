"""
Build the public "regulatory intelligence scan" demo page: one real Friday run, replayed.

Usage:
    python tools/build_scan_demo.py            # write site/scan-demo/index.html
    python tools/build_scan_demo.py --check    # exit 1 if the committed page differs from a fresh build

WHAT IT SHOWS. The pinned run RUN_ID and the advisory it produced, ADVISORY: every listing the
orchestrator read, every notice it triaged with its verdict, reason and quote, what acceptance did with
each, the extracted advisory with its quoted indicators, the owner's typology decisions, the agents'
tool surface, the schedule, and the measured quality bands. A replay control steps through the run.

WHERE EVERY VALUE COMES FROM. Nothing on the page is typed here except presentation and the declared
cross-repository facts in FC10 (which evals/check_scan_demo.py checks against the portfolio's published
NEXUS case page when that checkout is present):
  run, listings, notices      data/feeds/runs/<RUN_ID>/run.json, items.json
  verdicts, reasons, quotes   the run's triage rows
  dispositions                the run's accepted.json -- accepted and deferred are named by item KEY,
                              dropped by item ID (two namespaces, measured 2026-10-14); every notice must
                              land in exactly one, or the build refuses
  citation check              the run's extraction-runs row (checked / off_page)
  advisory, indicators        data/feeds/records/<ADVISORY>.json
  owner decisions             the decision log rows whose advisory_id is ADVISORY
  coverage                    feeds.sources.SOURCES (live), tools/fetch_fatf_via_chrome.js (manual), and
                              schemas.advisory.SourceType for what is not yet scanned
  tool surface, model         agents.orchestrate_feeds and agents.extract_advisory constants
  schedule                    scripts/schedule/uk.fc08.friday-run.plist
  typology library            data/typologies.json
  extraction quality          evals/score_report.json totals.typologies
  triage band, reviewer R     the dated lines in CLAUDE.md that record them (parsed; a reworded line
                              refuses the build rather than going stale silently)

Cost is deliberately not shown (owner, 2026-10-14). Deterministic: no clock, no network, no git.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import plistlib
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from agents.extract_advisory import KC_TOOLS  # noqa: E402
from agents.orchestrate_feeds import MODEL, TRIAGE_TOOLS  # noqa: E402
from feeds.sources import SOURCES  # noqa: E402
from governance import decisions as gd  # noqa: E402
from schemas.advisory import SCHEMA_VERSION, SourceType  # noqa: E402

RUN_ID = "feeds-2026-10-11-e7ad24"
ADVISORY = "ADV-2026-0026"
RUN_DIR = ROOT / "data" / "feeds" / "runs" / RUN_ID
RECORD = ROOT / "data" / "feeds" / "records" / ("%s.json" % ADVISORY)
TYPOLOGIES = ROOT / "data" / "typologies.json"
SCORE_REPORT = ROOT / "evals" / "score_report.json"
CLAUDE_MD = ROOT / "CLAUDE.md"
PLIST = ROOT / "scripts" / "schedule" / "uk.fc08.friday-run.plist"
FATF_MANUAL = ROOT / "tools" / "fetch_fatf_via_chrome.js"
OUT = ROOT / "site" / "scan-demo" / "index.html"
PROPOSALS_IMPORT = ROOT / "data" / "typology_proposals.json"
IMPACT_IMPORT = ROOT / "data" / "advisory_impact.json"   # Stage566 K4b: fc-10's advisory impact, imported
# Stage565 S4 (spec §7.2, plan R21): the six steps from "the agent noticed something" to "NEXUS scores it".
# BUILT only when the named fc-08 files exist (evals/check_scan_demo.py checks); Build and Live happen in
# NEXUS, and fc-08 sees them through the imported proposals and the typology export.
PIPELINE = [
    {"n": 1, "name": "Spot", "actor": "AGENT", "built": True, "evidence": ["agents/extract_advisory.py"],
     "what": "The extraction agent reads an advisory, searches the typology library, and when nothing fits it "
             "proposes an emergent pattern, with the quotes it rests on."},
    {"n": 2, "name": "Decide", "actor": "PERSON", "built": True, "evidence": ["tools/review.py"],
     "what": "A person approves or rejects every emergent pattern in the review gate. A rejection is recorded "
             "with its reason; nothing the agent proposed counts until a person decides."},
    {"n": 3, "name": "Propose", "actor": "PERSON", "built": True,
     "evidence": ["tools/import_fc10_proposals.py", "mcp_server/knowledge_centre_server.py"],
     "what": "The owner opens a typology proposal in NEXUS from approved patterns. From then on the agents see "
             "it, and an advisory describing the same technique is linked to it as more evidence."},
    {"n": 4, "name": "Define", "actor": "PERSON", "built": True, "evidence": ["agents/draft_doctrine.py"],
     "what": "A drafting agent writes doctrine in which every statement cites the evidence; a person edits it, "
             "commits it to a toolkit and approves it. Only then does the technique get a typology id."},
    {"n": 5, "name": "Build", "actor": "NEXUS", "built": True, "evidence": ["tools/import_fc10_proposals.py"],
     "what": "Engineers build the detection engine, sample data and NEXUS integration by hand; NEXUS records the "
             "toolkit commit and refuses to call it live until a release passes."},
    {"n": 6, "name": "Live", "actor": "NEXUS", "built": True,
     "evidence": ["data/typologies.json", "mcp_server/knowledge_centre_server.py"],
     "what": "The typology is in the library the agents search, so the next advisory describing it is linked "
             "as a governed typology, not proposed as something new."},
]

# Source types that are not regulators or agencies: never shown as "not yet scanned".
NOT_A_FEED = ("industry", "press", "other")
DISPLAY = {"fincen": "FinCEN", "ofac": "OFAC", "ofsi": "OFSI", "fatf": "FATF", "fca": "FCA", "nca": "NCA",
           "europol": "Europol", "wolfsberg": "Wolfsberg"}
DAYS = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}

# The SAN006 indicator the advisory's network finding corroborates: must be one SAN006 actually lists.
CORROBORATES = ("SAN006", "Trading party owned by / linked to a designated party")

# Cross-repository facts: the NEXUS case NEXUS already manufactures for SAN006, as published. Declared, not
# read (fc-10 is another repository); evals/check_scan_demo.py checks them against the portfolio's copy.
FC10 = {
    "typology": "SAN006",
    "subject": "Global Metals Ltd",
    "case_id": "SAN006-TRD001",
    "run_id": "san006-ba55d5fa16",
    "case_page": "../investigation-cross-domain/products/SAN006.html",
    "doctrine_page": "../knowledge-centre/knowledge/SAN006.html",
}

TRIAGE_BAND = re.compile(r"The triage band, measured (\d{4}-\d\d-\d\d): recall ([\d.]+)-([\d.]+) \(mean [\d.]+\), "
                         r"precision ([\d.]+)-([\d.]+) \(mean [\d.]+\) over (\d+) items and (\w+) repeats")
REVIEWER = re.compile(r"FULL SET, all (\d+), (\d{4}-\d\d-\d\d): extraction P ([\d.]+) R ([\d.]+) F1 ([\d.]+) "
                      r"-> \+ reviewer P ([\d.]+) R ([\d.]+)")


def _jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def inputs() -> dict:
    """Everything the page is built from, read once. The guard perturbs a deep copy of this."""
    claude = CLAUDE_MD.read_text(encoding="utf-8")
    t, r = TRIAGE_BAND.search(claude), REVIEWER.search(claude)
    if not t or not r:
        raise SystemExit("REFUSED: CLAUDE.md no longer states the triage band or the reviewer figures in the "
                         "form this page parses; re-anchor TRIAGE_BAND / REVIEWER")
    plist = plistlib.loads(PLIST.read_bytes())
    when = plist["StartCalendarInterval"]
    return {
        "run": json.loads((RUN_DIR / "run.json").read_text(encoding="utf-8")),
        "items": json.loads((RUN_DIR / "items.json").read_text(encoding="utf-8")),
        "triage": _jsonl(RUN_DIR / "triage.jsonl"),
        "accepted": json.loads((RUN_DIR / "accepted.json").read_text(encoding="utf-8")),
        "extraction": [x for x in _jsonl(RUN_DIR / "extraction_runs.jsonl") if x.get("advisory_id") == ADVISORY],
        "record": json.loads(RECORD.read_text(encoding="utf-8")),
        "decisions": [d for d in _jsonl(gd.LOG) if d.get("advisory_id") == ADVISORY],
        "typologies": json.loads(TYPOLOGIES.read_text(encoding="utf-8"))["typologies"],
        "score": json.loads(SCORE_REPORT.read_text(encoding="utf-8"))["totals"]["typologies"],
        "triage_band": {"date": t.group(1), "recall": [t.group(2), t.group(3)], "precision": [t.group(4), t.group(5)],
                        "items": int(t.group(6)), "repeats": t.group(7)},
        "reviewer": {"advisories": int(r.group(1)), "date": r.group(2), "recall": r.group(7)},
        "live": sorted(SOURCES),
        "manual": ["fatf"] if FATF_MANUAL.exists() else [],
        "source_types": [s.value for s in SourceType],
        "model": MODEL,
        "triage_tools": list(TRIAGE_TOOLS),
        "kc_tools": list(KC_TOOLS),
        "schema_version": SCHEMA_VERSION,
        "schedule": {"day": DAYS[when["Weekday"]], "time": "%02d:%02d" % (when["Hour"], when.get("Minute", 0))},
        "log": _jsonl(gd.LOG),
        "proposals": json.loads(PROPOSALS_IMPORT.read_text(encoding="utf-8"))["proposals"],
        # K4b-R2: no import yet reads as an empty one -- the page then claims nothing was absorbed.
        "impact": (json.loads(IMPACT_IMPORT.read_text(encoding="utf-8")) if IMPACT_IMPORT.exists()
                   else {"typologies": {}}),
        "pipeline": copy.deepcopy(PIPELINE),
    }


def _duration(start: str, end: str) -> str:
    secs = int((datetime.fromisoformat(end.replace("Z", "+00:00"))
                - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
    return "%d min %02d s" % (secs // 60, secs % 60)


def _pipeline(inp: dict, links: list) -> dict:
    """The something-new section's data (Stage565 S4): counts from the decision log and the import; the example is
    the first open proposal or, while none is open, this advisory's decided emergent pattern."""
    latest = {}
    for d in inp["log"]:
        latest[d["link_key"]] = d
    em = [d for d in latest.values() if d.get("kind") == "emergent"]
    props = sorted(inp["proposals"], key=lambda p: p["proposal_id"])
    counts = {"emergent_decided": len(em), "emergent_approved": sum(d["decision"] == "approve" for d in em),
              "emergent_rejected": sum(d["decision"] == "reject" for d in em),
              "proposal_links_approved": sum(d.get("kind") == "proposal" and d["decision"] == "approve"
                                             for d in latest.values()),
              "open": len(props),
              "defining": sum(p["stage"] in ("doctrine_drafted", "doctrine_approved") for p in props),
              "building": sum(p["stage"] == "engine_built" for p in props)}
    if props:
        p = props[0]
        example = {"ref": p["proposal_id"], "kind": "proposal", "name": p["working_name"], "stage": p["stage"],
                   "advisories": sorted({e["advisory_id"] for e in p.get("evidence", [])})}
    else:
        em_links = [l for l in links if l["emergent"]]
        if not em_links:
            raise SystemExit("REFUSED: no open proposal and no decided emergent on %s to show as the example" % ADVISORY)
        l = em_links[0]
        example = {"ref": "%s::EMERGENT[%s]" % (ADVISORY, l["name"].lower()), "kind": "emergent", "name": l["name"],
                   "decision": l["decision"], "note": l["note"], "decided_on": l["decided_on"]}
    # The evidence paths stay here: they are repository paths, and the publish boundary keeps those off a public
    # page. The guard checks them against the same inputs the page is built from.
    steps = [{k: v for k, v in step.items() if k != "evidence"} for step in inp["pipeline"]]
    return {"headline": "The agent can only notice; a person defines.", "steps": steps,
            "counts": counts, "example": example}


def impact_view(impact: dict) -> dict:
    """What the Now block shows, from the imported advisory impact export alone (Stage566 K4b, spec §5.2)."""
    ts = impact.get("typologies") or {}
    corrs = [c for t in ts.values() for c in t.get("corroborations") or []]
    rrs = [r for t in ts.values() for r in t.get("rereviews") or []]
    mine = ts.get(CORROBORATES[0]) or {}
    mc = mine.get("corroborations") or []
    doc = next((c for c in mc if c["advisory_id"] == ADVISORY), mc[0] if mc else None)
    rr = (mine.get("rereviews") or [None])[0]
    return {
        "built": bool(mc),
        "absorbed_on": max((c["absorbed_at"][:10] for c in corrs), default=""),
        "corroborations": len(corrs),
        "typologies": sum(1 for t in ts.values() if t.get("corroborations")),
        "rereviews": len(rrs),
        "open": sum(r["status"] == "open" for r in rrs),
        "doctrine": {k: doc[k] for k in ("advisory_id", "publisher", "decided_at", "quotes")} if doc else None,
        "rereview": ({k: rr[k] for k in ("id", "subject", "case_id", "status", "outcome", "raised_at", "closed_at")}
                     if rr else None),
    }


def payload(inp: dict) -> dict:
    run, acc = inp["run"], inp["accepted"]
    by_key = {row["key"]: row for row in inp["triage"]}
    order = {row["key"]: i for i, row in enumerate(inp["triage"])}
    listings, notices = [], []
    for src in sorted(inp["items"]["sources"]):
        block = inp["items"]["sources"][src]
        listings.append({"source": DISPLAY.get(src, src), "listed": block["listed"],
                         "already_seen": block["already_seen"], "new": len(block["items"])})
        for it in block["items"]:
            key, dropped_as = it["key"], "%s:%s" % (src, it["item_id"])
            fates = [f for f, hit in (("accepted", key in acc["accepted"]), ("deferred", key in acc["deferred"]),
                                      ("dropped", dropped_as in acc["dropped"])) if hit]
            if len(fates) != 1:
                raise SystemExit("REFUSED: %s has %d dispositions in accepted.json, not 1" % (key, len(fates)))
            row = by_key.get(key)
            notices.append({
                "key": key, "source": DISPLAY.get(src, src), "published": it["published"], "title": it["title"],
                "url": it["url"], "verdict": row["verdict"] if row else None,
                "reason": row["reason"] if row else None, "quote": row["quote"] if row else None,
                "match": row["match"] if row else None, "fate": fates[0],
                "advisory": acc["accepted"].get(key),
            })
    notices.sort(key=lambda n: (order.get(n["key"], len(order)), n["key"]))

    ext = inp["extraction"]
    if len(ext) != 1:
        raise SystemExit("REFUSED: %d extraction rows for %s in %s, not 1" % (len(ext), ADVISORY, RUN_ID))
    rec = inp["record"]
    decided = {d["link_key"]: d for d in inp["decisions"]}
    links = []
    for t in rec["typologies"]:
        lk = ("%s::%s" % (ADVISORY, t["typology_id"]) if t["typology_id"]
              else "%s::EMERGENT[%s]" % (ADVISORY, t["label"].lower()))
        d = decided.get(lk)
        if d is None:
            raise SystemExit("REFUSED: no owner decision for %s" % lk)
        links.append({"id": t["typology_id"], "name": t["label"], "emergent": t["emergent"],
                      "decision": d["decision"], "note": d["note"], "decided_on": d["decided_at"][:10]})
    lib = {t["typology_id"]: t for t in inp["typologies"]}
    san = lib[CORROBORATES[0]]
    if CORROBORATES[1] not in san["indicators"]:
        raise SystemExit("REFUSED: %s no longer lists the indicator the page says it corroborates" % CORROBORATES[0])
    item = next(n for n in notices if n["advisory"] == ADVISORY)
    taken = set(inp["live"]) | set(inp["manual"]) | set(NOT_A_FEED)
    return {
        "run": {"id": RUN_ID, "model": run["model"], "started": run["started_at"], "ended": run["ended_at"],
                "duration": _duration(run["started_at"], run["ended_at"]), "status": acc["status"],
                "decided_on": acc["decided_on"]},
        "listings": listings,
        "notices": notices,
        "counts": {"listed": sum(x["listed"] for x in listings), "seen": sum(x["already_seen"] for x in listings),
                   "new": len(notices), "accepted": len(acc["accepted"]), "deferred": len(acc["deferred"]),
                   "dropped": len(acc["dropped"]), "triaged": sum(1 for n in notices if n["verdict"])},
        "extraction": {"checked": ext[0]["citation_check"]["checked"],
                       "off_page": ext[0]["citation_check"]["off_page"],
                       "repair_turns": ext[0]["quote_repair"]["repair_turns"]},
        "advisory": {"id": ADVISORY, "title": item["title"], "url": item["url"], "published": rec["source"]["published_on"],
                     "publisher": rec["source"]["publisher"],
                     "indicators": [{"type": i["indicator_type"], "description": i["description"],
                                     "quotes": [c["quote"] for c in i["citations"]],
                                     "detectable": i["detectable_in_transaction_data"]} for i in rec["indicators"]],
                     "desks": rec["suggested_desks"], "links": links},
        "corroborates": {"typology": CORROBORATES[0], "name": san["label"], "indicator": CORROBORATES[1]},
        "pipeline": _pipeline(inp, links),
        "fc10": FC10,
        "impact": impact_view(inp["impact"]),
        "coverage": {"live": [DISPLAY[s] for s in inp["live"]], "manual": [DISPLAY[s] for s in inp["manual"]],
                     "not_yet": [DISPLAY.get(s, s) for s in inp["source_types"] if s not in taken]},
        "agents": {"model": inp["model"], "triage_tools": inp["triage_tools"], "kc_tools": inp["kc_tools"],
                   "typologies": len(inp["typologies"]), "schema_version": inp["schema_version"],
                   "schedule": inp["schedule"]},
        "quality": {"triage": inp["triage_band"], "reviewer": inp["reviewer"],
                    "extraction": {"precision": "%.3f" % inp["score"]["precision"],
                                   "recall": "%.3f" % inp["score"]["recall"]}},
    }


def _fig_box(x: int, y: int, w: int, title: str, sub: str, cls: str = "") -> str:
    cx = x + w // 2
    return ('<rect class="%s" x="%d" y="%d" width="%d" height="56" rx="8"/>'
            '<text class="t" x="%d" y="%d" text-anchor="middle" dominant-baseline="central">%s</text>'
            '<text x="%d" y="%d" text-anchor="middle" dominant-baseline="central">%s</text>'
            % (cls, x, y, w, cx, y + 19, html.escape(title), cx, y + 38, html.escape(sub)))


def _fig_open(mid: str, height: int, title: str, desc: str) -> str:
    return ('<svg class="fig" viewBox="0 0 680 %d" role="img"><title>%s</title><desc>%s</desc>'
            '<defs><marker id="%s" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" '
            'orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="#8d9db3" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round"/></marker></defs>'
            % (height, html.escape(title), html.escape(desc), mid))


def two_paths_svg() -> str:
    """The fork after a person's decision: a link to a known typology, or a pattern that matches nothing.
    The known path is absorbed into NEXUS (Stage566 K4b): corroboration and a product re-review."""
    arr = ' class="arr" marker-end="url(#figA)"'
    parts = [_fig_open("figA", 580, "After a person decides: two paths",
                       "A scan reads advisories, an agent proposes links, a person reviews each one. A link to a "
                       "known typology is routed to its desk; a pattern matching nothing becomes a typology "
                       "proposal that, once live, joins the library so the next advisory takes the known path."),
             _fig_box(190, 30, 300, "Weekly scan", "Fridays: fetch and triage advisories"),
             '<line x1="340" y1="86" x2="340" y2="114"%s/>' % arr,
             _fig_box(190, 116, 300, "An agent reads the advisory", "Indicators, quotes, proposed links", "agent"),
             '<line x1="340" y1="172" x2="340" y2="200"%s/>' % arr,
             _fig_box(190, 202, 300, "A person reviews each link", "Approve or reject, with a reason", "person"),
             '<path d="M340 258 L340 272 L190 272 L190 286"%s/>' % arr,
             '<path d="M340 258 L340 272 L490 272 L490 286"%s/>' % arr,
             _fig_box(60, 288, 260, "Links a known typology", "e.g. %s to %s" % (ADVISORY, CORROBORATES[0])),
             _fig_box(360, 288, 260, "Matches nothing known", "An emergent pattern"),
             '<line x1="190" y1="344" x2="190" y2="382"%s/>' % arr,
             '<line x1="490" y1="344" x2="490" y2="382"%s/>' % arr,
             _fig_box(60, 384, 260, "Absorbed into NEXUS", "Corroborate + re-review"),
             _fig_box(360, 384, 260, "Typology proposal", "Opened by the owner in NEXUS"),
             '<line x1="490" y1="440" x2="490" y2="478"%s/>' % arr,
             _fig_box(360, 480, 260, "Goes live", "Joins the typology library"),
             '<path class="arr loop" d="M360 508 L190 508 L190 442" marker-end="url(#figA)"/>',
             '<text x="275" y="528" text-anchor="middle">The next advisory on it</text>',
             '<text x="275" y="546" text-anchor="middle">takes the known path</text>',
             "</svg>"]
    return "".join(parts)


FIG_ACTOR = {"AGENT": ("agent", "An agent"), "PERSON": ("person", "A person decides"), "NEXUS": ("", "Done in NEXUS")}


def steps_svg() -> str:
    """PIPELINE drawn as a flow, two rows of three, coloured by actor: generated from the same list the step
    cards render, so the picture and the cards cannot disagree."""
    xs, ys, w = (40, 250, 460), (30, 140), 180
    parts = [_fig_open("figS", 270, "From a noticed pattern to a live typology",
                       "The six steps " + ", ".join(s["name"] for s in PIPELINE) + ", coloured by who acts.")]
    for i, s in enumerate(PIPELINE):
        x, y = xs[i % 3], ys[i // 3]
        cls, who = FIG_ACTOR[s["actor"]]
        parts.append(_fig_box(x, y, w, "%d %s" % (s["n"], s["name"]), who, cls))
        if i % 3 != 2 and i + 1 < len(PIPELINE):
            parts.append('<line class="arr" x1="%d" y1="%d" x2="%d" y2="%d" marker-end="url(#figS)"/>'
                         % (x + w, y + 28, x + w + 28, y + 28))
    if len(PIPELINE) > 3:
        parts.append('<path class="arr" d="M550 86 L550 113 L130 113 L130 138" marker-end="url(#figS)"/>')
    parts.append('<rect class="agent" x="150" y="230" width="12" height="12" rx="3"/><text x="170" y="240">Agent</text>'
                 '<rect class="person" x="250" y="230" width="12" height="12" rx="3"/><text x="270" y="240">Person</text>'
                 '<rect x="370" y="230" width="12" height="12" rx="3"/><text x="390" y="240">NEXUS</text></svg>')
    return "".join(parts)


def build(inp: dict) -> str:
    data = json.dumps(payload(inp), ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    return (TEMPLATE.replace("__PAYLOAD__", data).replace("__RUN__", html.escape(RUN_ID))
            .replace("__FIG_PATHS__", two_paths_svg()).replace("__FIG_STEPS__", steps_svg()))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXUS Regulatory Scan</title>
<meta name="description" content="A real Friday run of the NEXUS regulatory intelligence agents, replayed: what they read, what they kept, why, and what a person decided.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root{--bg:#060910;--surface:#0b1220;--raised:#0d1626;--line:#172131;--line-2:#22314a;--fg:#eaf1f9;--fg-2:#c9d5e4;--muted:#a7b7cd;--faint:#8d9db3;--blue:#79c4ff;--blue-ink:#06192e;--gold:#e9c877;--ok:#4fdca0;--warn:#ff8f6b;--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 var(--sans)}
a{color:var(--blue)}a:hover{color:#b9e0ff}
button{font:inherit;cursor:pointer}
button:focus-visible,a:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.wrap{max-width:1360px;margin:0 auto;padding-inline:20px}
.mono{font-family:var(--mono)}
header{border-bottom:1px solid var(--line);background:#0a0f19}
header .wrap{display:flex;flex-wrap:wrap;align-items:center;gap:12px 22px;padding-block:14px}
.brand{display:flex;align-items:center;gap:12px;margin-right:auto}
.brand b{display:block;letter-spacing:.2em;font-size:17px}
.brand small{display:block;font-size:11px;color:var(--muted)}
.pill{font:11px var(--mono);color:var(--muted);border:1px solid var(--line-2);border-radius:8px;padding:6px 10px;background:var(--raised)}
main{display:flex;flex-direction:column;gap:20px;padding-block:24px 48px}
h1{margin:0;font-size:30px;line-height:1.2;text-wrap:balance}
h2{margin:0;font-size:16px}
.lede{margin:8px 0 0;color:var(--muted);max-width:86ch}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0}
.sub{margin:4px 0 12px;font-size:12.5px;color:var(--faint);max-width:92ch}
.label{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:18px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:10px}
.tile{border:1px solid var(--line-2);border-radius:10px;padding:12px;background:var(--raised)}
.tile b{display:block;font-size:13.5px}
.tile p{margin:6px 0 0;font-size:12.5px;color:var(--fg-2)}
.tile .tech{font:11px var(--mono);color:var(--faint);margin-top:8px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.chip{font:12px var(--mono);padding:4px 9px;border-radius:999px;border:1px solid var(--line-2);color:var(--faint)}
.chip.live{border-color:var(--ok);color:var(--ok)}
.chip.manual{border-color:var(--gold);color:var(--gold)}
.chip.notyet{border-style:dashed}
.big{font:600 24px var(--mono)}
.note{font-size:12px;color:var(--faint);margin-top:8px}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;margin-bottom:12px}
.controls h2{margin-right:auto}
.btn{min-height:40px;padding:6px 16px;border-radius:8px;border:1px solid var(--line-2);background:transparent;color:var(--fg-2)}
.btn.primary{border:0;background:var(--blue);color:var(--blue-ink);font-weight:600}
.phase{font:12px var(--mono);color:var(--gold)}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin-bottom:12px}
.bar i{display:block;height:6px;background:var(--blue);transition:width .3s}
.listing{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:8px;margin-bottom:12px}
.listing div{border:1px solid var(--line-2);border-radius:10px;padding:8px 10px;font-size:12.5px}
.rows{display:flex;flex-direction:column;gap:8px}
.row{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--raised);opacity:.55}
.row.on{opacity:1}
.row.now{border-color:var(--blue)}
.row.kept.on{background:rgba(79,220,160,.05)}
.rhead{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px}
.rhead .meta{font:11px var(--mono);color:var(--faint);min-width:96px}
.rhead .t{font-weight:500;flex:1 1 320px;min-width:0}
.badge{font:600 11px var(--mono);padding:3px 8px;border-radius:6px;border:1px solid var(--line-2);color:#6f8199}
.badge.accepted{border-color:var(--ok);color:var(--ok)}
.badge.dropped{border-color:var(--muted);color:var(--muted)}
.badge.deferred{border-color:var(--gold);color:var(--gold)}
.detail{margin-top:8px;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:8px 16px;font-size:12.5px}
.k{color:var(--faint)}
.q{font-style:italic;color:var(--fg-2)}
.ok{color:var(--ok);font:11px var(--mono);font-style:normal}
.ind{border:1px solid var(--line-2);border-radius:10px;padding:10px 12px;margin-top:8px}
.link{border:1px solid var(--line-2);border-radius:10px;padding:12px;margin-top:10px}
.link.approve{border-color:rgba(79,220,160,.5);background:rgba(79,220,160,.05)}
.lhead{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px}
.dec{font:600 11px var(--mono)}
.dec.approve{color:var(--ok)}.dec.reject{color:var(--warn)}
.legend{display:flex;flex-wrap:wrap;gap:12px 18px;margin-bottom:12px;font-size:12px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:2px;display:inline-block}
.stage{border:1px solid var(--line-2);border-radius:10px;padding:12px;background:var(--raised)}
.stage .top{display:flex;justify-content:space-between;align-items:baseline;gap:6px}
.kind{font:600 10.5px var(--mono);border:1px solid;border-radius:5px;padding:1px 6px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px;margin-top:8px}
.step{border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.step .n{font:600 11px var(--mono);color:var(--faint)}
.step .tech{font:11px/1.5 var(--mono);color:var(--faint);margin-top:8px}
.built{font:600 10px var(--mono);color:var(--ok);border:1px solid var(--ok);border-radius:6px;padding:1px 6px}
.next{border:1.5px dashed var(--gold);border-radius:14px;padding:16px;background:rgba(233,200,119,.04)}
.nb{font:600 11px var(--mono);color:var(--gold);border:1px solid var(--gold);border-radius:6px;padding:2px 8px}
.dash{border:1px dashed var(--line-2);border-radius:10px;padding:12px}
.tools{font:11.5px var(--mono);color:var(--fg-2);margin-top:6px;line-height:1.7;overflow-wrap:anywhere}
.figwrap{overflow-x:auto;margin-top:10px}
.fig{display:block;width:100%;min-width:520px;max-width:680px;height:auto;margin:0 auto}
.fig text{font:12px var(--sans);fill:var(--fg-2)}
.fig text.t{font-size:14px;font-weight:500;fill:var(--fg)}
.fig rect{fill:var(--raised);stroke:var(--line-2);stroke-width:1}
.fig rect.agent{stroke:var(--blue)}.fig rect.person{stroke:var(--gold)}
.fig .arr{fill:none;stroke:#8d9db3;stroke-width:1.2}.fig .loop{stroke:var(--ok);stroke-dasharray:4 3}
footer{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;font-size:12px;color:var(--faint);border-top:1px solid var(--line);padding-top:12px}
</style>
</head>
<body>
<header><div class="wrap">
<div class="brand"><svg width="30" height="34" viewBox="0 0 40 46" aria-hidden="true"><path d="M20 2 L36 8 V22 C36 33 29 41 20 44 C11 41 4 33 4 22 V8 Z" fill="rgba(121,196,255,.06)" stroke="#e9c877" stroke-width="1.8"/><path d="M14 30 V16 L26 30 V16" stroke="#79c4ff" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
<div><b>NEXUS</b><small>Regulatory intelligence · agentic scan</small></div></div>
<span class="pill" id="runPill">Friday run __RUN__</span>
</div></header>
<main class="wrap">
<section><h1 id="headline">&nbsp;</h1>
<p class="lede">An agent reads each new notice from the regulators NEXUS watches, keeps only what describes a laundering or evasion method, quotes the page to justify every call, and maps what it keeps onto NEXUS's own governed typologies. A person approves every link before it counts. This is a replay of a real run.</p></section>

<section class="grid3" aria-label="Coverage, agents and quality">
<div class="card"><div class="label">Landscape coverage</div><div class="chips" id="coverage"></div>
<div class="note" id="coverageNote"></div></div>
<div class="card"><div class="label">The agents</div>
<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:8px">
<div><div class="big" style="color:var(--blue)">3</div><div style="font-size:12px;color:var(--muted)">agents: triage, extraction, review</div></div>
<div><div class="big" style="color:var(--blue)">2</div><div style="font-size:12px;color:var(--muted)">MCP tool servers they work through</div></div>
<div><div class="big" style="color:var(--gold)">0</div><div style="font-size:12px;color:var(--muted)">general-purpose tools (no shell, files or web search)</div></div>
</div><div class="note" id="agentsNote"></div></div>
<div class="card"><div class="label">Measured quality</div>
<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:8px">
<div><div class="big" style="font-size:18px;color:var(--ok)" id="qTriage"></div><div style="font-size:12px;color:var(--muted)" id="qTriageSub"></div></div>
<div><div class="big" style="font-size:18px;color:var(--warn)" id="qTyp"></div><div style="font-size:12px;color:var(--muted)">typology recall: agent alone → with the reviewer agent</div></div>
</div><div class="note" id="qualityNote"></div></div>
</section>

<section class="card" aria-label="Scan replay">
<div class="controls"><h2>The scan, replayed</h2><span class="phase" id="phase" aria-live="polite"></span>
<button type="button" class="btn primary" id="play">Play</button>
<button type="button" class="btn" id="step">Step</button>
<button type="button" class="btn" id="reset">Reset</button></div>
<div class="bar"><i id="bar" style="width:0%"></i></div>
<div class="listing" id="listing"></div>
<div class="rows" id="rows"></div>
<p class="note" id="replayNote"></p>
</section>

<section class="card" aria-label="Under the hood">
<h2>Under the hood: agents decide, code checks</h2>
<p class="sub" style="font-size:13px;color:var(--muted)">A language model is good at judgement: is this notice describing a laundering method, and which known pattern does it resemble? It is not trusted with anything that can be checked mechanically. So the scan alternates: an agent makes a call, ordinary deterministic code verifies it, and only then does the next step run.</p>
<div class="legend"><span><span class="sw" style="background:var(--blue)"></span>Agent: a Claude model making a judgement</span><span><span class="sw" style="background:var(--ok)"></span>Code: deterministic, same input same answer</span><span><span class="sw" style="background:var(--gold)"></span>Person: the owner's decision, recorded</span></div>
<div class="tiles" id="stages"></div>
<div class="tiles" style="margin-top:14px">
<div class="tile"><b>Tools through MCP, not open access</b><p>The agents reach the outside world only through two Model Context Protocol servers written for this job. Every write-capable call passes a permission check in code before it runs.</p><div class="tools" id="toolList"></div></div>
<div class="tile"><b>Grounded in NEXUS's own doctrine</b><p id="doctrineText"></p></div>
<div class="tile"><b>Runs itself, and leaves a trail</b><p id="scheduleText"></p></div>
</div>
</section>

<section class="grid2" aria-label="The advisory">
<div class="card" id="advisory"></div>
<div class="card"><div class="label">Typology links, decided by a person</div><div id="links"></div></div>
</section>

<section class="card" aria-label="Two paths after a decision">
<h2>After a person decides: two paths</h2>
<p class="sub" style="font-size:13px;color:var(--muted)">The scan never creates a typology. A person's decision on each link sends it one of two ways: a link to a typology NEXUS already governs goes to that typology's desk; a pattern that matches nothing can become a new typology, and once live it is one the next advisory links to directly.</p>
<div class="figwrap">__FIG_PATHS__</div>
</section>

<section class="card" aria-label="When the agent finds something new">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px"><h2>When the agent finds something new</h2></div>
<p class="sub" id="newHeadline"></p>
<div class="figwrap">__FIG_STEPS__</div>
<div class="grid3" id="newSteps"></div>
<div class="dash" id="newExample" style="margin-top:12px"></div>
</section>

<section class="next" aria-label="Now: the advisory acts inside NEXUS">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px"><h2>Now: the advisory acts inside NEXUS</h2><span id="nowBadge"></span></div>
<p class="sub" style="color:var(--muted)" id="nowSub"></p>
<div class="grid2" style="gap:14px">
<div class="dash" id="nowDoctrine"></div>
<div class="dash" id="nowCase"></div>
</div>
<p class="note" id="nowTotals"></p>
</section>

<section class="card" aria-label="Next capability">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px"><h2>Next</h2><span class="nb">NOT BUILT</span></div>
<ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--fg-2)">
<li><b>New red flags:</b> an agent compares the advisory with the typology's red flags; a person approves genuinely new ones.</li>
<li><b>Cases on the desk:</b> re-review the queue cases of the typology, not only its product.</li>
</ul>
</section>

<footer><span>Deep-dive on one advisory, from PDF to approved links: <a href="index.html">the threat-intelligence walkthrough</a> · <a href="../index.html">NEXUS</a></span><span>Public regulator notices; NEXUS case data is synthetic</span></footer>
</main>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function () {
  "use strict";
  var P = JSON.parse(document.getElementById("payload").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var C = P.counts, A = P.advisory, Q = P.quality, G = P.agents;
  var words = ["Zero","One","Two","Three","Four","Five","Six","Seven","Eight","Nine","Ten","Eleven","Twelve"];
  var n = function (x) { return x < words.length ? words[x] : String(x); };
  $("headline").textContent = n(C.new) + " new regulator notices in. " + n(C.accepted) + " became work for the desks.";
  $("runPill").textContent = "Friday run " + P.run.id + " · " + P.run.model + " · " + P.run.duration;

  $("coverage").innerHTML = P.coverage.live.map(function (s) { return '<span class="chip live">' + esc(s) + ' · live</span>'; }).join("") +
    P.coverage.manual.map(function (s) { return '<span class="chip manual">' + esc(s) + ' · manual</span>'; }).join("") +
    P.coverage.not_yet.map(function (s) { return '<span class="chip notyet">' + esc(s) + ' · not yet</span>'; }).join("");
  $("coverageNote").textContent = n(P.coverage.live.length) + " feeds are scanned automatically every " + G.schedule.day + ". " +
    (P.coverage.manual.length ? P.coverage.manual.join(", ") + " is read by hand because its site blocks automated fetching. " : "") +
    "The rest are in the record schema but not yet scanned.";
  $("agentsNote").textContent = "Built on the Claude Agent SDK, all three on " + G.model + ". Each agent sees only the tools its job needs.";
  $("qTriage").textContent = Q.triage.recall[0] + "–" + Q.triage.recall[1];
  $("qTriageSub").textContent = "triage recall (precision " + Q.triage.precision[0] + "–" + Q.triage.precision[1] + ")";
  $("qTyp").textContent = Q.extraction.recall + " → " + Q.reviewer.recall;
  $("qualityNote").textContent = "Triage: " + Q.triage.items + " owner-labelled notices, " + Q.triage.repeats + " repeats, " + Q.triage.date +
    ". Typologies: " + Q.reviewer.advisories + " golden advisories, " + Q.reviewer.date + " (precision " + Q.extraction.precision + " alone). The weak number is shown on purpose.";

  $("listing").innerHTML = P.listings.map(function (l) {
    return '<div><b class="mono">' + esc(l.source) + '</b> · ' + l.listed + ' listed · ' + l.already_seen + ' already read · <b>' + l.new + ' new</b></div>';
  }).join("");

  var STEPS = P.notices.length + 2;
  var step = 0, timer = null;
  var FATE = { accepted: "KEPT → ", dropped: "DROPPED", deferred: "DEFERRED" };
  function rows() {
    $("rows").innerHTML = P.notices.map(function (it, i) {
      var on = i < step, now = i === step - 1;
      var badge = on ? (it.fate === "accepted" ? FATE.accepted + it.advisory : FATE[it.fate]) : "QUEUED";
      var detail = "";
      if (on) {
        var verdict = it.verdict === "relevant" ? "relevant" : it.verdict === "not_relevant" ? "not relevant" : null;
        detail = '<div class="detail"><div><span class="k">Triage verdict:</span> ' + (verdict ? '<b>' + verdict + '</b> · ' + esc(it.reason)
            : 'not reached: the run ended before this notice was triaged') + '</div>' +
          (it.quote ? '<div><span class="k">Quoted from the page:</span> <span class="q">“' + esc(it.quote) + '”</span> <span class="ok">✓ ' + esc(it.match) + ' match on page</span></div>' : "") +
          (it.fate === "deferred" && verdict ? '<div><span class="k">At acceptance:</span> deferred rather than dropped, so it is read again next Friday.</div>' : "") + '</div>';
      }
      return '<div class="row' + (on ? " on" : "") + (now ? " now" : "") + (it.fate === "accepted" ? " kept" : "") + '">' +
        '<div class="rhead"><span class="meta">' + esc(it.source) + ' · ' + esc(it.published) + '</span><span class="t">' + esc(it.title) + '</span>' +
        '<span class="badge' + (on ? " " + it.fate : "") + '">' + esc(badge) + '</span></div>' + detail + '</div>';
    }).join("");
  }
  function phase() {
    var t;
    if (step === 0) t = "Code · " + C.listed + " listings read, " + C.seen + " already decided, " + C.new + " new";
    else if (step <= P.notices.length) t = "Orchestrator agent · triage " + step + " of " + P.notices.length + " · quote checked by code";
    else if (step === P.notices.length + 1) t = "Extraction agent · " + A.id + " drafted · " + P.extraction.checked + " citations checked, " + P.extraction.off_page + " off their page";
    else t = "Reviewer agent proposed · owner decided: " + A.links.map(function (l) { return (l.id || "emergent") + " " + (l.decision === "approve" ? "approved" : "rejected"); }).join(", ");
    $("phase").textContent = t;
    $("bar").style.width = Math.round(step / STEPS * 100) + "%";
    $("play").textContent = timer ? "Pause" : step >= STEPS ? "Replay" : "Play";
  }
  function render() { rows(); phase(); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }
  $("play").addEventListener("click", function () {
    if (timer) { stop(); phase(); return; }
    if (step >= STEPS) step = 0;
    timer = setInterval(function () { if (step >= STEPS) { stop(); } else { step++; } render(); }, 900);
    render();
  });
  $("step").addEventListener("click", function () { stop(); if (step < STEPS) step++; render(); });
  $("reset").addEventListener("click", function () { stop(); step = 0; render(); });
  $("replayNote").textContent = "Pacing is illustrative; every verdict, reason and quote is the run's own record. The run ended " + P.run.status +
    ": of " + C.new + " new notices, " + C.triaged + " were triaged; acceptance on " + P.run.decided_on + " kept " + C.accepted + ", dropped " + C.dropped + " and deferred " + C.deferred + ".";

  var STAGES = [
    ["01", "CODE", "Fetch and de-duplicate", "Reads each regulator's listing (web pages and an Atom feed) through an HTTP client pinned to an allow-list of hosts. A ledger of notices already decided means each is read once.", "allow-listed HTTP · seen-ledger"],
    ["02", "AGENT", "Triage", "The orchestrator agent opens each new notice and decides whether it describes a method, a red flag or a case. It must justify the call with a verbatim quote.", G.model + " · Agent SDK · feeds MCP server"],
    ["03", "CODE", "Quote check", "The quote is searched for on the fetched page itself. A verdict whose quote is not on its page does not stand.", "exact-match locator"],
    ["04", "AGENT", "Extraction", "A fresh agent per kept notice turns it into a structured advisory: indicators, actors, jurisdictions and candidate typologies, every field quoted. A quote that fails the check gets one repair turn.", G.model + " · Knowledge Centre MCP server"],
    ["05", "CODE", "Validate", "The advisory must pass its schema, and every typology id must exist in NEXUS's governed library. Anything else is refused, not repaired silently.", "advisory schema v" + G.schema_version + " · governed ids"],
    ["06", "PERSON", "Review and route", "A reviewer agent proposes each typology link with its evidence; the owner approves or rejects it, reason recorded. Approved links route the advisory to the desks.", "reviewer agent · decision log · desk routing"]
  ];
  var KC = { AGENT: "var(--blue)", CODE: "var(--ok)", PERSON: "var(--gold)" };
  $("stages").innerHTML = STAGES.map(function (s) {
    return '<div class="stage" style="border-top:3px solid ' + KC[s[1]] + '"><div class="top"><span class="mono" style="font-size:11px;color:var(--faint)">' + s[0] +
      '</span><span class="kind" style="color:' + KC[s[1]] + ';border-color:' + KC[s[1]] + '">' + s[1] + '</span></div><b style="display:block;margin-top:4px">' + esc(s[2]) +
      '</b><p style="margin:6px 0 0;font-size:12.5px;color:var(--fg-2)">' + esc(s[3]) + '</p><div class="tech">' + esc(s[4]) + '</div></div>';
  }).join("");
  $("toolList").innerHTML = "feeds server: " + G.triage_tools.map(esc).join(", ") + "<br>Knowledge Centre server: " + G.kc_tools.map(esc).join(", ");
  $("doctrineText").textContent = "The typology library the agents search is an export of NEXUS's " + G.typologies + " governed typologies. An agent cannot invent an id; when nothing fits, it must say so and propose an emergent pattern for a person to judge.";
  $("scheduleText").textContent = "A scheduled job starts the scan every " + G.schedule.day + " at " + G.schedule.time + ". Each run records every tool call the agents made, every verdict with its quote, and a report; an interrupted run still writes its report. Accuracy is measured against owner-labelled notices and a golden set of advisories, not assumed.";

  $("advisory").innerHTML = '<div class="mono" style="font-size:11px;color:var(--gold)">' + esc(A.id) + ' · ' + esc(A.publisher) + ' · published ' + esc(A.published) + '</div>' +
    '<h2 style="margin:6px 0 4px;font-size:18px">' + esc(A.title) + '</h2>' +
    '<div class="note" style="margin-top:0"><a href="' + esc(A.url) + '" rel="noopener">Read the notice on the regulator\'s site</a> · routed to: ' + A.desks.map(function (d) { return esc(d.replace(/_/g, " ")); }).join(", ") + '</div>' +
    '<div class="label" style="margin-top:12px">What the extraction agent found, each claim quoted</div>' +
    A.indicators.map(function (i) {
      return '<div class="ind"><div style="font-size:13px"><b>' + esc(i.type) + '</b> · ' + esc(i.description) + ' <span class="mono" style="font-size:11px;color:' + (i.detectable ? "var(--ok)" : "var(--faint)") + '">' +
        (i.detectable ? "detectable in transaction data" : "not detectable in transaction data") + '</span></div>' + i.quotes.map(function (q) { return '<div class="q" style="font-size:12px;margin-top:4px">“' + esc(q) + '”</div>'; }).join("") + '</div>';
    }).join("") +
    '<div class="note">' + P.extraction.checked + ' citations checked against the page, ' + P.extraction.off_page + ' off it; ' + P.extraction.repair_turns + ' repair turns needed.</div>';
  $("links").innerHTML = A.links.map(function (l) {
    return '<div class="link ' + l.decision + '"><div class="lhead"><b>' + (l.emergent ? "Emergent: " : esc(l.id) + " · ") + esc(l.name) + '</b><span class="dec ' + l.decision + '">' +
      (l.decision === "approve" ? "APPROVED" : "REJECTED") + '</span></div><div style="font-size:12px;color:var(--muted);margin-top:2px">' +
      (l.emergent ? "A new pattern the agent proposed because nothing in the library fitted." : "Governed NEXUS typology, proposed from the library the agent is allowed to read.") +
      '</div><div style="font-size:12.5px;margin-top:6px">Owner, ' + esc(l.decided_on) + ': “' + esc(l.note.replace(/^owner \d{4}-\d\d-\d\d: /, "")) + '”</div></div>';
  }).join("");

  var N = P.pipeline, NC = N.counts;
  var COUNT = [
    NC.emergent_decided + " emergent pattern(s) proposed and decided",
    NC.emergent_approved + " approved, " + NC.emergent_rejected + " rejected",
    NC.open + " proposal(s) open; " + NC.proposal_links_approved + " advisory link(s) approved",
    NC.defining + " in doctrine",
    NC.building + " engine(s) built, awaiting release",
    "counted in NEXUS: the export carries only proposals still in development"
  ];
  $("newHeadline").textContent = N.headline + " Six steps take a pattern an agent noticed to a typology NEXUS scores; each is marked as built.";
  $("newSteps").innerHTML = N.steps.map(function (s, i) {
    return '<div class="step"><div class="top"><span class="n">' + s.n + '</span> <span class="kind">' + esc(s.actor) + '</span> <span class="' + (s.built ? "built" : "nb") + '">' + (s.built ? "BUILT" : "NOT BUILT") + '</span></div>' +
      '<b style="display:block;margin-top:4px">' + esc(s.name) + '</b><p style="margin:6px 0 0;font-size:12.5px;color:var(--fg-2)">' + esc(s.what) + '</p>' +
      '<div class="tech">' + esc(COUNT[i]) + '</div></div>';
  }).join("");
  var X = N.example;
  $("newExample").innerHTML = X.kind === "proposal"
    ? '<div class="label">In development now</div><b>' + esc(X.ref) + ' · ' + esc(X.name) + '</b> — stage ' + esc(X.stage) + ', ' + X.advisories.length + ' advisory(ies): ' + X.advisories.map(esc).join(", ")
    : '<div class="label">The real example, from this run</div>On ' + esc(X.decided_on) + ' the agent proposed <b>' + esc(X.name) + '</b> as something new. The owner ' + (X.decision === "approve" ? "approved" : "rejected") + ' it: “' + esc(X.note.replace(/^owner \d{4}-\d\d-\d\d: /, "")) + '”. No typology proposal is open yet, so this pattern stopped at step 2 — the gate working.';

  var K = P.corroborates, F = P.fc10;
  var I = P.impact, D = I.doctrine, R = I.rereview;
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function day(v) { var d = new Date(v.slice(0, 10) + "T00:00:00Z"); return d.getUTCDate() + " " + MON[d.getUTCMonth()] + " " + d.getUTCFullYear(); }
  var NOT = '<p style="margin:0;font-size:12.5px;color:var(--muted)">Not yet absorbed in NEXUS</p>';
  var HEAD = '<div class="mono" style="font-size:11px;color:var(--gold)">';
  $("nowBadge").innerHTML = I.built ? '<span class="built">BUILT</span>' : "";
  $("nowSub").textContent = I.built ? "On " + day(I.absorbed_on) + " the owner absorbed " + I.corroborations + " approved advisory links. Each corroborates its typology and puts its product up for re-review. Nothing reopens a case or edits doctrine on its own." : "Not yet absorbed in NEXUS.";
  $("nowDoctrine").innerHTML = D ? HEAD + esc(D.advisory_id) + ' → ' + esc(K.typology) + ' doctrine</div><b style="display:block;margin-top:4px">Corroborated</b>' +
    D.quotes.map(function (q) { return '<p class="q" style="margin:4px 0 0;font-size:12.5px">“' + esc(q.quote) + '” (p. ' + esc(String(q.page)) + ')</p>'; }).join("") +
    '<p style="margin:6px 0 0;font-size:12.5px;color:var(--muted)">' + esc(D.publisher) + ' · approved ' + esc(day(D.decided_at)) + ' · <a href="' + esc(F.doctrine_page) + '">' + esc(K.typology) + ' doctrine</a></p>' : NOT;
  $("nowCase").innerHTML = R ? HEAD + esc(K.typology) + ' → product re-review</div><b style="display:block;margin-top:4px">' + esc(R.id) + ' · <a href="' + esc(F.case_page) + '">' + esc(R.subject) + ' (' + esc(R.case_id) + ')</a></b>' +
    '<p style="margin:4px 0 0;font-size:12.5px;color:var(--muted)">requested ' + esc(day(R.raised_at)) + ' · ' + (R.status === "closed" ? "closed " + esc(day(R.closed_at)) + " · " + esc(R.outcome) : esc(R.status)) + '</p>' : NOT;
  $("nowTotals").textContent = I.built ? "Across NEXUS: " + I.typologies + " typologies corroborated · " + I.rereviews + " re-reviews (" + I.open + " open)" : "";
  render();
})();
</script>
</body>
</html>
"""


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build the regulatory scan demo page")
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed page differs from a fresh build")
    args = ap.parse_args(argv)
    page = build(inputs())
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != page:
            print("STALE: site/scan-demo/index.html differs from a fresh build; run tools/build_scan_demo.py")
            return 1
        print("HOLDS: site/scan-demo/index.html is a fresh build")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print("wrote site/scan-demo/index.html (%d bytes)" % len(page.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
