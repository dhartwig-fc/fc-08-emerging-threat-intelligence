"""
Pin the seen-items ledger, the run inbox and the accept_run skeleton (slice 2, sub-project A).

Usage:
    python evals/check_feeds_ledger.py
    python evals/check_feeds_ledger.py --mutate unsorted        # ledger written in arrival order
    python evals/check_feeds_ledger.py --mutate allow-reseen    # an already-decided item may be decided again
    python evals/check_feeds_ledger.py --mutate escape-inbox    # a path outside the run's folder is written
    python evals/check_feeds_ledger.py --mutate overwrite-pin   # a pinned file is overwritten with other bytes
    python evals/check_feeds_ledger.py --mutate skip-coverage   # accept_run takes decisions that miss an item
    python evals/check_feeds_ledger.py --mutate accept-allowed  # accept_run records an accept it cannot carry out
    python evals/check_feeds_ledger.py --mutate newline-run-id  # a run id with a trailing newline is accepted

WHAT IT HOLDS. "New" is decided by data/feeds/seen.json and nothing else, so that file must be
canonical (the same decisions give the same bytes), must never decide an item twice, and must be
written only by tools/accept_run.py, which refuses the whole run unless every listed item is decided
exactly once. In sub-project A an "accept" is refused: accepting also moves the item's record and
document into tracked data, which is sub-project C, and a ledger saying "accepted" over nothing
moved would be false. A run's inbox is written only inside inbox/<run_id>/, and a pinned file there
is immutable.

WRITER SCAN. Among the repository's Python files, only feeds/ledger.py names seen.json, only
tools/accept_run.py calls record_decisions(), and only those two (and the guards, which write
temporary ledgers) call ledger.dump( -- the canonical bytes a direct write of SEEN_PATH would need.
It is a scan for NAMES and calls, not a proof about every possible write: a module that built the
JSON itself and wrote it through a path it assembled would pass. The scanner is itself checked on a
planted rogue writer, one line per rule, each required to be caught, so an empty scan cannot pass by
matching nothing.

COLD. Temporary folders only; the tracked ledger is read, never written.
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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.model import FeedItem  # noqa: E402

LEDGER = ROOT / "feeds" / "ledger.py"
INBOX = ROOT / "feeds" / "inbox.py"
ACCEPT = ROOT / "tools" / "accept_run.py"
RUN = "feeds-2026-10-02-abc123"
TODAY = date(2026, 10, 2)

MUTATIONS = {
    "unsorted": (LEDGER, 'items = sorted(entries, key=lambda e: (e["source"], e["item_id"]))', "items = list(entries)"),
    "allow-reseen": (LEDGER, "        if key in seen:\n", "        if False:\n"),
    "escape-inbox": (INBOX, "    if folder not in target.parents:\n", "    if False:\n"),
    "overwrite-pin": (INBOX, "        if target.read_bytes() != data:\n", "        if False:\n"),
    "skip-coverage": (ACCEPT, "    if missing or extra:\n", "    if False:\n"),
    "accept-allowed": (ACCEPT, "    if accepted:\n", "    if False:\n"),
    "newline-run-id": (INBOX, '    if not RUN_ID.fullmatch(run_id or ""):\n',
                       '    if not re.match(r"^feeds-\\d{4}-\\d{2}-\\d{2}-[0-9a-f]{6}$", run_id or ""):\n'),
}


def load(name: str, path: Path, mutation) -> types.ModuleType:
    """Load a module from source, mutated when the mutation targets this file, and install it."""
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
    package, _, leaf = name.rpartition(".")
    if package:
        setattr(importlib.import_module(package), leaf, module)
    return module


def writer_violations(files: dict) -> list:
    out = []
    for rel, text in sorted(files.items()):
        if "seen.json" in text and rel not in ("feeds/ledger.py", "evals/check_feeds_ledger.py",
                                               "evals/check_feeds_server.py"):
            out.append("%s names seen.json" % rel)
        if "record_decisions(" in text and rel not in ("feeds/ledger.py", "tools/accept_run.py",
                                                       "evals/check_feeds_ledger.py"):
            out.append("%s calls record_decisions()" % rel)
        if "ledger.dump(" in text and rel not in ("feeds/ledger.py", "tools/accept_run.py",
                                                  "evals/check_feeds_ledger.py", "evals/check_feeds_server.py"):
            out.append("%s calls ledger.dump()" % rel)
    return out


def repo_python() -> dict:
    skip = {".venv", ".superpowers", ".git", "__pycache__"}
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8", errors="replace")
            for p in ROOT.rglob("*.py") if not skip & set(p.relative_to(ROOT).parts)}


def item(source: str, item_id: str) -> dict:
    return dict(FeedItem(source, item_id, "Title " + item_id, "https://example.invalid/" + item_id,
                         "2026-10-01").to_json(), document=None)


def checks(ledger, inbox, accept) -> list:
    out = []
    tracked = ledger.SEEN_PATH.read_text(encoding="utf-8")
    out.append((tracked == ledger.dump(ledger.load().values()), "the tracked ledger loads and is in canonical form",
                "%d entries" % len(ledger.load())))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        a, b = tmp / "a.json", tmp / "b.json"
        for p in (a, b):
            p.write_text(ledger.dump([]), encoding="utf-8")
        ds = [{"source": "ofsi", "item_id": "z", "decision": "drop"},
              {"source": "fincen", "item_id": "m", "decision": "drop"},
              {"source": "ofac", "item_id": "a", "decision": "accept"}]
        ledger.record_decisions(RUN, "2026-10-02", ds, path=a)
        ledger.record_decisions(RUN, "2026-10-02", list(reversed(ds)), path=b)
        out.append((a.read_bytes() == b.read_bytes(), "the same decisions give the same bytes in any arrival order", ""))

        before = a.read_bytes()
        for label, call in (
                ("an already-decided item", lambda: ledger.record_decisions("feeds-2026-10-09-def456", "2026-10-09",
                                                                            [ds[0]], path=a)),
                ("an item decided twice in one call", lambda: ledger.record_decisions(
                    RUN, "2026-10-02", [dict(ds[0], item_id="n"), dict(ds[0], item_id="n")], path=a)),
                ("a decision that is not accept or drop", lambda: ledger.record_decisions(
                    RUN, "2026-10-02", [dict(ds[0], item_id="k", decision="keep")], path=a)),
                ("a malformed date", lambda: ledger.record_decisions(
                    RUN, "2 Oct", [dict(ds[0], item_id="q")], path=a))):
            try:
                call()
                refused = False
            except ValueError:
                refused = True
            out.append((refused and a.read_bytes() == before, "record_decisions refuses %s and writes nothing" % label, ""))

        root = tmp / "inbox"
        for label, rel in (("a parent-relative path", "../escape.txt"), ("an absolute path", str(tmp / "abs.txt"))):
            try:
                inbox.write_file(RUN, rel, b"x", root)
                refused = False
            except ValueError:
                refused = True
            out.append((refused and not (tmp / "escape.txt").exists() and not (tmp / "abs.txt").exists(),
                        "inbox.write_file refuses %s outside the run's folder" % label, rel))
        inbox.write_file(RUN, "docs/pinned.html", b"one", root)
        same = inbox.write_file(RUN, "docs/pinned.html", b"one", root) == "docs/pinned.html"
        try:
            inbox.write_file(RUN, "docs/pinned.html", b"two", root)
            refused = False
        except ValueError:
            refused = True
        out.append((same and refused and (root / RUN / "docs" / "pinned.html").read_bytes() == b"one",
                    "a pinned file takes the same bytes again and refuses different ones", ""))
        try:
            inbox.run_dir("../escape", root)
            refused = False
        except ValueError:
            refused = True
        out.append((refused, "a malformed run id is refused", ""))
        try:
            inbox.run_dir(RUN + "\n", root)
            refused = False
        except ValueError:
            refused = True
        out.append((refused and inbox.run_dir(RUN, root) == root / RUN,
                    "a run id with a trailing newline is refused (exact match), and the same id without it is not",
                    repr(RUN + "\n")))

        seen = tmp / "seen.json"
        seen.write_text(ledger.dump([]), encoding="utf-8")
        listed = [item("ofsi", "o1"), item("ofsi", "o2"), item("fincen", "f1")]
        inbox.save(RUN, {"run_id": RUN, "sources": {"ofsi": {"items": listed[:2]}, "fincen": {"items": listed[2:]}}},
                   root)
        keys = sorted(it["key"] for it in listed)

        def run(decisions: dict, *extra) -> tuple:
            f = tmp / "decisions.json"
            f.write_text(json.dumps(decisions), encoding="utf-8")
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = accept.main([RUN, "--decisions", str(f), *extra], inbox_root=root, seen_path=seen,
                                       today=TODAY)
            except Exception as exc:  # a crash is not a refusal: the check must fail, not the guard
                return None, "CRASHED: %s: %s" % (type(exc).__name__, exc)
            return code, buf.getvalue()

        empty = seen.read_bytes()
        for label, decisions in (("a decision missing for one item", {k: "drop" for k in keys[1:]}),
                                 ("a key the run did not list", dict({k: "drop" for k in keys}, **{"ofac:0": "drop"})),
                                 ("an accept", dict({k: "drop" for k in keys}, **{keys[0]: "accept"}))):
            code, said = run(decisions)
            out.append((code == 1 and "REFUSED" in said and seen.read_bytes() == empty,
                        "accept_run refuses %s and writes nothing" % label, said.strip()[:160]))
        code, said = run({k: "drop" for k in keys}, "--dry-run")
        out.append((code == 0 and "DRY RUN" in said and seen.read_bytes() == empty,
                    "a dry run writes nothing", said.strip()))
        code, said = run({k: "drop" for k in keys})
        got = ledger.load(seen)
        out.append((code == 0 and len(got) == 3 and all(e["first_seen_run"] == RUN and e["decision"] == "drop"
                                                         and e["decided_on"] == "2026-10-02" for e in got.values()),
                    "an all-drop run records every listed item, with its run and date", said.strip()))
        code, said = run({k: "drop" for k in keys})
        out.append((code == 1 and "already decided" in said, "the same run cannot be decided twice", said.strip()[:160]))
        f = tmp / "none.json"
        f.write_text("{}", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = accept.main(["feeds-2026-10-02-000000", "--decisions", str(f)], inbox_root=root, seen_path=seen)
        out.append((code == 1 and "no items.json" in buf.getvalue(), "a run with no inbox is refused", ""))

    scanned = repo_python()
    real = writer_violations(scanned)
    has_writers = "feeds/ledger.py" in scanned and "tools/accept_run.py" in scanned and len(scanned) >= 20
    planted = writer_violations(dict(scanned, **{"tools/rogue.py": "ledger.record_decisions(r, d, x)\n"
                                                                   "open('data/feeds/seen.json')\n"
                                                                   "ledger.SEEN_PATH.write_text(ledger.dump(entries))\n"}))
    want = ["tools/rogue.py names seen.json", "tools/rogue.py calls record_decisions()", "tools/rogue.py calls ledger.dump()"]
    out.append((has_writers and not real and sorted(planted) == sorted(want),
                "only feeds/ledger.py names seen.json, only tools/accept_run.py records decisions, and no other module "
                "calls ledger.dump( (a planted rogue writer is caught on each of the three)",
                "violations %s; planted %s; scanned %d files" % (real, planted, len(scanned))))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the seen-items ledger, the inbox and accept_run")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS), help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    ledger = load("feeds.ledger", LEDGER, args.mutate)
    inbox = load("feeds.inbox", INBOX, args.mutate)
    accept = load("accept_run_under_test", ACCEPT, args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks(ledger, inbox, accept):
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
