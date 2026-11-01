"""
Pin tools/intake_document.py (spec 2026-10-31 §2): a document the owner downloaded becomes one run in the Friday
run's shape, and nothing is fetched.

Usage:
    python evals/check_intake.py
    python evals/check_intake.py --mutate owner-as-agent             # the selection is recorded as the agent's
    python evals/check_intake.py --mutate no-pdf-check               # a file that is not a PDF is taken in
    python evals/check_intake.py --mutate any-url-host               # a provenance URL on any host is accepted
    python evals/check_intake.py --mutate ledger-unchecked           # a document already in the ledger is taken in again
    python evals/check_intake.py --mutate quote-unchecked            # a quote on no page reaches the run
    python evals/check_intake.py --mutate manual-needs-orchestrator  # reconcile calls a manual run FAILED
    python evals/check_intake.py --mutate manual-forced              # reconcile treats every run as manual
    python evals/check_intake.py --mutate never-listed-forced        # a run listing no source is not told so
    python evals/check_intake.py --mutate no-telemetry-check         # a run with no orchestrator is not flagged
    python evals/check_intake.py --mutate orchestrator-none-ok       # no orchestrator no longer means FAILED
    python evals/check_intake.py --mutate manual-ended-ignored       # a manual run is not "ended" (no outcome check)
    python evals/check_intake.py --mutate owner-tier-always          # every accepted item is tiered owner intake
    python evals/check_intake.py --mutate by-unchecked               # decide(by=) takes any value
    python evals/check_intake.py --mutate quote-bounds-unchecked     # a too-short quote is found after the write
    python evals/check_intake.py --mutate reason-bound-unchecked     # an over-long reason is found after the write
    python evals/check_intake.py --mutate date-unchecked             # 2026-02-30 is a date
    python evals/check_intake.py --mutate crash-uncaught             # an extractor that raises leaves no crash record
    python evals/check_intake.py --mutate interrupt-uncaught         # a Ctrl-C during extraction leaves a blocking run
    python evals/check_intake.py --mutate pending-label-dropped      # --pending calls a manual run "pending"
    python evals/check_intake.py --mutate back-pressure-unlabelled   # the Friday refusal does not say a run is manual
    python evals/check_intake.py --mutate manual-defer-allowed       # accept_run defers a manual item (it is lost)
    python evals/check_intake.py --mutate manual-default-defer       # a failed manual item defaults to defer
    python evals/check_intake.py --mutate report-ten-not-listed      # a manual report shows ten "not listed" rows
    python evals/check_intake.py --mutate failed-manual-blocks       # a manual run whose extraction failed blocks Friday
    python evals/check_intake.py --mutate extracted-manual-unblocked # a manual run with an extracted item is not pending
    python evals/check_intake.py --mutate live-manual-host-overlap   # a manual host may also be a live source's

WHAT IT HOLDS, in a temporary inbox with a stub extractor (cold; feeds.http.get is replaced by one that raises):
  shape      the run is marked manual; its one item's document carries exactly a live item's keys plus
             delivered_by; the selection is a triage line by the owner, reason "owner-selected: ...", its quote
             found on a page; reconcile_run calls the run COMPLETE; report.md is written;
  refusals   each refused BEFORE anything is written: a file that is not a PDF; a URL over http; a URL on
             another host; a live source; a quote on no page; a document already in the ledger;
  overlap    feeds.sources refuses at import a source declared both live and manual, and a manual host that is
             also a live source's host or document host;
  blocking   an unaccepted manual run is listed "manual" by accept_run --pending and named so in the Friday
             refusal; accept_run refuses to defer its item and defaults an unextracted one to drop; its
             report.md shows its own source row, not ten "not listed" rows.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "tools"))

from check_document_pages import tiny_pdf  # noqa: E402
from feeds import extraction, http as feeds_http, inbox, ledger, reconcile, runs  # noqa: E402
from feeds import triage as feeds_triage  # noqa: E402

INTAKE = ROOT / "tools" / "intake_document.py"
RECONCILE = ROOT / "feeds" / "reconcile.py"
SOURCES_PY = ROOT / "feeds" / "sources.py"
TRIAGE = ROOT / "feeds" / "triage.py"
ACCEPT = ROOT / "tools" / "accept_run.py"
PREFLIGHT = ROOT / "feeds" / "preflight.py"
RUNS = ROOT / "feeds" / "runs.py"
REPORT = ROOT / "feeds" / "report.py"
LIVE_RUN = ROOT / "data" / "feeds" / "runs" / "feeds-2026-10-30-b2a3cf" / "items.json"  # tracked
SENTENCE = "Professional money launderers use trade-based schemes and shell companies to move proceeds."
URL = "https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Professional-Money-Laundering.pdf"
ITEM_ID = "/content/dam/fatf-gafi/reports/Professional-Money-Laundering.pdf"
MUTATIONS = {
    "failed-manual-blocks": (RUNS, 'if state.get("manual") and failed_extracting_nothing(folder):', "if False:"),
    "extracted-manual-unblocked": (RUNS, 'if state.get("manual") and failed_extracting_nothing(folder):',
                                   'if state.get("manual"):'),
    "pending-label-dropped": (ACCEPT, 'label == runs.PENDING and runs.is_manual(r, inbox_root)', "False"),
    "back-pressure-unlabelled": (PREFLIGHT, 'MANUAL_NOTE if runs.is_manual(r, root) else ""', '""'),
    "manual-defer-allowed": (ACCEPT, "    if manual_defers:", "    if False:"),
    "manual-default-defer": (ACCEPT, "    if manual:  # nothing re-lists", "    if False:  # nothing re-lists"),
    "report-ten-not-listed": (REPORT, 'if inbox.load(run_id, root).get("manual") else reconcile.SOURCES',
                              "if False else reconcile.SOURCES"),
    "live-manual-host-overlap": (SOURCES_PY, "\nif _overlap:", "\nif False:"),
    "owner-as-agent": (INTAKE, 'by="owner"', 'by="agent"'),
    "no-pdf-check": (INTAKE, 'if not body.startswith(b"%PDF-"):', "if False:"),
    "any-url-host": (INTAKE, "_check_host(args.url, src.hosts)",
                     "_check_host(args.url, frozenset({urlsplit(args.url).netloc}))"),
    "ledger-unchecked": (INTAKE, "if (item.source, item.item_id) in seen:", "if False:"),
    "quote-unchecked": (INTAKE, "if not found_on:", "if False:"),
    "manual-needs-orchestrator": (RECONCILE, "elif (orchestrator is None and not manual)", "elif (orchestrator is None)"),
    "manual-forced": (RECONCILE, 'manual = bool(state.get("manual"))', "manual = True"),
    "never-listed-forced": (RECONCILE, 'never_listed = [] if manual else [s for s in SOURCES if s not in state["sources"]]',
                            "never_listed = []"),
    "no-telemetry-check": (RECONCILE, 'problems.append("the orchestrator session left no telemetry")', "pass"),
    "orchestrator-none-ok": (RECONCILE, "elif (orchestrator is None and not manual) or (orchestrator is not None and ",
                             "elif (orchestrator is not None and "),
    "manual-ended-ignored": (RECONCILE, "ended = manual or (orchestrator", "ended = (orchestrator"),
    "owner-tier-always": (ACCEPT, 'if verdict.get("by") == "owner":', "if True:"),
    "by-unchecked": (TRIAGE, 'if by not in ("agent", "owner"):', "if False:"),
    "quote-bounds-unchecked": (INTAKE, "if not QUOTE_MIN <= len(quote) <= QUOTE_MAX:", "if False:"),
    "reason-bound-unchecked": (INTAKE, "if len(reason) > feeds_triage.REASON_MAX:", "if False:"),
    "date-unchecked": (INTAKE, "date.fromisoformat(args.published)", "None"),
    "crash-uncaught": (INTAKE, "    except Exception as exc:  # the Friday run's crash path",
                       "    except ZeroDivisionError as exc:  # the Friday run's crash path"),
    "interrupt-uncaught": (INTAKE, "    except (KeyboardInterrupt, asyncio.CancelledError) as exc:  # Ctrl-C",
                           "    except (ZeroDivisionError,) as exc:  # Ctrl-C"),
}


def load(name: str, path: Path, mutation) -> types.ModuleType:
    source = path.read_text(encoding="utf-8")
    if mutation in MUTATIONS and MUTATIONS[mutation][0] == path:
        old, new = MUTATIONS[mutation][1:]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
        source = source.replace(old, new)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    package, _, leaf = name.rpartition(".")
    if package:
        setattr(importlib.import_module(package), leaf, module)
    return module


def stub_extractor(run, request, advisory_id, root):
    """Writes the two fields reconcile_run checks, as an extraction would; spends nothing."""
    rel = "%s/%s.json" % (inbox.RECORDS, advisory_id)
    inbox.write_file(run.run_id, rel, json.dumps({"advisory_id": advisory_id, "source": {
        "document_sha256": request["document"]["sha256"]}}).encode("utf-8"), root)

    async def done():
        return {"key": request["key"], "advisory_id": advisory_id, "extraction_run_id": None, "status": "extracted",
                "record": rel, "error": None, "cost_usd": 0.0}
    return done()


def argv(pdf: Path, **over) -> list:
    a = {"--source": "fatf", "--file": str(pdf), "--url": URL, "--title": "Professional Money Laundering",
         "--published": "2018-07-26", "--reason": "sets out professional laundering methods", "--quote": SENTENCE}
    a.update(over)
    return [x for k, v in a.items() for x in (k, v)]


def runs_in(root: Path) -> list:
    return sorted(p.name for p in root.glob("feeds-*") if p.is_dir()) if root.exists() else []


def world(t: Path, ledger_items: list):
    root, seen, alist = t / "inbox", t / "ledger.json", t / "feed_advisory_list.json"
    seen.write_text(ledger.dump(ledger_items), encoding="utf-8")
    pdf = t / "fatf.pdf"
    pdf.write_bytes(tiny_pdf([SENTENCE]))
    bad = t / "not.pdf"
    bad.write_bytes(b"<html>challenge</html>\n" + tiny_pdf([SENTENCE]))  # a bot-check page ahead of real PDF bytes
    return root, seen, alist, pdf, bad


def checks(mutation) -> list:
    runs_mod = load("feeds.runs", RUNS, mutation)  # first, so every importer below binds the (possibly mutated) one
    tri_mod = load("feeds.triage", TRIAGE, mutation)
    rec_mod = load("feeds.reconcile", RECONCILE, mutation)
    acc_mod = load("accept_run", ACCEPT, mutation)
    pre_mod = load("feeds.preflight", PREFLIGHT, mutation)
    load("feeds.report", REPORT, mutation)  # before the intake imports it
    intake = load("intake_document", INTAKE, mutation)
    intake.reconcile = rec_mod  # the intake reads the (possibly mutated) reconcile, as the guard does
    feeds_http.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the intake fetched something"))
    live_keys = set(json.loads(LIVE_RUN.read_text(encoding="utf-8"))["sources"]["ofac"]["items"][0]["document"])
    out = []
    with tempfile.TemporaryDirectory() as t:
        root, seen, alist, pdf, _ = world(Path(t), [])
        code = intake.main(argv(pdf), root=root, seen_path=seen, advisory_lists=[alist], extractor=stub_extractor)
        names = runs_in(root)
        out.append((code == 0 and len(names) == 1, "a good intake writes one run and exits 0", (code, names)))
        if len(names) == 1:
            run = names[0]
            state = inbox.load(run, root)
            item = inbox.items(state)[0]
            out.append(((state.get("manual") or {}).get("by") == "owner", "the run is marked manual, by the owner",
                        state.get("manual")))
            out.append((set(item["document"]) == live_keys | {"delivered_by"},
                        "its document carries a live item's keys plus delivered_by",
                        sorted(set(item["document"]) ^ (live_keys | {"delivered_by"}))))
            verdict = feeds_triage.load(run, root).get(item["key"], {})
            out.append((verdict.get("by") == "owner" and verdict.get("reason", "").startswith("owner-selected: ")
                        and bool(verdict.get("found_on")),
                        "the selection is a triage line by the owner, its quote found",
                        {k: verdict.get(k) for k in ("by", "reason", "found_on")}))
            rec = rec_mod.reconcile_run(run, root)
            out.append((rec["status"] == rec_mod.COMPLETE, "reconcile_run calls the manual run COMPLETE",
                        (rec["status"], rec["problems"][:2])))
            out.append(((inbox.run_dir(run, root) / "report.md").exists(), "report.md is written", run))
            ok, msg = tri_mod.decide(run, item["key"], "relevant", "r", SENTENCE, root, by="bogus")
            out.append((not ok and "agent or owner" in msg, "decide() refuses a by that is neither agent nor owner", msg))
            folder = inbox.run_dir(run, root)
            outcomes_file = folder / extraction.OUTCOMES
            kept = outcomes_file.read_bytes()
            out.append((runs_mod.classify(run, root) == runs_mod.PENDING and [r for r, _ in runs_mod.blocking(root)] == [run],
                        "a manual run with an extracted item is pending and blocks Friday",
                        (runs_mod.classify(run, root), runs_mod.blocking(root))))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                acc_mod.main(["--pending"], inbox_root=root)
            out.append((buf.getvalue().split() == [run, "manual"], "accept_run --pending lists the manual run as manual",
                        buf.getvalue()))
            msg = pre_mod.back_pressure(root) or ""
            out.append((run in msg and "MANUAL" in msg, "the Friday refusal names the run and says it is manual", msg))
            text = (folder / "report.md").read_text(encoding="utf-8")
            out.append(("| fatf | ok |" in text and "not listed" not in text,
                        "a manual run's report shows its own source row, not ten not-listed rows", text.count("not listed")))
            key = item["key"]
            try:
                acc_mod.plan(run, {key: "defer"}, inbox_root=root, seen_path=seen, data=Path(t) / "data",
                             advisory_list=alist, golden_list=alist)
                got = "planned"
            except ValueError as exc:
                got = str(exc)
            out.append(("cannot be deferred" in got, "accept_run refuses to defer a manual run's item", got[:120]))
            outcomes_file.unlink()
            out.append((acc_mod.default_decisions(run, root) == {key: "drop"},
                        "an unextracted manual item defaults to drop, never defer", acc_mod.default_decisions(run, root)))
            rec = rec_mod.reconcile_run(run, root)
            out.append((rec["status"] != rec_mod.COMPLETE and any("has no outcome" in p for p in rec["problems"]),
                        "a manual run whose extraction request has no outcome is not COMPLETE",
                        (rec["status"], rec["problems"][:2])))
            outcomes_file.write_bytes(kept)
            state.pop("manual")
            inbox.save(run, state, root)
            rec = rec_mod.reconcile_run(run, root)
            out.append((rec["status"] == rec_mod.FAILED and "the orchestrator session left no telemetry" in rec["problems"]
                        and bool(rec["never_listed_sources"]),
                        "the same run, not marked manual, is FAILED: no orchestrator, no telemetry, sources unlisted",
                        (rec["status"], rec["problems"][:2], rec["never_listed_sources"][:1])))
    def failing(run, request, advisory_id, root):
        async def done():
            return {"key": request["key"], "advisory_id": advisory_id, "extraction_run_id": None, "status": "failed",
                    "record": None, "error": "extraction refused", "cost_usd": 0.0}
        return done()

    with tempfile.TemporaryDirectory() as t:
        root, seen, alist, pdf, _ = world(Path(t), [])
        c1 = intake.main(argv(pdf), root=root, seen_path=seen, advisory_lists=[alist], extractor=failing)
        first = runs_in(root)
        ok = (len(first) == 1 and runs_mod.classify(first[0], root) == runs_mod.NOTHING
              and not runs_mod.blocking(root))
        out.append((ok, "a manual run whose extraction failed is nothing-to-decide and does not block Friday",
                    (c1, first, ok and runs_mod.classify(first[0], root))))
        c2 = intake.main(argv(pdf), root=root, seen_path=seen, advisory_lists=[alist], extractor=stub_extractor)
        out.append((c2 == 0 and len(runs_in(root)) == 2, "the same document can then be taken in again: a second run",
                    (c2, runs_in(root))))

    def exploding(run, request, advisory_id, root):
        raise ConnectionError("the extraction session dropped")

    with tempfile.TemporaryDirectory() as t:
        root, seen, alist, pdf, _ = world(Path(t), [])
        try:
            code = intake.main(argv(pdf), root=root, seen_path=seen, advisory_lists=[alist], extractor=exploding)
        except Exception as exc:  # noqa: BLE001 -- an uncaught crash is the defect this clause is about
            code = "raised %s" % type(exc).__name__
        names = runs_in(root)
        ok = code == 1 and len(names) == 1
        if ok:
            folder = inbox.run_dir(names[0], root)
            saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
            rec = rec_mod.reconcile_run(names[0], root)
            ok = (bool(saved.get("crash")) and (folder / "report.md").exists() and rec["status"] != rec_mod.COMPLETE
                  and runs.classify(names[0], root) == runs.NOTHING and not runs.blocking(root))
        out.append((ok, "an extractor that raises leaves a crash run: report written, not COMPLETE, not blocking Friday",
                    (code, names)))
    def interrupted(run, request, advisory_id, root):
        raise KeyboardInterrupt

    with tempfile.TemporaryDirectory() as t:
        root, seen, alist, pdf, _ = world(Path(t), [])
        try:
            intake.main(argv(pdf), root=root, seen_path=seen, advisory_lists=[alist], extractor=interrupted)
            code = "returned"
        except KeyboardInterrupt:
            code = "re-raised"
        names = runs_in(root)
        ok = code == "re-raised" and len(names) == 1
        if ok:
            folder = inbox.run_dir(names[0], root)
            ok = ((folder / "run.json").exists() and (folder / "report.md").exists()
                  and "KeyboardInterrupt" in (json.loads((folder / "run.json").read_text(encoding="utf-8"))
                                              .get("crash") or "")
                  and not runs.blocking(root))
        out.append((ok, "a Ctrl-C during extraction takes the crash path, then is re-raised: not blocking Friday",
                    (code, names)))
    live = ("live feed", "live feed run feeds-2026-10-30-b2a3cf, item ofac:0123456789abcdef: triaged relevant: why")
    got = (acc_mod._provenance({"reason": "why"}, "feeds-2026-10-30-b2a3cf", "ofac:0123456789abcdef"),
           acc_mod._provenance({"reason": "why", "by": "agent"}, "feeds-2026-10-30-b2a3cf", "ofac:0123456789abcdef"),
           acc_mod._provenance({"reason": "owner-selected: why", "by": "owner"}, "feeds-2026-10-31-aaaaaa", "fatf:0123456789abcdef"))
    out.append((got[0] == live and got[1] == live and got[2] == (
        "owner intake", "owner intake run feeds-2026-10-31-aaaaaa, item fatf:0123456789abcdef: owner-selected: why"),
        "accept_run: a live verdict keeps its exact live-feed tier and rationale; an owner verdict is an owner intake",
        got))
    refusals = {"a file that is not a PDF": ({"--file": "bad"}, []),
                "a file that does not exist": ({"--file": "missing"}, []),
                "a file that starts %PDF- and is not one": ({"--file": "corrupt"}, []),
                "a quote shorter than the contract's minimum": ({"--quote": SENTENCE[:9]}, []),
                "a reason over the limit once its prefix is added": ({"--reason": "x" * 290}, []),
                "a publication date that is not a day": ({"--published": "2026-02-30"}, []),
                "a URL over http": ({"--url": URL.replace("https://", "http://")}, []),
                "a URL on another host": ({"--url": "https://evil.example/report.pdf"}, []),
                "a live source": ({"--source": "wolfsberg"}, []),
                "a quote on no page": ({"--quote": "This sentence appears nowhere in the document at all."}, []),
                "a document already in the ledger": ({}, [{"source": "fatf", "item_id": ITEM_ID, "decision": "accept",
                                                           "first_seen_run": "feeds-2026-10-01-abcdef",
                                                           "decided_on": "2026-10-01"}])}
    for label, (over, ledger_items) in refusals.items():
        with tempfile.TemporaryDirectory() as t:
            root, seen, alist, pdf, bad = world(Path(t), ledger_items)
            if "--file" in over:
                corrupt = Path(t) / "corrupt.pdf"
                corrupt.write_bytes(b"%PDF-1.4\nthis is not a pdf body\n")
                over = dict(over, **{"--file": str({"bad": bad, "missing": Path(t) / "nope.pdf",
                                                    "corrupt": corrupt}[over["--file"]])})
            try:
                code = intake.main(argv(pdf, **over), root=root, seen_path=seen, advisory_lists=[alist],
                                   extractor=stub_extractor)
            except Exception as exc:  # noqa: BLE001 -- a crash is not a refusal
                code = "raised %s" % type(exc).__name__
            out.append((code == 2 and not runs_in(root), "refused, nothing written: %s" % label, (code, runs_in(root))))
    src = SOURCES_PY.read_text(encoding="utf-8").replace(
        'MANUAL_SOURCES = {"fatf"', 'MANUAL_SOURCES = {"fca": ManualSource("fca", frozenset()), "fatf"', 1)
    probe = types.ModuleType("overlap")
    sys.modules["overlap"] = probe  # dataclass resolves its class's module by name
    try:
        exec(compile(src, str(SOURCES_PY), "exec"), probe.__dict__)
        out.append((False, "a source declared live and manual is refused at import", "imported"))
    except RuntimeError as exc:
        out.append(("both live and manual" in str(exc), "a source declared live and manual is refused at import",
                    str(exc)[:120]))
    finally:
        sys.modules.pop("overlap", None)
    from feeds import sources as live
    host = sorted(live.SOURCES["fca"].hosts)[0]
    src = SOURCES_PY.read_text(encoding="utf-8").replace(
        'ManualSource("fatf", frozenset({"www.fatf-gafi.org"}))',
        'ManualSource("fatf", frozenset({"www.fatf-gafi.org", %r}))' % host, 1)
    source = src
    if mutation in MUTATIONS and MUTATIONS[mutation][0] == SOURCES_PY:
        old, new = MUTATIONS[mutation][1:]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, SOURCES_PY))
        source = source.replace(old, new)
    probe = types.ModuleType("overlap")
    sys.modules["overlap"] = probe
    try:
        exec(compile(source, str(SOURCES_PY), "exec"), probe.__dict__)
        out.append((False, "a manual host that is also a live source's host is refused at import", "imported"))
    except RuntimeError as exc:
        out.append(("nothing may fetch it" in str(exc), "a manual host that is also a live source's host is refused at import",
                    str(exc)[:120]))
    finally:
        sys.modules.pop("overlap", None)
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--mutate", choices=sorted(MUTATIONS))
    args = ap.parse_args(argv)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s" % ("HOLDS" if not failures else "FAILED: %d" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
