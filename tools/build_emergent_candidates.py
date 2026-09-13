"""
Build data/emergent_candidates.json — the week-4 candidate list for the
Knowledge Centre.

Usage:
    python tools/build_emergent_candidates.py
    python tools/build_emergent_candidates.py --out data/emergent_candidates.json

WHAT THIS IS FOR. Every emergent entry is the pipeline saying "this technique is
real and the library does not hold it". Fifty such entries now exist across
fifteen advisories, from the extraction and from the additive reviewer. This
collects them with their evidence so a curator can decide which deserve a
governed typology id.

IT SUGGESTS ADJACENCY. IT DOES NOT ASSERT IDENTITY, and that is a measured
decision rather than caution.

The obvious artefact is clustered: group the variants, one row per technique. It
was built and rejected. Measured 2026-09-13 over all fifty labels:

  containment >= 0.50, as the scorer uses   39 clusters, and the largest merged
                                            FOUR distinct techniques on the words
                                            "money laundering" -- Cyber-Enabled
                                            Fraud, DPRK Proliferation Financing,
                                            Money Laundering from Environmental
                                            Crime, and Services-Based Money
                                            Laundering.

  generic words dropped, >= 0.67            44 clusters, six with more than one
                                            member -- and reading them, only ONE
                                            is unambiguously right (the two Black
                                            Market Peso Exchange variants).
                                            "Cryptocurrency Layering via Mixing
                                            Services" merged with "Services-Based
                                            Money Laundering" on the word
                                            "services".

The scorer's 0.50 threshold was validated for a different task: matching ONE
predicted label against ONE golden label, a paraphrase pair. Clustering arbitrary
labels against each other is not that task, and in a corpus where every label
names a money-laundering technique the domain vocabulary carries no
discriminating power. Applying a threshold validated for one job to another is
the error this project has made repeatedly; this file is where it was caught
before shipping.

So each candidate carries `near_neighbours` -- the labels it resembles, with the
score -- and the curator decides whether they are the same technique. A wrong
suggestion costs a moment's reading. A wrong merge silently destroys the evidence
that two advisories described different things.

PROVENANCE IS PER ENTRY. Extraction and reviewer additions stay distinguishable,
because they come from different mechanisms with different failure modes and a
curator should be able to weigh them differently.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.advisory import SCHEMA_VERSION  # noqa: E402

_spec = importlib.util.spec_from_file_location("fc08_score", ROOT / "evals" / "score.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

# Reported alongside every neighbour score so a reader knows what it means.
NEIGHBOUR_FLOOR = 0.50

# Dropped when looking for neighbours ONLY. In this corpus every label names a
# money-laundering technique, so these are the domain's "the" and "of" and they
# make unrelated labels look alike. The labels themselves are reported verbatim.
_GENERIC_PREFIXES = ("money", "laund", "financ", "based", "schem", "abuse")


def _neighbour_tokens(label: str) -> frozenset:
    return frozenset(w for w in sc.tokens(label)
                     if not any(w.startswith(g) for g in _GENERIC_PREFIXES))


def collect() -> list:
    """Every emergent entry from the records and the reviewer, with provenance."""
    out = []
    for p in sorted((ROOT / "data" / "records").glob("ADV-2026-*.json")):
        if "schema-" in p.name or "week1" in p.name:
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for t in d.get("typologies", []):
            if not t.get("typology_id"):
                out.append({"advisory_id": d["advisory_id"], "source": "extraction",
                            "label": t["label"], "family": t.get("family"),
                            "confidence": t.get("confidence"),
                            "citations": t.get("citations", [])})
    for sub in ("rep1", "rep2", "rep3", "rest"):
        d_ = ROOT / "data" / "reviewed" / sub
        if not d_.exists():
            continue
        for p in sorted(d_.glob("*.additions.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            for a in d.get("additions", []):
                if not a.get("typology_id"):
                    out.append({"advisory_id": d["advisory_id"], "source": "reviewer",
                                "label": a["label"], "family": a.get("family"),
                                "confidence": a.get("confidence"),
                                "citations": a.get("citations", []),
                                "doctrine_justification": a.get("doctrine_justification"),
                                "where_found": a.get("where_found")})
    return out


def with_neighbours(entries: list) -> list:
    """Attach near neighbours. Suggestion, not assertion -- see the module docstring."""
    toks = [_neighbour_tokens(e["label"]) for e in entries]
    for i, e in enumerate(entries):
        near = []
        for j, other in enumerate(entries):
            if i == j or other["label"] == e["label"]:
                continue
            s = sc.containment(toks[i], toks[j])
            if s >= NEIGHBOUR_FLOOR:
                near.append({"label": other["label"], "advisory_id": other["advisory_id"],
                             "source": other["source"], "score": round(s, 2)})
        near.sort(key=lambda n: (-n["score"], n["label"]))
        e["near_neighbours"] = near
    return entries


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build the emergent candidate list")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "emergent_candidates.json")
    args = ap.parse_args(argv)

    entries = with_neighbours(collect())
    # Most evidence first: a technique several advisories describe is a better
    # library candidate than one a single document mentions once.
    entries.sort(key=lambda e: (-len(e["near_neighbours"]), e["advisory_id"], e["label"]))

    doc = {
        "generated": date.today().isoformat(),
        "generated_by": "tools/build_emergent_candidates.py",
        "schema_version_of_records": SCHEMA_VERSION,
        "counts": {
            "candidates": len(entries),
            "distinct_labels": len({e["label"] for e in entries}),
            "advisories": len({e["advisory_id"] for e in entries}),
            "from_extraction": sum(1 for e in entries if e["source"] == "extraction"),
            "from_reviewer": sum(1 for e in entries if e["source"] == "reviewer"),
            "with_near_neighbours": sum(1 for e in entries if e["near_neighbours"]),
        },
        "method": (
            "Every typology entry carrying no typology_id, from the 20 records and from the "
            "additive reviewer's additions. near_neighbours are labels scoring >= %.2f on token "
            "containment after generic domain words are dropped." % NEIGHBOUR_FLOOR
        ),
        "caveat": (
            "NEIGHBOURS ARE A SUGGESTION, NOT A MERGE. Automatic clustering was built and "
            "rejected: at the scorer's 0.50 threshold it merged four distinct techniques on the "
            "words 'money laundering', and at the best threshold tested only one of six "
            "multi-member clusters was unambiguously right. The scorer's threshold was validated "
            "for matching one predicted label against one golden label, which is a different "
            "task. A wrong suggestion costs a moment's reading; a wrong merge destroys the "
            "evidence that two advisories described different things. The curator decides."
        ),
        "candidates": entries,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    c = doc["counts"]
    print("Wrote %s" % args.out)
    print("  %d candidates, %d distinct labels, across %d advisories"
          % (c["candidates"], c["distinct_labels"], c["advisories"]))
    print("  from extraction %d | from reviewer %d | with near neighbours %d"
          % (c["from_extraction"], c["from_reviewer"], c["with_near_neighbours"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
