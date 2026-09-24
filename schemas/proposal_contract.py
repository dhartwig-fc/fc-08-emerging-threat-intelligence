"""
The proposal contract: ONE definition, shared by the side that writes a proposal
and the side that judges it.

mcp_server/knowledge_centre_server.py enforces this at proposal time;
governance/proposals.py re-asserts it at review time, because the queue is a
plain tracked file and anything could have changed a line since the server wrote
it. Until the final week-5 review the two sides each carried their own copy --
the server its Field bounds and its own hash, the gate nothing at all -- and
six hand-tampered copies of a real line (an empty quote, the quote "the",
neither or both of typology and emergent label, an invented stage, an edited
rationale keeping its old id) all passed the review-time re-check clean.
A rule the gate does not re-assert is a rule a text editor can remove.

agents/run_identity.py takes STAGES from here too, so the runner cannot start a
stage the gate would quarantine.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA = "proposal/2"
STAGES = ("extractor", "reviewer")

# Quote bounds, in characters. The server applies them as Field bounds on the
# agent's input; the gate applies them to the quote after strip, so whitespace
# padding cannot make "the" long enough.
QUOTE_MIN = 10
QUOTE_MAX = 600

# Keys that describe the WRITE, not the proposal: excluded from the id so the
# same proposal made twice has the same id.
_NOT_HASHED = ("proposal_id", "proposed_at")


def proposal_id(body: dict) -> str:
    """sha256 of the canonical body, first 16 hex characters.

    `body` is the queue line minus proposal_id and proposed_at (either may be
    present; they are dropped here). This is exactly the canonicalisation the
    server used before it was moved here, so every id already in data/proposals/
    still recomputes -- change it and every existing line quarantines.
    """
    canonical = {k: v for k, v in body.items() if k not in _NOT_HASHED}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
