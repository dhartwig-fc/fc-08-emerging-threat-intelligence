"""
The review gate: the ONLY way a proposal becomes an approved link.

Usage:
    python tools/review.py                      # step through open links: approve / reject / skip / quit
    python tools/review.py --list               # what is open, decided, new evidence, quarantined, skipped
    python tools/review.py --decisions FILE     # apply a pasted list (e.g. from a phone)
    python tools/review.py --check              # fail unless approvals match the log AND the log is the gate's

A decisions file holds one line per link. Leading list markers (-, *, a bullet)
and a lowercase "adv-" are accepted, because that is what a phone pastes. A line
that does not mention ADV- is ignored; one that does and cannot be read refuses
the whole list -- a decision is never silently dropped. An empty list is refused.
    ADV-2026-0002 BA008: approve -- note
    - ADV-2026-0002 EMERGENT[shadow fleet ship-to-ship transfer]: reject -- note

Both deciding modes go through governance.decisions.apply, which refuses an
unknown or quarantined link, a link twice in one list, and overturning a decided
link. Every decision is followed by rebuilding the approvals files from the
decision log, so the two can never disagree.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance import card  # noqa: E402
from governance import decisions as gd  # noqa: E402
from governance import proposals as gp  # noqa: E402

MARKERS = re.compile(r"^[\s\-*\u2022]+")  # leading whitespace, -, * and the bullet a phone inserts
LINE = re.compile(r"^(ADV-\d{4}-\d{4})\s+(?:([A-Z]{2,6}\d{3}[A-Z]?)|EMERGENT\[(.+?)\]):\s*(approve|reject)"
                  r"\s*(?:--\s*(.*))?$", re.I)


def parse_decisions(text: str) -> list:
    out = []
    for raw in text.splitlines():
        line = MARKERS.sub("", raw).strip()
        if "adv-" not in line.lower():
            continue
        m = LINE.match(line)
        if not m:
            raise SystemExit("cannot read decision line, nothing written: %r" % raw.strip())
        aid, tid, label, decision, note = m.groups()
        out.append((gp.link_key(aid.upper(), tid.upper() if tid else None, label), decision.lower(),
                    (note or "").strip()))
    return out


def _load(args):
    proposals, skipped = gp.load_queue(args.queue_dir)
    clean, quarantined = gp.recheck(proposals)
    links = gp.group(clean)
    return links, gp.quarantined_links(quarantined, links), quarantined, skipped


def _context():
    advisories = {a["advisory_id"]: a for a in
                  json.loads(gp.ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}
    library = {t["typology_id"]: t for t in json.loads(gp.LIBRARY.read_text(encoding="utf-8"))["typologies"]}
    golden = {}
    for aid in advisories:
        path = ROOT / "evals" / "golden" / ("%s.json" % aid)
        if path.exists():
            golden[aid] = {t.get("typology_id") for t in json.loads(path.read_text(encoding="utf-8"))["typologies"]}
    return advisories, library, golden


def _finish(args) -> None:
    gd.write_approved(gd.load_log(args.log), args.approved_links, args.approved_emergent)


def cmd_list(args) -> int:
    links, q_links, quarantined, skipped = _load(args)
    prior = gd.latest(gd.load_log(args.log))
    by_state = {gd.OPEN: [], gd.NEW_EVIDENCE: [], gd.DECIDED: []}
    for key, link in links.items():
        by_state[gd.state(link, prior.get(key))].append(key)
    for name in (gd.OPEN, gd.NEW_EVIDENCE, gd.DECIDED):
        print("%s: %d" % (name.replace("_", " "), len(by_state[name])))
        for key in by_state[name]:
            print("  %s" % key)
    print("quarantined links: %d" % len(q_links))
    for key, reason in q_links.items():
        print("  %s -- %s" % (key, reason))
    print("quarantined proposals: %d | skipped lines: %d" % (len(quarantined), len(skipped)))
    for q in quarantined:
        print("  quarantined %s (%s) -- %s" % (q.proposal.proposal_id, q.proposal.link_key, q.reason))
    for note in skipped:
        print("  skipped %s" % note)
    if gp.LEGACY_QUEUE.exists():
        print("legacy queue (frozen, never reviewed): %s" % gp.LEGACY_QUEUE.relative_to(ROOT))
    return 0


def cmd_decisions(args) -> int:
    links, q_links, _, _ = _load(args)
    requests = parse_decisions(args.decisions.read_text(encoding="utf-8"))
    try:
        made = gd.apply(requests, links, q_links, log_path=args.log)
    except gd.GateRefusal as exc:
        print("REFUSED, nothing written: %s" % exc, file=sys.stderr)
        return 1
    _finish(args)
    print("recorded %d decision%s; approvals rebuilt" % (len(made), "" if len(made) == 1 else "s"))
    return 0


def cmd_check(args) -> int:
    decisions, problems = gd.load_log_checked(args.log)
    problems += gd.check_approved(decisions, args.approved_links, args.approved_emergent)
    known = {p.proposal_id: p.link_key for p in gp.load_queue(args.queue_dir)[0]}
    problems += gd.check_log(decisions, known)
    for p in problems:
        print("FAIL  %s" % p)
    print("approvals match the decision log, and every decision cites the queue" if not problems
          else "the approvals and the decision log DO NOT agree with the gate")
    return 1 if problems else 0


def _split_override(args) -> bool:
    """True when exactly one of --queue-dir / --log was pointed away from the real files: a
    fixture queue must never feed the real log, nor the real queue a stray log."""
    def moved(path, default) -> bool:
        return Path(path).resolve() != Path(default).resolve()
    return moved(args.queue_dir, gp.QUEUE_DIR) != moved(args.log, gd.LOG)


def cmd_interactive(args) -> int:
    links, q_links, _, skipped = _load(args)
    advisories, library, golden = _context()
    prior = gd.latest(gd.load_log(args.log))
    todo = [k for k, link in links.items() if gd.state(link, prior.get(k)) != gd.DECIDED]
    print("%d link%s to review (%d quarantined, %d lines skipped)" % (
        len(todo), "" if len(todo) == 1 else "s", len(q_links), len(skipped)))
    decided = 0
    for key in todo:
        link = links[key]
        print(card.render(link, prior.get(key), advisories, library, golden.get(link.advisory_id, set())))
        while True:
            try:
                choice = input("[a]pprove  [r]eject  [s]kip  [q]uit > ").strip().lower()
            except EOFError:
                choice = "q"
            if choice in ("a", "r", "s", "q"):
                break
        if choice == "q":
            break
        if choice == "s":
            continue
        try:
            note = input("note (optional) > ").strip()
        except EOFError:
            note = ""
        try:
            gd.apply([(key, "approve" if choice == "a" else "reject", note)], links, q_links, log_path=args.log)
        except gd.GateRefusal as exc:
            print("REFUSED: %s" % exc)
            continue
        decided += 1
        _finish(args)  # after every decision, so quitting never leaves the files behind the log
    print("recorded %d decision%s" % (decided, "" if decided == 1 else "s"))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="The review gate")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--decisions", type=Path, help="apply a pasted list of decisions")
    mode.add_argument("--list", action="store_true", help="summarise the queue; decide nothing")
    mode.add_argument("--check", action="store_true", help="fail if the approvals files differ from the log")
    ap.add_argument("--queue-dir", type=Path, default=gp.QUEUE_DIR)
    ap.add_argument("--log", type=Path, default=gd.LOG)
    ap.add_argument("--approved-links", type=Path, default=gd.APPROVED_LINKS)
    ap.add_argument("--approved-emergent", type=Path, default=gd.APPROVED_EMERGENT)
    args = ap.parse_args(argv)
    if args.list:
        return cmd_list(args)
    if args.check:
        return cmd_check(args)
    if _split_override(args):
        print("REFUSED: override --queue-dir and --log together or neither; a deciding mode must not "
              "mix a real and a stray file", file=sys.stderr)
        return 2
    if args.decisions:
        return cmd_decisions(args)
    return cmd_interactive(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
