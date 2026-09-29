"""
Prove the orchestrator reaches its mode's tools and nothing else, and pin the run's budget (slice 2 B, C).

Usage:
    python evals/check_feeds_orchestrator.py
    python evals/check_feeds_orchestrator.py --mutate builtin-tools      # the base tool set is not removed
    python evals/check_feeds_orchestrator.py --mutate settings           # the operator's settings are inherited
    python evals/check_feeds_orchestrator.py --mutate preapprove-triage  # feeds_triage bypasses the callback
    python evals/check_feeds_orchestrator.py --mutate allow-propose      # the callback allows propose_link
    python evals/check_feeds_orchestrator.py --mutate extract-tool       # an extraction tool reaches triage-only mode
    python evals/check_feeds_orchestrator.py --mutate no-asymmetry       # the prompt loses "when in doubt, keep it"
    python evals/check_feeds_orchestrator.py --mutate extract-in-eval    # an eval run's callback allows feeds_extract
    python evals/check_feeds_orchestrator.py --mutate inherit-catalogue  # a live server inherits FEEDS_CATALOGUE
    python evals/check_feeds_orchestrator.py --mutate triage-drift       # a live run's triage instructions differ from B's
    python evals/check_feeds_orchestrator.py --mutate unpinned-budget    # the session cap moves off US$1.50
    python evals/check_feeds_orchestrator.py --mutate over-ceiling       # the caps no longer fit the US$5 ceiling
    python evals/check_feeds_orchestrator.py --mutate stale-full-hash    # FULL_PROMPT_SHA256 no longer matches FULL_PROMPT

WHAT IT HOLDS (spec sections 1 and 4; the questions evals/check_tool_surface.py asks of the extractor):
  no built-ins   tools=[] and the argv carries --tools "", setting_sources=[], strict_mcp_config -- both modes;
  one server     the feeds server only, with the run's identity: an EVAL run's catalogue and batch, and a
                 LIVE run's FEEDS_CATALOGUE and FEEDS_CATALOGUE_BATCH set EMPTY, so a shell export cannot
                 turn a Friday run into an eval run (B carry-forward);
  reads only     allowed_tools pre-approves exactly feeds_read_page, and nothing bypasses the callback;
  the callback   EVAL allows list, fetch, triage and DENIES feeds_extract; LIVE allows those and feeds_extract;
                 both DENY propose_link and Bash;
  the lists      AGENT_TOOLS is exactly an EVAL server's tools and FULL_AGENT_TOOLS a LIVE server's, each split
                 into the mode's write allowlist and the read-only tools;
  identity       FeedsRun refuses a malformed run id, a half-set eval mode and a batch over the cap of 10;
  telemetry      the Post hooks are installed; the shadowing advisory names only feeds_read_page;
  the prompts    triage-only states the asymmetry, offers no extraction, and PROMPT_SHA256 is its hash; the
                 LIVE prompt BEGINS with those exact bytes and adds the extraction step (at most 3);
                 FULL_PROMPT_SHA256 is the sha256 of FULL_PROMPT itself -- the value run_session() passes
                 telemetry.run_started for a live run (prompt-sha brief, 2026-09-29). Neither this guard nor
                 check_friday_run.py drives run_session() far enough to reach that call without a model, so
                 this pins the constant, not the call site;
  the budget     pinned: US$1.50 and 80 turns per session, US$1.00 and 60 turns per extraction, 3
                 extractions and 10 verdicts per run, a US$5.00 ceiling -- and session + 3 extractions fits it.

STATIC. No model, no network. Each --mutate changes the options or a module constant in memory.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import os
import sys
import tempfile
import types
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
from feeds import extraction as feeds_extraction, triage as feeds_triage  # noqa: E402

MUTATIONS = ("builtin-tools", "settings", "preapprove-triage", "allow-propose", "extract-tool", "no-asymmetry",
             "extract-in-eval", "inherit-catalogue", "triage-drift", "unpinned-budget", "over-ceiling",
             "stale-full-hash")
LIVE = of.FeedsRun("feeds-2026-10-02-fff555")
EVAL_RUN = of.FeedsRun("feeds-2026-10-02-fff666", catalogue=ROOT / "evals" / "feeds" / "catalogue.json",
                       batch=("ofsi:0123456789abcdef",))
TRIAGE = "mcp__feeds__feeds_triage"
EXTRACT = "mcp__feeds__feeds_extract"
SERVER = ROOT / "mcp_server" / "feeds_server.py"
PINNED = {"MAX_BUDGET_USD": 1.50, "MAX_TURNS": 80, "RUN_CEILING_USD": 5.00, "EXTRACTION_BUDGET_USD": 1.00,
          "EXTRACTION_MAX_TURNS": 60}


def server_tools(eval_mode: bool) -> tuple:
    """(names, read-only names) of a feeds server started in the given mode, loaded afresh from source."""
    if eval_mode:
        os.environ["FEEDS_CATALOGUE"] = str(ROOT / "evals" / "feeds" / "catalogue.json")
    try:
        module = types.ModuleType("feeds_server_mode_%s" % eval_mode)
        module.__file__ = str(SERVER)
        exec(compile(SERVER.read_text(encoding="utf-8"), str(SERVER), "exec"), module.__dict__)
        listed = asyncio.run(module.mcp.list_tools())
    finally:
        os.environ.pop("FEEDS_CATALOGUE", None)
    names = sorted("mcp__feeds__%s" % t.name for t in listed)
    ro = sorted("mcp__feeds__%s" % t.name for t in listed
                if t.annotations is not None and getattr(t.annotations, "read_only_hint", False))
    return names, ro


def surface(o, run, mutation) -> list:
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    from claude_agent_sdk.types import ToolPermissionContext
    mode = "live" if run.live else "eval"
    if mutation == "builtin-tools":
        o = dataclasses.replace(o, tools=None)
    if mutation == "settings":
        o = dataclasses.replace(o, setting_sources=["user", "project"])
    if mutation == "preapprove-triage":
        o = dataclasses.replace(o, allowed_tools=list(o.allowed_tools) + [TRIAGE])
    out = []
    cmd = built_command(o)
    pairs = list(zip(cmd, cmd[1:]))
    out.append((o.tools == [] and ("--tools", "") in pairs and o.setting_sources == [] and o.strict_mcp_config is True,
                '%s: tools=[] and --tools "", setting_sources=[], strict_mcp_config' % mode,
                "tools=%r setting_sources=%r" % (o.tools, o.setting_sources)))
    server = o.mcp_servers.get("feeds", {})
    want_env = run.env() if not run.live else {"FEEDS_RUN_ID": run.run_id, "FEEDS_CATALOGUE": "",
                                                 "FEEDS_CATALOGUE_BATCH": ""}
    out.append((list(o.mcp_servers) == ["feeds"] and server.get("args") == [str(of.SERVER_PATH)]
                and server.get("env") == want_env,
                "%s: one MCP server, the feeds server, with the run's identity%s" % (
                    mode, " and the eval variables set EMPTY" if run.live else ""), server.get("env")))
    allowed_arg = cmd[cmd.index("--allowedTools") + 1] if "--allowedTools" in cmd else ""
    out.append((list(o.allowed_tools) == list(FEEDS_READ_ONLY_TOOLS) and allowed_arg.split(",") == list(FEEDS_READ_ONLY_TOOLS)
                and "--permission-mode" not in cmd and "--dangerously-skip-permissions" not in cmd
                and o.permission_prompt_tool_name is None and o.output_format is None,
                "%s: only feeds_read_page is pre-approved, and nothing bypasses the callback" % mode,
                "--allowedTools %s" % allowed_arg))
    ctx = ToolPermissionContext(tool_use_id="static")
    ask = lambda name: asyncio.run(o.can_use_tool(name, {}, ctx))  # noqa: E731
    allows = {t: isinstance(ask("mcp__feeds__%s" % t), PermissionResultAllow)
              for t in ("feeds_list_new", "feeds_fetch", "feeds_triage")}
    extract_allowed = isinstance(ask(EXTRACT), PermissionResultAllow)
    denies = {t: isinstance(ask(t), PermissionResultDeny) for t in (PROPOSE_TOOL, "Bash")}
    out.append((all(allows.values()) and all(denies.values()) and extract_allowed == run.live,
                "%s: the callback allows list, fetch and triage, %s feeds_extract, and denies propose_link and Bash"
                % (mode, "ALLOWS" if run.live else "DENIES"),
                "allows %s; extract allowed %s; denies %s" % (allows, extract_allowed, denies)))
    out.append((sorted(o.hooks or {}) == ["PostToolUse", "PostToolUseFailure"],
                "%s: the Post hooks are installed for telemetry" % mode, str(sorted(o.hooks or {}))))
    return out


def checks(mutation) -> list:
    from claude_agent_sdk import types as sdk_types
    if mutation == "allow-propose":
        of.FEEDS_WRITE_ALLOWLIST = of.FEEDS_WRITE_ALLOWLIST | {PROPOSE_TOOL}
        of.FEEDS_FULL_WRITE_ALLOWLIST = of.FEEDS_FULL_WRITE_ALLOWLIST | {PROPOSE_TOOL}
    if mutation == "extract-in-eval":
        of.FEEDS_WRITE_ALLOWLIST = of.FEEDS_WRITE_ALLOWLIST | {EXTRACT}
    if mutation == "extract-tool":
        of.AGENT_TOOLS = of.AGENT_TOOLS + (EXTRACT,)
    if mutation == "no-asymmetry":
        of.TRIAGE_PROMPT = of.TRIAGE_PROMPT.replace("When in doubt, keep it", "When in doubt, drop it")
    if mutation == "inherit-catalogue":
        of.LIVE_SERVER_BLANKS = {}
    if mutation == "triage-drift":
        of.FULL_PROMPT = of.FULL_PROMPT.replace("When in doubt, keep it", "When in doubt, keep it, always", 1)
    if mutation == "unpinned-budget":
        of.MAX_BUDGET_USD = 3.00
    if mutation == "over-ceiling":
        of.EXTRACTION_BUDGET_USD = 1.50
        PINNED["EXTRACTION_BUDGET_USD"] = 1.50  # the pin moved WITH it: only the ceiling arithmetic can catch this
    if mutation == "stale-full-hash":
        of.FULL_PROMPT_SHA256 = "0" * 64
    out = []
    for run in (EVAL_RUN, LIVE):
        out += surface(of.agent_options(run), run, mutation)

    live_names, live_ro = server_tools(False)
    eval_names, eval_ro = server_tools(True)
    out.append((sorted(of.AGENT_TOOLS) == eval_names and sorted(of.FULL_AGENT_TOOLS) == live_names
                and set(of.FEEDS_WRITE_ALLOWLIST) | set(FEEDS_READ_ONLY_TOOLS) == set(eval_names)
                and set(of.FEEDS_FULL_WRITE_ALLOWLIST) | set(FEEDS_READ_ONLY_TOOLS) == set(live_names)
                and eval_ro == live_ro == list(FEEDS_READ_ONLY_TOOLS),
                "AGENT_TOOLS is exactly an eval server's tools and FULL_AGENT_TOOLS a live server's, each split into "
                "the mode's write allowlist and the read-only tools", "eval %s | live %s" % (eval_names, live_names)))

    refused = []
    for kwargs in ({"run_id": "not-a-run"}, {"run_id": LIVE.run_id, "batch": ("ofsi:0123456789abcdef",)},
                   {"run_id": LIVE.run_id, "catalogue": Path("c.json"),
                    "batch": tuple("ofsi:%016x" % i for i in range(11))}):
        try:
            of.FeedsRun(**kwargs)
        except ValueError:
            refused.append(True)
    out.append((len(refused) == 3 and LIVE.live and not EVAL_RUN.live,
                "FeedsRun refuses a bad run id, a half-set eval mode and a batch over 10; live is decided by the run",
                "%d refused" % len(refused)))

    o = of.agent_options(EVAL_RUN)
    msg = sdk_types._get_can_use_tool_shadowed_warning(o.permission_mode, list(o.allowed_tools)) or ""
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with expected_shadowing(FEEDS_READ_ONLY_TOOLS):
            warnings.warn(msg, sdk_types.CanUseToolShadowedWarning)
            warnings.warn("can_use_tool will not be invoked for: %s. x" % TRIAGE, sdk_types.CanUseToolShadowedWarning)
    out.append((msg.startswith("can_use_tool will not be invoked for: %s." % FEEDS_READ_ONLY_TOOLS[0])
                and len(seen) == 1 and TRIAGE in str(seen[0].message),
                "the shadowing advisory names only feeds_read_page, and only that advisory is silenced", msg[:70]))

    live_prompt = of.agent_options(LIVE).system_prompt
    out.append(("When in doubt, keep it" in o.system_prompt
                and hashlib.sha256(of.TRIAGE_PROMPT.encode("utf-8")).hexdigest() == of.PROMPT_SHA256
                and "extract" not in o.system_prompt.replace("You do not extract", "").replace("worth extracting", ""),
                "triage-only: the prompt states the asymmetry, offers no extraction, and PROMPT_SHA256 is its hash",
                of.PROMPT_SHA256[:16]))
    out.append((live_prompt.startswith(of.TRIAGE_PROMPT) and live_prompt == of.FULL_PROMPT
                and hashlib.sha256(live_prompt[:len(of.TRIAGE_PROMPT)].encode("utf-8")).hexdigest() == of.PROMPT_SHA256
                and "feeds_extract" in live_prompt[len(of.TRIAGE_PROMPT):] and "At most 3" in live_prompt,
                "live: the prompt BEGINS with B's measured triage bytes and adds the extraction step (at most 3)",
                of.FULL_PROMPT_SHA256[:16]))
    # Prompt-sha brief (2026-09-29): run_session passes telemetry.run_started this exact constant for a
    # live run. Pinned here rather than at the call site -- see the docstring above.
    out.append((of.FULL_PROMPT_SHA256 == hashlib.sha256(of.FULL_PROMPT.encode("utf-8")).hexdigest(),
                "FULL_PROMPT_SHA256 is the sha256 of FULL_PROMPT, the hash a live run's run_started call reports",
                of.FULL_PROMPT_SHA256[:16]))

    got = {k: getattr(of, k) for k in PINNED}
    fits = of.MAX_BUDGET_USD + feeds_extraction.MAX_PER_RUN * of.EXTRACTION_BUDGET_USD <= of.RUN_CEILING_USD
    out.append((got == PINNED and feeds_extraction.MAX_PER_RUN == 3 and feeds_triage.MAX_PER_RUN == 10 and fits,
                "the budget is pinned (session US$1.50/80 turns, extraction US$1.00/60, 3 extractions, 10 verdicts, "
                "US$5 ceiling) and session + 3 extractions fits the ceiling",
                "%s, fits %s" % (got, fits)))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Prove the orchestrator's tool surface and pin the run's budget")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
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
