"""
Pin schema 1.4.0's `added_by` / `review_justification` pair.

Usage:
    python evals/check_added_by.py
    python evals/check_added_by.py --mutate   # drop the validator; the refusals MUST stop

WHY THE PAIR EXISTS. The additive reviewer (agents/review_advisory.py) finds
typologies the extraction missed -- measured full-set F1 0.510 -> 0.665 -- and it
earns each one by quoting the doctrine's own words. Its additions were held in
separate files precisely because merging them into a record would have lost WHICH
mechanism produced each claim and WHY.

The 2026-09-13 trace of ADV-2026-0016 found SAN006 retrieved, confirmed with
get_typology, and then dropped, with no record anywhere of why. Rule 3 governs
what ENTERS a record; nothing governed the reasoning behind it. An addition that
arrives without its justification is that same defect pointing the other way, so
the validator makes the reason travel with the claim or refuse the claim.

WHAT THIS PROTECTS, and it is the contract rather than the constant:
  1. `added_by` DEFAULTS to extractor, so every record written before 1.4.0 means
     what it always meant. A default that drifted would silently relabel history.
  2. A reviewer addition WITHOUT a justification is refused.
  3. An extractor entry WITH a justification is refused -- the field is not a
     general notes box, and a mechanism that can attach reasons to anything
     records nothing.
  4. The example record demonstrates BOTH values, because a contract nobody has
     written an instance of is a contract nobody has tested.

NOT A VACUOUS PASS. --mutate removes the validator and the two refusals must stop
firing. A guard never seen to fail is decoration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.advisory import SCHEMA_VERSION, AddedBy, TypologyReference  # noqa: E402

BASE = dict(family="tbml", typology_id="TBML001", label="Over invoicing", emergent=False,
            confidence="high",
            citations=[dict(page=4, quote="A customer that significantly overpays for a listed item.")])
JUST = ("TBML001 doctrine says the price of goods is intentionally inflated beyond their true "
        "market value; red flag 4 states the customer significantly overpays, which is that "
        "mechanism in payment terms.")


def refused(**kw) -> bool:
    try:
        TypologyReference(**{**BASE, **kw})
        return False
    except Exception:
        return True


def checks() -> list:
    out = []
    out.append((SCHEMA_VERSION == "1.4.0", "schema version is 1.4.0",
                "the pair shipped with this version; a bump without it is a silent contract change"))

    t = TypologyReference(**BASE)
    out.append((t.added_by is AddedBy.EXTRACTOR and t.review_justification is None,
                "added_by DEFAULTS to extractor",
                "every pre-1.4.0 record means what it always meant; got %r" % t.added_by.value))

    out.append((refused(added_by="reviewer"),
                "a reviewer addition WITHOUT a justification is refused",
                "the reason travels with the claim or the claim does not enter"))

    out.append((refused(review_justification=JUST),
                "an extractor entry WITH a justification is refused",
                "the field is not a general notes box"))

    out.append((not refused(added_by="reviewer", review_justification=JUST),
                "a reviewer addition WITH a justification is accepted",
                "the guard must not refuse the thing it exists to permit"))

    # The example record is the contract's only worked instance.
    ex = json.loads((ROOT / "evals" / "example_record.json").read_text(encoding="utf-8"))
    vals = {t.get("added_by", "extractor") for t in ex["typologies"]}
    out.append((vals == {"extractor", "reviewer"},
                "the example record demonstrates BOTH added_by values",
                "found %s -- a contract with no written instance is untested" % sorted(vals)))
    out.append((ex.get("schema_version") == SCHEMA_VERSION,
                "the example record declares the current schema version",
                "rule 1: the example is updated in the same commit as the bump"))
    return out


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the added_by contract")
    ap.add_argument("--mutate", action="store_true",
                    help="drop the validator; the two refusals MUST stop firing")
    args = ap.parse_args(argv)

    if args.mutate:
        # Remove the model validator the way a careless edit would: leave the
        # fields, delete the rule that makes them mean anything.
        TypologyReference.__pydantic_decorators__.model_validators.pop(
            "_reviewer_additions_carry_their_reason", None)
        TypologyReference.model_rebuild(force=True)
        print("MUTATED: validator removed. The two refusal checks must fail, or this\n"
              "         probe proves nothing about the contract.\n")

    failures = 0
    for ok, label, detail in checks():
        print("  %-4s %s\n         %s" % ("PASS" if ok else "FAIL", label, detail))
        failures += 0 if ok else 1

    if args.mutate:
        print("\n%s" % ("HELD: the probe detects the defect when the validator is removed" if failures
                        else "NOTHING PROVED: it passed with the validator gone"))
        return 0 if failures else 1
    print("\n%s (%d failure%s)" % ("HELD" if not failures else "REFUSED",
                                   failures, "" if failures == 1 else "s"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
