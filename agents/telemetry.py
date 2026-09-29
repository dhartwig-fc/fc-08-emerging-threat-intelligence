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
  - A call the CLI REFUSED before any hook ran (input that "could not be parsed as
    JSON", measured 2026-09-27) fires neither and reaches no callback. Its is_error
    tool_result in the transcript is the terminal event: record_unhooked (slice 2 C).
    A SUCCESS result never qualifies -- see record_unhooked.
  - A structured-output MCP tool's reply reaches PostToolUse as a JSON-encoded
    STRING, not a dict -- measured live 2026-09-24 on knowledge_centre_propose_link:
    the reply arrives as '{"result": "Rejected: ..."}', so _texts() must decode a
    str that looks like JSON before it can see the refusal inside it. It decodes
    that ENVELOPE once and never the tool's data inside it (see _texts).
A PreToolUse hook is not used: the Post inputs already carry duration_ms.
That is the design. Whether a given run achieved it is reconcile()'s answer,
recorded in RUN_COMPLETED as terminal_check.

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
    """Every text string in a tool reply, whatever shape the transport delivers it in.

    DECODE THE TRANSPORT ENVELOPE, NEVER THE TOOL'S DATA. A top-level string that
    parses as a JSON object or array is decoded ONCE; inside it, strings are taken
    as they are. get_typology returns json.dumps(record), so its "result" is itself
    a JSON document -- decoding that too found no text keys and recorded every
    get_typology SUCCESS with an empty outcome, and would have read a record
    holding "text": "Rejected: ..." as a refusal (final review, 2026-09-24).
    """
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped[:1] in ("{", "["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [obj]
            if isinstance(parsed, (dict, list)):
                return _envelope_texts(parsed) or [obj]
        return [obj]
    return _envelope_texts(obj)


def _envelope_texts(obj) -> list:
    """Walk the MCP envelope: content / result / structuredContent / list items.

    A string found here is text, never JSON to decode -- it is the tool's own reply.
    """
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        found = [obj["text"]] if isinstance(obj.get("text"), str) else []
        for key in ("content", "result", "structuredContent"):
            if key in obj:
                found += _envelope_texts(obj[key])
        return found
    if isinstance(obj, (list, tuple)):
        return [t for item in obj for t in _envelope_texts(item)]
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


def terminated(run) -> set:
    """The tool_use ids this run's telemetry already holds a terminal event for."""
    path = telemetry_path(run)
    out = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = json.loads(line)
                if event.get("stage") in (TOOL_CALL, PERMISSION_DENIED):
                    out.add(event.get("payload", {}).get("tool_use_id"))
    return out


def record_unhooked(run, calls: dict, results: dict) -> list:
    """The ONE terminal event for each call the CLI answered before any hook ran (slice 2 C).

    Measured in B's pilot transcript (2026-09-27): three feeds_triage calls whose input "could not be
    parsed as JSON" were each answered by a tool_result with is_error -- and fired no hook and no
    permission callback, so the run's telemetry held nothing for them and terminal_check called them
    unterminated. The runner saw both halves in the message stream. `calls` is tool_use_id -> tool name,
    `results` tool_use_id -> (is_error, text); a call with an is_error result and no terminal event gets
    one FAILURE event here, marked source "transcript" so the evidence says where it came from.

    ONLY an is_error result, the class that was measured. A call that ran and succeeded ALWAYS fires
    PostToolUse, so a SUCCESS result with no event means the hook failed to record -- an emit that raised,
    a hook dropped at runtime -- which is exactly what terminal_check exists to catch. Backfilling it would
    report `unterminated: []` over that defect (Task 3 review, Important 1). It stays unterminated. A call
    with NEITHER a result nor an event stays unterminated too: nothing is invented.
    """
    done = terminated(run)
    out = []
    for tool_use_id, tool in calls.items():
        if tool_use_id in done or tool_use_id not in results:
            continue
        is_error, text = results[tool_use_id]
        if not is_error:
            continue  # a success with no hook event is a hook that failed: leave it for terminal_check
        out.append(emit(run, TOOL_CALL, FAILURE, "%s failure (answered by the CLI; no hook fired)" % tool,
                        tool=tool, tool_use_id=tool_use_id, latency_ms=None, outcome=(text or "")[:200],
                        source="transcript"))
    return out


def reconcile(run, tool_use_ids) -> dict:
    """Did THIS run leave exactly one terminal event per tool call? Read, not assumed.

    The hooks and the callback are built to leave one each, and check_telemetry.py
    proves they can. A real run can still leave zero -- an emit that raised inside a
    hook, a cancelled callback, a call cut off by max_turns or the budget -- and
    nothing downstream would notice. So each runner passes every ToolUseBlock id it
    saw, and the answer goes into RUN_COMPLETED as terminal_check. A non-empty list
    is RECORDED, never raised: a run's evidence must not be lost to its own
    bookkeeping.
    """
    ids = list(dict.fromkeys(tool_use_ids))
    counts = dict.fromkeys(ids, 0)
    path = telemetry_path(run)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            tool_use_id = event.get("payload", {}).get("tool_use_id")
            if event.get("stage") in (TOOL_CALL, PERMISSION_DENIED) and tool_use_id in counts:
                counts[tool_use_id] += 1
    return {"calls": len(ids),
            "unterminated": [i for i in ids if counts[i] == 0],
            "duplicated": [i for i in ids if counts[i] > 1]}


def run_started(run, model: str, max_budget_usd: float, max_turns: int, tools, prompt_sha256: str = None) -> dict:
    """`tools` is every qualified tool name the agent can call. It is recorded so what a run HAD is
    measured, not inferred from its date (the walkthrough's section 10 counts it).

    `prompt_sha256` is the sha256 of the prompt this run was actually sent (owner decision, 2026-09-29,
    before Task 9's first live dry run): the spec measures a resolver change "by the resolution rate on
    live runs", and a run can only be tied to the prompt it ran under if its own telemetry says which
    prompt that was. Recorded as `null` when not passed, never omitted, so a caller that does not pass it
    reads the same as a run from before this field existed: absent or null both mean "not recorded"."""
    return emit(run, RUN_STARTED, SUCCESS, "%s run started" % run.stage, model=model,
                max_budget_usd=max_budget_usd, max_turns=max_turns, pdf_sha256=run.pdf_sha256,
                tools=list(tools), prompt_sha256=prompt_sha256)


def run_completed(run, status: str, message: str, *, result=None, validated: bool = False, **extra) -> dict:
    """The run's closing event. `extra` is merged into the payload -- the runners pass
    terminal_check=reconcile(...) so the invariant is recorded per run, not assumed."""
    return emit(run, RUN_COMPLETED, status, message, validated=validated,
                turns=getattr(result, "num_turns", None), cost_usd=getattr(result, "total_cost_usd", None),
                duration_ms=getattr(result, "duration_ms", None),
                permission_denials=len(getattr(result, "permission_denials", None) or []) if result else None,
                **extra)
