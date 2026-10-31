"""
Pin the source adapters (feeds/sources.py) and the allowlisted fetch (feeds/http.py).

Usage:
    python evals/check_feed_adapters.py
    python evals/check_feed_adapters.py --mutate no-marker-fincen   # FinCEN's marker unchecked; a changed page MUST pass
    python evals/check_feed_adapters.py --mutate empty-ok           # OFAC returns [] when nothing parses
    python evals/check_feed_adapters.py --mutate ofsi-link-id       # OFSI keyed by link; a revision MUST collapse
    python evals/check_feed_adapters.py --mutate relative-url       # FinCEN URLs left relative
    python evals/check_feed_adapters.py --mutate ofac-date-optional # an OFAC row without a date is accepted
    python evals/check_feed_adapters.py --mutate follow-redirects   # a redirect off the allowlist is followed
    python evals/check_feed_adapters.py --mutate no-size-cap        # an oversized body is accepted
    python evals/check_feed_adapters.py --mutate skip-linkless-row  # a FinCEN advisory row without its link is skipped
    python evals/check_feed_adapters.py --mutate http-allowed       # plain http passes the allowlist
    python evals/check_feed_adapters.py --mutate any-port           # an allowed host on another port passes
    python evals/check_feed_adapters.py --mutate untitled-ok        # an item with an empty title is accepted
    python evals/check_feed_adapters.py --mutate ofac-truncated-ok  # an OFAC body ending inside a row drops the row
    python evals/check_feed_adapters.py --mutate narrow-except      # only URLError becomes FetchRefused
    python evals/check_feed_adapters.py --mutate hand-list          # a hand copy of the source list in reconcile.py
    python evals/check_feed_adapters.py --mutate rule-missing        # a live source with no triage rule entry
    python evals/check_feed_adapters.py --mutate rss-date-optional  # an undated RSS item is accepted
    python evals/check_feed_adapters.py --mutate rss-unsorted       # an RSS feed comes back in document order
    python evals/check_feed_adapters.py --mutate fca-host-open      # FCA's declared hosts gain an extra host
    python evals/check_feed_adapters.py --mutate publisher-missing  # a source without a PUBLISHERS entry

CONTRACT. Each adapter, run on the committed snapshot of its listing (tests/fixtures/feeds/, fetched
2026-09-26, public government pages), must return the pinned items: count, the digest of their ids in
order, and the first and last item field by field. Each must raise LayoutChanged, never return an
empty list, when its marker is gone, when the marker is there but nothing parses, when an item
has no date, and when an item's title is empty; OFAC also raises when the body ends inside an open
views-row (a truncated body under the size cap). OFSI keys an item by its Atom <id>, which carries a timestamp, so a revised publication
is a NEW item (a ruling of the sub-project A plan).

TRANSPORT. The allowlist is exact on scheme and netloc: https only, the host with no other port and
no userinfo, so "http://allowed/", "https://allowed:8443/" and "https://allowed@evil/" are refused
(checked on the rule itself, under its real https-only setting). feeds.http.get refuses a URL off
the allowlist, a redirect off the allowlist BEFORE any request reaches the other host, a body over
the size cap, and a content type not allowed -- checked against a local HTTP server on 127.0.0.1,
for which the guard alone widens the scheme to http, so it stays cold. Every transport failure is a
FetchRefused, not only urllib's URLError: a server that stalls before its headers, one that stalls
mid-body, and one that closes without answering must each come back REFUSED (the guard alone
lowers the timeout, as it widens the scheme). Before 2026-09-26 the last three escaped as
TimeoutError and RemoteDisconnected (final review of slice 2 A, Important 1).

FinCEN's rows are told apart from the page's other tables by the listing's title cell: a row that
has the cell but lost its advisory link raises, so one missing advisory cannot silently shrink the
list (review of Task 3, 2026-09-26).

NOT A VACUOUS PASS. Each --mutate rewrites one module's SOURCE in memory; at least one check must fail.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import importlib
import json
import re
import socketserver
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from feeds.model import LayoutChanged  # noqa: E402

SOURCES_PY = ROOT / "feeds" / "sources.py"
HTTP_PY = ROOT / "feeds" / "http.py"
FIX = ROOT / "tests" / "fixtures" / "feeds"
SNAPSHOTS = {"ofsi": ("ofsi.atom", "b63d891e06aceaaf42021a4637573ad16cedc7c6b84ab7082332903b4b6d31c9"),
             "fincen": ("fincen_advisories.html", "295483b8950e51cd839f1b0198c6b20d8a802180b55487ee6551412bcbd3b10b"),
             "ofac": ("ofac_recent_actions.html", "9b2cdcdc61a65f954e3157d216ce154aa3ad1fddfea810f97d78ad6bb9f0e669"),
             "otsi": ("otsi.atom", "4989315d391a8e805fc54471a40d25be7ee8b33fe6db83bc991a1dcd55696737"),
             "fca": ("fca.rss", "7bf89e542865addeaf14355f82eb77a54c64466e9ecd8fc55cb0ffcaed99ee0b"),
             "nca": ("nca.rss", "50a3328fafc35dd918f03d6488d5a21b15114b3719a947961fa5068788d9da3b"),
             "eu_council": ("eu_council.rss", "8ad8d9da81a433c4e91c6205f3b4c33fd655528517c993ac0f6a58eb2fbfef44"),
             "eba": ("eba.rss", "550eb52f4e5b25afec8fda7dc8137578ac1a581d0690a491223da56d83677b47"),
             "amla": ("amla.rss", "91e9ba1e45b2719bc2547d4fb61f57b5740daf441c8ad37376442868964eb57c"),
             "wolfsberg": ("wolfsberg_news.html", "0f8707eb271f1de4f61c5e77904490bf382a49852ed8e712e731516c5b47e2a1"),}
EXPECTED = {
    "ofsi": {"count": 20, "ids": "db1898e619e089de7649a2443ffbe1ca707fa31d623ebae87729f76e5916067e",
             "first": {"item_id": "https://www.gov.uk/government/publications/uk-financial-sanctions-faqs#2026-09-24T08:49:08Z",
                       "title": "Guidance: UK Financial Sanctions FAQs",
                       "url": "https://www.gov.uk/government/publications/uk-financial-sanctions-faqs",
                       "published": "2026-09-24",
                       "summary": "OFSI publishes FAQs providing short-form guidance and technical information on "
                                  "financial sanctions."},
             "last": {"item_id": "https://www.gov.uk/government/publications/russia-sanctions-guidance#2026-05-19T23:01:01Z",
                      "title": "Statutory guidance: Russia sanctions: guidance",
                      "url": "https://www.gov.uk/government/publications/russia-sanctions-guidance",
                      "published": "2026-05-19"}},
    "fincen": {"count": 15, "ids": "b683612db4df8f00f89d80adb2180b3256d556f37ae6be087ef8bbe2f54665c6",
               "first": {"item_id": "fincen-advisory-fin-2026-a002", "title": "FinCEN Advisory FIN-2026-A002",
                         "url": "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2026-a002",
                         "published": "2026-06-05",
                         "summary": "Joint Advisory on Non-Work Authorized Populations and Their Employers and Risks "
                                    "to the Integrity of the U.S. Financial System"},
               "last": {"item_id": "fincen-advisory-fin-2020-a009", "title": "FinCEN Advisory FIN-2020-A009",
                        "url": "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2020-a009",
                        "published": "2020-11-06"}},
    "ofac": {"count": 10, "ids": "a2d84aa40095354bec149d01c732dc24373f92e406777ccede587061ed21b629",
             "first": {"item_id": "20260924", "url": "https://ofac.treasury.gov/recent-actions/20260924",
                       "published": "2026-09-24", "summary": "",
                       "title": "Publication of Regulatory Amendments; Publication of Report for Licensing Activities "
                                "Undertaken Pursuant to the Trade Sanctions Reform and Export Enhancement Act (TSRA)"},
             "last": {"item_id": "20260904", "url": "https://ofac.treasury.gov/recent-actions/20260904",
                      "published": "2026-09-04",
                      "title": "Iran-related Designations; Issuance of Iran-related General License"}},
    'otsi': {"count": 20, "ids": '65cebafd4b83dd73bb4f26bd1838d7ef8f5cef5212f5e4e686aa647e9d74b898',
      "first": {'item_id': 'https://www.gov.uk/government/publications/complying-with-trade-sanctions-relating-to-specified-ships#2026-10-27T10:00:00Z', 'title': 'Guidance: Complying with trade sanctions relating to specified ships', 'url': 'https://www.gov.uk/government/publications/complying-with-trade-sanctions-relating-to-specified-ships', 'published': '2026-10-27', 'summary': 'Guidance outlining obligations under trade sanctions relating to specified ships and the Office of Trade Sanction Implementation’s (OTSI) implementation and enforcement responsibilities.'},
      "last": {'item_id': 'https://www.gov.uk/guidance/how-to-use-exceptions-and-licences-to-comply-with-sanctions#2026-04-23T11:26:39Z', 'title': 'How to use exceptions and licences to comply with sanctions', 'url': 'https://www.gov.uk/guidance/how-to-use-exceptions-and-licences-to-comply-with-sanctions', 'published': '2026-04-23'}},
    'fca': {"count": 20, "ids": '5211f258013bd7d4edc034b43087d6f7d2e87ff49a604964a30c4963cfdf5e23',
      "first": {'item_id': '177091', 'title': 'Brits nearly twice as likely to spot pressure tactics in horror films as investment red flags', 'url': 'https://www.fca.org.uk/news/press-releases/brits-nearly-twice-likely-spot-pressure-tactics-horror-films-investment-red-flags', 'published': '2026-10-30', 'summary': ''},
      "last": {'item_id': '176576', 'title': 'Two plead guilty after clients lose £2m in fraud case', 'url': 'https://www.fca.org.uk/news/press-releases/two-plead-guilty-after-clients-lose-2m-fraud-case', 'published': '2026-10-13'}},
    'nca': {"count": 20, "ids": '0f5e56574d689c27a8d85090f441e735e2f40364b8a21f62ec1791d10f96fb90',
      "first": {'item_id': 'https://www.nationalcrimeagency.gov.uk/news/people-smuggling-network-get-combined-jail-terms-of-more-than-84-years-as-final-members-sentenced', 'title': 'People smuggling network get combined jail terms of more than 84 years as final members sentenced', 'url': 'https://www.nationalcrimeagency.gov.uk/news/people-smuggling-network-get-combined-jail-terms-of-more-than-84-years-as-final-members-sentenced', 'published': '2026-10-28', 'summary': ''},
      "last": {'item_id': 'https://www.nationalcrimeagency.gov.uk/news/gang-ringleader-arrested-by-the-nca-convicted-over-channel-boat-deaths', 'title': 'Gang ringleader arrested by the NCA convicted over Channel boat deaths', 'url': 'https://www.nationalcrimeagency.gov.uk/news/gang-ringleader-arrested-by-the-nca-convicted-over-channel-boat-deaths', 'published': '2026-10-01'}},
    'eu_council': {"count": 20, "ids": '7209e7d9900f8f877f792e6bf5d15088d05f56a82aaffa46402ec2daa2271e4e',
      "first": {'item_id': '151917', 'title': 'Weekly schedule of President António Costa', 'url': 'https://www.consilium.europa.eu/en/press/press-releases/2026/10/30/weekly-schedule-of-president-antonio-costa/', 'published': '2026-10-30', 'summary': ''},
      "last": {'item_id': '151695', 'title': 'Weekly schedule of President António Costa', 'url': 'https://www.consilium.europa.eu/en/press/press-releases/2026/10/23/weekly-schedule-of-president-antonio-costa/', 'published': '2026-10-23'}},
    'eba': {"count": 10, "ids": '381810fb8f9f9ce7700ac8d7a8fe8c34c82824411cbd8b71b17661285969ec61',
      "first": {'item_id': 'https://www.eba.europa.eu/publications-and-media/press-releases/eba-advises-targeted-simplifications-taxonomy-disclosures', 'title': 'The EBA advises on targeted simplifications to Taxonomy disclosures', 'url': 'https://www.eba.europa.eu/publications-and-media/press-releases/eba-advises-targeted-simplifications-taxonomy-disclosures', 'published': '2026-10-29', 'summary': ''},
      "last": {'item_id': 'https://www.eba.europa.eu/publications-and-media/press-releases/eueea-banks-display-strength-amid-challenging-risk-environment', 'title': 'EU/EEA banks display strength amid a challenging risk environment', 'url': 'https://www.eba.europa.eu/publications-and-media/press-releases/eueea-banks-display-strength-amid-challenging-risk-environment', 'published': '2026-09-25'}},
    'amla': {"count": 30, "ids": '57d5f3c96875e065467e2c33a9167cb82c275ecb99dfc929501e2e080a974682',
      "first": {'item_id': 'https://www.amla.europa.eu/call-expression-interest-technology-providers-roundtable-partnerships-information-sharing_en', 'title': 'Call for expression of interest: technology providers roundtable on partnerships for information sharing', 'url': 'https://www.amla.europa.eu/call-expression-interest-technology-providers-roundtable-partnerships-information-sharing_en', 'published': '2026-10-30', 'summary': ''},
      "last": {'item_id': 'https://www.amla.europa.eu/press-release-amla-consults-clear-rules-cross-border-fiu-information-exchanges_en', 'title': 'Press Release: AMLA consults on clear rules for cross-border FIU information exchanges', 'url': 'https://www.amla.europa.eu/press-release-amla-consults-clear-rules-cross-border-fiu-information-exchanges_en', 'published': '2026-07-06'}},
    "wolfsberg": {"count": 10, "ids": "bbc59c6928669e73331f92a7b93835e6567f1c18a9ad5036e126eb7f8c7e1618",
                  "first": {"item_id": "guidance-on-the-provision-of-banking-services",
                            "title": "The Wolfsberg Group publishes Guidance on the provision of banking services to "
                                     "non-bank payment service providers (PSPs)",
                            "url": "https://wolfsberg-group.org/news/guidance-on-the-provision-of-banking-services",
                            "published": "2026-07-15", "summary": ""},
                  "last": {"item_id": "the-wolfsberg-group-celebrates-its-25th-anniversary-and-welcomes-new-management-"
                                      "committee-members",
                           "title": "The Wolfsberg Group Celebrates its 25th Anniversary and Welcomes New Management "
                                    "Committee Members",
                           "url": "https://wolfsberg-group.org/news/the-wolfsberg-group-celebrates-its-25th-anniversary-"
                                  "and-welcomes-new-management-committee-members",
                           "published": "2025-06-17"}},
}
# (label, source, regex, replacement), applied to EVERY match: each must make the adapter raise LayoutChanged.
BREAKS = [
    ("marker gone", "wolfsberg", r'class="news-item', 'class="renamed-item'),
    ("an item without a date", "wolfsberg", r"<!--\[-->2026-07-15<!--\]-->", "<!--[-->soon<!--]-->"),
    ("an item with an empty title", "wolfsberg",
     r"<!--\[-->The Wolfsberg Group publishes Guidance on the provision of banking services to non-bank payment service "
     r"providers \(PSPs\)<!--\]-->", "<!--[--> <!--]-->"),
    ("a body ending inside an open news card", "wolfsberg",
     r'(?s)(<a href="/news/the-wolfsberg-group-celebrates[^"]*"[^>]*></a>).*', r"\1"),
    ("marker gone", "ofsi", r"<feed ", "<rss "),
    ("marker gone", "fincen", r'id="view-title-table-column"', 'id="view-renamed"'),
    ("marker gone", "ofac", r"view-recent-actions-search", "view-renamed"),
    ("nothing parses", "ofsi", r"(?s)<entry>.*</entry>", ""),
    ("nothing parses", "fincen", r'href="/resources/advisories/', 'href="/elsewhere/'),
    ("nothing parses", "ofac", r"search-result views-row", "search-result"),
    ("an item without a date", "ofsi", r"<updated>2026-09-24T08:49:08Z</updated>\s*<link", "<updated>yesterday</updated><link"),
    ("an item without a date", "fincen", r'datetime="2026-06-05T12:00:00Z"', ""),
    ("an item without a date", "ofac", r"September 24, 2026 -", "24 Sep -"),
    ("one advisory row without its link", "fincen", r'href="/resources/advisories/fincen-advisory-fin-2026-a002"',
     'href="/elsewhere/fin-2026-a002"'),
    ("an item with an empty title", "ofsi", r"<title>Guidance: UK Financial Sanctions FAQs</title>", "<title> </title>"),
    ("an item with an empty title", "fincen", r'hreflang="en">FinCEN Advisory FIN-2026-A002</a>', 'hreflang="en"></a>'),
    ("an item with an empty title", "ofac", r'hreflang="en">Democratic Republic of the Congo-related Designations '
     r'Removals</a>', 'hreflang="en"></a>'),
    ("an item without a date", "nca", r"<pubDate>[^<]*</pubDate>", ""),
    ("an item without a date", "eu_council", r"<a10:updated>[^<]*</a10:updated>", ""),
    ("an item with a date in no known format", "fca", r"<pubDate>[^<]*</pubDate>", "<pubDate>yesterday</pubDate>"),
    # A body cut off inside the last row (the size cap, a dropped connection): nine rows parse, the
    # tenth is open when the input ends.
    ("a body ending inside an open views-row", "ofac", r'(?s)(<a href="/recent-actions/20260904" hreflang="en">).*',
     r"\1Iran-related Designations"),
]

MUTATIONS = {
    "no-marker-fincen": (SOURCES_PY, 'raise LayoutChanged("fincen: the listing table (th#view-title-table-column) is missing")',
                         "pass"),
    "empty-ok": (SOURCES_PY, 'raise LayoutChanged("ofac: the view is present but no views-row parsed")', "pass"),
    "ofsi-link-id": (SOURCES_PY, 'FeedItem(source, eid.strip(),', 'FeedItem(source, link.get("href"),'),
    "relative-url": (SOURCES_PY, 'urljoin(FINCEN_BASE, row["href"])', 'row["href"]'),
    "ofac-date-optional": (SOURCES_PY, 'if not row["href"] or not row["date"]:', 'if not row["href"]:'),
    "follow-redirects": (HTTP_PY, "        _check_host(newurl, self.allowed_hosts)\n", ""),
    "no-size-cap": (HTTP_PY, "    if len(body) > max_bytes:\n", "    if False:\n"),
    "skip-linkless-row": (SOURCES_PY, '            if row["title_cell"] and not row["href"]:\n', "            if False:\n"),
    "http-allowed": (HTTP_PY, 'ALLOWED_SCHEMES = ("https",)', 'ALLOWED_SCHEMES = ("https", "http")'),
    "any-port": (HTTP_PY, '(parts.netloc or "").lower() not in allowed_hosts', '(parts.hostname or "") not in allowed_hosts'),
    "untitled-ok": (SOURCES_PY, '        raise LayoutChanged("%s: the item %s has an empty title" % (source, where))\n',
                    "        pass\n"),
    "ofac-truncated-ok": (SOURCES_PY, '        raise LayoutChanged("ofac: the listing ends inside an open views-row (a '
                          'truncated body)")\n', "        pass\n"),
    "rss-date-optional": (SOURCES_PY, 'raise LayoutChanged("%s: the item %s has no date" % (source, where))', 'return ""'),
    "rss-unsorted": (SOURCES_PY, "return sorted(items, key=", "return list(items) or sorted(items, key="),
    "fca-host-open": (SOURCES_PY, 'frozenset({"www.fca.org.uk"}), parse_fca',
                      'frozenset({"www.fca.org.uk", "evil.example"}), parse_fca'),
    "narrow-except": (HTTP_PY, "    except (OSError, http.client.HTTPException) as exc:\n", "    except () as exc:\n"),
}


def load(name: str, path: Path, mutation) -> types.ModuleType:
    source = path.read_text(encoding="utf-8")
    if mutation in MUTATIONS and MUTATIONS[mutation][0] == path:
        old, new = MUTATIONS[mutation][1:]
        if source.count(old) != 1:
            raise SystemExit("MUTATION TARGET MISSING: %r is not in %s exactly once" % (old, path))
        source = source.replace(old, new)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    package, _, leaf = name.rpartition(".")
    setattr(importlib.import_module(package), leaf, module)
    return module


def raw(source: str) -> bytes:
    return (FIX / SNAPSHOTS[source][0]).read_bytes()


def adapter_checks(sources) -> list:
    out = []
    for name, (fname, sha) in sorted(SNAPSHOTS.items()):
        body = raw(name)
        out.append((hashlib.sha256(body).hexdigest() == sha, "%s: the snapshot %s is the pinned bytes" % (name, fname), ""))
        try:
            items = sources.SOURCES[name].parse(body)
        except LayoutChanged as exc:
            out.append((False, "%s: the snapshot parses" % name, str(exc)))
            continue
        want = EXPECTED[name]
        ids = hashlib.sha256("\n".join(i.item_id for i in items).encode("utf-8")).hexdigest()
        out.append((len(items) == want["count"] and ids == want["ids"],
                    "%s: %d items, ids in the pinned order" % (name, want["count"]), "%d items, ids %s" % (len(items), ids)))
        for end, it in (("first", items[0]), ("last", items[-1])):
            got = {k: getattr(it, k) for k in want[end]}
            out.append((got == want[end], "%s: the %s item is the pinned one, field by field" % (name, end),
                        "" if got == want[end] else "got %s" % got))
        hosts = sources.SOURCES[name].hosts
        off = [i.url for i in items if not re.match(r"^https://(%s)/" % "|".join(map(re.escape, hosts)), i.url)]
        out.append((not off and len({i.key for i in items}) == len(items),
                    "%s: every item URL is absolute on the source's hosts, and keys are unique" % name, "off: %s" % off[:2]))
    for label, name, pattern, repl in BREAKS:
        broken, n = re.subn(pattern, repl, raw(name).decode("utf-8"))
        try:
            got = sources.SOURCES[name].parse(broken.encode("utf-8"))
            ok, detail = False, "returned %d items" % len(got)
        except LayoutChanged as exc:
            ok, detail = True, str(exc)
        out.append((n >= 1 and ok, "%s: %s raises LayoutChanged, never an empty or partial list" % (name, label), detail))
    text = raw("ofsi").decode("utf-8")
    first = re.search(r"(?s)<entry>.*?</entry>", text).group(0)
    revised = first.replace("#2026-09-24T08:49:08Z</id>", "#2026-09-25T10:00:00Z</id>").replace(
        "<updated>2026-09-24T08:49:08Z</updated>", "<updated>2026-09-25T10:00:00Z</updated>")
    items = sources.parse_ofsi(text.replace(first, revised + first, 1).encode("utf-8"))
    out.append((len(items) == 21 and len({i.key for i in items}) == 21 and items[0].url == items[1].url,
                "ofsi: a revised publication (same link, new <id> timestamp) is a new item", "%d items" % len(items)))
    return out


# The spec's table: each new source's listing hosts and the hosts a document linked from an item may come from.
NEW_HOSTS = {"otsi": ({"www.gov.uk"}, {"assets.publishing.service.gov.uk"}),
             "fca": ({"www.fca.org.uk"}, {"www.fca.org.uk"}),
             "nca": ({"www.nationalcrimeagency.gov.uk"}, {"www.nationalcrimeagency.gov.uk"}),
             "eu_council": ({"www.consilium.europa.eu"}, {"www.consilium.europa.eu"}),
             "eba": ({"www.eba.europa.eu"}, {"www.eba.europa.eu"}),
             "amla": ({"www.amla.europa.eu"}, {"www.amla.europa.eu"}),
             "wolfsberg": ({"wolfsberg-group.org"}, {"db.wolfsberg-group.org"})}


def host_checks(sources) -> list:
    return [(set(sources.SOURCES[n].hosts) == h and set(sources.SOURCES[n].document_hosts) == d,
             "%s: hosts and document_hosts are exactly the spec's table" % n,
             "got %s / %s" % (sorted(sources.SOURCES[n].hosts), sorted(sources.SOURCES[n].document_hosts)))
            for n, (h, d) in NEW_HOSTS.items()]


def publisher_checks(sources, mutation) -> list:
    """tools/accept_run.py PUBLISHERS names every source: accepting an item from one without an entry is a KeyError."""
    import ast
    tree = ast.parse((ROOT / "tools" / "accept_run.py").read_text(encoding="utf-8"))
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "PUBLISHERS" for t in node.targets):
            names = ast.literal_eval(node.value)
    if mutation == "publisher-missing":
        names.pop("amla", None)
    missing = sorted((set(sources.SOURCES) | set(sources.MANUAL_SOURCES)) - set(names))
    return [(bool(names) and not missing, "every source has a publisher name in tools/accept_run.py PUBLISHERS",
             "missing: %s" % missing)]


def boundary_checks(fh) -> list:
    """The allowlist rule itself, under its real (https-only) setting, before transport_checks widens it."""
    hosts, out = frozenset({"www.fincen.gov"}), []
    for url, admitted in (("https://www.fincen.gov/x", True), ("https://WWW.FINCEN.GOV/x", True),
                          ("http://www.fincen.gov/x", False), ("https://www.fincen.gov:8443/x", False),
                          ("https://www.fincen.gov@evil.invalid/x", False),
                          ("https://evil.invalid@www.fincen.gov/x", False)):
        try:
            fh._check_host(url, hosts)
            got = True
        except fh.FetchRefused:
            got = False
        out.append((got == admitted, "the allowlist %s %s" % ("admits" if admitted else "refuses", url), ""))
    return out


def transport_checks(fh) -> list:
    # The local test server speaks http on its own port: widen the scheme for these checks only, and
    # lower the timeout so the stalling handlers below cost well under a second each.
    fh.REQUEST_GAP_SECONDS, fh.ALLOWED_SCHEMES, fh.TIMEOUT_SECONDS = 0, ("http",), 0.5
    hosts_seen = []
    release = threading.Event()  # set on shutdown, so a stalled handler thread ends at once

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            hosts_seen.append(self.headers.get("Host", "").split(":")[0])
            port = self.server.server_address[1]
            if self.path == "/stall-headers":  # accepts the request, never answers
                release.wait(10)
                return
            if self.path == "/stall-body":  # headers and part of the body, then nothing
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b"<p>partial")
                self.wfile.flush()
                release.wait(10)
                return
            if self.path == "/close":  # closes the connection without a response
                self.close_connection = True
                return
            if self.path == "/away":
                self.send_response(302)
                self.send_header("Location", "http://localhost:%d/doc" % port)
                self.end_headers()
                return
            if self.path == "/home":
                self.send_response(302)
                self.send_header("Location", "/doc")
                self.end_headers()
                return
            ctype, body = {"/big": ("text/html", b"x" * 2000), "/zip": ("application/zip", b"PK")}.get(
                self.path, ("text/html; charset=utf-8", b"<p>ok</p>"))
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads, block_on_close = True, False

    server = Server(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    allowed, types_ = frozenset({"127.0.0.1:%d" % port}), frozenset({"text/html", "application/pdf"})

    def get(path: str, host: str = "127.0.0.1"):
        try:
            got = fh.get("http://%s:%d%s" % (host, port, path), allowed_hosts=allowed, allowed_types=types_, max_bytes=1000)
            return "OK", got
        except fh.FetchRefused as exc:
            return "REFUSED", str(exc)

    out = []
    try:
        s, got = get("/doc")
        out.append((s == "OK" and got.body == b"<p>ok</p>" and got.content_type == "text/html",
                    "an allowlisted URL is fetched, with its content type", s))
        s, got = get("/home")
        out.append((s == "OK" and got.final_url.endswith("/doc"), "a redirect within the allowlist is followed", s))
        del hosts_seen[:]
        s, why = get("/away")
        out.append((s == "REFUSED" and "localhost" not in hosts_seen,
                    "a redirect off the allowlist is refused before any request reaches the other host",
                    "%s; hosts requested %s" % (s, hosts_seen)))
        del hosts_seen[:]
        s, why = get("/doc", host="localhost")
        out.append((s == "REFUSED" and not hosts_seen, "a URL off the allowlist is refused without a request", s))
        s, why = get("/big")
        out.append((s == "REFUSED" and "larger" in str(why), "a body over the size cap is refused", str(why)[-60:]))
        s, why = get("/zip")
        out.append((s == "REFUSED" and "application/zip" in str(why), "a content type not allowed is refused", str(why)[-60:]))
        for path, label in (("/stall-headers", "a server that stalls before its headers"),
                            ("/stall-body", "a server that stalls mid-body"),
                            ("/close", "a server that closes the connection without a response")):
            try:
                s, why = get(path)
            except Exception as exc:  # an escaping failure is the defect: the check fails, not the guard
                s, why = "ESCAPED", "%s: %s" % (type(exc).__name__, exc)
            out.append((s == "REFUSED", "%s is REFUSED (a FetchRefused), never a raw exception" % label,
                        "%s: %s" % (s, str(why)[-80:])))
    finally:
        release.set()
        server.shutdown()
        server.server_close()
    return out


RUNTIME_DIRS = ("feeds", "mcp_server", "agents", "tools")


def one_list_checks(mutation) -> list:
    """Spec §1: feeds/sources.py is the only place that names the live sources together. A string or tuple naming
    two or more source ids anywhere else in the runtime is a hand copy, which drifts the day a source is added."""
    import ast
    sys.path.insert(0, str(ROOT))
    from feeds.sources import SOURCES
    ids = set(SOURCES)
    copies = []
    for d in RUNTIME_DIRS:
        for path in sorted((ROOT / d).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel == "feeds/sources.py":
                continue
            text = path.read_text(encoding="utf-8")
            if mutation == "hand-list" and rel == "feeds/reconcile.py":
                text += '\nHAND = ("ofsi", "fincen", "ofac")\n'
            tree = ast.parse(text)
            docs = {id(n.body[0].value) for n in ast.walk(tree)
                    if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                    and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Tuple) and all(isinstance(e, ast.Constant) and e.value in ids for e in node.elts) \
                        and len(node.elts) >= 2:
                    copies.append("%s:%d tuple" % (rel, node.lineno))
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    named = {t for t in re.findall(r"[a-z_]+", node.value) if t in ids}
                    if len(named) >= 2:
                        copies.append("%s:%d %r" % (rel, node.lineno, node.value[:60]))
    return [(not copies, "no runtime module outside feeds/sources.py names the live sources together", copies)]


def rules_checks(mutation) -> list:
    """Spec §3: every live source has a triage rule entry (the empty string written explicitly means none)."""
    from feeds.sources import SOURCES
    rules = json.loads((ROOT / "feeds" / "triage_rules.json").read_text(encoding="utf-8"))
    if mutation == "rule-missing":
        rules.pop("fca", None)
    ok = set(rules) == set(SOURCES) and all(isinstance(v, str) for v in rules.values())
    return [(ok, "feeds/triage_rules.json has exactly one string rule per live source",
             sorted(set(SOURCES) ^ set(rules)))]


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the feed adapters and the allowlisted fetch")
    ap.add_argument("--mutate", choices=sorted(MUTATIONS) + ["hand-list", "publisher-missing", "rule-missing"],
                    help="break one rule; a check MUST fail")
    args = ap.parse_args(argv)
    fh = load("feeds.http", HTTP_PY, args.mutate)
    sources = load("feeds.sources", SOURCES_PY, args.mutate)
    if args.mutate:
        print("MUTATED: %s\n" % args.mutate)
    failures = 0
    for ok, label, detail in adapter_checks(sources) + boundary_checks(fh) + transport_checks(fh) \
            + one_list_checks(args.mutate) \
            + host_checks(sources) + publisher_checks(sources, args.mutate) + rules_checks(args.mutate):
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1
    if args.mutate:
        print("\n%s" % ("HELD: the mutation is detected (%d check%s failed)" % (failures, "" if failures == 1 else "s")
                        if failures else "NOTHING PROVED: every check passed with the rule broken"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED", failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
