"""
Build the public threat-intelligence walkthrough: one advisory, from PDF to owner-approved
typology links, rendered from the governed files and nothing else.

Usage:
    python tools/build_walkthrough.py            # write site/threat-intel/index.html
    python tools/build_walkthrough.py --check    # exit 1 when the committed page differs from a fresh build

WHAT IT READS (inputs(), once each; paths through the owning modules' constants):
  the advisory list entry          -> section 2 (title, publisher, date, URL, pages, sha256)
  the merged record                -> section 3 (typologies, who asserted each, citations)
  the typology library             -> labels and families
  the decided run's queue file     -> sections 4 and 5 (proposals, grouped into links)
  data/digests/CURRENT + manifest  -> how many decision-log lines the page may read
  the decision log, THAT prefix    -> section 5 (the owner's decisions), via log_prefix only
  the golden label                 -> the review card's context line, as the owner saw it
  the desk routing table           -> "desks reached" and the routing table's own desk total, section 1
  the actor-resolution report      -> section 6 (each named actor's resolution), over the extractor's records
  the actor register               -> section 6 (the entity_key seam) and section 10
  the Sanctions desk digest file   -> section 7 (the advisory's block only; never the file's header)
  the telemetry run's event file   -> section 8 (tool calls, permissions, the RUN_COMPLETED payload)
  the telemetry run's queue file   -> section 8 (its proposals, separate from the decided run's)
  evals/golden vs both record sets -> section 9, scored by evals.score.score_dirs at build time
  the owner-attested citations     -> section 10 (how many the matcher cannot place)
  the extractor's tools and prompt -> section 10 (whether it is asked to resolve actors)

DETERMINISTIC. No clock, no git, no PDF, no gitignored file: the same inputs give the same
bytes. A decision appended to the log after the batch was cut does not reach the page --
the page is the snapshot the current digest batch saw, and says which lines it read.

PUBLIC. Every data value is escaped. The page names advisories, runs and typologies by id;
it never names a local path, a repository data path or anyone's address (see
governance/publish_boundary.py, which evals/check_walkthrough.py runs over it).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import card  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance.digest import (APPROVED_NOT_IN_RECORD, DIGESTS_DIR, RECORDS_DIR, _in_scope,  # noqa: E402
                               _routes, _visible)
from governance.proposals import (ADVISORY_LIST, LEGACY_QUEUE, LIBRARY, QUEUE_DIR, group, link_key,  # noqa: E402
                                  load_queue_files)
from governance.routing import desks_in_order, load_routing  # noqa: E402
from agents import telemetry  # noqa: E402
from agents.extract_advisory import KC_TOOLS, SYSTEM_PROMPT  # noqa: E402
from agents.permissions import PROPOSE_TOOL, READ_ONLY_TOOLS  # noqa: E402
from evals.actor_resolution import RECORDS as EXTRACTOR_RECORDS, REPORT as ACTOR_REPORT  # noqa: E402
from evals.check_citations import ATTESTED_PATH  # noqa: E402
from evals.score import score_dirs  # noqa: E402
from tools.build_actor_register import load_register  # noqa: E402

OUT = ROOT / "site" / "threat-intel" / "index.html"
ADVISORY = "ADV-2026-0013"
DECIDED_RUN = "adv-2026-0013-extractor-f617bd3b00"
TELEMETRY_RUN = "adv-2026-0013-extractor-69eeab7b41"
GOLDEN_DIR = ROOT / "evals" / "golden"
DIGEST_DESK = "sanctions_desk"
RESOLVER = "knowledge_centre_resolve_actor"
# The day the resolver tool entered the Knowledge Centre (commit 891b2b0). The builder may not call git;
# evals/check_walkthrough.py holds this date against the repository history.
RESOLVER_ADDED = "2026-09-25"
LABEL_PASS = ROOT / "evals" / "owner_decisions" / "label_pass_2026-09-24.json"
LABEL_PROVENANCE = "Claude-drafted, Claude-reviewed"
REPO_BLOB = "https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence/blob/main/"
TRACE = "evals/traces/FULL_BASELINE_2026-09-12.md"
TRACE_URL = REPO_BLOB + TRACE
BANDS_TRACE = "evals/traces/REVIEWER_BANDS_2026-09-13.md"
BANDS_URL = REPO_BLOB + BANDS_TRACE
SCORE_FIELDS = (("typologies", "Typologies (library)"), ("emergent", "Emergent typologies"),
                ("actors", "Actors"), ("jurisdictions", "Jurisdictions"))
_MUTATE = None  # set only by evals/check_walkthrough.py through --_mutate
MUTATIONS = ("drop-citation", "unpinned-log", "wrong-page", "swap-notes", "wrong-count", "desk-scope", "two-runs",
             "typed-score", "actor-id", "digest-header", "telemetry-count", "attested-count", "swap-moves",
             "proposal-date", "desk-total")

e = html.escape
PAST = {"approve": "approved", "reject": "rejected"}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class _RunId:
    """The one attribute telemetry.telemetry_path reads, so the path comes from its owner."""
    def __init__(self, run_id: str):
        self.run_id = run_id


def inputs(log: Path = gd.LOG) -> dict:
    """Every input the page is built from, loaded once. Refuses inputs that disagree with each other."""
    advisories = {a["advisory_id"]: a for a in _json(ADVISORY_LIST)["advisories"]}
    advisory = advisories[ADVISORY]
    if not advisory.get("url", "").startswith(("http://", "https://")):
        raise ValueError("the advisory URL %r is not http(s); a public page links nothing else" % advisory.get("url"))
    record = _json(RECORDS_DIR / ("%s.json" % ADVISORY))
    library = {t["typology_id"]: t for t in _json(LIBRARY)["typologies"]}

    proposals, skipped = load_queue_files([QUEUE_DIR / ("%s.jsonl" % DECIDED_RUN)])
    if skipped:
        raise ValueError("the decided run's queue has unreadable lines: %s" % "; ".join(skipped))

    batch = (DIGESTS_DIR / "CURRENT").read_text(encoding="utf-8").strip()
    pinned = _json(DIGESTS_DIR / batch / "manifest.json")["decision_log"]
    if _MUTATE == "unpinned-log":
        lines, sha, decisions = gd.log_prefix(None, log)
    else:
        lines, sha, decisions = gd.log_prefix(pinned["lines"], log)
        if sha != pinned["sha256"]:
            raise ValueError("the first %d lines of the decision log no longer hash to what batch %s pinned: "
                             "the log was rewritten" % (lines, batch))

    # "Every citation below is pinned to that hash" is a claim; make it true by construction.
    doc = advisory["sha256"]
    if record["source"]["document_sha256"] != doc:
        raise ValueError("the record's document hash is not the advisory list's")
    stray = sorted({p.proposal_id for p in proposals if p.document_sha256 != doc or p.advisory_id != ADVISORY})
    if stray:
        raise ValueError("proposals not about this document: %s" % ", ".join(stray))

    golden = _json(GOLDEN_DIR / ("%s.json" % ADVISORY))
    routing = load_routing()

    # Section 6. The resolution report reads the EXTRACTOR's records; the page's record is the merged
    # one. Say so only because it is true: the two must carry the same actors for this advisory.
    resolution = _json(ACTOR_REPORT)
    actor_rows = [r for r in resolution["actors"] if r["advisory_id"] == ADVISORY]
    suggestions = {s["name"]: s["suggestions"] for s in resolution["suggestions"] if s["advisory_id"] == ADVISORY}
    if _json(EXTRACTOR_RECORDS / ("%s.json" % ADVISORY))["actors"] != record["actors"]:
        raise ValueError("the merged record's actors are not the extractor record's; section 6 says they are")
    categories = [a for a in record["actors"] if a.get("actor_type") == "category"]
    if [r["name"] for r in actor_rows] != [a["name"] for a in record["actors"] if a.get("actor_type") != "category"]:
        raise ValueError("the actor-resolution report's rows are not this record's named actors: re-run "
                         "evals/actor_resolution.py")
    register = load_register()
    if any(a.get("entity_key") is not None for a in register):
        raise ValueError("a register entry now carries an entity_key; sections 6 and 10 say none does")

    # Section 7: the advisory's block of the desk file, cut below the file's header.
    desk_text = (DIGESTS_DIR / batch / ("%s.md" % DIGEST_DESK)).read_text(encoding="utf-8")
    m = re.search(r"^## %s -- .*?(?=^## |\Z)" % re.escape(ADVISORY), desk_text, re.S | re.M)
    if not m:
        raise ValueError("batch %s's %s file has no %s block" % (batch, DIGEST_DESK, ADVISORY))
    digest_block = (desk_text[:m.end()] if _MUTATE == "digest-header" else m.group(0)).rstrip("\n")

    # Section 8: the run with telemetry, which is not the decided run.
    events = [json.loads(line) for line in telemetry.telemetry_path(_RunId(TELEMETRY_RUN))
              .read_text(encoding="utf-8").splitlines() if line.strip()]
    started = [ev for ev in events if ev["stage"] == telemetry.RUN_STARTED]
    completed = [ev for ev in events if ev["stage"] == telemetry.RUN_COMPLETED]
    if len(started) != 1 or len(completed) != 1:
        raise ValueError("run %s's telemetry does not hold exactly one start and one completion" % TELEMETRY_RUN)
    if started[0]["payload"].get("pdf_sha256") != doc or started[0]["payload"].get("run_id") != TELEMETRY_RUN:
        raise ValueError("run %s's telemetry is not about this document" % TELEMETRY_RUN)
    tel_proposals, skipped = load_queue_files([QUEUE_DIR / ("%s.jsonl" % TELEMETRY_RUN)])
    if skipped or any(p.document_sha256 != doc or p.advisory_id != ADVISORY for p in tel_proposals):
        raise ValueError("run %s's queue is unreadable or not about this document" % TELEMETRY_RUN)
    # "Neither the decided run nor the record's extraction: three extractions" -- true only while the
    # telemetry run proposed a different typology set from the one the record's extractor asserted.
    record_ext = {t["typology_id"] for t in record["typologies"]
                  if t.get("typology_id") and t.get("added_by") in (None, "extractor")}
    if {p.typology_id for p in tel_proposals if p.typology_id} == record_ext:
        raise ValueError("run %s proposed exactly the record's extractor typologies; section 8 says it is a "
                         "different extraction" % TELEMETRY_RUN)
    tel_runs = sorted(f.stem for f in telemetry.TELEMETRY_DIR.glob("%s-*.jsonl" % ADVISORY.lower()))
    if TELEMETRY_RUN not in tel_runs or DECIDED_RUN in tel_runs:
        raise ValueError("section 8 says %s has telemetry and the decided run has none; the directory holds %s"
                         % (TELEMETRY_RUN, tel_runs))

    # Section 10: "the extractor is not asked to resolve actors" must stay true to be said -- the
    # substring, so any spelling of the tool in the prompt counts as asking.
    if "resolve_actor" in SYSTEM_PROMPT:
        raise ValueError("the extractor's prompt now names resolve_actor; section 10 says it does not")
    # "No committed extraction had the resolver": every committed queue's newest proposal predates it.
    queues = [LEGACY_QUEUE] + sorted(QUEUE_DIR.glob("*.jsonl"))
    if _MUTATE == "proposal-date":
        queues = [LEGACY_QUEUE]
    newest = max(json.loads(line)["proposed_at"][:10] for q in queues
                 for line in q.read_text(encoding="utf-8").splitlines() if line.strip())
    if newest >= RESOLVER_ADDED:
        raise ValueError("a committed proposal is dated %s, on or after the resolver's %s; section 10 says no "
                         "committed extraction had it" % (newest, RESOLVER_ADDED))

    # Sections 5, 9, 10: the golden labels are Claude's, with the owner's decisions on the disputed entries.
    label_pass = _json(LABEL_PASS)["decisions"]
    unlabelled = sorted(a["advisory_id"] for a in advisories.values()
                        if LABEL_PROVENANCE not in a.get("label_status", ""))
    if unlabelled:
        raise ValueError("label_status does not say %r for %s" % (LABEL_PROVENANCE, ", ".join(unlabelled)))
    listed = sum(int(m.group(1)) for a in advisories.values()
                 for m in [re.search(r"on (\d+) disputed entr", a.get("label_status", ""))] if m)
    if listed != len(label_pass):
        raise ValueError("the advisory list counts %d owner-decided disputed entries; the label pass holds %d"
                         % (listed, len(label_pass)))

    attested = _json(ATTESTED_PATH)["attested"]
    if any(a.get("attested_by") != "owner" for a in attested):
        raise ValueError("an attested citation was not attested by the owner; section 10 says each was")

    return {
        "advisory": advisory,
        "advisories": advisories,
        "record": record,
        "library": library,
        "proposals": proposals,
        "links": group(proposals),
        "batch": batch,
        "log_lines": lines,
        "log_sha256": sha,
        "decisions": [d for d in decisions if d.advisory_id == ADVISORY],
        "golden_ids": {t["typology_id"] for t in golden["typologies"] if t.get("typology_id")},
        "routing": routing,
        "desks": _routes(record, gd.latest(decisions), library, routing),
        "all_decisions": decisions,
        "actor_rows": actor_rows,
        "suggestions": suggestions,
        "categories": categories,
        "register": register,
        "digest_block": digest_block,
        "events": events,
        "run_started": started[0]["payload"],
        "run_completed": completed[0]["payload"],
        "tel_proposals": tel_proposals,
        "scores": {"extraction": score_dirs(GOLDEN_DIR, EXTRACTOR_RECORDS), "reviewer": score_dirs(GOLDEN_DIR, RECORDS_DIR)},
        "attested": attested,
        "resolver_available": RESOLVER in KC_TOOLS,
        "newest_proposal": newest,
        "tel_runs": tel_runs,
        "label_pass": label_pass,
    }


# ---------------------------------------------------------------- helpers

def _plural(n: int, word: str, many: str = "") -> str:
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


def _asserted_by(t: dict) -> str:
    return "extractor" if t.get("added_by") in (None, "extractor") else "reviewer"


def _name(t: dict, library: dict) -> tuple:
    """(id shown, label, family) -- the library is the governed source for a governed typology."""
    tid = t.get("typology_id")
    if tid:
        lib = library.get(tid, {})
        return tid, lib.get("label", t.get("label", "?")), lib.get("family", t.get("family", "?"))
    return "emergent", t.get("label", "?"), t.get("family", "?")


def _key(t: dict) -> str:
    return link_key(ADVISORY, t.get("typology_id"), None if t.get("typology_id") else t.get("label"))


def _cites(citations) -> str:
    bump = 1 if _MUTATE == "wrong-page" else 0
    return "".join('<div class="cite"><span class="pg">p%d</span><blockquote>%s</blockquote></div>'
                   % (int(pg) + bump, e(q)) for pg, q in citations)


def _standing(inp: dict) -> dict:
    return gd.latest(inp["decisions"])


def _ids(ids) -> str:
    return ", ".join(e(i) for i in ids)


def desk_view(inp: dict) -> list:
    """[(desk, title, approved ids, awaiting ids)] per desk the advisory reaches, by the digest's own
    rule: approvals in the desk's scope (governed, then emergent labels), and record typologies in scope
    with no standing decision. Mirrors governance.digest.render_desk's selection; the guard holds it
    against the committed desk files."""
    library, routing, rec = inp["library"], inp["routing"], inp["record"]
    mine = list(_standing(inp).values())
    decided = {d.link_key for d in mine}
    out = []
    for desk, reasons in inp["desks"].items():
        def scope(tid):
            return True if _MUTATE == "desk-scope" else _in_scope(tid, desk, reasons, library, routing)
        approved = sorted(d.typology_id for d in mine if _visible(d) and d.kind == "governed" and scope(d.typology_id))
        approved += sorted(d.emergent_label for d in mine if _visible(d) and d.kind == "emergent")
        awaiting = sorted({t["typology_id"] for t in rec["typologies"]
                           if t.get("typology_id") and link_key(ADVISORY, t["typology_id"], None) not in decided
                           and scope(t["typology_id"])})
        out.append((desk, inp["routing"]["desk_titles"].get(desk, desk), approved, awaiting))
    return out


def two_extractions(inp: dict) -> dict:
    """Set differences between the record's typologies and the decided run's proposals (governed ids)."""
    rec = [t for t in inp["record"]["typologies"] if t.get("typology_id")]
    ext = {t["typology_id"] for t in rec if _asserted_by(t) == "extractor"}
    rev = {t["typology_id"] for t in rec if _asserted_by(t) == "reviewer"}
    run = {p.typology_id for p in inp["proposals"] if p.typology_id}
    record_only = (ext | rev) - run if _MUTATE == "two-runs" else ext - run
    return {"record-only": sorted(record_only), "run-only": sorted(run - ext - rev),
            "run-reviewer": sorted(run & rev), "both": sorted(run & ext)}


# ---------------------------------------------------------------- sections

def _count(name: str, n: int, word: str = "", many: str = "") -> str:
    tail = (" " + (word if n == 1 else (many or word + "s"))) if word else ""
    return '<span class="count" data-count="%s">%d</span>%s' % (name, n, tail)


def section_question(inp: dict) -> str:
    a, rec = inp["advisory"], inp["record"]
    typs = rec["typologies"]
    n_ext = sum(1 for t in typs if _asserted_by(t) == "extractor")
    n_emergent = sum(1 for t in typs if not t.get("typology_id"))
    standing = _standing(inp)
    n_app = sum(1 for d in standing.values() if d.decision == "approve")
    n_rej = sum(1 for d in standing.values() if d.decision == "reject")
    if _MUTATE == "wrong-count":
        n_ext += 1
    desks = desk_view(inp)
    n_desks_total = len(desks_in_order(inp["routing"]))
    if _MUTATE == "desk-total":
        n_desks_total += 1
    rows = "".join(
        '\n        <li class="desk">%s: %d approved%s; %d awaiting review%s</li>'
        % (e(title), len(app), (" (%s)" % _ids(app)) if app else "", len(wait), (" (%s)" % _ids(wait)) if wait else "")
        for _, title, app, wait in desks)
    return """<section id="question">
  <h2><span class="n">01</span> The question</h2>
  <ol class="chain">
    <li><span class="step">Question</span>
      <p>What does <strong>%s</strong> (%s, %s) tell a financial-crime team to look for, and which desks need to hear it?</p></li>
    <li><span class="step">Capability</span>
      <p>An extraction agent reads the advisory and writes a governed record: every typology it asserts carries a page number and a verbatim quote from a document pinned by its sha256. The agent's only write is <code>propose_link</code>, which will not record a proposal whose quote it cannot find on the cited page. A second, reviewer agent adds what the extractor missed, each addition with its justification; the owner decides each proposed link at a review gate; every decision is a dated line in an append-only log.</p></li>
    <li><span class="step">Intelligence produced</span>
      <p>%s asserted in the record &mdash; %s by the extractor, %s added by the reviewer agent, %s of them emergent (not in the typology library). Run <code>%s</code> made %s; the owner approved %s and rejected %s.</p></li>
    <li><span class="step">Investigator outcome</span>
      <p>The routing table has %s; this advisory reached %s. What each desk's digest carries for it:</p>
      <ul class="desks">%s
      </ul></li>
  </ol>
</section>
""" % (e(a["title"]), e(a["publisher"]), e(a["published_on"]),
       _count("typologies", len(typs), "typology", "typologies"), _count("extractor", n_ext), _count("reviewer", len(typs) - n_ext),
       _count("emergent", n_emergent), e(DECIDED_RUN), _count("proposals", len(inp["proposals"]), "proposal"),
       _count("approved", n_app, "link"), _count("rejected", n_rej), _count("desk-total", n_desks_total, "desk"),
       _count("desks", len(desks), "desk"), rows)


def section_source(inp: dict) -> str:
    a = inp["advisory"]
    return """<section id="source">
  <h2><span class="n">02</span> The source</h2>
  <dl class="facts">
    <dt>Title</dt><dd>%s</dd>
    <dt>Publisher</dt><dd>%s</dd>
    <dt>Published</dt><dd>%s</dd>
    <dt>Document</dt><dd><a href="%s" rel="noopener">%s</a></dd>
    <dt>Pages</dt><dd>%d</dd>
    <dt>sha256</dt><dd class="hash">%s</dd>
  </dl>
  <p>Every citation below is pinned to this hash: a page number and a quote name a place in exactly this document, and the build refuses a record or proposal that names any other.</p>
</section>
""" % (e(a["title"]), e(a["publisher"]), e(a["published_on"]), e(a["url"], quote=True), e(a["url"]),
       int(a["pages"]), e(a["sha256"]))


def section_extraction(inp: dict) -> str:
    rec, library = inp["record"], inp["library"]
    standing = _standing(inp)
    rows = []
    for t in rec["typologies"]:
        tid, label, family = _name(t, library)
        d = standing.get(_key(t))
        status = ("%s %s" % (PAST[d.decision], d.decided_at[:10])) if d else "awaiting review"
        cites = [(c["page"], c["quote"]) for c in t["citations"]]
        if _MUTATE == "drop-citation":
            cites = cites[:-1]
        why = ""
        if _asserted_by(t) == "reviewer" and t.get("review_justification"):
            why = ('<details class="why"><summary>Reviewer&rsquo;s justification</summary><p>%s</p></details>'
                   % e(t["review_justification"]))
        rows.append("""    <tr>
      <td data-h="Typology"><code>%s</code> %s</td>
      <td data-h="Family">%s</td>
      <td data-h="Asserted by">%s</td>
      <td data-h="Owner">%s</td>
      <td data-h="Citations">%s%s</td>
    </tr>""" % (e(tid), e(label), e(family), e(_asserted_by(t)), e(status), _cites(cites), why))
    s = two_extractions(inp)
    dates = sorted({p.proposed_at[:10] for p in inp["proposals"]})

    def span(name: str) -> str:
        return '<span class="ids" data-set="%s">%s</span>' % (name, _ids(s[name]) or "none")
    return """<section id="extraction">
  <h2><span class="n">03</span> What the record asserts</h2>
  <p>The merged record for %s: %s, each with the quotes that ground it. &ldquo;Owner&rdquo; is the standing decision in the pinned decision log; a typology with none is awaiting review.</p>
  <table class="rows">
    <thead><tr><th>Typology</th><th>Family</th><th>Asserted by</th><th>Owner</th><th>Citations</th></tr></thead>
    <tbody>
%s
    </tbody>
  </table>
  <p class="flag">The record and the decided proposals come from two separate extractions of this document. Both assert %s. The record&rsquo;s extractor also asserted %s, which run <code>%s</code> (proposals written %s) did not propose; that run proposed %s, which the record lacks, and %s, which the record carries only as a reviewer addition. The owner decides links, on the quotes shown in section 5.</p>
</section>
""" % (e(ADVISORY), _plural(len(rec["typologies"]), "typology", "typologies"), "\n".join(rows),
       span("both"), span("record-only"), e(DECIDED_RUN), e(", ".join(dates)), span("run-only"), span("run-reviewer"))


def section_grounding(inp: dict) -> str:
    library = inp["library"]
    items = []
    for p in inp["proposals"]:
        label = library.get(p.typology_id, {}).get("label", "?") if p.typology_id else p.emergent_label
        items.append("""    <li class="proposal">
      <div class="ph"><code>%s</code> %s <span class="conf">confidence %s</span></div>
      %s
    </li>""" % (e(p.typology_id or "emergent"), e(label), e(p.confidence), _cites(p.citations)))
    return """<section id="grounding">
  <h2><span class="n">04</span> Grounding: the proposals</h2>
  <p>Run <code>%s</code> made %s. Each quote was located on its cited page of the pinned document by <code>propose_link</code> before the proposal was written &mdash; that is the tool&rsquo;s contract, and a quote it cannot place is refused, never queued. This page is built without the PDF and does not re-check them.</p>
  <ol class="props">
%s
  </ol>
</section>
""" % (e(DECIDED_RUN), _plural(len(inp["proposals"]), "proposal"), "\n".join(items))


SEPARATOR = "=" * 100


def _card(inp: dict, link) -> str:
    """The review gate's own card, minus its terminal separator. Raises if the card's shape moved."""
    text = card.render(link, None, inp["advisories"], inp["library"], inp["golden_ids"])
    first, _, rest = text.partition("\n")
    if first != SEPARATOR:
        raise ValueError("governance.card.render no longer opens with its separator line; re-read the card "
                         "before trimming it")
    return rest


def _decision_li(d, prefix: str = "") -> str:
    return ('\n      <li class="decision">%s<time>%s</time> <b class="%s">%s</b> <span class="note">%s</span></li>'
            % (prefix, e(d.decided_at[:10]), e(d.decision), e(d.decision.upper()), e(d.note or "(no note)")))


def _label_here(inp: dict) -> str:
    n = sum(1 for d in inp["label_pass"] if d["advisory_id"] == ADVISORY)
    if not n:
        if "awaiting owner review" not in inp["advisory"].get("label_status", ""):
            raise ValueError("%s's label_status no longer says it awaits owner review" % ADVISORY)
        return "the owner has not yet reviewed it"
    return "the owner has decided its %s, not yet the rest" % _plural(n, "disputed entry", "disputed entries")


def section_review(inp: dict) -> str:
    rec_ids = {t.get("typology_id") for t in inp["record"]["typologies"] if t.get("typology_id")}
    by_link = {}
    for d in inp["decisions"]:
        by_link.setdefault(d.link_key, []).append(d)
    keys = list(inp["links"])
    if _MUTATE == "swap-notes":
        by_link = {keys[i]: by_link.get(keys[(i + 1) % len(keys)], []) for i in range(len(keys))}
    blocks = []
    for key, link in inp["links"].items():
        text = _card(inp, link)
        lines = "".join(_decision_li(d) for d in by_link.get(key, []))
        flag = ""
        if link.typology_id and link.typology_id not in rec_ids:
            reached = [inp["routing"]["desk_titles"].get(desk, desk) for desk, reasons in inp["desks"].items()
                       if any(r.startswith(link.typology_id + " ") and APPROVED_NOT_IN_RECORD in r for r in reasons)]
            routed = (" The digest still routes it, to the %s, marked &ldquo;%s&rdquo;."
                      % (e(", ".join(reached)), e(APPROVED_NOT_IN_RECORD))) if reached else ""
            flag = ('\n    <p class="flag"><code>%s</code> is not in the merged record: it reached the owner as this '
                    "run&rsquo;s proposal, not through the record.%s</p>" % (e(link.typology_id), routed))
        blocks.append("""  <article class="link">
    <pre>%s</pre>%s
    <ul class="decisions">%s
    </ul>
  </article>""" % (e(text), flag, lines or '\n      <li class="undecided">no decision in the pinned prefix</li>'))
    shown = set(inp["links"])
    others = [d for d in inp["decisions"] if d.link_key not in shown]
    tail = ""
    if others:
        tail = """
  <article class="link">
    <p>Decisions on %s for links this run did not propose:</p>
    <ul class="decisions">%s
    </ul>
  </article>""" % (e(ADVISORY), "".join(_decision_li(d, "<code>%s</code> " % e(d.typology_id or d.emergent_label))
                                        for d in others))
    return """<section id="review">
  <h2><span class="n">05</span> Review: what the owner saw, and decided</h2>
  <p>The decisions shown are the first %s of the owner&rsquo;s decision log &mdash; the lines digest batch <code>%s</code> was built from (sha256 <span class="hash">%s</span>); %s of them decide %s.</p>
  <p>Each card is rendered by the review gate&rsquo;s own card renderer from run <code>%s</code>&rsquo;s queue, without the terminal&rsquo;s separator line, and followed by the owner&rsquo;s decision. &ldquo;Golden label HOLDS&rdquo; or &ldquo;LACKS&rdquo; on a card refers to this advisory&rsquo;s reference answer (its golden label), drafted and reviewed by Claude; %s. It was shown to the owner as context only, never a rule.</p>
%s%s
</section>
""" % (_plural(inp["log_lines"], "line"), e(inp["batch"]), e(inp["log_sha256"]), len(inp["decisions"]),
       e(ADVISORY), e(DECIDED_RUN), _label_here(inp), "\n".join(blocks), tail)


def section_actors(inp: dict) -> str:
    rec, rows, cats, register = inp["record"], inp["actor_rows"], inp["categories"], inp["register"]
    by_name = {a["name"]: a for a in rec["actors"]}
    trs = []
    for r in rows:
        a = by_name[r["name"]]
        act = r["actor_id"] or ""
        if r["status"] == "resolved":
            if _MUTATE == "actor-id":
                act = ""
                res = "resolved, matched as &ldquo;%s&rdquo;" % e(r["matched"])
            else:
                res = "resolved to <code>%s</code>, matched as &ldquo;%s&rdquo;" % (e(act), e(r["matched"]))
        elif r["status"] == "ambiguous":
            res = "ambiguous: matches %s; the resolver does not choose" % _ids(r["entries"])
        else:
            sug = inp["suggestions"].get(r["name"], [])
            res = "unresolved: no register entry matches it; " + (
                "suggested, not confirmed: %s" % ", ".join("<code>%s</code> %s" % (e(x["actor_id"]), e(x["name"]))
                                                         for x in sug) if sug else "no suggestion")
        trs.append("""    <tr class="actor" data-actor="%s" data-status="%s" data-act="%s" data-entries="%s">
      <td data-h="Actor">%s<span class="role">%s</span></td>
      <td data-h="Resolution">%s</td>
    </tr>""" % (e(r["name"]), e(r["status"]), e(act), e(",".join(r["entries"])), e(r["name"]),
                e(a.get("role") or ""), res))
    publishers = {t.strip() for t in inp["advisory"]["publisher"].split("/")}
    unresolved = [r["name"] for r in rows if r["status"] == "unresolved"]
    own = [n for n in unresolved if ({n} | set(by_name[n].get("aliases", []))) & publishers]
    rest = [n for n in unresolved if n not in own]
    own_html = ", ".join('<span class="who" data-publisher="%s">%s</span>' % (e(n), e(n)) for n in own)
    note = ""
    if own:
        note = ("<p>%s of the %s named actors that do not resolve are the note&rsquo;s own publishers &mdash; %s. "
                "The extractor recorded the note&rsquo;s issuers as actors; the register, built from the parties "
                "the reference labels name, has no entry for them.%s</p>"
                % (len(own), len(unresolved), own_html,
                   (" %s %s unresolved too, with no register entry to match." % (e(", ".join(rest)),
                                                                                "is" if len(rest) == 1 else "are"))
                   if rest else ""))
    lis = "".join('\n    <li class="category" data-actor="%s">%s <span class="nr">not resolvable: a class of actor, '
                  'not a named party</span></li>' % (e(a["name"]), e(a["name"])) for a in cats)
    empty = sum(1 for a in register if a.get("entity_key") is None)
    return """<section id="actors">
  <h2><span class="n">06</span> Actors: who the advisory names</h2>
  <p>The record names %s: %s and %s. The reviewer agent added none &mdash; these are the extractor&rsquo;s. Each named actor is looked up in the actor register: %s built from the parties the reference labels name, each with an <code>ACT-</code> id. The lookup shown is the actor-resolution evaluation&rsquo;s, run over the extractor&rsquo;s committed records after extraction (section 10 says why).</p>
  <table class="rows two">
    <thead><tr><th>Actor</th><th>Resolution</th></tr></thead>
    <tbody>
%s
    </tbody>
  </table>
  %s
  <p>The record&rsquo;s categories are classes of actor, never looked up:</p>
  <ul class="cats">%s
  </ul>
  <dl class="facts">
    <dt>entity_key</dt><dd data-entity-key="empty" data-empty="%d" data-of="%d">empty, on all %d register entries</dd>
  </dl>
  <p>The <code>entity_key</code> is the seam where a register entry would link to the platform&rsquo;s resolved-entity estate. It is left empty on purpose: that estate is synthetic demonstration data, and a real designation will never name a synthetic party. A link waits for a real substrate.</p>
</section>
""" % (_plural(len(rec["actors"]), "actor"), _plural(len(rows), "named actor"), _plural(len(cats), "category", "categories"),
       _plural(len(register), "entry", "entries"), "\n".join(trs), note, lis, empty, len(register), len(register))


def section_digest(inp: dict) -> str:
    title = inp["routing"]["desk_titles"].get(DIGEST_DESK, DIGEST_DESK)
    if DIGEST_DESK not in inp["desks"]:
        raise ValueError("%s does not reach the %s; section 7 shows its entry there" % (ADVISORY, title))
    return """<section id="digest">
  <h2><span class="n">07</span> What a desk&rsquo;s digest carries</h2>
  <p>The advisory reached %s (section 1). This is the %s&rsquo;s entry for it, exactly as written in digest batch <code data-batch="%s">%s</code>, which was built from the first <span data-count="digest-log-lines">%d</span> lines of the decision log &mdash; the same lines section 5 reads. It is markdown, shown as written; &ldquo;asserted by the pipeline&rdquo; means in the record, awaiting the owner.</p>
  <pre class="digest">%s</pre>
</section>
""" % (_plural(len(inp["desks"]), "desk"), e(title), e(inp["batch"]), e(inp["batch"]), inp["log_lines"],
       e(inp["digest_block"]))


STATUS_ORDER = (telemetry.SUCCESS, telemetry.REFUSED, telemetry.FAILURE)
STATUS_SHOWN = {telemetry.SUCCESS: "Succeeded", telemetry.REFUSED: "Refused", telemetry.FAILURE: "Failed"}


def _short(tool: str) -> str:
    return tool.split("__")[-1]


def _first_line(text: str, width: int = 110) -> str:
    line = (text or "").splitlines()[0] if text else ""
    return line if len(line) <= width else line[:width].rstrip() + "…"


def section_telemetry(inp: dict) -> str:
    events, s0, done = inp["events"], inp["run_started"], inp["run_completed"]
    calls = [ev for ev in events if ev["stage"] == telemetry.TOOL_CALL]
    if _MUTATE == "telemetry-count":
        calls = [ev for ev in calls if ev["status"] != telemetry.FAILURE]
    statuses = list(STATUS_ORDER) + sorted({ev["status"] for ev in calls} - set(STATUS_ORDER))
    tools = sorted({ev["payload"]["tool"] for ev in calls}, key=lambda t: (_short(t), t))
    count = {}
    for ev in calls:
        k = (ev["payload"]["tool"], ev["status"])
        count[k] = count.get(k, 0) + 1
    head = "".join("<th>%s</th>" % e(STATUS_SHOWN.get(st, st)) for st in statuses)
    body = "\n".join("    <tr><td data-h=\"Tool\"><code>%s</code></td>%s</tr>" % (
        e(_short(t)), "".join('<td data-h="%s" data-tool="%s" data-status="%s">%d</td>'
                              % (e(STATUS_SHOWN.get(st, st)), e(t), e(st), count.get((t, st), 0)) for st in statuses)) for t in tools)
    perm = {st: [ev for ev in events if ev["stage"] == st]
            for st in (telemetry.PERMISSION_ALLOWED, telemetry.PERMISSION_DENIED)}
    perm_tools = sorted({ev["payload"].get("tool") for evs in perm.values() for ev in evs})
    pre = ""
    if not set(perm_tools) & set(READ_ONLY_TOOLS):
        pre = " The read-only lookup tools are pre-approved and never reach the check."
    about = ""
    if perm_tools:
        about = " Every decision concerns %s%s." % (", ".join("<code>%s</code>" % e(_short(t)) for t in perm_tools),
                                                    ", the agent&rsquo;s one write" if perm_tools == [PROPOSE_TOOL] else "")
    failed = [ev for ev in calls if ev["status"] == telemetry.FAILURE]
    fails = ""
    if failed:
        fails = ("\n  <p>%s failed. The error each logged, first line:</p>\n  <ul class=\"fails\">%s\n  </ul>"
                 % (_plural(len(failed), "call"), "".join(
                     '\n    <li><code>%s</code> <span class="err">%s</span></li>'
                     % (e(_short(ev["payload"]["tool"])), e(_first_line(ev["payload"].get("outcome", ""))))
                     for ev in failed)))

    def rc(key: str, shown: str) -> str:
        return '<dd data-rc="%s" data-raw="%s">%s</dd>' % (key, e(json.dumps(done[key])), e(shown))
    facts = "\n    ".join([
        "<dt>Turns</dt>" + rc("turns", "%d of at most %d" % (done["turns"], s0["max_turns"])),
        "<dt>Duration</dt>" + rc("duration_ms", "%.1f seconds" % (done["duration_ms"] / 1000)),
        "<dt>SDK cost estimate</dt>" + rc("cost_usd", "US$%.2f at API prices, as computed by the agent SDK; "
                                           "not a bill" % done["cost_usd"]),
        "<dt>The run&rsquo;s own record validated</dt>" + rc("validated", "yes" if done["validated"] else "no")])

    # Its proposals: separate from the decided run's. Say, per link, what the pinned log decided.
    tel = inp["tel_proposals"]
    pinned = inp["decisions"]
    cited = {pid for d in pinned for pid in d.proposal_ids}
    standing = _standing(inp)

    def name(p):
        return p.typology_id or p.emergent_label
    decided = sorted(name(p) for p in tel if p.link_key in standing)
    undecided = sorted(name(p) for p in tel if p.link_key not in standing)
    by_runs = sorted({r for p in tel if p.link_key in standing for r in standing[p.link_key].run_ids})
    verdicts = sorted({PAST[standing[p.link_key].decision] for p in tel if p.link_key in standing})
    n_cited = sum(1 for p in tel if p.proposal_id in cited)
    n_propose = sum(count.get((t, telemetry.SUCCESS), 0) for t in tools if t == PROPOSE_TOOL)
    match = ("Its %s successful <code>%s</code> calls match the %s in its queue"
             % (n_propose, e(_short(PROPOSE_TOOL)), _plural(len(tel), "proposal"))) if n_propose == len(tel) else (
        "Its queue holds %s against %d successful <code>%s</code> calls"
        % (_plural(len(tel), "proposal"), n_propose, e(_short(PROPOSE_TOOL))))
    if decided:
        decided_line = ('Of the links they name, <span class="ids" data-set="tel-decided-elsewhere">%s</span> were decided '
                        "on proposals from run %s (%s); " % (_ids(decided), ", ".join("<code>%s</code>" % e(r) for r in by_runs),
                                                            "all " + verdicts[0] if len(verdicts) == 1 else ", ".join(verdicts)))
    else:
        decided_line = ('Of the links they name, <span class="ids" data-set="tel-decided-elsewhere">none</span> is '
                        "decided; ")
    sdk = ""
    if any(_short(t) == "StructuredOutput" for t in tools):
        sdk = (" <code>StructuredOutput</code> is the agent SDK&rsquo;s tool for handing in the finished record. "
               "&ldquo;Refused&rdquo; would mean a tool declined the call under its own rules, as "
               "<code>%s</code> does with a quote it cannot place; &ldquo;failed&rdquo; means the call raised an error."
               % e(_short(PROPOSE_TOOL)))
    return """<section id="telemetry">
  <h2><span class="n">08</span> Telemetry: what the agent did</h2>
  <p>Every tool call and permission decision in an extraction run has been logged since telemetry was added. <span class="count" data-count="tel-runs">%d</span> %s of this advisory %s telemetry: <code>%s</code> (%s, started %s), with <span class="count" data-count="events">%d</span> events. The decided run, <code>%s</code>, has none.</p>
  <table class="rows tel">
    <thead><tr><th>Tool call</th>%s</tr></thead>
    <tbody>
%s
    </tbody>
  </table>
  <p>%s</p>%s
  <p>Permission decisions: <span data-perm="%s">%d</span> allowed, <span data-perm="%s">%d</span> denied.%s%s</p>
  <dl class="facts">
    %s
  </dl>
  <p class="flag">Run <code>%s</code> is neither the run the owner decided (<code>%s</code>, sections 4 and 5) nor the extraction the record carries (section 3): this advisory has three extractions. %s: <span class="ids" data-set="tel-proposed">%s</span>. They are separate from the decided run&rsquo;s proposals: <span data-count="tel-cited">%d</span> of them %s cited by any decision in the pinned log, so as proposals they remain undecided. %s%s</p>
</section>
""" % (len(inp["tel_runs"]), "run" if len(inp["tel_runs"]) == 1 else "runs", "has" if len(inp["tel_runs"]) == 1 else "have",
       ", ".join(e(r) for r in inp["tel_runs"]), e(s0.get("model", "?")), e(events[0]["timestamp"][:10]), len(events),
       e(DECIDED_RUN), head, body,
       sdk.strip(), fails,
       telemetry.PERMISSION_ALLOWED, len(perm[telemetry.PERMISSION_ALLOWED]), telemetry.PERMISSION_DENIED,
       len(perm[telemetry.PERMISSION_DENIED]), about, pre, facts, e(TELEMETRY_RUN), e(DECIDED_RUN), match,
       _ids(sorted(name(p) for p in tel)), n_cited, "is" if n_cited == 1 else "are", decided_line,
       ('<span class="ids" data-set="tel-no-decision">%s</span> %s no decision.'
        % (_ids(undecided) or "none", "has" if len(undecided) == 1 else "have")))


def _score_table(key: str, caption: str, report: dict) -> str:
    rows = []
    for field, label in SCORE_FIELDS:
        cells = []
        for metric in ("precision", "recall", "f1"):
            v = "%.3f" % report["totals"][field][metric]
            if _MUTATE == "typed-score" and key == "reviewer" and field == "typologies" and metric == "f1":
                v = "0.700"
            cells.append('<td data-h="%s" data-score="%s" data-field="%s" data-m="%s">%s</td>'
                         % ({"f1": "F1"}.get(metric, metric.capitalize()), key, field, metric, v))
        rows.append("      <tr><td data-h=\"Field\">%s</td>%s</tr>" % (e(label), "".join(cells)))
    return """  <table class="rows score">
    <caption>%s</caption>
    <thead><tr><th>Field</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
    <tbody>
%s
    </tbody>
  </table>""" % (caption, "\n".join(rows))


def section_score(inp: dict) -> str:
    ext, rev = inp["scores"]["extraction"], inp["scores"]["reviewer"]
    if ext["scored"] != rev["scored"]:
        raise ValueError("the two record sets score different advisories; the tables would not compare")
    same = [label.lower() for field, label in SCORE_FIELDS if ext["totals"][field] == rev["totals"][field]]
    moved = []
    for f, label in SCORE_FIELDS:
        if ext["totals"][f] == rev["totals"][f]:
            continue
        a, b = "%.3f" % ext["totals"][f]["f1"], "%.3f" % rev["totals"][f]["f1"]
        if _MUTATE == "swap-moves":
            a, b = b, a
        moved.append('<span class="move" data-move="%s" data-from="%s" data-to="%s">%s F1 %s &rarr; %s</span>'
                     % (f, a, b, e(label.lower()), a, b))
    diff = ""
    if moved:
        diff = "<p>Adding the reviewer moves %s.%s</p>" % ("; ".join(moved), (
            " %s score the same in both tables." % e(" and ".join(same)).capitalize()) if same else "")
    return """<section id="score">
  <h2><span class="n">09</span> How well the extraction scores</h2>
  <p>Across the <span class="count" data-count="scored">%d</span> advisories scored, %s among them, each record is scored against a reference answer (its golden label), drafted and reviewed by Claude; the owner has decided the set&rsquo;s <span class="count" data-count="label-decided">%d</span> disputed entries, not yet the rest. Precision: of what the pipeline asserted, the share the label holds. Recall: of what the label holds, the share the pipeline asserted. F1 balances the two. Computed when this page was built.</p>
%s
%s
  %s
  <p class="flag">Each table is a single full-set run: one extraction of each advisory, scored once. The repeat records are not committed and these figures have no bands of their own. Two committed traces give context. <a href="%s" rel="noopener">The reviewer&rsquo;s acceptance bands, 2026-09-13</a>: typology precision, recall and F1 over three repeats of the reviewer on four advisories, before the owner&rsquo;s label pass &mdash; bands for that experiment, not for these figures. <a href="%s" rel="noopener">The first full-set run, 2026-09-12</a>: what limits typology recall; its figures are that day&rsquo;s, not these.</p>
</section>
""" % (len(ext["scored"]), (e(ADVISORY) if ADVISORY in ext["scored"] else "not including " + e(ADVISORY)),
       len(inp["label_pass"]),
       _score_table("extraction", "Extraction only: the extractor&rsquo;s committed records", ext),
       _score_table("reviewer", "Extraction + reviewer: the merged records, with the reviewer agent&rsquo;s additions",
                    rev), diff, e(BANDS_URL, quote=True), e(TRACE_URL, quote=True))


ATTEST_REASONS = {"page_break": "across a page break", "bullet_glyph": "with a list bullet extracted as a letter",
                  "dropped_accent": "with an accent dropped", "ellipsis_across_pages": "with an ellipsis spanning pages"}


def section_limits(inp: dict) -> str:
    attested = inp["attested"]
    counted = [a for a in attested if a["advisory_id"] == ADVISORY] if _MUTATE == "attested-count" else attested
    reasons = {}
    for a in attested:
        reasons[a["reason"]] = reasons.get(a["reason"], 0) + 1
    why = ", ".join("%d %s" % (n, e(ATTEST_REASONS.get(r, r)))
                    for r, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])))
    here = sum(1 for a in attested if a["advisory_id"] == ADVISORY)
    register = inp["register"]
    keyed = sum(1 for a in register if a.get("entity_key") is not None)
    emergent_ok = sum(1 for d in gd.latest(inp["all_decisions"]).values()
                      if d.kind == "emergent" and d.decision == "approve")
    tools = ("the extraction agent&rsquo;s current instructions do not name it, though it is among the agent&rsquo;s tools"
             if inp["resolver_available"] else "the extraction agent neither has it among its tools nor is told of it")
    label_advisories = len({d["advisory_id"] for d in inp["label_pass"]})
    return """<section id="limits">
  <h2><span class="n">10</span> What this slice does not do yet</h2>
  <ul class="limits">
    <li><strong>Actor resolution is not part of extraction.</strong> No committed extraction had the resolver: <code>%s</code> was added to the Knowledge Centre on <span data-date="resolver-added">%s</span>, and the newest proposal in any committed queue is dated <span data-date="newest-proposal">%s</span>. Separately, %s. Section 6&rsquo;s resolution was run afterwards, over the committed records. Resolving during extraction is slice 2.</li>
    <li><strong>No actor is linked to the platform&rsquo;s entities.</strong> <span data-count="entity-keys">%d</span> of the <span data-count="register">%d</span> register entries carry an <code>entity_key</code>; section 6 says why.</li>
    <li><strong>Digests are built, not delivered.</strong> A batch is cut on demand; nothing sends it to a desk.</li>
    <li><strong>Approved emergent candidates are not doctrine.</strong> An emergent typology the owner approves is recorded as approved; it is not added to the typology library. The pinned log holds <span data-count="emergent-approved">%d</span> such approvals.</li>
    <li><strong>Some citations are attested, not matched.</strong> <span data-count="attested">%d</span> citations across the merged records are true quotes the citation matcher cannot place on their page (%s), each attested by the owner. <span data-count="attested-here">%d</span> of them are on %s.</li>
    <li><strong>The reference answers are Claude&rsquo;s.</strong> Every golden label was drafted and reviewed by Claude. The owner has decided the <span data-count="label-decided">%d</span> entries disputed in the label pass, across <span data-count="label-advisories">%d</span> advisories, and not yet the rest. Section 9&rsquo;s scores are measured against these labels.</li>
    <li><strong>The scores are single runs.</strong> Section 9 shows one extraction per advisory; its figures have no bands of their own.</li>
  </ul>
</section>
""" % (RESOLVER, RESOLVER_ADDED, e(inp["newest_proposal"]), tools, keyed, len(register), emergent_ok, len(counted), why,
       here, e(ADVISORY), len(inp["label_pass"]), label_advisories)


# ---------------------------------------------------------------- the page

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Threat Intelligence Walkthrough</title>
<style>
  :root{
    --bg0:#060910; --bg1:#0b1120; --panel:rgba(255,255,255,.035);
    --edge:rgba(255,255,255,.10);
    --ink:#eaf1f9; --ink2:#a7b7cd; --ink3:#71839a;
    --acc:#79c4ff; --gold:#e9c877;
    --crit:#ff5d6c; --good:#4fdca0;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:"SF Mono",ui-monospace,"Roboto Mono",Menlo,monospace;
    --maxw:820px;
    --wm:linear-gradient(180deg,#f4f8ff,#aec0d7 58%,#7f92ac);
  }
  @media (prefers-color-scheme: light){
    :root{
      --bg0:#f5f7fb; --bg1:#ffffff; --panel:rgba(10,30,60,.04);
      --edge:rgba(10,30,60,.14);
      --ink:#0f1a2a; --ink2:#34465e; --ink3:#5b6d84;
      --acc:#0b64b8; --gold:#8a5f00;
      --crit:#c42636; --good:#0f7d52;
      --wm:linear-gradient(180deg,#1b2b45,#33496a 58%,#51678a);
    }
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg0);color:var(--ink);font-family:var(--sans);line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:var(--maxw);margin:0 auto;padding:32px 16px 72px}
  a{color:var(--acc);text-decoration:none;overflow-wrap:anywhere}
  a:hover{text-decoration:underline}
  code{font-family:var(--mono);font-size:.88em;color:var(--ink);overflow-wrap:anywhere}
  .backlink{display:inline-block;margin-bottom:10px;font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--ink3)}
  .brand{display:flex;align-items:center;gap:13px;margin-bottom:6px}
  .shield{width:38px;height:44px;flex:none;filter:drop-shadow(0 0 10px rgba(121,196,255,.35))}
  .wm{font-weight:800;letter-spacing:.2em;font-size:19px;background:var(--wm);-webkit-background-clip:text;background-clip:text;color:transparent}
  .wm .x{color:var(--acc);-webkit-text-fill-color:var(--acc)}
  .kicker{font-family:var(--mono);font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--ink3);margin-top:3px}
  h1{font-size:27px;line-height:1.22;font-weight:800;letter-spacing:-.015em;margin:24px 0 10px}
  .lede{font-size:16px;color:var(--ink2);margin:0 0 8px}
  section{margin-top:40px}
  h2{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--acc);font-weight:700;margin:0 0 14px;padding-bottom:9px;border-bottom:1px solid var(--edge);display:flex;gap:9px}
  h2 .n{font-family:var(--mono);color:var(--ink3);font-size:11px}
  p{margin:0 0 13px;color:var(--ink2)}
  p strong{color:var(--ink)}
  .chain{list-style:none;margin:0;padding:0}
  .chain>li{border-left:2px solid var(--edge);padding:0 0 4px 14px;margin:0 0 6px}
  .chain>li:last-child{border-left-color:var(--gold)}
  .step{display:block;font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);margin-bottom:3px}
  .facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:0 0 14px}
  .facts dt{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);padding-top:3px}
  .facts dd{margin:0;color:var(--ink);min-width:0;overflow-wrap:anywhere}
  .hash{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere;word-break:break-all}
  table.rows{width:100%;border-collapse:collapse;table-layout:fixed;font-size:14px}
  table.rows th{text-align:left;font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--edge)}
  table.rows th:nth-child(1){width:22%}
  table.rows th:nth-child(2){width:14%}
  table.rows th:nth-child(3){width:12%}
  table.rows th:nth-child(4){width:14%}
  table.rows td{vertical-align:top;padding:10px 8px;border-bottom:1px solid var(--edge);color:var(--ink2);overflow-wrap:anywhere;min-width:0}
  .cite{display:flex;gap:8px;align-items:baseline;margin:0 0 8px}
  .pg{flex:none;font-family:var(--mono);font-size:11px;color:var(--gold)}
  blockquote{margin:0;padding:2px 0 2px 10px;border-left:2px solid var(--edge);color:var(--ink);font-size:14px;overflow-wrap:anywhere;min-width:0}
  .props{list-style:none;margin:0;padding:0}
  .proposal{background:var(--panel);border:1px solid var(--edge);border-radius:10px;padding:12px 14px;margin:0 0 10px}
  .ph{margin-bottom:8px;color:var(--ink)}
  .conf{font-family:var(--mono);font-size:11px;color:var(--ink3);margin-left:6px}
  .link{background:var(--panel);border:1px solid var(--edge);border-radius:10px;padding:12px 14px;margin:0 0 14px}
  pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--mono);font-size:11.5px;line-height:1.5;color:var(--ink2);margin:0 0 10px}
  .decisions{list-style:none;margin:0;padding:8px 0 0;border-top:1px solid var(--edge)}
  .decisions li{margin:0 0 4px;color:var(--ink2)}
  .decisions time{font-family:var(--mono);font-size:12px;color:var(--ink3)}
  .approve{color:var(--good)}
  .reject{color:var(--crit)}
  .flag{border-left:2px solid var(--gold);padding-left:10px;color:var(--ink)}
  .desks{margin:0 0 6px;padding-left:18px;color:var(--ink2)}
  .desks li{margin:0 0 3px}
  .why{margin:2px 0 6px;font-size:13px;color:var(--ink2)}
  .why summary{cursor:pointer;font-family:var(--mono);font-size:11px;color:var(--ink3)}
  .why p{margin:6px 0 0;overflow-wrap:anywhere}
  table.two th:nth-child(1){width:44%}
  table.two th:nth-child(2){width:auto}
  table.tel th:nth-child(n){width:auto}
  table.tel th:nth-child(1),table.score th:nth-child(1){width:46%}
  table.score th:nth-child(n+2){width:18%}
  table.tel td:nth-child(n+2),table.score td:nth-child(n+2){font-family:var(--mono);font-size:13px}
  table.score{margin:0 0 16px}
  caption{text-align:left;font-size:13px;color:var(--ink);padding:0 0 6px}
  .role{display:block;font-size:12.5px;color:var(--ink3);margin-top:2px}
  .cats,.limits,.fails{margin:0 0 12px;padding-left:18px;color:var(--ink2)}
  .cats li,.limits li,.fails li{margin:0 0 6px}
  .limits strong{color:var(--ink)}
  .nr{color:var(--ink3);font-size:13px}
  .err{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}
  pre.digest{background:var(--panel);border:1px solid var(--edge);border-radius:10px;padding:12px 14px}
  @media (max-width:640px){
    h1{font-size:23px}
    table.rows thead{display:none}
    table.rows,table.rows tbody,table.rows tr,table.rows td{display:block;width:100%}
    table.rows tr{border-bottom:1px solid var(--edge);padding:8px 0}
    table.rows td{border:0;padding:3px 0}
    table.rows td:nth-child(2),table.rows td:nth-child(3),table.rows td:nth-child(4){display:inline-block;width:auto;margin-right:18px}
    table.two td:nth-child(2){display:block;margin-right:0}
    table.rows td::before{content:attr(data-h);display:block;font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3)}
    .facts{grid-template-columns:1fr;gap:0}
    .facts dd{margin-bottom:8px}
  }
</style>
</head>
<body>
<div class="wrap">
"""

BRAND = """  <a href="../future-capabilities.html" class="backlink">&larr; Future capabilities</a>
  <div class="brand">
    <svg class="shield" viewBox="0 0 40 46" fill="none" aria-hidden="true">
      <path d="M20 2 L36 8 V22 C36 33 29 41 20 44 C11 41 4 33 4 22 V8 Z"
            fill="rgba(121,196,255,.06)" stroke="url(#sg)" stroke-width="1.6"/>
      <path d="M14 30 V16 L26 30 V16" stroke="var(--acc)" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      <defs><linearGradient id="sg" x1="4" y1="2" x2="36" y2="44" gradientUnits="userSpaceOnUse">
        <stop stop-color="#79c4ff"/><stop offset="1" stop-color="#e9c877"/></linearGradient></defs>
    </svg>
    <div>
      <div class="wm">NE<span class="x">X</span>US</div>
      <div class="kicker">Threat Intelligence &middot; Slice 1</div>
    </div>
  </div>
"""

TAIL = """</div>
</body>
</html>
"""


def build(inp: dict) -> str:
    intro = """
  <h1>One advisory, from PDF to owner-approved typology links</h1>
  <p class="lede">%s, followed through extraction, grounding and review to the desks it reaches, with the actors it names, what the agent did, how the extraction scores and what this slice does not do yet. Every figure and quote on this page is read from a governed file when the page is built.</p>
""" % e(ADVISORY)
    sections = [section_question(inp), section_source(inp), section_extraction(inp),
                section_grounding(inp), section_review(inp), section_actors(inp), section_digest(inp),
                section_telemetry(inp), section_score(inp), section_limits(inp)]
    return HEAD + BRAND + intro + "\n" + "\n".join(sections) + TAIL


def main(argv: list) -> int:
    global _MUTATE
    ap = argparse.ArgumentParser(description="Build the public threat-intelligence walkthrough")
    ap.add_argument("--check", action="store_true", help="exit 1 when the committed page differs from a fresh build")
    ap.add_argument("--stdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--log", type=Path, default=gd.LOG, help=argparse.SUPPRESS)
    ap.add_argument("--_mutate", choices=MUTATIONS, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    _MUTATE = args._mutate
    page = build(inputs(args.log))
    if args.stdout:
        sys.stdout.buffer.write(page.encode("utf-8"))
        return 0
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != page:
            print("the committed page differs from a fresh build: run tools/build_walkthrough.py")
            return 1
        print("the committed page is a fresh build (%d bytes)" % len(page.encode("utf-8")))
        return 0
    if _MUTATE:
        print("REFUSED: a mutated builder never writes the committed page", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print("wrote %s (%d bytes)" % (OUT.relative_to(ROOT), len(page.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
