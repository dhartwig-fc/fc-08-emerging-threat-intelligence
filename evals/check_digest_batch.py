"""
Pin the digest batch contract: a batch records the inputs it was built from, can be
re-checked after any number of later decisions, and is never overwritten.

Usage:
    python evals/check_digest_batch.py
    python evals/check_digest_batch.py --mutate prefix      # --check reads the WHOLE log; checks MUST fail
    python evals/check_digest_batch.py --mutate overwrite   # an existing batch may be rewritten; MUST fail

WHY. Week 5's first batch could not be re-verified once a new decision landed: --check
rebuilt from the whole log, so any later decision made a correct batch look broken, and
a broken renderer looked the same as a moved world. The manifest separates the two.

OFFLINE. Everything runs over COPIES of the real records, queue and decision log in a
temporary directory; the real data/ tree is never written. No model, no PDF.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import decisions as gd  # noqa: E402
from governance.digest import RECORDS_DIR  # noqa: E402
from governance.proposals import ADVISORY_LIST, LIBRARY, QUEUE_DIR  # noqa: E402
from governance.routing import ROUTING  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="fc08_batch_"))
MUTATION = None


def _cli(*args) -> subprocess.CompletedProcess:
    extra = ["--_mutate", MUTATION] if MUTATION else []
    return subprocess.run([sys.executable, str(ROOT / "tools" / "build_digests.py")] + list(args) + extra,
                          capture_output=True, text=True, cwd=ROOT)


def _copy_inputs(name: str) -> dict:
    base = WORK / name
    shutil.copytree(RECORDS_DIR, base / "records")
    shutil.copytree(QUEUE_DIR, base / "proposals")
    shutil.copy(gd.LOG, base / "log.jsonl")
    return {"--records-dir": base / "records", "--queue-dir": base / "proposals",
            "--log": base / "log.jsonl", "--out-dir": base / "digests"}


def _args(paths: dict) -> list:
    return [x for k, v in paths.items() for x in (k, str(v))]


def checks() -> list:
    out = []
    p = _copy_inputs("a")
    r = _cli("--batch-id", "guard-a", *_args(p))
    manifest = p["--out-dir"] / "guard-a" / "manifest.json"
    out.append((r.returncode == 0 and manifest.exists(), "a build writes manifest.json beside the desk files",
                (r.stdout + r.stderr).strip()[-160:]))
    m = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    lines, sha, _ = gd.log_prefix(None, p["--log"])
    out.append((m.get("decision_log") == {"lines": lines, "sha256": sha},
                "the manifest pins the decision log's line count and hash", str(m.get("decision_log"))))
    out.append((len(m.get("records", {})) == 20 and len(m.get("proposals", {})) >= 1,
                "the manifest hashes every record and every queue file it read",
                "%d records, %d queue files" % (len(m.get("records", {})), len(m.get("proposals", {})))))
    text = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
    out.append((bool(text) and gd.LOG.name not in text and "/" not in "".join(m.get("records", {})),
                "the manifest names inputs by role and filename, never the log's filename or a path", text[:80]))

    r = _cli("--batch-id", "guard-a", "--check", *_args(p))
    out.append((r.returncode == 0, "a fresh batch --check matches", r.stdout.strip()[-120:]))

    # A LATER decision reversing the last link. The batch must still match: it reads its pinned prefix.
    later = json.loads(p["--log"].read_text(encoding="utf-8").splitlines()[-1])
    later["decided_at"] = "2099-01-01T00:00:00+00:00"
    later["decision"] = "reject" if later["decision"] == "approve" else "approve"
    with open(p["--log"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(later, sort_keys=True) + "\n")
    r = _cli("--batch-id", "guard-a", "--check", *_args(p))
    out.append((r.returncode == 0,
                "after a LATER decision reverses a link, the batch still matches (it reads its pinned prefix)",
                r.stdout.strip()[-160:]))

    r = _cli("--batch-id", "guard-a", *_args(p))
    out.append((r.returncode == 2 and "exists" in (r.stdout + r.stderr),
                "building an existing batch id is REFUSED, exit 2", (r.stdout + r.stderr).strip()[-160:]))

    rec = sorted(p["--records-dir"].glob("ADV-*.json"))[0]
    rec.write_text(rec.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    r = _cli("--batch-id", "guard-a", "--check", *_args(p))
    out.append((r.returncode == 1 and ("inputs moved since this batch: %s" % rec.name) in r.stdout,
                "a changed record reads as INPUTS MOVED, naming the file", r.stdout.strip()[-160:]))

    q = _copy_inputs("b")
    _cli("--batch-id", "guard-b", *_args(q))
    desk = sorted((q["--out-dir"] / "guard-b").glob("*.md"))[0]
    desk.write_text(desk.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    r = _cli("--batch-id", "guard-b", "--check", *_args(q))
    out.append((r.returncode == 1 and ("same inputs, different output: %s" % desk.stem) in r.stdout,
                "a changed desk file with unchanged inputs reads as SAME INPUTS, DIFFERENT OUTPUT",
                r.stdout.strip()[-160:]))

    s = _copy_inputs("c")
    _cli("--batch-id", "guard-c", *_args(s))
    kept = s["--log"].read_text(encoding="utf-8").splitlines(keepends=True)[:-1]
    s["--log"].write_text("".join(kept), encoding="utf-8")
    r = _cli("--batch-id", "guard-c", "--check", *_args(s))
    out.append((r.returncode == 1 and "decision log" in r.stdout,
                "a log with a pinned line REMOVED fails, naming the decision log", r.stdout.strip()[-160:]))

    # The manifest also pins the typology library, advisory list and routing table:
    # build_batch() reads all three, so any of them moving is as much a moved input as a
    # record is. A temp copy of the routing table (never the real data/ tree) proves it.
    t = _copy_inputs("d")
    r = _cli("--batch-id", "guard-d", *_args(t))
    manifest_d_path = t["--out-dir"] / "guard-d" / "manifest.json"
    manifest_d = json.loads(manifest_d_path.read_text(encoding="utf-8")) if manifest_d_path.exists() else {}
    out.append((set(manifest_d.get("config", {})) == {LIBRARY.name, ADVISORY_LIST.name, ROUTING.name},
                "the manifest pins the library, advisory list and routing table by filename",
                str(sorted(manifest_d.get("config", {})))))

    routing_copy = WORK / "d" / "moved_routing" / ROUTING.name
    routing_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROUTING, routing_copy)
    routing_copy.write_text(routing_copy.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    r = _cli("--batch-id", "guard-d", "--check", *_args(t), "--routing", str(routing_copy))
    out.append((r.returncode == 1 and ("inputs moved since this batch: %s" % ROUTING.name) in r.stdout,
                "a routing table changed via --routing (the real data/ tree untouched) reads as INPUTS "
                "MOVED, naming desk_routing.json", r.stdout.strip()[-160:]))

    real = ROOT / "data" / "digests" / "slice1-2026-09-24" / "manifest.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_digests.py"), "--batch-id",
                        "slice1-2026-09-24", "--check"], capture_output=True, text=True, cwd=ROOT)
    out.append((real.exists() and r.returncode == 0,
                "the committed batch slice1-2026-09-24 has a manifest and matches", r.stdout.strip()[-160:]))
    return out


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Pin the digest batch contract")
    ap.add_argument("--mutate", choices=("prefix", "overwrite"), help="break one rule; checks MUST fail")
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if MUTATION:
        print("MUTATED: %s\n" % {"prefix": "--check rebuilds from the whole log, not the pinned prefix.",
                                 "overwrite": "an existing batch id may be rebuilt over."}[MUTATION])
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if MUTATION:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
