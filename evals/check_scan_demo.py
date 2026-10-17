"""
Pin the public regulatory-scan demo page (tools/build_scan_demo.py) to the records it claims to show.

Usage:
    python evals/check_scan_demo.py
    python evals/check_scan_demo.py --mutate drop-notice     # a notice vanishes from the page; MUST fail
    python evals/check_scan_demo.py --mutate flip-verdict    # a dropped notice shows as relevant
    python evals/check_scan_demo.py --mutate move-fate       # a deferred notice shows as dropped
    python evals/check_scan_demo.py --mutate edit-quote      # a triage quote no longer says what the run recorded
    python evals/check_scan_demo.py --mutate reverse-decision  # the owner's approval shows as a rejection
    python evals/check_scan_demo.py --mutate citation-count  # the citation check shows a quote off its page
    python evals/check_scan_demo.py --mutate wrong-model     # the page names a model the agents do not run
    python evals/check_scan_demo.py --mutate extra-tool      # the page lists a tool the orchestrator does not have
    python evals/check_scan_demo.py --mutate eval-number     # the triage band is not the one recorded
    python evals/check_scan_demo.py --mutate drop-coverage   # a live feed is missing from the coverage strip
    python evals/check_scan_demo.py --mutate leak-path       # a local path reaches the page
    python evals/check_scan_demo.py --mutate show-cost       # a cost figure reaches the page
    python evals/check_scan_demo.py --mutate built-without-import  # the Now block claims BUILT from an empty import
    python evals/check_scan_demo.py --mutate wrong-rereview  # the Now block shows a re-review the import does not hold
    python evals/check_scan_demo.py --mutate flags-lie       # the Now block counts a red flag the import does not hold
    python evals/check_scan_demo.py --mutate built-lie       # a step shows BUILT naming a file that does not exist
    python evals/check_scan_demo.py --mutate drop-decision   # the step counts lose the decided emergent patterns
    python evals/check_scan_demo.py --mutate fake-proposal   # an invented open proposal reaches the step counts
    python evals/check_scan_demo.py --mutate unpinned-log    # the builder counts a decision made after the pin

WHY. The page is a public claim that a real run went exactly this way. Every value on it must equal the
record it came from, so this guard reads those records ITSELF -- not through the builder's inputs() -- and
compares them with the payload the page carries. A builder bug that misreads a file and a page that agrees
with the misreading would pass a guard that shared the builder's reader.

WHAT IT CHECKS (checks()):
  fresh        the committed page equals a fresh build, under four PYTHONHASHSEED values (plain runs only)
  notices      the same notices as the run's listings, each with the verdict, reason and quote of its triage
               row (None when it was never triaged), and the disposition accepted.json gives it
  counts       listed / already-decided / new per source, and the run's totals
  advisory     every indicator's quotes equal the record's citations; every typology link carries the owner's
               logged decision and note; the citation check equals the extraction-runs row
  agents       model and tool lists equal the agents' own constants; typology count, schema version
  quality      the triage band and reviewer recall are the ones CLAUDE.md records; extraction precision and
               recall are evals/score_report.json's
  coverage     the live feeds are exactly feeds.sources.SOURCES
  cross-link   the walkthrough links to this page and this page to the walkthrough (both published side by side)
  boundary     the page crosses no publish boundary (no paths, internal files, emails)
  pipeline     the six steps, in order, BUILT only over files that exist; the step counts and the example
               equal the decision log CUT at the snapshot's decided_through and the snapshot's proposals
  snapshot     site/scan_demo_snapshot.json is the shape --repin writes, and its cut is a decision the log
               really holds (2026-10-16: a review no longer moves the page; only --repin does)
  no cost      no money figure appears (owner, 2026-10-14)
  impact       the Now block equals data/advisory_impact.json, read here; BUILT only with a SAN006 corroboration
  nexus        WARM: the portfolio's published SAN006 case page names the subject, case and run the page
               declares, and the doctrine page exists. NOT RUN without the portfolio checkout.

NOT A VACUOUS PASS. Each --mutate perturbs a deep copy of the builder's inputs (or, for leak-path and
show-cost, the built page) in memory; at least one check must then fail.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_scan_demo as bs  # noqa: E402
from agents.extract_advisory import KC_TOOLS  # noqa: E402
from agents.orchestrate_feeds import MODEL, TRIAGE_TOOLS  # noqa: E402
from feeds.sources import SOURCES  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402
from publish_scan_demo import DEFAULT_PORTFOLIO  # noqa: E402

MUTATIONS = ("drop-notice", "flip-verdict", "move-fate", "edit-quote", "reverse-decision", "citation-count",
             "wrong-model", "extra-tool", "eval-number", "drop-coverage", "leak-path", "show-cost",
             "built-lie", "drop-decision", "fake-proposal", "built-without-import", "wrong-rereview",
             "unpinned-log", "flags-lie")
MUTATION = None
NOT_RUN = object()
SEEDS = ("0", "1", "42", "4242")
COST = re.compile(r"US\$|\$\s?\d|\bspent\b|\bcost_usd\b", re.I)


def _jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _mutated_inputs() -> dict:
    inp = copy.deepcopy(bs.inputs())
    m = MUTATION
    if m == "drop-notice":
        inp["items"]["sources"]["ofsi"]["items"].pop()
    elif m == "flip-verdict":
        inp["triage"][0]["verdict"] = "relevant"
    elif m == "move-fate":
        acc = inp["accepted"]
        key = acc["deferred"].pop(0)
        item = next(it for b in inp["items"]["sources"].values() for it in b["items"] if it["key"] == key)
        acc["dropped"].append("%s:%s" % (item["source"], item["item_id"]))
    elif m == "edit-quote":
        inp["triage"][3]["quote"] = inp["triage"][3]["quote"].replace("designated", "listed", 1)
    elif m == "reverse-decision":
        for d in inp["decisions"]:
            if d["decision"] == "approve":
                d["decision"] = "reject"
    elif m == "citation-count":
        inp["extraction"][0]["citation_check"]["off_page"] = 1
    elif m == "wrong-model":
        inp["model"] = "claude-unrecorded-model"
    elif m == "extra-tool":
        inp["triage_tools"] = inp["triage_tools"] + ["web_search"]
    elif m == "eval-number":
        inp["triage_band"]["recall"][0] = "0.990"
    elif m == "drop-coverage":
        inp["live"] = [s for s in inp["live"] if s != "ofsi"]
    elif m == "built-lie":
        inp["pipeline"][3]["evidence"] = ["agents/no_such_drafter.py"]
    elif m == "drop-decision":
        inp["log"] = [d for d in inp["log"] if d.get("kind") != "emergent"]
    elif m == "fake-proposal":
        inp["proposals"] = inp["proposals"] + [{"proposal_id": "TP-2099-999", "working_name": "Invented",
                                                "family": "sanctions", "stage": "open", "evidence": []}]
    elif m == "built-without-import":
        inp["impact"] = {"typologies": {}}
    elif m == "flags-lie":
        inp["impact"]["typologies"][bs.CORROBORATES[0]]["flags"] = [{
            "id": "FLG-99", "text": "Invented", "advisory_id": bs.ADVISORY, "quote": "x", "page": 1,
            "status": "approved", "in_doctrine_commit": ""}]
    elif m == "wrong-rereview":
        inp["impact"]["typologies"][bs.CORROBORATES[0]]["rereviews"][0]["subject"] = "Someone Else Ltd"
    elif m == "unpinned-log":
        # A builder that ignores the pin: the whole live log plus one emergent decision made after the cut,
        # so the mutation proves something even on a day when nothing has been decided since the snapshot.
        later = datetime.fromisoformat(bs.load_snapshot()["decided_through"]) + timedelta(days=1)
        inp["log"] = _jsonl(gd.LOG) + [{"advisory_id": "ADV-2099-0001", "decided_at": later.isoformat(),
                                        "decision": "reject", "kind": "emergent",
                                        "link_key": "ADV-2099-0001::EMERGENT[invented]"}]
    return inp


def _page() -> str:
    page = bs.build(_mutated_inputs())
    if MUTATION == "leak-path":
        page = page.replace("Friday run ", "Friday run /Users/someone/runs ", 1)
    elif MUTATION == "show-cost":
        page = page.replace("This is a replay of a real run.", "This is a replay of a real run, which spent US$0.42.", 1)
    return page


def _payload(page: str) -> dict:
    m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else {}


def _snapshot() -> dict:
    """The committed snapshot, read raw (the shape clause uses the builder's loader; this does not)."""
    return json.loads(bs.SNAPSHOT.read_text(encoding="utf-8"))


def _cut(log: list) -> list:
    """The log at or before the snapshot's decided_through: the slice the page may count."""
    through = datetime.fromisoformat(_snapshot()["decided_through"])
    return [d for d in log if datetime.fromisoformat(d["decided_at"]) <= through]


def _truth() -> dict:
    """The run, read straight from its records: independent of the builder's reader."""
    run_dir = bs.RUN_DIR
    items = json.loads((run_dir / "items.json").read_text(encoding="utf-8"))["sources"]
    triage = {r["key"]: r for r in _jsonl(run_dir / "triage.jsonl")}
    acc = json.loads((run_dir / "accepted.json").read_text(encoding="utf-8"))
    fate = {}
    for src, block in items.items():
        for it in block["items"]:
            if it["key"] in acc["accepted"]:
                fate[it["key"]] = "accepted"
            elif it["key"] in acc["deferred"]:
                fate[it["key"]] = "deferred"
            elif "%s:%s" % (src, it["item_id"]) in acc["dropped"]:
                fate[it["key"]] = "dropped"
    ext = [x for x in _jsonl(run_dir / "extraction_runs.jsonl") if x.get("advisory_id") == bs.ADVISORY]
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    return {
        "items": items, "triage": triage, "accepted": acc, "fate": fate, "extraction": ext,
        "record": json.loads(bs.RECORD.read_text(encoding="utf-8")),
        "decisions": {d["link_key"]: d for d in _cut(_jsonl(gd.LOG)) if d.get("advisory_id") == bs.ADVISORY},
        "typologies": json.loads(bs.TYPOLOGIES.read_text(encoding="utf-8"))["typologies"],
        "score": json.loads(bs.SCORE_REPORT.read_text(encoding="utf-8"))["totals"]["typologies"],
        "log": _cut(_jsonl(gd.LOG)),
        "proposals": _snapshot()["proposals"],
        "impact": json.loads((ROOT / "data" / "advisory_impact.json").read_text(encoding="utf-8")),
        "triage_line": next((ln for ln in claude.splitlines() if "The triage band, measured" in ln), ""),
        "reviewer_line": next((ln for ln in claude.splitlines() if "FULL SET, all" in ln and "reviewer" in ln), ""),
    }


def _fresh_under_seeds() -> list:
    """sha256 of a fresh build in a subprocess per hash seed -- one value means deterministic."""
    shas = set()
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        code = ("import sys,hashlib;sys.path[:0]=[%r,%r];import build_scan_demo as b;"
                "print(hashlib.sha256(b.build(b.inputs()).encode()).hexdigest())") % (str(ROOT), str(ROOT / "tools"))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT)
        shas.add(r.stdout.strip() if r.returncode == 0 else "ERROR: %s" % r.stderr.strip()[-200:])
    return sorted(shas)


def checks():
    T = _truth()
    try:
        page = _page()
    except SystemExit as exc:
        yield False, "the builder accepts the inputs", str(exc)
        return
    P = _payload(page)
    yield bool(P), "the page carries its payload", "%d top-level keys" % len(P)
    if not P:
        return

    if MUTATION is None:
        committed = bs.OUT.read_text(encoding="utf-8") if bs.OUT.exists() else ""
        yield committed == bs.build(bs.inputs()), "the committed page is a fresh build", "site/scan-demo/index.html"
        shas = _fresh_under_seeds()
        yield (len(shas) == 1 and not shas[0].startswith("ERROR")
               and shas[0] == hashlib.sha256(committed.encode("utf-8")).hexdigest()), \
            "a fresh build is identical under %d hash seeds" % len(SEEDS), ", ".join(s[:16] for s in shas)

    notices = {n["key"]: n for n in P["notices"]}
    keys = {it["key"] for b in T["items"].values() for it in b["items"]}
    yield set(notices) == keys and len(keys) >= 5, "the page shows exactly the run's notices", \
        "%d on the page, %d listed new in the run" % (len(notices), len(keys))

    bad = []
    for key in sorted(keys & set(notices)):
        n, row = notices[key], T["triage"].get(key)
        want = (row["verdict"], row["reason"], row["quote"]) if row else (None, None, None)
        if (n["verdict"], n["reason"], n["quote"]) != want:
            bad.append(key)
        if n["fate"] != T["fate"].get(key):
            bad.append("%s fate %s != %s" % (key, n["fate"], T["fate"].get(key)))
    yield not bad and len(T["triage"]) >= 5, "each notice carries its own verdict, reason, quote and disposition", \
        ", ".join(bad) or "%d triage rows compared" % len(T["triage"])

    acc = T["accepted"]
    want_counts = {"listed": sum(b["listed"] for b in T["items"].values()),
                   "seen": sum(b["already_seen"] for b in T["items"].values()), "new": len(keys),
                   "accepted": len(acc["accepted"]), "deferred": len(acc["deferred"]), "dropped": len(acc["dropped"]),
                   "triaged": len(T["triage"])}
    yield P["counts"] == want_counts, "the run's totals", "%s vs %s" % (P["counts"], want_counts)

    rec_quotes = [[c["quote"] for c in i["citations"]] for i in T["record"]["indicators"]]
    page_quotes = [i["quotes"] for i in P["advisory"]["indicators"]]
    yield page_quotes == rec_quotes and bool(rec_quotes), "every indicator quotes the record's own citations", \
        "%d indicators" % len(rec_quotes)

    link_bad = []
    for link in P["advisory"]["links"]:
        lk = ("%s::%s" % (bs.ADVISORY, link["id"]) if link["id"]
              else "%s::EMERGENT[%s]" % (bs.ADVISORY, link["name"].lower()))
        d = T["decisions"].get(lk)
        if d is None or (link["decision"], link["note"]) != (d["decision"], d["note"]):
            link_bad.append(lk)
    yield not link_bad and len(P["advisory"]["links"]) == len(T["record"]["typologies"]) >= 1, \
        "every typology link carries the owner's logged decision", ", ".join(link_bad) or \
        "%d links" % len(P["advisory"]["links"])

    ext = T["extraction"]
    want_ext = ext and {"checked": ext[0]["citation_check"]["checked"], "off_page": ext[0]["citation_check"]["off_page"],
                        "repair_turns": ext[0]["quote_repair"]["repair_turns"]}
    yield len(ext) == 1 and P["extraction"] == want_ext, "the citation check is the extraction run's", \
        "%s vs %s" % (P["extraction"], want_ext)

    A = P["agents"]
    yield (A["model"], A["triage_tools"], A["kc_tools"]) == (MODEL, list(TRIAGE_TOOLS), list(KC_TOOLS)), \
        "the model and tool lists are the agents' own", "%s · %d + %d tools" % (A["model"], len(A["triage_tools"]),
                                                                                 len(A["kc_tools"]))
    yield A["typologies"] == len(T["typologies"]) and A["schema_version"] == bs.SCHEMA_VERSION, \
        "typology count and schema version", "%s typologies, schema %s" % (A["typologies"], A["schema_version"])

    Q = P["quality"]
    tri = Q["triage"]
    yield all(x in T["triage_line"] for x in ("recall %s-%s" % tuple(tri["recall"]),
                                                "precision %s-%s" % tuple(tri["precision"]), tri["date"])), \
        "the triage band is the one CLAUDE.md records", "recall %s-%s" % tuple(tri["recall"])
    yield ("R %s" % Q["reviewer"]["recall"]) in T["reviewer_line"].split("reviewer", 1)[-1] \
        and (Q["extraction"]["precision"], Q["extraction"]["recall"]) == \
        ("%.3f" % T["score"]["precision"], "%.3f" % T["score"]["recall"]), \
        "typology quality is score_report's and CLAUDE.md's", \
        "%s -> %s" % (Q["extraction"]["recall"], Q["reviewer"]["recall"])

    yield sorted(P["coverage"]["live"]) == sorted(bs.DISPLAY[s] for s in SOURCES), \
        "the live feeds are exactly the configured sources", ", ".join(P["coverage"]["live"])

    walkthrough = (ROOT / "site" / "threat-intel" / "index.html").read_text(encoding="utf-8")
    yield 'href="index.html"' in page and 'href="scan.html"' in walkthrough, \
        "the scan page and the walkthrough link to each other", "scan -> index.html, walkthrough -> scan.html"

    leaks = pb.violations(page)
    yield not leaks, "the page crosses no publish boundary", ", ".join(leaks) or "clean"
    costs = sorted(set(m.group(0) for m in COST.finditer(page)))
    yield not costs, "no cost figure on the page", ", ".join(costs) or "none"

    # Stage565 S4 (spec §7.2, plan R21): the six steps, computed here from the raw files, never from the builder.
    PL = P.get("pipeline", {})
    names = [s["name"] for s in PL.get("steps", [])]
    yield names == ["Spot", "Decide", "Propose", "Define", "Build", "Live"], \
        "the something-new section lays out the six steps, in order", names
    used = _mutated_inputs()["pipeline"]          # the inputs the page was built from; paths never reach the page
    missing = ["%s: %s" % (s["name"], f) for s in used if s["built"] for f in s["evidence"] if not (ROOT / f).exists()]
    shown = [(s["name"], s["built"]) for s in PL.get("steps", [])]
    yield bool(used) and not missing and shown == [(s["name"], s["built"]) for s in used], \
        "every step marked BUILT names fc-08 files that exist", missing or shown
    latest = {}
    for d in T["log"]:
        latest[d["link_key"]] = d
    em = [d for d in latest.values() if d.get("kind") == "emergent"]
    want = {"emergent_decided": len(em), "emergent_approved": sum(d["decision"] == "approve" for d in em),
            "emergent_rejected": sum(d["decision"] == "reject" for d in em),
            "proposal_links_approved": sum(d.get("kind") == "proposal" and d["decision"] == "approve"
                                           for d in latest.values()),
            "open": len(T["proposals"]),
            "defining": sum(p["stage"] in ("doctrine_drafted", "doctrine_approved") for p in T["proposals"]),
            "building": sum(p["stage"] == "engine_built" for p in T["proposals"])}
    yield PL.get("counts") == want, "the step counts are the decision log's and the import's", PL.get("counts")
    ex = PL.get("example", {})
    want_ex = (sorted(p["proposal_id"] for p in T["proposals"])[0] if T["proposals"]
               else "%s::EMERGENT" % bs.ADVISORY)
    yield ex.get("ref", "").startswith(want_ex), \
        "the example is the first open proposal, or ADV-2026-0026's decided emergent when none is open", ex.get("ref")
    yield "The agent can only notice; a person defines." in page, "the section says who decides", ""

    I, TI = P.get("impact", {}), T["impact"]["typologies"]
    san = TI.get(bs.CORROBORATES[0], {})
    yield I.get("built") is bool(san.get("corroborations")) and I.get("built") is True, \
        "the Now block is BUILT exactly when the import holds a SAN006 corroboration", I.get("built")
    want_rr = (san.get("rereviews") or [None])[0]
    fields = ("id", "subject", "case_id", "status", "outcome", "raised_at", "closed_at")
    yield bool(want_rr) and I.get("rereview") == {k: want_rr[k] for k in fields}, \
        "the Now block's re-review is the import's", (I.get("rereview") or {}).get("id")
    corrs = [c for t in TI.values() for c in t.get("corroborations", [])]
    rrs = [r for t in TI.values() for r in t.get("rereviews", [])]
    want_tot = {"corroborations": len(corrs), "typologies": sum(1 for t in TI.values() if t.get("corroborations")),
                "rereviews": len(rrs), "open": sum(r["status"] == "open" for r in rrs),
                "absorbed_on": max((c["absorbed_at"][:10] for c in corrs), default="")}
    yield {k: I.get(k) for k in want_tot} == want_tot, "the Now block's totals are the import's", want_tot
    # Stage566 K3c: the red-flag counts are the import's, and "New red flags" leaves Next only when one exists.
    fl = [f for t in TI.values() for f in t.get("flags", [])]
    want_fl = {"flags": sum(f["status"] == "approved" for f in fl),
               "flags_in_doctrine": sum(f["status"] == "in_doctrine" for f in fl)}
    yield {k: I.get(k) for k in want_fl} == want_fl, "the Now block's red-flag counts are the import's", want_fl
    yield 'id="nextFlags"' in page and "New red flags:" in page, \
        "the Next block still lists New red flags for the page to move", ""
    fv = bs.impact_view({"typologies": {"SAN006": {"corroborations": [], "rereviews": [], "flags": [
        {"id": "FLG-1", "status": "approved"}, {"id": "FLG-2", "status": "in_doctrine"},
        {"id": "FLG-3", "status": "withdrawn"}]}}})
    yield (fv["flags"], fv["flags_in_doctrine"]) == (1, 1), "impact_view counts approved and in-doctrine flags, " \
        "not withdrawn ones", (fv["flags"], fv["flags_in_doctrine"])
    yield bool(want_rr) and (bs.FC10["subject"], bs.FC10["case_id"]) == (want_rr["subject"], want_rr["case_id"]), \
        "the declared FC10 case is the import's SAN006 re-review", bs.FC10["case_id"]
    closed = copy.deepcopy(T["impact"])
    for r in closed["typologies"].get(bs.CORROBORATES[0], {}).get("rereviews", [])[:1]:
        r.update(status="closed", outcome="unchanged", closed_at="2026-10-20T09:00:00")
    cv = bs.impact_view(closed)
    yield (cv["rereview"] or {}).get("status") == "closed" and cv["open"] == want_tot["open"] - 1, \
        "impact_view shows a closed re-review as closed", "open %s" % cv["open"]
    ev = bs.impact_view({"typologies": {}})
    yield ev["built"] is False and ev["doctrine"] is None and ev["rereview"] is None, \
        "an empty import builds no BUILT claim", ""
    try:
        bs.load_snapshot()
        shape = ""
    except SystemExit as exc:
        shape = str(exc)
    yield not shape, "the snapshot is the shape --repin writes", shape or bs.SNAPSHOT.name
    through = _snapshot().get("decided_through")
    yield any(d.get("decided_at") == through for d in _jsonl(gd.LOG)), \
        "the snapshot's cut is a decision the log really holds", through

    portfolio = Path(os.path.expanduser(DEFAULT_PORTFOLIO))
    nexus = portfolio / "projects" / "nexus"
    if not nexus.is_dir():
        yield NOT_RUN, "the declared NEXUS case matches the published one", "no portfolio checkout"
        return
    F = P["fc10"]
    case = (nexus / "threat-intel" / F["case_page"]).resolve()
    doctrine = (nexus / "threat-intel" / F["doctrine_page"]).resolve()
    text = case.read_text(encoding="utf-8") if case.exists() else ""
    # The link lands on the subject's entity page; the run id lives on the product page it links to, so the
    # provenance is checked one hop on: the entity page must name the subject and link to that product page.
    product = (case.parent / ("../products/%s.html" % F["typology"])).resolve()
    links = 'href="../products/%s.html"' % F["typology"] in text
    ptext = product.read_text(encoding="utf-8") if product.exists() else ""
    yield (all(v in text for v in (F["subject"], F["typology"])) and links
           and all(v in ptext for v in (F["subject"], F["run_id"])) and doctrine.exists()), \
        "the declared NEXUS case matches the published one", "%s · %s · %s" % (F["subject"], F["case_id"], F["run_id"])


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the public regulatory scan demo page")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule; checks MUST fail")
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        if ok is NOT_RUN:
            print("  NOT RUN: %s\n         %s" % (label, detail))
            continue
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
