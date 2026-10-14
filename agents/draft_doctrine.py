#!/usr/bin/env python3
"""The doctrine drafting agent (Stage565 S3, spec §6). On demand, for ONE imported typology proposal.

    .venv/bin/python agents/draft_doctrine.py TP-2026-001 [--model M] [--max-budget-usd 0.50] [--max-turns 20]

It reads the proposal from data/typology_proposals.json (fc-10's export, imported) and the Knowledge Centre's
three lookups, and answers in the DoctrineDraft schema; code checks every citation against the proposal's
evidence and renders the markdown. It writes data/doctrine_drafts/<TP>.md and a manifest beside it, and
nothing else: no write tool, a deny-all callback (S3 plan R15). A draft is never overwritten (R16) and never
approved as written -- the owner edits a copy into the toolkit and fc-10's approve-doctrine pins THAT file.
No RunIdentity or telemetry: those name a document and a draft has none (R14); the manifest is the record.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, PermissionResultDeny, ResultMessage  # noqa: E402

from agents.extract_advisory import LIBRARY_PATH, SERVER_PATH  # noqa: E402
from agents.permissions import SERVER_KEY  # noqa: E402
from schemas import doctrine_draft as ddr  # noqa: E402

IMPORT_PATH = ROOT / "data" / "typology_proposals.json"
DRAFTS_DIR = ROOT / "data" / "doctrine_drafts"
DRAFT_TOOLS = tuple("mcp__%s__%s" % (SERVER_KEY, t) for t in (
    "knowledge_centre_list_typologies", "knowledge_centre_get_typology", "knowledge_centre_search_typologies"))

SYSTEM_PROMPT = """You draft doctrine for a financial crime typology that NEXUS is still defining.

You are given one typology proposal: its working name, family, and the evidence an owner approved -- verbatim
quotes from published advisories, each with its advisory id and page. Write a draft under exactly five headings,
in this order: Purpose, Intelligence Question, Detection Rules, Risk Drivers, Investigation Actions.

Rules:
- Every statement must be supported by the evidence and cite it as {advisory_id, page} from the evidence given.
  Cite only pairs that appear in the evidence. If the evidence does not support a statement, leave it out.
- Each statement is one line of plain prose: no markdown, no bold, no backticks, no pipes, no line breaks.
- Use paragraphs for Purpose and Intelligence Question; bullets for the other three.
- You may use the Knowledge Centre lookups to see how existing typologies in the same family are written, and to
  say how this technique differs from the closest one. Do not cite the Knowledge Centre: cite only the evidence.
- You draft; a person decides. Do not give the technique a typology id.
"""
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def load_proposal(pid, import_path=None):
    path = Path(import_path or IMPORT_PATH)
    raw = path.read_bytes()
    found = [p for p in json.loads(raw).get("proposals", []) if p["proposal_id"] == pid]
    if not found:
        raise SystemExit("%s is not an open proposal in %s: import fc-10's export first" % (pid, path.name))
    return found[0], hashlib.sha256(raw).hexdigest()


def _refuse_pageless(proposal):
    if not ddr.allowed_citations(proposal):
        raise SystemExit("%s's evidence carries no pages: re-import fc-10's export (Stage565 S3 adds them)"
                         % proposal["proposal_id"])


def _refuse_existing(path):
    if path.exists():
        raise SystemExit("%s exists and a draft is never overwritten: remove it in its own commit to redraft"
                         % path.name)


async def _deny(tool_name, tool_input, context):
    return PermissionResultDeny(message="Denied: the drafting agent reads the Knowledge Centre and writes nothing.")


def agent_options(model, max_budget_usd, max_turns):
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT, model=model, max_turns=max_turns, max_budget_usd=max_budget_usd,
        mcp_servers={SERVER_KEY: {"type": "stdio", "command": sys.executable, "args": [str(SERVER_PATH)],
                                  "env": {"NEXUS_TYPOLOGY_PATH": str(LIBRARY_PATH)}}},
        strict_mcp_config=True, tools=[], setting_sources=[], allowed_tools=list(DRAFT_TOOLS),
        can_use_tool=_deny,
        output_format={"type": "json_schema", "schema": ddr.DoctrineDraft.model_json_schema()},
    )


def build_prompt(proposal):
    lines = ["Proposal %s: %s (family: %s)." % (proposal["proposal_id"], proposal["working_name"], proposal["family"]),
             "", "Evidence:"]
    for e in proposal["evidence"]:
        for c in e.get("citations", []):
            lines.append('- %s p.%s (%s): "%s"' % (e["advisory_id"], c["page"], e.get("publisher", ""), c["quote"]))
    lines += ["", "Answer with proposal_id %s." % proposal["proposal_id"]]
    return "\n".join(lines)


async def draft(pid, model, max_budget_usd, max_turns, import_path=None, out_dir=None):
    proposal, import_sha = load_proposal(pid, import_path)
    _refuse_pageless(proposal)
    out = Path(out_dir or DRAFTS_DIR)
    md_path, manifest_path = out / ("%s.md" % pid), out / ("%s.json" % pid)
    _refuse_existing(md_path)
    result = None
    async with ClaudeSDKClient(agent_options(model, max_budget_usd, max_turns)) as client:
        await client.query(build_prompt(proposal))
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                result = message
    if result is None or result.is_error or result.structured_output is None:
        raise RuntimeError("the drafting session produced no draft: %s" % getattr(result, "result", None))
    answer = ddr.DoctrineDraft.model_validate(result.structured_output)
    problems = ddr.problems(answer, proposal)
    if problems:
        raise RuntimeError("draft refused, nothing written: %s" % "; ".join(problems))
    md = ddr.render(answer)
    out.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    manifest = {"proposal_id": pid, "import_sha256": import_sha, "model": model, "prompt_sha256": PROMPT_SHA256,
                "cost_usd": result.total_cost_usd, "num_turns": result.num_turns,
                "draft_sha256": hashlib.sha256(md.encode("utf-8")).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return md_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draft doctrine for one typology proposal")
    ap.add_argument("proposal")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-budget-usd", type=float, default=0.50)
    ap.add_argument("--max-turns", type=int, default=20)
    args = ap.parse_args(argv)
    path = asyncio.run(draft(args.proposal, args.model, args.max_budget_usd, args.max_turns))
    print("draft written: %s -- edit a copy into the toolkit, then fc-10 record-draft / approve-doctrine" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
