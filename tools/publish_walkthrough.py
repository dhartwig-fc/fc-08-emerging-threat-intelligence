"""
Publish the threat-intelligence walkthrough to the portfolio working tree.

Usage:
    python tools/publish_walkthrough.py --portfolio <path>

Steps, and each one refuses rather than guessing:
  1. rebuild the page in memory and require it to equal the committed
     site/threat-intel/index.html (commit first; never publish an uncommitted page);
  2. run the publish boundary on it;
  3. require <portfolio>/projects/nexus/ to exist (a wrong root is the typo that matters);
  4. write <portfolio>/projects/nexus/threat-intel/index.html (creating threat-intel/ only);
  5. write site/PUBLISHED with the page's sha256, which the staleness gate reads.
It never commits or pushes either repository.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_walkthrough as bw  # noqa: E402
from governance import publish_boundary as pb  # noqa: E402

PUBLISHED = ROOT / "site" / "PUBLISHED"
DEST_REL = Path("projects") / "nexus" / "threat-intel" / "index.html"
DEFAULT_PORTFOLIO = os.environ.get("NEXUS_PORTFOLIO", "~/Cowork HB/dan-hartwig-portfolio")


def publish(portfolio: Path) -> int:
    page = bw.build(bw.inputs())
    if not bw.OUT.exists() or bw.OUT.read_text(encoding="utf-8") != page:
        print("REFUSED: the committed page differs from a fresh build; rebuild and commit it first", file=sys.stderr)
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
    PUBLISHED.write_text(hashlib.sha256(page.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")
    print("published %s (%d bytes); recorded in site/PUBLISHED" % (DEST_REL.as_posix(), len(page.encode("utf-8"))))
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Publish the walkthrough to the portfolio working tree")
    ap.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
    args = ap.parse_args(argv)
    return publish(Path(os.path.expanduser(args.portfolio)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
