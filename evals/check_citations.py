"""
Week-1 review helper: does every citation in an AdvisoryRecord point at text that
actually exists on the page it names?

Usage:
    python check_citations.py <record.json> <advisory.pdf>
    python check_citations.py --all
    python check_citations.py --all --write-baseline

This is the mechanical half of "read the record against the PDF". It does NOT
judge whether the typology mapping is right; it only proves each quote is real.
The plan's week-4 reviewer subagent does the same check inside the pipeline.

--all checks every data/records_merged/ADV-*.json against its own PDF, located
the same way evals/check_proposal_contract.py locates one: the "file" field in
evals/golden/advisory_list.json, resolved under data/advisories/ (gitignored).

Measured 2026-09-25: evals/golden (the hand-written labels) has ZERO citation
defects across 843 citations -- the checker and the PDFs are sound. The
MERGED records are a different, and real, story: 118 of 717 citations in
data/records_merged cite the wrong page or text that is not in the document at
all. Nobody re-verified a record's citations after week 1. That is a release
finding for the owner, not something this guard fixes by rewriting records.

Re-measured 2026-09-25 after schemas/citation_match.py gained the ARTEFACT tier
(footnote markers, line-break hyphens): 18 of the 43 "missing" were true quotes
the matcher could not see -- 15 are on the cited page and are no longer defects,
3 are on another page and are now off_page. 103 remained (78 off_page, 25 missing).

Re-measured again 2026-09-25 after the ELLIPSIS and SPANS tiers (owner's decision): the
12 ellipsis quotations with every fragment on the cited page left the baseline; the
SPANS tier moved none of the 5 page-spanning quotes and was removed the same day (the
owner chose to attest true quotes the matcher cannot place rather than widen the shared
rule). 91 remain (78 off_page, 13 missing); the baseline file is the live number, not
this paragraph.

So --all does not simply fail red forever. It compares the CURRENT defect set
against a frozen baseline, evals/known_citation_defects.json (tracked, an
input this task pins, not a build output):
  - exit 0  only if the current set is EXACTLY the baseline (same defects,
            same multiplicities) -- the guard stays green while the known
            defects are known, and goes red the moment anything CHANGES.
  - exit 1  if a defect exists now that is not in the baseline ("NEW defect"),
            or a baseline defect no longer reproduces ("FIXED (remove from
            baseline)") -- either way, something moved and a human must look.
  - exit 2  if a PDF this run needs is not on this machine (needs-pdfs).

A NEW defect is asserted as a fact, not waved through: the baseline is a
record of what is ALREADY wrong, not a budget for how much MORE is allowed to
go wrong. --write-baseline regenerates the file from the current state; it
exists to build the baseline once (or after an owner-approved fix removes an
entry), and must NEVER be run to make a newly introduced defect disappear --
that would hide the regression check_citations.py exists to catch, not close
it. Only the commit that actually fixes a record's citation may remove that
record's entry from the baseline.

ATTESTATION (owner's decision 2026-09-25). Some true quotes cannot be placed by the shared
matcher -- a quote running over a page break, an ellipsis whose fragment crosses a page,
a dropped accent, a list bullet pypdf extracts as a letter -- and the owner chose not to
widen the matcher for them (every tolerance there also loosens propose_link's gate). They
are ATTESTED instead, in evals/attested_citations.json, one entry per citation by its full
identity (advisory_id, section, item, page, quote_sha256) with a reason, a page-text
excerpt as evidence, attested_by "owner" and a date. --all counts an attested citation as
verified-by-attestation (reported separately), NOT as a defect, and REFUSES (exit 1) the
list when an entry is malformed, appears twice, matches no citation ("stale
attestation"), or is now placed by the matcher ("attestation no longer needed -- remove
it"). The list is read here only; the matcher, the MCP server and the review gate never
see it. Pinned cold by evals/check_attestations.py.

--records-dir (hidden; not for interactive use) points the defect computation
at a different directory of ADV-*.json records instead of data/records_merged.
It exists solely so a guard on this guard can run --all against a temporary,
mutated COPY of the records without ever touching the real ones, while still
diffing against the real tracked baseline.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import ARTEFACT, ELLIPSIS, EXACT, OFF_PAGE, SPACING, PageIndex  # noqa: E402

BASELINE_PATH = ROOT / "evals" / "known_citation_defects.json"
ATTESTED_PATH = ROOT / "evals" / "attested_citations.json"
ATTEST_REASONS = ("page_break", "ellipsis_across_pages", "dropped_accent", "bullet_glyph")
ATTEST_FIELDS = ("advisory_id", "section", "item", "page", "quote_sha256", "reason", "evidence",
                 "attested_by", "attested_on")
ATTEST_EVIDENCE_MAX = 300
# Set only by evals/check_attestations.py, in-process, to prove its checks bite:
#   cover-anything   an attestation covers any citation of the same advisory and item
#   no-stale         an attestation matching no citation is accepted
#   no-still-needed  an attestation of a citation the matcher places is accepted
#   no-dup           a duplicated entry is accepted
_MUTATE = None
DEFAULT_RECORDS_DIR = ROOT / "data" / "records_merged"
ADVISORIES_DIR = ROOT / "data" / "advisories"
ADVISORY_LIST = ROOT / "evals" / "golden" / "advisory_list.json"

BASELINE_NOTE = ("record citations never re-verified after week 1; pinned 2026-09-25 "
                  "pending an owner decision on remediation; an entry is removed only in "
                  "the commit that fixes it; re-measured 2026-09-25 after the ELLIPSIS and "
                  "SPANS tiers; was 103")


# ---------------------------------------------------------------------------
# Two-argument form: one record against one PDF, verbose. Week 1's form, plus the ARTEFACT tier (2026-09-25).
# ---------------------------------------------------------------------------

def check_record(record_path, pdf_path, verbose: bool = True):
    """Check one record against one PDF. Returns (checked, exact, spacing, artefact, off_page, missing).

    "artefact" counts every tier past spacing -- artefact and ellipsis -- so the tuple
    keeps its shape; the verbose line names the tier. Before 2026-09-25 an ellipsis
    hit fell through to MISSING here while --all (which asks hit.ok) accepted it.
    """
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    # The matching rule lives in schemas/citation_match.py, shared with the MCP
    # server and the review gate, so all three accept and refuse the same quotes.
    index = PageIndex.from_pdf(pdf_path)

    checked = 0
    exact = 0
    spacing = 0
    artefact = 0
    off_page = 0
    missing = 0
    for section in ("typologies", "actors", "indicators"):
        for item in record.get(section, []):
            label = item.get("label") or item.get("name") or item.get("description", "")[:60]
            for c in item.get("citations", []):
                checked += 1
                hit = index.locate(c["page"], c["quote"])
                if hit.status == EXACT:
                    exact += 1
                    status = "OK         "
                elif hit.status == SPACING:
                    spacing += 1
                    status = "OK-SPACING "
                elif hit.status == ARTEFACT:
                    artefact += 1
                    status = "OK-ARTEFACT"
                elif hit.status == ELLIPSIS:
                    # counted with the artefact tier in the summary; named per line
                    artefact += 1
                    status = "OK-%s" % hit.status.upper()
                elif hit.status == OFF_PAGE:
                    off_page += 1
                    status = "OFF-PAGE  (found on %s)" % list(hit.found_on)
                else:
                    missing += 1
                    status = "MISSING    "
                if verbose:
                    print("%s p%-3d %-10s %s" % (status, c["page"], section[:10], label[:60]))
                    if not hit.ok:
                        print("           quote: %r" % c["quote"][:140])
    return checked, exact, spacing, artefact, off_page, missing


def main(record_path: str, pdf_path: str) -> int:
    checked, exact, spacing, artefact, off_page, missing = check_record(record_path, pdf_path, verbose=True)

    print()
    print("citations checked: %d | exact on page: %d | on page modulo pypdf spacing: %d | "
          "on page modulo PDF artefacts, ellipses or a page break: %d | right quote wrong page: %d | not in document: %d"
          % (checked, exact, spacing, artefact, off_page, missing))
    if checked == 0:
        print("FAIL: no citations examined; a record with nothing to check is not a pass")
        return 1
    return 0 if missing == 0 and off_page == 0 else 1


# ---------------------------------------------------------------------------
# --all: the current defect set over every record, diffed against the baseline.
# ---------------------------------------------------------------------------

def _quote_sha256(quote: str) -> str:
    return hashlib.sha256(quote.encode("utf-8")).hexdigest()


def _label_for(item: dict) -> str:
    return item.get("label") or item.get("name") or item.get("description", "")[:60]


def attestation_identity(e: dict) -> tuple:
    return (e["advisory_id"], e["section"], e["item"], e["page"], e["quote_sha256"])


def load_attestations(path: Path = ATTESTED_PATH):
    """(entries, problems). No file is no attestations. Every entry is schema-checked."""
    if not path.exists():
        return [], []
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("attested")
    except (ValueError, AttributeError) as exc:
        return [], ["%s is not a JSON object with an 'attested' list: %s" % (path.name, exc)]
    if not isinstance(entries, list):
        return [], ["%s: 'attested' is not a list" % path.name]
    problems, good = [], []
    for n, e in enumerate(entries):
        where = "attested[%d]" % n
        if not isinstance(e, dict) or set(e) != set(ATTEST_FIELDS):
            problems.append("%s: fields must be exactly %s" % (where, ", ".join(ATTEST_FIELDS)))
            continue
        bad = []
        if e["reason"] not in ATTEST_REASONS:
            bad.append("reason %r is not one of %s" % (e["reason"], ", ".join(ATTEST_REASONS)))
        if not isinstance(e["evidence"], str) or not e["evidence"].strip() or len(e["evidence"]) > ATTEST_EVIDENCE_MAX:
            bad.append("evidence must be a non-empty excerpt of at most %d characters" % ATTEST_EVIDENCE_MAX)
        if e["attested_by"] != "owner":
            bad.append("attested_by must be 'owner', not %r" % e["attested_by"])
        if not isinstance(e["page"], int) or not re.fullmatch(r"[0-9a-f]{64}", str(e["quote_sha256"])) \
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e["attested_on"])):
            bad.append("page must be an int, quote_sha256 64 hex, attested_on YYYY-MM-DD")
        if bad:
            problems.append("%s (%s p%s): %s" % (where, e["advisory_id"], e["page"], "; ".join(bad)))
        else:
            good.append(e)
    seen = Counter(attestation_identity(e) for e in good)
    if _MUTATE != "no-dup":
        for ident, k in sorted(seen.items()):
            if k > 1:
                problems.append("attestation appears twice (x%d): %s %s %r p%d" % (k, ident[0], ident[1], ident[2][:40], ident[3]))
    return good, problems


def _attest_key(ident: tuple) -> tuple:
    if _MUTATE == "cover-anything":
        return (ident[0], ident[2])
    return ident


def check_record_citations(advisory_id: str, record: dict, index) -> list:
    """[(identity, ok, defect-or-None)] for every citation of one record, in record order."""
    out = []
    for section in ("typologies", "actors", "indicators"):
        for item in record.get(section, []):
            label = _label_for(item)
            for c in item.get("citations", []):
                ident = (advisory_id, section, label, c["page"], _quote_sha256(c["quote"]))
                hit = index.locate(c["page"], c["quote"])
                if hit.ok:  # exact, spacing, artefact or ellipsis -- the matcher decides, not a list here
                    out.append((ident, True, None))
                    continue
                if hit.status == OFF_PAGE:
                    kind, found_on = "off_page", sorted(hit.found_on)
                else:
                    kind, found_on = "missing", []
                out.append((ident, False, {
                    "advisory_id": advisory_id, "section": section, "item": label, "page": c["page"],
                    "quote_sha256": ident[4], "kind": kind, "found_on": found_on}))
    return out


def apply_attestations(checked: list, attested: list, unchecked=()):
    """(defects, n_attested, problems): attested citations leave the defects; bad entries are problems.

    An entry covers ONE citation, by its full identity. Entries for an advisory in
    `unchecked` (its PDF is not on this machine) are not judged either way.
    """
    keys = {}
    for e in attested:
        keys.setdefault(_attest_key(attestation_identity(e)), e)
    used, defects, problems, n = set(), [], [], 0
    for ident, ok, defect in checked:
        k = _attest_key(ident)
        if k in keys:
            used.add(k)
            if ok and _MUTATE != "no-still-needed":
                problems.append("attestation no longer needed -- remove it: %s %s %r p%d (the matcher places it)"
                                % (ident[0], ident[1], ident[2][:40], ident[3]))
            elif not ok:
                n += 1
            continue
        if defect is not None:
            defects.append(defect)
    if _MUTATE != "no-stale":
        for k, e in sorted(keys.items(), key=lambda kv: attestation_identity(kv[1])):
            if k not in used and e["advisory_id"] not in unchecked:
                problems.append("stale attestation: %s %s %r p%d matches no citation in the records"
                                % (e["advisory_id"], e["section"], e["item"][:40], e["page"]))
    return defects, n, problems


def compute_current_defects(records_dir: Path, attested=None):
    """Returns (defects, total_checked, missing_pdf_advisory_ids, (n_attested, attestation_problems)).

    defects is a list of dicts: advisory_id, section, item, page, quote_sha256,
    kind ("off_page"|"missing"), found_on (list of pages, [] for missing).
    A record whose PDF is not on this machine contributes nothing to defects
    or total_checked and is reported separately in missing_pdf_advisory_ids --
    an incomplete measurement is never silently folded into a complete one.
    """
    by_id = {a["advisory_id"]: a for a in
              json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}

    checked = []
    missing_pdfs = []
    total_checked = 0
    for record_path in sorted(records_dir.glob("ADV-*.json")):
        advisory_id = record_path.stem
        entry = by_id.get(advisory_id)
        if entry is None:
            missing_pdfs.append(advisory_id)
            continue
        pdf_path = ADVISORIES_DIR / Path(entry["file"]).name
        if not pdf_path.exists():
            missing_pdfs.append(advisory_id)
            continue

        record = json.loads(record_path.read_text(encoding="utf-8"))
        rows = check_record_citations(advisory_id, record, PageIndex.from_pdf(pdf_path))
        total_checked += len(rows)
        checked += rows
    if attested is None:
        attested, problems = load_attestations()
    else:
        problems = []
    defects, n_attested, more = apply_attestations(checked, attested, unchecked=set(missing_pdfs))
    return defects, total_checked, missing_pdfs, (n_attested, problems + more)


def _sort_key(d: dict):
    return (d["advisory_id"], d["section"], d["item"], d["page"], d["quote_sha256"])


def _identity(d: dict):
    return (d["advisory_id"], d["section"], d["item"], d["page"], d["quote_sha256"], d["kind"])


def _describe(d: dict) -> str:
    tail = " -- found on %s" % d["found_on"] if d.get("found_on") else ""
    return "%s %-10s %-42s p%-3d %s%s" % (
        d["advisory_id"], d["section"], d["item"][:42], d["page"], d["kind"], tail)


def load_baseline() -> list:
    if not BASELINE_PATH.exists():
        return []
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("defects", [])


def write_baseline(defects: list) -> None:
    payload = {"note": BASELINE_NOTE, "defects": sorted(defects, key=_sort_key)}
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main_all(records_dir: Path = DEFAULT_RECORDS_DIR, write_baseline_flag: bool = False) -> int:
    defects, total_checked, missing_pdfs, (n_attested, attest_problems) = compute_current_defects(records_dir)

    for problem in attest_problems:
        print("ATTESTATION REFUSED: %s" % problem)
    if attest_problems:
        print("\ncitations: %s is refused (%d problem%s); nothing was compared against the baseline"
              % (ATTESTED_PATH.relative_to(ROOT), len(attest_problems), "" if len(attest_problems) == 1 else "s"))
        return 1

    if write_baseline_flag:
        write_baseline(defects)
        print("wrote %d defects to %s" % (len(defects), BASELINE_PATH.relative_to(ROOT)))
        return 0

    if missing_pdfs:
        for advisory_id in missing_pdfs:
            print("%-16s NEEDS-PDFS  PDF not on this machine (data/advisories/ is gitignored)"
                  % advisory_id)
        print("\ncitations: NEEDS-PDFS -- %d advisor%s could not be checked; nothing was compared "
              "against the baseline"
              % (len(missing_pdfs), "y" if len(missing_pdfs) == 1 else "ies"))
        return 2

    baseline = load_baseline()
    baseline_counts = Counter(_identity(d) for d in baseline)
    current_counts = Counter(_identity(d) for d in defects)
    by_identity = {}
    for d in baseline + defects:
        by_identity.setdefault(_identity(d), d)

    new_counts = current_counts - baseline_counts
    fixed_counts = baseline_counts - current_counts

    for key in sorted(new_counts):
        n = new_counts[key]
        print("NEW defect%s: %s" % (" (x%d)" % n if n > 1 else "", _describe(by_identity[key])))
    for key in sorted(fixed_counts):
        n = fixed_counts[key]
        print("FIXED (remove from baseline)%s: %s" % (
            " (x%d)" % n if n > 1 else "", _describe(by_identity[key])))

    n_new = sum(new_counts.values())
    n_fixed = sum(fixed_counts.values())
    print("\ncitations: %d checked, %d verified by attestation, %d known defects pinned, %d new, %d fixed"
          % (total_checked, n_attested, len(baseline), n_new, n_fixed))
    return 1 if (n_new or n_fixed) else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "--all":
        rest = argv[1:]
        records_dir = DEFAULT_RECORDS_DIR
        write_flag = False
        i = 0
        while i < len(rest):
            if rest[i] == "--records-dir" and i + 1 < len(rest):
                records_dir = Path(rest[i + 1])
                i += 2
            elif rest[i] == "--write-baseline":
                write_flag = True
                i += 1
            else:
                print("unknown argument for --all: %s" % rest[i])
                sys.exit(2)
        sys.exit(main_all(records_dir, write_flag))
    if len(argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(argv[0], argv[1]))
