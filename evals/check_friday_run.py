"""
Pin the Friday run's budget, reconciliation and report, and the terminal event for a call no hook saw (slice 2 C).

Usage:
    python evals/check_friday_run.py
    python evals/check_friday_run.py --mutate no-budget-check         # an extraction starts past the ceiling
    python evals/check_friday_run.py --mutate unknown-cost-free       # a cost that never arrived counts as zero
    python evals/check_friday_run.py --mutate no-transcript-terminal  # a call the CLI refused stays unterminated
    python evals/check_friday_run.py --mutate validated-empty         # a session leaving items unfinished is validated
    python evals/check_friday_run.py --mutate quiet-reconcile         # an unterminated call does not fail reconciliation
    python evals/check_friday_run.py --mutate report-hides-drops      # the report omits what triage dropped
    python evals/check_friday_run.py --mutate transcript-duplicates   # a call a hook recorded is terminated again
    python evals/check_friday_run.py --mutate invent-terminal         # a call with no hook and no result is terminated
    python evals/check_friday_run.py --mutate refused-extracted       # a refused request gets an id and an extraction
    python evals/check_friday_run.py --mutate no-run-lock             # two Friday runs may allocate at once
    python evals/check_friday_run.py --mutate unfinished-omits-failed # line 3 counts a failure the section omits
    python evals/check_friday_run.py --mutate rows-by-key             # report rows sorted by key, not queue order
    python evals/check_friday_run.py --mutate no-crash-report         # a run that raises leaves no run.json/report
    python evals/check_friday_run.py --mutate telemetry-elsewhere     # friday() leaves telemetry where it was
    python evals/check_friday_run.py --mutate no-cap-recheck          # a fourth request line is extracted
    python evals/check_friday_run.py --mutate writes-real-inbox       # the run also writes a file into the REAL inbox/
    python evals/check_friday_run.py --mutate crash-skips-unreached   # after a crash, only the in-flight item is recorded
    python evals/check_friday_run.py --mutate recon-ignores-allocation  # a record naming another advisory id is not RECONCILIATION_FAILED
    python evals/check_friday_run.py --mutate no-citation-warning     # the runner never checks an extracted record's citations
    python evals/check_friday_run.py --mutate runner-own-rule         # the runner judges "off page" by its own, narrower rule
    python evals/check_friday_run.py --mutate citation-error-silent   # a citation check that could not run reads as clean

WHAT IT HOLDS (spec sections 1, 2 and 5):
  budget       extractions start in queue order only while spend + US$1.00 <= US$5.00; the next is DEFERRED
               FOR BUDGET with no advisory id; ids are allocated in order (ADV-2026-0021, -0022); a cost that
               never arrived counts at its cap (the session's US$1.50, an extraction's US$1.00);
  refused      a request line that carries an error (a linked PDF that could not be read) is reported FAILED
               before any advisory id is allocated or any extraction starts: no id, no extractor call;
  serialised   one Friday run at a time per inbox: the exclusive lock is held across the session, the
               allocation and every extraction, and a run that cannot take it is REFUSED before any agent,
               allocating nothing (advisory-id allocation's read-then-append window, Task 2's carry-forward);
  failure      a failed orchestrator session starts no extraction and the run is FAILED;
  refusal      ANTHROPIC_API_KEY or an eval variable in the environment refuses the run before any agent,
               with a REFUSED report;
  reconcile    an unterminated tool call makes the run RECONCILIATION_FAILED; a layout change is UNFINISHED
               and LOUD; a run that listed nothing is NOTHING_NEW; an extracted record naming another advisory
               id, or another document's sha256, than the one this extraction actually allocated and pinned is
               RECONCILIATION_FAILED, naming the mismatch (I-2, final review 2026-09-29 -- the check at
               feeds/reconcile.py:102-106 had never been seen to fail);
  report       written on every run above; names every dropped item with its reason and quote, the deferred,
               the cost against the ceiling; renders the same bytes twice; line 3's "N unfinished" equals the
               ## Unfinished section's count and its rows, which list failed items with their WHOLE error and
               deferred ones with the spend; rows go in queue order (asserted on a run whose queue order is
               not its key order), and a reason ending in "." is not doubled;
  crash        an exception inside the run (here, the second of three extractions) still leaves run.json and
               report.md: FAILED, naming the exception, the crashed extraction counted at its cap, the lock
               released -- and EVERY queued request has exactly one outcome: the in-flight one and the one never
               reached are FAILED "the run crashed before this item was extracted (...)", no id is allocated for
               them (the in-flight item keeps, and names, the id it held before it started), and ## Unfinished
               and line 3 both count them. At the boundary: a crash INSIDE allocate_advisory_id records every
               item without crashing again; when recording itself fails, the report is still written and names
               it as a RECONCILIATION problem;
  citations    (C2, owner decision 2026-09-30, "warn"; the first live run, feeds-2026-09-30-bd1185, reported two
               records "extracted" and accept_run then refused each for one citation not on its page) right
               after an extraction that produced a record, friday() checks its citations by THE rule accept_run
               refuses on: a VALID record with one quote not on its page leaves the run COMPLETE, line 3 unchanged,
               the Extraction table's "citations off page" cell "1 of 2" and a loud **CITATIONS: ...** line naming
               the item and the first bad citation -- and accept_run's own plan refuses that SAME item for that
               SAME citation, both through one function (a spy on evals/check_citations.unplaced_citations sees
               the runner and accept_run call it); a clean record gets no warning and plan accepts it; a check
               that cannot run (a citation with no quote) is recorded with its error, stated loudly, and does not
               raise; an outcome written before the field existed still reconciles, renders ("not checked") and
               plans;
  telemetry    friday() itself points every session's telemetry into inbox/<run_id>/telemetry/, whatever the
               caller left TELEMETRY_DIR at, and restores it after;
  cap          a fourth request line (request() refuses one; planted here) is not extracted, gets no id, and
               the run is RECONCILIATION_FAILED;
  transcript   run_session, driven by a scripted message stream: a call answered by an is_error tool_result
               and no hook gets ONE terminal event (source "transcript"), terminal_check is clean, and a
               session that left a listed item without a verdict is NOT validated; a call a hook already
               recorded (PostToolUse, or PostToolUseFailure with an is_error result) is NOT terminated again;
               a call with neither a hook event nor a result stays unterminated, and friday() driving that
               session reports RECONCILIATION_FAILED;
  hands off    the repository's git status, the real inbox/ and data/telemetry/ are unchanged -- and the
               writes-real-inbox mutation proves that check can go red. It must watch the REAL inbox to mean
               anything: a default argument (root=inbox.INBOX_ROOT) is bound to the real path when the module
               is loaded, so a decoy root would not see the leak it exists to catch. So, under that mutation
               only, the run writes ONE file whose exact path the guard chose and recorded first:
               inbox/.check_friday_run-plant-<pid>-<random>.json. No live run can own that name: it fails
               inbox.RUN_ID (a leading dot), so run_dir refuses it and feeds.runs never lists it. The guard
               refuses to start if the path already exists, and afterwards deletes exactly that path (and the
               inbox folder itself only if this guard created it and it is empty). Nothing is deleted by pattern.

COLD. Stub sessions and extractors, a scripted message stream in place of the SDK's query, a temporary
inbox and advisory list. No network, no model, no CLI.

NOT A VACUOUS PASS. Each --mutate rewrites one module's source in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
import agents  # noqa: E402
import feeds  # noqa: E402
from feeds import extraction, http as fh, inbox, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem  # noqa: E402
from feeds.sources import linked_pdfs  # noqa: E402
from check_document_pages import tiny_pdf  # noqa: E402

FILES = {"telemetry": ROOT / "agents" / "telemetry.py", "of": ROOT / "agents" / "orchestrate_feeds.py",
         "reconcile": ROOT / "feeds" / "reconcile.py", "report": ROOT / "feeds" / "report.py",
         "friday": ROOT / "tools" / "friday_run.py"}
MUTATIONS = {
    "no-budget-check": ("friday", "    return spent + of.EXTRACTION_BUDGET_USD <= of.RUN_CEILING_USD + 1e-9\n",
                        "    return True\n"),
    "unknown-cost-free": ("friday", "    return cap if cost is None else cost\n", "    return cost or 0.0\n"),
    "no-transcript-terminal": ("telemetry", "        if tool_use_id in done or tool_use_id not in results:\n",
                               "        if True:\n"),
    "validated-empty": ("of", '    validated = failure is None and not items["unfinished"]\n',
                        "    validated = failure is None\n"),
    "quiet-reconcile": ("reconcile", '        if s["unterminated"] or s["duplicated"]:\n', "        if False:\n"),
    "report-hides-drops": ("report", '                        ("Dropped by triage (not relevant), with the reason and '
                                     'the quote", rec["not_relevant"])):\n',
                           '                        ("Dropped by triage (not relevant), with the reason and the quote", [])):\n'),
    "transcript-duplicates": ("telemetry", "        if tool_use_id in done or tool_use_id not in results:\n",
                              "        if tool_use_id not in results:\n"),
    "invent-terminal": ("telemetry", "        if tool_use_id in done or tool_use_id not in results:\n"
                                     "            continue\n"
                                     "        is_error, text = results[tool_use_id]\n",
                        "        if tool_use_id in done:\n"
                        "            continue\n"
                        "        is_error, text = results.get(tool_use_id, (True, \"no result\"))\n"),
    "refused-extracted": ("friday", '                elif req.get("error") or not req.get("document"):\n',
                          "                elif False:\n"),
    "no-run-lock": ("friday", "        if not held:\n", "        if False:\n"),
    "unfinished-omits-failed": ("report", '                  + [(k, "extraction failed: %s" % _cell(rec["failed"][k], '
                                          'None)) for k in rec["failed"]]\n', "                  + []\n"),
    "rows-by-key": ("reconcile", '"queued": list(requests)', '"queued": sorted(requests)'),
    "no-crash-report": ("friday", "    except Exception as exc:  # a report on EVERY run: a crashed one is FAILED and says "
                                  "why\n", "    except ZeroDivisionError as exc:\n"),
    # Anchored on the comment above it: _scheduled (C2, 03d21b1) has the same assignment, so the bare line has not
    # been unique since, and this mutation refused to run ("MUTATION TARGET MISSING") -- found 2026-09-30.
    "telemetry-elsewhere": ("friday", "    # run's own folder, whoever called friday(): never data/telemetry/, which reconcile_run does not read.\n"
                                      "    telemetry.TELEMETRY_DIR = inbox.run_dir(run.run_id, root) / inbox.TELEMETRY\n",
                            "    # run's own folder, whoever called friday(): never data/telemetry/, which reconcile_run does not read.\n"
                            "    pass\n"),
    "no-cap-recheck": ("friday", "                if position >= extraction.MAX_PER_RUN:\n", "                if False:\n"),
    "crash-skips-unreached": ("friday", '                                               "advisory_id": '
                                        'allocations.get(req["key"]), "error": reason}, root)\n',
                              '                                               "advisory_id": allocations.get(req["key"]), '
                              '"error": reason}, root)\n            break\n'),
    "writes-real-inbox": ("friday", "    _save(inbox.run_dir(run.run_id, root) / reconcile.RUN_JSON,\n",
                          "    _save(Path(os.environ[\"FC08_GUARD_PLANT\"]), {\"planted_by\": run.run_id})\n"
                          "    _save(inbox.run_dir(run.run_id, root) / reconcile.RUN_JSON,\n"),
    "recon-ignores-allocation": ("reconcile",
        '            elif record.get("advisory_id") != allocations.get(k) or record.get("advisory_id") != o.get("advisory_id"):\n'
        '                problems.append("%s\'s record names %s, but the run allocated %s" % (k, record.get("advisory_id"),\n'
        '                                                                                     allocations.get(k)))\n',
        '            elif False:\n'
        '                problems.append("%s\'s record names %s, but the run allocated %s" % (k, record.get("advisory_id"),\n'
        '                                                                                     allocations.get(k)))\n'),
    # C2 citation warning (owner decision 2026-09-30, "warn"):
    "no-citation-warning": ("friday", '                        outcome["citation_check"] = citation_check(run.run_id, '
                                      'outcome, req, root)\n', "                        pass\n"),
    "runner-own-rule": ("friday", '        checked, bad = unplaced_citations(outcome["advisory_id"], raw, folder / '
                                  'request["document"]["path"])\n',
                        '        checked, bad = unplaced_citations(outcome["advisory_id"], raw, folder / '
                        'request["document"]["path"])\n'
                        '        bad = [d for d in bad if d["kind"] == "off_page"]\n'),
    "citation-error-silent": ("friday", '        return {"checked": None, "off_page": None, "first": None,\n'
                                        '                "error": ("%s: %s" % (type(exc).__name__, exc))[:300]}\n',
                              '        return {"checked": 0, "off_page": 0, "first": None, "error": None}\n'),
}
PLANT_ENV = "FC08_GUARD_PLANT"
SENTENCE = "This advisory describes red flags for trade-based money laundering through shell companies."


def load_all(mutation):
    """telemetry, orchestrate_feeds, reconcile, report, friday_run -- each from its (possibly mutated) source,
    installed so the ones loaded after it import it."""
    mods = {}
    for name, (pkg, attr, modname) in (("telemetry", (agents, "telemetry", "agents.telemetry")),
                                       ("of", (agents, "orchestrate_feeds", "agents.orchestrate_feeds")),
                                       ("reconcile", (feeds, "reconcile", "feeds.reconcile")),
                                       ("report", (feeds, "report", "feeds.report")),
                                       ("friday", (None, None, "friday_run_under_test"))):
        path = FILES[name]
        source = path.read_text(encoding="utf-8")
        if mutation and MUTATIONS[mutation][0] == name:
            old, new = MUTATIONS[mutation][1:]
            if source.count(old) != 1:
                raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
            source = source.replace(old, new)
        module = types.ModuleType(modname)
        module.__file__ = str(path)
        sys.modules[modname] = module
        if pkg is not None:
            setattr(pkg, attr, module)
        exec(compile(source, str(path), "exec"), module.__dict__)
        mods[name] = module
    return mods


class Stub:
    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        return fh.Fetched(url, url, "application/pdf", tiny_pdf(["Advisory text on shell companies."]))


class Unreadable:
    """A linked 'PDF' pypdf cannot page: request() pins it and records the refusal on the request line."""

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        return fh.Fetched(url, url, "application/pdf", b"this is not a PDF at all, whatever its label says")


def listed_run(m, root: Path, run_id: str, n_relevant: int, n_dropped: int, queue: int, cost, fail=None,
               unterminated=(), layout_changed=False, nothing=False, refused=(), against_keys=False):
    """What an orchestrator session leaves: items listed and pinned, verdicts, requests, and its telemetry.
    `refused`: queue positions whose linked PDF cannot be read, so their request line carries an error.
    `against_keys`: queue in DESCENDING key order, so queue order and key order provably differ. The returned
    keys are then in queue order."""
    run = m["of"].FeedsRun(run_id)
    m["telemetry"].TELEMETRY_DIR = inbox.run_dir(run_id, root) / inbox.TELEMETRY
    state = {"run_id": run_id, "sources": {s: {"status": "ok", "error": None, "listed": 0, "already_seen": 0,
                                               "items": []} for s in ("ofsi", "fincen", "ofac")}}
    if layout_changed:
        state["sources"]["fincen"].update(status="layout_changed", error="fincen: the listing table is missing")
    keys = []
    for i in range(0 if nothing else n_relevant + n_dropped):
        link = "https://www.fincen.gov/system/files/a%d.pdf" % i
        raw = ("<html><body><main><h1>Advisory %d</h1><p>%s</p><p><a href=\"%s\">PDF</a></p></main></body></html>"
               % (i, SENTENCE, link)).encode("utf-8")
        it = FeedItem("fincen", "fin-%s-%d" % (run_id[-6:], i), "Advisory number %d" % i,
                      "https://www.fincen.gov/resources/advisories/f%s-%d" % (run_id[-6:], i),
                      "2026-10-01")
        sha = hashlib.sha256(raw).hexdigest()
        rel = inbox.write_file(run_id, "docs/%s.html" % sha, raw, root)
        state["sources"]["fincen"]["items"].append(dict(it.to_json(), document={
            "path": rel, "sha256": sha, "content_type": "text/html", "bytes": len(raw), "final_url": it.url,
            "pages": 1, "text_pages": 1, "page_error": None, "linked_pdfs": linked_pdfs(raw, it.url)}))
        keys.append(it.key)
    inbox.save(run_id, state, root)
    for i, k in enumerate(keys):
        ok, msg = feeds_triage.decide(run_id, k, "relevant" if i < n_relevant else "not_relevant",
                                      "Drop reason %d: a licence notice." % i if i >= n_relevant else "Red flags.",
                                      SENTENCE, root)
        assert ok, msg
    if against_keys:
        keys = sorted(keys[:queue], reverse=True) + keys[queue:]
    for i, k in enumerate(keys[:queue]):
        ok, msg = extraction.request(run_id, k, Unreadable() if i in refused else Stub(), root)
        assert ok, msg
    tel = m["telemetry"]
    tel.run_started(run, "stub", 1.5, 80, m["of"].FULL_AGENT_TOOLS)
    for tid in ("toolu_a",):
        tel.emit(run, tel.TOOL_CALL, tel.SUCCESS, "stub", tool="mcp__feeds__feeds_list_new", tool_use_id=tid,
                 latency_ms=1, outcome="ok")
    check = {"calls": 1 + len(unterminated), "unterminated": list(unterminated), "duplicated": []}
    tel.run_completed(run, tel.FAILURE if fail else tel.SUCCESS, fail or "ended",
                      result=types.SimpleNamespace(num_turns=9, total_cost_usd=cost, duration_ms=1,
                                                   permission_denials=[]),
                      validated=fail is None, terminal_check=check)

    async def session(_run):
        return {"run_id": run_id, "failure": fail, "cost_usd": cost, "limit": None}
    return run, keys, session


WRONG_ADVISORY_ID = "ADV-2026-9999"
WRONG_DOCUMENT_SHA256 = "f" * 64


def extractor_with(m, costs: list, calls: list = None, probe=None, corrupt=None):
    """A stub extraction: a record of the pinned document under the allocated id, a two-line queue and its
    telemetry, as slice 1's extract leaves them. Costs are taken in order; None = a cost that never arrived.
    `calls` collects the keys it was asked to extract; `probe` runs inside it (the lock check).
    `corrupt`: "advisory_id" | "document_sha256" (I-2, final review 2026-09-29) writes a record naming another
    id, or another document, than the one this extraction was actually allocated and pinned -- the OUTCOME
    friday() records still names the real, allocated id, exactly as a real extractor's return value would."""
    costs = list(costs)

    async def extractor(run, req, advisory_id, root):
        from agents.run_identity import RunIdentity
        if calls is not None:
            calls.append(req["key"])
        if probe is not None:
            probe()
        folder = inbox.run_dir(run.run_id, root)
        ident = RunIdentity.new("extractor", advisory_id, folder / req["document"]["path"], feeds_run=run.run_id,
                                inbox_root=root)
        cost = costs.pop(0)
        tel = m["telemetry"]
        tel.run_started(ident, "stub", 1.0, 60, ())
        tel.run_completed(ident, tel.SUCCESS, "record validated", validated=True,
                          result=types.SimpleNamespace(num_turns=20, total_cost_usd=cost, duration_ms=1,
                                                       permission_denials=[]),
                          terminal_check={"calls": 0, "unterminated": [], "duplicated": []})
        rel = "records/%s.json" % advisory_id
        inbox.write_file(run.run_id, rel, json.dumps({
            "advisory_id": advisory_id if corrupt != "advisory_id" else WRONG_ADVISORY_ID,
            "actors": [], "source": {
                "document_sha256": ident.pdf_sha256 if corrupt != "document_sha256" else WRONG_DOCUMENT_SHA256}}
            ).encode("utf-8"), root)
        ident.queue_path.parent.mkdir(parents=True, exist_ok=True)
        ident.queue_path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
        return {"key": req["key"], "advisory_id": advisory_id, "extraction_run_id": ident.run_id, "status": "extracted",
                "record": rel, "error": None, "cost_usd": cost}
    return extractor


QUOTE = "Advisory text on shell companies."   # Stub's pinned PDF holds exactly this on page 1
NOT_ON_PAGE = "Advisory text on front companies."   # a one-word slip, as the live record's CJK character was


def cited_extractor(m, quotes: list):
    """A stub extraction leaving a VALID record (schemas/advisory.py) of the pinned PDF, one SAN001 typology
    citing `quotes` on page 1 (None = a citation with no quote at all, which the check cannot even read), a
    queue line the review gate accepts, and completed telemetry -- so accept_run's plan reaches its citation
    check and nothing else refuses the item."""
    from schemas.proposal_contract import SCHEMA, proposal_id

    async def extractor(run, req, advisory_id, root):
        from agents.run_identity import RunIdentity
        folder = inbox.run_dir(run.run_id, root)
        ident = RunIdentity.new("extractor", advisory_id, folder / req["document"]["path"], feeds_run=run.run_id,
                                inbox_root=root)
        tel = m["telemetry"]
        tel.run_started(ident, "stub", 1.0, 60, ())
        tel.run_completed(ident, tel.SUCCESS, "record validated", validated=True,
                          result=types.SimpleNamespace(num_turns=20, total_cost_usd=0.6, duration_ms=1,
                                                       permission_denials=[]),
                          terminal_check={"calls": 0, "unterminated": [], "duplicated": []})
        cites = [{"page": 1, "quote": q} if q is not None else {"page": 1} for q in quotes]
        record = {"schema_version": "1.4.0", "advisory_id": advisory_id,
                  "source": {"source_type": "fincen", "publisher": "FinCEN", "title": "A FinCEN advisory",
                             "published_on": "2026-10-01", "published_on_precision": "day",
                             "url": req["document"]["url"], "document_sha256": ident.pdf_sha256, "page_count": 1},
                  "summary": "A synthetic advisory about shell companies, built by the Friday-run guard.",
                  "jurisdictions": ["US"], "actors": [], "indicators": [], "suggested_desks": ["trade_desk"],
                  "overall_confidence": "low", "extraction_notes": None,
                  "typologies": [{"family": "sanctions", "typology_id": "SAN001", "label": "Sanctions evasion",
                                  "emergent": False, "confidence": "low", "citations": cites}]}
        rel = "records/%s.json" % advisory_id
        inbox.write_file(run.run_id, rel, json.dumps(record, indent=2).encode("utf-8"), root)
        body = {"schema": SCHEMA, "run_id": ident.run_id, "stage": "extractor", "advisory_id": advisory_id,
                "document_sha256": ident.pdf_sha256, "typology_id": "SAN001", "emergent_label": None,
                "rationale": "Page 1 describes shell companies.", "confidence": "low",
                "citations": [{"page": 1, "quote": QUOTE}]}
        ident.queue_path.parent.mkdir(parents=True, exist_ok=True)
        ident.queue_path.write_text(json.dumps(dict(body, proposal_id=proposal_id(body),
                                                    proposed_at="2026-10-02T09:00:00+00:00")) + "\n", encoding="utf-8")
        return {"key": req["key"], "advisory_id": advisory_id, "extraction_run_id": ident.run_id, "status": "extracted",
                "record": rel, "error": None, "cost_usd": 0.6}
    return extractor


def load_accept():
    """tools/accept_run.py, unmutated, loaded after load_all so it reads the reconcile/extraction under test."""
    path = ROOT / "tools" / "accept_run.py"
    module = types.ModuleType("accept_run_for_friday_guard")
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


def scripted_query(m, variant="transcript"):
    """Stands in for claude_agent_sdk.query.

    transcript  toolu_ok      a call PostToolUse records, and its (successful) tool_result;
                toolu_raised  a call PostToolUseFailure records, and its is_error tool_result -- a hooked call
                              the transcript ALSO answers, which must not be terminated a second time;
                toolu_bad     a call the CLI refuses with an is_error tool_result and NO hook (B's pilot).
    lost        toolu_ok as above, and toolu_lost: a call with neither a hook event nor a tool_result."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage

    async def fake(prompt, options):
        post = options.hooks["PostToolUse"][0].hooks[0]
        post_failure = options.hooks["PostToolUseFailure"][0].hooks[0]
        uses = [ToolUseBlock(id="toolu_ok", name="mcp__feeds__feeds_list_new", input={"source": "ofsi"})]
        if variant == "transcript":
            uses += [ToolUseBlock(id="toolu_raised", name="mcp__feeds__feeds_fetch", input={"item_key": "x"}),
                     ToolUseBlock(id="toolu_bad", name="mcp__feeds__feeds_triage",
                                  input={"__unparsedToolInput": "{\"para"})]
        else:
            uses += [ToolUseBlock(id="toolu_lost", name="mcp__feeds__feeds_fetch", input={"item_key": "y"})]
        yield AssistantMessage(content=uses, model="stub")
        await post({"tool_name": "mcp__feeds__feeds_list_new", "tool_use_id": "toolu_ok",
                    "tool_response": "No new items", "duration_ms": 3}, "toolu_ok", None)
        results = [ToolResultBlock(tool_use_id="toolu_ok", content="No new items", is_error=False)]
        if variant == "transcript":
            await post_failure({"tool_name": "mcp__feeds__feeds_fetch", "tool_use_id": "toolu_raised",
                                "error": "RuntimeError: the fetch raised", "duration_ms": 4}, "toolu_raised", None)
            results += [ToolResultBlock(tool_use_id="toolu_raised", is_error=True,
                                        content="RuntimeError: the fetch raised"),
                        ToolResultBlock(tool_use_id="toolu_bad", is_error=True,
                                        content="<tool_use_error>InputValidationError: mcp__feeds__feeds_triage"
                                                " was called with input that could not be parsed as JSON.")]
        yield UserMessage(content=results)
        yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=5, is_error=False, num_turns=2,
                            session_id="s", total_cost_usd=0.05)
    return fake


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


def untracked_state() -> list:
    """The gitignored places a Friday run could write into by mistake: git status cannot see them."""
    out = []
    for base in (ROOT / "inbox", ROOT / "data" / "telemetry", ROOT / "data" / "feeds"):
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    st = p.stat()
                    out.append((str(p.relative_to(ROOT)), st.st_size, st.st_mtime_ns))
    return out


def plant_path() -> Path:
    """The ONE path the writes-real-inbox mutation may write: a name no live run can own (it fails inbox.RUN_ID,
    so run_dir refuses it and feeds.runs never lists it), unique to this process."""
    path = ROOT / "inbox" / (".check_friday_run-plant-%d-%s.json" % (os.getpid(), secrets.token_hex(6)))
    assert not inbox.RUN_ID.fullmatch(path.name)
    return path


def remove_plant(path: Path, inbox_existed: bool) -> list:
    """Delete exactly `path` (and its _save temp name), and the inbox folder only if this guard created it and it
    is empty. Never a pattern, never anything else."""
    removed = []
    for p in (path, path.with_name("." + path.name + ".tmp")):
        if p.exists():
            p.unlink()
            removed.append(p.name)
    if not inbox_existed and path.parent.exists() and not any(path.parent.iterdir()):
        path.parent.rmdir()
        removed.append(path.parent.name + "/")
    return removed


def unfinished_counts(text: str) -> tuple:
    """(line 3's "N unfinished", the ## Unfinished header's count, the rows under it)."""
    lines = text.splitlines()
    head = re.search(r"(\d+) unfinished;", lines[2]) if len(lines) > 2 else None
    at = next((i for i, l in enumerate(lines) if l.startswith("## Unfinished: ")), None)
    if at is None:
        return (int(head.group(1)) if head else None, None, None)
    rows, j = 0, at + 2
    while j < len(lines) and lines[j].startswith("- `"):
        rows, j = rows + 1, j + 1
    return (int(head.group(1)) if head else None, int(re.match(r"## Unfinished: (\d+)", lines[at]).group(1)), rows)


def report_text(rid: str, box: Path) -> str:
    path = inbox.run_dir(rid, box) / "report.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def events_of(path: Path) -> list:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def checks(mutation) -> list:
    plant, inbox_existed = plant_path(), (ROOT / "inbox").exists()
    if plant.exists():
        raise SystemExit("REFUSED: %s already exists; the guard deletes only what it creates" % plant)
    before, before_untracked = git_status(), untracked_state()
    if mutation == "writes-real-inbox":
        os.environ[PLANT_ENV] = str(plant)
    try:
        out = body(mutation)
        after = untracked_state()
        out.append((git_status() == before and after == before_untracked,
                    "the repository's git status, the real inbox/, data/telemetry/ and data/feeds/ are unchanged",
                    "changed: %s" % sorted({p for p, _, _ in after} ^ {p for p, _, _ in before_untracked})))
    finally:
        os.environ.pop(PLANT_ENV, None)
        planted = remove_plant(plant, inbox_existed)
    if planted:
        print("  (removed exactly what this guard planted in the real inbox: %s)" % planted)
    return out


def citation_cases(m, run_friday, tmp: Path, box: Path, alist: Path) -> list:
    """C2's citation warning (owner decision 2026-09-30, "warn"), against accept_run's own plan."""
    import check_citations
    from feeds import ledger
    acc = load_accept()
    out = []
    # A COPY of the tracked ledger, read by plan() only (it never writes): this guard does not build ledger bytes
    # itself (check_feeds_ledger allows only named files to dump the ledger), and no stub item is in it.
    seen = tmp / "citations-ledger.json"
    shutil.copyfile(ledger.SEEN_PATH, seen)
    feed_list = tmp / "citations-feed-list.json"
    feed_list.write_text(json.dumps({"schema": "fc08-feed-advisories/1", "advisories": []}), encoding="utf-8")

    def plan(rid_, key_):
        try:
            p = acc.plan(rid_, {key_: "accept"}, inbox_root=box, seen_path=seen, data=tmp / "citations-data",
                         advisory_list=feed_list, golden_list=alist)
            return "PLANNED %s" % [a["advisory_id"] for a in p["accepted"]]
        except Exception as exc:
            return "%s: %s" % (type(exc).__name__, exc)

    def row(text, key_):
        return next((l for l in text.splitlines() if l.startswith("| `%s`" % key_)), "")

    # A: a VALID record, one of its two citations not on its page.
    real, calls = check_citations.unplaced_citations, []

    def spy(advisory_id, *a, **k):
        calls.append(advisory_id)
        return real(advisory_id, *a, **k)
    rid = "feeds-2026-10-02-aaa021"
    run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3)
    check_citations.unplaced_citations = spy
    try:
        rec = run_friday(box, run, session, cited_extractor(m, [QUOTE, NOT_ON_PAGE]), alist)
        runner_calls = list(calls)
        said = plan(rid, keys[0])
    finally:
        check_citations.unplaced_citations = real
    o = extraction.load_outcomes(rid, box).get(keys[0], {})
    adv, cc, text = o.get("advisory_id"), o.get("citation_check") or {}, report_text(rid, box)
    loud = ("**CITATIONS: %s %s: 1 of 2 citation(s) are not on the page they name (first: typologies p1); accept_run "
            "will refuse this item -- defer or drop it**" % (keys[0], adv))
    lines = text.splitlines()
    out.append((rec.get("status") == "COMPLETE" and lines[:1] == ["# Friday run %s: COMPLETE" % rid]
                and len(lines) > 2 and "1 extracted, 0 unfinished;" in lines[2]
                and cc.get("checked") == 2 and cc.get("off_page") == 1 and loud in text
                and "| 1 of 2 |" in row(text, keys[0]) and "| citations off page |" in text,
                "a VALID record with one of its two citations not on its page: the run stays COMPLETE and line 3 "
                "counts it extracted, the Extraction table says '1 of 2' and the report says so LOUDLY, naming the "
                "item and the first bad citation", "%s | %s | %s" % (rec.get("status"), cc,
                                                                    next((l for l in lines if "CITATIONS" in l), "no line"))))
    want = "%s: 1 citation(s) are not on the page they name, first: typologies p1 (missing)" % keys[0]
    out.append((want in said and runner_calls == [adv] and calls == [adv, adv] and loud in text,
                "accept_run's own plan refuses that SAME item for that SAME citation, and both the runner and "
                "accept_run went through the one function, evals/check_citations.unplaced_citations",
                "runner calls %s, all calls %s | %s" % (runner_calls, calls, said[:120])))

    # B: the same, clean -- no warning, and plan accepts it.
    rid = "feeds-2026-10-02-aaa022"
    run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3)
    rec = run_friday(box, run, session, cited_extractor(m, [QUOTE]), alist)
    o = extraction.load_outcomes(rid, box).get(keys[0], {})
    cc, text, said = o.get("citation_check") or {}, report_text(rid, box), plan(rid, keys[0])
    out.append((rec.get("status") == "COMPLETE" and cc == {"checked": 1, "off_page": 0, "first": None, "error": None}
                and "**CITATIONS" not in text and "| 0 of 1 |" in row(text, keys[0])
                and said == "PLANNED %s" % [o.get("advisory_id")],
                "a clean record: checked, no warning, '0 of 1', and accept_run's plan accepts it",
                "%s | %s | %s" % (rec.get("status"), cc, said[:120])))

    # An outcome written BEFORE the field existed (strip it from B's): reconcile, report and accept_run still load it.
    path = inbox.run_dir(rid, box) / extraction.OUTCOMES
    old = [{k: v for k, v in json.loads(l).items() if k != "citation_check"}
           for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    path.write_text("".join(json.dumps(e) + "\n" for e in old), encoding="utf-8")
    try:
        text, status = m["report"].render(rid, box), m["reconcile"].reconcile_run(rid, box)["status"]
    except Exception as exc:
        text, status = "", "RAISED %s: %s" % (type(exc).__name__, exc)
    said = plan(rid, keys[0])
    out.append((status == "COMPLETE" and "| not checked |" in row(text, keys[0]) and "**CITATIONS" not in text
                and said.startswith("PLANNED"),
                "an outcome written before the citation check existed still reconciles, renders ('not checked', "
                "no warning) and plans", "%s | %s | %s" % (status, row(text, keys[0])[-60:], said[:80])))

    # C: a check that cannot run (a citation with no quote) is recorded and stated, never raised or passed.
    rid = "feeds-2026-10-02-aaa023"
    run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3)
    rec = run_friday(box, run, session, cited_extractor(m, [QUOTE, None]), alist)
    o = extraction.load_outcomes(rid, box).get(keys[0], {})
    cc, text = o.get("citation_check") or {}, report_text(rid, box)
    out.append((rec.get("status") == "COMPLETE" and (cc.get("error") or "").startswith("KeyError")
                and cc.get("off_page") is None and "| CHECK FAILED |" in row(text, keys[0])
                and ("**CITATIONS: %s %s: the citation check could not run (KeyError" % (keys[0], o.get("advisory_id")))
                in text,
                "a citation check that cannot run does not raise: its error is recorded on the outcome, the table "
                "says CHECK FAILED and a loud line says so; the run stays COMPLETE",
                "%s | %s" % (rec.get("status"), cc)))
    return out


def body(mutation) -> list:
    m = load_all(mutation)
    fr = m["friday"]
    out = []

    def run_friday(root, run, session, extractor, alist):
        try:
            # A temporary tracked-runs folder too: the real data/feeds/runs/ would move the ids asserted here.
            return asyncio.run(fr.friday(run, session=session, extractor=extractor, root=root, advisory_list=alist,
                                         tracked_runs=Path(root).parent / "data" / "feeds" / "runs"))
        except Exception as exc:
            return {"status": "RAISED %s: %s" % (type(exc).__name__, exc)}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020"}]}), encoding="utf-8")
        box = tmp / "inbox"

        rid = "feeds-2026-10-02-aaa001"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=2, queue=3, cost=2.50)
        rec = run_friday(box, run, session, extractor_with(m, [1.30, 1.30, 1.30]), alist)
        outs = extraction.load_outcomes(rid, box)
        statuses = [outs.get(k, {}).get("status") for k in keys[:3]]
        out.append((statuses == ["extracted", "extracted", "deferred_budget"]
                    and extraction.load_allocations(rid, box) == {keys[0]: "ADV-2026-0021", keys[1]: "ADV-2026-0022"}
                    and abs((rec.get("spent_usd") or 0) - 5.10) < 1e-6 and rec.get("status") == "UNFINISHED",
                    "session US$2.50, extractions US$1.30 each: two start (2.50+1 and 3.80+1 fit US$5), the third is "
                    "DEFERRED FOR BUDGET with no id; ids -0021, -0022; UNFINISHED",
                    "%s, spent %s, %s" % (statuses, rec.get("spent_usd"), rec.get("status"))))
        text = report_text(rid, box)
        again = m["report"].render(rid, box)
        out.append((text.startswith("# Friday run %s: UNFINISHED\n" % rid) and "1 deferred for budget" in text
                    and all(("Drop reason %d" % i) in text for i in (3, 4)) and SENTENCE[:40] in text
                    and "US$5.10 counted against the US$5.00 ceiling" in text and text == again,
                    "the report names every dropped item with its reason and quote, the deferral and the cost against "
                    "the ceiling, and renders the same bytes twice", text.splitlines()[0][:80] if text else "no report"))
        out.append((unfinished_counts(text) == (1, 1, 1)
                    and ("deferred for budget: US$5.10 spent; US$1.00 more would pass the US$5.00 ceiling") in text
                    and "notice.. Quote" not in text and "notice. Quote" in text,
                    "line 3's unfinished count equals the Unfinished section's, which names the deferral and its "
                    "spend; a reason ending in a full stop is not given a second",
                    "line 3 / header / rows %s" % (unfinished_counts(text),)))

        rid = "feeds-2026-10-02-aaa016"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=0, queue=3, cost=0.3, against_keys=True)
        rec = run_friday(box, run, session, extractor_with(m, [0.4, 0.4, 0.4]), alist)
        text = report_text(rid, box)
        lines = text.splitlines()
        table = [next((i for i, l in enumerate(lines) if l.startswith("| `%s`" % k)), None) for k in keys]
        kept = [next((i for i, l in enumerate(lines) if l.startswith("- `%s`" % k)), None) for k in keys]
        alloc = extraction.load_allocations(rid, box)
        out.append((keys != sorted(keys) and None not in table + kept and table == sorted(table)
                    and kept == sorted(kept) and [alloc.get(k) for k in keys] == sorted(alloc.values()),
                    "report rows go in QUEUE order, the order ids were allocated and the budget spent, on a run "
                    "queued against key order", "table rows at %s, kept rows at %s" % (table, kept)))

        rid = "feeds-2026-10-02-aaa002"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=0, queue=3, cost=None)
        rec = run_friday(box, run, session, extractor_with(m, [None, None, None]), alist)
        n = sum(1 for o in extraction.load_outcomes(rid, box).values() if o["status"] == "extracted")
        out.append((abs((rec.get("spent_usd") or 0) - 4.50) < 1e-6 and n == 3,
                    "a cost that never arrived counts at its cap: US$1.50 + 3 x US$1.00 = US$4.50", rec.get("spent_usd")))

        rid = "feeds-2026-10-02-aaa003"
        run, keys, session = listed_run(m, box, rid, n_relevant=2, n_dropped=0, queue=2, cost=0.4,
                                        fail="CLIConnectionError: not authenticated")
        rec = run_friday(box, run, session, extractor_with(m, [0.5, 0.5]), alist)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((rec.get("status") == "FAILED" and not extraction.load_allocations(rid, box)
                    and "**FAILED: CLIConnectionError: not authenticated**" in text,
                    "a failed orchestrator session starts no extraction; the run is FAILED, loudly", rec.get("status")))

        rid = "feeds-2026-10-02-aaa004"
        reasons = fr.refusals({"ANTHROPIC_API_KEY": "x", "FEEDS_CATALOGUE": "/tmp/c.json"})
        rec = fr.write_refusal(rid, reasons, box)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((len(reasons) == 2 and rec["status"] == "REFUSED" and text.startswith("# Friday run %s: REFUSED" % rid)
                    and "**REFUSED: ANTHROPIC_API_KEY" in text and not (inbox.run_dir(rid, box) / "items.json").exists(),
                    "an API key or an eval catalogue in the environment refuses the run before any agent, with a report",
                    reasons))

        rid = "feeds-2026-10-02-aaa005"
        run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3,
                                        unterminated=("toolu_lost",))
        rec = run_friday(box, run, session, extractor_with(m, [0.5]), alist)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((rec.get("status") == "RECONCILIATION_FAILED" and "**RECONCILIATION: session %s: 1 tool call" % rid in text
                    and "--override-reconciliation" in text,
                    "an unterminated tool call fails reconciliation, loudly, and the report names the override",
                    rec.get("status")))

        # I-2 (2026-09-29 final review): the check that an extracted record names its own allocated advisory id
        # and the pinned document's sha256 (feeds/reconcile.py:102-106) had never been seen to fail. Two
        # records, otherwise unremarkable: one names another advisory id, one names another document's sha256.
        # Both must be RECONCILIATION_FAILED, naming the mismatch.
        for corrupt, rid, expect in (
                ("advisory_id", "feeds-2026-10-02-aaa019", "but the run allocated"),
                ("document_sha256", "feeds-2026-10-02-aaa020", "is not of the document its request pinned")):
            run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3)
            rec = run_friday(box, run, session, extractor_with(m, [0.5], corrupt=corrupt), alist)
            out.append((rec.get("status") == "RECONCILIATION_FAILED"
                        and any(expect in p for p in rec.get("problems", [])),
                        "an extracted record naming another %s than the one actually allocated and pinned is "
                        "RECONCILIATION_FAILED, naming the mismatch" % corrupt,
                        "%s | %s" % (rec.get("status"), rec.get("problems"))))

        out += citation_cases(m, run_friday, tmp, box, alist)

        rid = "feeds-2026-10-02-aaa006"
        run, keys, session = listed_run(m, box, rid, n_relevant=0, n_dropped=0, queue=0, cost=0.1, nothing=True)
        rec = run_friday(box, run, session, extractor_with(m, []), alist)
        out.append((rec.get("status") == "NOTHING_NEW" and (inbox.run_dir(rid, box) / "report.md").exists(),
                    "a run that listed nothing new is NOTHING_NEW, and still writes its report", rec.get("status")))

        rid = "feeds-2026-10-02-aaa007"
        run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3, layout_changed=True)
        rec = run_friday(box, run, session, extractor_with(m, [0.5]), alist)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((rec.get("status") == "UNFINISHED" and "**LAYOUT CHANGED: fincen" in text,
                    "a listing whose layout changed is UNFINISHED and stated loudly", rec.get("status")))

        # Carried ruling 3: a refused request (its line carries an error) is failed BEFORE any id or extraction.
        rid = "feeds-2026-10-02-aaa009"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=0, queue=3, cost=0.3, refused=(1,))
        asked = []
        rec = run_friday(box, run, session, extractor_with(m, [0.5, 0.5, 0.5], calls=asked), alist)
        outs, alloc = extraction.load_outcomes(rid, box), extraction.load_allocations(rid, box)
        req_err = next((r.get("error") for r in extraction.load_requests(rid, box) if r["key"] == keys[1]), None)
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8")
        out.append((bool(req_err) and outs.get(keys[1], {}).get("status") == "failed" and keys[1] not in alloc
                    and unfinished_counts(text) == (1, 1, 1)
                    and ("extraction failed: %s" % " ".join(req_err.split())) in text
                    and asked == [keys[0], keys[2]] and sorted(alloc) == sorted([keys[0], keys[2]])
                    and keys[1] in rec.get("failed", {}) and ("`%s` | - | failed: Rejected:" % keys[1]) in text,
                    "a request whose line carries an error (an unreadable linked PDF) is reported FAILED, gets no "
                    "advisory id and is never extracted, and is listed as Unfinished with its WHOLE error, so line 3 "
                    "and the section agree; the items either side of it are extracted",
                    "extractor asked %s; allocated %s; line 3 / header / rows %s" % (
                        asked, sorted(alloc), unfinished_counts(text))))

        # Carried ruling 1: one Friday run at a time; the lock is held across the session and every extraction.
        rid = "feeds-2026-10-02-aaa010"
        run, keys, session = listed_run(m, box, rid, n_relevant=2, n_dropped=0, queue=2, cost=0.3)
        seen_inside = []

        def probe():
            with fr.run_lock(box) as held:
                seen_inside.append(held)
        rec = run_friday(box, run, session, extractor_with(m, [0.5, 0.5], probe=probe), alist)
        rid2 = "feeds-2026-10-02-aaa011"
        run2, keys2, session2 = listed_run(m, box, rid2, n_relevant=1, n_dropped=0, queue=1, cost=0.3)
        started = []

        async def watched(r):
            started.append(r.run_id)
            return await session2(r)
        box.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(box / fr.LOCK), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rec2 = run_friday(box, run2, watched, extractor_with(m, [0.5]), alist)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        text2 = (inbox.run_dir(rid2, box) / "report.md").read_text(encoding="utf-8") \
            if (inbox.run_dir(rid2, box) / "report.md").exists() else ""
        out.append((seen_inside == [False, False] and rec.get("status") == "COMPLETE"
                    and rec2.get("status") == "REFUSED" and started == []
                    and not extraction.load_allocations(rid2, box) and not extraction.load_outcomes(rid2, box)
                    and "**REFUSED: another Friday run holds" in text2,
                    "Friday runs are serialised: the lock is held through every extraction, and a run that cannot "
                    "take it is REFUSED before its session starts, allocating no advisory id",
                    "held inside %s; first run %s; second run %s, sessions started %s" % (
                        seen_inside, rec.get("status"), rec2.get("status"), started)))

        # Review fix 1 (+ round 2): a run that raises still leaves run.json and report.md, FAILED and naming the
        # exception, and every queued request -- in flight or never reached -- has exactly one outcome.
        rid = "feeds-2026-10-02-aaa014"
        run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=0, queue=3, cost=0.3)
        inner = extractor_with(m, [0.5])

        async def crashing(run_, req, advisory_id, root_):
            if req["key"] == keys[1]:
                raise RuntimeError("boom in extraction")
            return await inner(run_, req, advisory_id, root_)
        rec = run_friday(box, run, session, crashing, alist)
        run_json = inbox.run_dir(rid, box) / "run.json"
        saved = json.loads(run_json.read_text(encoding="utf-8")) if run_json.exists() else {}
        text = report_text(rid, box)
        with fr.run_lock(box) as free:
            pass
        out.append((rec.get("status") == "FAILED" and saved.get("crash") == "the run raised RuntimeError: boom in extraction"
                    and text.startswith("# Friday run %s: FAILED\n" % rid)
                    and "**FAILED: the run raised RuntimeError: boom in extraction**" in text
                    and abs((saved.get("spent_usd") or 0) - 1.8) < 1e-6 and free,
                    "a run that raises mid-extraction still writes run.json and report.md: FAILED, naming the "
                    "exception, the crashed extraction counted at its US$1.00 cap (0.3+0.5+1.0), the lock released",
                    "%s; crash %r; spent %s; lock free %s" % (rec.get("status"), saved.get("crash"),
                                                              saved.get("spent_usd"), free)))
        outs, alloc = extraction.load_outcomes(rid, box), extraction.load_allocations(rid, box)
        why = "the run crashed before this item was extracted (RuntimeError: boom in extraction)"
        out.append((sorted(outs) == sorted(keys) and outs[keys[0]]["status"] == "extracted"
                    and all(outs[k]["status"] == "failed" and outs[k]["error"] == why for k in keys[1:])
                    and keys[2] not in alloc and outs[keys[2]].get("advisory_id") is None
                    and alloc.get(keys[1]) is not None and outs[keys[1]].get("advisory_id") == alloc[keys[1]]
                    and len(alloc) == 2 and unfinished_counts(text) == (2, 2, 2)
                    and ("extraction failed: %s" % why) in text
                    and not any("has no outcome" in p_ for p_ in rec.get("problems", [])),
                    "after a crash on the 2nd of 3, the in-flight and the never-reached request each get ONE failed "
                    "'run crashed' outcome and no new id (the 2nd keeps the id it held); ## Unfinished and line 3 "
                    "both count 2", "outcomes %s; allocated %d; line 3 / header / rows %s" % (
                        [outs.get(k, {}).get("status") for k in keys], len(alloc), unfinished_counts(text))))

        # The boundary: a crash INSIDE allocate_advisory_id (an advisory list that is not JSON).
        rid = "feeds-2026-10-02-aaa017"
        run, keys, session = listed_run(m, box, rid, n_relevant=2, n_dropped=0, queue=2, cost=0.3)
        broken = tmp / "broken_advisory_list.json"
        broken.write_text("{not json", encoding="utf-8")
        asked = []
        rec = run_friday(box, run, session, extractor_with(m, [0.5, 0.5], calls=asked), broken)
        outs, text = extraction.load_outcomes(rid, box), report_text(rid, box)
        out.append((rec.get("status") == "FAILED" and asked == [] and not extraction.load_allocations(rid, box)
                    and sorted(outs) == sorted(keys) and all(o["status"] == "failed" and "JSONDecodeError" in o["error"]
                                                              for o in outs.values())
                    and unfinished_counts(text) == (2, 2, 2),
                    "a crash inside allocate_advisory_id records every queued request once, allocates nothing, and "
                    "does not crash again", "%s; outcomes %d; line 3 / header / rows %s" % (
                        rec.get("status"), len(outs), unfinished_counts(text))))

        # The boundary: recording itself fails -- the report is still written, and names it.
        rid = "feeds-2026-10-02-aaa018"
        run, keys, session = listed_run(m, box, rid, n_relevant=1, n_dropped=0, queue=1, cost=0.3)
        real_append = extraction.append_outcome

        def refuse_append(*a, **k):
            raise OSError("disk full")
        extraction.append_outcome = refuse_append
        try:
            rec = run_friday(box, run, session, extractor_with(m, [0.5]), alist)
        finally:
            extraction.append_outcome = real_append
        text = report_text(rid, box)
        out.append((rec.get("status") == "FAILED" and text.startswith("# Friday run %s: FAILED\n" % rid)
                    and "**RECONCILIATION: after the crash, the unfinished requests' outcomes could not be recorded: "
                        "OSError: disk full**" in text,
                    "when recording the crash's outcomes itself fails, the report is still written, FAILED, and says "
                    "so as a reconciliation problem", "%s" % rec.get("status")))

        # Review fix 2: friday() points telemetry at the run folder itself, and restores what it found.
        rid = "feeds-2026-10-02-aaa013"
        run, keys, session = listed_run(m, box, rid, n_relevant=2, n_dropped=0, queue=2, cost=0.3)
        stray = tmp / "stray-telemetry"
        m["telemetry"].TELEMETRY_DIR = stray
        rec = run_friday(box, run, session, extractor_with(m, [0.4, 0.4]), alist)
        ext = [s_ for s_ in rec.get("sessions", []) if s_["agent"] == "extractor"]
        out.append((not (stray.exists() and any(stray.iterdir())) and len(ext) == 2
                    and all(abs((s_["cost_usd"] or 0) - 0.4) < 1e-9 for s_ in ext)
                    and m["telemetry"].TELEMETRY_DIR == stray,
                    "friday() itself puts every session's telemetry under inbox/<run_id>/telemetry/, whatever the "
                    "caller left TELEMETRY_DIR at, and restores it after",
                    "extractor sessions in the run %d; stray files %s" % (
                        len(ext), sorted(p.name for p in stray.iterdir()) if stray.exists() else [])))

        # Review fix 3: a fourth request line (request() refuses one; planted) is not extracted.
        rid = "feeds-2026-10-02-aaa015"
        run, keys, session = listed_run(m, box, rid, n_relevant=4, n_dropped=0, queue=3, cost=0.3)
        cap = extraction.MAX_PER_RUN
        extraction.MAX_PER_RUN = cap + 1
        try:
            planted_ok, _ = extraction.request(rid, keys[3], Stub(), box)
        finally:
            extraction.MAX_PER_RUN = cap
        asked = []
        rec = run_friday(box, run, session, extractor_with(m, [0.3] * 4, calls=asked), alist)
        outs, alloc = extraction.load_outcomes(rid, box), extraction.load_allocations(rid, box)
        out.append((planted_ok and asked == keys[:3] and keys[3] not in alloc
                    and outs.get(keys[3], {}).get("status") == "failed"
                    and "at most 3" in (outs.get(keys[3], {}).get("error") or "")
                    and rec.get("status") == "RECONCILIATION_FAILED"
                    and "4 extraction requests; a run queues at most 3" in rec.get("problems", []),
                    "friday() re-checks the cap: a fourth request line is not extracted and gets no id, and the run "
                    "is RECONCILIATION_FAILED", "extractor asked %d; %s" % (len(asked), rec.get("status"))))

        # Carried ruling 2: run_session itself, driven by a scripted stream.
        rid = "feeds-2026-10-02-aaa008"
        state = {"run_id": rid, "sources": {"ofsi": {"status": "ok", "items": [dict(FeedItem(
            "ofsi", "x#1", "A notice", "https://www.gov.uk/x", "2026-10-01").to_json(), document=None)]}}}
        inbox.save(rid, state, box)
        live = m["of"].FeedsRun(rid)
        m["telemetry"].TELEMETRY_DIR = tmp / "tel8"
        m["of"].query = scripted_query(m, "transcript")
        try:
            summary = asyncio.run(m["of"].run_session(live, inbox_root=box))
        except Exception as exc:
            summary = {"terminal_check": {"unterminated": ["RAISED %s" % exc], "duplicated": []}, "validated": None}
        events = events_of(tmp / "tel8" / ("%s.jsonl" % rid))
        tx = [e for e in events if e["payload"].get("source") == "transcript"]
        per_call = {t: sum(1 for e in events if e["stage"] == "FC08_TOOL_CALL" and e["payload"].get("tool_use_id") == t)
                    for t in ("toolu_ok", "toolu_raised", "toolu_bad")}
        out.append((summary["terminal_check"]["unterminated"] == [] and len(tx) == 1
                    and tx[0]["payload"]["tool_use_id"] == "toolu_bad" and tx[0]["status"] == "FAILURE",
                    "a call the CLI answered with no hook gets ONE terminal event from the transcript; terminal_check "
                    "is clean", "%s; transcript events %d" % (summary["terminal_check"], len(tx))))
        out.append((per_call == {"toolu_ok": 1, "toolu_raised": 1, "toolu_bad": 1}
                    and summary["terminal_check"].get("duplicated") == [],
                    "a call a hook already recorded (PostToolUse, or PostToolUseFailure with an is_error result) is "
                    "not terminated again from the transcript", "%s; duplicated %s" % (
                        per_call, summary["terminal_check"].get("duplicated"))))
        out.append((summary.get("validated") is False,
                    "a session that left a listed item without a verdict is not validated", summary.get("validated")))

        rid = "feeds-2026-10-02-aaa012"
        inbox.save(rid, {"run_id": rid, "sources": {}}, box)
        live = m["of"].FeedsRun(rid)
        m["telemetry"].TELEMETRY_DIR = inbox.run_dir(rid, box) / inbox.TELEMETRY
        m["of"].query = scripted_query(m, "lost")

        async def real_session(r):
            return await m["of"].run_session(r, inbox_root=box)
        rec = run_friday(box, live, real_session, extractor_with(m, []), alist)
        events = events_of(inbox.run_dir(rid, box) / inbox.TELEMETRY / ("%s.jsonl" % rid))
        lost = [e for e in events if e["stage"] == "FC08_TOOL_CALL" and e["payload"].get("tool_use_id") == "toolu_lost"]
        orch = next((s for s in rec.get("sessions", []) if s["run_id"] == rid), {})
        text = (inbox.run_dir(rid, box) / "report.md").read_text(encoding="utf-8") \
            if (inbox.run_dir(rid, box) / "report.md").exists() else ""
        out.append((lost == [] and orch.get("unterminated") == ["toolu_lost"]
                    and rec.get("status") == "RECONCILIATION_FAILED"
                    and ("**RECONCILIATION: session %s: 1 tool call(s) with no terminal event" % rid) in text,
                    "a call with neither a hook event nor a result stays unterminated; friday() driving run_session "
                    "reports RECONCILIATION_FAILED", "events for it %d; %s; %s" % (
                        len(lost), orch.get("unterminated"), rec.get("status"))))

    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the Friday run's budget, reconciliation and report")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, str(detail)[:160]))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
