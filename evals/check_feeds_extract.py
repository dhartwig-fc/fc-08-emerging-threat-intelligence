"""
Pin feeds_extract and where an extraction a feeds run starts may write (slice 2 C, spec sections 1 and 2).

Usage:
    python evals/check_feeds_extract.py
    python evals/check_feeds_extract.py --mutate no-verdict-check  # an item not triaged relevant is queued
    python evals/check_feeds_extract.py --mutate no-cap            # more than 3 extractions in one run
    python evals/check_feeds_extract.py --mutate second-request    # an item is queued twice
    python evals/check_feeds_extract.py --mutate any-host          # a linked PDF off the document hosts is fetched
    python evals/check_feeds_extract.py --mutate reuse-id          # an allocated advisory id is allocated again
    python evals/check_feeds_extract.py --mutate queue-escape      # a feeds extraction's queue lands in data/proposals
    python evals/check_feeds_extract.py --mutate unreadable-raises # a linked "PDF" pypdf cannot page escapes as an exception
    python evals/check_feeds_extract.py --mutate unreadable-unrecorded  # ...is refused but not recorded, so a retry refetches
    python evals/check_feeds_extract.py --mutate own-host-rule     # the link rule is a second copy, blind to scheme and port
    python evals/check_feeds_extract.py --mutate no-text-queued    # a linked PDF with no text is told "Queued"
    python evals/check_feeds_extract.py --mutate eval-extract      # request() queues an item of an eval run
    python evals/check_feeds_extract.py --mutate reallocate        # an id another run already allocated is allocated again
    python evals/check_feeds_extract.py --mutate hide-duplicates   # load_allocations keeps the last of two lines silently
    python evals/check_feeds_extract.py --mutate inbox-ids-only    # accepted runs' tracked allocations are not read
    python evals/check_feeds_extract.py --mutate no-identity-match-check  # extract() trusts a mismatched RunIdentity
    python evals/check_feeds_extract.py --mutate identity-check-refuses-all  # every passed identity is refused
    python evals/check_feeds_extract.py --mutate no-resolve         # the identity check compares an unresolved path
    python evals/check_feeds_extract.py --mutate stale-prompt-hash  # run_started is passed a constant/stale hash
    python evals/check_feeds_extract.py --mutate no-prompt-hash     # run_started is called with no prompt_sha256 at all
    python evals/check_feeds_extract.py --mutate no-repair-turn     # a record with a quote off its page gets no repair turn
    python evals/check_feeds_extract.py --mutate two-repair-turns   # a still-bad record gets a SECOND repair turn
    python evals/check_feeds_extract.py --mutate repair-skips-recheck  # the corrected record is trusted, not re-checked
    python evals/check_feeds_extract.py --mutate tool-private-matcher  # check_quote answers by its own substring test
    python evals/check_feeds_extract.py --mutate repair-unrecorded  # the Friday outcome drops the quote_repair note
    python evals/check_feeds_extract.py --mutate repair-cell-hidden # the report's citations cell hides the repair turn
    python evals/check_feeds_extract.py --mutate repair-reports-last-turn  # RUN_COMPLETED reports only the repair turn's turns/denials/duration
    python evals/check_feeds_extract.py --mutate rounds-not-counted  # RUN_COMPLETED's model_rounds stays 0 whatever the session did
    python evals/check_feeds_extract.py --mutate no-result-subtype   # RUN_COMPLETED drops the closing result's subtype
    python evals/check_feeds_extract.py --mutate repair-ignores-allowance  # the repair turn is not held to the turns left
    python evals/check_feeds_extract.py --mutate repair-raise-uncaught     # an SDK exception mid-repair escapes extract()
    python evals/check_feeds_extract.py --mutate invalid-repair-uncaught   # a corrected record that fails validation escapes
    python evals/check_feeds_extract.py --mutate first-check-uncaught      # a first quote check that cannot run escapes

WHAT IT HOLDS:
  relevant only  a request is refused for an item not listed, with no verdict, or triaged not_relevant;
  once, capped   a second request for an item is refused; the fourth request in a run is refused;
  the document   a pinned page linking ONE PDF on its source's document hosts gets that PDF, fetched with
                 exactly those hosts and PDF only, pinned under docs/<sha256>.pdf; a page linking none is
                 extracted as itself; two is refused as ambiguous; a link on any other host is ignored and
                 recorded; a failed fetch is recorded, not retried; bytes labelled application/pdf that are not
                 a PDF are refused and recorded, the bytes stay pinned, and a retry is answered from the record
                 with no second fetch; a PDF with no text is refused ("Rejected:"), never told "Queued";
  the host rule  a plain-http link and an allowed host on another port are off the document hosts, by
                 feeds.http._check_host itself;
  live only      request() refuses an eval run itself, with no fetch and no line;
  ids            next_advisory_id is one past every id in the advisory list and every id any run allocated,
                 expired runs included; a key is never allocated a second id, an id already allocated is never
                 allocated again (a stale computation raises), and load_allocations RAISES on a duplicate;
                 an EMPTY inbox (a fresh clone) still allocates above every id in accepted runs' TRACKED copies,
                 data/feeds/runs/<run>/advisory_ids.jsonl (here a temporary one), and refuses one of them;
  the queue      an extraction naming its feeds run writes inbox/<run>/proposals/<run_id>.jsonl: the runner's
                 RunIdentity and the server derive the SAME path; a malformed feeds run is refused; with no
                 feeds run the queue is data/proposals/ exactly as in slice 1;
  the tool       the server's feeds_extract applies these rules under a run identity and refuses without one;
  identity       extract() refuses a passed RunIdentity that does not match its own call's advisory id or
                 document, before any session starts and with no file read for the mismatched path; a
                 MATCHING identity -- same document, differently spelled -- gets past the check, proved by
                 reaching (a stubbed) document_pages, never a session;
  inbox only     every file written is inside the temporary inbox; the repository's git status is unchanged.
  quote tool     (slice 2 C2, 2026-10-02) knowledge_centre_check_quote answers "Verbatim: on page N.", "Wrong page: the
                 quote is on page(s) M, not N." and "Not found: ..." with where the quote and the page part company
                 (the OFAC shape: the bracketed Arabic script the extractor dropped), briefly, on a fixture of an
                 OFAC-shaped HTML page; it agrees with evals/check_citations.unplaced_citations on every one of a
                 record's citations, including one only the SPACING tier places -- one rule, never a copy;
  repair turn    extract() runs unplaced_citations on its own record and, for one off-page quote and one non-Latin
                 drop, sends EXACTLY ONE repair turn in the same session naming both (section, item, cited page and
                 the rule's own answer); the corrected record is re-checked and passes; a still-bad record is
                 reported (failing before/after, repair_turns 1) and gets NO second turn; a clean record gets none;
                 a first turn that already spent the budget gets none; a repair turn that errors keeps the first
                 record. One client, one options object, the same max_budget_usd (the repair is inside the
                 US$1.00 cap), extraction.MAX_PER_RUN still 3. Driven through a stub ClaudeSDKClient: no model;
  one session    after a repair turn RUN_COMPLETED and the summary report turns, permission denials and duration SUMMED
                 over both turns (each stub turn reports its own) and the cost as the session's running total;
                 the repair turn gets only the turns left of the extraction's total (none under REPAIR_MIN_TURNS,
                 interrupted past them);
  keeps the record  an SDK exception mid-repair, a corrected record that fails validation (schema, unknown typology
                 id) and a first quote check that cannot run each keep the first record, report why in
                 quote_repair.error, and raise nothing out of extract();
  recorded       the summary and RUN_COMPLETED carry quote_repair; tools/friday_run.extract_one puts it on the
                 outcome with the session's running cost; the report's citations cell shows the repair turn.
  prompt sha     extract() passes run_started the sha256 of the prompt it actually sends: sha256(system_prompt)
                 == recorded prompt_sha256 == extract_advisory.PROMPT_SHA256, proved by stubbing query() so no
                 session can start.

COLD. Stubbed HTTP, temporary inbox and advisory list. No network, no model.

NOT A VACUOUS PASS. Each --mutate rewrites feeds/extraction.py or the Knowledge Centre server in memory;
at least one check must fail.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
import feeds  # noqa: E402
from agents import telemetry  # noqa: E402
from feeds import http as fh, inbox, triage as feeds_triage  # noqa: E402
from feeds.model import FeedItem  # noqa: E402
from feeds.sources import linked_pdfs  # noqa: E402
from check_document_pages import tiny_pdf  # noqa: E402

EXTRACTION = ROOT / "feeds" / "extraction.py"
KC = ROOT / "mcp_server" / "knowledge_centre_server.py"
SERVER = ROOT / "mcp_server" / "feeds_server.py"
EXTRACT_ADVISORY = ROOT / "agents" / "extract_advisory.py"
TELEMETRY = ROOT / "agents" / "telemetry.py"
FRIDAY_RUN = ROOT / "tools" / "friday_run.py"
REPORT = ROOT / "feeds" / "report.py"
RUN = "feeds-2026-10-02-ccc333"
JUNK_RUN = "feeds-2026-10-02-eee555"  # its own run, so this run's cap of 3 is not spent on it
EVAL_RUN = "feeds-2026-10-02-fff666"  # an eval run (state["eval"]), as feeds_server's eval mode marks one
HTTP_LINK = "http://www.fincen.gov/system/files/2026-10/plain.pdf"  # the right host, the wrong scheme
PORT_LINK = "https://www.fincen.gov:8443/system/files/2026-10/port.pdf"  # the right host, another port
NOT_A_PDF = b"%PDF-1.4\nlabelled a PDF, but these bytes are not one\n"
PDF_URL = "https://www.fincen.gov/system/files/2026-10/advisory.pdf"
SENTENCE = "This advisory describes red flags for trade-based money laundering through shell companies."
MUTATIONS = {
    "no-verdict-check": (EXTRACTION, "    if verdict is None or verdict[\"verdict\"] != feeds_triage.RELEVANT:\n",
                         "    if False:\n"),
    "no-cap": (EXTRACTION, "MAX_PER_RUN = 3\n", "MAX_PER_RUN = 30\n"),
    "second-request": (EXTRACTION, "    if any(r[\"key\"] == key for r in done):\n", "    if False:\n"),
    "any-host": (EXTRACTION, "    ok = [u for u in links if _on_hosts(u, hosts)]\n", "    ok = list(links)\n"),
    "own-host-rule": (EXTRACTION, "if _on_hosts(u, hosts)]", "if u.split(\"/\")[2].split(\":\")[0].lower() in hosts]"),
    "no-text-queued": (EXTRACTION, "    if entry[\"error\"]:  # recorded, and refused", "    if False:  # recorded, and refused"),
    "eval-extract": (EXTRACTION, "    if state.get(\"eval\"):\n", "    if False:\n"),
    "reallocate": (EXTRACTION, "    if advisory_id in allocated:\n", "    if False:\n"),
    "hide-duplicates": (EXTRACTION, "        if entry[\"key\"] in out or entry[\"advisory_id\"] in out.values():\n",
                        "        if False:\n"),
    "reuse-id": (EXTRACTION, "        taken += _ids_in(path)\n", "        pass\n"),
    "inbox-ids-only": (EXTRACTION, '    files += sorted(Path(tracked_runs).glob("*/%s" % ALLOCATIONS))\n', ""),
    "unreadable-raises": (EXTRACTION, "        except Exception as exc:  # labelled a PDF, but not one pypdf can page",
                          "        except ZeroDivisionError as exc:  # labelled a PDF, but not one pypdf can page"),
    "unreadable-unrecorded": (EXTRACTION, "            _append(run_id, REQUESTS, entry, root)  # recorded, so a retry",
                              "            pass  # recorded, so a retry"),
    "queue-escape": (KC, "    folder = feeds_inbox.proposals_dir(feeds_run, FEEDS_INBOX_ROOT) if feeds_run else QUEUE_DIR\n",
                     "    folder = QUEUE_DIR\n"),
    "no-identity-match-check": (EXTRACT_ADVISORY,
        "    if run is not None:\n"
        "        resolved = Path(path).resolve()\n"
        '        if run.advisory_id != advisory_id or run.pdf_path != resolved:\n'
        '            raise ValueError("the run identity %s (advisory %s, document %s) does not match this '
        'call\'s own "\n'
        '                             "arguments (advisory %s, document %s)"\n'
        "                             % (run.run_id, run.advisory_id, run.pdf_path, advisory_id, resolved))\n",
        ""),
    # Fix round 1, Important (F6): a version that refuses EVERY passed identity, matching one included, must
    # also go red -- the negative-only guard above could not tell this apart from the real check.
    "identity-check-refuses-all": (EXTRACT_ADVISORY,
        '        if run.advisory_id != advisory_id or run.pdf_path != resolved:\n',
        "        if True:\n"),
    "no-resolve": (EXTRACT_ADVISORY, "        resolved = Path(path).resolve()\n", "        resolved = Path(path)\n"),
    "stale-prompt-hash": (EXTRACT_ADVISORY,
        "    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256=PROMPT_SHA256)\n",
        '    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256="0" * 64)\n'),
    "no-prompt-hash": (EXTRACT_ADVISORY,
        "    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS, prompt_sha256=PROMPT_SHA256)\n",
        "    telemetry.run_started(run, model, max_budget_usd, max_turns, AGENT_TOOLS)\n"),
    # Slice 2 C2 (2026-10-02): the extractor checks its own quotes.
    "no-repair-turn": (EXTRACT_ADVISORY, "    for _ in range(MAX_REPAIR_TURNS):\n", "    for _ in range(0):\n"),
    "two-repair-turns": (EXTRACT_ADVISORY, "MAX_REPAIR_TURNS = 1\n", "MAX_REPAIR_TURNS = 2\n"),
    "repair-skips-recheck": (EXTRACT_ADVISORY,
        '        note["checked"], bad = _unplaced(record, path, advisory_id, index)\n'
        '        note["failing_after"] = len(bad)\n',
        '        bad = []\n'
        '        note["failing_after"] = 0\n'),
    "tool-private-matcher": (KC, "    return quote_reply(index, params.page, params.quote)\n",
        "    page_text = index.pages[params.page - 1] if 1 <= params.page <= len(index) else \"\"\n"
        "    return (\"Verbatim: on page %d.\" % params.page if \" \".join(params.quote.lower().split()) in page_text\n"
        "            else \"Not found: no such text.\")\n"),
    "repair-unrecorded": (FRIDAY_RUN,
        '        out.update(status="extracted", record=rel, quote_repair=summary.get("quote_repair"))\n',
        '        out.update(status="extracted", record=rel)\n'),
    "repair-cell-hidden": (REPORT, '    if isinstance(qr, dict) and qr.get("repair_turns"):\n', "    if False:\n"),
    # Fix round 1 (review quote-check-review.md I-2, I-3).
    "rounds-not-counted": (EXTRACT_ADVISORY, "    seen.rounds += len(rounds)\n", "    pass\n"),
    "no-result-subtype": (TELEMETRY, '                result_subtype=getattr(result, "subtype", None),\n', ""),
    "repair-reports-last-turn": (EXTRACT_ADVISORY,
        "            result = _session_total(result, turn)  # cost: the running total; turns, denials, duration: summed\n",
        "            result = turn\n"),
    "repair-ignores-allowance": (EXTRACT_ADVISORY,
        "            turn = await _receive_turn(client, seen, limit=allowance)\n",
        "            turn = await _receive_turn(client, seen)\n"),
    "repair-raise-uncaught": (EXTRACT_ADVISORY,
        "        except Exception as exc:  # noqa: BLE001 -- the SDK raising mid-repair must not lose a valid record\n",
        "        except ZeroDivisionError as exc:  # noqa: BLE001 -- the SDK raising mid-repair must not lose a valid record\n"),
    "invalid-repair-uncaught": (EXTRACT_ADVISORY,
        "        except Exception as exc:  # noqa: BLE001 -- the original record stands\n",
        "        except ZeroDivisionError as exc:  # noqa: BLE001 -- the original record stands\n"),
    # S-1: an interrupted turn leaves a tool call the interrupt cut off with no result and no hook; each needs a
    # terminal event, or the extraction's reconciliation fails at accept time.
    "no-interrupt-backfill": (EXTRACT_ADVISORY,
        "        telemetry.record_interrupted(run, seen.names, seen.results)\n", "        pass\n"),
    # S-3: the interrupt was issued, then the turn raised: quote_repair must still say interrupted.
    "interrupted-lost-on-raise": (EXTRACT_ADVISORY,
        '            note["interrupted"] = seen.interrupted  # S-3: the interrupt may have been issued before it raised\n',
        ""),
    # Fix round 1, I-1: record_interrupted's two safety properties. (A) it must not terminate a call that has a
    # SUCCESS result and no hook event -- that is a failed hook, and must stay visible; (B) it runs only in a
    # session the runner interrupted. The first is a mutation of agents/telemetry.py, applied in memory.
    "interrupt-backfills-successes": (TELEMETRY, "        if tool_use_id in done or tool_use_id in results:\n",
                                      "        if tool_use_id in done:\n"),
    "backfill-without-interrupt": (EXTRACT_ADVISORY,
        "    if seen.interrupted:\n        telemetry.record_interrupted(run, seen.names, seen.results)\n",
        "    telemetry.record_interrupted(run, seen.names, seen.results)\n"),
    "first-check-uncaught": (EXTRACT_ADVISORY,
        "    except Exception as exc:  # noqa: BLE001 -- the runner's own check reports a document that cannot be checked\n",
        "    except ZeroDivisionError as exc:  # noqa: BLE001 -- the runner's own check reports a document that cannot be checked\n"),
}


def mutate_telemetry(mutation) -> None:
    """A mutation of agents/telemetry.py, applied in memory: the guard's `telemetry` is the real, shared module,
    so the mutated source is executed into its own namespace (the process ends with the run)."""
    if mutation and MUTATIONS[mutation][0] == TELEMETRY:
        old, new = MUTATIONS[mutation][1:]
        source = TELEMETRY.read_text(encoding="utf-8")
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, TELEMETRY))
        exec(compile(source.replace(old, new), str(TELEMETRY), "exec"), telemetry.__dict__)


def load(name: str, path: Path, mutation):
    source = path.read_text(encoding="utf-8")
    if mutation and MUTATIONS[mutation][0] == path:
        old, new = MUTATIONS[mutation][1:]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
        source = source.replace(old, new)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def page(links=()) -> bytes:
    anchors = "".join('<a href="%s">document</a>' % u for u in links)
    return ("<html><body><main><h1>Advisory</h1><p>%s</p><p>%s</p></main></body></html>"
            % (SENTENCE, anchors)).encode("utf-8")


class Stub:
    def __init__(self, fail=False, body=None):
        self.calls, self.fail, self.body = [], fail, body

    def __call__(self, url, *, allowed_hosts, allowed_types, max_bytes):
        self.calls.append((url, sorted(allowed_hosts), sorted(allowed_types)))
        if self.fail:
            raise fh.FetchRefused("stub: connection reset")
        return fh.Fetched(url, url, "application/pdf",
                          self.body if self.body is not None else tiny_pdf(["Advisory text on shell companies."]))


def setup(tmp: Path, docs: dict, run: str = RUN) -> list:
    """A run that listed one fincen item per entry of `docs` (name -> page bytes), each fetched and pinned."""
    state = {"run_id": run, "sources": {"fincen": {"status": "ok", "items": []}}}
    keys = []
    for name, raw in docs.items():
        it = FeedItem("fincen", name, "Advisory %s" % name, "https://www.fincen.gov/resources/advisories/%s" % name,
                      "2026-10-01")
        rel = inbox.write_file(run, "docs/%s.html" % __import__("hashlib").sha256(raw).hexdigest(), raw, tmp)
        doc = {"path": rel, "sha256": __import__("hashlib").sha256(raw).hexdigest(), "content_type": "text/html",
               "bytes": len(raw), "final_url": it.url, "pages": 1, "text_pages": 1, "page_error": None,
               "linked_pdfs": linked_pdfs(raw, it.url)}
        state["sources"]["fincen"]["items"].append(dict(it.to_json(), document=doc))
        keys.append(it.key)
    inbox.save(run, state, tmp)
    return keys


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


# ---------------------------------------------------------------------------
# Slice 2 C2 (2026-10-02): the extractor checks its own quotes. The fixture is an OFAC-shaped page (the 10ce44
# ADV-2026-0025 shape: an SDN entry carries each name's original script) of three pages, built in code so the
# guard runs cold and reads nothing outside the repository.
# ---------------------------------------------------------------------------
SCRIPT = "مهنوش پورصراف همدانی"  # Persian script
SDN = "HAMEDANI, Mehnoosh Poursaraf (Arabic: %s), China; DOB 07 Mar 1984; POB Qom, Iran; nationality Iran" % SCRIPT
SDN_DROPPED = "HAMEDANI, Mehnoosh Poursaraf, China; DOB 07 Mar 1984; POB Qom, Iran; nationality Iran"  # the script gone
SDN_SPAN = "DOB 07 Mar 1984; POB Qom, Iran; nationality Iran"  # a span that contains none
TYPOLOGY_LINE = "Over-invoicing and under-invoicing of goods remains the most common TBML technique observed."
SPACED_PAGE = "The officials were in collus ion with the exporter to hide the shipment."  # pypdf-style split word
SPACED_QUOTE = "in collusion with the exporter to hide the shipment"  # placed by the SPACING tier only
INDICATOR_LINE = "Prices that deviate significantly from market benchmarks should prompt further enquiry."
QUOTE_ADV = "ADV-2026-0088"
QUOTE_RUN = "feeds-2026-10-02-abc123"
FIRST_COST, REPAIRED_COST, BUDGET = 0.30, 0.45, 1.00


def _para(text: str, size: int = 1600) -> str:
    out = text
    while len(out) < size:  # long enough that two paragraphs never share a 3000-character page
        out += " The register lists further entries for this programme."
    return out


def quote_document() -> bytes:
    paras = (SDN + ". " + TYPOLOGY_LINE, SPACED_PAGE, INDICATOR_LINE)
    return ("<html><body><main>%s</main></body></html>" % "".join("<p>%s</p>" % _para(t) for t in paras)).encode("utf-8")


def quote_record(actor_quote: str, indicator_page: int) -> dict:
    """The example record with three citations: the typology's is verbatim on page 1; the actor's quote is
    `actor_quote` on page 1; the indicator's text is on page 3 and is cited as `indicator_page`."""
    rec = json.loads((ROOT / "evals" / "example_record.json").read_text(encoding="utf-8"))
    rec["advisory_id"] = QUOTE_ADV
    rec["typologies"] = [dict(rec["typologies"][0], citations=[{"page": 1, "paragraph": 1, "quote": TYPOLOGY_LINE}])]
    rec["actors"] = [dict(rec["actors"][0], name="HAMEDANI, Mehnoosh Poursaraf", actor_type="person", aliases=[],
                          citations=[{"page": 1, "paragraph": 1, "quote": actor_quote}])]
    rec["indicators"] = [dict(rec["indicators"][0], citations=[{"page": indicator_page, "paragraph": 1,
                                                                 "quote": INDICATOR_LINE}])]
    return rec


def turn(structured, cost, *, error=False, calls=1, turns=1, denials=None, duration=10, tag="t"):
    """One scripted turn of the stubbed session: `calls` check_quote tool uses (each its own API round, with its
    own message id), then the ResultMessage, which reports THIS turn's `turns`, `denials` and `duration` (the
    CLI's per-turn figures) and the session's running `cost`."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock
    name = "mcp__knowledge_centre__knowledge_centre_check_quote"
    msgs = [AssistantMessage(content=[ToolUseBlock(id="%s%d" % (tag, i), name=name, input={})], model="stub",
                             message_id="%s-msg-%d" % (tag, i)) for i in range(calls)]
    return msgs + [ResultMessage(subtype="error_max_budget_usd" if error else "success", duration_ms=duration,
                                 duration_api_ms=duration - 2, is_error=error, num_turns=turns, session_id="stub",
                                 total_cost_usd=cost, structured_output=structured,
                                 permission_denials=list(denials or []),
                                 errors=["stub: out of budget"] if error else None)]


class RaisingTurn(list):
    """A scripted turn that, once the runner has interrupted it, raises `then_raise` instead of ending."""
    then_raise = None


def stub_session(script):
    """A stand-in for claude_agent_sdk.ClaudeSDKClient: no CLI, no model. Each query() consumes the next scripted
    turn (a list of messages ending in a ResultMessage); `log` records every client built, every message sent."""
    log = {"built": [], "sent": [], "interrupts": 0}

    class _Client:
        def __init__(self, options):
            log["built"].append(options)
            self._turns, self._now, self._stopped = list(script), None, False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def query(self, prompt, session_id="default"):
            log["sent"].append(prompt)
            self._now = self._turns.pop(0) if self._turns else []
            self._stopped = False
            if isinstance(self._now, BaseException):  # the SDK raising mid-session
                raise self._now

        async def interrupt(self):
            log["interrupts"] += 1
            self._stopped = True

        async def receive_response(self):
            from claude_agent_sdk import AssistantMessage, ResultMessage
            for message in self._now or []:
                if self._stopped and isinstance(message, AssistantMessage):
                    continue  # an interrupted turn does no more rounds ...
                if self._stopped and isinstance(message, ResultMessage):  # ... and ends with an error result
                    message = ResultMessage(subtype="error_during_execution", duration_ms=1, duration_api_ms=1,
                                            is_error=True, num_turns=1, session_id="stub",
                                            total_cost_usd=message.total_cost_usd, errors=["stub: interrupted"])
                yield message
                if self._stopped and getattr(self._now, "then_raise", None) is not None:
                    raise self._now.then_raise
    return _Client, log


def quote_checks(mutation, ea, kc, tmp: Path, box: Path) -> list:
    """The quote tool, the repair turn and where each is recorded -- see WHAT IT HOLDS."""
    import agents
    import check_citations
    from agents.run_identity import RunIdentity
    from feeds import extraction as feeds_extraction, report as _report
    from schemas.citation_match import PageIndex
    mutate_telemetry(mutation)
    fr = load("friday_run_under_test", FRIDAY_RUN, mutation)
    rep = load("feeds_report_under_test", REPORT, mutation)
    out = []
    doc = tmp / "quote-fixture.html"
    doc.write_bytes(quote_document())
    index = PageIndex.from_document(doc)
    ident = RunIdentity.new("extractor", QUOTE_ADV, doc)

    # ---- the tool: three answers, brief, one rule ----
    saved = {k: os.environ.get(k) for k in ident.env()}
    os.environ.update(ident.env())

    def ask(page, quote):
        try:
            return asyncio.run(kc.check_quote(kc.CheckQuoteInput(page=page, quote=quote)))
        except Exception as exc:
            return "RAISED %s: %s" % (type(exc).__name__, exc)
    try:
        verbatim, wrong = ask(1, SDN_SPAN), ask(2, INDICATOR_LINE)
        absent = ask(1, SDN_DROPPED)
        spaced = ask(2, SPACED_QUOTE)
        # One citation of each kind, asked of the tool and of THE rule accept_run refuses on, by the same record.
        record = quote_record(SDN_DROPPED, 2)
        record["indicators"][0]["citations"].append({"page": 2, "paragraph": 1, "quote": SPACED_QUOTE})
        record["indicators"][0]["citations"].append({"page": 1, "paragraph": 1, "quote": SDN_SPAN})
        _, bad = check_citations.unplaced_citations(QUOTE_ADV, record, doc, index=index)
        flagged = {(d["section"], d["page"], d["quote_sha256"]) for d in bad}
        disagree = []
        for section in ("typologies", "actors", "indicators"):
            for item in record[section]:
                for c in item["citations"]:
                    said = ask(c["page"], c["quote"]).startswith("Verbatim")
                    ruled = (section, c["page"], check_citations._quote_sha256(c["quote"])) not in flagged
                    if said != ruled:
                        disagree.append((section, c["page"], c["quote"][:30], ask(c["page"], c["quote"])[:40]))
        for k in ident.env():
            os.environ.pop(k, None)
        no_run = ask(1, SDN_SPAN)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    out.append((verbatim == "Verbatim: on page 1." and wrong == "Wrong page: the quote is on page(s) 3, not 2."
                and absent.startswith("Not found: the longest matching prefix is ")
                and " characters" in absent and "the page then reads '(Arabic: " + SCRIPT in absent
                and "where the quote has ', China; DOB 07 Mar 1984" in absent,
                "knowledge_centre_check_quote answers verbatim, wrong page, and not found with the divergence "
                "(the page reads '(Arabic: <script>)' where the quote dropped it), on the real server function",
                "%s | %s | %s" % (verbatim, wrong, absent[:90])))
    out.append((len(absent) < 400 and "register lists further entries" not in absent
                and spaced == "Verbatim: on page 2." and no_run.startswith("Rejected"),
                "its replies are brief (a divergence, never a page), a spacing-tier quote is verbatim, and without a "
                "run identity it refuses rather than guess a document",
                "%d chars | %s | %s" % (len(absent), spaced, no_run[:50])))
    out.append((len(bad) == 2 and not disagree,
                "the tool and evals/check_citations.unplaced_citations agree on every citation of a record (a "
                "verbatim span, a wrong page, a dropped script, and a quote only the SPACING tier places): one "
                "rule, never a private copy", "flagged %d; disagree: %s" % (len(bad), disagree[:2])))

    # ---- the repair turn, through a stub session ----
    good = quote_record(SDN_SPAN, 3)
    first_bad = quote_record(SDN_DROPPED, 2)
    still_bad = quote_record(SDN_DROPPED, 3)

    spy_calls = []
    real_unplaced = check_citations.unplaced_citations

    def spy(*a, **k):
        spy_calls.append(1)
        return real_unplaced(*a, **k)

    def drive(script, budget=BUDGET, max_turns=60, broken_index=False):
        """extract() on the fixture with a stub session; (record, summary, log, telemetry events) or the exception."""
        client, log = stub_session(script)
        real_client, real_dir = ea.ClaudeSDKClient, telemetry.TELEMETRY_DIR
        ea.ClaudeSDKClient = client
        telemetry.TELEMETRY_DIR = tmp / "telemetry-scratch"
        run = RunIdentity.new("extractor", QUOTE_ADV, doc)
        check_citations.unplaced_citations = spy
        real_index = ea.PageIndex
        if broken_index:
            class _Unreadable:
                @staticmethod
                def from_document(path):
                    raise OSError("stub: the pinned document cannot be read back")
            ea.PageIndex = _Unreadable
        spy_calls.clear()
        try:
            record, summary = asyncio.run(ea.extract(doc, QUOTE_ADV, "stub-model", budget, max_turns, run=run))
            path = telemetry.telemetry_path(run)
            events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
            return record, summary, log, events
        except Exception as exc:
            return exc, None, log, []
        finally:
            ea.ClaudeSDKClient, telemetry.TELEMETRY_DIR = real_client, real_dir
            check_citations.unplaced_citations = real_unplaced
            ea.PageIndex = real_index

    def quote_of(record, section):
        return getattr(record, section)[0].citations[0].quote

    rec_a, sum_a, log_a, ev_a = drive([turn(first_bad, FIRST_COST), turn(good, REPAIRED_COST)])
    qa = (sum_a or {}).get("quote_repair") or {}
    sent_a = log_a["sent"][1] if len(log_a["sent"]) > 1 else ""
    out.append((sum_a is not None and len(log_a["sent"]) == 2 and qa.get("repair_turns") == 1
                and qa.get("failing_before") == 2 and qa.get("failing_after") == 0
                and "2 of 3 citations are not on the page they name" in sent_a
                and 'indicators "' in sent_a and "cites page 2" in sent_a
                and "Wrong page: the quote is on page(s) 3, not 2." in sent_a
                and 'actors "HAMEDANI, Mehnoosh Poursaraf"' in sent_a and "(Arabic: " + SCRIPT in sent_a
                and sent_a.count("\n1. ") == 1 and sent_a.count("\n2. ") == 1 and "\n3. " not in sent_a
                and "knowledge_centre_check_quote" in sent_a,
                "one off-page quote and one non-Latin drop: exactly ONE repair turn is sent, in the same session, "
                "naming both (section, item, cited page, and the rule's own answer for each)",
                "%s | sent %d | %s" % (rec_a if sum_a is None else "ok", len(log_a["sent"]), qa)))
    out.append((sum_a is not None and quote_of(rec_a, "actors") == SDN_SPAN and rec_a.indicators[0].citations[0].page == 3
                and len(spy_calls) == 2 and sum_a["tool_calls"] == {
                    "mcp__knowledge_centre__knowledge_centre_check_quote": 2},
                "the corrected record is the one returned, it is re-checked by the shared rule (unplaced_citations ran "
                "twice: before and after), and tool calls from BOTH turns are counted",
                "spy calls %d | %s" % (len(spy_calls), (sum_a or {}).get("tool_calls"))))

    rec_b, sum_b, log_b, ev_b = drive([turn(first_bad, FIRST_COST), turn(still_bad, REPAIRED_COST), turn(good, 0.6)])
    qb = (sum_b or {}).get("quote_repair") or {}
    done_b = [e for e in ev_b if e.get("stage") == telemetry.RUN_COMPLETED]
    out.append((sum_b is not None and len(log_b["sent"]) == 2 and qb.get("repair_turns") == 1
                and qb.get("failing_before") == 2 and qb.get("failing_after") == 1
                and quote_of(rec_b, "actors") == SDN_DROPPED
                and done_b and (done_b[-1]["payload"].get("quote_repair") or {}).get("failing_after") == 1,
                "a record still failing after its repair turn is REPORTED (failing 2 -> 1, in the summary and in "
                "RUN_COMPLETED) and gets NO second turn: the first message and one repair, never a loop",
                "%s | sent %d | %s" % (rec_b if sum_b is None else "ok", len(log_b["sent"]), qb)))

    rec_c, sum_c, log_c, _ = drive([turn(good, FIRST_COST), turn(good, REPAIRED_COST)])
    qc = (sum_c or {}).get("quote_repair") or {}
    out.append((sum_c is not None and len(log_c["sent"]) == 1 and qc.get("repair_turns") == 0
                and qc.get("failing_before") == 0 and qc.get("failing_after") == 0,
                "a record with every citation on its page gets no repair turn", str(qc)))

    rec_d, sum_d, log_d, _ = drive([turn(first_bad, BUDGET), turn(good, BUDGET + 0.2)])
    qd = (sum_d or {}).get("quote_repair") or {}
    out.append((sum_d is not None and len(log_d["sent"]) == 1 and qd.get("repair_turns") == 0
                and qd.get("failing_before") == 2 and qd.get("skipped"),
                "a first turn that has already spent the whole budget gets no repair turn (the repair is inside the "
                "cap, never on top of it); the failure is reported as before", str(qd)))

    rec_e, sum_e, log_e, _ = drive([turn(first_bad, FIRST_COST), turn(None, 0.4, error=True)])
    qe = (sum_e or {}).get("quote_repair") or {}
    out.append((sum_e is not None and len(log_e["sent"]) == 2 and qe.get("error") and qe.get("failing_after") == 2
                and quote_of(rec_e, "actors") == SDN_DROPPED and sum_e["cost_usd"] == 0.4,
                "a repair turn that errors keeps the first valid record and reports the error: an extraction that "
                "had a record is never lost to its repair", "%s | %s" % (rec_e if sum_e is None else "ok", qe)))

    # ---- fix round 1, I-2: one session's closing figures, summed across its turns ----
    first_t = turn(first_bad, FIRST_COST, turns=7, denials=["denied-a"], duration=1000, tag="f")
    repair_t = turn(good, REPAIRED_COST, turns=5, denials=["denied-b", "denied-c"], duration=2000, tag="r")
    rec_f, sum_f, log_f, ev_f = drive([first_t, repair_t])
    done_f = [e for e in ev_f if e.get("stage") == telemetry.RUN_COMPLETED]
    pay_f = done_f[-1]["payload"] if done_f else {}
    out.append((sum_f is not None and pay_f.get("turns") == 12 and pay_f.get("permission_denials") == 3
                and pay_f.get("duration_ms") == 3000 and pay_f.get("cost_usd") == REPAIRED_COST
                and sum_f["turns"] == 12 and sum_f["permission_denials"] == 3 and sum_f["duration_s"] == 3.0
                and sum_f["cost_usd"] == REPAIRED_COST,
                "after a repair turn RUN_COMPLETED and the summary report turns, permission denials and duration "
                "SUMMED over both turns (7+5, 1+2, 1000+2000 ms: each stub turn reports its own, as the CLI does) "
                "and the cost as the session's running total (not summed)",
                "%s | summary %s" % ({k: pay_f.get(k) for k in ("turns", "permission_denials", "duration_ms", "cost_usd")},
                                     {k: (sum_f or {}).get(k) for k in ("turns", "permission_denials", "duration_s")})))
    # 2026-10-16: the CLI's num_turns (12 here, as scripted) is recorded beside what the runner counted itself --
    # two distinct assistant messages, one per turn -- and the closing result's subtype, so a turn count above
    # max_turns can be told apart from a cap the CLI let pass.
    out.append((pay_f.get("model_rounds") == 2 and pay_f.get("result_subtype") == "success"
                and (sum_f or {}).get("model_rounds") == 2,
                "RUN_COMPLETED records the model rounds the runner counted across both turns (2, beside the CLI's "
                "num_turns 12) and the closing result's subtype",
                {k: pay_f.get(k) for k in ("model_rounds", "result_subtype", "turns")}))

    # the turn allowance: the repair gets what is LEFT of max_turns (here 60 - 56 = 4), never a fresh one
    long_repair = turn(good, REPAIRED_COST, calls=6, turns=6, tag="L")
    rec_g, sum_g, log_g, _ = drive([turn(first_bad, FIRST_COST, turns=56, tag="g"), long_repair], max_turns=60)
    qg = (sum_g or {}).get("quote_repair") or {}
    out.append((sum_g is not None and len(log_g["sent"]) == 2 and qg.get("repair_allowance_turns") == 4
                and log_g["interrupts"] == 1 and qg.get("interrupted") is True and qg.get("error")
                and quote_of(rec_g, "actors") == SDN_DROPPED,
                "the repair turn is held to the turns left of the extraction's total (4 of 60 here): a repair that "
                "runs past them is interrupted once, and the first record stands with the reason reported",
                "%s | interrupts %d | %s" % (rec_g if sum_g is None else "ok", log_g["interrupts"], qg)))
    # S-1: the stub DID start tool calls in the interrupted turn (5 of them: the sixth round is never read)
    rec_s, sum_s, log_s, ev_s = drive([turn(first_bad, FIRST_COST, turns=56, tag="s"),
                                       turn(good, REPAIRED_COST, calls=6, turns=6, tag="S")], max_turns=60)
    started = {e["payload"].get("tool_use_id") for e in ev_s if e.get("stage") == telemetry.TOOL_CALL}
    out.append((sum_s is not None and log_s["interrupts"] == 1 and sum_s["unterminated"] == 0
                and sum_s["duplicated"] == 0 and {"S0", "S4"} <= started
                and quote_of(rec_s, "actors") == SDN_DROPPED,
                "an interrupted repair turn that started tool calls leaves 0 unterminated (each is given one "
                "terminal event) and the first record is kept",
                "%s | unterminated %s | terminal events for %s" % (
                    rec_s if sum_s is None else "ok", (sum_s or {}).get("unterminated"), sorted(started))))
    raising = RaisingTurn(turn(good, REPAIRED_COST, calls=6, turns=6, tag="R"))
    raising.then_raise = RuntimeError("stub: the CLI died after the interrupt")
    rec_r, sum_r, log_r, _ = drive([turn(first_bad, FIRST_COST, turns=56, tag="r"), raising], max_turns=60)
    qr = (sum_r or {}).get("quote_repair") or {}
    out.append((sum_r is not None and log_r["interrupts"] == 1 and qr.get("interrupted") is True
                and "the repair turn raised" in (qr.get("error") or "") and sum_r["unterminated"] == 0,
                "an interrupt issued and then a turn that raises: quote_repair.interrupted is still True and the "
                "calls are still terminated", "%s | %s" % (rec_r if sum_r is None else "ok", qr)))
    # I-1 (A): a call the CLI ANSWERED with a success and for which no hook fired is a failed hook. The interrupt
    # backfill must leave it unterminated, or terminal_check goes green over exactly the defect it exists to catch.
    from claude_agent_sdk import ToolResultBlock, UserMessage
    answered = turn(good, REPAIRED_COST, calls=6, turns=6, tag="Q")
    answered.insert(1, UserMessage(content=[ToolResultBlock(tool_use_id="Q0", content="ok", is_error=False)]))
    rec_t, sum_t, log_t, ev_t = drive([turn(first_bad, FIRST_COST, turns=56, tag="t"), answered], max_turns=60)
    held = {e["payload"].get("tool_use_id") for e in ev_t if e.get("stage") == telemetry.TOOL_CALL}
    out.append((sum_t is not None and log_t["interrupts"] == 1 and sum_t["unterminated"] == 1 and "Q0" not in held
                and {"Q1", "Q4", "t0"} <= held,
                "an interrupt backfills the calls it cut off (no result, no event) but NOT a call with a success "
                "result and no hook event: that one stays unterminated, so a failed hook stays visible",
                "unterminated %s | terminal events for %s" % ((sum_t or {}).get("unterminated"), sorted(held))))
    # I-1 (B): the backfill runs only in a session the runner interrupted. Here nothing is interrupted and the stub
    # fires no hooks, so both calls (one per turn) are genuinely unterminated and must be reported as such.
    rec_u, sum_u, log_u, _ = drive([turn(first_bad, FIRST_COST, tag="u"), turn(good, REPAIRED_COST, tag="U")])
    out.append((sum_u is not None and log_u["interrupts"] == 0 and sum_u["unterminated"] == 2,
                "in a session that was NOT interrupted, calls with no terminal event are never backfilled: "
                "both stay unterminated", "interrupts %s | unterminated %s" % (
                    log_u["interrupts"], (sum_u or {}).get("unterminated"))))
    rec_h, sum_h, log_h, _ = drive([turn(first_bad, FIRST_COST, turns=57, tag="h"), turn(good, REPAIRED_COST)],
                                   max_turns=60)
    qh = (sum_h or {}).get("quote_repair") or {}
    out.append((sum_h is not None and len(log_h["sent"]) == 1 and qh.get("repair_turns") == 0 and qh.get("skipped")
                and "57" in qh["skipped"], "a first turn that left fewer than REPAIR_MIN_TURNS (3 of 60) gets no "
                "repair turn, and says why", str(qh)))
    rec_i, sum_i, log_i, _ = drive([turn(first_bad, FIRST_COST, turns=2, tag="i"), long_repair], max_turns=60)
    out.append((sum_i is not None and log_i["interrupts"] == 0 and len(log_i["sent"]) == 2
                and quote_of(rec_i, "actors") == SDN_SPAN,
                "a repair turn inside its allowance (6 rounds of 58 left) is never interrupted",
                "interrupts %d" % log_i["interrupts"]))

    # ---- fix round 1, I-3: the branches that keep the first record ----
    rec_j, sum_j, log_j, _ = drive([turn(first_bad, FIRST_COST), RuntimeError("stub: the CLI died mid-turn")])
    qj = (sum_j or {}).get("quote_repair") or {}
    out.append((sum_j is not None and quote_of(rec_j, "actors") == SDN_DROPPED and len(log_j["sent"]) == 2
                and "the repair turn raised RuntimeError" in (qj.get("error") or ""),
                "the SDK raising mid-repair: the first record is kept and reported, nothing raises out of extract()",
                "%s | %s" % (rec_j if sum_j is None else "ok", qj.get("error"))))
    schema_bad = dict(good, typologies=[dict(good["typologies"][0], confidence="certain-beyond-doubt")])
    id_bad = dict(good, typologies=[dict(good["typologies"][0], typology_id="ZZZ999")])
    refused = []
    for label, corrected in (("schema violation", schema_bad), ("unknown typology id", id_bad)):
        rec_k, sum_k, log_k, _ = drive([turn(first_bad, FIRST_COST), turn(corrected, REPAIRED_COST)])
        qk = (sum_k or {}).get("quote_repair") or {}
        refused.append((label, sum_k is not None and quote_of(rec_k, "actors") == SDN_DROPPED
                        and "the repair turn's record was refused" in (qk.get("error") or "")
                        and qk.get("failing_after") == 2))
    out.append((all(ok for _, ok in refused),
                "a corrected record that fails validation (a schema violation; an unknown typology id) keeps the "
                "first record and reports it refused, raising nothing out of extract()", str(refused)))
    rec_l, sum_l, log_l, _ = drive([turn(first_bad, FIRST_COST), turn(good, REPAIRED_COST)], broken_index=True)
    ql = (sum_l or {}).get("quote_repair") or {}
    out.append((sum_l is not None and quote_of(rec_l, "actors") == SDN_DROPPED and len(log_l["sent"]) == 1
                and "the quote check could not run" in (ql.get("error") or "") and ql.get("repair_turns") == 0,
                "a first quote check that cannot run (the document cannot be read back) keeps the record, sends no "
                "repair turn, and reports why -- the runner's own check then says it again",
                "%s | %s" % (rec_l if sum_l is None else "ok", ql.get("error"))))

    from agents import orchestrate_feeds as of
    built = log_a["built"]
    out.append((len(built) == 1 and built[0].max_budget_usd == BUDGET and of.EXTRACTION_BUDGET_USD == 1.00
                and feeds_extraction.MAX_PER_RUN == 3 and ea.MAX_REPAIR_TURNS == 1
                and sum_a is not None and sum_a["cost_usd"] == REPAIRED_COST <= BUDGET,
                "the caps are unchanged: ONE client and ONE options object carry the first turn and the repair, "
                "with the budget it was called with; the extraction budget is still US$1.00 and a run still "
                "extracts at most 3; the reported cost is the session's running total, repair included",
                "built %d client(s), max_budget_usd %s; EXTRACTION_BUDGET_USD %s; MAX_PER_RUN %s" % (
                    len(built), built[0].max_budget_usd if built else None, of.EXTRACTION_BUDGET_USD,
                    feeds_extraction.MAX_PER_RUN)))

    # ---- where it is recorded: the Friday outcome and the report ----
    real_attr = getattr(agents, "extract_advisory", None)
    client, log = stub_session([turn(first_bad, FIRST_COST), turn(good, REPAIRED_COST)])
    run_box = tmp / "friday-box"
    (run_box / QUOTE_RUN / "docs").mkdir(parents=True)
    pinned = run_box / QUOTE_RUN / "docs" / "quote-fixture.html"
    pinned.write_bytes(quote_document())
    real_client, real_dir = ea.ClaudeSDKClient, telemetry.TELEMETRY_DIR
    ea.ClaudeSDKClient = client
    agents.extract_advisory = ea  # extract_one imports it by name at call time
    telemetry.TELEMETRY_DIR = run_box / QUOTE_RUN / inbox.TELEMETRY
    try:
        outcome = asyncio.run(fr.extract_one(of.FeedsRun(QUOTE_RUN), {"key": "ofac:abc", "document": {
            "path": "docs/quote-fixture.html"}}, QUOTE_ADV, run_box))
    except Exception as exc:
        outcome = {"status": "RAISED %s: %s" % (type(exc).__name__, exc)}
    finally:
        ea.ClaudeSDKClient, telemetry.TELEMETRY_DIR = real_client, real_dir
        if real_attr is not None:
            agents.extract_advisory = real_attr
    qo = outcome.get("quote_repair") or {}
    out.append((outcome.get("status") == "extracted" and qo.get("repair_turns") == 1 and qo.get("failing_before") == 2
                and qo.get("failing_after") == 0 and outcome.get("cost_usd") == REPAIRED_COST,
                "the Friday outcome records whether a repair turn ran and the failing counts before and after, and "
                "its cost is the session's running total (repair included)", str(outcome)[:160]))
    cell = rep.citation_cell(dict(outcome, citation_check={"off_page": 0, "checked": 3, "error": None}))
    out.append((cell == "0 of 3 (repair turn: 2 failing before, 0 after)"
                and rep.citation_cell(dict(outcome, quote_repair=None, citation_check={
                    "off_page": 0, "checked": 3, "error": None})) == "0 of 3",
                "the report's citations cell shows the repair turn when there was one, and is unchanged when there "
                "was not", cell))
    return out



def checks(mutation) -> list:
    ex = load("feeds.extraction", EXTRACTION, mutation)
    feeds.extraction = ex
    kc = load("kc_under_test", KC, mutation)
    out, before = [], git_status()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        box = tmp / "inbox"
        other = "https://evil.example/advisory.pdf"
        keys = setup(box, {"a1": page([PDF_URL, other, HTTP_LINK, PORT_LINK]), "a2": page(), "a3": page([PDF_URL]),
                           "a4": page(), "a5": page(["https://www.fincen.gov/x.pdf", "https://www.fincen.gov/y.pdf"]),
                           "a6": page(), "a7": page([PDF_URL])})
        a1, a2, a3, a4, a5, a6, a7 = keys
        stub = Stub()

        def requests() -> list:
            try:
                return ex.load_requests(RUN, box)
            except ValueError as exc:  # a duplicated request line is corruption the mutation produced
                return [{"corrupt": str(exc), "chosen": None, "document": None, "error": None, "ignored_links": None}] * 9

        def req(key, get=stub):
            try:
                return ex.request(RUN, key, get, box)
            except Exception as exc:
                return False, "RAISED %s: %s" % (type(exc).__name__, exc)

        said = req(a1)
        out.append((not said[0] and said[1].startswith("Rejected") and not requests(),
                    "an item with no verdict is refused and nothing is written", said[1][:80]))
        for k in (a1, a2, a3, a4, a5, a6, a7):
            ok, msg = feeds_triage.decide(RUN, k, "relevant" if k != a6 else "not_relevant", "Red flags.", SENTENCE, box)
            assert ok, msg
        said = req(a6)
        out.append((not said[0] and "not_relevant" in said[1], "an item triaged not_relevant is refused", said[1][:80]))
        said = req("fincen:0000000000000000")
        out.append((not said[0] and "not listed" in said[1], "an item not listed in this run is refused", said[1][:80]))

        said = req(a1)
        reqs = requests()
        pinned = box / RUN / (reqs[0]["document"]["path"] if reqs and reqs[0]["document"] else "none")
        out.append((said[0] and said[1].startswith("Queued") and len(stub.calls) == 1
                    and stub.calls[0] == (PDF_URL, ["www.fincen.gov"], ["application/pdf"])
                    and reqs[0]["chosen"] == "linked" and reqs[0]["ignored_links"] == [other, HTTP_LINK, PORT_LINK]
                    and pinned.exists() and pinned.name == "%s.pdf" % reqs[0]["document"]["sha256"],
                    "a page linking one PDF on the document hosts: that PDF, fetched with those hosts and PDF only, "
                    "pinned by sha256; the off-host, plain-http and other-port links are ignored and recorded", "%s %s" % (said[1][:60], stub.calls)))
        said = req(a1)
        out.append((not said[0] and "already queued" in said[1] and len(requests()) == 1,
                    "a second request for the same item is refused", said[1][:80]))
        said = req(a5)
        out.append((not said[0] and "2 PDFs" in said[1], "a page linking two PDFs is refused as ambiguous", said[1][:90]))
        said = req(a2)
        reqs = requests()
        out.append((said[0] and reqs[-1]["chosen"] == "pinned" and reqs[-1]["document"]["path"].endswith(".html")
                    and len(stub.calls) == 1, "a page linking no PDF is extracted as the page itself, with no fetch",
                    said[1][:80]))
        said = req(a3, Stub(fail=True))
        reqs = requests()
        out.append((said[1].startswith("Failed") and reqs[-1]["error"] and reqs[-1]["document"] is None,
                    "a failed fetch is recorded on the request, not retried", said[1][:80]))
        said = req(a4)
        out.append((not said[0] and "cap of 3" in said[1] and len(requests()) == 3,
                    "the fourth request in a run is refused: at most 3", said[1][:80]))

        j1, j2 = setup(box, {"j1": page([PDF_URL]), "j2": page([PDF_URL])}, JUNK_RUN)
        for k in (j1, j2):
            assert feeds_triage.decide(JUNK_RUN, k, "relevant", "Red flags.", SENTENCE, box)[0]
        junk = Stub(body=NOT_A_PDF)

        def junk_req():
            try:
                return ex.request(JUNK_RUN, j1, junk, box)
            except Exception as exc:
                return False, "RAISED %s: %s" % (type(exc).__name__, exc)

        said = junk_req()
        lines = ex.load_requests(JUNK_RUN, box)
        pin = box / JUNK_RUN / "docs" / ("%s.pdf" % __import__("hashlib").sha256(NOT_A_PDF).hexdigest())
        again = junk_req()
        out.append((said[1].startswith("Rejected") and "could not be read" in said[1] and len(junk.calls) == 1
                    and len(lines) == 1 and lines[0]["error"] == said[1] and lines[0]["document"]["page_error"]
                    and pin.exists() and pin.read_bytes() == NOT_A_PDF
                    and again[1].startswith("Rejected") and "could not be read" in again[1]
                    and "not fetched again" in again[1] and len(junk.calls) == 1
                    and len(ex.load_requests(JUNK_RUN, box)) == 1,
                    "bytes labelled application/pdf that are not a PDF: refused and recorded, the bytes pinned, "
                    "one fetch; a retry is answered from the record with no second fetch",
                    "%s | retry: %s | fetches %d" % (said[1][:70], again[1][:50], len(junk.calls))))

        blank = Stub(body=tiny_pdf([""]))
        try:
            said = ex.request(JUNK_RUN, j2, blank, box)
        except Exception as exc:
            said = False, "RAISED %s: %s" % (type(exc).__name__, exc)
        try:
            line = [r for r in ex.load_requests(JUNK_RUN, box) if r["key"] == j2]
        except ValueError as exc:  # a duplicated line (a mutation's corruption) must fail a check, not the guard
            line, said = [], (False, "CORRUPT %s" % exc)
        out.append((said[1].startswith("Rejected") and "no text" in said[1] and len(blank.calls) == 1
                    and len(line) == 1 and line[0]["error"] == said[1],
                    "a linked PDF with no text is refused with its reason and recorded, never told \"Queued\"",
                    said[1][:80]))

        (e1,) = setup(box, {"e1": page([PDF_URL])}, EVAL_RUN)
        state = inbox.load(EVAL_RUN, box)
        state["eval"] = True
        inbox.save(EVAL_RUN, state, box)
        assert feeds_triage.decide(EVAL_RUN, e1, "relevant", "Red flags.", SENTENCE, box)[0]
        live = Stub()
        try:
            said = ex.request(EVAL_RUN, e1, live, box)
        except Exception as exc:
            said = False, "RAISED %s: %s" % (type(exc).__name__, exc)
        out.append((not said[0] and said[1].startswith("Rejected") and "eval run" in said[1] and not live.calls
                    and not ex.load_requests(EVAL_RUN, box),
                    "request() itself refuses an eval run: no fetch, no line", said[1][:80]))

        alist = tmp / "advisory_list.json"
        alist.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020"}, {"advisory_id": "ADV-2025-0400"}]}),
                         encoding="utf-8")
        tracked = tmp / "data" / "feeds" / "runs"   # temporary: the real one would move every id asserted here
        first = ex.allocate_advisory_id(RUN, a1, 2026, alist, box, tracked)
        expired = box / "expired" / "feeds-2026-09-01-ddd444"
        expired.mkdir(parents=True)
        (expired / ex.ALLOCATIONS).write_text(json.dumps({"key": "k", "advisory_id": "ADV-2026-0023"}) + "\n",
                                              encoding="utf-8")
        got = ex.next_advisory_id(2026, alist, box, tracked)
        out.append((first == "ADV-2026-0021" and got == "ADV-2026-0024" and ex.load_allocations(RUN, box) == {a1: first}
                    and ex.next_advisory_id(2027, alist, box, tracked) == "ADV-2027-0001",
                    "the next advisory id is past the list and every run's allocations, expired runs included", got))

        def refused(fn):
            try:
                return "ALLOWED %s" % (fn(),)
            except ValueError as exc:
                return "REFUSED %s" % exc
        twice = refused(lambda: ex.allocate_advisory_id(RUN, a1, 2026, alist, box, tracked))
        computed = ex.next_advisory_id
        ex.next_advisory_id = lambda *a, **k: "ADV-2026-0023"  # stale: an expired run allocated it meanwhile
        try:
            stale = refused(lambda: ex.allocate_advisory_id(RUN, a2, 2026, alist, box, tracked))
        finally:
            ex.next_advisory_id = computed
        out.append((twice.startswith("REFUSED") and stale.startswith("REFUSED") and "already allocated" in stale
                    and ex.load_allocations(RUN, box) == {a1: first},
                    "a key is never allocated a second id, and an id another run already allocated is refused, "
                    "not written", "%s | %s" % (twice[:45], stale[:45])))
        dups = []
        for run, lines in (("feeds-2026-10-02-aaa111", [("k1", "ADV-2026-0030"), ("k1", "ADV-2026-0031")]),
                           ("feeds-2026-10-02-bbb222", [("k2", "ADV-2026-0032"), ("k3", "ADV-2026-0032")])):
            (box / run).mkdir(parents=True)
            (box / run / ex.ALLOCATIONS).write_text("".join(json.dumps({"key": k, "advisory_id": i}) + "\n"
                                                            for k, i in lines), encoding="utf-8")
            dups.append(refused(lambda: ex.load_allocations(run, box)))
        out.append((all(d.startswith("REFUSED") for d in dups),
                    "load_allocations raises on a key with two ids and on an id given to two keys", str(dups)[:90]))

        # A fresh clone: NO inbox history, only an accepted run's tracked copy (the gap ADV-2026-0040 among them).
        fresh = tmp / "fresh-clone-inbox"
        (fresh / RUN).mkdir(parents=True)
        (tracked / "feeds-2026-09-18-eee555").mkdir(parents=True)
        (tracked / "feeds-2026-09-18-eee555" / ex.ALLOCATIONS).write_text(
            "".join(json.dumps({"key": k, "advisory_id": i}) + "\n" for k, i in (("ka", "ADV-2026-0039"),
                                                                                ("kb", "ADV-2026-0040"))),
            encoding="utf-8")
        nxt = ex.next_advisory_id(2026, alist, fresh, tracked)
        computed = ex.next_advisory_id
        ex.next_advisory_id = lambda *a, **k: "ADV-2026-0040"  # stale: the gap, computed without the tracked copy
        try:
            reissued = refused(lambda: ex.allocate_advisory_id(RUN, a1, 2026, alist, fresh, tracked))
        finally:
            ex.next_advisory_id = computed
        out.append((nxt == "ADV-2026-0041" and reissued.startswith("REFUSED") and "already allocated" in reissued
                    and not ex.load_allocations(RUN, fresh),
                    "a checkout with no inbox history still allocates above an accepted run's TRACKED allocations, and "
                    "refuses to issue one of them again", "%s | %s" % (nxt, reissued[:50])))

        from agents.run_identity import RunIdentity
        doc = tmp / "doc.html"
        doc.write_bytes(page())
        ident = RunIdentity.new("extractor", "ADV-2026-0024", doc, feeds_run=RUN, inbox_root=box)
        saved = {k: os.environ.get(k) for k in (kc.FEEDS_RUN_ENV,)}
        kc.FEEDS_INBOX_ROOT = box
        os.environ[kc.FEEDS_RUN_ENV] = RUN
        try:
            derived = kc._proposals_path(ident.env())
            refusal = kc._refuse_queue(ident.env())
            os.environ[kc.FEEDS_RUN_ENV] = "feeds-../../data"
            bad = kc._refuse_queue(dict(ident.env(), NEXUS_FEEDS_RUN="feeds-../../data"))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        out.append((derived == ident.queue_path == box / RUN / "proposals" / ("%s.jsonl" % ident.run_id)
                    and refusal is None and ident.env()["NEXUS_FEEDS_RUN"] == RUN,
                    "a feeds extraction's queue is inbox/<run>/proposals/<run_id>.jsonl, derived the same by runner "
                    "and server", "%s | %s" % (derived, refusal)))
        out.append((bool(bad) and bad.startswith("Rejected"), "a malformed feeds run is refused", str(bad)[:80]))
        plain = RunIdentity.new("extractor", "ADV-2026-0013", doc)
        out.append((kc._proposals_path(plain.env()) == plain.queue_path == kc.QUEUE_DIR / ("%s.jsonl" % plain.run_id)
                    and "NEXUS_FEEDS_RUN" not in plain.env(),
                    "with no feeds run the queue is data/proposals/ exactly as in slice 1", str(plain.queue_path)[-40:]))

        fs = load("feeds_server_under_test", SERVER, None)
        fs.HTTP_GET, fs.INBOX_ROOT = Stub(), box
        os.environ.pop(fs.RUN_ENV, None)

        def tool(key):
            try:
                return asyncio.run(fs.extract(fs.ExtractInput(item_key=key)))
            except Exception as exc:
                return "RAISED %s: %s" % (type(exc).__name__, exc)

        said = tool(a7)
        out.append((said.startswith("Rejected") and "run identity" in said, "the tool refuses without a run identity",
                    said[:80]))
        os.environ[fs.RUN_ENV] = RUN
        try:
            said = tool(a7)
        finally:
            os.environ.pop(fs.RUN_ENV, None)
        out.append((said.startswith("Rejected") and "cap of 3" in said,
                    "the server's feeds_extract applies the same rules (this run's cap is already reached)", said[:80]))
        written = [p.relative_to(tmp) for p in tmp.rglob("*") if p.is_file()]
        planted = {tracked.relative_to(tmp) / "feeds-2026-09-18-eee555" / ex.ALLOCATIONS}  # this guard's own fixture
        out.append((all(str(w).startswith("inbox/") or w.name in ("advisory_list.json", "doc.html") or w in planted
                        for w in written),
                    "every file written is inside the temporary inbox", "%d files; outside: %s" % (
                        len(written), [str(w) for w in written if not str(w).startswith("inbox/")
                                       and w.name not in ("advisory_list.json", "doc.html") and w not in planted][:3])))

        # F6 (2026-09-28 fixes brief): extract() must refuse a passed RunIdentity that does not match this
        # call's own arguments, before any session starts. Never actually calls the model: a mismatch is
        # caught before extract() even reads the document, proved here with a document that does not exist.
        ea = load("extract_advisory_under_test", EXTRACT_ADVISORY, mutation)
        from agents.run_identity import RunIdentity as RI
        doc_a = tmp / "identity-a.pdf"
        doc_a.write_bytes(page())  # RunIdentity.new hashes it, so it must exist; the CALL's own path need not
        ident = RI.new("extractor", "ADV-2026-0001", doc_a)

        def raised(coro):
            try:
                asyncio.run(coro)
                return None
            except Exception as exc:
                return exc

        exc1 = raised(ea.extract(tmp / "does-not-exist.pdf", "ADV-2026-0002", "stub-model", 1.0, 5, run=ident))
        exc2 = raised(ea.extract(tmp / "also-missing.pdf", "ADV-2026-0001", "stub-model", 1.0, 5, run=ident))
        out.append((isinstance(exc1, ValueError) and "ADV-2026-0001" in str(exc1) and "ADV-2026-0002" in str(exc1)
                   and isinstance(exc2, ValueError) and "also-missing.pdf" in str(exc2),
                   "extract() refuses a passed RunIdentity that does not match this call's own advisory id or "
                   "document, before any session starts (no file even read for the mismatched path)",
                   "%s | %s" % (exc1, exc2)))

        # Fix round 1, Important (F6): the case above only ever proves a REFUSAL. A version of the check that
        # refuses every passed identity (or that compares an unresolved path) would stay green. Add the
        # positive case: a MATCHING identity, the same document spelled differently (redundant ".." segments,
        # never resolved by hand here), must get PAST the check -- proved by reaching document_pages, stubbed
        # to raise a sentinel so no session can ever start.
        differently_spelled = doc_a.parent / ".." / doc_a.parent.name / doc_a.name
        assert differently_spelled != doc_a and differently_spelled.resolve() == doc_a.resolve(), (
            "the fixture must be an unresolved spelling of the SAME file, or this case proves nothing")

        class _GotPastIdentityCheck(Exception):
            pass

        real_document_pages = ea.document_pages

        def stubbed(_path):
            raise _GotPastIdentityCheck("stub: extract() reached document_pages -- no session was reachable")
        ea.document_pages = stubbed
        try:
            exc3 = raised(ea.extract(differently_spelled, "ADV-2026-0001", "stub-model", 1.0, 5, run=ident))
        finally:
            ea.document_pages = real_document_pages
        out.append((isinstance(exc3, _GotPastIdentityCheck),
                   "a MATCHING RunIdentity -- same document, spelled differently -- gets past the check "
                   "(reaches document_pages; a refuse-everything or an unresolved-path version would raise "
                   "ValueError here instead, before ever reaching it)", str(exc3)))

        # Prompt-sha brief (2026-09-29): the extractor must pass run_started the hash of the prompt it
        # actually SENDS, not a constant or a stale one. Get further than the identity-check positive case
        # above -- past run_started and the options -- and still start no session, by stubbing query()
        # (not document_pages) in the extract_advisory module namespace -- since slice 2 C2 the session is a
        # ClaudeSDKClient, so it is the client that is stubbed, stopping at its first query(). TELEMETRY_DIR is
        # redirected so the real run_started, left in place, writes nowhere near the checkout.
        doc_b = tmp / "identity-b.pdf"
        doc_b.write_bytes(tiny_pdf(["Advisory text for the prompt-sha probe."]))  # a real PDF: document_pages()
        ident_b = RI.new("extractor", "ADV-2026-0077", doc_b)                    # runs for real, unlike exc1-exc3

        class _GotPastRunStarted(Exception):
            pass

        captured: dict = {}
        real_client = ea.ClaudeSDKClient
        real_run_started = telemetry.run_started
        real_telemetry_dir = telemetry.TELEMETRY_DIR

        class _StopAtFirstQuery:
            def __init__(self, options):
                captured["system_prompt"] = options.system_prompt

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def query(self, prompt, session_id="default"):
                raise _GotPastRunStarted("stub: extract() reached the session's first query() -- no session was started")

        def capturing_run_started(run, model, max_budget_usd, max_turns, tools, **kwargs):
            captured["prompt_sha256"] = kwargs.get("prompt_sha256")
            return real_run_started(run, model, max_budget_usd, max_turns, tools, **kwargs)

        ea.ClaudeSDKClient = _StopAtFirstQuery
        telemetry.run_started = capturing_run_started
        telemetry.TELEMETRY_DIR = tmp / "telemetry-scratch"  # never data/telemetry/
        try:
            exc4 = raised(ea.extract(doc_b, "ADV-2026-0077", "stub-model", 1.0, 5, run=ident_b))
        finally:
            ea.ClaudeSDKClient = real_client
            telemetry.run_started = real_run_started
            telemetry.TELEMETRY_DIR = real_telemetry_dir

        sent_hash = hashlib.sha256(captured.get("system_prompt", "").encode("utf-8")).hexdigest()
        out.append((isinstance(exc4, _GotPastRunStarted)
                   and captured.get("prompt_sha256") == ea.PROMPT_SHA256 == sent_hash,
                   "the extractor passes run_started the hash of the prompt it actually sends: "
                   "sha256(system_prompt) == recorded prompt_sha256 == extract_advisory.PROMPT_SHA256 "
                   "(reaches the session's first query(); no session was started)",
                   "%s | recorded %s | PROMPT_SHA256 %s" % (
                       type(exc4).__name__, str(captured.get("prompt_sha256"))[:16], ea.PROMPT_SHA256[:16])))

        out += quote_checks(mutation, ea, kc, tmp, box)

    out.append((git_status() == before, "the repository's git status is unchanged", ""))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin feeds_extract and an extraction's queue")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule in memory; a check MUST fail")
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
