"""
The three automated sources and their adapters: raw listing bytes in, FeedItems out.

Each adapter checks the structural MARKER it depends on and raises LayoutChanged when it is
missing, when the marker is present but no item parses, or when an item lacks its link or date.
An empty result is never returned: each of these listings always shows its latest entries
(measured 2026-09-26: OFSI 20, FinCEN 15, OFAC 10), so "nothing parsed" means the page changed.

Measured 2026-09-26, and why fetch pins LANDING pages in sub-project A: the URL a FinCEN or OFSI
item lists is an HTML landing page; the advisory itself is a PDF linked from it (FinCEN on
www.fincen.gov, OFSI on assets.publishing.service.gov.uk). OFAC's recent action IS the HTML page.
linked_pdfs() records those links; following them is decided in sub-project C.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, FrozenSet, List
from urllib.parse import urljoin, urlsplit

from feeds.model import FeedItem, LayoutChanged

MAX_LISTING_BYTES = 2_000_000
MAX_DOCUMENT_BYTES = 20_000_000
DOCUMENT_TYPES = frozenset({"text/html", "application/pdf"})
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T")

# ---------------------------------------------------------------------------- OFSI: GOV.UK Atom

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_ofsi(raw: bytes) -> List[FeedItem]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LayoutChanged("ofsi: not well-formed XML (%s)" % exc)
    if root.tag != ATOM + "feed":
        raise LayoutChanged("ofsi: the root element is %r, not an Atom feed" % root.tag)
    items = []
    for entry in root.findall(ATOM + "entry"):
        eid, updated, title = (entry.findtext(ATOM + t) for t in ("id", "updated", "title"))
        link = entry.find(ATOM + "link[@rel='alternate']")
        if not (eid and updated and title and link is not None and link.get("href")):
            raise LayoutChanged("ofsi: an entry lacks its id, updated, title or alternate link")
        if not ISO_DATE.match(updated):
            raise LayoutChanged("ofsi: updated %r is not an ISO timestamp" % updated)
        items.append(FeedItem("ofsi", eid.strip(), " ".join(title.split()), link.get("href"), updated[:10],
                              " ".join((entry.findtext(ATOM + "summary") or "").split())))
    if not items:
        raise LayoutChanged("ofsi: the feed parsed but holds no entries")
    return items

# ---------------------------------------------------------------------------- the HTML listings


class _Events(HTMLParser):
    """Start tags, end tags and text in document order: the one walker both HTML listings use."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list = []

    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, dict(attrs)))

    def handle_endtag(self, tag):
        self.events.append(("end", tag, {}))

    def handle_data(self, data):
        self.events.append(("text", data, {}))


def _events(source: str, raw: bytes) -> list:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LayoutChanged("%s: the listing is not UTF-8 (%s)" % (source, exc))
    parser = _Events()
    parser.feed(text)
    parser.close()
    return parser.events


def _classes(attrs: dict) -> set:
    return set((attrs.get("class") or "").split())


FINCEN_BASE = "https://www.fincen.gov"


def parse_fincen(raw: bytes) -> List[FeedItem]:
    events = _events("fincen", raw)
    if not any(k == "start" and t == "th" and a.get("id") == "view-title-table-column" for k, t, a in events):
        raise LayoutChanged("fincen: the listing table (th#view-title-table-column) is missing")
    items, row = [], None
    for kind, tag, attrs in events:
        if kind == "start" and tag == "tr":
            row = {"href": None, "title": [], "date": None, "subject": [], "in_a": False, "in_subject": False,
                   "title_cell": False}
        elif row is None:
            continue
        elif kind == "start" and tag == "a" and row["href"] is None \
                and (attrs.get("href") or "").startswith("/resources/advisories/"):
            row["href"], row["in_a"] = attrs["href"], True
        elif kind == "end" and tag == "a":
            row["in_a"] = False
        elif kind == "start" and tag == "time" and row["date"] is None:
            row["date"] = attrs.get("datetime")
        elif kind == "start" and tag == "td" and attrs.get("headers") == "view-title-table-column":
            row["title_cell"] = True
        elif kind == "start" and tag == "td" and attrs.get("headers") == "view-field-advisory-subject-table-column":
            row["in_subject"] = True
        elif kind == "end" and tag == "td":
            row["in_subject"] = False
        elif kind == "text" and row["in_a"]:
            row["title"].append(tag)
        elif kind == "text" and row["in_subject"]:
            row["subject"].append(tag)
        elif kind == "end" and tag == "tr":
            # A row with the listing's title cell IS an advisory row: losing its link is a layout
            # change, never a row to skip (rows without the cell are the page's other tables).
            if row["title_cell"] and not row["href"]:
                raise LayoutChanged("fincen: an advisory row has its title cell but no /resources/advisories/ link")
            if row["href"]:
                if not (row["date"] and ISO_DATE.match(row["date"])):
                    raise LayoutChanged("fincen: the row for %s has no <time datetime>" % row["href"])
                items.append(FeedItem("fincen", row["href"].rstrip("/").rsplit("/", 1)[1],
                                      " ".join("".join(row["title"]).split()),
                                      urljoin(FINCEN_BASE, row["href"]), row["date"][:10],
                                      " ".join("".join(row["subject"]).split())))
            row = None
    if not items:
        raise LayoutChanged("fincen: the table is present but no advisory row parsed")
    return items


OFAC_BASE = "https://ofac.treasury.gov"
OFAC_DATE = re.compile(r"^\s*([A-Z][a-z]+) (\d{2}), (\d{4})\s*-")
# Month names by table, not strptime("%B"), which follows the process locale.
MONTHS = {m: n for n, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"), 1)}


def parse_ofac(raw: bytes) -> List[FeedItem]:
    events = _events("ofac", raw)
    if not any(k == "start" and "view-recent-actions-search" in _classes(a) for k, t, a in events):
        raise LayoutChanged("ofac: the recent-actions view (div.view-recent-actions-search) is missing")
    items, row, depth = [], None, 0
    for kind, tag, attrs in events:
        if kind == "start" and tag == "div" and {"search-result", "views-row"} <= _classes(attrs):
            row, depth = {"href": None, "title": [], "date": None, "in_a": False}, 0
        if row is None:
            continue
        if kind == "start" and tag == "div":
            depth += 1
        elif kind == "end" and tag == "div":
            depth -= 1
            if depth == 0:
                if not row["href"] or not row["date"]:
                    raise LayoutChanged("ofac: a views-row lacks its link or its 'Month DD, YYYY -' date line")
                items.append(FeedItem("ofac", row["href"].rstrip("/").rsplit("/", 1)[1],
                                      " ".join("".join(row["title"]).split()),
                                      urljoin(OFAC_BASE, row["href"]), row["date"]))
                row = None
        elif kind == "start" and tag == "a" and row["href"] is None \
                and (attrs.get("href") or "").startswith("/recent-actions/"):
            row["href"], row["in_a"] = attrs["href"], True
        elif kind == "end" and tag == "a":
            row["in_a"] = False
        elif kind == "text" and row["in_a"]:
            row["title"].append(tag)
        elif kind == "text" and row["href"] and row["date"] is None:
            m = OFAC_DATE.match(tag)
            if m and m.group(1) in MONTHS:
                row["date"] = "%s-%02d-%s" % (m.group(3), MONTHS[m.group(1)], m.group(2))
    if not items:
        raise LayoutChanged("ofac: the view is present but no views-row parsed")
    return items

# ---------------------------------------------------------------------------- the registry


@dataclass(frozen=True)
class Source:
    name: str
    listing_url: str
    listing_ext: str
    listing_types: FrozenSet[str]
    hosts: FrozenSet[str]  # the listing's host and every item URL's host
    parse: Callable[[bytes], List[FeedItem]]


SOURCES = {
    "fincen": Source("fincen", "https://www.fincen.gov/resources/advisoriesbulletinsfact-sheets/advisories", "html",
                     frozenset({"text/html"}), frozenset({"www.fincen.gov"}), parse_fincen),
    "ofac": Source("ofac", "https://ofac.treasury.gov/recent-actions", "html",
                   frozenset({"text/html"}), frozenset({"ofac.treasury.gov"}), parse_ofac),
    "ofsi": Source("ofsi", "https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation.atom",
                   "atom", frozenset({"application/atom+xml"}), frozenset({"www.gov.uk"}), parse_ofsi),
}


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: List[str] = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.append(href)


def linked_pdfs(raw: bytes, base_url: str) -> List[str]:
    """Absolute URLs of the PDFs an HTML page links to, first occurrence order. Listed, never fetched, in A."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    parser = _Links()
    parser.feed(text)
    parser.close()
    out: List[str] = []
    for href in parser.hrefs:
        url = urljoin(base_url, href)
        if urlsplit(url).path.lower().endswith(".pdf") and url not in out:
            out.append(url)
    return out
