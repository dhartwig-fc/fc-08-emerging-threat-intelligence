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
    python evals/check_walkthrough.py --mutate proposal-date   # the newest-proposal date ignores the run queues; MUST fail

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
from governance.proposals import ADVISORY_LIST, LEGACY_QUEUE, QUEUE_DIR, load_queue_files  # noqa: E402
from governance.routing import load_routing  # noqa: E402
from agents.extract_advisory import SYSTEM_PROMPT  # noqa: E402
from agents.telemetry import TELEMETRY_DIR  # noqa: E402
from evals.actor_resolution import REPORT as ACTOR_REPORT  # noqa: E402
from evals.check_citations import ATTESTED_PATH  # noqa: E402
from evals.score import score_dirs  # noqa: E402
from tools.build_actor_register import load_register  # noqa: E402

REPO_BLOB = "https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence/blob/main/"
TRACE_URL = REPO_BLOB + "evals/traces/FULL_BASELINE_2026-09-12.md"
BANDS_URL = REPO_BLOB + "evals/traces/REVIEWER_BANDS_2026-09-13.md"
LABEL_PASS = ROOT / "evals" / "owner_decisions" / "label_pass_2026-09-24.json"
SERVER = "mcp_server/knowledge_centre_server.py"


def _resolver_added() -> str:
    """The first commit that put knowledge_centre_resolve_actor into the Knowledge Centre server, by date --
    read from git here because the builder may not call it."""
    r = subprocess.run(["git", "log", "--reverse", "--format=%ad", "--date=short", "-S",
                        "knowledge_centre_resolve_actor", "--", SERVER],
                       capture_output=True, text=True, cwd=ROOT)
    lines = r.stdout.split()
    return lines[0] if r.returncode == 0 and lines else "git history unavailable (%s)" % r.stderr.strip()[:80]

BUILDER = ROOT / "tools" / "build_walkthrough.py"
SECTIONS = ("question", "source", "extraction", "grounding", "review",
            "actors", "digest", "telemetry", "score", "limits")
SEEDS = ("0", "1", "4242", "987654")
MUTATIONS = ("drop-citation", "unpinned-log", "wrong-page", "swap-notes", "wrong-count", "desk-scope", "two-runs",
             "typed-score", "actor-id", "digest-header", "telemetry-count", "attested-count", "swap-moves",
             "proposal-date")
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


def checks_sections_6_to_10(bw, page: str, record: dict, pinned: list) -> list:
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
                 re.finditer(r'<li class="category" data-actor="([^"]*)">[^<]*<span class="nr">not resolvable: '
                             r'a class of actor, not a named party</span></li>', actors)]
    out.append((bool(cats) and cat_shown == cats and len(rows) + len(cats) == len(record["actors"]),
                "#actors lists every category actor in the record, in order, as not resolvable",
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
    reports = {}
    for run, pred in (("extraction", ROOT / "data" / "records"), ("reviewer", RECORDS_DIR)):
        reports[run] = score_dirs(ROOT / "evals" / "golden", pred)
        totals = reports[run]["totals"]
        for field in ("typologies", "emergent", "actors", "jurisdictions"):
            for metric in ("precision", "recall", "f1"):
                n += 1
                cell = re.search(r'data-score="%s" data-field="%s" data-m="%s">([^<]*)<' % (run, field, metric), sc)
                want_v = "%.3f" % totals[field][metric]
                if not cell or cell.group(1) != want_v:
                    wrong.append("%s/%s/%s want %s page %s" % (run, field, metric, want_v,
                                                              cell.group(1) if cell else None))
    out.append((n == 24 and not wrong, "#score's 24 precision/recall/F1 values equal score_dirs recomputed now",
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
    label_pass = json.loads(LABEL_PASS.read_text(encoding="utf-8"))["decisions"]
    sc_counts = _attrs(sc, "data-count")
    out.append((sc_counts.get("scored") == str(len(reports["extraction"]["scored"]))
                and sc_counts.get("label-decided") == str(len(label_pass))
                and "drafted and reviewed by Claude" in sc and "hand-written" not in page,
                "#score names the advisories scored and the owner-decided label entries, and says the labels are "
                "Claude's", "page %s; scored %d, label pass %d" % (sc_counts, len(reports["extraction"]["scored"]),
                                                                  len(label_pass))))

    # 10 -- limits. Every count recomputed.
    lim = section(page, "limits")
    attested = json.loads(ATTESTED_PATH.read_text(encoding="utf-8"))["attested"]
    emergent_ok = sum(1 for d in gd.latest(gd.log_prefix(manifest["decision_log"]["lines"])[2]).values()
                      if d.kind == "emergent" and d.decision == "approve")
    want_lim = {"attested": str(len(attested)),
                "attested-here": str(sum(1 for a in attested if a["advisory_id"] == bw.ADVISORY)),
                "label-decided": str(len(label_pass)),
                "label-advisories": str(len({d["advisory_id"] for d in label_pass})),
                "entity-keys": str(len(register) - empty), "register": str(len(register)),
                "emergent-approved": str(emergent_ok)}
    got_lim = _attrs(lim, "data-count")
    out.append((got_lim == want_lim, "every count in #limits equals the guard's own count from the files",
                "want %s; page %s" % (want_lim, got_lim)))
    out.append((bool(attested) and all(a.get("attested_by") == "owner" for a in attested)
                and "each attested by the owner" in lim,
                "every attested citation was attested by the owner, as #limits says",
                "attested_by values: %s" % sorted({a.get("attested_by") for a in attested})))
    newest = max(json.loads(line)["proposed_at"][:10] for q in [LEGACY_QUEUE] + sorted(QUEUE_DIR.glob("*.jsonl"))
                 for line in q.read_text(encoding="utf-8").splitlines() if line.strip())
    added = _resolver_added()
    dates = _attrs(lim, "data-date")
    out.append((dates == {"resolver-added": added, "newest-proposal": newest} and newest < added
                and "resolve_actor" not in SYSTEM_PROMPT,
                "#limits dates the resolver by git history and the newest committed proposal before it, and the "
                "extractor's prompt does not name resolve_actor",
                "git %s, newest proposal %s; page %s" % (added, newest, dates)))
    return out


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

    out += checks_sections_6_to_10(bw, page, record, pinned)

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
