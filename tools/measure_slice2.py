"""
Measure the live Friday runs of an inbox, read-only (slice 2 D).

Usage:
    python -m tools.measure_slice2 --inbox ~/fc-08-schedule/inbox [--markdown] [--all]

READ-ONLY: it opens files in the inbox and never writes one.

DEFINITIONS
  cost per run          run.json's spent_usd;
  live resolution rate  resolved / resolver calls, both summed across the measured runs (not a mean of rates);
  items per source      new items per source (items.json);
  triage band           the committed back-catalogue band in evals/feeds/score.json. Live kept/total is
                        reported as observed and never as a band: live items have no ground truth.
EXCLUDED  a REFUSED run (refusal.json, which also covers rehearsal checkouts), a run with no run.json, and a
          run with spent_usd == 0. A manual run (not a Friday) is kept and flagged scheduled: false.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCORE = ROOT / "evals" / "feeds" / "score.json"
RESOLVER = "__knowledge_centre_resolve_actor"
SOURCES = ("ofsi", "fincen", "ofac")
_MUTATE = None


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _lines(p: Path) -> list:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def _run(d: Path) -> dict:
    run = _json(d / "run.json")
    day = date.fromisoformat(d.name[6:16])
    items = _json(d / "items.json")["sources"] if (d / "items.json").exists() else {}
    triage = _lines(d / "triage.jsonl")
    calls = [e["payload"] for f in sorted((d / "telemetry").glob("adv-*.jsonl")) for e in _lines(f)
             if e.get("stage") == "FC08_TOOL_CALL" and e["payload"].get("tool", "").endswith(RESOLVER)]
    return {"run_id": d.name, "date": day.isoformat(), "weekday": day.strftime("%A"), "scheduled": day.weekday() == 4,
            "status": "completed", "spent_usd": run["spent_usd"],
            "items_new": {s: len(items.get(s, {}).get("items", [])) for s in SOURCES},
            "triage_kept": sum(1 for t in triage if t.get("verdict") == "relevant"), "triage_total": len(triage),
            "resolver_calls": len(calls), "resolved": sum(1 for c in calls if c.get("outcome", "").startswith("Resolved: "))}


def measure(inbox: Path, *, live_only: bool = True) -> dict:
    runs = []
    for d in sorted(Path(inbox).glob("feeds-*")):
        refused = (d / "refusal.json").exists() and _MUTATE != "keep-refused"
        if refused or (not (d / "run.json").exists() and _MUTATE != "keep-refused"):
            continue
        if not (d / "run.json").exists():
            runs.append({"run_id": d.name, "date": d.name[6:16], "weekday": "", "scheduled": False, "status": "refused",
                         "spent_usd": 0, "items_new": {s: 0 for s in SOURCES}, "triage_kept": 0, "triage_total": 0,
                         "resolver_calls": 0, "resolved": 0})
            continue
        r = _run(d)
        if live_only and not r["spent_usd"]:
            continue
        runs.append(r)
    costs = [r["spent_usd"] for r in runs]
    calls, resolved = sum(r["resolver_calls"] for r in runs), sum(r["resolved"] for r in runs)
    if _MUTATE == "sum-rates":
        rate = sum(r["resolved"] / r["resolver_calls"] for r in runs if r["resolver_calls"])
    else:
        rate = resolved / calls if calls else None
    ov = _json(SCORE)["overall"]
    return {"runs": runs,
            "totals": {"runs": len(runs), "cost_mean_usd": round(sum(costs) / len(costs), 3) if costs else None,
                       "cost_max_usd": max(costs) if costs else None,
                       "resolution_rate": round(rate, 4) if rate is not None else None, "resolver_calls": calls,
                       "resolved": resolved, "items_by_source": {s: sum(r["items_new"][s] for r in runs) for s in SOURCES},
                       "triage_kept_ratio": [sum(r["triage_kept"] for r in runs), sum(r["triage_total"] for r in runs)]},
            "band": {"%s_%s" % (k, s): ov[k][s] for k in ("recall", "precision") for s in ("min", "mean", "max")}}


def render(m: dict, markdown: bool) -> str:
    t, b = m["totals"], m["band"]
    out = []
    if markdown:
        out += ["| run | date | weekday | scheduled | spent US$ | ofsi | fincen | ofac | triage kept/total | resolved/calls |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        out += ["| %s | %s | %s | %s | %.3f | %d | %d | %d | %d/%d | %d/%d |" % (
            r["run_id"], r["date"], r["weekday"], "yes" if r["scheduled"] else "no (manual)", r["spent_usd"],
            r["items_new"]["ofsi"], r["items_new"]["fincen"], r["items_new"]["ofac"], r["triage_kept"],
            r["triage_total"], r["resolved"], r["resolver_calls"]) for r in m["runs"]]
        out.append("")
    else:
        out += ["%s %s %-9s scheduled=%-5s US$%.3f items=%s triage=%d/%d resolved=%d/%d" % (
            r["run_id"], r["date"], r["weekday"], r["scheduled"], r["spent_usd"], r["items_new"], r["triage_kept"],
            r["triage_total"], r["resolved"], r["resolver_calls"]) for r in m["runs"]]
    rate = "n/a" if t["resolution_rate"] is None else "%.1f%%" % (100 * t["resolution_rate"])
    out += ["runs measured: %d" % t["runs"], "cost per run: mean US$%s, max US$%s" % (t["cost_mean_usd"], t["cost_max_usd"]),
            "live resolution: %d of %d resolver calls (%s)" % (t["resolved"], t["resolver_calls"], rate),
            "new items by source: %s" % ", ".join("%s %d" % kv for kv in t["items_by_source"].items()),
            "live triage kept (observed, no ground truth): %d of %d" % tuple(t["triage_kept_ratio"]),
            "committed triage band (back-catalogue; OFAC per-source recall rests on n=3): recall %s-%s (mean %s), precision %s-%s (mean %s)" % (
                b["recall_min"], b["recall_max"], b["recall_mean"], b["precision_min"], b["precision_max"], b["precision_mean"])]
    return "\n".join(out)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Read-only measurement of the live Friday runs")
    ap.add_argument("--inbox", required=True, type=Path)
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--all", action="store_true", help="also keep runs that spent nothing")
    args = ap.parse_args(argv)
    print(render(measure(args.inbox, live_only=not args.all), args.markdown))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
