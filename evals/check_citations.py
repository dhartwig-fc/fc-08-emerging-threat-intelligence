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
3 are on another page and are now off_page. 103 remain (78 off_page, 25 missing);
the baseline file is the live number, not this paragraph.

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

--records-dir (hidden; not for interactive use) points the defect computation
at a different directory of ADV-*.json records instead of data/records_merged.
It exists solely so a guard on this guard can run --all against a temporary,
mutated COPY of the records without ever touching the real ones, while still
diffing against the real tracked baseline.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import ARTEFACT, EXACT, OFF_PAGE, SPACING, PageIndex  # noqa: E402

BASELINE_PATH = ROOT / "evals" / "known_citation_defects.json"
DEFAULT_RECORDS_DIR = ROOT / "data" / "records_merged"
ADVISORIES_DIR = ROOT / "data" / "advisories"
ADVISORY_LIST = ROOT / "evals" / "golden" / "advisory_list.json"

BASELINE_NOTE = ("record citations never re-verified after week 1; pinned 2026-09-25 "
                  "pending an owner decision on remediation; an entry is removed only in "
                  "the commit that fixes it; re-measured 2026-09-25 after the matcher gained "
                  "the ARTEFACT tier (footnote digits, line-break hyphens); was 118")


# ---------------------------------------------------------------------------
# Two-argument form: one record against one PDF, verbose. Unchanged since week 1.
# ---------------------------------------------------------------------------

def check_record(record_path, pdf_path, verbose: bool = True):
    """Check one record against one PDF. Returns (checked, exact, spacing, artefact, off_page, missing)."""
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
                    status = "OK       "
                elif hit.status == SPACING:
                    spacing += 1
                    status = "OK-SPACING"
                elif hit.status == ARTEFACT:
                    artefact += 1
                    status = "OK-ARTEFACT"
                elif hit.status == OFF_PAGE:
                    off_page += 1
                    status = "OFF-PAGE  (found on %s)" % list(hit.found_on)
                else:
                    missing += 1
                    status = "MISSING  "
                if verbose:
                    print("%s p%-3d %-10s %s" % (status, c["page"], section[:10], label[:60]))
                    if not hit.ok:
                        print("           quote: %r" % c["quote"][:140])
    return checked, exact, spacing, artefact, off_page, missing


def main(record_path: str, pdf_path: str) -> int:
    checked, exact, spacing, artefact, off_page, missing = check_record(record_path, pdf_path, verbose=True)

    print()
    print("citations checked: %d | exact on page: %d | on page modulo pypdf spacing: %d | "
          "on page modulo PDF artefacts: %d | right quote wrong page: %d | not in document: %d"
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


def compute_current_defects(records_dir: Path):
    """Returns (defects, total_checked, missing_pdf_advisory_ids).

    defects is a list of dicts: advisory_id, section, item, page, quote_sha256,
    kind ("off_page"|"missing"), found_on (list of pages, [] for missing).
    A record whose PDF is not on this machine contributes nothing to defects
    or total_checked and is reported separately in missing_pdf_advisory_ids --
    an incomplete measurement is never silently folded into a complete one.
    """
    by_id = {a["advisory_id"]: a for a in
              json.loads(ADVISORY_LIST.read_text(encoding="utf-8"))["advisories"]}

    defects = []
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
        index = PageIndex.from_pdf(pdf_path)
        for section in ("typologies", "actors", "indicators"):
            for item in record.get(section, []):
                label = _label_for(item)
                for c in item.get("citations", []):
                    total_checked += 1
                    hit = index.locate(c["page"], c["quote"])
                    if hit.ok:  # exact, spacing or artefact -- the matcher decides, not a list here
                        continue
                    if hit.status == OFF_PAGE:
                        kind, found_on = "off_page", sorted(hit.found_on)
                    else:
                        kind, found_on = "missing", []
                    defects.append({
                        "advisory_id": advisory_id,
                        "section": section,
                        "item": label,
                        "page": c["page"],
                        "quote_sha256": _quote_sha256(c["quote"]),
                        "kind": kind,
                        "found_on": found_on,
                    })
    return defects, total_checked, missing_pdfs


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
    defects, total_checked, missing_pdfs = compute_current_defects(records_dir)

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
    print("\ncitations: %d checked, %d known defects pinned, %d new, %d fixed"
          % (total_checked, len(baseline), n_new, n_fixed))
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
