"""
Mutation-verify tools/publish_walkthrough.py -- against TEMPORARY portfolio
directories only. Never touches the real portfolio checkout, never writes the
real site/PUBLISHED.

Usage:
    python evals/check_publisher.py
    python evals/check_publisher.py --mutate skip-boundary    # the publisher skips pb.violations; MUST fail
    python evals/check_publisher.py --mutate skip-freshness   # the publisher skips the committed-equals-fresh
                                                                # step; MUST fail
    python evals/check_publisher.py --mutate disk-only        # the gate reads the portfolio's on-disk file, not
                                                                # its committed HEAD copy; MUST fail

WHAT IT CHECKS:
  - a publish into a temp portfolio writes the page byte-identical to the committed
    site/threat-intel/index.html, and records its sha256 in a redirected PUBLISHED file;
  - the temp portfolio is a GIT REPOSITORY (git init + an initial commit of projects/nexus/),
    because the live site serves what the portfolio COMMITS, not what sits on its disk.
    evals.check_published_walkthrough.gate() FAILS right after that publish -- the page is on
    disk but untracked, which is exactly the state that would push a link to a 404 -- and
    names the portfolio add+commit step; it HOLDS once the page is added and committed in the
    temp repository; it FAILS when the portfolio commits a copy that differs by one byte; and
    it FAILS (cold half) when the temp PUBLISHED file names a different sha;
  - main() reports NOT RUN (exit 2) for a portfolio directory that is not a git repository:
    without a HEAD there is no committed copy to compare, and passing would be a guess;
  - a portfolio root with no projects/nexus/ is refused with return 2, writing nothing;
  - a page that crosses the publish boundary is refused. The plant is put through the
    ADVISORY-TITLE input field (bw.inputs()["advisory"]["title"]), not the output: a plant
    in the output would just be overwritten by publish()'s own rebuild (the lesson fc-10
    already learned -- see fc-10's CLAUDE.md on mutation harnesses). inputs() validates
    several other fields (the advisory URL, document hashes, label_status, ...) but never
    the title, so prefixing it with "/Users/x " reaches the rendered page (sections 1 and
    2 both show it) without tripping any of inputs()'s own refusals;
  - a STALE committed page is refused. bw.OUT is redirected to a temp file holding a fresh
    build PLUS one extra HTML comment, so it differs from what bw.build(bw.inputs()) produces
    at publish() time: publish() must return 1 and write nothing, to either the temp portfolio
    or the temp PUBLISHED file. --mutate skip-freshness makes bw.build always return whatever
    bw.OUT currently holds, which trivially satisfies publish()'s own equality check without
    touching its source -- proving that check is load-bearing.

Every portfolio and PUBLISHED path used here is created under tempfile.mkdtemp() and torn
down afterward. tools/publish_walkthrough.PUBLISHED is monkeypatched to a temp file for the
duration of each check and always restored, so the real site/PUBLISHED is never written.

OFFLINE and COLD. Tracked inputs only, same as build_walkthrough / check_walkthrough.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_walkthrough as bw  # noqa: E402
import publish_walkthrough as pw  # noqa: E402
from evals import check_published_walkthrough as cpw  # noqa: E402

MUTATIONS = ("skip-boundary", "skip-freshness", "disk-only")
MUTATION = None


def _temp_portfolio(with_nexus: bool = True) -> Path:
    root = Path(tempfile.mkdtemp(prefix="fc08_check_publisher_portfolio_"))
    if with_nexus:
        (root / "projects" / "nexus").mkdir(parents=True)
    return root


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """git in a TEMP repository only; no hooks, no signing, a fixed identity, so the machine's own git
    configuration cannot change the outcome."""
    return subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                           "-c", "user.name=check_publisher", "-c", "user.email=check_publisher@localhost"]
                          + list(args), capture_output=True, text=True)


def _temp_git_portfolio() -> Path:
    """A temp portfolio that is a git repository: projects/nexus/ holds one file, committed."""
    root = _temp_portfolio()
    (root / "projects" / "nexus" / "future-capabilities.html").write_text("<p>placeholder</p>\n", encoding="utf-8")
    for args in (("init", "-q"), ("add", "projects/nexus"), ("commit", "-q", "-m", "initial")):
        r = _git(root, *args)
        if r.returncode != 0:
            raise RuntimeError("could not set up a temp git portfolio: git %s: %s" % (args[0], r.stderr.strip()))
    return root


def _commit_page(portfolio: Path, message: str) -> None:
    for args in (("add", pw.DEST_REL.as_posix()), ("commit", "-q", "-m", message)):
        r = _git(portfolio, *args)
        if r.returncode != 0:
            raise RuntimeError("git %s failed in the temp portfolio: %s" % (args[0], r.stderr.strip()))


def _temp_published() -> Path:
    return Path(tempfile.mkdtemp(prefix="fc08_check_publisher_site_")) / "PUBLISHED"


def _check_publish_and_gate() -> list:
    """A clean publish into a temp GIT portfolio, then gate() against it: untracked, committed,
    committed with different bytes, and the cold half."""
    out = []
    committed_page = bw.OUT.read_bytes()
    committed_sha = hashlib.sha256(committed_page).hexdigest()

    portfolio = _temp_git_portfolio()
    published = _temp_published()
    orig_published = pw.PUBLISHED
    pw.PUBLISHED = published
    try:
        rc = pw.publish(portfolio)
        dest = portfolio / pw.DEST_REL
        matches = dest.exists() and dest.read_bytes() == committed_page
        out.append((rc == 0 and matches,
                    "publish() writes the page byte-identical to the committed one into a temp portfolio",
                    "rc=%d dest_exists=%s matches=%s" % (rc, dest.exists(), matches)))

        recorded = published.read_text(encoding="utf-8").strip() if published.exists() else None
        out.append((recorded == committed_sha,
                    "publish() records the page's sha256 in the redirected PUBLISHED file",
                    "want %s; got %s" % (committed_sha, recorded)))

        # The defect this check exists for: the page is on the portfolio's disk, byte-identical, and
        # NOT committed there. Pushing the portfolio now would publish a link to a page it does not hold.
        problems = cpw.gate(bw.OUT, published, portfolio)
        out.append((any(p.startswith(cpw.NOT_COMMITTED) and "add %s" % pw.DEST_REL.as_posix() in p
                        and "commit" in p for p in problems),
                    "gate() FAILS right after publish(): the page is on the temp portfolio's disk but untracked, "
                    "and the failure names the add+commit step", str(problems)))

        _commit_page(portfolio, "the walkthrough")
        problems = cpw.gate(bw.OUT, published, portfolio)
        out.append((problems == [],
                    "gate() HOLDS once the page is added and committed in the temp portfolio", str(problems)))

        original_dest = dest.read_bytes()
        dest.write_bytes(original_dest[:-1] + bytes([original_dest[-1] ^ 0xFF]))
        _commit_page(portfolio, "one byte off")
        problems = cpw.gate(bw.OUT, published, portfolio)
        out.append((any(p.startswith(cpw.COPY_DIFFERS) for p in problems),
                    "gate() FAILS when the portfolio COMMITS a copy that differs by one byte", str(problems)))
        # A republish that is not re-committed: the disk is right again, HEAD still holds the old bytes.
        dest.write_bytes(original_dest)
        problems = cpw.gate(bw.OUT, published, portfolio)
        out.append((any(p.startswith(cpw.NOT_COMMITTED) and "HEAD holds other bytes" in p for p in problems),
                    "gate() FAILS when the right page is on disk but the portfolio's HEAD holds other bytes, "
                    "naming the commit step", str(problems)))
        _commit_page(portfolio, "restored")

        original_published = published.read_text(encoding="utf-8")
        published.write_text("0" * 64 + "\n", encoding="utf-8")
        problems = cpw.gate(bw.OUT, published, None)
        out.append((any(p.startswith(cpw.PAGE_CHANGED) for p in problems),
                    "gate() FAILS (cold half) when the temp PUBLISHED holds a different sha", str(problems)))
        published.write_text(original_published, encoding="utf-8")
    finally:
        pw.PUBLISHED = orig_published
        shutil.rmtree(portfolio, ignore_errors=True)
        shutil.rmtree(published.parent, ignore_errors=True)
    return out


def _check_not_a_git_repository() -> tuple:
    """main() cannot compare a committed copy in a directory with no HEAD: NOT RUN, exit 2."""
    portfolio = _temp_portfolio()
    try:
        rc = cpw.main(["--portfolio", str(portfolio)])
        return (rc == 2, "the gate reports NOT RUN (exit 2) for a portfolio that is not a git repository",
                "rc=%d" % rc)
    finally:
        shutil.rmtree(portfolio, ignore_errors=True)


def _check_missing_nexus() -> tuple:
    """A portfolio root with no projects/nexus/ is refused, and nothing is written."""
    portfolio = _temp_portfolio(with_nexus=False)
    published = _temp_published()
    orig_published = pw.PUBLISHED
    pw.PUBLISHED = published
    try:
        rc = pw.publish(portfolio)
        wrote_anything = any(portfolio.rglob("*")) or published.exists()
        return (rc == 2 and not wrote_anything,
                "a portfolio root with no projects/nexus/ is refused (return 2), writing nothing",
                "rc=%d portfolio_contents=%s published_exists=%s"
                % (rc, list(portfolio.rglob("*")), published.exists()))
    finally:
        pw.PUBLISHED = orig_published
        shutil.rmtree(portfolio, ignore_errors=True)
        shutil.rmtree(published.parent, ignore_errors=True)


def _check_boundary_refusal() -> tuple:
    """Plant a local path through the advisory-title INPUT field, not the output, so the
    committed-equals-fresh-build step passes honestly and the publish boundary is what
    refuses. Honors MUTATION == "skip-boundary" via the caller patching pw.pb.violations."""
    orig_inputs = bw.inputs
    orig_out = bw.OUT

    def mutated_inputs(*args, **kwargs):
        inp = orig_inputs(*args, **kwargs)
        inp["advisory"]["title"] = "/Users/x " + inp["advisory"]["title"]
        return inp

    tmp_dir = Path(tempfile.mkdtemp(prefix="fc08_check_publisher_boundary_"))
    tmp_out = tmp_dir / "index.html"
    portfolio = _temp_portfolio()
    published = _temp_published()
    orig_published = pw.PUBLISHED
    try:
        bw.inputs = mutated_inputs
        mutated_page = bw.build(bw.inputs())
        tmp_out.write_text(mutated_page, encoding="utf-8")
        bw.OUT = tmp_out
        pw.PUBLISHED = published

        rc = pw.publish(portfolio)
        dest = portfolio / pw.DEST_REL
        ok = rc == 1 and not dest.exists() and not published.exists()
        return (ok, "publish() refuses a page that crosses the boundary (planted via bw.inputs()['advisory']['title'])",
                "rc=%d dest_exists=%s published_exists=%s" % (rc, dest.exists(), published.exists()))
    finally:
        bw.inputs = orig_inputs
        bw.OUT = orig_out
        pw.PUBLISHED = orig_published
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(portfolio, ignore_errors=True)
        shutil.rmtree(published.parent, ignore_errors=True)


def _check_stale_page_refusal() -> tuple:
    """publish() must refuse (return 1) when the committed page is not a fresh build, writing
    nothing to either the portfolio or PUBLISHED. bw.OUT is redirected to a temp file holding
    a fresh build plus one extra marker, computed BEFORE bw.OUT or bw.build is touched, so the
    baseline itself is an honest fresh build. Honors MUTATION == "skip-freshness" by making
    bw.build always return whatever bw.OUT holds -- which makes publish()'s own
    `bw.OUT.read_text() != page` check vacuously false, without editing publish()'s source."""
    orig_out = bw.OUT
    orig_build = bw.build

    fresh_page = bw.build(bw.inputs())
    stale_page = fresh_page + "\n<!-- stale marker: not a fresh build -->\n"

    tmp_dir = Path(tempfile.mkdtemp(prefix="fc08_check_publisher_stale_"))
    tmp_out = tmp_dir / "index.html"
    tmp_out.write_text(stale_page, encoding="utf-8")
    portfolio = _temp_portfolio()
    published = _temp_published()
    orig_published = pw.PUBLISHED
    try:
        bw.OUT = tmp_out
        if MUTATION == "skip-freshness":
            bw.build = lambda inp: bw.OUT.read_text(encoding="utf-8")
        pw.PUBLISHED = published

        rc = pw.publish(portfolio)
        dest = portfolio / pw.DEST_REL
        ok = rc == 1 and not dest.exists() and not published.exists()
        return (ok, "publish() refuses (return 1) a stale committed page (OUT differs from a fresh "
                "build), writing nothing", "rc=%d dest_exists=%s published_exists=%s"
                % (rc, dest.exists(), published.exists()))
    finally:
        bw.OUT = orig_out
        bw.build = orig_build
        pw.PUBLISHED = orig_published
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(portfolio, ignore_errors=True)
        shutil.rmtree(published.parent, ignore_errors=True)


def checks() -> list:
    out = []
    orig_committed = cpw.committed_copy
    try:
        if MUTATION == "disk-only":
            # The defect the review found: a gate that reads the file on the portfolio's disk.
            cpw.committed_copy = lambda portfolio: ((portfolio / pw.DEST_REL).read_bytes()
                                                    if (portfolio / pw.DEST_REL).exists() else None)
        out += _check_publish_and_gate()
    finally:
        cpw.committed_copy = orig_committed
    out.append(_check_not_a_git_repository())
    out.append(_check_missing_nexus())
    out.append(_check_stale_page_refusal())

    orig_violations = pw.pb.violations
    try:
        if MUTATION == "skip-boundary":
            pw.pb.violations = lambda text: []
        out.append(_check_boundary_refusal())
    finally:
        pw.pb.violations = orig_violations
    return out


def main(argv: list) -> int:
    global MUTATION
    ap = argparse.ArgumentParser(description="Mutation-verify the publisher against temporary portfolios only")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule; the matching refusal check MUST fail")
    args = ap.parse_args(argv)
    MUTATION = args.mutate
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the rule is removed" if failures
                        else "NOTHING PROVED: it passed with the rule gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
