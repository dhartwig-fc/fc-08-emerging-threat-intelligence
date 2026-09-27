"""
Pin the public walkthrough page: it is a faithful, deterministic projection of the
governed files, and it carries nothing the publish boundary refuses.

Usage:
    python evals/check_walkthrough.py
    python evals/check_walkthrough.py --mutate drop-citation   # the builder skips each typology's last citation; MUST fail
    python evals/check_walkthrough.py --mutate unpinned-log    # the builder reads the WHOLE decision log; MUST fail
    python evals/check_walkthrough.py --mutate wrong-page      # every citation is rendered one page off; MUST fail
    python evals/check_walkthrough.py --mutate swap-notes      # each decision lands under the next link's card; MUST fail
    python evals/check_walkthrough.py --mutate wrong-count     # section 1 miscounts the extractor's typologies; MUST fail
    python evals/check_walkthrough.py --mutate desk-scope      # a desk is shown every family's links; MUST fail
    python evals/check_walkthrough.py --mutate two-runs        # the record-only set counts reviewer additions; MUST fail
    python evals/check_walkthrough.py --mutate typed-score     # merged typology F1 is a typed 0.700, not computed; MUST fail
    python evals/check_walkthrough.py --mutate actor-id        # a resolved actor is shown without its ACT- id; MUST fail
    python evals/check_walkthrough.py --mutate digest-header   # the digest cut starts at the desk file's header; MUST fail
    python evals/check_walkthrough.py --mutate telemetry-count # FAILURE tool calls are left out of the counts; MUST fail
    python evals/check_walkthrough.py --mutate attested-count  # #limits counts only this advisory's attestations; MUST fail
    python evals/check_walkthrough.py --mutate swap-moves      # section 9's "moves F1 x -> y" swaps x and y; MUST fail
    python evals/check_walkthrough.py --mutate resolver-runs   # the builder's _resolver_runs -- what --repin classifies
                                                               # with; the page reads the snapshot -- skips a committed
                                                               # run; caught by (b) and the fixture; MUST fail
    python evals/check_walkthrough.py --mutate resolver-prompt # #limits misstates whether the prompt names the resolver; MUST fail
    python evals/check_walkthrough.py --mutate feed-accepted   # #limits' accepted-feed-items count is off by one; MUST fail
    python evals/check_walkthrough.py --mutate desk-total      # section 1's routing-table desk total is off by one; MUST fail
    python evals/check_walkthrough.py --mutate register-unresolved  # #actors' "named but not resolved" list keeps the
                                                                     # resolved entries too; MUST fail
    python evals/check_walkthrough.py --mutate corpus-count    # #limits' advisory count is off by one; MUST fail
    python evals/check_walkthrough.py --mutate emergent-undecided  # #limits counts DECIDED emergent candidates; MUST fail
    python evals/check_walkthrough.py --mutate legacy-count    # #limits' legacy-queue proposal count is off by one; MUST fail
    python evals/check_walkthrough.py --mutate snapshot-count  # #limits reads the snapshot's null had_resolver as False, so
                                                               # its no-tool-record count disagrees with the snapshot; MUST fail
    python evals/check_walkthrough.py --mutate snapshot-evidence  # a pinned run's files now say it had and used the
                                                                  # resolver (a temporary copy; nothing tracked is
                                                                  # written); MUST fail
    python evals/check_walkthrough.py --mutate unpinned-advisory  # the builder does not filter the advisory list to the
                                                                  # snapshot's corpus; MUST fail
    python evals/check_walkthrough.py --mutate unpinned-golden    # section 9 scores every golden label, not only the
                                                                  # pinned corpus's; MUST fail
    python evals/check_walkthrough.py --mutate snapshot-undercount  # the ledger (read in memory) holds one more accept
                                                                    # decided by taken_on than the snapshot counts; MUST fail

SECTION 10 IS PINNED TO site/walkthrough_snapshot.json. Three of its inputs move every Friday once
live runs are accepted: extraction queue files, accepted feed items in the seen-items ledger, and
new advisory-list entries. The page renders the committed snapshot of them, never the live files,
so an accepted run does not change the page. This guard holds three things apart:
  (a) the page renders the snapshot exactly -- its counts (computed here by the guard's own
      classifier over the PINNED runs' files), its dated span, and a corpus of exactly the pinned
      advisories, which a build over PLANTED live data must leave byte-identical;
  (b) the snapshot still agrees with the evidence it names -- every pinned run's queue file exists
      and its telemetry classifies it as the snapshot says, every pinned advisory is still listed,
      and feed_accepted EQUALS the ledger's accepts decided on or before taken_on. Evidence is
      immutable, so (b) stays green however much new data arrives;
  Section 9 scores ONLY the pinned corpus (owner decision 2026-09-27): the guard rescores it over a
  temporary copy holding only the pinned advisories' golden labels, and the plant adds a golden label
  and records for an unpinned advisory, which must leave the page byte-identical. A malformed snapshot
  is a labelled FAIL, never a traceback.
  (c) an INFO line, never a failure, saying when live data has moved past the snapshot. Re-pinning
      is deliberate: tools/build_walkthrough.py --repin, then rebuild and republish on the owner's go.

WHY. The page will leave this repository. A page that drifts from its inputs, differs
between two machines, or quietly drops a citation says something the governance never
said -- to a reader who cannot check. Every figure on it must come from a file.

OFFLINE and COLD. Tracked inputs only: no PDF, no model, no gitignored file. The
decision-log check works on a TEMPORARY copy of the log with one synthetic decision
appended; the real log is never written.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402
from governance.digest import DIGESTS_DIR, RECORDS_DIR  # noqa: E402
from governance.proposals import ADVISORY_LIST, LEGACY_QUEUE, QUEUE_DIR, link_key, load_queue_files  # noqa: E402
from governance.routing import load_routing  # noqa: E402
from agents.extract_advisory import SYSTEM_PROMPT  # noqa: E402
from agents.telemetry import TELEMETRY_DIR  # noqa: E402
from feeds import ledger as feeds_ledger  # noqa: E402
from evals.actor_resolution import REPORT as ACTOR_REPORT  # noqa: E402
from evals.check_citations import ATTESTED_PATH  # noqa: E402
from evals.score import score_dirs  # noqa: E402
from tools.build_actor_register import load_register  # noqa: E402

REPO_BLOB = "https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence/blob/main/"
TRACE_URL = REPO_BLOB + "evals/traces/FULL_BASELINE_2026-09-12.md"
BANDS_URL = REPO_BLOB + "evals/traces/REVIEWER_BANDS_2026-09-13.md"
LABEL_PASS = ROOT / "evals" / "owner_decisions" / "label_pass_2026-09-24.json"


NOT_RUN = None  # a check's ok value when it cannot run here: printed as NOT RUN, never counted as a failure
INFO = "info"   # a check's ok value for a line that informs and never fails: printed as INFO, never counted

BUILDER = ROOT / "tools" / "build_walkthrough.py"
SNAPSHOT = ROOT / "site" / "walkthrough_snapshot.json"
RESOLVER_SUFFIX = "__knowledge_centre_resolve_actor"
SECTIONS = ("question", "source", "extraction", "grounding", "review",
            "actors", "digest", "telemetry", "score", "limits")
SEEDS = ("0", "1", "4242", "987654")
MUTATIONS = ("drop-citation", "unpinned-log", "wrong-page", "swap-notes", "wrong-count", "desk-scope", "two-runs",
             "typed-score", "actor-id", "digest-header", "telemetry-count", "attested-count", "swap-moves",
             "resolver-runs", "resolver-prompt", "feed-accepted", "desk-total", "register-unresolved",
             "corpus-count", "emergent-undecided", "legacy-count", "snapshot-count", "snapshot-evidence",
             "unpinned-advisory", "unpinned-golden", "snapshot-undercount")
# The guard-side mutations: they change what THIS guard reads, not the builder. Every other mutation
# is the builder's own, passed through --_mutate.
GUARD_MUTATIONS = ("snapshot-evidence", "snapshot-undercount")
MUTATION = None


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_walkthrough", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._MUTATE = None if MUTATION in GUARD_MUTATIONS else MUTATION
    return mod


def _cli(*args, env=None) -> subprocess.CompletedProcess:
    extra = ["--_mutate", MUTATION] if MUTATION and MUTATION not in GUARD_MUTATIONS else []
    return subprocess.run([sys.executable, str(BUILDER)] + list(args) + extra,
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT, env=env)


def section(page: str, sid: str) -> str:
    m = re.search(r'<section id="%s"[^>]*>(.*?)</section>' % re.escape(sid), page, re.S)
    return m.group(1) if m else ""


def _desk_block(text: str, advisory: str):
    """(approved, awaiting) ids from one desk digest's block for advisory, or None if it has none."""
    m = re.search(r"^## %s -- .*?(?=^## |\Z)" % re.escape(advisory), text, re.S | re.M)
    if not m:
        return None
    block = m.group(0)

    def part(head: str) -> str:
        p = re.search(r"^### %s\n(.*?)(?=^### |\Z)" % re.escape(head), block, re.S | re.M)
        return p.group(1) if p else ""
    approved = re.findall(r"^- \*\*(\S+) ", part("Approved links"), re.M)
    approved += re.findall(r"^- \*\*(.+?)\*\*", part("Approved emergent candidates"), re.M)
    awaiting = re.findall(r"^- (\S+) .* -- asserted by the pipeline", part("Awaiting review"), re.M)
    return sorted(approved), sorted(awaiting)


def _pinned_advisory_decisions(advisory: str) -> list:
    """The guard's OWN reading of the pinned prefix -- not the builder's -- so the two can disagree."""
    batch = (DIGESTS_DIR / "CURRENT").read_text(encoding="utf-8").strip()
    manifest = json.loads((DIGESTS_DIR / batch / "manifest.json").read_text(encoding="utf-8"))
    _, _, decisions = gd.log_prefix(manifest["decision_log"]["lines"])
    return [d for d in decisions if d.advisory_id == advisory]


def _attrs(block: str, attr: str) -> dict:
    """{attr value: inner text} for every element carrying attr in block (values unescaped)."""
    return {html.unescape(m.group(1)): html.unescape(m.group(2))
            for m in re.finditer(r'<[a-z]+[^>]*? %s="([^"]*)"[^>]*>([^<]*)<' % re.escape(attr), block)}


def _desk_cut(text: str, advisory: str) -> str:
    """The guard's OWN cut of one advisory's block from a desk digest: its heading line up to the
    next level-2 heading or the end. String search, not the builder's regex, so the two can disagree."""
    start = text.find("\n## %s -- " % advisory)
    if start < 0:
        return ""
    start += 1
    end = text.find("\n## ", start)
    return (text[start:] if end < 0 else text[start:end]).rstrip("\n")


def _own_classify(run: str, queue_dir: Path, telemetry_dir: Path) -> dict:
    """The guard's OWN classification of one extraction run from its files -- not the builder's
    _resolver_runs, so the two can disagree. queue: the run's queue file exists. had_resolver: None when
    it has no telemetry or its RUN_STARTED carries no tools list (no record), else whether the list names
    the resolver. resolved: whether a resolver call answered "Resolved:"."""
    tel = telemetry_dir / ("%s.jsonl" % run)
    evs = ([json.loads(line) for line in tel.read_text(encoding="utf-8").splitlines() if line.strip()]
           if tel.exists() else [])
    start = next((ev for ev in evs if ev.get("stage") == "RUN_STARTED"), None)
    tools = None if start is None else start["payload"].get("tools")
    return {"queue": (queue_dir / ("%s.jsonl" % run)).exists(),
            "had_resolver": None if tools is None else any(t.endswith(RESOLVER_SUFFIX) for t in tools),
            "resolved": any(ev.get("stage") == "FC08_TOOL_CALL"
                            and ev["payload"].get("tool", "").endswith(RESOLVER_SUFFIX)
                            and ev["payload"].get("outcome", "").startswith('{"result":"Resolved: ') for ev in evs)}


def _own_counts_of(classified: list) -> dict:
    """Section 10's four resolver counts from a list of _own_classify results."""
    return {"runs": len(classified), "with_tool": sum(1 for c in classified if c["had_resolver"] is True),
            "no_record": sum(1 for c in classified if c["had_resolver"] is None),
            "resolved": sum(1 for c in classified if c["resolved"])}


def _own_resolver_counts(queue_dir: Path, telemetry_dir: Path) -> dict:
    """The guard's OWN reading of the resolver counts over EVERY committed extraction queue in queue_dir.
    A run is COMMITTED when it has an EXTRACTOR queue file: '-extractor-' in its stem, so a reviewer run's
    queue (propose_link names every queue file after the calling run's id, and the reviewer agent calls it
    too) is never counted as an extraction. Returns the four counts as numbers, not the run ids."""
    runs = sorted(q.stem for q in queue_dir.glob("*.jsonl") if "-extractor-" in q.stem)
    return _own_counts_of([_own_classify(r, queue_dir, telemetry_dir) for r in runs])


def _read_snapshot() -> dict:
    """The committed snapshot, read here -- not through the builder's load_snapshot."""
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _snapshot_problems(snap) -> list:
    """The guard's OWN shape check of a snapshot, as readable problems -- so a malformed file is a
    labelled FAIL, never a KeyError or TypeError traceback. Empty means well-formed."""
    if not isinstance(snap, dict):
        return ["not a JSON object"]
    out = []
    want = ["advisories", "extraction_runs", "feed_accepted", "taken_on"]
    if sorted(snap) != want:
        out.append("fields %s, want exactly %s" % (sorted(snap), want))
    t = snap.get("taken_on")
    if not (isinstance(t, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)):
        out.append("taken_on %r is not YYYY-MM-DD" % (t,))
    adv = snap.get("advisories")
    if not (isinstance(adv, list) and all(isinstance(a, str) for a in adv) and adv == sorted(set(adv))):
        out.append("advisories is not a sorted list of distinct ids")
    runs = snap.get("extraction_runs")
    if not (isinstance(runs, list) and all(
            isinstance(r, dict) and sorted(r) == ["had_resolver", "resolved", "run_id"]
            and isinstance(r["run_id"], str) and (r["had_resolver"] is None or isinstance(r["had_resolver"], bool))
            and isinstance(r["resolved"], bool) for r in runs)
            and [r["run_id"] for r in runs] == sorted({r["run_id"] for r in runs})):
        out.append("extraction_runs is not a run_id-sorted list of distinct {run_id, had_resolver (bool or null), "
                   "resolved (bool)}")
    fa = snap.get("feed_accepted")
    if not (isinstance(fa, int) and not isinstance(fa, bool) and fa >= 0):
        out.append("feed_accepted %r is not a count" % (fa,))
    return out


def _accepts_by(entries, taken_on: str) -> int:
    """The ledger's accepts decided on or before taken_on: what "by that date K had been accepted" means."""
    return sum(1 for x in entries if x["decision"] == "accept" and x["decided_on"] <= taken_on)


def _pinned_scores(snapshot: dict) -> dict:
    """Section 9 over the PINNED corpus, computed the guard's own way: score_dirs, unfiltered, over a
    temporary golden directory holding only the pinned advisories' labels -- not the builder's
    advisory_ids filter, so the two can disagree."""
    keep = set(snapshot["advisories"])
    with tempfile.TemporaryDirectory(prefix="fc08_pinned_golden_") as tmp:
        for f in sorted((ROOT / "evals" / "golden").glob("ADV-*.json")):
            if json.loads(f.read_text(encoding="utf-8")).get("advisory_id") in keep:
                shutil.copy(f, Path(tmp) / f.name)
        return {run: score_dirs(Path(tmp), pred) for run, pred in (("extraction", ROOT / "data" / "records"),
                                                                    ("reviewer", RECORDS_DIR))}


def _snapshot_self_checks(bw) -> list:
    """Standing proofs, on synthetic data only, that (b)'s exact accepted-count reading discriminates by
    date, and that a malformed snapshot is refused READABLY by both sides: the guard's own validator
    names a problem, and the builder's load_snapshot raises a ValueError naming the file."""
    out = []
    taken = "2026-10-02"
    ledger = [{"decision": "accept", "decided_on": taken}, {"decision": "accept", "decided_on": "2026-10-03"},
              {"decision": "drop", "decided_on": "2026-10-01"}]
    out.append((_accepts_by(ledger, taken) == 1 and _accepts_by(ledger, "2026-10-03") == 2
                and _accepts_by(ledger, "2026-10-01") == 0,
                "(b)'s exact accepted-count reading counts accepts decided ON or BEFORE taken_on and nothing else "
                "(a snapshot counting 0 against an accept on its own date is an under-count)",
                "by %s: %d; by 2026-10-03: %d; by 2026-10-01: %d" % (taken, _accepts_by(ledger, taken),
                                                                  _accepts_by(ledger, "2026-10-03"),
                                                                  _accepts_by(ledger, "2026-10-01"))))
    good = {"taken_on": taken, "advisories": ["ADV-9999-0001"], "feed_accepted": 0,
            "extraction_runs": [{"run_id": "r", "had_resolver": None, "resolved": False}]}
    bad = {"missing feed_accepted": {k: v for k, v in good.items() if k != "feed_accepted"},
           "feed_accepted a string": dict(good, feed_accepted="0"),
           "feed_accepted a bool": dict(good, feed_accepted=False),
           "taken_on not a date": dict(good, taken_on="27 Sep"),
           "advisories not a list": dict(good, advisories="ADV-9999-0001"),
           "had_resolver an int": dict(good, extraction_runs=[{"run_id": "r", "had_resolver": 1, "resolved": False}]),
           "a run missing resolved": dict(good, extraction_runs=[{"run_id": "r", "had_resolver": None}]),
           "run_ids of mixed types": dict(good, extraction_runs=[{"run_id": "r", "had_resolver": None, "resolved": False},
                                                                 {"run_id": 7, "had_resolver": None, "resolved": False}]),
           "a list, not an object": [good]}
    wrong = []
    with tempfile.TemporaryDirectory(prefix="fc08_bad_snapshot_") as tmp:
        path = Path(tmp) / "walkthrough_snapshot.json"
        cases = [(name, json.dumps(snap)) for name, snap in bad.items()] + [("not JSON", "{\"taken_on\": ")]
        for name, text in cases:
            path.write_text(text, encoding="utf-8")
            try:
                own = _snapshot_problems(json.loads(text))
            except json.JSONDecodeError:
                own = ["not JSON"]
            try:
                bw.load_snapshot(path)
                built = "ACCEPTED"
            except ValueError as exc:
                built = "" if path.name in str(exc) else "ValueError not naming the file: %s" % exc
            except Exception as exc:  # anything but a ValueError is a crash, not a refusal
                built = "%s: %s" % (type(exc).__name__, exc)
            if not own or built:
                wrong.append("%s: guard %s; builder %s" % (name, own or "found nothing", built or "refused"))
        path.write_text(json.dumps(good), encoding="utf-8")
        try:
            bw.load_snapshot(path)
            ok_good = not _snapshot_problems(good)
        except Exception as exc:
            ok_good, wrong = False, wrong + ["the well-formed control was refused: %s" % exc]
    out.append((ok_good and not wrong,
                "a malformed snapshot (%d shapes) is refused readably: the guard's validator names a problem and "
                "the builder raises a ValueError naming the snapshot; a well-formed control is accepted" % len(cases),
                "; ".join(wrong) or "all %d refused, control accepted" % len(cases)))
    return out


def _resolver_counts_fixture_checks(bw) -> list:
    """A synthetic fixture, written only under tempfile.TemporaryDirectory (nothing touches the
    repository), that gives every committed count a NON-zero answer -- the real committed data has
    every resolver count at 0, so a wrong predicate on either side would still agree with it by
    accident. Proves both counters -- the guard's own _own_resolver_counts and the builder's
    _resolver_runs -- discriminate: an extractor run that resolved; one with tools recorded but not the
    resolver; one with a queue file and no telemetry at all; a REVIEWER run that lists the resolver in
    its tools (must not be counted as an extraction); and an extractor run whose resolver call answered
    Unresolved (has the tool, does not resolve)."""
    resolver = "mcp__knowledge_centre__knowledge_centre_resolve_actor"
    other = "mcp__knowledge_centre__knowledge_centre_search_typologies"

    def write_run(queue_dir: Path, telemetry_dir: Path, run_id: str, tools, outcome: str = None,
                  telemetry_file: bool = True) -> None:
        (queue_dir / ("%s.jsonl" % run_id)).write_text("", encoding="utf-8")
        if not telemetry_file:
            return
        agent = "reviewer" if "-reviewer-" in run_id else "extractor"
        events = [{"stage": "RUN_STARTED", "status": "SUCCESS", "timestamp": "2026-10-02T00:00:00Z",
                  "message": "%s run started" % agent,
                  "payload": {"run_id": run_id, "agent": agent, "advisory_id": "ADV-9999",
                              "model": "claude-sonnet-5", "max_budget_usd": 5.0, "max_turns": 60,
                              "pdf_sha256": "fixture", "tools": list(tools)}}]
        if outcome is not None:
            events.append({"stage": "FC08_TOOL_CALL", "status": "SUCCESS", "timestamp": "2026-10-02T00:00:01Z",
                           "message": "%s resolve_actor" % agent,
                           "payload": {"run_id": run_id, "agent": agent, "advisory_id": "ADV-9999",
                                       "tool": resolver, "tool_use_id": "t1", "latency_ms": 5,
                                       "outcome": outcome}})
        (telemetry_dir / ("%s.jsonl" % run_id)).write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    out = []
    with tempfile.TemporaryDirectory(prefix="fc08_resolver_fixture_") as tmp:
        queue_dir, telemetry_dir = Path(tmp) / "proposals", Path(tmp) / "telemetry"
        queue_dir.mkdir()
        telemetry_dir.mkdir()

        write_run(queue_dir, telemetry_dir, "adv-9999-extractor-aaaaaaaaaa", [resolver],
                  outcome='{"result":"Resolved: X -> ACT-1 X (matched \'X\')"}')
        write_run(queue_dir, telemetry_dir, "adv-9999-extractor-bbbbbbbbbb", [other])
        write_run(queue_dir, telemetry_dir, "adv-9999-extractor-cccccccccc", [], telemetry_file=False)
        write_run(queue_dir, telemetry_dir, "adv-9999-reviewer-dddddddddd", [resolver],
                  outcome='{"result":"Resolved: Y -> ACT-2 Y (matched \'Y\')"}')
        write_run(queue_dir, telemetry_dir, "adv-9999-extractor-eeeeeeeeee", [resolver],
                  outcome='{"result":"Unresolved: no candidate match"}')

        want = {"runs": 4, "with_tool": 2, "no_record": 1, "resolved": 1}

        own = _own_resolver_counts(queue_dir, telemetry_dir)
        out.append((own == want,
                    "the guard's own resolver counts, on a synthetic non-zero fixture, discriminate "
                    "extractor-vs-reviewer runs, tool presence, no telemetry and Resolved-vs-Unresolved",
                    "want %s; got %s" % (want, own)))

        built = bw._resolver_runs(queue_dir, telemetry_dir)
        built_counts = {k: len(v) for k, v in built.items()}
        out.append((built_counts == want,
                    "the builder's _resolver_runs gives the same counts as the guard's own, on the same "
                    "fixture",
                    "want %s; got %s" % (want, built_counts)))
        # A count alone cannot tell "the right run resolved" from "some other run happened to resolve
        # instead" when exactly one run matches each predicate -- swapping "Resolved: " for
        # "Unresolved: " leaves the TOTAL at 1 either way. Pin the actual ids too.
        want_ids = {
            "runs": {"adv-9999-extractor-aaaaaaaaaa", "adv-9999-extractor-bbbbbbbbbb",
                    "adv-9999-extractor-cccccccccc", "adv-9999-extractor-eeeeeeeeee"},
            "with_tool": {"adv-9999-extractor-aaaaaaaaaa", "adv-9999-extractor-eeeeeeeeee"},
            "no_record": {"adv-9999-extractor-cccccccccc"},
            "resolved": {"adv-9999-extractor-aaaaaaaaaa"},
        }
        got_ids = {k: set(v) for k, v in built.items()}
        out.append((got_ids == want_ids,
                    "the builder's _resolver_runs names the RIGHT runs, not just the right totals -- "
                    "specifically the Resolved run, not the Unresolved one, as resolved",
                    "want %s; got %s" % (want_ids, got_ids)))

        # --repin writes what compute_snapshot returns. On the same fixture, plus a ledger with one
        # accept and one drop and a two-entry advisory list, it must classify each run as the guard's
        # own classifier does -- null had_resolver for no record, never False -- and count one accept.
        ledger_path, adv_path = Path(tmp) / "ledger.json", Path(tmp) / "advisories.json"
        ledger_path.write_text(json.dumps({"schema": feeds_ledger.SCHEMA, "items": [
            {"source": "ofsi", "item_id": "a", "decision": "accept", "first_seen_run": "r", "decided_on": "2026-10-02"},
            {"source": "ofsi", "item_id": "b", "decision": "drop", "first_seen_run": "r", "decided_on": "2026-10-02"}]}),
            encoding="utf-8")
        adv_path.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-9999-0002"},
                                                       {"advisory_id": "ADV-9999-0001"}]}), encoding="utf-8")
        try:
            snap = bw.compute_snapshot("2026-10-02", queue_dir=queue_dir, telemetry_dir=telemetry_dir,
                                       ledger_path=ledger_path, advisory_list=adv_path)
        except Exception as exc:  # a missing or broken --repin is a failure to report, not a crash
            snap = "%s: %s" % (type(exc).__name__, exc)
        want_snap = {"taken_on": "2026-10-02", "feed_accepted": 1, "advisories": ["ADV-9999-0001", "ADV-9999-0002"],
                     "extraction_runs": [
                         dict(run_id=r, **{k: v for k, v in _own_classify(r, queue_dir, telemetry_dir).items()
                                           if k != "queue"})
                         for r in sorted(want_ids["runs"])]}
        out.append((snap == want_snap
                    and [r["had_resolver"] for r in want_snap["extraction_runs"]] == [True, False, None, True],
                    "--repin's compute_snapshot, on the same non-zero fixture, classifies every extraction run as "
                    "the guard's own classifier does (null for no record), counts one accepted item and sorts the "
                    "advisory ids", "want %s; got %s" % (want_snap, snap)))
    return out


def _plant_checks(bw, page: str, snapshot: dict) -> list:
    """(a)'s strongest clause: live data moving past the snapshot must leave the page BYTE-IDENTICAL.
    Builds the page in process over TEMPORARY copies with each of the three weekly-moving inputs planted
    -- a new extractor queue file WITH telemetry that had and used the resolver, an accepted item in the
    ledger, a new advisory-list entry, and a golden label with extractor and merged records for that
    unpinned advisory (section 9 scores only the pinned corpus) -- and compares it with the committed
    page. The advisory is
    planted twice: once as a live acceptance would add it (no label_status, which the builder refuses
    for a PINNED advisory), once fully labelled (so a leak shows as a count, not only as a refusal).
    Nothing under the repository is written; every redirected global is restored."""
    out = []
    listed = json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))
    base = dict(listed["advisories"][0])
    unlabelled = {k: v for k, v in base.items() if k != "label_status"}
    unlabelled.update(advisory_id="ADV-2099-0001", title="Planted live advisory")
    labelled = dict(base, advisory_id="ADV-2099-0002", title="Planted labelled advisory",
                    label_status=bw.LABEL_PROVENANCE)  # labelled, and naming no disputed entries of its own
    run = "adv-2099-0001-extractor-planted000"
    saved = (bw.QUEUE_DIR, bw.ADVISORY_LIST, bw.feeds_ledger, bw.telemetry.TELEMETRY_DIR,
             bw.GOLDEN_DIR, bw.EXTRACTOR_RECORDS, bw.RECORDS_DIR)
    with tempfile.TemporaryDirectory(prefix="fc08_walkthrough_plant_") as tmp:
        tmp = Path(tmp)
        queue_dir, telemetry_dir = tmp / "proposals", tmp / "telemetry"
        shutil.copytree(QUEUE_DIR, queue_dir)
        shutil.copytree(TELEMETRY_DIR, telemetry_dir)
        (queue_dir / ("%s.jsonl" % run)).write_text("", encoding="utf-8")
        (telemetry_dir / ("%s.jsonl" % run)).write_text("\n".join(json.dumps(ev) for ev in [
            {"stage": "RUN_STARTED", "status": "SUCCESS", "timestamp": "2099-01-01T00:00:00Z", "message": "planted",
             "payload": {"run_id": run, "tools": ["mcp__knowledge_centre" + RESOLVER_SUFFIX]}},
            {"stage": "FC08_TOOL_CALL", "status": "SUCCESS", "timestamp": "2099-01-01T00:00:01Z", "message": "planted",
             "payload": {"run_id": run, "tool": "mcp__knowledge_centre" + RESOLVER_SUFFIX,
                         "outcome": '{"result":"Resolved: X -> ACT-1 X"}'}}]) + "\n", encoding="utf-8")
        # A golden label and both records for the unpinned ADV-2099-0002, each a copy of a pinned
        # advisory's with the id changed -- a pair score_dirs WOULD score if it were not filtered.
        planted_dirs = {}
        for key, src in (("golden", bw.GOLDEN_DIR), ("records", bw.EXTRACTOR_RECORDS), ("merged", bw.RECORDS_DIR)):
            planted_dirs[key] = tmp / key
            shutil.copytree(src, planted_dirs[key])
            doc = json.loads((src / "ADV-2026-0001.json").read_text(encoding="utf-8"))
            doc["advisory_id"] = labelled["advisory_id"]
            (planted_dirs[key] / ("%s.json" % labelled["advisory_id"])).write_text(json.dumps(doc), encoding="utf-8")
        ledger_path = tmp / "ledger.json"
        entries = list(feeds_ledger.load().values()) + [
            {"source": "ofsi", "item_id": "planted", "decision": "accept", "first_seen_run": run,
             "decided_on": "2099-01-01"}]
        ledger_path.write_text(json.dumps({"schema": feeds_ledger.SCHEMA, "items": entries}), encoding="utf-8")

        class _Ledger:
            """The ledger module as the builder sees it, loading the planted copy whatever path it asks."""
            SCHEMA, SEEN_PATH = feeds_ledger.SCHEMA, ledger_path

            @staticmethod
            def load(path=None):
                return feeds_ledger.load(ledger_path)

        for name, planted in (("unlabelled", unlabelled), ("labelled", labelled)):
            adv_path = tmp / ("advisories_%s.json" % name)
            adv_path.write_text(json.dumps(dict(listed, advisories=listed["advisories"] + [planted])), encoding="utf-8")
            try:
                bw.QUEUE_DIR, bw.ADVISORY_LIST, bw.feeds_ledger = queue_dir, adv_path, _Ledger
                bw.telemetry.TELEMETRY_DIR = telemetry_dir
                bw.GOLDEN_DIR, bw.EXTRACTOR_RECORDS, bw.RECORDS_DIR = (planted_dirs["golden"], planted_dirs["records"],
                                                                       planted_dirs["merged"])
                try:
                    inp = bw.inputs()
                    built, corpus = bw.build(inp), sorted(inp["advisories"])
                except Exception as exc:  # a leak that makes the builder refuse is still a leak
                    built, corpus = "%s: %s" % (type(exc).__name__, exc), None
            finally:
                (bw.QUEUE_DIR, bw.ADVISORY_LIST, bw.feeds_ledger, bw.telemetry.TELEMETRY_DIR,
                 bw.GOLDEN_DIR, bw.EXTRACTOR_RECORDS, bw.RECORDS_DIR) = saved
            out.append((built == page and corpus == snapshot["advisories"],
                        "a build over planted live data (a new extraction queue that resolved an actor, an accepted "
                        "ledger item, a new %s advisory-list entry, a golden label and records for an unpinned "
                        "advisory) is byte-identical to the committed page, and its corpus is exactly the "
                        "snapshot's" % name,
                        "identical" if built == page else ("the page CHANGED" if corpus is not None else built)[:300]))
    return out


def checks_sections_6_to_10(bw, page: str, record: dict, pinned: list, snapshot: dict) -> list:
    out = []

    # 6 -- actors. Every resolution row for the advisory, with its ACT- id when resolved, its
    # entries when ambiguous; every category actor as not resolvable; the entity_key seam empty.
    actors = section(page, "actors")
    rows = [r for r in json.loads(ACTOR_REPORT.read_text(encoding="utf-8"))["actors"]
            if r["advisory_id"] == bw.ADVISORY]
    shown = {html.unescape(m.group(1)): (m.group(2), html.unescape(m.group(3)), html.unescape(m.group(4)))
             for m in re.finditer(r'<tr class="actor" data-actor="([^"]*)" data-status="([a-z]*)" '
                                  r'data-act="([^"]*)" data-entries="([^"]*)">', actors)}
    want = {r["name"]: (r["status"], r["actor_id"] or "", ",".join(r["entries"])) for r in rows}
    ids_visible = all(r["actor_id"] in actors for r in rows if r["status"] == "resolved")
    out.append((bool(rows) and shown == want and ids_visible,
                "#actors shows each %s resolution row: name, status, ACT- id when resolved, entries when ambiguous"
                % bw.ADVISORY, "want %s; page %s" % (want, shown)))
    cats = [a["name"] for a in record["actors"] if a.get("actor_type") == "category"]
    cat_shown = [html.unescape(m.group(1)) for m in
                 re.finditer(r'<li class="category" data-actor="([^"]*)">[^<]*<span class="nr">recorded by the '
                             r'extractor as a category, so never looked up</span></li>', actors)]
    out.append((bool(cats) and cat_shown == cats and len(rows) + len(cats) == len(record["actors"])
                and "not a named party" not in actors,
                "#actors lists every category actor in the record, in order, as recorded by the extractor as a "
                "category and never looked up (not as 'not a named party')",
                "record %s; page %s; named rows %d + categories %d vs %d actors"
                % (cats, cat_shown, len(rows), len(cats), len(record["actors"]))))
    listed = {a["advisory_id"]: a for a in json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    publishers = {t.strip() for t in listed[bw.ADVISORY]["publisher"].split("/")}
    by_name = {a["name"]: a for a in record["actors"]}
    own = sorted(r["name"] for r in rows if r["status"] == "unresolved"
                 and ({r["name"]} | set(by_name.get(r["name"], {}).get("aliases", []))) & publishers)
    said = sorted(html.unescape(m.group(1)) for m in re.finditer(r'data-publisher="([^"]*)"', actors))
    out.append((bool(own) and said == own,
                "#actors names exactly the unresolved actors that are the note's own publishers",
                "computed %s; page %s" % (own, said)))
    register = load_register()
    # The register's OWN reading: parties the reference labels name for this advisory that no row resolved
    # (resolved to them, or listed among an ambiguous row's entries).
    reached = {r["actor_id"] for r in rows if r["status"] == "resolved"} | {x for r in rows for x in r["entries"]}
    named_here = [a for a in register if any(n["advisory_id"] == bw.ADVISORY for n in a.get("named_in", []))]
    unresolved_reg = sorted(a["actor_id"] for a in named_here if a["actor_id"] not in reached)
    pairs = {m.group(1): html.unescape(m.group(2)) for m in
             re.finditer(r'data-register="(ACT-[0-9a-f]+)" data-category="([^"]*)"', actors)}
    n_named = _attrs(actors, "data-count").get("named-unresolved")
    out.append((bool(named_here) and bool(unresolved_reg) and sorted(pairs) == unresolved_reg
                and n_named == str(len(unresolved_reg)) and all(c in cats for c in pairs.values()),
                "#actors names each register entry named in %s that no row resolved, each against a category "
                "actor in the record" % bw.ADVISORY,
                "register %s; page %s (%s)" % (unresolved_reg, pairs, n_named)))
    empty = sum(1 for a in register if a.get("entity_key") is None)
    m = re.search(r'data-entity-key="empty" data-empty="(\d+)" data-of="(\d+)"', actors)
    out.append((bool(m) and (int(m.group(1)), int(m.group(2))) == (empty, len(register)) and empty == len(register),
                "#actors shows the entity_key seam empty, with the register's own count",
                "register %d/%d empty; page %s" % (empty, len(register), m.groups() if m else None)))

    # 7 -- digest. The advisory's block from the Sanctions desk file of the CURRENT batch, verbatim.
    digest = section(page, "digest")
    batch = (DIGESTS_DIR / "CURRENT").read_text(encoding="utf-8").strip()
    desk_text = (DIGESTS_DIR / batch / "sanctions_desk.md").read_text(encoding="utf-8")
    cut = _desk_cut(desk_text, bw.ADVISORY)
    out.append((bool(cut) and ('<pre class="digest">%s</pre>' % html.escape(cut)) in digest,
                "#digest carries the %s block of batch %s's Sanctions desk file, exactly (escaped)"
                % (bw.ADVISORY, batch), "%d chars cut; %s" % (len(cut), "present" if cut and html.escape(cut) in digest
                                                               else "NOT on the page as cut")))
    manifest = json.loads((DIGESTS_DIR / batch / "manifest.json").read_text(encoding="utf-8"))
    shown_batch = _attrs(digest, "data-batch")
    shown_lines = _attrs(digest, "data-count").get("digest-log-lines")
    out.append((list(shown_batch) == [batch] and shown_lines == str(manifest["decision_log"]["lines"]),
                "#digest names the CURRENT batch and its pinned decision-log line count",
                "CURRENT %s, %d lines; page %s, %s" % (batch, manifest["decision_log"]["lines"],
                                                      list(shown_batch), shown_lines)))

    # 8 -- telemetry. Every count recomputed from the run's own file.
    tel = section(page, "telemetry")
    events = [json.loads(l) for l in (TELEMETRY_DIR / ("%s.jsonl" % bw.TELEMETRY_RUN))
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    calls = {}
    for ev in events:
        if ev["stage"] == "FC08_TOOL_CALL":
            k = (ev["payload"]["tool"], ev["status"])
            calls[k] = calls.get(k, 0) + 1
    got = {(html.unescape(m.group(1)), m.group(2)): int(m.group(3))
           for m in re.finditer(r'data-tool="([^"]*)" data-status="([A-Z]+)">(\d+)<', tel)}
    got = {k: v for k, v in got.items() if v}
    perms = {st: sum(1 for ev in events if ev["stage"] == st) for st in ("PERMISSION_ALLOWED", "PERMISSION_DENIED")}
    got_perms = {k: int(v) for k, v in _attrs(tel, "data-perm").items()}
    n_events = _attrs(tel, "data-count").get("events")
    out.append((bool(calls) and got == calls and got_perms == perms and n_events == str(len(events)),
                "#telemetry's per-tool, per-status call counts, permission counts and event total equal the file's",
                "file %s %s %d; page %s %s %s" % (sorted(calls.items()), perms, len(events), sorted(got.items()),
                                                 got_perms, n_events)))
    done = [ev for ev in events if ev["stage"] == "RUN_COMPLETED"]
    started = [ev for ev in events if ev["stage"] == "RUN_STARTED"]
    raw = {m.group(1): (json.loads(html.unescape(m.group(2))), html.unescape(m.group(3)))
           for m in re.finditer(r'data-rc="([a-z_]+)" data-raw="([^"]*)">([^<]*)<', tel)}
    ok_rc, why = len(done) == 1 and len(started) == 1, []
    if ok_rc:
        p, s0 = done[0]["payload"], started[0]["payload"]
        expect = {"turns": (p["turns"], "%d of at most %d" % (p["turns"], s0["max_turns"])),
                  "duration_ms": (p["duration_ms"], "%.1f seconds" % (p["duration_ms"] / 1000)),
                  "cost_usd": (p["cost_usd"], "US$%.2f at API prices, as computed by the agent SDK; not a bill"
                               % p["cost_usd"]),
                  "validated": (p["validated"], "yes" if p["validated"] else "no")}
        ok_rc = raw == expect
        why = [expect, raw]
    out.append((ok_rc, "#telemetry's turns, duration, cost and validated equal the RUN_COMPLETED payload", str(why)))
    queued, _ = load_queue_files([QUEUE_DIR / ("%s.jsonl" % bw.TELEMETRY_RUN)])
    cited = {pid for d in pinned for pid in d.proposal_ids}
    decided_links = {d.link_key for d in pinned}
    tel_ids = [q.typology_id or q.emergent_label for q in queued]
    sets = {"tel-proposed": sorted(tel_ids),
            "tel-decided-elsewhere": sorted(q.typology_id or q.emergent_label for q in queued
                                            if q.link_key in decided_links),
            "tel-no-decision": sorted(q.typology_id or q.emergent_label for q in queued
                                      if q.link_key not in decided_links)}
    shown_sets = {k: sorted(x.strip() for x in v.split(",") if x.strip() and x.strip() != "none")
                  for k, v in _attrs(tel, "data-set").items()}
    n_cited = _attrs(tel, "data-count").get("tel-cited")
    rec_ext = {t["typology_id"] for t in record["typologies"]
               if t.get("typology_id") and t.get("added_by") in (None, "extractor")}
    out.append((bool(queued) and bw.TELEMETRY_RUN in tel and shown_sets == sets
                and {q.typology_id for q in queued if q.typology_id} != rec_ext
                and "neither the run the owner decided" in tel
                and n_cited == str(sum(1 for q in queued if q.proposal_id in cited)),
                "#telemetry names its run, its proposals, and which of their links the pinned log decided",
                "want %s cited %d; page %s cited %s" % (sets, sum(1 for q in queued if q.proposal_id in cited),
                                                        shown_sets, n_cited)))

    tel_runs = sorted(f.stem for f in TELEMETRY_DIR.glob("%s-*.jsonl" % bw.ADVISORY.lower()))
    shown_runs = _attrs(tel, "data-count").get("tel-runs")
    out.append((shown_runs == str(len(tel_runs)) and bw.TELEMETRY_RUN in tel_runs and bw.DECIDED_RUN not in tel_runs
                and ("The decided run, <code>%s</code>, has none." % bw.DECIDED_RUN) in tel,
                "#telemetry's count of this advisory's telemetry runs equals the telemetry directory's, and the "
                "decided run has none there", "directory %s; page %s" % (tel_runs, shown_runs)))

    # 9 -- score. All 24 values recomputed with the scorer at check time.
    sc = section(page, "score")
    wrong = []
    n = 0
    reports = _pinned_scores(snapshot)
    for run in ("extraction", "reviewer"):
        totals = reports[run]["totals"]
        for field in ("typologies", "emergent", "actors", "jurisdictions"):
            for metric in ("precision", "recall", "f1"):
                n += 1
                cell = re.search(r'data-score="%s" data-field="%s" data-m="%s">([^<]*)<' % (run, field, metric), sc)
                want_v = "%.3f" % totals[field][metric]
                if not cell or cell.group(1) != want_v:
                    wrong.append("%s/%s/%s want %s page %s" % (run, field, metric, want_v,
                                                              cell.group(1) if cell else None))
    out.append((n == 24 and not wrong and set(reports["extraction"]["scored"]) <= set(snapshot["advisories"]),
                "#score's 24 precision/recall/F1 values equal score_dirs recomputed now over the PINNED corpus's "
                "golden labels only",
                "; ".join(wrong) or "all 24 equal"))
    out.append(('href="%s"' % html.escape(TRACE_URL) in sc and 'href="%s"' % html.escape(BANDS_URL) in sc
                and "single full-set run" in sc and "no bands of their own" in sc,
                "#score says the figures are single runs without bands and links both committed traces", ""))
    ext_t, rev_t = reports["extraction"]["totals"], reports["reviewer"]["totals"]
    want_moves = {f: ("%.3f" % ext_t[f]["f1"], "%.3f" % rev_t[f]["f1"]) for f in ext_t if ext_t[f] != rev_t[f]}
    got_moves = {m.group(1): (m.group(2), m.group(3)) for m in
                 re.finditer(r'data-move="([a-z]+)" data-from="([0-9.]+)" data-to="([0-9.]+)">[^<]* F1 \2 &rarr; \3<',
                             sc)}
    out.append((bool(want_moves) and got_moves == want_moves,
                "#score's 'adding the reviewer moves F1 x -> y' names each moved field with its own two F1 values",
                "want %s; page %s" % (want_moves, got_moves)))
    label_pass = [d for d in json.loads(LABEL_PASS.read_text(encoding="utf-8"))["decisions"]
                  if d["advisory_id"] in set(snapshot["advisories"])]
    sc_counts = _attrs(sc, "data-count")
    out.append((sc_counts.get("scored") == str(len(reports["extraction"]["scored"]))
                and sc_counts.get("label-decided") == str(len(label_pass))
                and "drafted and reviewed by Claude" in sc and "hand-written" not in page,
                "#score names the advisories scored and the owner-decided label entries, and says the labels are "
                "Claude's", "page %s; scored %d, label pass %d" % (sc_counts, len(reports["extraction"]["scored"]),
                                                                  len(label_pass))))

    # 10 -- limits. Every count recomputed.
    lim = section(page, "limits")
    decided_keys = set(gd.latest(pinned))
    undecided_emergent = sorted(t["label"] for t in record["typologies"] if not t.get("typology_id")
                                and link_key(bw.ADVISORY, None, t["label"]) not in decided_keys)
    in_digests = sorted(lab for lab in undecided_emergent for f in sorted((DIGESTS_DIR / batch).glob("*.md"))
                        if lab in f.read_text(encoding="utf-8"))
    shown_und = _attrs(lim, "data-set").get("emergent-undecided", "")
    out.append((all(html.escape(lab) in lim for lab in undecided_emergent) and not in_digests
                and bool(shown_und) == bool(undecided_emergent),
                "#limits names this record's undecided emergent candidates, and no desk file of the batch carries "
                "them, as it says", "record %s; in a desk file: %s; page %r" % (undecided_emergent, in_digests,
                                                                             shown_und)))
    out.append(("Live ingestion is being built" in lim and "Nothing flows into detection yet" in lim,
                "#limits says live ingestion is still being built, and that nothing flows into detection yet", ""))
    attested = json.loads(ATTESTED_PATH.read_text(encoding="utf-8"))["attested"]
    emergent_ok = sum(1 for d in gd.latest(gd.log_prefix(manifest["decision_log"]["lines"])[2]).values()
                      if d.kind == "emergent" and d.decision == "approve")
    # Section 10's resolver counts are the SNAPSHOT's runs, each classified here from its own files by the
    # guard's own classifier. (b) below holds the snapshot's recorded classification to the same reading.
    queue_dir, telemetry_dir = QUEUE_DIR, TELEMETRY_DIR
    tmp_evidence = None
    if MUTATION == "snapshot-evidence":
        # A pinned run's files now say otherwise: in a TEMPORARY copy, the first pinned run's telemetry
        # records the resolver among its tools and a Resolved call. Nothing tracked is written.
        tmp_evidence = Path(tempfile.mkdtemp(prefix="fc08_snapshot_evidence_"))
        queue_dir, telemetry_dir = tmp_evidence / "proposals", tmp_evidence / "telemetry"
        shutil.copytree(QUEUE_DIR, queue_dir)
        shutil.copytree(TELEMETRY_DIR, telemetry_dir)
        first = snapshot["extraction_runs"][0]["run_id"]
        (telemetry_dir / ("%s.jsonl" % first)).write_text("\n".join(json.dumps(ev) for ev in [
            {"stage": "RUN_STARTED", "payload": {"run_id": first, "tools": ["mcp__knowledge_centre" + RESOLVER_SUFFIX]}},
            {"stage": "FC08_TOOL_CALL", "payload": {"run_id": first, "tool": "mcp__knowledge_centre" + RESOLVER_SUFFIX,
                                                    "outcome": '{"result":"Resolved: X -> ACT-1 X"}'}}]) + "\n",
            encoding="utf-8")
    try:
        pinned_runs = [r["run_id"] for r in snapshot["extraction_runs"]]
        own = {r: _own_classify(r, queue_dir, telemetry_dir) for r in pinned_runs}
        counts = _own_counts_of(list(own.values()))
        live = _own_resolver_counts(queue_dir, telemetry_dir)
        live_runs = sorted(q.stem for q in queue_dir.glob("*.jsonl") if "-extractor-" in q.stem)
        built_live = bw._resolver_runs(queue_dir, telemetry_dir)
    finally:
        if tmp_evidence is not None:
            shutil.rmtree(tmp_evidence, ignore_errors=True)
    # The frozen pre-week-5 queue, read here line by line -- not through the builder's _legacy_queue.
    legacy = [json.loads(line) for line in LEGACY_QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]
    legacy_days = sorted(r["proposed_at"][:10] for r in legacy)
    out.append((bool(legacy) and not any("run_id" in r for r in legacy)
                and "Nothing enters the corpus without a person." in lim and "every one was added by a person" in lim
                and "legacy queue without run ids" in lim,
                "#limits' first heading is 'Nothing enters the corpus without a person.', and its legacy queue truly "
                "has no run ids", "%d legacy proposals, %d with a run id" % (len(legacy),
                                                                        sum(1 for r in legacy if "run_id" in r))))
    # Read through feeds.ledger.load(), never the raw ledger path: evals/check_feeds_ledger.py's writer
    # scan allows only that module (and itself) to name the ledger file, and this guard is neither.
    ledger_entries = list(feeds_ledger.load().values())
    if MUTATION == "snapshot-undercount":
        # In memory only: the ledger holds one more accept, decided ON taken_on, than the snapshot counts.
        ledger_entries.append({"source": "ofsi", "item_id": "undercount", "decision": "accept",
                               "first_seen_run": "mutation", "decided_on": snapshot["taken_on"]})
    feed_accepted = sum(1 for e in ledger_entries if e["decision"] == "accept")
    accepted_by = _accepts_by(ledger_entries, snapshot["taken_on"])

    # (b) The snapshot still agrees with the evidence it names. Evidence is immutable, so this holds
    # however much new data arrives after the snapshot was taken.
    wrong_runs = sorted("%s: snapshot %s, files %s" % (r["run_id"], {k: r[k] for k in ("had_resolver", "resolved")},
                                                       own[r["run_id"]])
                        for r in snapshot["extraction_runs"]
                        if not own[r["run_id"]]["queue"] or own[r["run_id"]]["had_resolver"] != r["had_resolver"]
                        or own[r["run_id"]]["resolved"] != r["resolved"])
    out.append((bool(snapshot["extraction_runs"]) and not wrong_runs,
                "(b) every extraction run the snapshot pins still has its queue file, and its own telemetry classifies "
                "it as the snapshot says (had_resolver, resolved)", "; ".join(wrong_runs) or
                "%d pinned runs agree with their files" % len(snapshot["extraction_runs"])))
    # --repin classifies through the builder's _resolver_runs: over the pinned runs it must agree too.
    by_builder = {r: (None if r in built_live["no_record"] else r in built_live["with_tool"], r in built_live["resolved"])
                  for r in built_live["runs"]}
    disagree = sorted(r["run_id"] for r in snapshot["extraction_runs"]
                      if by_builder.get(r["run_id"]) != (r["had_resolver"], r["resolved"]))
    out.append((not disagree, "(b) the builder's _resolver_runs, which --repin uses, classifies every pinned run as the "
                "snapshot does", "disagree: %s" % (disagree or "none")))
    missing_adv = sorted(set(snapshot["advisories"]) - set(listed))
    out.append((bool(snapshot["advisories"]) and not missing_adv and snapshot["advisories"] == sorted(set(snapshot["advisories"]))
                and bw.ADVISORY in snapshot["advisories"],
                "(b) every advisory the snapshot pins is still in the advisory list, sorted once each, %s among them"
                % bw.ADVISORY, "missing: %s" % (missing_adv or "none")))
    out.append((snapshot["feed_accepted"] == accepted_by,
                "(b) the snapshot's accepted feed items EQUAL the ledger's accepts decided on or before its taken_on",
                "snapshot %r; ledger accepts by %s: %d (all accepts: %d)" % (snapshot["feed_accepted"],
                                                                          snapshot["taken_on"], accepted_by,
                                                                          feed_accepted)))
    out.append((SNAPSHOT.read_text(encoding="utf-8")
                == json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                and sorted(snapshot) == ["advisories", "extraction_runs", "feed_accepted", "taken_on"]
                and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot["taken_on"]))
                and [r["run_id"] for r in snapshot["extraction_runs"]]
                == sorted({r["run_id"] for r in snapshot["extraction_runs"]}),
                "the snapshot file is canonical JSON (sorted keys, indent 2, trailing newline) with exactly its four "
                "fields, a YYYY-MM-DD taken_on and its runs sorted once each", "taken_on %r" % snapshot.get("taken_on")))

    # (c) Live data moving past the snapshot is INFORMATION, not a failure: the page stays the snapshot's
    # until the owner re-pins, rebuilds and republishes.
    new_runs = sorted(set(live_runs) - set(pinned_runs))
    new_adv = sorted(set(listed) - set(snapshot["advisories"]))
    new_acc = feed_accepted - snapshot["feed_accepted"]
    moved = bool(new_runs or new_adv or new_acc)
    out.append((INFO, ("live: %s, %s, %s since the snapshot of %s; re-pin with --repin when you choose to republish"
                       % (_n(len(new_runs), "new extraction run"), _n(new_acc, "accepted item"),
                          _n(len(new_adv), "new advisory", "new advisories"), snapshot["taken_on"])) if moved
                else "live data has not moved past the snapshot of %s" % snapshot["taken_on"],
                "live %s (%s), %s, %s; snapshot %d, %d, %d"
                % (_n(live["runs"], "extraction run"), ", ".join(new_runs) or "none new",
                   _n(feed_accepted, "accepted item"), _n(len(listed), "advisory", "advisories"), len(pinned_runs),
                   snapshot["feed_accepted"], len(snapshot["advisories"]))))

    want_lim = {"attested": str(len(attested)),
                "attested-here": str(sum(1 for a in attested if a["advisory_id"] == bw.ADVISORY)),
                "label-decided": str(len(label_pass)),
                "label-advisories": str(len({d["advisory_id"] for d in label_pass})),
                "entity-keys": str(len(register) - empty), "register": str(len(register)),
                "emergent-approved": str(emergent_ok),
                "advisories": str(len(snapshot["advisories"])),
                "emergent-undecided": str(len(undecided_emergent)),
                "feed-accepted": str(snapshot["feed_accepted"]),
                "legacy-proposals": str(len(legacy)),
                "extraction-runs": str(counts["runs"]), "runs-with-resolver": str(counts["with_tool"]),
                "runs-no-tool-record": str(counts["no_record"]), "runs-resolved": str(counts["resolved"])}
    got_lim = _attrs(lim, "data-count")
    out.append((got_lim == want_lim, "(a) every count in #limits equals the guard's own count: the resolver counts "
                "classified from the pinned runs' own files, the corpus and accepted items from the snapshot",
                "want %s; page %s" % (want_lim, got_lim)))
    out.append((bool(attested) and all(a.get("attested_by") == "owner" for a in attested)
                and "each attested by the owner" in lim,
                "every attested citation was attested by the owner, as #limits says",
                "attested_by values: %s" % sorted({a.get("attested_by") for a in attested})))
    flag = _attrs(lim, "data-flag").get("prompt-names-resolver")
    names = "resolve_actor" in SYSTEM_PROMPT
    # The only dates #limits may carry are the snapshot's taken_on -- once in the corpus clause and once in
    # the resolver clause, since both describe the snapshot -- and the legacy queue's two, each equal to the
    # guard's own reading. Any other data-date -- the old typed "resolver-added" / "newest-proposal" among
    # them -- fails. Read as a LIST, so a duplicated or missing span cannot hide in a dict.
    dates = [(html.unescape(m.group(1)), html.unescape(m.group(2)))
             for m in re.finditer(r'<[a-z]+[^>]*? data-date="([^"]*)"[^>]*>([^<]*)<', lim)]
    want_dates = [("snapshot", snapshot["taken_on"]), ("snapshot", snapshot["taken_on"])]
    want_dates += [("legacy-first", legacy_days[0]), ("legacy-last", legacy_days[-1])] if legacy_days else []
    out.append((flag == ("name" if names else "do not name") and dates == want_dates
                and "At the snapshot of" in lim and "by that date" in lim,
                "#limits says truly whether the extractor's prompt names resolve_actor, and carries no typed date: "
                "its dates are the snapshot's taken_on, in the corpus and resolver clauses, and the legacy queue's "
                "first and last, computed",
                "prompt names it: %s; page %r; dates want %s, page %s" % (names, flag, want_dates, dates)))
    return out


def _n(n: int, word: str, many: str = "") -> str:
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


def checks() -> list:
    out = []
    try:
        bw = _load_builder()
    except (FileNotFoundError, ImportError, AttributeError) as exc:
        return [(False, "the builder exists and imports", "%s: %s" % (type(exc).__name__, exc))]

    r = _cli("--check")
    out.append((r.returncode == 0, "build_walkthrough --check passes (the committed page is a fresh build)",
                (r.stdout + r.stderr).strip()[-200:]))

    # A malformed snapshot is a LABELLED failure: every later check reads it.
    try:
        snapshot = _read_snapshot()
        problems = _snapshot_problems(snapshot)
    except (OSError, json.JSONDecodeError) as exc:
        problems = ["%s: %s" % (type(exc).__name__, exc)]
    out.append((not problems, "the committed snapshot %s exists, parses and is well-formed" % SNAPSHOT.name,
                "; ".join(problems) or "four fields, all well-typed"))
    if problems:
        return out
    try:
        page = bw.build(bw.inputs())
    except ValueError as exc:
        out.append((False, "the builder builds from the committed inputs", "ValueError: %s" % exc))
        return out
    again = bw.build(bw.inputs())
    out.append((page == again, "two consecutive builds are byte-identical", "%d bytes" % len(page.encode("utf-8"))))

    bad_seeds = []
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        s = _cli("--stdout", env=env)
        if s.returncode != 0 or s.stdout != page:
            bad_seeds.append("%s (exit %d, %d bytes)" % (seed, s.returncode, len(s.stdout)))
    out.append((not bad_seeds, "a subprocess build under PYTHONHASHSEED %s is byte-identical" % ", ".join(SEEDS),
                ", ".join(bad_seeds) or "all identical"))

    counts = {sid: len(re.findall(r'<section id="%s"' % sid, page)) for sid in SECTIONS}
    out.append((all(n == 1 for n in counts.values()), "each of the %d section ids appears exactly once" % len(SECTIONS),
                str(counts)))

    found = pb.violations(page)
    out.append((found == [], "the publish boundary finds nothing on the page", str(found)))

    record = json.loads((RECORDS_DIR / ("%s.json" % bw.ADVISORY)).read_text(encoding="utf-8"))
    extraction = section(page, "extraction")
    ids = [t.get("typology_id") or t["label"] for t in record["typologies"]]
    missing_ids = [i for i in ids if html.escape(i) not in extraction]
    out.append((bool(ids) and not missing_ids,
                "every typology in the record (id, or label when emergent) appears in #extraction",
                "%d typologies; missing: %s" % (len(ids), missing_ids)))

    quotes = [(t.get("typology_id") or t["label"], c["page"], c["quote"])
              for t in record["typologies"] for c in t["citations"]]
    missing_q = ["%s p%d %r" % (tid, pg, q[:40]) for tid, pg, q in quotes
                 if '<span class="pg">p%d</span><blockquote>%s</blockquote>' % (pg, html.escape(q)) not in extraction]
    out.append((bool(quotes) and not missing_q,
                "every citation is in #extraction as its page and its verbatim quote (escaped), together",
                "%d citations; missing: %s" % (len(quotes), missing_q)))

    pinned = _pinned_advisory_decisions(bw.ADVISORY)
    review = section(page, "review")
    shown = len(re.findall(r'<li class="decision"', review))
    out.append((bool(pinned) and shown == len(pinned),
                "#review shows one decision line per %s decision in the pinned log prefix" % bw.ADVISORY,
                "pinned: %d, shown: %d" % (len(pinned), shown)))
    absent = sorted({d.typology_id or d.emergent_label for d in pinned}
                    - {d.typology_id or d.emergent_label for d in pinned
                       if html.escape(d.typology_id or d.emergent_label) in review})
    out.append((bool(pinned) and not absent, "every decided link's typology appears in #review",
                "missing: %s" % absent))

    # Section 1 says, per desk, what that desk's digest carries. Hold every line against the
    # committed batch's desk files -- the digest the desks actually received.
    batch = (DIGESTS_DIR / "CURRENT").read_text(encoding="utf-8").strip()
    titles = load_routing()["desk_titles"]
    delivered = {}
    for f in sorted((DIGESTS_DIR / batch).glob("*.md")):
        block = _desk_block(f.read_text(encoding="utf-8"), bw.ADVISORY)
        if block is not None:
            delivered[titles[f.stem]] = block
    question = section(page, "question")
    said = {}
    for m in re.finditer(r'<li class="desk">(.+?): (\d+) approved(?: \(([^)]*)\))?; '
                         r'(\d+) awaiting review(?: \(([^)]*)\))?</li>', question):
        app = [x.strip() for x in (m.group(3) or "").split(",") if x.strip()]
        wait = [x.strip() for x in (m.group(5) or "").split(",") if x.strip()]
        ok_n = int(m.group(2)) == len(app) and int(m.group(4)) == len(wait)
        said[html.unescape(m.group(1))] = (sorted(html.unescape(x) for x in app),
                                           sorted(html.unescape(x) for x in wait), ok_n)
    wrong = sorted(t for t in set(delivered) | set(said)
                   if t not in said or t not in delivered or said[t][:2] != delivered[t] or not said[t][2])
    out.append((bool(delivered) and not wrong,
                "#question's per-desk approved/awaiting ids equal each batch %s desk file's %s block"
                % (batch, bw.ADVISORY),
                "files: %s; page: %s; wrong: %s" % (delivered, {k: v[:2] for k, v in said.items()}, wrong)))

    # Section 1's counts, recomputed here from the files -- not read back from the builder.
    proposals, _ = load_queue_files([QUEUE_DIR / ("%s.jsonl" % bw.DECIDED_RUN)])
    standing = gd.latest(pinned)
    n_ext = sum(1 for t in record["typologies"] if t.get("added_by") in (None, "extractor"))
    want = {"typologies": len(record["typologies"]), "extractor": n_ext,
            "reviewer": len(record["typologies"]) - n_ext,
            "emergent": sum(1 for t in record["typologies"] if not t.get("typology_id")),
            "proposals": len(proposals),
            "approved": sum(1 for d in standing.values() if d.decision == "approve"),
            "rejected": sum(1 for d in standing.values() if d.decision == "reject"),
            "desks": len(delivered), "desk-total": len(titles)}
    got = {m.group(1): int(m.group(2)) for m in re.finditer(r'data-count="([a-z-]+)">(\d+)<', question)}
    out.append((got == want, "every count in #question equals the guard's own count from the files",
                "want %s; page %s" % (want, got)))

    # Two extractions: the record's typologies and the decided run's proposals are separate runs.
    ext = {t["typology_id"] for t in record["typologies"]
           if t.get("typology_id") and t.get("added_by") in (None, "extractor")}
    rev = {t["typology_id"] for t in record["typologies"] if t.get("typology_id") and t.get("added_by") == "reviewer"}
    run = {p.typology_id for p in proposals if p.typology_id}
    sets = {"both": run & ext, "record-only": ext - run, "run-only": run - ext - rev, "run-reviewer": run & rev}
    shown_sets = {m.group(1): {x.strip() for x in m.group(2).split(",") if x.strip() and x.strip() != "none"}
                  for m in re.finditer(r'<span class="ids" data-set="([a-z-]+)">([^<]*)</span>', extraction)}
    out.append((bool(run) and shown_sets == {k: v for k, v in sets.items()},
                "#extraction's two-extractions paragraph names exactly the computed set differences",
                "want %s; page %s" % ({k: sorted(v) for k, v in sets.items()},
                                      {k: sorted(v) for k, v in shown_sets.items()})))

    # Each decision sits under the card of the link it decides, verdict and note together.
    articles = re.findall(r'<article class="link">(.*?)</article>', review, re.S)
    misplaced = []
    for d in pinned:
        name = d.typology_id or d.emergent_label
        unit = '<b class="%s">%s</b> <span class="note">%s</span>' % (
            html.escape(d.decision), html.escape(d.decision.upper()), html.escape(d.note or "(no note)"))
        home = [a for a in articles if ("PROPOSED LINK  %s " % name) in a
                or ("PROPOSED EMERGENT TYPOLOGY  %s" % html.escape(repr(name))) in a]
        if len(home) != 1 or unit not in home[0]:
            misplaced.append("%s (%d cards name it)" % (name, len(home)))
    out.append((bool(pinned) and not misplaced,
                "every pinned decision's verdict and note sit in the card naming its typology",
                "misplaced: %s" % misplaced))

    out += checks_sections_6_to_10(bw, page, record, pinned, snapshot)
    out += _plant_checks(bw, page, snapshot)
    out += _resolver_counts_fixture_checks(bw)
    out += _snapshot_self_checks(bw)

    for sid in ("grounding", "review"):
        out.append((bw.DECIDED_RUN in section(page, sid), "#%s names the decided run %s" % (sid, bw.DECIDED_RUN),
                    ""))

    # A decision appended AFTER the pinned prefix must not reach the page: the page is a
    # snapshot of what the batch saw. Temp copy only -- the real log is never written.
    work = Path(tempfile.mkdtemp(prefix="fc08_walkthrough_"))
    try:
        log = work / "log.jsonl"
        shutil.copy(gd.LOG, log)
        extra = replace(pinned[-1], decided_at="2099-01-01T00:00:00+00:00", decision="reject",
                        note="synthetic decision appended by check_walkthrough after the pinned prefix")
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(extra.to_line() + "\n")
        t = _cli("--stdout", "--log", str(log))
        out.append((t.returncode == 0 and t.stdout == page,
                    "a decision appended after the pinned prefix leaves the page unchanged",
                    "exit %d, %s" % (t.returncode, "identical" if t.stdout == page else "the page CHANGED")))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the public walkthrough page")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule; checks MUST fail")
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        if ok is NOT_RUN:
            print("  NOT RUN: %s\n         %s" % (label, detail))
            continue
        if ok == INFO:
            print("  INFO %s\n         %s" % (label, detail))
            continue
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
