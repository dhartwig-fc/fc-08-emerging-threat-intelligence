"""
Deterministic text pages for an HTML document, so a quote can be cited as (page, verbatim text).

THE RULE, which is part of every HTML citation -- change it and every cited page number moves:
  1. Decode the pinned bytes as UTF-8, strictly. A page that is not UTF-8 is refused, never
     repaired, because a replacement character would sit inside a quote the matcher then checks.
  2. Keep the text inside <main>; if the page has none, inside <article>; else inside <body>.
  3. Drop everything inside DROP (navigation, headers, footers, scripts, forms and the like).
  4. A BLOCK tag ends a paragraph. Whitespace inside a paragraph collapses to single spaces.
     Entities are decoded (&amp; is &).
  5. Pages are filled with whole paragraphs, joined by a blank line, until the next paragraph
     would take the page past PAGE_CHARS. A paragraph is never split: one longer than
     PAGE_CHARS stands alone on its own page.
Only the standard library's html.parser is used, so the same bytes give the same pages on any
machine; no browser, whose rendering changes with its version, is involved.
"""

from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
from typing import Dict, List

PAGE_CHARS = 3000
SCOPES = ("main", "article", "body")
DROP = frozenset({"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "aside",
                  "form", "button"})
BLOCK = frozenset({"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th",
                   "table", "section", "article", "main", "blockquote", "pre", "dt", "dd", "dl", "br",
                   "hr", "figcaption", "caption"})
VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
                  "track", "wbr"})


class _Paragraphs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.paras: Dict[str, List[str]] = {s: [] for s in SCOPES}
        self.cur: Dict[str, List[str]] = {s: [] for s in SCOPES}

    def _break(self) -> None:
        for scope in SCOPES:
            text = " ".join("".join(self.cur[scope]).split())
            if text:
                self.paras[scope].append(text)
            self.cur[scope] = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self._break()
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in BLOCK:
            self._break()

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self._break()
        if tag in self.stack:  # an end tag with no open start tag is ignored
            while self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if any(t in DROP for t in self.stack):
            return
        for scope in SCOPES:
            if scope in self.stack:
                self.cur[scope].append(data)


def paragraphs(raw: bytes) -> List[str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("the document is not UTF-8 (%s); it is refused, not repaired" % exc)
    parser = _Paragraphs()
    parser.feed(text)
    parser.close()
    parser._break()
    for scope in SCOPES:
        if parser.paras[scope]:
            return parser.paras[scope]
    return []


def paginate(paras: List[str]) -> List[str]:
    pages: List[str] = []
    cur: List[str] = []
    size = 0
    for para in paras:
        if cur and size + 2 + len(para) > PAGE_CHARS:
            pages.append("\n\n".join(cur))
            cur, size = [], 0
        size += (2 if cur else 0) + len(para)
        cur.append(para)
    if cur:
        pages.append("\n\n".join(cur))
    return pages


def html_pages(raw: bytes) -> List[str]:
    return paginate(paragraphs(raw))


def pages_digest(pages: List[str]) -> str:
    """sha256 of the pages as canonical JSON: the value a guard pins."""
    return hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode("utf-8")).hexdigest()
