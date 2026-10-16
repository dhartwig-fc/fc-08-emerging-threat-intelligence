#!/usr/bin/env python3
"""The flag agent (Stage566 K3a, fc-10 K3 design §4). On demand, for ONE approved governed link ADV::TYP.

    .venv/bin/python agents/compare_flags.py ADV-2026-0028::SAN004 [--model M] [--max-budget-usd 0.50]

It reads the advisory record's indicators and the typology's indicators (the Knowledge Centre's imported list) and
answers one verdict per advisory indicator in the FlagComparison schema: `matches` names a typology indicator
verbatim, `new` states a red flag the typology does not list, citing one quote already in that indicator's
page-checked citations. Code enforces both (schemas/flag_comparison.py). Each `new` verdict becomes one queue line
in data/proposals/flags-<ADV>-<TYP>.jsonl -- a FLAG link the owner decides in tools/review.py -- and a manifest
beside it records every verdict, matches included. Nothing else is written: no write tool, a deny-all callback.
A re-run for the same link is refused while either file exists; a refused answer writes nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, PermissionResultDeny, ResultMessage  # noqa: E402

from agents.extract_advisory import LIBRARY_PATH, SERVER_PATH  # noqa: E402
from agents.permissions import SERVER_KEY  # noqa: E402
from governance.decisions import APPROVED_LINKS  # noqa: E402
from governance.proposals import ADVISORY_LIST, FEED_ADVISORY_LIST, _advisories  # noqa: E402
from schemas import flag_comparison as fcmp  # noqa: E402
from schemas.proposal_contract import SCHEMA, proposal_id  # noqa: E402

APPROVED_PATH = APPROVED_LINKS   # read only: governance/decisions.py is its one writer
RECORD_DIRS = (ROOT / "data" / "records", ROOT / "data" / "feeds" / "records")
PROPOSALS_DIR = ROOT / "data" / "proposals"
STAGE = "flags"
COMPARE_TOOLS = tuple("mcp__%s__%s" % (SERVER_KEY, t) for t in (
    "knowledge_centre_list_typologies", "knowledge_centre_get_typology", "knowledge_centre_search_typologies"))

SYSTEM_PROMPT = """You compare a published advisory's red-flag indicators with a governed financial crime typology.

You are given the advisory's indicators, each numbered, each with numbered verbatim quotes from the advisory, and
the typology's existing indicators. Answer exactly one verdict for every advisory indicator:
- "matches" when the typology already lists the same red flag: put that typology indicator in matched_indicator,
  copied exactly as given. A paraphrase is refused.
- "new" when the typology does not list it: state the red flag in flag_text as ONE plain line of at most 200
  characters (no markdown, no bold, no backticks, no pipes, no line breaks), general enough to apply beyond this
  advisory, and give citation_index, the number of the one quote that best supports it.
Prefer "matches" when the typology's indicator covers the same behaviour in other words. You may use the Knowledge
Centre lookups to read the typology. You propose; a person decides.
"""
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _split(link_key: str):
    adv, _, typ = link_key.partition("::")
    return adv, typ


def _refuse_unapproved(link_key: str, approved_path: Path):
    keys = {a["link_key"] for a in json.loads(Path(approved_path).read_text(encoding="utf-8")).get("approved", [])}
    if link_key not in keys:
        raise SystemExit("%s is not an approved governed link: approve it in tools/review.py first" % link_key)


def _refuse_existing(*paths):
    for path in paths:
        if Path(path).exists():
            raise SystemExit("%s exists and a comparison is never re-run over it: remove it in its own commit"
                             % Path(path).name)


def load_record(advisory_id: str, record_dirs=RECORD_DIRS):
    for d in record_dirs:
        path = Path(d) / ("%s.json" % advisory_id)
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if not record.get("indicators"):
                raise SystemExit("%s's record carries no indicators: nothing to compare" % advisory_id)
            return record, _sha(path)
    raise SystemExit("no record for %s in %s" % (advisory_id, ", ".join(str(d) for d in record_dirs)))


def load_indicators(typology_id: str, library_path=LIBRARY_PATH):
    for t in json.loads(Path(library_path).read_text(encoding="utf-8"))["typologies"]:
        if t["typology_id"] == typology_id:
            if not t.get("indicators"):
                raise SystemExit("%s lists no indicators to compare against" % typology_id)
            return list(t["indicators"]), _sha(library_path)
    raise SystemExit("%s is not in the library %s" % (typology_id, Path(library_path).name))


async def _deny(tool_name, tool_input, context):
    return PermissionResultDeny(message="Denied: the flag agent reads the Knowledge Centre and writes nothing.")


def agent_options(model, max_budget_usd, max_turns, library_path=LIBRARY_PATH):
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT, model=model, max_turns=max_turns, max_budget_usd=max_budget_usd,
        mcp_servers={SERVER_KEY: {"type": "stdio", "command": sys.executable, "args": [str(SERVER_PATH)],
                                  "env": {"NEXUS_TYPOLOGY_PATH": str(library_path)}}},
        strict_mcp_config=True, tools=[], setting_sources=[], allowed_tools=list(COMPARE_TOOLS),
        can_use_tool=_deny,
        output_format={"type": "json_schema", "schema": fcmp.FlagComparison.model_json_schema()},
    )


def build_prompt(link_key, record, typology_indicators):
    adv, typ = _split(link_key)
    lines = ["Link %s: advisory %s, typology %s." % (link_key, adv, typ), "", "Advisory indicators:"]
    for i, ind in enumerate(record["indicators"]):
        lines.append("%d. [%s] %s" % (i, ind.get("indicator_type", ""), ind["description"]))
        for j, c in enumerate(ind.get("citations") or []):
            lines.append('   quote %d (p.%s): "%s"' % (j, c["page"], c["quote"]))
    lines += ["", "%s's indicators:" % typ] + ["- %s" % t for t in typology_indicators]
    lines += ["", "Answer with link_key %s." % link_key]
    return "\n".join(lines)


def flag_lines(answer, link_key, record, document_sha256, proposed_at):
    """One queue line per `new` verdict, in the proposal contract's shape (stage "flags", run_id = file stem)."""
    adv, typ = _split(link_key)
    run_id = "flags-%s-%s" % (adv, typ)
    out = []
    for v in sorted(answer.verdicts, key=lambda v: v.indicator_index):
        if v.verdict != "new":
            continue
        ind = record["indicators"][v.indicator_index]
        cite = ind["citations"][v.citation_index]
        text = " ".join(v.flag_text.split())
        body = {"schema": SCHEMA, "run_id": run_id, "stage": STAGE, "advisory_id": adv,
                "document_sha256": document_sha256, "typology_id": None, "emergent_label": None,
                "rationale": text, "confidence": ind.get("confidence") or "medium",
                "citations": [{"page": int(cite["page"]), "quote": cite["quote"]}],
                "flag": "%s:%s" % (typ, fcmp.flag_sha8(text))}
        out.append(dict(body, proposal_id=proposal_id(body), proposed_at=proposed_at))
    return run_id, out


async def compare(link_key, model, max_budget_usd, max_turns, out_dir=None, approved_path=None, record_dirs=None,
                  library_path=None, advisory_lists=None):
    adv, typ = _split(link_key)
    _refuse_unapproved(link_key, approved_path or APPROVED_PATH)
    out = Path(out_dir or PROPOSALS_DIR)
    queue_path = out / ("flags-%s-%s.jsonl" % (adv, typ))
    manifest_path = out / ("flags-%s-%s.manifest.json" % (adv, typ))
    _refuse_existing(queue_path, manifest_path)
    record, record_sha = load_record(adv, record_dirs or RECORD_DIRS)
    library = library_path or LIBRARY_PATH
    indicators, library_sha = load_indicators(typ, library)
    advisories = _advisories(*(advisory_lists or (ADVISORY_LIST, FEED_ADVISORY_LIST)))
    if adv not in advisories:
        raise SystemExit("%s is not in the advisory list" % adv)
    result = None
    async with ClaudeSDKClient(agent_options(model, max_budget_usd, max_turns, library)) as client:
        await client.query(build_prompt(link_key, record, indicators))
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                result = message
    if result is None or result.is_error or result.structured_output is None:
        raise RuntimeError("the comparison session produced no answer: %s" % getattr(result, "result", None))
    answer = fcmp.FlagComparison.model_validate(result.structured_output)
    problems = fcmp.problems(answer, link_key, record, indicators)
    if problems:
        raise RuntimeError("answer refused, nothing written: %s" % "; ".join(problems))
    proposed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    run_id, lines = flag_lines(answer, link_key, record, advisories[adv]["sha256"], proposed_at)
    text = "".join(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n" for line in lines)
    out.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(text, encoding="utf-8")
    manifest = {"link_key": link_key, "run_id": run_id, "model": model, "prompt_sha256": PROMPT_SHA256,
                "cost_usd": result.total_cost_usd, "num_turns": result.num_turns, "proposed_at": proposed_at,
                "record_sha256": record_sha, "library_sha256": library_sha,
                "queue_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "new_flags": len(lines),
                "verdicts": [v.model_dump() for v in sorted(answer.verdicts, key=lambda v: v.indicator_index)]}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return queue_path, len(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare one approved advisory link's indicators with its typology")
    ap.add_argument("link_key", help="ADV-YYYY-NNNN::TYP, an approved governed link")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-budget-usd", type=float, default=0.50)
    ap.add_argument("--max-turns", type=int, default=20)
    args = ap.parse_args(argv)
    path, n = asyncio.run(compare(args.link_key, args.model, args.max_budget_usd, args.max_turns))
    print("%d new flag(s) written to %s -- decide each FLAG link in tools/review.py" % (n, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
