"""
Pin tools/accept_run.py end to end: the only way a live result enters tracked data (slice 2 C, spec section 2).

Usage:
    python evals/check_accept_run.py
    python evals/check_accept_run.py --mutate no-citation-check   # a record citing text not on its page is accepted
    python evals/check_accept_run.py --mutate no-gate-recheck     # a queue line the review gate would quarantine is accepted
    python evals/check_accept_run.py --mutate ledger-defers       # a deferred item is written to the ledger
    python evals/check_accept_run.py --mutate no-override-needed  # a RECONCILIATION_FAILED run is accepted without a reason
    python evals/check_accept_run.py --mutate overwrite-target    # an existing tracked file is overwritten
    python evals/check_accept_run.py --mutate no-rollback         # a failure mid-write leaves copies behind
    python evals/check_accept_run.py --mutate slice1-records      # an accepted record lands in data/records/
    python evals/check_accept_run.py --mutate rollback-leaves-dirs  # a rolled-back call leaves its folders, blocking a retry
    python evals/check_accept_run.py --mutate failed-default-drop   # a failed or budget-deferred item defaults to DROP
    python evals/check_accept_run.py --mutate gap-unrecorded        # an allocated id nothing used is not named
    python evals/check_accept_run.py --mutate expire-unlocked       # --expire moves a run while a Friday run holds the lock
    python evals/check_accept_run.py --mutate register-after-copy   # a copy is registered for rollback only once complete
    python evals/check_accept_run.py --mutate marker-bare           # a marker failure after the ledger reads as REFUSED
    python evals/check_accept_run.py --mutate direct-write          # feeds/runs.mark_accepted writes the marker directly
    python evals/check_accept_run.py --mutate accept-unlocked       # accepting proceeds while a Friday run holds the lock
    python evals/check_accept_run.py --mutate no-not-extracted-refusal  # accepting a never-extracted item crashes instead of refusing
    python evals/check_accept_run.py --mutate no-verdict-refusal     # accepting an extracted item with no triage verdict crashes

WHAT IT HOLDS:
  accept      an EXTRACTED item's document, record, queue and telemetry are copied byte for byte to
              data/advisories/<adv>-<source>.<ext>, data/feeds/records/, data/proposals/, data/telemetry/; the
              advisory list gains its entry (source, URL, sha256, date, the feed run) and its counts; the run's
              evidence is copied to data/feeds/runs/<run>/; the REVIEW GATE passes the copied queue against
              the new entry and document; the ledger holds the accepted and the dropped item and NOT the deferred;
              the run is marked accepted, and a second acceptance is refused; the gate refuses an advisory id
              that is in both the golden and the live-feed list rather than letting one shadow the other;
  refuse all  an accept of an item never extracted, a record citing text not on its page, a queue line the
              gate would quarantine, an existing target, or a RECONCILIATION_FAILED run without an override
              refuses the WHOLE run: no file, no ledger line, the advisory list byte-identical;
  override    with --override-reconciliation "<reason>" that run is accepted and the reason is recorded;
  rollback    a failure while writing removes every copy AND every folder this call made and restores the
              advisory list, so the same acceptance, retried, succeeds -- including a failure PART-WAY through a
              copy (each target is created exclusively and registered before its first byte);
  marker      if the inbox marker cannot be written after the ledger, accept_run says RECORDED, BUT NOT MARKED
              (exit 2), never REFUSED, and names the one copy that recovers it; that copy does;
  unfinished  an item whose extraction FAILED, or was DEFERRED FOR BUDGET, cannot be accepted; the interactive
              default for it is DEFER (never drop), and a deferred item is not in the ledger, so it returns
              next Friday (Task 4 carry-forward: never silently lost, never dropped by default);
  crash       in a run that crashed mid-extraction, the in-flight item holds an allocated advisory id but no
              record: it cannot be accepted (even with the override); deferred, its id is named in
              accepted.json as allocated-and-unused -- a recorded GAP, never reused (owner decision 11);
  expire      a pending run under 14 days refuses --expire; at 14 it moves to inbox/expired/ and the ledger is
              untouched; an eval-marked run is never pending; while a Friday run holds the inbox's lock
              (tools/friday_run.run_lock, the SAME lock), --expire is refused and moves nothing;
  lock        accepting (plan + apply, --dry-run included) takes the SAME lock and is refused while a Friday
              run holds it, writing nothing; released, the same acceptance succeeds;
  marker atomicity  feeds/runs.mark_accepted writes accepted.json atomically: a crash mid-write leaves no
              marker at all, never a truncated one classify() would misread as accepted, and the run still
              classifies as pending;
  no-verdict  an extracted item with no triage verdict refuses ("extracted but has no triage verdict"), never
              crashes;
  seed        --seed-catalogue records every catalogue item as a drop under "catalogue:<sha12>", once.

COLD. Temporary inbox, data folders, advisory list and ledger; the document is a hand-built PDF; the queue
and record are built to slice 1's contracts. No network, no model. The repository's git status is unchanged,
and so are the gitignored places a leak would hide from it (inbox/, data/advisories/).

NOT A VACUOUS PASS. Each --mutate rewrites tools/accept_run.py (or, for "direct-write", feeds/runs.py) in
memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import builtins
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from feeds import extraction, inbox, ledger, runs  # noqa: E402
from schemas.proposal_contract import SCHEMA, proposal_id  # noqa: E402
from check_friday_run import listed_run, load_all  # noqa: E402

ACCEPT = ROOT / "tools" / "accept_run.py"
RUNS = ROOT / "feeds" / "runs.py"
TODAY = date(2026, 10, 3)
QUOTE = "Advisory text on shell companies."
MUTATIONS = {
    "no-citation-check": ("    if bad:\n        problems.append(\"%s: %d citation(s)", "    if False:\n        problems.append(\"%s: %d citation(s)"),
    "no-gate-recheck": ("    for q in quarantined:\n", "    for q in []:\n"),
    "ledger-defers": ('               for k in sorted(listed) if decisions[k] != "defer"]\n', "               for k in sorted(listed)]\n"),
    "no-override-needed": ('    if rec["status"] not in reconcile.ACCEPTABLE and not override:\n', "    if False:\n"),
    "overwrite-target": ("        if path.exists():\n            problems.append(\"%s: %s already exists", "        if False:\n            problems.append(\"%s: %s already exists"),
    "no-rollback": ("            if path.exists():\n                path.unlink()\n", "            pass\n"),
    "slice1-records": ('            "record": data / "feeds" / "records" / ("%s.json" % adv),', '            "record": data / "records" / ("%s.json" % adv),'),
    "rollback-leaves-dirs": ("            if folder.exists() and not any(folder.iterdir()):\n                folder.rmdir()\n",
                             "            pass\n"),
    "failed-default-drop": ('    return "defer"  # failed, deferred for budget, relevant but never queued, or unfinished\n',
                            '    return "drop"\n'),
    "gap-unrecorded": ('"allocated_not_accepted": p["gaps"],', '"allocated_not_accepted": {},'),
    "expire-unlocked": ("            if not held:\n", "            if False:\n"),
    "register-after-copy": ("        created.append(dst)\n        fill(out)\n", "        fill(out)\n        created.append(dst)\n"),
    "marker-bare": ("    except Exception as exc:  # after the ledger: nothing to roll back",
                    "    except ZeroDivisionError as exc:  # after the ledger: nothing to roll back"),
    "accept-unlocked": (
        "        if not held:\n            print(\"REFUSED: a Friday run holds %s; accepting a run reads",
        "        if False:\n            print(\"REFUSED: a Friday run holds %s; accepting a run reads"),
    "no-not-extracted-refusal": (
        '    if not outcome or outcome.get("status") != "extracted":\n        return None, ["%s cannot be '
        'accepted: it was not extracted (%s)" % (key, (outcome or {}).get("status", "never queued"))]\n',
        "    pass\n"),
    "no-verdict-refusal": (
        '    if verdict is None:\n        return None, ["%s: extracted but has no triage verdict" % key]\n', ""),
}

# feeds/runs.py is mutated separately: mark_accepted's atomicity is tested directly, not through accept_run.
RUNS_MUTATIONS = {
    "direct-write": (
        '    body = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\\n"\n'
        '    tmp_path = path.with_name(".%s.tmp-%d" % (path.name, os.getpid()))\n'
        "    try:\n"
        '        with open(tmp_path, "w", encoding="utf-8") as f:\n'
        "            f.write(body)\n"
        "        os.link(tmp_path, path)\n"
        "    finally:\n"
        "        if tmp_path.exists():\n"
        "            tmp_path.unlink()\n",
        '    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\\n", '
        'encoding="utf-8")\n'),
}


def load_accept(mutation):
    source = ACCEPT.read_text(encoding="utf-8")
    if mutation and mutation in MUTATIONS:
        old, new = MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, ACCEPT))
        source = source.replace(old, new)
    module = types.ModuleType("accept_run_under_test")
    module.__file__ = str(ACCEPT)
    exec(compile(source, str(ACCEPT), "exec"), module.__dict__)
    return module


def load_runs(mutation):
    """feeds/runs.py, mutated when `mutation` names one of RUNS_MUTATIONS. Loaded fresh and separately from
    the real `runs` import above, so F1's atomicity check exercises mark_accepted/classify directly, and every
    other check here (which uses the real, always-correct `runs`) is unaffected by this mutation."""
    source = RUNS.read_text(encoding="utf-8")
    if mutation and mutation in RUNS_MUTATIONS:
        old, new = RUNS_MUTATIONS[mutation]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, RUNS))
        source = source.replace(old, new)
    module = types.ModuleType("runs_under_test")
    module.__file__ = str(RUNS)
    exec(compile(source, str(RUNS), "exec"), module.__dict__)
    return module


def valid_extractor(m, tamper=None):
    """A stub extraction leaving what slice 1's extract leaves, to its contracts: a VALID record citing the pinned
    PDF, a proposal queue the gate accepts, and completed, clean telemetry. `tamper`: "record" | "queue"."""

    async def extractor(run, req, advisory_id, root):
        from agents.run_identity import RunIdentity
        folder = inbox.run_dir(run.run_id, root)
        ident = RunIdentity.new("extractor", advisory_id, folder / req["document"]["path"], feeds_run=run.run_id,
                                inbox_root=root)
        tel = m["telemetry"]
        tel.run_started(ident, "stub", 1.0, 60, ())
        tel.run_completed(ident, tel.SUCCESS, "record validated", validated=True,
                          result=types.SimpleNamespace(num_turns=20, total_cost_usd=0.6, duration_ms=1, permission_denials=[]),
                          terminal_check={"calls": 0, "unterminated": [], "duplicated": []})
        cite = [{"page": 1, "quote": QUOTE if tamper != "record" else "Advisory text on front companies."}]
        record = {"schema_version": "1.4.0", "advisory_id": advisory_id,
                  "source": {"source_type": "fincen", "publisher": "FinCEN", "title": "A FinCEN advisory",
                             "published_on": "2026-10-01", "published_on_precision": "day", "url": req["document"]["url"],
                             "document_sha256": ident.pdf_sha256, "page_count": 1},
                  "summary": "A synthetic advisory about shell companies, built by the accept_run guard.",
                  "jurisdictions": ["US"], "actors": [], "indicators": [], "suggested_desks": ["trade_desk"],
                  "overall_confidence": "low", "extraction_notes": None,
                  "typologies": [{"family": "sanctions", "typology_id": "SAN001", "label": "Sanctions evasion", "emergent": False,
                                  "confidence": "low", "citations": cite}]}
        rel = "records/%s.json" % advisory_id
        inbox.write_file(run.run_id, rel, json.dumps(record, indent=2).encode("utf-8"), root)
        body = {"schema": SCHEMA, "run_id": ident.run_id, "stage": "extractor", "advisory_id": advisory_id,
                "document_sha256": ident.pdf_sha256, "typology_id": "SAN001", "emergent_label": None,
                "rationale": "Page 1 describes shell companies.", "confidence": "low",
                "citations": [{"page": 1, "quote": QUOTE if tamper != "queue" else "Text this document never held."}]}
        ident.queue_path.parent.mkdir(parents=True, exist_ok=True)
        ident.queue_path.write_text(json.dumps(dict(body, proposal_id=proposal_id(body),
                                                    proposed_at="2026-10-02T09:00:00+00:00")) + "\n", encoding="utf-8")
        return {"key": req["key"], "advisory_id": advisory_id, "extraction_run_id": ident.run_id, "status": "extracted",
                "record": rel, "error": None, "cost_usd": 0.6}
    return extractor


def crashing_extractor(m, crash_at: int):
    """valid_extractor, except that call number `crash_at` raises AFTER its id was allocated: the run crashes
    with that item in flight (tools/friday_run.record_crash gives it a FAILED outcome naming the id it held)."""
    ok, calls = valid_extractor(m), []

    async def extractor(run, req, advisory_id, root):
        calls.append(req["key"])
        if len(calls) == crash_at:
            raise RuntimeError("the machine slept mid-extraction (planted)")
        return await ok(run, req, advisory_id, root)
    return extractor


def read_json(path: Path) -> dict:
    """A file the check expects, or {}: a missing file is a FAIL below, never a crash of the guard."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                          capture_output=True, text=True).stdout


def ignored_state() -> list:
    """The gitignored places accept_run could leak into, which git status cannot see: every file's path,
    size and mtime under the REAL inbox/ and data/advisories/."""
    out = []
    for base in (ROOT / "inbox", ROOT / "data" / "advisories"):
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    st = p.stat()
                    out.append((str(p.relative_to(ROOT)), st.st_size, st.st_mtime_ns))
    return out


def checks(mutation) -> list:
    import asyncio
    m = load_all(None)
    acc = load_accept(mutation)
    out, before, before_ignored = [], git_status(), ignored_state()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        box, data, seen = tmp / "inbox", tmp / "data", tmp / "ledger.json"
        golden, alist = tmp / "golden.json", tmp / "feed_advisory_list.json"
        seen.write_text(ledger.dump([]), encoding="utf-8")
        golden.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020", "source_type": "fatf"}]}),
                          encoding="utf-8")
        alist.write_text(json.dumps({"schema": "fc08-feed-advisories/1", "advisories": []}, indent=2) + "\n",
                         encoding="utf-8")
        golden_bytes = golden.read_bytes()

        def make(rid, tamper=None, unterminated=(), extractor=None, queue=1, cost=0.3, refused=()):
            run, keys, session = listed_run(m, box, rid, n_relevant=3, n_dropped=1, queue=queue, cost=cost,
                                            unterminated=unterminated, refused=refused)
            asyncio.run(m["friday"].friday(run, session=session, extractor=extractor or valid_extractor(m, tamper),
                                           root=box, advisory_list=(golden, alist),
                                           tracked_runs=data / "feeds" / "runs"))
            return keys

        def accept(rid, decisions, *extra):
            f = tmp / ("%s.decisions.json" % rid)
            f.write_text(json.dumps(decisions), encoding="utf-8")
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = acc.main([rid, "--decisions", str(f), *extra], inbox_root=box, seen_path=seen, today=TODAY,
                                    data=data, advisory_list=alist, golden_list=golden)
            except Exception as exc:
                return None, "CRASHED %s: %s" % (type(exc).__name__, exc)
            return code, buf.getvalue()

        def untouched(label, said, alist_before, ledger_before):
            files = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file()) if data.exists() else []
            return (not files and alist.read_bytes() == alist_before and seen.read_bytes() == ledger_before,
                    "refused, writing nothing: %s" % label, "%s | files %s" % (said.strip()[:120], files[:3]))

        rid = "feeds-2026-10-02-bbb001"
        keys = make(rid)
        k_acc, k_def, k_def2, k_drop = keys[0], keys[1], keys[2], keys[3]
        decisions = {k_acc: "accept", k_def: "defer", k_def2: "defer", k_drop: "drop"}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        code, said = accept(rid, dict(decisions, **{k_drop: "accept"}))
        ok, label, detail = untouched("an accept of an item never extracted", said, a0, l0)
        # F4 (2026-09-28 fixes brief): untouched() alone cannot tell a real refusal from a crash -- accept()
        # returns (None, "CRASHED ...") on an exception, and "nothing written" still passes on a TypeError.
        # Pin the actual refusal too: exit 1, and the reason accept_run prints.
        out.append((ok and code == 1 and "was not extracted" in said, label, "code %s | %s" % (code, detail)))
        code, said = accept(rid, decisions, "--dry-run")
        out.append((code == 0 and "DRY RUN" in said and untouched("", said, a0, l0)[0], "a dry run writes nothing",
                    said.strip()[:120]))
        code, said = accept(rid, decisions)
        adv = "ADV-2026-0021"
        xrun = extraction.load_outcomes(rid, box)[k_acc]["extraction_run_id"]
        folder = box / rid
        req = extraction.load_requests(rid, box)[0]
        copies = {data / "advisories" / ("%s-fincen.pdf" % adv.lower()): folder / req["document"]["path"],
                  data / "feeds" / "records" / ("%s.json" % adv): folder / "records" / ("%s.json" % adv),
                  data / "proposals" / ("%s.jsonl" % xrun): folder / "proposals" / ("%s.jsonl" % xrun),
                  data / "telemetry" / ("%s.jsonl" % xrun): folder / "telemetry" / ("%s.jsonl" % xrun)}
        same = all(dst.exists() and dst.read_bytes() == src.read_bytes() for dst, src in copies.items())
        got = json.loads(alist.read_text(encoding="utf-8"))
        entry = got["advisories"][-1] if got["advisories"] else {"feed": {}}  # a FAIL below, never a crash
        out.append((code == 0 and same and entry["advisory_id"] == adv and entry["sha256"] == req["document"]["sha256"]
                    and entry["url"] == req["document"]["url"] and entry["feed"]["run_id"] == rid
                    and len(got["advisories"]) == 1 and golden.read_bytes() == golden_bytes
                    and got.get("schema") == "fc08-feed-advisories/1"
                    and got.get("counts") == {"advisories": 1, "by_source_type": {"fincen": 1}},
                    "an accepted item's document, record, queue and telemetry are copied byte for byte; the LIVE-FEED "
                    "advisory list gains its entry and the golden list is byte-identical",
                    "%s | %s" % (said.strip()[:100], entry.get("advisory_id"))))
        from governance import proposals as gate
        qpath = data / "proposals" / ("%s.jsonl" % xrun)
        props = [gate.Proposal.from_line(json.loads(l), source_file=qpath.name) for l in
                 (qpath.read_text().splitlines() if qpath.exists() else []) if l.strip()]
        clean, quarantined = gate.recheck(props, advisory_list=golden, advisories_dir=data / "advisories",
                                          feed_list=alist)
        out.append((len(clean) == 1 and not quarantined,
                    "the review gate passes the accepted queue against the new entry and the copied document",
                    [q.reason for q in quarantined]))
        clash = tmp / "clash.json"
        clash.write_text(json.dumps({"advisories": [{"advisory_id": "ADV-2026-0020", "source_type": "fincen"}]}),
                         encoding="utf-8")
        try:
            gate.recheck(props, advisory_list=golden, advisories_dir=data / "advisories", feed_list=clash)
            shadowed = "not refused"
        except ValueError as exc:
            shadowed = str(exc)
        out.append(("ADV-2026-0020" in shadowed and "both" in shadowed,
                    "the review gate refuses an advisory id in both the golden and the live-feed list, never "
                    "shadowing one with the other", shadowed[:120]))
        entries = ledger.load(seen)
        decided = {"%s:%s" % k: v["decision"] for k, v in entries.items()}
        items = {it["key"]: it for it in inbox.items(inbox.load(rid, box))}
        want = {"%s:%s" % (items[k]["source"], items[k]["item_id"]): d for k, d in ((k_acc, "accept"), (k_drop, "drop"))}
        run_dest = data / "feeds" / "runs" / rid
        out.append((decided == want and runs.classify(rid, box) == runs.ACCEPTED_STATE
                    and all((run_dest / n).exists() for n in ("triage.jsonl", "report.md", "accepted.json", "items.json"))
                    and (run_dest / "telemetry" / ("%s.jsonl" % rid)).exists(),
                    "the ledger holds the accepted and the dropped item and not the two deferred; the run's evidence is "
                    "in data/feeds/runs/<run>/ and the run is marked accepted", decided))
        code, said = accept(rid, decisions)
        out.append((code == 1 and "already accepted" in said, "a second acceptance is refused", said.strip()[:100]))

        # F4 (same weakness, same group): "code == 1" plus the reason accept_run actually prints, not just
        # "nothing was written" -- which a crash also leaves true.
        for n, (tamper, label, reason) in enumerate((
                ("record", "a record citing text not on its page", "citation(s) are not on the page"),
                ("queue", "a queue line the review gate would quarantine", "review gate would quarantine"))):
            rid = "feeds-2026-10-02-bbb00%d" % (n + 2)
            keys = make(rid, tamper=tamper)
            snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
            a0, l0 = alist.read_bytes(), seen.read_bytes()
            code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
            now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
            out.append((code == 1 and reason in said and now == snap and alist.read_bytes() == a0
                        and seen.read_bytes() == l0, "refused, writing nothing: %s" % label, said.strip()[:140]))

        rid = "feeds-2026-10-02-bbb004"
        keys = make(rid)
        xrun = extraction.load_outcomes(rid, box)[keys[0]]["extraction_run_id"]
        blocker = data / "proposals" / ("%s.jsonl" % xrun)
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("pre-existing\n", encoding="utf-8")
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        out.append((code == 1 and blocker.read_text() == "pre-existing\n" and alist.read_bytes() == a0
                    and seen.read_bytes() == l0 and "already exists; nothing is overwritten" in said,
                    "refused BY THE PLAN, before any write: a target that already exists",
                    said.strip()[:120]))
        blocker.rename(tmp / "moved-blocker")

        rid = "feeds-2026-10-02-bbb005"
        keys = make(rid, unterminated=("toolu_lost",))
        dec = {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        code, said = accept(rid, dec)
        refused = code == 1 and "RECONCILIATION_FAILED" in said and alist.read_bytes() == a0 and seen.read_bytes() == l0
        code2, said2 = accept(rid, dec, "--override-reconciliation", "owner read the transcript; the call was a retry")
        record = read_json(data / "feeds" / "runs" / rid / "accepted.json") if code2 == 0 else {}
        out.append((refused and code2 == 0 and record.get("override_reconciliation", "").startswith("owner read"),
                    "a RECONCILIATION_FAILED run is refused without an override, and accepted with one, the reason "
                    "recorded", "%s | %s" % (said.strip()[:80], said2.strip()[:60])))

        rid = "feeds-2026-10-02-bbb006"
        keys = make(rid)
        snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        real = acc.ledger.record_decisions
        acc.ledger = types.SimpleNamespace(**{k: getattr(ledger, k) for k in dir(ledger) if not k.startswith("__")})
        acc.ledger.record_decisions = lambda *a, **k: (_ for _ in ()).throw(ValueError("disk full (planted)"))
        code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        acc.ledger.record_decisions = real
        now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        leftover = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_dir() and not any(p.iterdir()))
        out.append((code == 1 and "disk full" in said and now == snap and alist.read_bytes() == a0
                    and seen.read_bytes() == l0 and runs.classify(rid, box) == runs.PENDING and not leftover,
                    "a failure while writing removes every copy and every folder this call made and restores the "
                    "advisory list", "%s | empty folders left %s" % (said.strip()[:100], leftover)))
        code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        out.append((code == 0 and runs.classify(rid, box) == runs.ACCEPTED_STATE,
                    "after the rollback, the same acceptance retried succeeds (nothing the failed call made blocks it)",
                    said.strip()[:120]))

        # Task 4 carry-forward: FAILED and DEFERRED-FOR-BUDGET items. Orchestrator US$3.50; the first extraction
        # (US$0.60) runs; the second request's linked PDF is unreadable (failed); the third would pass the
        # US$5.00 ceiling (deferred_budget).
        rid = "feeds-2026-10-02-bbb007"
        keys = make(rid, queue=3, cost=3.5, refused=(1,))
        outcomes = extraction.load_outcomes(rid, box)
        statuses = [outcomes.get(k, {}).get("status") for k in keys[:3]]
        defaults = acc.default_decisions(rid, box)
        want = {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"}
        out.append((statuses == ["extracted", "failed", "deferred_budget"] and defaults == want,
                    "the interactive default for a FAILED and a BUDGET-DEFERRED item is defer, never drop",
                    "%s | %s" % (statuses, [defaults.get(k) for k in keys])))
        refusals = []
        for k in keys[1:3]:
            snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
            a0, l0 = alist.read_bytes(), seen.read_bytes()
            code, said = accept(rid, dict(want, **{k: "accept"}), "--override-reconciliation", "owner accepts all")
            now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
            refusals.append(code == 1 and "was not extracted (%s)" % outcomes[k]["status"] in said and now == snap
                            and alist.read_bytes() == a0 and seen.read_bytes() == l0)
        code, said = accept(rid, want)
        decided = {"%s:%s" % k for k in ledger.load(seen)}
        items = {it["key"]: it for it in inbox.items(inbox.load(rid, box))}
        named = {k: "%s:%s" % (items[k]["source"], items[k]["item_id"]) for k in keys}
        out.append((refusals == [True, True] and code == 0 and named[keys[0]] in decided and named[keys[3]] in decided
                    and named[keys[1]] not in decided and named[keys[2]] not in decided,
                    "a failed or budget-deferred item cannot be accepted, even with the override; deferred, it is NOT "
                    "in the ledger, so it is listed again next Friday", "%s | %s" % (refusals, said.strip()[:100])))

        # Task 4 carry-forward: a run that CRASHED with an extraction in flight. That item holds an allocated id
        # and no record.
        rid = "feeds-2026-10-02-bbb008"
        keys = make(rid, queue=2, extractor=crashing_extractor(m, 2))
        rec = m["reconcile"].reconcile_run(rid, box)
        gap = extraction.load_allocations(rid, box).get(keys[1])
        inflight = extraction.load_outcomes(rid, box).get(keys[1], {})
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        dec = {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"}
        c_acc, s_acc = accept(rid, dict(dec, **{keys[1]: "accept"}), "--override-reconciliation", "owner read the crash")
        c_bare, s_bare = accept(rid, dec)
        refused = (c_acc == 1 and "was not extracted (failed)" in s_acc and c_bare == 1 and "FAILED" in s_bare
                   and alist.read_bytes() == a0 and seen.read_bytes() == l0)
        code, said = accept(rid, dec, "--override-reconciliation", "owner read the crash; the first record stands")
        record = read_json(data / "feeds" / "runs" / rid / "accepted.json") if code == 0 else {}
        listed_ids = {a["advisory_id"] for a in json.loads(alist.read_text(encoding="utf-8"))["advisories"]}
        nxt = extraction.next_advisory_id(2026, (golden, alist), box, data / "feeds" / "runs")
        # ...and from a checkout with no inbox at all, only the tracked copy accept_run made.
        cold = extraction.next_advisory_id(2026, (golden, alist), tmp / "no-inbox", data / "feeds" / "runs")
        out.append((rec["status"] == "FAILED" and bool(rec["crash"]) and gap is not None
                    and inflight.get("status") == "failed" and inflight.get("advisory_id") == gap and refused
                    and code == 0 and record.get("allocated_not_accepted") == {keys[1]: gap}
                    and gap not in listed_ids and nxt > gap and cold > gap,
                    "a crashed run's in-flight item (an allocated id, no record) cannot be accepted, even with the "
                    "override; deferred, its id is named in accepted.json as allocated-and-unused, a gap never reused",
                    "gap %s, next %s (%s with no inbox) | %s | %s" % (gap, nxt, cold, s_acc.strip()[:50],
                                                                     record.get("allocated_not_accepted"))))

        # Review fix 1: a failure PART-WAY through a copy (here the record's: the second copy writes some bytes, then
        # the disk is full). The truncated file must be rolled back like any other, and the retry must succeed.
        rid = "feeds-2026-10-02-bbb009"
        keys = make(rid)
        snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        real_shutil, copies_seen = acc.shutil, []

        def half_then_full(inp, out, *a):
            copies_seen.append(out.name)
            if len(copies_seen) == 2:
                out.write(inp.read(7))
                raise OSError(28, "No space left on device (planted mid-copy)")
            return real_shutil.copyfileobj(inp, out, *a)
        acc.shutil = types.SimpleNamespace(**{k: getattr(real_shutil, k) for k in dir(real_shutil)
                                              if not k.startswith("__")})
        acc.shutil.copyfileobj = half_then_full
        try:
            code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        finally:
            acc.shutil = real_shutil
        now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        leftover = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_dir() and not any(p.iterdir()))
        restored = alist.read_bytes() == a0 and seen.read_bytes() == l0
        code2, said2 = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        out.append((code == 1 and "planted mid-copy" in said and len(copies_seen) == 2 and now == snap
                    and not leftover and restored and code2 == 0
                    and runs.classify(rid, box) == runs.ACCEPTED_STATE,
                    "a failure PART-WAY through a copy leaves no truncated file and no folder behind, and the retry "
                    "succeeds", "%s | left %s | %s" % (said.strip()[:80], sorted(set(map(str, now)) - set(map(str, snap)))[:2],
                                                    said2.strip()[:40])))

        # Review fix 3: the inbox marker cannot be written AFTER the ledger. Recorded, not refused; the printed
        # recovery (one copy) is followed literally, and the run then reads as accepted.
        rid = "feeds-2026-10-02-bbb010"
        keys = make(rid)
        real_runs = acc.runs
        acc.runs = types.SimpleNamespace(**{k: getattr(runs, k) for k in dir(runs) if not k.startswith("__")})
        acc.runs.mark_accepted = lambda *a, **k: (_ for _ in ()).throw(OSError(30, "Read-only file system (planted)"))
        try:
            code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        finally:
            acc.runs = real_runs
        items = {it["key"]: it for it in inbox.items(inbox.load(rid, box))}
        in_ledger = (items[keys[0]]["source"], items[keys[0]]["item_id"]) in ledger.load(seen)
        pending = runs.classify(rid, box) == runs.PENDING
        cp = [l.split() for l in said.splitlines() if l.strip().startswith("cp ")]
        if len(cp) == 1 and len(cp[0]) == 3 and Path(cp[0][1]).is_file() and not Path(cp[0][2]).exists():
            Path(cp[0][2]).write_bytes(Path(cp[0][1]).read_bytes())  # the recovery, exactly as printed
        code2, said2 = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        out.append((code == 2 and "RECORDED, BUT NOT MARKED" in said and "REFUSED" not in said and in_ledger and pending
                    and len(cp) == 1 and cp[0][2] == str(box / rid / "accepted.json")
                    and runs.classify(rid, box) == runs.ACCEPTED_STATE and code2 == 1 and "already accepted" in said2,
                    "a marker that cannot be written after the ledger reads RECORDED, BUT NOT MARKED (exit 2), not "
                    "REFUSED, and the one copy it prints recovers the run", said.strip().splitlines()[0][:120]))

        young, old = "feeds-2026-09-25-ccc001", "feeds-2026-09-19-ccc002"
        for r in (young, old, "feeds-2026-09-01-ccc003"):
            inbox.save(r, {"run_id": r, "sources": {"ofac": {"items": [{"key": "ofac:%016x" % len(r), "source": "ofac",
                                                                          "item_id": r}]}}}, box)
        inbox.save("feeds-2026-09-02-ccc004", {"run_id": "feeds-2026-09-02-ccc004", "eval": True,
                                               "sources": {"ofac": {"items": [{"key": "ofac:1", "source": "ofac"}]}}}, box)
        l0 = seen.read_bytes()
        blocking = [r for r, _ in runs.blocking(box, TODAY)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            young_code = acc.main(["--expire", young], inbox_root=box, seen_path=seen, today=TODAY, data=data,
                                  advisory_list=alist)
            all_code = acc.main(["--expire"], inbox_root=box, seen_path=seen, today=TODAY, data=data, advisory_list=alist)
        out.append((young in blocking and old not in blocking and "feeds-2026-09-02-ccc004" not in
                    [r for r, _ in runs.pending(box, TODAY)] and young_code == 1 and all_code == 0
                    and (box / "expired" / old).is_dir() and (box / "expired" / "feeds-2026-09-01-ccc003").is_dir()
                    and (box / young).is_dir() and seen.read_bytes() == l0,
                    "a pending run under 14 days blocks and refuses --expire; at 14+ it moves to inbox/expired/, the "
                    "ledger untouched; an eval run is never pending", "%s | blocking %s" % (buf.getvalue().strip()[:80],
                                                                                          blocking)))

        # Task 4 carry-forward: --expire takes the Friday run's OWN lock (tools/friday_run.run_lock), so it cannot
        # move a run folder while a live run is reading every run's allocations.
        stale = "feeds-2026-09-10-ccc005"
        inbox.save(stale, {"run_id": stale, "sources": {"ofac": {"items": [{"key": "ofac:%016x" % 5, "source": "ofac",
                                                                            "item_id": stale}]}}}, box)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with m["friday"].run_lock(box) as held:
                locked_code = acc.main(["--expire", stale], inbox_root=box, seen_path=seen, today=TODAY, data=data,
                                       advisory_list=alist)
                locked_all = acc.main(["--expire"], inbox_root=box, seen_path=seen, today=TODAY, data=data,
                                      advisory_list=alist)
                still = (box / stale).is_dir() and not (box / "expired" / stale).exists()
            free_code = acc.main(["--expire", stale], inbox_root=box, seen_path=seen, today=TODAY, data=data,
                                 advisory_list=alist)
        said = buf.getvalue()
        out.append((held and locked_code == 1 and locked_all == 1 and still and "Friday run" in said
                    and free_code == 0 and (box / "expired" / stale).is_dir() and seen.read_bytes() == l0,
                    "--expire is refused while a Friday run holds the inbox's lock (the SAME lock), moving nothing; "
                    "released, it expires the run", said.strip().splitlines()[0][:120] if said.strip() else ""))

        # F2 (2026-09-28 fixes brief): accepting a run takes the SAME lock -- reconciliation reads every run's
        # allocations, and a live Friday run could still be making them.
        rid = "feeds-2026-10-02-bbb012"
        keys = make(rid)
        dec = {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        with m["friday"].run_lock(box) as held2:
            locked_code2, locked_said2 = accept(rid, dec)
            locked_untouched = (alist.read_bytes() == a0 and seen.read_bytes() == l0
                                and runs.classify(rid, box) == runs.PENDING)
        free_code2, free_said2 = accept(rid, dec)
        out.append((held2 and locked_code2 == 1 and "Friday run" in locked_said2 and locked_untouched
                    and free_code2 == 0 and runs.classify(rid, box) == runs.ACCEPTED_STATE,
                    "accepting is refused while a Friday run holds the inbox's lock (the SAME lock), writing "
                    "nothing; released, the same acceptance succeeds",
                    "%s | %s" % (locked_said2.strip()[:100], free_said2.strip()[:60])))

        # F1 (2026-09-28 fixes brief): feeds/runs.mark_accepted must never leave a PARTIAL marker. classify()
        # only checks whether accepted.json EXISTS -- never its content -- so a crash mid-write must leave
        # nothing at the final path, not a truncated file classify() would misread as accepted.
        box2 = tmp / "runs-f1"
        rid_f1 = "feeds-2026-10-02-fff001"
        inbox.save(rid_f1, {"run_id": rid_f1, "sources": {"ofac": {"items": [
            {"key": "ofac:1", "source": "ofac", "item_id": "1"}]}}}, box2)
        runs_mod = load_runs(mutation)

        def crashing(real):
            def opener(file, mode="r", *a, **kw):
                f = real(file, mode, *a, **kw)
                if any(c in mode for c in "wxa"):
                    real_write = f.write

                    def write(data, _rw=real_write):
                        _rw(data[:5])
                        raise OSError(28, "No space left on device (planted mid-write)")
                    f.write = write
                return f
            return opener

        real_bopen, real_ioopen = builtins.open, io.open
        builtins.open, io.open = crashing(real_bopen), crashing(real_ioopen)
        crashed = False
        try:
            runs_mod.mark_accepted(rid_f1, {"run_id": rid_f1, "decided_on": "2026-10-02"}, box2)
        except OSError as exc:
            crashed = "planted mid-write" in str(exc)
        finally:
            builtins.open, io.open = real_bopen, real_ioopen
        marker_dir = inbox.run_dir(rid_f1, box2)
        leftover = sorted(p.name for p in marker_dir.iterdir() if p.name != inbox.ITEMS)
        out.append((crashed and not (marker_dir / runs.ACCEPTED).exists() and not leftover
                    and runs.classify(rid_f1, box2) == runs.PENDING,
                    "a crash mid-write to the inbox marker leaves no marker at all (never a truncated one); "
                    "the run still classifies as pending, not accepted",
                    "leftover %s | classify %s" % (leftover, runs.classify(rid_f1, box2))))

        # F5 (2026-09-28 fixes brief): an extracted item with no triage verdict must refuse, never crash.
        rid = "feeds-2026-10-02-bbb013"
        keys = make(rid)
        k0 = keys[0]
        real_reconcile = acc.reconcile

        def no_verdict(rid_, root_):
            rec = real_reconcile.reconcile_run(rid_, root_)
            return dict(rec, verdicts={k: v for k, v in rec["verdicts"].items() if k != k0})
        acc.reconcile = types.SimpleNamespace(**{k: getattr(real_reconcile, k) for k in dir(real_reconcile)
                                                 if not k.startswith("__")})
        acc.reconcile.reconcile_run = no_verdict
        snap = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        a0, l0 = alist.read_bytes(), seen.read_bytes()
        try:
            code, said = accept(rid, {keys[0]: "accept", keys[1]: "defer", keys[2]: "defer", keys[3]: "drop"})
        finally:
            acc.reconcile = real_reconcile
        now = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
        out.append((code == 1 and "has no triage verdict" in said and k0 in said and now == snap
                    and alist.read_bytes() == a0 and seen.read_bytes() == l0,
                    "an extracted item with no triage verdict refuses, naming it, and writes nothing",
                    said.strip()[:140]))

        cat = tmp / "catalogue.json"
        cat.write_text(json.dumps({"items": [{"source": "ofsi", "item_id": "c%d" % i} for i in range(4)]}), encoding="utf-8")
        seed_ledger = tmp / "seed-ledger.json"
        seed_ledger.write_text(ledger.dump([]), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            dry = acc.seed_catalogue(TODAY, seed_ledger, cat, dry_run=True)
            first = acc.seed_catalogue(TODAY, seed_ledger, cat)
            second = acc.seed_catalogue(TODAY, seed_ledger, cat)
        got = ledger.load(seed_ledger)
        label = "catalogue:%s" % hashlib.sha256(cat.read_bytes()).hexdigest()[:12]
        out.append((dry == 0 and first == 0 and second == 1 and len(got) == 4
                    and all(e["decision"] == "drop" and e["first_seen_run"] == label for e in got.values()),
                    "--seed-catalogue records every catalogue item as a drop under catalogue:<sha12>, once",
                    buf.getvalue().strip().splitlines()[-1][:100]))
    after = ignored_state()
    out.append((git_status() == before and after == before_ignored,
                "the repository's git status is unchanged, and so are the real inbox/ and data/advisories/",
                "changed: %s" % sorted({p for p, _, _ in after} ^ {p for p, _, _ in before_ignored})))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin accept_run end to end")
    ap.add_argument("--mutate", choices=sorted(set(MUTATIONS) | set(RUNS_MUTATIONS)),
                    help="break one rule in memory; a check MUST fail")
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
