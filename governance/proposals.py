"""
The review gate's view of the proposal queue: load, re-check, group.

Proposals are written by the MCP server (propose_link) into one tracked file per
run under data/proposals/. The server already verified every quote. This module
verifies them AGAIN, because the queue is a plain file and anything could have
changed it since -- a proposal that fails is quarantined: shown with its reason,
never approvable.

The re-check re-asserts the WHOLE proposal contract (schemas/proposal_contract.py),
not only the quotes: the id still recomputes, exactly one of typology and
emergent label, a known stage, the run_id is its queue file's name, and every
quote is within bounds. The final week-5 review measured six hand-tampered lines
passing a quotes-only re-check clean, one of them an approvable link to
"EMERGENT[]".

A LINK is what a human decides: one advisory + one typology (or one emergent
label), collecting every proposal behind it from every run. One decision per
link, not per proposal -- measured 2026-09-24, one legacy link was proposed 11
times.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import PageIndex, file_sha256, norm  # noqa: E402
from schemas.proposal_contract import QUOTE_MAX, QUOTE_MIN, SCHEMA, STAGES, proposal_id  # noqa: E402

QUEUE_DIR = ROOT / "data" / "proposals"
LEGACY_QUEUE = ROOT / "data" / "proposals_legacy_2026-09-10_to_13.jsonl"
ADVISORY_LIST = ROOT / "evals" / "golden" / "advisory_list.json"
ADVISORIES_DIR = ROOT / "data" / "advisories"
LIBRARY = ROOT / "data" / "typologies.json"


def quote_hash(page: int, quote: str) -> str:
    return hashlib.sha256(("%d|%s" % (page, norm(quote))).encode("utf-8")).hexdigest()[:16]


def link_key(advisory_id: str, typology_id: Optional[str], emergent_label: Optional[str]) -> str:
    if typology_id:
        return "%s::%s" % (advisory_id, typology_id)
    return "%s::EMERGENT[%s]" % (advisory_id, " ".join((emergent_label or "").split()).lower())


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    proposed_at: str
    run_id: str
    stage: str
    advisory_id: str
    document_sha256: str
    typology_id: Optional[str]
    emergent_label: Optional[str]
    rationale: str
    confidence: str
    citations: Tuple[Tuple[int, str], ...]
    # The queue file the line was read from. Not part of the proposal: never in
    # body(), so never in the id. The re-check holds it against run_id.
    source_file: str = ""

    @classmethod
    def from_line(cls, d: dict, source_file: str = "") -> "Proposal":
        return cls(proposal_id=d["proposal_id"], proposed_at=d["proposed_at"], run_id=d["run_id"],
                   stage=d["stage"], advisory_id=d["advisory_id"], document_sha256=d["document_sha256"],
                   typology_id=d.get("typology_id"), emergent_label=d.get("emergent_label"),
                   rationale=d["rationale"], confidence=d["confidence"],
                   citations=tuple((int(c["page"]), c["quote"]) for c in d["citations"]),
                   source_file=source_file)

    def body(self) -> dict:
        """What the server hashed: the line minus proposal_id and proposed_at, rebuilt from the fields
        the gate actually uses -- so the id covers everything a reviewer is shown."""
        return {"schema": SCHEMA, "run_id": self.run_id, "stage": self.stage, "advisory_id": self.advisory_id,
                "document_sha256": self.document_sha256, "typology_id": self.typology_id,
                "emergent_label": self.emergent_label, "rationale": self.rationale,
                "confidence": self.confidence,
                "citations": [{"page": pg, "quote": q} for pg, q in self.citations]}

    @property
    def kind(self) -> str:
        return "governed" if self.typology_id else "emergent"

    @property
    def link_key(self) -> str:
        return link_key(self.advisory_id, self.typology_id, self.emergent_label)


@dataclass(frozen=True)
class Quarantined:
    proposal: Proposal
    reason: str


@dataclass
class Link:
    key: str
    advisory_id: str
    typology_id: Optional[str]
    emergent_label: Optional[str]
    proposals: List[Proposal] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "governed" if self.typology_id else "emergent"

    def quotes(self) -> List[Tuple[int, str, int]]:
        """Distinct quotes in page order, each with how many proposals carried it."""
        seen: Dict[str, list] = {}
        for p in self.proposals:
            for page, q in p.citations:
                h = quote_hash(page, q)
                if h in seen:
                    seen[h][2] += 1
                else:
                    seen[h] = [page, q, 1]
        return sorted((tuple(v) for v in seen.values()), key=lambda t: (t[0], t[1]))

    def quote_hashes(self) -> frozenset:
        return frozenset(quote_hash(pg, q) for p in self.proposals for pg, q in p.citations)

    @property
    def proposal_ids(self) -> Tuple[str, ...]:
        return tuple(sorted({p.proposal_id for p in self.proposals}))

    @property
    def run_ids(self) -> Tuple[str, ...]:
        return tuple(sorted({p.run_id for p in self.proposals}))

    @property
    def stages(self) -> Tuple[str, ...]:
        return tuple(sorted({p.stage for p in self.proposals}))


def load_queue(queue_dir: Path = QUEUE_DIR) -> Tuple[List[Proposal], List[str]]:
    """Every proposal/2 line under queue_dir, and one note per line skipped -- none vanish silently."""
    proposals: List[Proposal] = []
    skipped: List[str] = []
    for path in (sorted(queue_dir.glob("*.jsonl")) if queue_dir.exists() else []):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                skipped.append("%s:%d is not JSON" % (path.name, n))
                continue
            if d.get("schema") != SCHEMA:
                skipped.append("%s:%d has schema %r, not %s" % (path.name, n, d.get("schema"), SCHEMA))
                continue
            try:
                proposals.append(Proposal.from_line(d, source_file=path.name))
            except (KeyError, TypeError, ValueError) as exc:
                skipped.append("%s:%d is malformed (%s)" % (path.name, n, exc))
    return proposals, skipped


def _advisories(path: Path) -> Dict[str, dict]:
    return {a["advisory_id"]: a for a in json.loads(path.read_text(encoding="utf-8"))["advisories"]}


def _library_ids(path: Path) -> frozenset:
    return frozenset(t["typology_id"] for t in json.loads(path.read_text(encoding="utf-8"))["typologies"])


def _contract_problem(p: Proposal) -> Optional[str]:
    """Why p breaks the proposal contract, or None. Factored out so the guard can remove it
    (evals/check_review_gate.py --mutate contract) and watch its checks fail."""
    recomputed = proposal_id(p.body())
    if recomputed != p.proposal_id:
        return ("proposal_id %s does not recompute (the line hashes to %s): it was changed after the "
                "server wrote it" % (p.proposal_id, recomputed))
    has_typology, has_label = bool((p.typology_id or "").strip()), bool((p.emergent_label or "").strip())
    if has_typology == has_label:
        return ("names %s of typology_id and emergent_label; a proposal names exactly one"
                % ("both" if has_typology else "neither"))
    if p.stage not in STAGES:
        return "stage %r is not one of %s" % (p.stage, ", ".join(STAGES))
    if Path(p.source_file).stem != p.run_id:
        return "run_id %s does not match its queue file %s" % (p.run_id, p.source_file or "(none)")
    for page, q in p.citations:
        n = len(q.strip())
        if not QUOTE_MIN <= n <= QUOTE_MAX:
            return ("quote on page %d is %d characters after strip; the contract allows %d to %d"
                    % (page, n, QUOTE_MIN, QUOTE_MAX))
    return None


def recheck(proposals, advisory_list: Path = ADVISORY_LIST, advisories_dir: Path = ADVISORIES_DIR,
            library: Path = LIBRARY) -> Tuple[List[Proposal], List[Quarantined]]:
    """Split proposals into clean and quarantined. A quarantined proposal can never be approved."""
    advisories = _advisories(advisory_list)
    known = _library_ids(library)
    indexes: Dict[str, Optional[PageIndex]] = {}
    clean: List[Proposal] = []
    quarantined: List[Quarantined] = []

    def index_for(a: dict) -> Optional[PageIndex]:
        aid = a["advisory_id"]
        if aid not in indexes:
            pdf = advisories_dir / Path(a["file"]).name
            ok = pdf.exists() and file_sha256(pdf) == a["sha256"]
            indexes[aid] = PageIndex.from_pdf(pdf) if ok else None
        return indexes[aid]

    def evidence_problem(p: Proposal) -> Optional[str]:
        """Why p's advisory, typology or quotes do not stand up against the documents, or None."""
        a = advisories.get(p.advisory_id)
        if a is None:
            return "advisory %s is not in the advisory list" % p.advisory_id
        if p.document_sha256 != a["sha256"]:
            return ("document hash %s... is not the advisory list's %s..."
                    % (p.document_sha256[:12], a["sha256"][:12]))
        if p.typology_id and p.typology_id not in known:
            return "%s is not in the library" % p.typology_id
        if not p.citations:
            return "no citations"
        index = index_for(a)
        if index is None:
            return ("the source PDF for %s is missing or does not match its hash on this machine; "
                    "its quotes cannot be re-checked" % p.advisory_id)
        for pg, q in p.citations:
            hit = index.locate(pg, q)
            if hit.ok:
                continue
            if hit.found_on:
                return "quote not on page %d (it appears on page %s): %r" % (
                    pg, ", ".join(str(n) for n in hit.found_on), q[:70])
            return "quote not in the document (cited page %d): %r" % (pg, q[:70])
        return None

    for p in proposals:
        # The contract first: a line that is not what the server wrote is not evidence of anything.
        reason = _contract_problem(p) or evidence_problem(p)
        if reason:
            quarantined.append(Quarantined(p, reason))
        else:
            clean.append(p)
    return clean, quarantined


def group(proposals) -> Dict[str, Link]:
    links: Dict[str, Link] = {}
    for p in sorted(proposals, key=lambda p: (p.link_key, p.proposed_at, p.proposal_id)):
        link = links.get(p.link_key)
        if link is None:
            link = links[p.link_key] = Link(p.link_key, p.advisory_id, p.typology_id, p.emergent_label)
        link.proposals.append(p)
    return dict(sorted(links.items()))


def quarantined_links(quarantined, links: Dict[str, Link]) -> Dict[str, str]:
    """Link keys whose EVERY proposal was quarantined, with the first reason."""
    out: Dict[str, str] = {}
    for q in quarantined:
        key = q.proposal.link_key
        if key not in links and key not in out:
            out[key] = q.reason
    return dict(sorted(out.items()))
