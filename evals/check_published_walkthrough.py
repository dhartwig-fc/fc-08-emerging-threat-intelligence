"""
The staleness gate: is the committed walkthrough page ahead of what was published?

Usage:
    python evals/check_published_walkthrough.py --cold          # cold half only (site/PUBLISHED vs the page)
    python evals/check_published_walkthrough.py                 # also compares against the portfolio checkout
    python evals/check_published_walkthrough.py --portfolio PATH

WHAT IT CHECKS (see gate()):
  cold half      -- if site/PUBLISHED holds a sha256, it must equal the committed page's. A rule that
                     compared bytes instead would need the portfolio checkout even to run cold.
  portfolio half -- if site/PUBLISHED exists, the portfolio's copy must be byte-identical to the
                     committed page. Skipped, not failed, when nothing has ever been published --
                     a rule that failed whenever the portfolio lacked the page would block every
                     commit to this repo until the first publish (Plan ruling 2).

Read-only: this gate never writes to the portfolio checkout, published or not. Only
tools/publish_walkthrough.py writes there, and only on an explicit, confirmed publish.

Without --cold, a missing portfolio checkout (no <portfolio>/projects/nexus/) is NOT a failure --
it means the check cannot run here. It prints NOT RUN and exits 2; check_all.py classes this guard
needs-portfolio for that reason.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGE_PATH = ROOT / "site" / "threat-intel" / "index.html"
PUBLISHED_PATH = ROOT / "site" / "PUBLISHED"
DEST_REL = Path("projects") / "nexus" / "threat-intel" / "index.html"
DEFAULT_PORTFOLIO = os.environ.get("NEXUS_PORTFOLIO", "~/Cowork HB/dan-hartwig-portfolio")


def gate(page_path: Path, published_path: Path, portfolio: Optional[Path]) -> List[str]:
    """Problems with what has been published, or []. Never writes anything."""
    problems: List[str] = []
    if not published_path.exists():
        return problems  # never published: nothing to be stale (cold and portfolio halves both moot)

    page_bytes = page_path.read_bytes()
    published_sha = published_path.read_text(encoding="utf-8").strip()
    committed_sha = hashlib.sha256(page_bytes).hexdigest()
    if published_sha != committed_sha:
        problems.append("the committed page changed since it was published: republish it")

    if portfolio is not None:
        dest = portfolio / DEST_REL
        if not dest.exists() or dest.read_bytes() != page_bytes:
            problems.append("the published copy differs from the committed page")

    return problems


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="The walkthrough's staleness gate")
    ap.add_argument("--cold", action="store_true", help="cold half only: skip the portfolio comparison")
    ap.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
    args = ap.parse_args(argv)

    portfolio = None
    if not args.cold:
        portfolio = Path(os.path.expanduser(args.portfolio))
        if not (portfolio / "projects" / "nexus").is_dir():
            print("NOT RUN: no portfolio checkout at %s" % portfolio.name)
            return 2

    if not PUBLISHED_PATH.exists():
        print("never published: nothing to be stale" if args.cold else "never published")
        return 0

    problems = gate(PAGE_PATH, PUBLISHED_PATH, portfolio)
    for p in problems:
        print("FAIL  %s" % p)
    if not problems:
        print("HOLDS: the published copy matches the committed page" if portfolio is not None
              else "HOLDS (cold): site/PUBLISHED still names the committed page's sha256")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
