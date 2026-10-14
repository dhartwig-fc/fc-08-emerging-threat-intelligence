"""
The staleness gate for the regulatory-scan demo: is the committed page ahead of what was published?

Mirrors evals/check_published_walkthrough.py exactly, for tools/build_scan_demo.py's page, published by
tools/publish_scan_demo.py to projects/nexus/threat-intel/scan.html with its sha256 in site/SCAN_PUBLISHED.

Usage:
    python evals/check_published_scan_demo.py --cold          # cold half only (site/SCAN_PUBLISHED vs the page)
    python evals/check_published_scan_demo.py                 # also compares the portfolio's COMMITTED copy
    python evals/check_published_scan_demo.py --portfolio PATH

cold half      -- if site/SCAN_PUBLISHED holds a sha256, it must equal the committed page's.
portfolio half -- the copy the portfolio has COMMITTED (`git show HEAD:...`, never the file on disk) must be
                  byte-identical to the committed page. Skipped, not failed, before the first publish.
Read-only. Without --cold, a missing portfolio checkout prints NOT RUN and exits 2 (class needs-portfolio).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# The publisher owns where the page goes and where its sha is recorded; the builder owns where the page is.
import build_scan_demo as bw  # noqa: E402
from publish_scan_demo import DEFAULT_PORTFOLIO, DEST_REL, PUBLISHED as PUBLISHED_PATH  # noqa: E402

PAGE_PATH = bw.OUT

NOT_COMMITTED = "the page is not committed in the portfolio"
COPY_DIFFERS = "the published copy differs from the committed page"
PAGE_CHANGED = "the committed page changed since it was published"


def is_git_root(portfolio: Path) -> bool:
    """True when portfolio is the top level of a git working tree (not merely somewhere inside one)."""
    try:
        r = subprocess.run(["git", "-C", str(portfolio), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
    except OSError:
        return False
    return r.returncode == 0 and Path(r.stdout.strip()).resolve() == portfolio.resolve()


def committed_copy(portfolio: Path) -> Optional[bytes]:
    """The page's bytes as the portfolio's HEAD commit holds them, or None when HEAD does not hold it."""
    r = subprocess.run(["git", "-C", str(portfolio), "show", "HEAD:%s" % DEST_REL.as_posix()], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def gate(page_path: Path, published_path: Path, portfolio: Optional[Path]) -> List[str]:
    """Problems with what has been published, or []. Never writes anything."""
    problems: List[str] = []
    if not published_path.exists():
        return problems  # never published: nothing to be stale (cold and portfolio halves both moot)

    page_bytes = page_path.read_bytes()
    published_sha = published_path.read_text(encoding="utf-8").strip()
    committed_sha = hashlib.sha256(page_bytes).hexdigest()
    if published_sha != committed_sha:
        problems.append(PAGE_CHANGED + ": republish it: "
                        "python tools/publish_scan_demo.py, then commit site/SCAN_PUBLISHED with the page")

    if portfolio is not None:
        held = committed_copy(portfolio)
        if held != page_bytes:
            dest = portfolio / DEST_REL
            commit = "git -C %s add %s && git -C %s commit" % (shlex.quote(str(portfolio)), DEST_REL.as_posix(),
                                                                shlex.quote(str(portfolio)))
            if dest.exists() and dest.read_bytes() == page_bytes:
                problems.append("%s (%s): %s" % (NOT_COMMITTED, "its HEAD holds other bytes" if held is not None
                                                 else "its HEAD does not hold it", commit))
            else:
                problems.append("%s: republish it (python tools/publish_scan_demo.py), then %s"
                                % (COPY_DIFFERS, commit))

    return problems


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="The regulatory scan demo's staleness gate")
    ap.add_argument("--cold", action="store_true", help="cold half only: skip the portfolio comparison")
    ap.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
    args = ap.parse_args(argv)

    portfolio = None
    if not args.cold:
        portfolio = Path(os.path.expanduser(args.portfolio))
        if not (portfolio / "projects" / "nexus").is_dir():
            print("NOT RUN: no portfolio checkout at %s" % portfolio.name)
            return 2
        if not is_git_root(portfolio):
            print("NOT RUN: %s is not the root of a git repository, so it has no committed copy to compare"
                  % portfolio.name)
            return 2

    if not PUBLISHED_PATH.exists():
        print("never published: nothing to be stale" if args.cold else "never published")
        return 0

    problems = gate(PAGE_PATH, PUBLISHED_PATH, portfolio)
    for p in problems:
        print("FAIL  %s" % p)
    if not problems:
        print("HOLDS: the portfolio's committed copy matches the committed page" if portfolio is not None
              else "HOLDS (cold): site/SCAN_PUBLISHED still names the committed page's sha256")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
