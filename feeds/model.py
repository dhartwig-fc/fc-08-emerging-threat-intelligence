"""The one shape of a listed item, shared by the adapters, the inbox, the ledger and the feeds server."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass


class LayoutChanged(Exception):
    """A listing no longer has the structure its adapter depends on. Reported loudly, never as "0 new items"."""


@dataclass(frozen=True)
class FeedItem:
    source: str
    # The publisher's own identifier: OFSI's Atom <id>, which carries a timestamp, so a REVISED
    # publication is a new item; FinCEN's and OFAC's last URL path segment.
    item_id: str
    title: str
    url: str
    published: str  # YYYY-MM-DD
    summary: str = ""

    @property
    def key(self) -> str:
        """The id the agent sees: fixed-width and DERIVED from the item, so an agent cannot mint one."""
        return "%s:%s" % (self.source, hashlib.sha256(self.item_id.encode("utf-8")).hexdigest()[:16])

    def to_json(self) -> dict:
        out = asdict(self)
        out["key"] = self.key
        return out
