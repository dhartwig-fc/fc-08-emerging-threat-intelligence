"""
A Friday run's reconciliation, IN CODE, after every agent has stopped (spec sections 1 and 5).

Reads only what the run wrote -- items.json, triage.jsonl, extractions.jsonl, advisory_ids.jsonl,
extraction_runs.jsonl, records/, proposals/, telemetry/, run.json, refusal.json -- and answers:
  every listed item has one verdict, or it is UNFINISHED;
  every relevant item was extracted, or its failure, its budget deferral or its not being queued is REPORTED;
  every tool call of every session has exactly one terminal event (each session's terminal_check), and
  every session that started also completed.
Bookkeeping that does not add up is a PROBLEM, and any problem makes the run RECONCILIATION_FAILED, which
tools/accept_run.py refuses without an explicit, recorded override (spec section 5). Skipped work is not a
problem: it is UNFINISHED, and accept_run defers it to next Friday.

STATUS, first match wins: REFUSED (refusal.json) | FAILED (the orchestrator session failed: auth, credit,
the CLI) | RECONCILIATION_FAILED | UNFINISHED | NOTHING_NEW | COMPLETE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from feeds import extraction, inbox, triage as feeds_triage

RUN_JSON = "run.json"
REFUSAL = "refusal.json"
RESOLVER = "knowledge_centre_resolve_actor"
SOURCES = ("ofsi", "fincen", "ofac")
REFUSED, FAILED, RECON_FAILED, UNFINISHED, NOTHING_NEW, COMPLETE = (
    "REFUSED", "FAILED", "RECONCILIATION_FAILED", "UNFINISHED", "NOTHING_NEW", "COMPLETE")
ACCEPTABLE = (UNFINISHED, NOTHING_NEW, COMPLETE)


def _json(path: Path) -> Optional[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def session(path: Path) -> dict:
    """One session's telemetry file, summarised: who, whether it completed, its cost and terminal_check."""
    events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    started = [e for e in events if e["stage"] == "RUN_STARTED"]
    done = [e for e in events if e["stage"] == "RUN_COMPLETED"]
    last = done[-1]["payload"] if done else {}
    check = last.get("terminal_check") or {}
    resolver = [e for e in events if e["stage"] == "FC08_TOOL_CALL" and str(e["payload"].get("tool", "")).endswith(RESOLVER)]
    return {"run_id": path.stem, "agent": (started or events or [{"payload": {}}])[0]["payload"].get("agent"),
            "started": bool(started), "completed": bool(done), "status": done[-1]["status"] if done else None,
            "message": done[-1]["message"] if done else None, "cost_usd": last.get("cost_usd"),
            "turns": last.get("turns"), "limit": last.get("limit"), "validated": last.get("validated"),
            "calls": check.get("calls"), "unterminated": check.get("unterminated") or [],
            "duplicated": check.get("duplicated") or [],
            "from_transcript": sum(1 for e in events if e["payload"].get("source") == "transcript"),
            "resolver_calls": len(resolver),
            "resolved": sum(1 for e in resolver if str(e["payload"].get("outcome", "")).startswith("Resolved:"))}


def session_cost(path: Path) -> Optional[float]:
    return session(path)["cost_usd"] if Path(path).exists() else None


def reconcile_run(run_id: str, root: Path = inbox.INBOX_ROOT) -> dict:
    folder = inbox.run_dir(run_id, root)
    refusal = _json(folder / REFUSAL)
    run = _json(folder / RUN_JSON) or {}
    state = inbox.load(run_id, root)
    listed = {it["key"]: it for it in inbox.items(state)}
    verdicts = feeds_triage.load(run_id, root) if (folder / feeds_triage.TRIAGE).exists() else {}
    requests = {r["key"]: r for r in extraction.load_requests(run_id, root)}
    outcomes = extraction.load_outcomes(run_id, root)
    allocations = extraction.load_allocations(run_id, root)
    tel = folder / inbox.TELEMETRY
    sessions = [session(p) for p in sorted(tel.glob("*.jsonl"))] if tel.exists() else []
    problems: List[str] = []

    relevant = sorted(k for k, v in verdicts.items() if v["verdict"] == feeds_triage.RELEVANT)
    for k in sorted(set(verdicts) - set(listed)):
        problems.append("a verdict for %s, which this run did not list" % k)
    for k in sorted(set(requests) - set(relevant)):
        problems.append("an extraction request for %s, which has no relevant verdict" % k)
    orchestrator = next((s for s in sessions if s["run_id"] == run_id), None)
    ended = orchestrator is not None and orchestrator["completed"]
    for k in sorted(set(outcomes) - set(requests)):
        problems.append("an extraction outcome for %s, which was never requested" % k)
    if ended and orchestrator["status"] != "FAILURE":
        for k in sorted(set(requests) - set(outcomes)):
            problems.append("the extraction request for %s has no outcome" % k)
    extracted, failed, deferred = [], {}, []
    for k, o in sorted(outcomes.items()):
        if o["status"] == "extracted":
            extracted.append(k)
            record = _json(folder / (o.get("record") or "none")) if o.get("record") else None
            want_sha = (requests.get(k, {}).get("document") or {}).get("sha256")
            if record is None:
                problems.append("%s is recorded extracted but its record is missing" % k)
            elif record.get("advisory_id") != allocations.get(k) or record.get("advisory_id") != o.get("advisory_id"):
                problems.append("%s's record names %s, but the run allocated %s" % (k, record.get("advisory_id"),
                                                                                     allocations.get(k)))
            elif (record.get("source") or {}).get("document_sha256") != want_sha:
                problems.append("%s's record is not of the document its request pinned" % k)
        elif o["status"] == "deferred_budget":
            deferred.append(k)
        else:
            failed[k] = o.get("error") or o["status"]
    for s in sessions:
        if s["started"] and not s["completed"]:
            problems.append("session %s started and never completed" % s["run_id"])
        if s["unterminated"] or s["duplicated"]:
            problems.append("session %s: %d tool call(s) with no terminal event, %d with more than one" % (
                s["run_id"], len(s["unterminated"]), len(s["duplicated"])))
    if refusal is None and run and orchestrator is None:
        problems.append("the orchestrator session left no telemetry")

    source_state = {name: {k: v for k, v in st.items() if k in ("status", "error", "listed", "already_seen")}
                    for name, st in state["sources"].items()}
    never_listed = [s for s in SOURCES if s not in state["sources"]]
    source_failures = sorted(n for n, st in source_state.items() if st.get("status") not in (None, "ok"))
    unfinished = sorted(k for k in listed if k not in verdicts)
    not_queued = [k for k in relevant if k not in requests]
    known = [s["cost_usd"] for s in sessions if s["cost_usd"] is not None]
    if refusal is not None:
        status = REFUSED
    elif orchestrator is None or orchestrator["status"] == "FAILURE" or run.get("failure"):
        status = FAILED
    elif problems:
        status = RECON_FAILED
    elif unfinished or not_queued or failed or deferred or source_failures or never_listed:
        status = UNFINISHED
    elif not listed:
        status = NOTHING_NEW
    else:
        status = COMPLETE
    return {"run_id": run_id, "status": status, "refusal": refusal, "failure": run.get("failure"),
            "sources": source_state, "never_listed_sources": never_listed, "source_failures": source_failures,
            "listed": sorted(listed), "verdicts": verdicts, "unfinished": unfinished, "relevant": relevant,
            "not_relevant": sorted(k for k, v in verdicts.items() if v["verdict"] == feeds_triage.NOT_RELEVANT),
            "queued": sorted(requests), "extracted": extracted, "failed": failed, "deferred_budget": deferred,
            "not_queued": not_queued, "allocations": allocations, "sessions": sessions, "problems": problems,
            "spent_usd": run.get("spent_usd"), "known_cost_usd": round(sum(known), 6),
            "unknown_cost_sessions": sum(1 for s in sessions if s["cost_usd"] is None)}
