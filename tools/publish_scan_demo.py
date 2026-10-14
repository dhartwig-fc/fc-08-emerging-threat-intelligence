"""
Publish the regulatory-scan demo page to the portfolio working tree.

Usage:
    python tools/publish_scan_demo.py --portfolio <path>      # default: $NEXUS_PORTFOLIO, else the usual checkout

The page is tools/build_scan_demo.py's (site/scan-demo/index.html); it lands beside the walkthrough at
projects/nexus/threat-intel/scan.html, which fc-08 owns. This script is its only writer and
evals/check_published_scan_demo.py its staleness gate. Same contract as tools/publish_walkthrough.py, which
it mirrors: refuse a page that is not a fresh build, refuse one that crosses the publish boundary, refuse a
wrong portfolio root, then write the page and site/SCAN_PUBLISHED (its sha256). It never commits or pushes;
a publish is finished when the portfolio has COMMITTED the page and both repositories are pushed.

OBLIGATION, once site/SCAN_PUBLISHED exists: a page rebuilt by tools/build_scan_demo.py must be republished,
committed in the portfolio, and site/SCAN_PUBLISHED committed TOGETHER WITH the rebuilt page, before the next
commit here -- the gate runs in tools/check_all.py on every commit.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_scan_demo as bw  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402

PUBLISHED = ROOT / "site" / "SCAN_PUBLISHED"
DEST_REL = Path("projects") / "nexus" / "threat-intel" / "scan.html"
DEFAULT_PORTFOLIO = os.environ.get("NEXUS_PORTFOLIO", "~/Cowork HB/dan-hartwig-portfolio")


def publish(portfolio: Path) -> int:
    page = bw.build(bw.inputs())
    if not bw.OUT.exists() or bw.OUT.read_text(encoding="utf-8") != page:
        shown = bw.OUT.relative_to(ROOT).as_posix() if bw.OUT.is_relative_to(ROOT) else str(bw.OUT)
        print("REFUSED: %s differs from a fresh build; run tools/build_scan_demo.py first" % shown,
              file=sys.stderr)
        return 1
    bad = pb.violations(page)
    if bad:
        print("REFUSED: the page crosses the publish boundary: %s" % ", ".join(bad), file=sys.stderr)
        return 1
    nexus = portfolio / "projects" / "nexus"
    if not nexus.is_dir():
        print("REFUSED: %s has no projects/nexus/ -- is this the portfolio root?" % portfolio.name, file=sys.stderr)
        return 2
    dest = portfolio / DEST_REL
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    sha = hashlib.sha256(page.encode("utf-8")).hexdigest()
    PUBLISHED.write_text(sha + "\n", encoding="utf-8")
    print("published %s (%d bytes); recorded sha256 %s in site/SCAN_PUBLISHED"
          % (DEST_REL.as_posix(), len(page.encode("utf-8")), sha))
    print(next_steps(portfolio, sha))
    return 0


def next_steps(portfolio: Path, sha: str) -> str:
    """What is still to do: nothing is live, and nothing is committed, when publish() returns."""
    q, dest = shlex.quote(str(portfolio)), DEST_REL.as_posix()
    return "\n".join([
        "NOT FINISHED: nothing is committed in either repository. Remaining steps, in order:",
        "  2. open %s at 375px and at desktop width; play the replay; follow the walkthrough and NEXUS links" % dest,
        "  3. git -C %s add %s && git -C %s commit" % (q, dest, q),
        "  4. git -C %s show HEAD:%s | shasum -a 256    # must print %s" % (q, dest, sha),
        "  5. here: git add site/SCAN_PUBLISHED (and the rebuilt page, on a republish) && git commit",
        "     -- the pre-commit hook refuses this commit until step 4 is done",
        "  6. push this repository, then the portfolio; follow the live link",
    ])


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Publish the regulatory scan demo to the portfolio working tree")
    ap.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
    args = ap.parse_args(argv)
    return publish(Path(os.path.expanduser(args.portfolio)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
