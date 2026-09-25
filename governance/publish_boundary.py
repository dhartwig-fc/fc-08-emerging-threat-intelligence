"""
What a page leaving this repository must not carry.

A public page may name advisory ids, run ids, typology ids, dates and public URLs.
It must not name a local path (it leaks a machine), an internal file (it points a
reader at something they cannot open and tells them how the governance is stored),
or anyone's email address. violations() returns every offending substring; a
publisher refuses a page with any.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import List, Optional, Pattern, Tuple

from governance import decisions as gd

FORBIDDEN_LITERALS: Tuple[str, ...] = (
    ".jsonl", ".superpowers", ".venv",
    gd.LOG.name, gd.APPROVED_LINKS.name, gd.APPROVED_EMERGENT.name,
)
_PATH_PATTERNS: Tuple[Pattern, ...] = (
    re.compile(r"/Users/[^\s\"'<]*"),
    re.compile(r"/home/[^\s\"'<]*"),
    re.compile(r"~/[^\s\"'<]*"),
    re.compile(r"\b[A-Za-z]:\\[^\s\"'<]*"),
)
_INTERNAL_PATTERNS: Tuple[Pattern, ...] = (
    re.compile(r"(?<![A-Za-z0-9./-])data/[^\s\"'<]*"),
)
_EMAIL: Optional[Pattern] = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def violations(text: str) -> List[str]:
    found = set()
    for lit in FORBIDDEN_LITERALS:
        if lit and lit in text:
            found.add(lit)
    for pat in _PATH_PATTERNS:
        found.update(m.group(0) for m in pat.finditer(text))
    for pat in _INTERNAL_PATTERNS:
        found.update(m.group(0) for m in pat.finditer(text))
    if _EMAIL is not None:
        found.update(m.group(0) for m in _EMAIL.finditer(text))
    # Also scan percent-encoded text
    unquoted = urllib.parse.unquote(text)
    if unquoted != text:
        for lit in FORBIDDEN_LITERALS:
            if lit and lit in unquoted:
                found.add(lit)
        for pat in _PATH_PATTERNS:
            found.update(m.group(0) for m in pat.finditer(unquoted))
        for pat in _INTERNAL_PATTERNS:
            found.update(m.group(0) for m in pat.finditer(unquoted))
        if _EMAIL is not None:
            found.update(m.group(0) for m in _EMAIL.finditer(unquoted))
    return sorted(found)
