"""
Publish the threat-intelligence walkthrough to the portfolio working tree.

Usage:
    python tools/publish_walkthrough.py --portfolio <path>      # default: $NEXUS_PORTFOLIO, else the usual checkout

fc-08 owns the portfolio's projects/nexus/threat-intel/: this script is its only writer and
evals/check_published_walkthrough.py its staleness gate. (The environment variable is
NEXUS_PORTFOLIO; fc-10's publishers use NEXUS_PORTFOLIO_ROOT for the same checkout.)

A publish is NOT finished when this script returns. It writes two files and commits neither:
the page into the portfolio's working tree, and site/PUBLISHED here. The live site serves what
the portfolio COMMITS and pushes, so the page must be added and committed in the portfolio, and
only then site/PUBLISHED committed here -- the staleness gate compares the portfolio's HEAD copy,
and the pre-commit hook refuses site/PUBLISHED until that copy matches. The full sequence, in the
order that lets every hook pass, is in CLAUDE.md ("The publish procedure"); the script prints the
remaining steps when it succeeds.

OBLIGATION, once site/PUBLISHED exists (i.e. after the first publish): a page
rebuilt by tools/build_walkthrough.py must be republished, committed in the
portfolio, and site/PUBLISHED committed TOGETHER WITH the rebuilt page, BEFORE
the next commit here. evals/check_published_walkthrough.py runs inside
tools/check_all.py, which the pre-commit hook runs on every commit -- not only
ones touching the walkthrough -- so a rebuilt, unrepublished page refuses ALL of
them until this script is run and both commits are made.

Steps, and each one refuses rather than guessing:
  1. rebuild the page in memory and require it to equal site/threat-intel/index.html on disk
     (a page that differs from a fresh build is refused). It deliberately does NOT require the page
     to be committed: on a republish the rebuilt page cannot be committed first -- the gate would
     refuse that commit, because site/PUBLISHED still names the old page -- so the page and
     site/PUBLISHED are committed together, after this script runs;
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
import shlex
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
        shown = bw.OUT.relative_to(ROOT).as_posix() if bw.OUT.is_relative_to(ROOT) else str(bw.OUT)
        print("REFUSED: %s differs from a fresh build; run tools/build_walkthrough.py first" % shown,
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
    print("published %s (%d bytes); recorded sha256 %s in site/PUBLISHED"
          % (DEST_REL.as_posix(), len(page.encode("utf-8")), sha))
    print(next_steps(portfolio, sha))
    return 0


def next_steps(portfolio: Path, sha: str) -> str:
    """What is still to do: nothing is live, and nothing is committed, when publish() returns."""
    q, dest = shlex.quote(str(portfolio)), DEST_REL.as_posix()
    return "\n".join([
        "NOT FINISHED: nothing is committed in either repository. Steps 2-7 of CLAUDE.md's publish procedure, in order:",
        "  2. open %s at 375px and at desktop width; follow the back link and the trace links" % dest,
        "  3. first publish only: git -C %s merge --ff-only fc08-slice1-publish" % q,
        "  4. git -C %s add %s && git -C %s commit" % (q, dest, q),
        "  5. git -C %s show HEAD:%s | shasum -a 256    # must print %s" % (q, dest, sha),
        "  6. here: git add site/PUBLISHED (and the rebuilt page, on a republish) && git commit",
        "     -- the pre-commit hook refuses this commit until step 4 is done",
        "  7. push this repository, then the portfolio; follow the live link",
    ])


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Publish the walkthrough to the portfolio working tree")
    ap.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
    args = ap.parse_args(argv)
    return publish(Path(os.path.expanduser(args.portfolio)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
