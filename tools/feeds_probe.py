"""
Live probe: fetch each source's listing once, through the allowlisted fetch, and parse it.

Usage:
    python tools/feeds_probe.py

NETWORK. This is the one tool in sub-project A that makes requests; no guard calls it and
tools/check_all.py never runs it. It writes nothing. It answers one question -- does each adapter
still parse its LIVE listing -- and exits 1 naming the source when a layout changed or a source is
unreachable. Run it by hand before trusting a change to feeds/sources.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds import http as feeds_http  # noqa: E402
from feeds.model import LayoutChanged  # noqa: E402
from feeds.sources import MAX_LISTING_BYTES, SOURCES  # noqa: E402


def main() -> int:
    failed = 0
    for name in sorted(SOURCES):
        src = SOURCES[name]
        try:
            got = feeds_http.get(src.listing_url, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                                 max_bytes=MAX_LISTING_BYTES)
            items = src.parse(got.body)
        except (feeds_http.FetchRefused, LayoutChanged) as exc:
            print("  FAIL %-6s %s" % (name, exc))
            failed += 1
            continue
        print("  OK   %-6s %2d items, newest %s, oldest %s (%d bytes)" % (
            name, len(items), max(i.published for i in items), min(i.published for i in items), len(got.body)))
    print("\n%s" % ("ALL SOURCES PARSE" if not failed else "%d SOURCE(S) FAILED" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
