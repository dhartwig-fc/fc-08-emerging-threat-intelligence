"""
The automated sources and their adapters: raw listing bytes in, FeedItems out.

Each adapter checks the structural MARKER it depends on and raises LayoutChanged when it is
missing, when the marker is present but no item parses, or when an item lacks its link, its date or
its title (the field the agent actually reads). OFAC also raises when the body ends inside an open
row, which is what a truncated body looks like.
An empty result is never returned: each of these listings always shows its latest entries
(measured 2026-09-26: OFSI 20, FinCEN 15, OFAC 10; 2026-10-31: OTSI 20, FCA 20, NCA 20, EU Council 20,
EBA 10, AMLA 30; 2026-10-31: Wolfsberg 10), so "nothing parsed" means the page changed.

Measured 2026-09-26, and why fetch pins LANDING pages in sub-project A: the URL a FinCEN or OFSI
item lists is an HTML landing page; the advisory itself is a PDF linked from it (FinCEN on
www.fincen.gov, OFSI on assets.publishing.service.gov.uk). OFAC's recent action IS the HTML page.
linked_pdfs() records those links; following them is decided in sub-project C.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Callable, FrozenSet, List
from urllib.parse import urljoin, urlsplit

from feeds.model import FeedItem, LayoutChanged

MAX_LISTING_BYTES = 2_000_000
MAX_DOCUMENT_BYTES = 20_000_000
DOCUMENT_TYPES = frozenset({"text/html", "application/pdf"})
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
DATE_FIELD = "published"  # FeedItem's date field (feeds/model.py)


def _title(source: str, parts: List[str], where: str) -> str:
    """An item's title, whitespace-normalised. An empty one is a layout change, never an untitled item."""
    title = " ".join("".join(parts).split())
    if not title:
        raise LayoutChanged("%s: the item %s has an empty title" % (source, where))
    return title

# ---------------------------------------------------------------------------- OFSI: GOV.UK Atom

ATOM = "{http://www.w3.org/2005/Atom}"


def _parse_govuk_atom(source: str, raw: bytes) -> List[FeedItem]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LayoutChanged("%s: not well-formed XML (%s)" % (source, exc))
    if root.tag != ATOM + "feed":
        raise LayoutChanged("%s: the root element is %r, not an Atom feed" % (source, root.tag))
    items = []
    for entry in root.findall(ATOM + "entry"):
        eid, updated, title = (entry.findtext(ATOM + t) for t in ("id", "updated", "title"))
        link = entry.find(ATOM + "link[@rel='alternate']")
        if not (eid and updated and title and link is not None and link.get("href")):
            raise LayoutChanged("%s: an entry lacks its id, updated, title or alternate link" % source)
        if not ISO_DATE.match(updated):
            raise LayoutChanged("%s: updated %r is not an ISO timestamp" % (source, updated))
        items.append(FeedItem(source, eid.strip(), _title(source, [title], eid.strip()), link.get("href"), updated[:10],
                              " ".join((entry.findtext(ATOM + "summary") or "").split())))
    if not items:
        raise LayoutChanged("%s: the feed parsed but holds no entries" % source)
    return items


def parse_ofsi(raw: bytes) -> List[FeedItem]:
    return _parse_govuk_atom("ofsi", raw)


def parse_otsi(raw: bytes) -> List[FeedItem]:
    return _parse_govuk_atom("otsi", raw)

# ---------------------------------------------------------------------------- RSS 2.0 (FCA, NCA, EU Council, EBA, AMLA)

RSS_DATE_FORMATS = ("%a, %d %b %Y %H:%M:%S %z",   # RFC 822 with a numeric zone (NCA, EBA, AMLA)
                    "%a, %d %b %Y %H:%M:%S %Z",   # RFC 822 with GMT/UTC
                    "%A, %B %d, %Y - %H:%M")      # FCA: "Friday, October 30, 2026 - 09:00", London wall-clock


def _rss_date(source: str, item, where: str) -> str:
    """An item's publication DATE, YYYY-MM-DD, in the publisher's own stated zone (plan R6): what OFSI
    (updated[:10]) and OFAC give, and what accept_run writes into published_on, which the schema types as a date.
    pubDate first, then a10:/atom:updated (EU Council). Never today."""
    raw = (item.findtext("pubDate") or "").strip()
    if raw:
        for fmt in RSS_DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        raise LayoutChanged("%s: the item %s has a pubDate %r in no known format" % (source, where, raw))
    updated = (item.findtext(ATOM + "updated") or "").strip()
    if ISO_DATE.match(updated):
        return updated[:10]
    raise LayoutChanged("%s: the item %s has no date" % (source, where))


def _parse_rss(source: str, raw: bytes) -> List[FeedItem]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LayoutChanged("%s: not well-formed XML (%s)" % (source, exc))
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise LayoutChanged("%s: the root element is %r, not an RSS channel" % (source, root.tag))
    items = []
    for item in channel.findall("item"):
        link = (item.findtext("link") or "").strip()
        if not link:
            raise LayoutChanged("%s: an item lacks its link" % source)
        title = _title(source, [item.findtext("title") or ""], link)
        guid = (item.findtext("guid") or "").strip() or link
        items.append(FeedItem(source, guid, title, link, _rss_date(source, item, link)))
    if not items:
        raise LayoutChanged("%s: the channel is present but no item parsed" % source)
    return sorted(items, key=lambda i: getattr(i, DATE_FIELD), reverse=True)


def _rss(source: str) -> Callable[[bytes], List[FeedItem]]:
    def parse(raw: bytes) -> List[FeedItem]:
        return _parse_rss(source, raw)
    parse.__name__ = "parse_" + source
    return parse


parse_fca, parse_nca, parse_eu_council, parse_eba, parse_amla = (
    _rss(s) for s in ("fca", "nca", "eu_council", "eba", "amla"))

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
                                      _title("fincen", row["title"], row["href"]),
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
                                      _title("ofac", row["title"], row["href"]),
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
    if row is not None:  # the body ended inside a views-row: truncated, never a row to drop
        raise LayoutChanged("ofac: the listing ends inside an open views-row (a truncated body)")
    if not items:
        raise LayoutChanged("ofac: the view is present but no views-row parsed")
    return items


WOLFSBERG_BASE = "https://wolfsberg-group.org"
DAY_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_wolfsberg(raw: bytes) -> List[FeedItem]:
    """The Wolfsberg Group's /news page, server-rendered (measured 2026-10-31): one <article class="news-item"> per
    item, holding a /news/<slug> link, the date in its first <span> as YYYY-MM-DD and the title in its <h3>."""
    events = _events("wolfsberg", raw)
    if not any(k == "start" and t == "article" and "news-item" in _classes(a) for k, t, a in events):
        raise LayoutChanged("wolfsberg: the news cards (article.news-item) are missing")
    items, card = [], None
    for kind, tag, attrs in events:
        if kind == "start" and tag == "article" and "news-item" in _classes(attrs):
            card = {"href": None, "date": [], "title": [], "in": None}
        elif card is None:
            continue
        elif kind == "start" and tag == "a" and card["href"] is None \
                and (attrs.get("href") or "").startswith("/news/"):
            card["href"] = attrs["href"]
        elif kind == "start" and tag == "span" and not card["date"] and card["in"] is None:
            card["in"] = "date"
        elif kind == "start" and tag == "h3" and not card["title"] and card["in"] is None:
            card["in"] = "title"
        elif kind == "end" and tag in ("span", "h3"):
            card["in"] = None
        elif kind == "text" and card["in"]:
            card[card["in"]].append(tag)
        elif kind == "end" and tag == "article":
            if not card["href"]:
                raise LayoutChanged("wolfsberg: a news card has no /news/ link")
            date = "".join(card["date"]).strip()
            if not DAY_ONLY.match(date):
                raise LayoutChanged("wolfsberg: the card for %s has no date" % card["href"])
            items.append(FeedItem("wolfsberg", card["href"].rstrip("/").rsplit("/", 1)[1],
                                  _title("wolfsberg", card["title"], card["href"]),
                                  urljoin(WOLFSBERG_BASE, card["href"]), date))
            card = None
    if card is not None:  # the body ended inside a card: truncated, never a card to drop
        raise LayoutChanged("wolfsberg: the listing ends inside an open news card (a truncated body)")
    if not items:
        raise LayoutChanged("wolfsberg: the cards are present but none parsed")
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
    # Slice 2 C: hosts a PDF LINKED from an item's pinned page may be fetched from, for extraction only
    # (feeds/extraction.py). Measured 2026-09-26/28: FinCEN links its advisory PDF on www.fincen.gov, OFSI
    # on assets.publishing.service.gov.uk; OFAC's action IS the page, and its /media/ downloads are not
    # followed (every OFAC page links /media/935656, so "the" document is not identifiable by rule).
    document_hosts: FrozenSet[str] = frozenset()
    # One page between an item and its PDF (Wolfsberg, measured 2026-10-31): a path prefix on the source's own hosts.
    # When an item's page links no PDF on document_hosts, exactly ONE link under this prefix is followed to the page
    # that does (feeds/extraction.py). Empty: no hop -- the behaviour of every source before it.
    document_via: str = ""


SOURCES = {
    "fincen": Source("fincen", "https://www.fincen.gov/resources/advisoriesbulletinsfact-sheets/advisories", "html",
                     frozenset({"text/html"}), frozenset({"www.fincen.gov"}), parse_fincen,
                     frozenset({"www.fincen.gov"})),
    "ofac": Source("ofac", "https://ofac.treasury.gov/recent-actions", "html",
                   frozenset({"text/html"}), frozenset({"ofac.treasury.gov"}), parse_ofac),
    "ofsi": Source("ofsi", "https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation.atom",
                   "atom", frozenset({"application/atom+xml"}), frozenset({"www.gov.uk"}), parse_ofsi,
                   frozenset({"assets.publishing.service.gov.uk"})),
    "otsi": Source("otsi", "https://www.gov.uk/government/organisations/office-of-trade-sanctions-implementation.atom",
                   "atom", frozenset({"application/atom+xml"}), frozenset({"www.gov.uk"}), parse_otsi,
                   frozenset({"assets.publishing.service.gov.uk"})),
    "fca": Source("fca", "https://www.fca.org.uk/news/rss.xml", "rss", frozenset({"application/rss+xml"}),
                  frozenset({"www.fca.org.uk"}), parse_fca, frozenset({"www.fca.org.uk"})),
    "nca": Source("nca", "https://www.nationalcrimeagency.gov.uk/news?format=feed&type=rss", "rss",
                  frozenset({"application/rss+xml"}), frozenset({"www.nationalcrimeagency.gov.uk"}), parse_nca,
                  frozenset({"www.nationalcrimeagency.gov.uk"})),
    "eu_council": Source("eu_council", "https://www.consilium.europa.eu/en/rss/pressreleases.ashx", "rss",
                         frozenset({"text/xml", "application/rss+xml"}), frozenset({"www.consilium.europa.eu"}),
                         parse_eu_council, frozenset({"www.consilium.europa.eu"})),
    "eba": Source("eba", "https://www.eba.europa.eu/news-press/news/rss.xml", "rss", frozenset({"application/rss+xml"}),
                  frozenset({"www.eba.europa.eu"}), parse_eba, frozenset({"www.eba.europa.eu"})),
    "amla": Source("amla", "https://www.amla.europa.eu/node/19/rss_en", "rss", frozenset({"application/rss+xml"}),
                   frozenset({"www.amla.europa.eu"}), parse_amla, frozenset({"www.amla.europa.eu"})),
    "wolfsberg": Source("wolfsberg", "https://wolfsberg-group.org/news", "html", frozenset({"text/html"}),
                        frozenset({"wolfsberg-group.org"}), parse_wolfsberg, frozenset({"db.wolfsberg-group.org"}),
                        "/resources/"),
}

# The order sources are named in the triage prompt and listed in a run. Appending keeps every earlier prompt's
# bytes (plan R5); a source missing here, or one here but not in SOURCES, is refused at import.
ORDER = ("ofsi", "fincen", "ofac", "otsi", "fca", "nca", "eu_council", "eba", "amla", "wolfsberg")
if set(ORDER) != set(SOURCES) or len(ORDER) != len(SOURCES):
    raise RuntimeError("feeds.sources: ORDER %r and SOURCES %r disagree" % (ORDER, sorted(SOURCES)))
SOURCE_PATTERN = r"^(%s)$" % "|".join(ORDER)
KEY_PATTERN = r"^(%s):[0-9a-f]{16}$" % "|".join(ORDER)


@dataclass(frozen=True)
class ManualSource:
    """A source whose site blocks automated fetching (FATF, measured 2026-10-31: Cloudflare's bot check on every URL).
    The owner downloads a document and tools/intake_document.py takes it in. Nothing in fc-08 fetches these hosts;
    they bound the provenance URL the owner records."""
    name: str
    hosts: FrozenSet[str]


MANUAL_SOURCES = {"fatf": ManualSource("fatf", frozenset({"www.fatf-gafi.org"}))}
if set(MANUAL_SOURCES) & set(SOURCES):
    raise RuntimeError("feeds.sources: %s are declared both live and manual" % sorted(set(MANUAL_SOURCES) & set(SOURCES)))


def named() -> str:
    """'ofsi, fincen and ofac': the sources in ORDER, as the prompt names them."""
    return ORDER[0] if len(ORDER) == 1 else ", ".join(ORDER[:-1]) + " and " + ORDER[-1]


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


def linked_pages(raw: bytes, base_url: str, prefix: str) -> List[str]:
    """Absolute URLs an HTML page links to whose path starts with `prefix`, first occurrence order. Listed, never
    fetched; the host is NOT checked here -- extraction asks feeds.http's one allowlist predicate (plan R8)."""
    if not prefix:
        return []
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
        if urlsplit(url).path.startswith(prefix) and url not in out:
            out.append(url)
    return out
