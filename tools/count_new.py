"""
Listing-only dry run (spec §6): fetch every source's listing, parse it, and count the items the seen-items ledger
does not yet hold. No agent runs, nothing is spent, nothing is written.

    python tools/count_new.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from feeds import http as feeds_http, ledger  # noqa: E402
from feeds.sources import MAX_LISTING_BYTES, ORDER, SOURCES  # noqa: E402


def current_items(name: str) -> list:
    """The items a source lists NOW, through its own parser."""
    src = SOURCES[name]
    got = feeds_http.get(src.listing_url, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                         max_bytes=MAX_LISTING_BYTES)
    return src.parse(got.body)


def main() -> int:
    seen = ledger.load(ledger.SEEN_PATH)  # the ledger feeds_list_new reads: (source, item_id) pairs
    total = 0
    for name in ORDER:
        items = current_items(name)
        new = [i for i in items if (i.source, i.item_id) not in seen]
        total += len(new)
        print("%-11s listed %3d  new %3d" % (name, len(items), len(new)))
    print("%-11s           new %3d" % ("all", total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
