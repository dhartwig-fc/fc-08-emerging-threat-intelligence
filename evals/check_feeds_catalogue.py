"""
Pin the triage back-catalogue (evals/feeds/catalogue.json) and its draft labels (evals/feeds/labels.json).

Usage:
    python evals/check_feeds_catalogue.py
    python evals/check_feeds_catalogue.py --mutate drop-item      # an item removed from the set
    python evals/check_feeds_catalogue.py --mutate minted-key     # a key not derived from its item
    python evals/check_feeds_catalogue.py --mutate dup-key        # one item listed twice
    python evals/check_feeds_catalogue.py --mutate no-text        # a document with no text pages
    python evals/check_feeds_catalogue.py --mutate unlabelled     # a catalogue item with no draft label
    python evals/check_feeds_catalogue.py --mutate bad-label      # a label other than relevant | not_relevant
    python evals/check_feeds_catalogue.py --mutate long-reason    # a draft reason over 300 characters
    python evals/check_feeds_catalogue.py --mutate rubric-edited  # the rubric changed after its hash was taken

WHAT IT HOLDS:
  fixed once    the catalogue's bytes are its canonical form and hash to CATALOGUE_SHA256, pinned the day
                it was built: the set cannot be rebuilt, re-ordered or edited without this guard saying so;
  the set       PER_SOURCE items listed per source, each either in "items" or in "excluded" with a reason;
  derived keys  every key is FeedItem's own derivation from the item, and no key or item id repeats;
  readable      every document is pinned by a 64-hex sha256, with at least one text page;
  where         the catalogue and labels are tracked; evals/feeds/docs/ is gitignored and holds nothing tracked;
  labels        (once labels.json exists) one draft label per catalogue item and no other, each relevant |
                not_relevant with a reason of 1..300 characters, drafted before any repeat, under a rubric
                whose sha256 is recorded beside it.

The documents themselves are gitignored, so this guard never opens them: evals/run_feeds_triage.py
refuses to start on a missing or changed copy, and the server refuses to serve one.

COLD. Tracked files and git only.

NOT A VACUOUS PASS. Each --mutate changes the loaded catalogue or labels in memory; a check must fail.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from feeds.model import FeedItem  # noqa: E402
from feeds.triage import REASON_MAX, VERDICTS  # noqa: E402
import build_feeds_catalogue as bfc  # noqa: E402

CATALOGUE = ROOT / "evals" / "feeds" / "catalogue.json"
LABELS = ROOT / "evals" / "feeds" / "labels.json"
# Pinned the day the catalogue was built (Task 3). Moving it is a new back-catalogue: an owner decision.
CATALOGUE_SHA256 = "90b57e8ba0224c49506ac8070b731e637d9bfde497b6c0aebdf6fe41f9ed3819"
LABELS_SCHEMA = "fc08-triage-labels/1"
# False until Task 5 writes labels.json; flipped to True in that commit, after which a missing or
# partial labels file FAILS rather than being skipped.
LABELS_DRAFTED = False
FIELDS = ("source", "item_id", "title", "url", "published", "summary")


def _git(*args) -> str:
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True).stdout


def catalogue_checks(cat: dict, raw: bytes) -> list:
    out = []
    items, excluded = cat.get("items", []), cat.get("excluded", [])
    out.append((raw.decode("utf-8") == bfc.dump(json.loads(raw)) and cat.get("schema") == bfc.SCHEMA,
                "the file is the builder's canonical form, schema %s" % bfc.SCHEMA, cat.get("schema")))
    digest = hashlib.sha256(bfc.dump(cat).encode("utf-8")).hexdigest()
    out.append((digest == CATALOGUE_SHA256, "the catalogue hashes to the sha256 pinned when it was built",
                digest[:16]))
    per = {s: sum(1 for it in items + excluded if it["source"] == s) for s in bfc.ORDER}
    out.append((per == {s: bfc.PER_SOURCE for s in bfc.ORDER} and all(e.get("reason") for e in excluded),
                "each source lists %d items, every one scored or excluded with a reason" % bfc.PER_SOURCE,
                "%s; %d excluded" % (per, len(excluded))))
    minted = [it["key"] for it in items + excluded if FeedItem(**{k: it[k] for k in FIELDS}).key != it["key"]]
    out.append((not minted, "every key is FeedItem's derivation from its item", minted[:3]))
    keys = [it["key"] for it in items + excluded]
    ids = [(it["source"], it["item_id"]) for it in items + excluded]
    out.append((len(set(keys)) == len(keys) and len(set(ids)) == len(ids), "no key or item id repeats",
                "%d keys" % len(keys)))
    bad = [it["key"] for it in items
           if not (re.fullmatch(r"[0-9a-f]{64}", (it.get("document") or {}).get("sha256", ""))
                   and it["document"].get("ext") in ("html", "pdf") and it["document"].get("text_pages", 0) >= 1)]
    out.append((items and not bad, "every scored item's document is pinned by sha256 and has text",
                "%d items; bad %s" % (len(items), bad[:3])))
    tracked_docs = _git("ls-files", "evals/feeds/docs").strip()
    ignored = subprocess.run(["git", "check-ignore", "-q", "evals/feeds/docs/probe.html"], cwd=ROOT).returncode == 0
    tracked = _git("ls-files", "evals/feeds/catalogue.json").strip()
    out.append((ignored and not tracked_docs and tracked == "evals/feeds/catalogue.json",
                "the catalogue is tracked; evals/feeds/docs/ is gitignored and holds nothing tracked",
                "ignored=%s tracked_docs=%r" % (ignored, tracked_docs[:60])))
    return out


def label_checks(cat: dict, labels: dict) -> list:
    out = []
    keys = {it["key"] for it in cat["items"]}
    got = labels.get("labels", {})
    out.append((labels.get("schema") == LABELS_SCHEMA and set(got) == keys,
                "one draft label per scored catalogue item, and no other",
                "missing %s; extra %s" % (sorted(keys - set(got))[:3], sorted(set(got) - keys)[:3])))
    bad = sorted(k for k, v in got.items()
                 if v.get("label") not in VERDICTS or not 1 <= len((v.get("reason") or "").strip()) <= REASON_MAX)
    out.append((not bad, "every label is relevant | not_relevant with a reason of 1..%d characters" % REASON_MAX,
                bad[:3]))
    rubric = labels.get("rubric", "")
    out.append((rubric and hashlib.sha256(rubric.encode("utf-8")).hexdigest() == labels.get("rubric_sha256")
                and labels.get("catalogue_sha256") == CATALOGUE_SHA256
                and labels.get("drafted_by") == "claude-in-session"
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", labels.get("drafted_on", "")),
                "the labels name their rubric by sha256, the catalogue they label, who drafted them and when",
                labels.get("drafted_on")))
    on_disk = LABELS.read_text(encoding="utf-8") if LABELS.exists() else ""
    out.append((_git("ls-files", "evals/feeds/labels.json").strip() == "evals/feeds/labels.json"
                and on_disk == bfc.dump(json.loads(on_disk or "{}")),
                "the labels are tracked, in canonical form (their sha256 is what every repeat records)", ""))
    return out


def mutate(name: str, cat: dict, labels):
    cat, labels = copy.deepcopy(cat), copy.deepcopy(labels)
    first = cat["items"][0]["key"]
    if name == "drop-item":
        cat["items"].pop()
    elif name == "minted-key":
        cat["items"][0]["key"] = "%s:0123456789abcdef" % cat["items"][0]["source"]
    elif name == "dup-key":
        cat["items"].append(copy.deepcopy(cat["items"][0]))
    elif name == "no-text":
        cat["items"][0]["document"]["text_pages"] = 0
    elif labels is None:
        raise SystemExit("MUTATION %s needs the draft labels (LABELS_DRAFTED is False)" % name)
    elif name == "unlabelled":
        labels["labels"].pop(first)
    elif name == "bad-label":
        labels["labels"][first]["label"] = "maybe"
    elif name == "long-reason":
        labels["labels"][first]["reason"] = "x" * (REASON_MAX + 1)
    elif name == "rubric-edited":
        labels["rubric"] += " Edited later."
    return cat, labels


MUTATIONS = ("drop-item", "minted-key", "dup-key", "no-text", "unlabelled", "bad-label", "long-reason",
             "rubric-edited")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Pin the triage back-catalogue and its draft labels")
    ap.add_argument("--mutate", choices=MUTATIONS, help="break one rule in memory; a check MUST fail")
    args = ap.parse_args(argv)
    raw = CATALOGUE.read_bytes()
    cat = json.loads(raw)
    labels = None
    if LABELS_DRAFTED:
        labels = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {"labels": {}}
    if args.mutate:
        cat, labels = mutate(args.mutate, cat, labels)
        print("MUTATED: %s\n" % args.mutate)
    results = catalogue_checks(cat, raw)
    if labels is not None:
        results += label_checks(cat, labels)
    else:
        print("  NOTE LABELS_DRAFTED is False: the draft labels are Task 5's, and their checks did not run\n")
    failures = 0
    for ok, label, detail in results:
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
