#!/usr/bin/env python3
"""
Pin the flag agent (Stage566 K3a): a match names one of the typology's indicators verbatim, a new flag is one plain
line citing a quote the advisory's own indicator already carries, every indicator is answered exactly once.

Usage:
    python evals/check_compare_flags.py
    python evals/check_compare_flags.py --mutate match-any    # the verbatim-match check disabled; MUST fail
    python evals/check_compare_flags.py --mutate cite-any     # the citation-index check disabled; MUST fail
    python evals/check_compare_flags.py --mutate write-tool   # a write tool allowed to the agent; MUST fail
    python evals/check_compare_flags.py --mutate overwrite    # the re-run refusal disabled; MUST fail
    python evals/check_compare_flags.py --mutate unapproved   # the approved-link check disabled; MUST fail
    python evals/check_compare_flags.py --mutate contract     # the gate's contract re-check removed; MUST fail

COLD: synthetic answers and a stub session in a scratch tree, no model call.
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

from claude_agent_sdk import ResultMessage  # noqa: E402

from agents import compare_flags as cf  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance import proposals as gp  # noqa: E402
from schemas import flag_comparison as fc  # noqa: E402
from schemas.proposal_contract import STAGES, proposal_id  # noqa: E402

MUTATIONS = ("match-any", "cite-any", "write-tool", "overwrite", "unapproved", "contract")
MUTATION = None

LINK = "ADV-2026-0028::SAN004"
INDICATORS = ["Front company with nominee directors", "Shared address with a designated party"]
RECORD = {"advisory_id": "ADV-2026-0028", "indicators": [
    {"indicator_type": "documentary", "description": "Trading company incorporated shortly before designation",
     "citations": [{"page": 1, "quote": "incorporated in 2024, months before the designation"},
                   {"page": 2, "quote": "registered by a formation agent in Hong Kong"}]},
    {"indicator_type": "network", "description": "Shares an address with a designated company",
     "citations": [{"page": 2, "quote": "shares its registered address with BONASOL GROUP"}]}]}


def _data() -> dict:
    return {"link_key": LINK, "verdicts": [
        {"indicator_index": 0, "verdict": "new",
         "flag_text": "Company incorporated shortly before its owner was designated", "citation_index": 0},
        {"indicator_index": 1, "verdict": "matches", "matched_indicator": INDICATORS[1]}]}


def _answer(data: dict) -> "fc.FlagComparison":
    return fc.FlagComparison.model_validate(data)


def _problems(data: dict) -> list:
    return fc.problems(_answer(data), LINK, RECORD, INDICATORS)


def checks_pure():
    yield _problems(_data()) == [], "a cited new flag and a verbatim match pass", "; ".join(_problems(_data()))

    d = _data()
    d["verdicts"][1]["matched_indicator"] = "Shared address with a sanctioned party"
    p = _problems(d)
    yield any("not one of the typology" in x for x in p), "a match naming text the typology does not list is refused", p

    d = _data()
    d["verdicts"][1]["matched_indicator"] = "  shared ADDRESS with a designated   party "
    yield _problems(d) == [], "a match differing only in case and spacing is accepted", _problems(d)

    d = _data()
    d["verdicts"][0]["citation_index"] = 2
    p = _problems(d)
    yield any("citation" in x for x in p), "a citation index outside the indicator's own citations is refused", p

    d = _data()
    d["verdicts"] = d["verdicts"][:1]
    p = _problems(d)
    yield any("unanswered" in x for x in p), "an indicator left unanswered is refused", p

    d = _data()
    d["verdicts"].append(dict(d["verdicts"][1]))
    p = _problems(d)
    yield any("more than once" in x for x in p), "an indicator answered twice is refused", p

    d = _data()
    d["verdicts"][1]["indicator_index"] = 7
    p = _problems(d)
    yield any("no indicator 7" in x for x in p), "a verdict for an indicator the record lacks is refused", p

    for name, text in (("a line break", "Company incorporated\nshortly before designation"),
                       ("bold markdown", "**Company** incorporated shortly before designation"),
                       ("a pipe", "Company | incorporated shortly before designation")):
        d = _data()
        d["verdicts"][0]["flag_text"] = text
        p = _problems(d)
        yield bool(p), "a flag containing %s is refused" % name, p

    d = _data()
    d["verdicts"][0]["flag_text"] = "x" * 201
    p = _problems(d)
    yield any("200" in x for x in p), "a flag over 200 characters is refused", p

    d = _data()
    d["verdicts"][0].pop("citation_index")
    p = _problems(d)
    yield any("citation" in x for x in p), "a new flag with no citation is refused", p

    d = _data()
    d["link_key"] = "ADV-2026-0028::SAN006"
    p = _problems(d)
    yield any("SAN006" in x for x in p), "an answer for another link is refused", p

    a, b = fc.flag_sha8("Front  Company\twith nominee directors"), fc.flag_sha8("front company with NOMINEE directors")
    yield a == b and len(a) == 8 and all(c in "0123456789abcdef" for c in a), \
        "the flag key ignores case and whitespace", a
    yield fc.flag_sha8("front company") != fc.flag_sha8("front companies"), "the flag key distinguishes wording", ""


def stub(structured=None, error=None):
    log = {"built": [], "prompt": None}

    class _Client:
        def __init__(self, options):
            log["built"].append(options)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def query(self, prompt, session_id="default"):
            log["prompt"] = prompt

        async def receive_response(self):
            yield ResultMessage(subtype="error_during_execution" if error else "success", duration_ms=1,
                                duration_api_ms=1, is_error=bool(error), num_turns=2, session_id="stub",
                                total_cost_usd=0.03, result=error, structured_output=structured)
    return _Client, log


def run(structured=None, error=None, link=LINK, approved=(LINK,), existing=False):
    """compare() against a stub session in a scratch tree: (result or the refusal, log, files written)."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "approved.json").write_text(json.dumps({"approved": [{"link_key": k} for k in approved]}))
        (d / "records").mkdir()
        (d / "records" / "ADV-2026-0028.json").write_text(json.dumps(RECORD))
        (d / "typologies.json").write_text(json.dumps({"typologies": [
            {"typology_id": "SAN004", "indicators": INDICATORS}, {"typology_id": "SAN006", "indicators": ["x"]}]}))
        (d / "advisories.json").write_text(json.dumps({"advisories": [
            {"advisory_id": "ADV-2026-0028", "sha256": "a" * 64, "file": "x.pdf"}]}))
        out = d / "proposals"
        if existing:
            out.mkdir()
            (out / "flags-ADV-2026-0028-SAN004.manifest.json").write_text("{}")
        client, log = stub(structured, error)
        real = cf.ClaudeSDKClient
        cf.ClaudeSDKClient = client
        try:
            got = asyncio.run(cf.compare(link, "stub-model", 0.5, 10, out_dir=out, approved_path=d / "approved.json",
                                         record_dirs=(d / "records",), library_path=d / "typologies.json",
                                         advisory_lists=(d / "advisories.json", None)))
        except (Exception, SystemExit) as exc:  # the refusal IS the result
            got = exc
        finally:
            cf.ClaudeSDKClient = real
        files = {p.name: p.read_text() for p in sorted(out.iterdir())} if out.exists() else {}
        return got, log, files


def checks_session():
    if MUTATION == "write-tool":
        cf.COMPARE_TOOLS = cf.COMPARE_TOOLS + ("Write",)
    got, log, files = run(_data())
    queue = files.get("flags-ADV-2026-0028-SAN004.jsonl", "")
    lines = [json.loads(x) for x in queue.splitlines()]
    yield not isinstance(got, BaseException) and len(lines) == 1, "an accepted answer writes one line per new flag", \
        repr(got)[:120]
    if lines:
        line = lines[0]
        body = {k: v for k, v in line.items() if k not in ("proposal_id", "proposed_at")}
        yield line["proposal_id"] == proposal_id(body), "the flag line's id recomputes under the proposal contract", \
            line["proposal_id"]
        yield (line["run_id"] == "flags-ADV-2026-0028-SAN004" and line["stage"] == "flags" and "flags" in STAGES
               and line["document_sha256"] == "a" * 64), "the line carries its file stem, stage flags and the list's sha", \
            "%s / %s" % (line["run_id"], line["stage"])
        yield (line["flag"] == "SAN004:" + fc.flag_sha8(line["rationale"]) and line["typology_id"] is None
               and line["citations"] == [{"page": 1, "quote": RECORD["indicators"][0]["citations"][0]["quote"]}]), \
            "the line names the flag by key and cites the record's own quote", line["flag"]
    manifest = json.loads(files.get("flags-ADV-2026-0028-SAN004.manifest.json", "{}"))
    yield [v["verdict"] for v in manifest.get("verdicts", [])] == ["new", "matches"], \
        "the manifest records every verdict, matches included", manifest.get("new_flags")
    opts = log["built"][0] if log["built"] else None
    allowed = list(getattr(opts, "allowed_tools", []) or [])
    yield (opts is not None and all(t.startswith("mcp__") and "knowledge_centre_" in t for t in allowed)
           and opts.tools == [] and opts.can_use_tool is cf._deny), "the agent can read the Knowledge Centre and nothing else", \
        allowed

    bad = _data()
    bad["verdicts"][1]["matched_indicator"] = "A paraphrase of an indicator"
    got, _, files = run(bad)
    yield isinstance(got, RuntimeError) and files == {}, "a refused answer writes nothing", repr(got)[:100]

    if MUTATION == "overwrite":
        cf._refuse_existing = lambda *a, **k: None
    got, log, files = run(_data(), existing=True)
    yield isinstance(got, SystemExit) and not log["built"] and "flags-ADV-2026-0028-SAN004.jsonl" not in files, \
        "a re-run over an existing comparison is refused before any model call", repr(got)[:100]

    if MUTATION == "unapproved":
        cf._refuse_unapproved = lambda *a, **k: None
    got, log, files = run(_data(), approved=())
    yield isinstance(got, SystemExit) and not log["built"] and files == {}, \
        "an unapproved link is refused before any model call", repr(got)[:100]

    got, log, _ = run(_data(), error="boom")
    yield isinstance(got, RuntimeError) and "no answer" in str(got), "a failed session writes nothing", repr(got)[:100]


def checks_gate():
    """The FLAG link kind in the review gate: a written line passes the contract, groups as a FLAG link, is read
    from a decision line, and an approval rebuilds into the fourth approvals file (gd.APPROVED_FLAGS) with what the owner was shown."""
    if MUTATION == "contract":
        gp._contract_problem = lambda proposal: None
    got, _, files = run(_data())
    if isinstance(got, BaseException):
        yield False, "the stub run writes a queue file for the gate checks", repr(got)[:100]
        return
    name = "flags-ADV-2026-0028-SAN004.jsonl"
    line = json.loads(files[name].splitlines()[0])
    p = gp.Proposal.from_line(line, source_file=name)
    yield gp._contract_problem(p) is None, "a written flag line passes the proposal contract", gp._contract_problem(p)
    key = "ADV-2026-0028::FLAG[%s]" % line["flag"]
    yield p.kind == "flag" and p.link_key == key, "it is a FLAG link keyed ADV::FLAG[TYP:sha8]", p.link_key

    def tampered(**change):
        d = {k: v for k, v in dict(line, **change).items() if not (k == "flag" and v is None)}
        body = {k: v for k, v in d.items() if k not in ("proposal_id", "proposed_at")}
        return gp.Proposal.from_line(dict(d, proposal_id=proposal_id(body)), source_file=name)
    for label, q, want in (
            ("a flag whose text no longer hashes to its key", tampered(rationale="Some other red flag entirely"),
             "does not recompute from its text"),
            ("a flag line that also names a typology", tampered(typology_id="SAN004"), "names both"),
            ("a flag outside the flags stage", tampered(stage="extractor"), "flags stage"),
            ("a flags-stage line naming no flag", tampered(flag=None, typology_id="SAN004"), "names no flag")):
        reason = gp._contract_problem(q) or ""
        yield want in reason, "%s is quarantined" % label, reason or "accepted"

    parsed = __import__("tools.review", fromlist=["parse_decisions"]).parse_decisions(
        "- ADV-2026-0028 FLAG[san004:%s]: approve -- yes" % line["flag"].split(":")[1])
    yield parsed == [(key, "approve", "yes")], "a FLAG decision line is read into its link key", parsed

    links = gp.group([p])
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.jsonl"
        gd.apply([(key, "approve", "new flag")], links, {}, log_path=log, now="2026-10-16T12:00:00+00:00")
        texts = gd.rebuild(gd.load_log(log))
    rows = json.loads(texts[3])["approved"]
    want = {"link_key": key, "advisory_id": "ADV-2026-0028", "typology_id": "SAN004", "flag": line["flag"],
            "flag_text": line["rationale"], "quote": line["citations"][0]["quote"], "page": 1}
    yield (len(rows) == 1 and all(rows[0].get(k) == v for k, v in want.items())
           and [json.loads(t)["approved"] for t in texts[:3]] == [[], [], []]), \
        "an approved flag rebuilds into the fourth approvals file only, with its text, quote and page", rows


def checks():
    yield from checks_pure()
    yield from checks_session()
    yield from checks_gate()


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the flag agent")
    ap.add_argument("--mutate", choices=MUTATIONS)
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if MUTATION == "match-any":
        fc.indicator_problems = lambda *a, **k: []
    elif MUTATION == "cite-any":
        fc.citation_problems = lambda *a, **k: []
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect" if failures else "NOTHING PROVED"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
