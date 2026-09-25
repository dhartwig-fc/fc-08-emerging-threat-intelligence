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
from governance.proposals import QUEUE_DIR, load_queue_files  # noqa: E402
from governance.routing import load_routing  # noqa: E402

BUILDER = ROOT / "tools" / "build_walkthrough.py"
SECTIONS = ("question", "source", "extraction", "grounding", "review")
SEEDS = ("0", "1", "4242", "987654")
MUTATIONS = ("drop-citation", "unpinned-log", "wrong-page", "swap-notes", "wrong-count", "desk-scope", "two-runs")
MUTATION = None


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_walkthrough", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._MUTATE = MUTATION
    return mod


def _cli(*args, env=None) -> subprocess.CompletedProcess:
    extra = ["--_mutate", MUTATION] if MUTATION else []
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


def checks() -> list:
    out = []
    try:
        bw = _load_builder()
    except (FileNotFoundError, ImportError, AttributeError) as exc:
        return [(False, "the builder exists and imports", "%s: %s" % (type(exc).__name__, exc))]

    r = _cli("--check")
    out.append((r.returncode == 0, "build_walkthrough --check passes (the committed page is a fresh build)",
                (r.stdout + r.stderr).strip()[-200:]))

    page = bw.build(bw.inputs())
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
    out.append((all(n == 1 for n in counts.values()), "each of the five section ids appears exactly once",
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
            "desks": len(delivered)}
    got = {m.group(1): int(m.group(2)) for m in re.finditer(r'data-count="([a-z]+)">(\d+)<', question)}
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
