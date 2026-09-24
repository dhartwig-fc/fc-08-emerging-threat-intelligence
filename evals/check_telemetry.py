"""
Pin the telemetry contract: one terminal event per tool call, and a refusal that reads as REFUSED.

Usage:
    python evals/check_telemetry.py
    python evals/check_telemetry.py --mutate refusal     # refusals classified as success; checks MUST fail

WHY. PLAN.md week 5: "telemetry for every decision". Probed 2026-09-24 (spec,
Section 3): PostToolUse carries duration_ms and the tool's reply; PostToolUseFailure
carries error and duration_ms; a DENIED call fires neither. So the Post hooks are
one source of terminal events and the permission callback (agents/permissions.py)
is the other. A governed refusal ("Rejected: ...") is the governance working and
must never read as SUCCESS -- today a refusal and a success look the same from
outside.

OFFLINE. Drives the real hook callbacks with inputs in the shapes the SDK was
measured to deliver. No model, no quota, no PDF. Writes only to a temp dir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import telemetry  # noqa: E402
from agents.run_identity import RunIdentity  # noqa: E402

telemetry.TELEMETRY_DIR = Path(tempfile.mkdtemp(prefix="fc08_telemetry_"))
RUN = RunIdentity(run_id="probe-telemetry", stage="extractor", advisory_id="ADV-2026-0002",
                  pdf_path=ROOT / "data" / "advisories" / "not-read.pdf", pdf_sha256="a" * 64)
SEARCH = "mcp__knowledge_centre__knowledge_centre_search_typologies"
PROPOSE = "mcp__knowledge_centre__knowledge_centre_propose_link"
GET = "mcp__knowledge_centre__knowledge_centre_get_typology"
REJECTION = "Rejected: 1 citation not found on the page named. Quote the page text verbatim."

# Input shapes measured 2026-09-24 (spec, Section 3, "Probed"). The dict-shaped
# response is the MCP result as a stdio server may deliver it; both must classify.
POST_OK = {"hook_event_name": "PostToolUse", "tool_name": SEARCH, "tool_use_id": "toolu_ok",
           "duration_ms": 41, "tool_input": {"query": "over invoicing"},
           "tool_response": [{"type": "text", "text": "TBML001 Over Invoicing (score 0.91)"}]}
POST_REFUSED = {"hook_event_name": "PostToolUse", "tool_name": PROPOSE, "tool_use_id": "toolu_ref",
                "duration_ms": 12, "tool_input": {}, "tool_response": [{"type": "text", "text": REJECTION}]}
POST_REFUSED_DICT = {"hook_event_name": "PostToolUse", "tool_name": PROPOSE, "tool_use_id": "toolu_ref2",
                     "duration_ms": 9, "tool_input": {},
                     "tool_response": {"content": [{"type": "text", "text": REJECTION}],
                                       "structuredContent": {"result": REJECTION}}}
POST_FAIL = {"hook_event_name": "PostToolUseFailure", "tool_name": GET, "tool_use_id": "toolu_fail",
             "duration_ms": 7, "tool_input": {}, "error": "boom: server raised", "is_interrupt": False}


def events() -> list:
    path = telemetry.telemetry_path(RUN)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fire(event_name: str, inp: dict) -> dict:
    hook = telemetry.tool_hooks(RUN)[event_name][0].hooks[0]
    return asyncio.run(hook(inp, inp.get("tool_use_id"), None))


def by_id(tool_use_id: str) -> list:
    return [e for e in events() if e["payload"].get("tool_use_id") == tool_use_id]


def hook_checks() -> list:
    out = []
    hooks = telemetry.tool_hooks(RUN)
    out.append((sorted(hooks) == ["PostToolUse", "PostToolUseFailure"],
                "tool_hooks supplies exactly the two Post hooks", str(sorted(hooks))))

    fire("PostToolUse", POST_OK)
    e = by_id("toolu_ok")
    out.append((len(e) == 1 and e[0]["stage"] == telemetry.TOOL_CALL and e[0]["status"] == telemetry.SUCCESS
                and e[0]["payload"]["latency_ms"] == 41 and e[0]["payload"]["tool"] == SEARCH,
                "a successful call leaves ONE FC08_TOOL_CALL event, SUCCESS, latency from duration_ms", str(e)[:160]))

    fire("PostToolUse", POST_REFUSED)
    e = by_id("toolu_ref")
    out.append((len(e) == 1 and e[0]["status"] == telemetry.REFUSED and "Rejected:" in e[0]["payload"]["outcome"],
                "a governed refusal (list-shaped reply) is REFUSED, not SUCCESS", str(e)[:160]))

    fire("PostToolUse", POST_REFUSED_DICT)
    e = by_id("toolu_ref2")
    out.append((len(e) == 1 and e[0]["status"] == telemetry.REFUSED,
                "a governed refusal (dict-shaped MCP reply) is REFUSED too", str(e)[:160]))

    fire("PostToolUseFailure", POST_FAIL)
    e = by_id("toolu_fail")
    out.append((len(e) == 1 and e[0]["status"] == telemetry.FAILURE and "boom" in e[0]["payload"]["outcome"]
                and e[0]["payload"]["latency_ms"] == 7,
                "a tool that raised leaves ONE FAILURE event carrying the error", str(e)[:160]))

    keys_ok = all(sorted(ev) == ["message", "payload", "stage", "status", "timestamp"] for ev in events())
    payload_ok = all({"run_id", "agent", "advisory_id", "tool", "tool_use_id", "latency_ms", "outcome"}
                     <= set(ev["payload"]) for ev in events() if ev["stage"] == telemetry.TOOL_CALL)
    out.append((bool(events()) and keys_ok and payload_ok,
                "every event has the portfolio shape; tool-call payloads carry all seven fields",
                "%d events" % len(events())))
    out.append((all(ev["payload"]["run_id"] == RUN.run_id and ev["payload"]["agent"] == "extractor"
                    and ev["payload"]["advisory_id"] == RUN.advisory_id for ev in events()),
                "every event names its run, agent and advisory", ""))

    started = telemetry.run_started(RUN, "claude-sonnet-5", 5.0, 60)
    done = telemetry.run_completed(RUN, telemetry.SUCCESS, "record validated", result=None, validated=True)
    out.append((started["stage"] == telemetry.RUN_STARTED and done["stage"] == telemetry.RUN_COMPLETED
                and done["payload"]["validated"] is True and started["payload"]["model"] == "claude-sonnet-5",
                "run_started and run_completed are recorded, the latter with its validated flag",
                "%s / %s" % (started["stage"], done["stage"])))
    return out


def all_checks() -> list:
    return hook_checks()


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the telemetry contract")
    ap.add_argument("--mutate", choices=("refusal",),
                    help="remove one rule; the checks that depend on it MUST fail")
    args = ap.parse_args(argv)

    if args.mutate == "refusal":
        telemetry.classify_response = lambda response: (telemetry.SUCCESS, "")
        print("MUTATED: every tool reply is classified SUCCESS.\n")

    failures = 0
    for ok, label, detail in all_checks():
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
