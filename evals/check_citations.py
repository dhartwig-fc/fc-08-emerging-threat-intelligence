"""
Week-1 review helper: does every citation in an AdvisoryRecord point at text that
actually exists on the page it names?

Usage:
    python check_citations.py <record.json> <advisory.pdf>

This is the mechanical half of "read the record against the PDF". It does NOT
judge whether the typology mapping is right; it only proves each quote is real.
The plan's week-4 reviewer subagent does the same check inside the pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.citation_match import EXACT, OFF_PAGE, SPACING, PageIndex  # noqa: E402


def main(record_path: str, pdf_path: str) -> int:
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    # The matching rule lives in schemas/citation_match.py, shared with the MCP
    # server and the review gate, so all three accept and refuse the same quotes.
    index = PageIndex.from_pdf(pdf_path)

    checked = 0
    exact = 0
    spacing = 0
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
                elif hit.status == OFF_PAGE:
                    off_page += 1
                    status = "OFF-PAGE  (found on %s)" % list(hit.found_on)
                else:
                    missing += 1
                    status = "MISSING  "
                print("%s p%-3d %-10s %s" % (status, c["page"], section[:10], label[:60]))
                if not hit.ok:
                    print("           quote: %r" % c["quote"][:140])

    print()
    print("citations checked: %d | exact on page: %d | on page modulo pypdf spacing: %d | "
          "right quote wrong page: %d | not in document: %d"
          % (checked, exact, spacing, off_page, missing))
    if checked == 0:
        print("FAIL: no citations examined; a record with nothing to check is not a pass")
        return 1
    return 0 if missing == 0 and off_page == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
