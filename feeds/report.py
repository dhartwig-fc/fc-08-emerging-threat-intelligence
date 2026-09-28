"""
The Friday report, inbox/<run_id>/report.md, written on EVERY run -- refused, failed, nothing new or full
(spec section 2). A deterministic projection of the run's own files through feeds/reconcile.py: the same
folder always renders the same bytes, and nothing here reads a clock, git or the network.

Its first two lines are the contract with the notification (C2): "# Friday run <id>: <STATUS>" and one
plain sentence. Failures are stated loudly, in capitals, above everything else.
"""

from __future__ import annotations

import json
from pathlib import Path

from feeds import extraction, inbox, reconcile

REPORT = "report.md"
CEILING_NOTE = "US$%.2f ceiling"


def _usd(x) -> str:
    return "unknown" if x is None else "US$%.2f" % x


def _cell(text, limit=160) -> str:
    """One line of text for a table cell or a bullet; limit=None keeps it whole."""
    return " ".join(str(text or "").split())[:limit].replace("|", "/")


def _sentence(text, limit) -> str:
    """A reason that already ends in a full stop does not get a second one."""
    return _cell(text, limit).rstrip(".")


def actor_resolution(record: dict) -> tuple:
    """(named, resolvable) actors of a record against the governed register, exact matches only -- the same
    rule as evals/actor_resolution.py -- so a run's resolution rate does not depend on the agent's calls."""
    from schemas.actor_match import resolve, variants_of
    from tools.build_actor_register import load_register
    register = load_register()
    named = resolved = 0
    for actor in record.get("actors", []):
        got = resolve(variants_of(actor), actor.get("actor_type"), register)
        if got["status"] == "category":
            continue
        named += 1
        resolved += got["status"] == "resolved"
    return named, resolved


def summary_line(rec: dict) -> str:
    if rec["status"] == reconcile.REFUSED:
        return "Refused before any agent ran: %s." % "; ".join(rec["refusal"].get("reasons", []))
    if rec["status"] == reconcile.FAILED:
        if rec.get("crash"):
            return "The run failed after its session: %s." % _sentence(rec["crash"], 200)
        return "The orchestrator session failed: %s." % _sentence(rec["failure"] or "no session telemetry", 200)
    # The "unfinished" count here and the ## Unfinished section list the SAME four kinds of skipped work
    # (check_friday_run pins that they agree): C2's notification reads this line, a person reads the section.
    return "%d new item(s), %d kept, %d dropped by triage, %d extracted, %d unfinished; %s spent of the %s." % (
        len(rec["listed"]), len(rec["relevant"]), len(rec["not_relevant"]), len(rec["extracted"]),
        len(rec["unfinished"]) + len(rec["not_queued"]) + len(rec["failed"]) + len(rec["deferred_budget"]),
        _usd(rec["spent_usd"]), CEILING_NOTE % 5.0)


def render(run_id: str, root: Path = inbox.INBOX_ROOT) -> str:
    rec = reconcile.reconcile_run(run_id, root)
    folder = inbox.run_dir(run_id, root)
    items = {it["key"]: it for it in inbox.items(inbox.load(run_id, root))}
    outcomes = extraction.load_outcomes(run_id, root)
    # Rows go in QUEUE order -- the order the budget was spent in -- then every other item in listing order.
    order = list(rec["queued"]) + [k for k in items if k not in rec["queued"]]
    rank = {k: i for i, k in enumerate(order)}

    def in_order(keys):
        return sorted(keys, key=lambda k: (rank.get(k, len(rank)), k))
    out = ["# Friday run %s: %s" % (run_id, rec["status"]), "", summary_line(rec), ""]
    loud = []
    if rec["refusal"]:
        loud += ["**REFUSED: %s**" % r for r in rec["refusal"].get("reasons", [])]
    if rec["status"] == reconcile.FAILED:
        loud.append("**FAILED: %s**" % _cell(rec["failure"] or "the orchestrator session left no telemetry", 300))
    for name in rec["source_failures"]:
        st = rec["sources"][name]
        word = "LAYOUT CHANGED" if st["status"] == "layout_changed" else "SOURCE DOWN"
        loud.append("**%s: %s (%s)**" % (word, name, _cell(st.get("error"), 200)))
    for name in rec["never_listed_sources"]:
        if not rec["refusal"]:
            loud.append("**NOT LISTED: %s was never listed in this run**" % name)
    if rec["problems"]:
        loud += ["**RECONCILIATION: %s**" % p for p in rec["problems"]]
    if loud:
        out += loud + [""]

    out += ["## Sources", "", "| source | status | listed | already decided | new |", "|---|---|---|---|---|"]
    for name in reconcile.SOURCES:
        st = rec["sources"].get(name)
        if st is None:
            out.append("| %s | not listed | - | - | - |" % name)
        else:
            new = sum(1 for it in items.values() if it["source"] == name)
            out.append("| %s | %s | %s | %s | %d |" % (name, st.get("status"), st.get("listed"), st.get("already_seen"),
                                                      new))
    for title, keys in (("Kept by triage (relevant)", rec["relevant"]),
                        ("Dropped by triage (not relevant), with the reason and the quote", rec["not_relevant"])):
        out += ["", "## %s: %d" % (title, len(keys)), ""]
        for k in in_order(keys):
            v = rec["verdicts"][k]
            out.append("- `%s` %s -- %s. Quote (p.%s): \"%s\"" % (
                k, _cell(items[k]["title"], 120), _sentence(v["reason"], 300), ",".join(map(str, v["found_on"])),
                _cell(v["quote"], 200)))
        if not keys:
            out.append("None.")
    # Every kind of skipped work summary_line counts, each with its WHOLE reason (never cut to a cell).
    unfinished = ([(k, "no verdict") for k in rec["unfinished"]]
                  + [(k, "relevant, not queued for extraction") for k in rec["not_queued"]]
                  + [(k, "extraction failed: %s" % _cell(rec["failed"][k], None)) for k in rec["failed"]]
                  + [(k, "deferred for budget: %s" % _cell(outcomes[k].get("error"), None)) for k in rec["deferred_budget"]])
    unfinished = sorted(unfinished, key=lambda row: (rank.get(row[0], len(rank)), row[0]))
    out += ["", "## Unfinished: %d (they return next Friday unless dropped)" % len(unfinished), ""]
    out += ["- `%s` %s: %s" % (k, _cell(items.get(k, {}).get("title"), 120), why) for k, why in unfinished]
    if not unfinished:
        out.append("None.")

    out += ["", "## Extraction: %d queued, %d extracted, %d failed, %d deferred for budget" % (
        len(rec["queued"]), len(rec["extracted"]), len(rec["failed"]), len(rec["deferred_budget"])), ""]
    if rec["queued"]:
        out += ["| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable "
                "| cost |", "|---|---|---|---|---|---|---|"]
    by_id = {s["run_id"]: s for s in rec["sessions"]}
    for k in rec["queued"]:
        o = outcomes.get(k, {"status": "no outcome"})
        s = by_id.get(o.get("extraction_run_id"), {})
        queue = folder / inbox.PROPOSALS / ("%s.jsonl" % o.get("extraction_run_id"))
        proposals = sum(1 for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()) if queue.exists() else 0
        actors = "-"
        if o.get("status") == "extracted" and o.get("record"):
            named, resolvable = actor_resolution(json.loads((folder / o["record"]).read_text(encoding="utf-8")))
            actors = "%d of %d" % (resolvable, named)
        status = o["status"] if o["status"] != "failed" else "failed: %s" % _cell(o.get("error"), 80)
        out.append("| `%s` | %s | %s | %d | %s | %s | %s |" % (
            k, o.get("advisory_id") or "-", status, proposals,
            "%d (%d)" % (s.get("resolver_calls", 0), s.get("resolved", 0)) if s else "-", actors, _usd(o.get("cost_usd"))))

    out += ["", "## Reconciliation: %s" % ("clean" if not rec["problems"] else "%d problem(s)" % len(rec["problems"])), "",
            "| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |",
            "|---|---|---|---|---|---|---|---|---|"]
    for s in rec["sessions"]:
        out.append("| %s | %s | %s | %s | %s | %s | %d | %d | %d |" % (
            s["run_id"], s["agent"], s["status"], _usd(s["cost_usd"]), s["turns"], s["calls"], len(s["unterminated"]),
            len(s["duplicated"]), s["from_transcript"]))
    out += ["", "## Cost", "",
            "%s counted against the %s (a session whose cost never arrived is counted at its cap); %s reported by the "
            "sessions' own telemetry." % (_usd(rec["spent_usd"]), CEILING_NOTE % 5.0, _usd(rec["known_cost_usd"])), ""]
    if rec["status"] in reconcile.ACCEPTABLE and rec["listed"]:
        out += ["## Next", "", "`python tools/accept_run.py %s` -- accept, drop or defer each item." % run_id, ""]
    elif rec["status"] == reconcile.RECON_FAILED:
        out += ["## Next", "", "Reconciliation failed: accepting this run needs `--override-reconciliation "
                "\"<reason>\"`, and the reason is recorded.", ""]
    return "\n".join(out)


def write(run_id: str, root: Path = inbox.INBOX_ROOT) -> Path:
    path = inbox.run_dir(run_id, root) / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(run_id, root), encoding="utf-8")
    return path
