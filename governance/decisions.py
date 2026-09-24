"""
The review gate's record: an append-only decision log, and the approvals rebuilt from it.

data/review_decisions.jsonl is the evidence. The two approvals files are DERIVED
from it, deterministically, every time -- so an approvals file can never say
something the log does not, and a hand edit is caught by check_approved. Nothing
else in the repository writes either file; evals/check_review_gate.py enforces it.

Refusals (GateRefusal), with NOTHING written -- the whole list is checked first:
  - the same link twice in one list;
  - a link that is not reviewable (unknown, or every proposal quarantined);
  - a link already decided with no new evidence: a change of mind needs its own
    dated record. A later run bringing a quote not seen before reopens the link;
    deciding it APPENDS, and the earlier line is never edited.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from governance.proposals import ROOT, Link

LOG = ROOT / "data" / "review_decisions.jsonl"
APPROVED_LINKS = ROOT / "data" / "approved_links.json"
APPROVED_EMERGENT = ROOT / "data" / "approved_emergent.json"
OPEN, DECIDED, NEW_EVIDENCE = "open", "decided", "new_evidence"
DECISIONS = ("approve", "reject")


class GateRefusal(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    decided_at: str
    link_key: str
    kind: str
    advisory_id: str
    typology_id: Optional[str]
    emergent_label: Optional[str]
    decision: str
    note: str
    proposal_ids: Tuple[str, ...]
    run_ids: Tuple[str, ...]
    quotes_seen_sha256: Tuple[str, ...]

    def to_line(self) -> str:
        d = asdict(self)
        for k in ("proposal_ids", "run_ids", "quotes_seen_sha256"):
            d[k] = list(d[k])
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_line(cls, d: dict) -> "Decision":
        return cls(**{**d, "proposal_ids": tuple(d["proposal_ids"]), "run_ids": tuple(d["run_ids"]),
                      "quotes_seen_sha256": tuple(d["quotes_seen_sha256"])})


def load_log(path: Path = LOG) -> List[Decision]:
    if not path.exists():
        return []
    return [Decision.from_line(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def latest(decisions) -> Dict[str, Decision]:
    """The standing decision per link: the log is append-only, so the last line wins."""
    out: Dict[str, Decision] = {}
    for d in decisions:
        out[d.link_key] = d
    return out


def state(link: Link, prior: Optional[Decision]) -> str:
    if prior is None:
        return OPEN
    return NEW_EVIDENCE if link.quote_hashes() - set(prior.quotes_seen_sha256) else DECIDED


def apply(requests, links: Dict[str, Link], quarantined: Dict[str, str], log_path: Path = LOG,
          now: Optional[str] = None) -> List[Decision]:
    """Check every (link_key, decision, note) request, then append them all -- or refuse and write nothing."""
    requests = list(requests)
    twice = sorted(k for k, n in Counter(k for k, _, _ in requests).items() if n > 1)
    if twice:
        raise GateRefusal("%s is decided twice in one list" % ", ".join(twice))
    prior = latest(load_log(log_path))
    stamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: List[Decision] = []
    for key, decision, note in requests:
        if decision not in DECISIONS:
            raise GateRefusal("%s: a decision is approve or reject, not %r" % (key, decision))
        if key not in links:
            if key in quarantined:
                raise GateRefusal("%s is quarantined and cannot be decided: %s" % (key, quarantined[key]))
            raise GateRefusal("no reviewable link %s" % key)
        link = links[key]
        if state(link, prior.get(key)) == DECIDED:
            p = prior[key]
            raise GateRefusal("%s was already decided (%s, %s) and no new evidence has arrived -- "
                              "a change of mind needs its own dated record" % (key, p.decision, p.decided_at[:10]))
        out.append(Decision(decided_at=stamp, link_key=key, kind=link.kind, advisory_id=link.advisory_id,
                            typology_id=link.typology_id, emergent_label=link.emergent_label,
                            decision=decision, note=(note or "").strip(), proposal_ids=link.proposal_ids,
                            run_ids=link.run_ids, quotes_seen_sha256=tuple(sorted(link.quote_hashes()))))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        for d in out:
            fh.write(d.to_line() + "\n")
    return out


def _rows(decisions, kind: str) -> list:
    rows = []
    for d in sorted(latest(decisions).values(), key=lambda d: d.link_key):
        if d.decision != "approve" or d.kind != kind:
            continue
        row = {"link_key": d.link_key, "advisory_id": d.advisory_id, "decided_at": d.decided_at,
               "note": d.note, "run_ids": list(d.run_ids), "proposal_ids": list(d.proposal_ids)}
        if kind == "governed":
            row["typology_id"] = d.typology_id
        else:
            row["emergent_label"] = d.emergent_label
        rows.append(row)
    return rows


def rebuild(decisions) -> Tuple[str, str]:
    """(links file text, emergent file text), byte-identical for the same log."""
    def dump(rows) -> str:
        return json.dumps({"generated_from": "data/review_decisions.jsonl", "approved": rows},
                          indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    decisions = list(decisions)
    return dump(_rows(decisions, "governed")), dump(_rows(decisions, "emergent"))


def write_approved(decisions, links_path: Path = APPROVED_LINKS, emergent_path: Path = APPROVED_EMERGENT) -> None:
    links_text, emergent_text = rebuild(decisions)
    links_path.parent.mkdir(parents=True, exist_ok=True)
    links_path.write_text(links_text, encoding="utf-8")
    emergent_path.write_text(emergent_text, encoding="utf-8")


def check_approved(decisions, links_path: Path = APPROVED_LINKS,
                   emergent_path: Path = APPROVED_EMERGENT) -> List[str]:
    """Problems, empty when the files are exactly what the log rebuilds to."""
    decisions = list(decisions)
    if not decisions and not links_path.exists() and not emergent_path.exists():
        return []
    problems = []
    for path, want in zip((links_path, emergent_path), rebuild(decisions)):
        if not path.exists():
            problems.append("%s is missing; rebuild with tools/review.py" % path.name)
        elif path.read_text(encoding="utf-8") != want:
            problems.append("%s does not match what the decision log rebuilds to" % path.name)
    return problems
