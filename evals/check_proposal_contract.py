"""
Pin the proposal contract: every proposal names its run and its quotes are real.

Usage:
    python evals/check_proposal_contract.py
    python evals/check_proposal_contract.py --mutate citations   # quote check removed; refusals MUST stop
    python evals/check_proposal_contract.py --mutate run         # advisory check removed; refusal MUST stop

WHY. Measured 2026-09-24: 383 proposals in the review queue, not one carrying a
citation or the run that made it. A reviewer shown such a proposal can read the
agent's reasoning but cannot check it, so approving it approves an assertion.
Since week 5 the runner tells the server who the run is (agents/run_identity.py)
and propose_link refuses: no run identity, an advisory other than the run's, a
document whose hash is not the run's, and any quote not on the page it names.

NOT A VACUOUS PASS. It also requires a correct proposal to be ACCEPTED -- a
server that refused everything would satisfy every refusal check.

NEEDS the ADV-2026-0002 PDF in data/advisories/ (gitignored). Without it this
exits 2 and says so; it never reports HELD over checks it did not run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADVISORY = "ADV-2026-0002"
OTHER_ADVISORY = "ADV-2026-0013"
QUEUE_DIR = Path(tempfile.mkdtemp(prefix="fc08_contract_"))
RUN_ID = "probe-contract"
QUEUE = QUEUE_DIR / ("%s.jsonl" % RUN_ID)
# Redirect the queue BEFORE any proposal: a guard never writes the real one. The
# server owns the directory (a module constant, repointed here in-process); the
# file name is the run id.
os.environ["NEXUS_PROPOSALS_PATH"] = str(QUEUE)

from mcp_server import knowledge_centre_server as kc  # noqa: E402

kc.QUEUE_DIR = QUEUE_DIR

_LIST = {a["advisory_id"]: a for a in
         json.loads((ROOT / "evals" / "golden" / "advisory_list.json").read_text(encoding="utf-8"))["advisories"]}
PDF = ROOT / "data" / "advisories" / Path(_LIST[ADVISORY]["file"]).name
SHA = _LIST[ADVISORY]["sha256"]


def _run_env(**override) -> None:
    env = {"NEXUS_RUN_ID": RUN_ID, "NEXUS_STAGE": "extractor", "NEXUS_ADVISORY_ID": ADVISORY,
           "NEXUS_PDF_PATH": str(PDF), "NEXUS_PDF_SHA256": SHA}
    env.update(override)
    for k in kc.RUN_ENV:
        os.environ.pop(k, None)
    for k, v in env.items():
        if v is not None:
            os.environ[k] = v


def _witness() -> tuple:
    """An untwinned typology from the golden label, with a citation known to be on its page."""
    g = json.loads((ROOT / "evals" / "golden" / ("%s.json" % ADVISORY)).read_text(encoding="utf-8"))
    for t in g["typologies"]:
        if t.get("typology_id") and t["typology_id"] not in kc.TYPOLOGY_TWINS:
            c = t["citations"][0]
            return t["typology_id"], {"page": c["page"], "quote": c["quote"]}
    raise SystemExit("no untwinned typology in the %s golden label -- the witness is gone" % ADVISORY)


def _propose(**kw) -> str:
    fn = getattr(kc.propose_link, "fn", kc.propose_link)
    return asyncio.run(fn(kc.ProposeLinkInput(**kw)))


def _schema_refuses(**kw) -> bool:
    try:
        kc.ProposeLinkInput(**kw)
        return False
    except Exception:
        return True


def _lines() -> list:
    if not QUEUE.exists():
        return []
    return [json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]


def checks() -> list:
    out = []
    tid, cite = _witness()
    base = dict(advisory_id=ADVISORY, typology_id=tid, confidence="medium", citations=[cite],
                rationale="The advisory describes this technique on page %d." % cite["page"])

    _run_env()
    got = _propose(**base)
    out.append((got.startswith("Accepted") and len(_lines()) == 1,
                "a correct proposal is ACCEPTED and written", got[:110]))
    first = (_lines() or [{}])[0]
    out.append((first.get("schema") == "proposal/2" and first.get("run_id") == "probe-contract"
                and first.get("stage") == "extractor" and first.get("document_sha256") == SHA
                and first.get("citations") == [cite],
                "the line carries schema, run id, stage, document hash and citations",
                "keys: %s" % sorted(first)))

    _propose(**base)
    ids = [line["proposal_id"] for line in _lines()]
    out.append((len(ids) == 2 and ids[0] == ids[1],
                "the same proposal twice has the same proposal_id", str(ids)))

    out.append((_schema_refuses(**{**base, "citations": []}),
                "a proposal with NO citation is refused", "citations has min_length=1"))

    wrong_page = cite["page"] + 1 if cite["page"] < 10 else cite["page"] - 1
    got = _propose(**{**base, "citations": [{"page": wrong_page, "quote": cite["quote"]}]})
    out.append((got.startswith("Rejected") and ("page %d" % cite["page"]) in got,
                "a quote on the WRONG page is refused, and the refusal names the right page", got[:140]))

    invented = {"page": cite["page"], "quote": "This sentence was written by the guard and is in no advisory."}
    got = _propose(**{**base, "citations": [invented]})
    out.append((got.startswith("Rejected") and "not in the document" in got,
                "an INVENTED quote is refused", got[:120]))

    _run_env(NEXUS_ADVISORY_ID=OTHER_ADVISORY)
    got = _propose(**base)
    out.append((got.startswith("Rejected") and OTHER_ADVISORY in got,
                "a proposal for an advisory other than the run's is refused", got[:120]))

    _run_env(NEXUS_PDF_SHA256="0" * 64)
    got = _propose(**base)
    out.append((got.startswith("Rejected") and "hash" in got,
                "a document whose hash is not the run's is refused", got[:120]))

    _run_env(NEXUS_RUN_ID=None)
    got = _propose(**base)
    out.append((got.startswith("Rejected") and "run identity" in got,
                "a server started WITHOUT a run identity refuses", got[:120]))

    _run_env()
    got = _propose(advisory_id=ADVISORY, emergent_label="Guard witness emergent technique",
                   confidence="low", citations=[cite],
                   rationale="Emergent witness: the guard proposes a label the library does not hold.")
    out.append((got.startswith("Accepted"), "an emergent proposal with a verified quote is accepted", got[:110]))

    legacy = ROOT / "data" / "proposals.jsonl"
    legacy_before = (legacy.stat().st_mtime, legacy.stat().st_size) if legacy.exists() else None
    _run_env()
    os.environ.pop("NEXUS_PROPOSALS_PATH", None)
    got = _propose(**base)
    os.environ["NEXUS_PROPOSALS_PATH"] = str(QUEUE)
    legacy_after = (legacy.stat().st_mtime, legacy.stat().st_size) if legacy.exists() else None
    out.append((got.startswith("Rejected") and "NEXUS_PROPOSALS_PATH" in got and legacy_after == legacy_before,
                "a run with NO queue path is refused, and the legacy queue is never written", got[:140]))

    stray = QUEUE_DIR / "elsewhere.jsonl"
    _run_env()
    os.environ["NEXUS_PROPOSALS_PATH"] = str(stray)
    got = _propose(**base)
    os.environ["NEXUS_PROPOSALS_PATH"] = str(QUEUE)
    out.append((got.startswith("Rejected") and "probe-contract.jsonl" in got and not stray.exists(),
                "a queue path that is not <queue dir>/<run_id>.jsonl is REFUSED, and nothing is written there",
                got[:160]))

    out.append((len(_lines()) == 3,
                "refusals wrote NOTHING to the queue",
                "%d lines; expected 3 (two identical proposals and one emergent)" % len(_lines())))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the proposal contract")
    ap.add_argument("--mutate", choices=("citations", "run", "queue"),
                    help="remove one refusal; the checks that depend on it MUST fail")
    args = ap.parse_args(argv)

    if not PDF.exists():
        print("CANNOT RUN: %s is not on this machine (data/advisories/ is gitignored).\n"
              "Nothing was checked; this is not a pass." % PDF.relative_to(ROOT))
        return 2

    if args.mutate == "citations":
        kc._refuse_citations = lambda params, run: None
        print("MUTATED: the quote and document-hash check is removed.\n")
    elif args.mutate == "run":
        kc._refuse_for_run = lambda params, run: None
        print("MUTATED: the advisory-must-match-the-run check is removed.\n")
    elif args.mutate == "queue":
        kc._refuse_queue = lambda run: None
        kc._proposals_path = lambda run: Path(run[kc.QUEUE_ENV])
        print("MUTATED: the queue path is taken from the environment again.\n")

    failures = 0
    for ok, label, detail in checks():
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
