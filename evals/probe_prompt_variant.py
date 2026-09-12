"""
Is the recall gap a capability limit, or is it instructed?

Usage:
    python evals/probe_prompt_variant.py ADV-2026-0016 <pdf> --runs 3

WHAT THIS TESTS. Traced on ADV-2026-0016 (2026-09-12): the golden label carries
10 governed typologies and all seven runs to date found 2-3. The trace showed
SAN006 RETRIEVED by the search tool, CONFIRMED with get_typology, and then
dropped -- so the search tool was not the constraint. Two candidates remain, and
both are in the prompt rather than in the agent:

  1. `SYSTEM_PROMPT` says "Prefer fewer, well-cited items over many weakly
     supported ones". The agent cites that rule back in its own
     extraction_notes as the reason it did not reproduce all fourteen of the
     alert's numbered red flags. It is following instructions.

  2. The golden set's document-shape convention -- in an INDICATOR-LIST document
     the indicators ARE the content, and a single bullet is sufficient evidence
     at low/medium confidence -- was an owner decision restated on 2026-09-11
     for LABELLERS. It never reached the agent's prompt. So the label and the
     agent apply different rules to the same document and the scorer calls the
     difference "recall".

The variant removes (1) and adds (2), verbatim from evals/golden/README.md.

NO GOVERNED SOURCE IS CHANGED. The variant is monkeypatched onto the module
attribute that `agent_options` reads at call time, so there is nothing to
restore and no chance of leaving an experimental prompt in the pipeline.

HOW TO READ THE RESULT. The seven existing runs of 0016 are the control
(2, 2, 2, 3, 3, 2, 3 governed typologies). If the variant does not move that,
the gap is the agent. If it does, a large part of what has been reported as a
recall gap is a prompt-label disagreement, and week 4 should not be built to
fix the agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import extract_advisory as ea  # noqa: E402

# INVERTED 2026-09-12: the document-shape rule was ADOPTED into SYSTEM_PROMPT, so
# the "variant" is now the PRE-ADOPTION prompt. The probe therefore still works,
# and still measures the same difference -- from the other side. A probe whose
# premise has been merged into the thing it tests can only raise; inverting it
# keeps a control band reproducible.
DROP = "- Whether an indicator is a typology depends on the shape of the document."

# Verbatim from evals/golden/README.md, "Labelling conventions".
_UNUSED_OLD_ADD = """- Whether an indicator is a typology depends on the shape of the document.
  In a narrative report, a red flag mentioned once in passing is not a typology; label what the report is about.
  In an indicator-list document -- a red alert, a FATF risk-indicator paper, a FinCEN red-flag section -- the indicators ARE the content. Each indicator, or each group of related indicators, may carry a typology, and a single bullet is sufficient evidence. Declining to label them would mean labelling almost nothing in the documents whose whole purpose is the list.
  Confidence carries the weight: one bullet supports a typology at low or medium; high needs the document to develop the technique.
"""


PRE_ADOPTION = "- Prefer fewer, well-cited items over many weakly supported ones.\n"


def variant_prompt() -> str:
    """The PRE-ADOPTION prompt: document-shape rule out, 'prefer fewer' back in."""
    p = ea.SYSTEM_PROMPT
    if DROP not in p:
        raise RuntimeError("the document-shape rule is not in SYSTEM_PROMPT as written; "
                           "this probe would test something other than it claims")
    lines = [ln for ln in p.splitlines(keepends=True)
             if not ln.startswith(DROP[:60]) and not ln.startswith("- Confidence carries the weight")
             and "indicators ARE the content" not in ln and not ln.startswith("  ")]
    out = "".join(lines)
    if "indicators ARE the content" in out:
        raise RuntimeError("failed to strip the document-shape rule")
    return out.replace("- Jurisdictions are ISO", PRE_ADOPTION + "- Jurisdictions are ISO")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Prompt-variant probe")
    ap.add_argument("advisory_id")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "repeats" / "promptvar")
    ap.add_argument("--model", default="claude-sonnet-5")
    args = ap.parse_args(argv)

    ea.SYSTEM_PROMPT = variant_prompt()          # the whole experiment, in one line
    print("variant prompt: 'prefer fewer' REMOVED, document-shape rule ADDED (%d chars)\n"
          % len(ea.SYSTEM_PROMPT))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.runs + 1):
        out = args.out_dir / ("%s.run%d.json" % (args.advisory_id, i))
        if out.exists():
            print("run %d already done, skipping" % i)
            continue
        print("=== variant run %d" % i)
        try:
            record, tel = asyncio.run(ea.extract(args.pdf, args.advisory_id, args.model, 5.0, 60))
        except Exception as exc:
            print("  FAILED: %s" % exc, file=sys.stderr)
            return 1
        out.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        gov = sorted({t.typology_id for t in record.typologies if t.typology_id})
        print("  governed typologies (%d): %s" % (len(gov), ", ".join(gov)))
        print("  emergent %d | actors %d | indicators %d | cost $%.2f | turns %s"
              % (len(record.emergent_candidates), len(record.actors), len(record.indicators),
                 tel["cost_usd"] or 0, tel["turns"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
