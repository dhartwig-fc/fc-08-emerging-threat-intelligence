"""
Prove the triage-only orchestrator can reach the four feeds tools and nothing else (slice 2 B).

Usage:
    python evals/check_feeds_orchestrator.py
    python evals/check_feeds_orchestrator.py --mutate builtin-tools     # the base tool set is not removed
    python evals/check_feeds_orchestrator.py --mutate settings          # the operator's settings are inherited
    python evals/check_feeds_orchestrator.py --mutate preapprove-triage # feeds_triage bypasses the callback
    python evals/check_feeds_orchestrator.py --mutate allow-propose     # the callback allows propose_link
    python evals/check_feeds_orchestrator.py --mutate extract-tool      # an extraction tool reaches triage-only mode
    python evals/check_feeds_orchestrator.py --mutate no-asymmetry      # the prompt loses "when in doubt, keep it"
    python evals/check_feeds_orchestrator.py --mutate error-dropped     # a failed attempt's record loses its error
    python evals/check_feeds_orchestrator.py --mutate unrecorded-raise  # a session that raises kills the runner unrecorded
    python evals/check_feeds_orchestrator.py --mutate retry-forever     # a repeated bug is re-run, and re-spent, again

WHAT IT HOLDS (spec sections 1 and 4; the same questions evals/check_tool_surface.py asks of the
extraction agent, asked of this one):
  no built-ins   tools=[] and the argv carries --tools "", setting_sources=[], strict_mcp_config;
  one server     the feeds server only, started with the run's identity and nothing the agent chose;
  reads only     allowed_tools pre-approves exactly feeds_read_page, in options and in the argv, with no
  pre-approved   permission mode or skip flag, so every tool that writes reaches the callback;
  the callback   ALLOWS list_new, fetch and triage; DENIES propose_link, an extraction tool and Bash;
  the lists      AGENT_TOOLS is exactly the server's tools, split exactly into the write allowlist and
                 the read-only tools, and the read-only annotation agrees -- a tool added to the server
                 is added to these lists or this guard fails;
  identity       FeedsRun refuses a malformed run id, a half-set eval mode and a batch over the cap;
  telemetry      the Post hooks are installed; the SDK's shadowing advisory names only feeds_read_page
                 and expected_shadowing() silences that one and no other;
  the prompt     states the spec's asymmetry ("When in doubt, keep it") and PROMPT_SHA256 is its hash.

AND THE RUNNER'S FAILURES (evals/run_feeds_triage.py; the Task 4 review ruling). run_triage records an
unexpected exception as a failure and the runner re-runs failed batches, so a bug could be re-run and
re-spent without limit. Driven through run_plan with sessions that fail, never a model:
  error recorded   a failed attempt keeps `error` "<Type>: <message>" and its kind: through the REAL
                   run_triage (its SDK loop patched to raise KeyError), through a session that raises
                   itself (recorded with its traceback, not a dead runner), and "sdk" for the SDK's
                   own errors and an agent error result;
  stops on repeat  the same non-SDK error twice in a row (run id normalised out) prints STOPPED and a
                   third invocation starts NO session; --after-fix buys exactly one more; the same SDK
                   error, or two different bugs, do not stop it.

STATIC. No model, no network: the options object, the argv the SDK would build, and the installed
callback asked directly. Each --mutate changes the options or a module constant in memory.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from agents import telemetry  # noqa: E402

telemetry.TELEMETRY_DIR = Path(tempfile.mkdtemp(prefix="fc08_orchestrator_telemetry_"))  # never data/telemetry/
from agents import orchestrate_feeds as of  # noqa: E402
from agents.permissions import FEEDS_READ_ONLY_TOOLS, PROPOSE_TOOL, expected_shadowing  # noqa: E402
from check_tool_surface import built_command  # noqa: E402

MUTATIONS = ("builtin-tools", "settings", "preapprove-triage", "allow-propose", "extract-tool", "no-asymmetry",
             "error-dropped", "unrecorded-raise", "retry-forever")
RUN = of.FeedsRun("feeds-2026-10-02-fff555")
EVAL_RUN = of.FeedsRun("feeds-2026-10-02-fff666", catalogue=ROOT / "evals" / "feeds" / "catalogue.json",
                       batch=("ofsi:0123456789abcdef",))
TRIAGE = "mcp__feeds__feeds_triage"


def checks(mutation) -> list:
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    from claude_agent_sdk import types as sdk_types
    from claude_agent_sdk.types import ToolPermissionContext
    from mcp_server import feeds_server

    if mutation == "allow-propose":
        of.FEEDS_WRITE_ALLOWLIST = of.FEEDS_WRITE_ALLOWLIST | {PROPOSE_TOOL}
    if mutation == "extract-tool":
        of.AGENT_TOOLS = of.AGENT_TOOLS + ("mcp__feeds__feeds_extract",)
    if mutation == "no-asymmetry":
        of.TRIAGE_PROMPT = of.TRIAGE_PROMPT.replace("When in doubt, keep it", "When in doubt, drop it")
    o = of.agent_options(RUN)
    if mutation == "builtin-tools":
        o = dataclasses.replace(o, tools=None)
    if mutation == "settings":
        o = dataclasses.replace(o, setting_sources=["user", "project"])
    if mutation == "preapprove-triage":
        o = dataclasses.replace(o, allowed_tools=list(o.allowed_tools) + [TRIAGE])

    out = []
    cmd = built_command(o)
    pairs = list(zip(cmd, cmd[1:]))
    out.append((o.tools == [] and ("--tools", "") in pairs, 'tools=[] and the argv carries --tools ""',
                "tools=%r" % (o.tools,)))
    out.append((o.setting_sources == [] and o.strict_mcp_config is True,
                "setting_sources=[] and strict_mcp_config: nothing inherited from the machine",
                "setting_sources=%r" % (o.setting_sources,)))
    server = o.mcp_servers.get("feeds", {})
    out.append((list(o.mcp_servers) == ["feeds"] and server.get("args") == [str(of.SERVER_PATH)]
                and server.get("env") == {"FEEDS_RUN_ID": RUN.run_id},
                "one MCP server, the feeds server, started with the run's identity only", sorted(server.get("env", {}))))
    allowed_arg = cmd[cmd.index("--allowedTools") + 1] if "--allowedTools" in cmd else ""
    out.append((list(o.allowed_tools) == list(FEEDS_READ_ONLY_TOOLS) and allowed_arg.split(",") == list(FEEDS_READ_ONLY_TOOLS)
                and "--permission-mode" not in cmd and "--dangerously-skip-permissions" not in cmd
                and o.permission_prompt_tool_name is None and o.output_format is None,
                "only feeds_read_page is pre-approved, in options and argv, and nothing bypasses the callback",
                "--allowedTools %s" % allowed_arg))

    ctx = ToolPermissionContext(tool_use_id="static")
    ask = lambda name: asyncio.run(o.can_use_tool(name, {}, ctx))  # noqa: E731
    allows = {t: isinstance(ask("mcp__feeds__%s" % t), PermissionResultAllow)
              for t in ("feeds_list_new", "feeds_fetch", "feeds_triage")}
    denies = {t: isinstance(ask(t), PermissionResultDeny)
              for t in (PROPOSE_TOOL, "mcp__feeds__feeds_extract", "Bash")}
    out.append((all(allows.values()) and all(denies.values()),
                "the installed callback allows list, fetch and triage, and denies propose_link, extract and Bash",
                "allows %s; denies %s" % (allows, denies)))

    listed = asyncio.run(feeds_server.mcp.list_tools())
    names = sorted("mcp__feeds__%s" % t.name for t in listed)
    ro = sorted("mcp__feeds__%s" % t.name for t in listed
                if t.annotations is not None and getattr(t.annotations, "read_only_hint", False))
    out.append((sorted(of.AGENT_TOOLS) == names
                and set(of.FEEDS_WRITE_ALLOWLIST) | set(FEEDS_READ_ONLY_TOOLS) == set(names)
                and not set(of.FEEDS_WRITE_ALLOWLIST) & set(FEEDS_READ_ONLY_TOOLS) and ro == list(FEEDS_READ_ONLY_TOOLS),
                "AGENT_TOOLS is exactly the server's tools, split into the write allowlist and the read-only tools",
                names))

    refused = []
    for kwargs in ({"run_id": "not-a-run"}, {"run_id": RUN.run_id, "batch": ("ofsi:0123456789abcdef",)},
                   {"run_id": RUN.run_id, "catalogue": Path("c.json"),
                    "batch": tuple("ofsi:%016x" % i for i in range(11))}):
        try:
            of.FeedsRun(**kwargs)
        except ValueError:
            refused.append(True)
    env = EVAL_RUN.env()
    out.append((len(refused) == 3 and env["FEEDS_CATALOGUE_BATCH"] == "ofsi:0123456789abcdef"
                and Path(env["FEEDS_CATALOGUE"]).is_absolute(),
                "FeedsRun refuses a bad run id, a half-set eval mode and a batch over the cap of 10", sorted(env)))

    out.append((sorted(o.hooks or {}) == ["PostToolUse", "PostToolUseFailure"],
                "the Post hooks are installed for telemetry", str(sorted(o.hooks or {}))))
    msg = sdk_types._get_can_use_tool_shadowed_warning(o.permission_mode, list(o.allowed_tools)) or ""
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with expected_shadowing(FEEDS_READ_ONLY_TOOLS):
            warnings.warn(msg, sdk_types.CanUseToolShadowedWarning)
            warnings.warn("can_use_tool will not be invoked for: %s. x" % TRIAGE, sdk_types.CanUseToolShadowedWarning)
    out.append((msg.startswith("can_use_tool will not be invoked for: %s." % FEEDS_READ_ONLY_TOOLS[0])
                and len(seen) == 1 and TRIAGE in str(seen[0].message),
                "the shadowing advisory names only feeds_read_page, and only that advisory is silenced", msg[:70]))

    out.append(("When in doubt, keep it" in o.system_prompt
                and hashlib.sha256(of.TRIAGE_PROMPT.encode("utf-8")).hexdigest() == of.PROMPT_SHA256
                and "extract" not in o.system_prompt.replace("You do not extract", "").replace("worth extracting", ""),
                "the prompt states the asymmetry, offers no extraction, and PROMPT_SHA256 is its hash",
                of.PROMPT_SHA256[:16]))
    return out


def runner_checks(mutation) -> list:
    import contextlib
    import io
    from datetime import date

    import run_feeds_triage as rf

    if mutation == "error-dropped":
        rf.failure_record = lambda summary: dict(summary, error_kind=rf.error_kind(str(summary["failure"])))
    if mutation == "unrecorded-raise":
        rf.attempt = lambda session, run: dict(asyncio.run(session(run)))  # the runner as first drafted
    if mutation == "retry-forever":
        rf.repeated_code_error = lambda failed_attempts, batch: None
    tmp = Path(tempfile.mkdtemp(prefix="fc08_runner_"))
    plan = [("batch-1", ["ofsi:0123456789abcdef"])]

    def counted(fn):
        async def session(run):
            session.calls += 1
            return await fn(run)
        session.calls = 0
        return session

    def invoke(session, progress, after_fix=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = rf.run_plan("rep1", plan, progress, tmp / "progress.json", session, date(2026, 10, 2),
                                   pilot=True, after_fix=after_fix)
            except Exception as exc:  # the runner died: nothing was recorded for this attempt
                code = "died: %s: %s" % (type(exc).__name__, exc)
        return code, out.getvalue()

    async def broken_query(**kwargs):  # the SDK loop raising a bug, not an SDK error
        raise KeyError("page")
        yield  # noqa: unreachable -- makes this an async generator, as query() is

    async def real_triage(run):
        return await of.run_triage(run, inbox_root=tmp / "inbox")

    async def raises(run):
        raise ValueError("boom in the runner's session")

    async def raises_with_run_id(run):
        raise FileNotFoundError("inbox/%s/items.json" % run.run_id)

    def returns(failure):
        async def session(run):
            return {"run_id": run.run_id, "failure": failure, "limit": None, "cost_usd": 0.01, "turns": 1}
        return session

    real_query = of.query
    of.query = broken_query
    try:
        out = []
        # error recorded
        seen = {}
        for label, session in (("run_triage", real_triage), ("raised", raises),
                               ("sdk", returns("CLIConnectionError: not logged in")),
                               ("agent", returns("agent run failed: ['credit balance too low']"))):
            progress = {"sessions": {}, "failed_attempts": []}
            code, _ = invoke(session, progress)
            a = progress["failed_attempts"][-1] if progress["failed_attempts"] else {}
            seen[label] = (code, a.get("error"), a.get("error_kind"), "traceback" in a
                           and "ValueError: boom" in a.get("traceback", ""))
        out.append((seen["run_triage"][:3] == (1, "KeyError: 'page'", "code")
                    and seen["raised"][:3] == (1, "ValueError: boom in the runner's session", "code") and seen["raised"][3]
                    and seen["sdk"][1:3] == ("CLIConnectionError: not logged in", "sdk")
                    and seen["agent"][2] == "sdk",
                    "a failed attempt records its error's type and message (run_triage's and a raised session's, "
                    "with its traceback) and whether the SDK raised it", seen))

        # stops on repeat
        calls = {}
        for label, fn in (("bug", real_triage), ("bug-with-run-id", raises_with_run_id),
                          ("sdk", returns("CLIConnectionError: not logged in"))):
            progress, session = {"sessions": {}, "failed_attempts": []}, counted(fn)
            outs = [invoke(session, progress)[1] for _ in range(3)]
            calls[label] = (session.calls, "STOPPED" in outs[1] and "STOPPED" in outs[2])
            if label == "bug":
                after = invoke(session, progress, after_fix=True)[1]
                again = invoke(session, progress)[1]
                calls["after-fix"] = (session.calls, "STOPPED" in after and "STOPPED" in again)
        two_bugs = {"sessions": {}, "failed_attempts": []}
        differ = counted(returns("KeyError: 'a'"))
        invoke(differ, two_bugs)
        invoke(counted(returns("TypeError: b")), two_bugs)
        invoke(differ, two_bugs)
        calls["two-bugs"] = (differ.calls, False)
        out.append((calls == {"bug": (2, True), "bug-with-run-id": (2, True), "sdk": (3, False),
                              "after-fix": (3, True), "two-bugs": (2, False)},
                    "the same non-SDK error twice in a row STOPS the runner: a third invocation starts no session, "
                    "--after-fix buys one; SDK errors and different bugs do not stop it", calls))
        return out
    finally:
        of.query = real_query


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Prove the triage-only orchestrator's tool surface")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate) + runner_checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
