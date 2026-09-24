"""
Telemetry for every tool call and every permission decision in a run.

PLAN.md week 5: "telemetry for every decision". Events use the portfolio's
Enterprise Telemetry shape -- {stage, status, timestamp, message, payload} --
with the plan's fields (agent, tool, latency, outcome) in the payload, and go to
data/telemetry/<run_id>.jsonl, TRACKED, so every run a proposal names can be
traced from a clone.

EXACTLY ONE TERMINAL EVENT PER TOOL CALL, from one of three places. Probed
2026-09-24 against SDK 0.2.152 (spec, Section 3):
  - PostToolUse fires for a call that ran; it carries duration_ms and the tool's
    reply. A reply beginning "Rejected:" is a governed refusal -> REFUSED.
  - PostToolUseFailure fires for a call that raised; it carries error and
    duration_ms -> FAILURE.
  - A call the permission callback DENIED fires neither. agents/permissions.py
    records that call's PERMISSION_DENIED event; it is the terminal one.
  - A structured-output MCP tool's reply reaches PostToolUse as a JSON-encoded
    STRING, not a dict -- measured live 2026-09-24 on knowledge_centre_propose_link:
    the reply arrives as '{"result": "Rejected: ..."}', so _texts() must decode a
    str that looks like JSON before it can see the refusal inside it.
A PreToolUse hook is not used: the Post inputs already carry duration_ms.

A REFUSAL IS NOT A SUCCESS. Before week 5, a propose_link that the server
refused looked, from outside, exactly like one it accepted. The refusals are the
governance working, so they are counted separately.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import HookMatcher

ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_DIR = ROOT / "data" / "telemetry"

TOOL_CALL = "FC08_TOOL_CALL"
PERMISSION_ALLOWED = "PERMISSION_ALLOWED"
PERMISSION_DENIED = "PERMISSION_DENIED"
RUN_STARTED = "RUN_STARTED"
RUN_COMPLETED = "RUN_COMPLETED"
SUCCESS, REFUSED, FAILURE, ALLOWED, DENIED = "SUCCESS", "REFUSED", "FAILURE", "ALLOWED", "DENIED"
REFUSAL_PREFIX = "Rejected:"


def telemetry_path(run) -> Path:
    # Read TELEMETRY_DIR at call time so a guard can redirect it.
    return TELEMETRY_DIR / ("%s.jsonl" % run.run_id)


def emit(run, stage: str, status: str, message: str, **payload) -> dict:
    event = {
        "stage": stage,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "message": message,
        "payload": {"run_id": run.run_id, "agent": run.stage, "advisory_id": run.advisory_id, **payload},
    }
    path = telemetry_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def _texts(obj) -> list:
    """Every text string in a tool reply, whatever shape the transport delivers it in."""
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped[:1] in ("{", "["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [obj]
            if isinstance(parsed, (dict, list)):
                return _texts(parsed)
        return [obj]
    if isinstance(obj, dict):
        found = [obj["text"]] if isinstance(obj.get("text"), str) else []
        for key in ("content", "result", "structuredContent"):
            if key in obj:
                found += _texts(obj[key])
        return found
    if isinstance(obj, (list, tuple)):
        return [t for item in obj for t in _texts(item)]
    return []


def classify_response(tool_response) -> tuple:
    """(status, outcome) for a call that ran: REFUSED if any reply text is a governed refusal."""
    texts = [t.strip() for t in _texts(tool_response) if t and t.strip()]
    for t in texts:
        if t.startswith(REFUSAL_PREFIX):
            return REFUSED, t[:200]
    return SUCCESS, (texts[0][:200] if texts else "")


def tool_hooks(run) -> dict:
    """PostToolUse and PostToolUseFailure hooks that write one terminal event per call."""

    async def post(input_data, tool_use_id, context):
        status, outcome = classify_response(input_data.get("tool_response"))
        tool = input_data.get("tool_name")
        emit(run, TOOL_CALL, status, "%s %s" % (tool, status.lower()), tool=tool,
             tool_use_id=input_data.get("tool_use_id") or tool_use_id,
             latency_ms=input_data.get("duration_ms"), outcome=outcome)
        return {}

    async def post_failure(input_data, tool_use_id, context):
        tool = input_data.get("tool_name")
        emit(run, TOOL_CALL, FAILURE, "%s raised" % tool, tool=tool,
             tool_use_id=input_data.get("tool_use_id") or tool_use_id,
             latency_ms=input_data.get("duration_ms"), outcome=str(input_data.get("error"))[:200],
             interrupted=bool(input_data.get("is_interrupt")))
        return {}

    return {"PostToolUse": [HookMatcher(matcher=None, hooks=[post])],
            "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[post_failure])]}


def run_started(run, model: str, max_budget_usd: float, max_turns: int) -> dict:
    return emit(run, RUN_STARTED, SUCCESS, "%s run started" % run.stage, model=model,
                max_budget_usd=max_budget_usd, max_turns=max_turns, pdf_sha256=run.pdf_sha256)


def run_completed(run, status: str, message: str, *, result=None, validated: bool = False) -> dict:
    return emit(run, RUN_COMPLETED, status, message, validated=validated,
                turns=getattr(result, "num_turns", None), cost_usd=getattr(result, "total_cost_usd", None),
                duration_ms=getattr(result, "duration_ms", None),
                permission_denials=len(getattr(result, "permission_denials", None) or []) if result else None)
