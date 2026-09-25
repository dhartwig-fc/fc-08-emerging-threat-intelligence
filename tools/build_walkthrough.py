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
  the desk routing table           -> "desks reached", through the digest's own routing rule

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import card  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance.digest import APPROVED_NOT_IN_RECORD, DIGESTS_DIR, RECORDS_DIR, _routes  # noqa: E402
from governance.proposals import ADVISORY_LIST, LIBRARY, QUEUE_DIR, group, link_key, load_queue_files  # noqa: E402
from governance.routing import load_routing  # noqa: E402

OUT = ROOT / "site" / "threat-intel" / "index.html"
ADVISORY = "ADV-2026-0013"
DECIDED_RUN = "adv-2026-0013-extractor-f617bd3b00"
TELEMETRY_RUN = "adv-2026-0013-extractor-69eeab7b41"
GOLDEN_DIR = ROOT / "evals" / "golden"
_MUTATE = None  # set only by evals/check_walkthrough.py through --_mutate

e = html.escape
PAST = {"approve": "approved", "reject": "rejected"}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def inputs(log: Path = gd.LOG) -> dict:
    """Every input the page is built from, loaded once. Refuses inputs that disagree with each other."""
    advisories = {a["advisory_id"]: a for a in _json(ADVISORY_LIST)["advisories"]}
    advisory = advisories[ADVISORY]
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
    return "".join('<div class="cite"><span class="pg">p%d</span><blockquote>%s</blockquote></div>'
                   % (int(pg), e(q)) for pg, q in citations)


def _standing(inp: dict) -> dict:
    return gd.latest(inp["decisions"])


# ---------------------------------------------------------------- sections

def section_question(inp: dict) -> str:
    a, rec = inp["advisory"], inp["record"]
    typs = rec["typologies"]
    n_ext = sum(1 for t in typs if _asserted_by(t) == "extractor")
    n_emergent = sum(1 for t in typs if not t.get("typology_id"))
    standing = _standing(inp)
    n_app = sum(1 for d in standing.values() if d.decision == "approve")
    n_rej = sum(1 for d in standing.values() if d.decision == "reject")
    titles = inp["routing"]["desk_titles"]
    desks = [titles.get(d, d) for d in inp["desks"]]
    return """<section id="question">
  <h2><span class="n">01</span> The question</h2>
  <ol class="chain">
    <li><span class="step">Question</span>
      <p>What does <strong>%s</strong> (%s, %s) tell a financial-crime team to look for, and which desks need to hear it?</p></li>
    <li><span class="step">Capability</span>
      <p>An extraction agent reads the advisory and writes a governed record: every typology it asserts carries a page number and a verbatim quote from a document pinned by its sha256. The agent's only write is <code>propose_link</code>, which will not record a proposal whose quote it cannot find on the cited page. A second, reviewer agent adds what the extractor missed, each addition with its justification; the owner decides each proposed link at a review gate; every decision is a dated line in an append-only log.</p></li>
    <li><span class="step">Intelligence produced</span>
      <p>%s asserted in the record &mdash; %d by the extractor, %d added by the reviewer agent, %d of them emergent (not in the typology library). Run <code>%s</code> proposed %s; the owner approved %d and rejected %d.</p></li>
    <li><span class="step">Investigator outcome</span>
      <p>The advisory reached %s: %s. Each desk reads the approved links in its own family, quoted from the page they came from.</p></li>
  </ol>
</section>
""" % (e(a["title"]), e(a["publisher"]), e(a["published_on"]),
       _plural(len(typs), "typology", "typologies"), n_ext, len(typs) - n_ext, n_emergent,
       e(DECIDED_RUN), _plural(len(inp["links"]), "link"), n_app, n_rej,
       _plural(len(desks), "desk"), e(", ".join(desks)))


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
        status = ("%s %s" % (PAST[d.decision], d.decided_at[:10])) if d else "not decided"
        cites = [(c["page"], c["quote"]) for c in t["citations"]]
        if _MUTATE == "drop-citation":
            cites = cites[:-1]
        rows.append("""    <tr>
      <td data-h="Typology"><code>%s</code> %s</td>
      <td data-h="Family">%s</td>
      <td data-h="Asserted by">%s</td>
      <td data-h="Owner">%s</td>
      <td data-h="Citations">%s</td>
    </tr>""" % (e(tid), e(label), e(family), e(_asserted_by(t)), e(status), _cites(cites)))
    in_record = {_key(t) for t in rec["typologies"]}
    outside = [d for k, d in sorted(standing.items()) if k not in in_record]
    note = ""
    if outside:
        note = "".join(
            "\n  <p class=\"flag\"><code>%s</code> is %s but not in this record: it reached the owner as a proposal "
            "from run %s, not through the record. Section 5 shows the decision.</p>"
            % (e(d.typology_id or d.emergent_label), e(PAST[d.decision]), e(", ".join(d.run_ids))) for d in outside)
    return """<section id="extraction">
  <h2><span class="n">03</span> What the record asserts</h2>
  <p>The merged record for %s: %s, each with the quotes that ground it. &ldquo;Owner&rdquo; is the standing decision in the pinned decision log, where there is one.</p>
  <table class="rows">
    <thead><tr><th>Typology</th><th>Family</th><th>Asserted by</th><th>Owner</th><th>Citations</th></tr></thead>
    <tbody>
%s
    </tbody>
  </table>%s
</section>
""" % (e(ADVISORY), _plural(len(rec["typologies"]), "typology", "typologies"), "\n".join(rows), note)


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
  <p>Run <code>%s</code> proposed %s. Each quote was located on its cited page of the pinned document by <code>propose_link</code> before the proposal was written &mdash; that is the tool's contract, and a quote it cannot place is refused, never queued. This page is built without the PDF and does not re-check them.</p>
  <ol class="props">
%s
  </ol>
</section>
""" % (e(DECIDED_RUN), _plural(len(inp["proposals"]), "proposal"), "\n".join(items))


def section_review(inp: dict) -> str:
    rec_ids = {t.get("typology_id") for t in inp["record"]["typologies"] if t.get("typology_id")}
    by_link = {}
    for d in inp["decisions"]:
        by_link.setdefault(d.link_key, []).append(d)
    blocks = []
    for key, link in inp["links"].items():
        text = card.render(link, None, inp["advisories"], inp["library"], inp["golden_ids"])
        lines = "".join('\n      <li class="decision"><time>%s</time> <b class="%s">%s</b> <span class="note">%s</span></li>'
                        % (e(d.decided_at[:10]), e(d.decision), e(d.decision.upper()), e(d.note or "(no note)"))
                        for d in by_link.get(key, []))
        flag = ""
        if link.typology_id and link.typology_id not in rec_ids:
            reached = [inp["routing"]["desk_titles"].get(desk, desk) for desk, reasons in inp["desks"].items()
                       if any(r.startswith(link.typology_id + " ") and APPROVED_NOT_IN_RECORD in r for r in reasons)]
            routed = (" The digest still routes it, to the %s, marked &ldquo;%s&rdquo;."
                      % (e(", ".join(reached)), e(APPROVED_NOT_IN_RECORD))) if reached else ""
            flag = ('\n    <p class="flag"><code>%s</code> is not in the merged record: it reached the owner as this '
                    "run's proposal, not through the record.%s</p>" % (e(link.typology_id), routed))
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
  </article>""" % (e(ADVISORY), "".join(
            '\n      <li class="decision"><code>%s</code> <time>%s</time> <b class="%s">%s</b> <span class="note">%s</span></li>'
            % (e(d.typology_id or d.emergent_label), e(d.decided_at[:10]), e(d.decision), e(d.decision.upper()),
               e(d.note or "(no note)")) for d in others))
    return """<section id="review">
  <h2><span class="n">05</span> Review: what the owner saw, and decided</h2>
  <p>Each card is rendered exactly as the review gate showed it, from run <code>%s</code>'s queue, followed by the owner's decision. Built from the first %s of the decision log, the prefix digest batch <code>%s</code> pinned (sha256 <span class="hash">%s</span>); %s of them decide %s.</p>
%s%s
</section>
""" % (e(DECIDED_RUN), _plural(inp["log_lines"], "line"), e(inp["batch"]), e(inp["log_sha256"]),
       len(inp["decisions"]), e(ADVISORY), "\n".join(blocks), tail)


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
  .chain li{border-left:2px solid var(--edge);padding:0 0 4px 14px;margin:0 0 6px}
  .chain li:last-child{border-left-color:var(--gold)}
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
  @media (max-width:640px){
    h1{font-size:23px}
    table.rows thead{display:none}
    table.rows,table.rows tbody,table.rows tr,table.rows td{display:block;width:100%}
    table.rows tr{border-bottom:1px solid var(--edge);padding:8px 0}
    table.rows td{border:0;padding:3px 0}
    table.rows td:nth-child(2),table.rows td:nth-child(3),table.rows td:nth-child(4){display:inline-block;width:auto;margin-right:18px}
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
  <p class="lede">%s, followed through extraction, grounding and review. Every figure and quote on this page is read from a governed file when the page is built.</p>
""" % e(ADVISORY)
    sections = [section_question(inp), section_source(inp), section_extraction(inp),
                section_grounding(inp), section_review(inp)]
    return HEAD + BRAND + intro + "\n" + "\n".join(sections) + TAIL


def main(argv: list) -> int:
    global _MUTATE
    ap = argparse.ArgumentParser(description="Build the public threat-intelligence walkthrough")
    ap.add_argument("--check", action="store_true", help="exit 1 when the committed page differs from a fresh build")
    ap.add_argument("--stdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--log", type=Path, default=gd.LOG, help=argparse.SUPPRESS)
    ap.add_argument("--_mutate", choices=("drop-citation", "unpinned-log"), help=argparse.SUPPRESS)
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
