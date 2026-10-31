# Six more regulators Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** The Friday sweep reads nine regulators (FinCEN, OFAC, OFSI, OTSI, FCA, NCA, EU Council, EBA, AMLA) from one
source list, with per-source triage rules as data, a US$10 / 20-item budget, and a listing-only dry run.

**Architecture:** `feeds/sources.py` stays the only declaration; every other module reads it. One RSS parser serves
five sources and the gov.uk Atom parser serves OFSI and OTSI. Rules move to `feeds/triage_rules.json`. The scan page
already lists live sources from `SOURCES`, so it follows with a rebuild.

**Tech Stack:** Python 3 stdlib (`xml.etree`, `datetime`, `zoneinfo`), fc-08 `.venv` at `~/fc-08-schedule/.venv`.

**Spec:** `docs/superpowers/specs/2026-10-31-six-more-regulators-design.md`

## Global constraints

- Work in `~/fc-08-scan-mechanics`, branch `sdd/six-regulators` (stacked on `sdd/scan-page-three-paths`). A full
  clone, never a linked worktree.
- Python: `~/fc-08-schedule/.venv/bin/python`.
- Commits: `PATH=~/fc-08-schedule/.venv/bin:$PATH env -u ANTHROPIC_API_KEY git commit`, explicit staging, never
  `-a`, never `--no-verify`, no Co-Authored-By trailer. No `.bak` files. Nothing published without the owner's go.
- Source ids, exactly: `fincen`, `ofac`, `ofsi`, `otsi`, `fca`, `nca`, `eu_council`, `eba`, `amla`.

## Rulings (made while planning)

- **R1, commits.** Task 1 changes no page and is committed alone. Tasks 2-5 change the published scan page (its live
  list and schema version come from code), and fc-08's pre-commit hook refuses a page that differs from its
  published copy, so tasks 2-5 are committed ONCE, in task 6, after the republish. Cost if wrong: none.
- **R2, the orchestrator's own cap scales with the item cap.** The spec doubles the triage cap (10 to 20) and the
  ceiling (US$5 to US$10). Twice the items means about twice the orchestrator's turns and spend, so its session cap
  (`MAX_BUDGET_USD`) and `MAX_TURNS` double too. Extraction is unchanged. Cost if wrong: the session stops early
  and leaves items UNFINISHED, which carry forward.
- **R3, the measured triage prompt changes.** The prompt names its sources inline, so nine sources change
  `PROMPT_SHA256`. The triage band on the scan page (recall/precision, measured 2026-09-27) was measured on the
  three-source prompt. Task 2 keeps the measurement and the page states the prompt it was measured on. Whether to
  re-measure (an eval run that costs money) is an owner decision, recorded and not taken here.
- **R4, mutation targets follow the refactor.** `evals/check_feed_adapters.py` mutates `feeds/sources.py` by exact
  text replacement. Where a refactor moves a target's text, its old/new strings are updated, and each mutation is
  re-run and must still fail.
- **R5, task 1 is byte-identical.** The prompt's source list is built from a tuple `ORDER` in `sources.py`
  (`("ofsi", "fincen", "ofac")` first), so task 1 renders today's exact prompt; `PROMPT_SHA256` and
  `FULL_PROMPT_SHA256` must not move in task 1.

## File structure

| File | Task | Change |
|---|---|---|
| `feeds/sources.py` | 1, 2 | `ORDER`, `named()`, `KEY_PATTERN`; gov.uk Atom generalised; `_parse_rss`; six `Source` entries |
| `mcp_server/feeds_server.py` | 1 | five key/source patterns read `KEY_PATTERN` / `SOURCE_PATTERN` |
| `feeds/reconcile.py` | 1 | `SOURCES` read from `feeds.sources.ORDER` |
| `agents/orchestrate_feeds.py` | 1, 3, 4 | prompt source list from `named()`; rules from JSON; caps |
| `feeds/triage_rules.json` | 3 | new: one rule per source |
| `schemas/advisory.py` | 2 | `SourceType` +4, `SCHEMA_VERSION` 1.5.0 |
| `tools/count_new.py` | 4 | new: the listing-only dry run |
| `tools/build_scan_demo.py` | 5 | `DISPLAY` +4; Europol's reason; triage-band prompt note |
| `tests/fixtures/feeds/*` | 2 | six recorded listings |
| `evals/check_feed_adapters.py` | 1, 2, 3 | one-list guard; six adapters pinned; rules guard |
| other `evals/check_*.py` | 1-5 | updated where they mean "every source" |

---

### Task 1: one source list (no behaviour change)

**Files:** `feeds/sources.py`, `mcp_server/feeds_server.py`, `feeds/reconcile.py`, `agents/orchestrate_feeds.py`, `evals/check_feed_adapters.py`.

- [ ] **Step 1: Record today's prompt hashes and fetch behaviour.**

```bash
cd ~/fc-08-scan-mechanics && ~/fc-08-schedule/.venv/bin/python -c "import sys; sys.path.insert(0,'.'); import agents.orchestrate_feeds as o; print(o.PROMPT_SHA256, o.FULL_PROMPT_SHA256)" | tee /tmp/fc08-prompt-before.txt
```

- [ ] **Step 2: Failing guard.** In `evals/check_feed_adapters.py` add, and call from `main()` alongside the existing
  check groups (its results reported like theirs):

```python
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
```

  Register `"hand-list"` in the `--mutate` choices and the docstring's mutation list. (The other mutations are
  `MUTATIONS` text replacements; `hand-list` is applied inside the check, so add it to the `choices` list without a
  `MUTATIONS` entry, or give it a no-op entry if `choices=sorted(MUTATIONS)` requires one: `"hand-list": (None, "", "")`
  and make `load()` skip a `None` path.) Ensure `import re` and `import sys` are present.

- [ ] **Step 3: Run; expect FAIL** naming `mcp_server/feeds_server.py` (five patterns), `feeds/reconcile.py:32` and
  `agents/orchestrate_feeds.py` (the prompt lines).

  `~/fc-08-schedule/.venv/bin/python evals/check_feed_adapters.py | grep -E "FAIL|HELD|REFUSED"`

- [ ] **Step 4: Implement.** In `feeds/sources.py`, after `SOURCES`:

```python
# The order sources are named in the triage prompt and listed in a run. Appending keeps every earlier prompt's
# bytes (plan R5); a source missing here, or one here but not in SOURCES, is refused at import.
ORDER = ("ofsi", "fincen", "ofac")
if set(ORDER) != set(SOURCES) or len(ORDER) != len(SOURCES):
    raise RuntimeError("feeds.sources: ORDER %r and SOURCES %r disagree" % (ORDER, sorted(SOURCES)))
SOURCE_PATTERN = r"^(%s)$" % "|".join(ORDER)
KEY_PATTERN = r"^(%s):[0-9a-f]{16}$" % "|".join(ORDER)


def named() -> str:
    """'ofsi, fincen and ofac': the sources in ORDER, as the prompt names them."""
    return ORDER[0] if len(ORDER) == 1 else ", ".join(ORDER[:-1]) + " and " + ORDER[-1]
```

  In `mcp_server/feeds_server.py`: import `KEY_PATTERN, SOURCE_PATTERN, named` from `feeds.sources` (extend the line-55
  import); line ~80 becomes `Field(..., pattern=SOURCE_PATTERN, description=named())`, and each of the four
  `pattern=r"^(ofsi|fincen|ofac):[0-9a-f]{16}$"` becomes `pattern=KEY_PATTERN`.

  In `feeds/reconcile.py`: `from feeds.sources import ORDER` and `SOURCES = ORDER`.

  In `agents/orchestrate_feeds.py`: import `named` from `feeds.sources`; in `TRIAGE_PROMPT` replace the literal
  `ofsi, fincen and ofac` with the token `__SOURCES__` and append `.replace("__SOURCES__", named())` to the
  constant's definition; in `_prompt()` replace both literal `ofsi, fincen and ofac` with `" + named() + "`
  (i.e. `"Run %s. Triage every new item from %s, then queue extraction." % (run.run_id, named())` and the same for
  the non-live line).

- [ ] **Step 5: Prove byte identity and green.**

```bash
cd ~/fc-08-scan-mechanics && ~/fc-08-schedule/.venv/bin/python -c "import sys; sys.path.insert(0,'.'); import agents.orchestrate_feeds as o; print(o.PROMPT_SHA256, o.FULL_PROMPT_SHA256)" | diff - /tmp/fc08-prompt-before.txt && echo PROMPT-IDENTICAL
~/fc-08-schedule/.venv/bin/python evals/check_feed_adapters.py | tail -2
PYTHONPYCACHEPREFIX=/tmp/mut-hand ~/fc-08-schedule/.venv/bin/python evals/check_feed_adapters.py --mutate hand-list | grep -E "FAIL|HELD:"
~/fc-08-schedule/.venv/bin/python tools/check_all.py | tail -3
```
  Expected: `PROMPT-IDENTICAL`; the adapter guard HELD; `hand-list` fails exactly the one-list clause; check_all
  `PASS: N run, 0 not run, 0 failed`. If another guard names the sources in a way the new clause flags, that guard is
  in `evals/`, which the clause does not scan; only runtime dirs are scanned.

- [ ] **Step 6: Commit (plan R1).**

```bash
git add feeds/sources.py mcp_server/feeds_server.py feeds/reconcile.py agents/orchestrate_feeds.py evals/check_feed_adapters.py
PATH=~/fc-08-schedule/.venv/bin:$PATH env -u ANTHROPIC_API_KEY git commit -m "Six regulators 1/6: one source list -- feeds_server, reconcile and the orchestrator read feeds.sources; a guard refuses a hand copy (prompt bytes unchanged)"
```

### Task 2: six sources, two parsers, the schema

**Files:** `feeds/sources.py`, `schemas/advisory.py`, `tests/fixtures/feeds/`, `evals/check_feed_adapters.py`, `evals/check_added_by.py`.

- [ ] **Step 1: Record the six listings as fixtures** (public pages, fetched today), named the way `raw(source)` in
  `evals/check_feed_adapters.py` reads them (read `raw()` first; it maps a source to a file under
  `tests/fixtures/feeds/`):

```bash
cd ~/fc-08-scan-mechanics/tests/fixtures/feeds && A="Mozilla/5.0 (fc-08 fixture)"
curl -sSL -A "$A" -o otsi.atom "https://www.gov.uk/government/organisations/office-of-trade-sanctions-implementation.atom"
curl -sSL -A "$A" -o fca.rss "https://www.fca.org.uk/news/rss.xml"
curl -sSL -A "$A" -o nca.rss "https://www.nationalcrimeagency.gov.uk/news?format=feed&type=rss"
curl -sSL -A "$A" -o eu_council.rss "https://www.consilium.europa.eu/en/rss/pressreleases.ashx"
curl -sSL -A "$A" -o eba.rss "https://www.eba.europa.eu/news-press/news/rss.xml"
curl -sSL -A "$A" -o amla.rss "https://www.amla.europa.eu/node/19/rss_en"
grep -c "<entry>" otsi.atom; for f in fca nca eu_council eba amla; do printf "%s " $f; grep -o "<item>" $f.rss | wc -l; done
```
  Rename to whatever extension `raw()` expects if it is not the `listing_ext`. Expected counts near 20/13+/20/20/10/30.

- [ ] **Step 2: Failing adapter checks.** Extend the pinned expectations in `adapter_checks` (the structure that
  pins count, id digest, first and last item for fincen/ofac/ofsi) with one entry per new source. Fill the pinned
  values from the parser's output in step 4, after checking by eye that the first and last items match the fixture
  (title and date of the first and last `<item>`/`<entry>`). Add mutations to `MUTATIONS`:

  - `rss-date-optional`: in `_rss_date`, the final `raise LayoutChanged("%s: the item %s has no date" % (source, where))`
    becomes `return ""` -- an undated item MUST be refused.
  - `rss-unsorted`: in `_parse_rss`, `return sorted(items, key=` becomes `return list(items) or sorted(items, key=` --
    AMLA's out-of-order feed MUST come back newest first.
  - `fca-host-open`: in the `fca` `Source`, `frozenset({"www.fca.org.uk"}), parse_fca` becomes
    `frozenset({"www.fca.org.uk", "evil.example"}), parse_fca` -- a host off the declared list MUST fail a clause that
    pins each new source's `hosts` to the spec's table.

  And a clause pinning each new source's `hosts` and `document_hosts` to the spec's table exactly.

- [ ] **Step 3: Run; expect FAIL** (no such sources yet).

- [ ] **Step 4: Implement.** In `feeds/sources.py`, generalise the gov.uk parser (keep `parse_ofsi` as a name):

```python
def _parse_govuk_atom(source: str, raw: bytes) -> List[FeedItem]:
    # the body of today's parse_ofsi, with every literal "ofsi" in a message or FeedItem replaced by `source`
    ...


def parse_ofsi(raw: bytes) -> List[FeedItem]:
    return _parse_govuk_atom("ofsi", raw)


def parse_otsi(raw: bytes) -> List[FeedItem]:
    return _parse_govuk_atom("otsi", raw)
```
  (Move parse_ofsi's existing body into `_parse_govuk_atom` verbatim except for the `source` substitution. Then apply
  plan R4 to every `MUTATIONS` entry whose old text moved.)

  Add the RSS parser after the Atom one:

```python
# ---------------------------------------------------------------------------- RSS 2.0 (FCA, NCA, EU Council, EBA, AMLA)

RSS_DATE_FORMATS = ("%a, %d %b %Y %H:%M:%S %z",   # RFC 822 with a numeric zone (NCA, EBA, AMLA)
                    "%a, %d %b %Y %H:%M:%S %Z",   # RFC 822 with GMT/UTC
                    "%A, %B %d, %Y - %H:%M")      # FCA: "Friday, October 30, 2026 - 09:00", London wall-clock


def _rss_date(source: str, item, where: str) -> str:
    """An item's date as ISO 8601 UTC. pubDate first, then a10:/atom:updated (EU Council). Never today."""
    raw = (item.findtext("pubDate") or "").strip()
    if raw:
        for fmt in RSS_DATE_FORMATS:
            try:
                when = datetime.strptime(raw, fmt)
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=ZoneInfo("Europe/London"))
            return when.astimezone(timezone.utc).isoformat()
        raise LayoutChanged("%s: the item %s has a pubDate %r in no known format" % (source, where, raw))
    updated = (item.findtext(ATOM + "updated") or "").strip()
    if ISO_DATE.match(updated):
        return datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
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
```
  Imports: `from datetime import datetime, timezone` and `from zoneinfo import ZoneInfo`. `DATE_FIELD` is the name of
  `FeedItem`'s fifth field (read `feeds/model.py`; define `DATE_FIELD = "<that name>"` beside `ISO_DATE`). If the
  existing parsers' date strings are plain `YYYY-MM-DD` (OFAC) and `feeds/` compares dates as strings anywhere,
  check that an ISO timestamp sorts and compares correctly there; report what you found.

  Add to `SOURCES` (keep the three existing entries unchanged) and extend `ORDER`:

```python
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
```
```python
ORDER = ("ofsi", "fincen", "ofac", "otsi", "fca", "nca", "eu_council", "eba", "amla")
```
  Update the module docstring's first lines from "The three automated sources" to "The automated sources" and add the
  measured 2026-10-31 counts beside the 2026-09-26 ones.

  In `schemas/advisory.py`: `SourceType` gains `OTSI = "otsi"`, `EU_COUNCIL = "eu_council"`, `EBA = "eba"`,
  `AMLA = "amla"`; `SCHEMA_VERSION = "1.5.0"` with a history line: `# 1.5.0 (2026-10-31, six more regulators):
  SourceType gains otsi, eu_council, eba, amla. Additive: every existing record validates unchanged.` Update
  `evals/check_added_by.py`'s pin to 1.5.0. `grep -rn '"1.4.0"' --include=*.py .` and update any other pin that means
  "the current version".

- [ ] **Step 5: Fill the pins; run; mutate.**

```bash
cd ~/fc-08-scan-mechanics && ~/fc-08-schedule/.venv/bin/python evals/check_feed_adapters.py | tail -2
for m in rss-date-optional rss-unsorted fca-host-open; do PYTHONPYCACHEPREFIX=/tmp/mut-$m ~/fc-08-schedule/.venv/bin/python evals/check_feed_adapters.py --mutate $m | grep -E "FAIL|HELD:"; done
for m in $(~/fc-08-schedule/.venv/bin/python -c "import sys; sys.path.insert(0,'evals'); import check_feed_adapters as c; print(' '.join(k for k in c.MUTATIONS if k not in ('rss-date-optional','rss-unsorted','fca-host-open','hand-list')))"); do PYTHONPYCACHEPREFIX=/tmp/mut-$m ~/fc-08-schedule/.venv/bin/python evals/check_feed_adapters.py --mutate $m | grep -c "HELD: the probe detects" | sed "s/^/$m /"; done
```
  Expected: HELD; each new mutation fails its clause; every old mutation still detected (count 1 each).

### Task 3: triage rules as data

**Files:** `feeds/triage_rules.json` (new), `agents/orchestrate_feeds.py`, `evals/check_feed_adapters.py`.

- [ ] **Step 1: Failing clause** in `evals/check_feed_adapters.py`:

```python
def rules_checks(mutation) -> list:
    """Spec §3: every live source has a triage rule entry (the empty string written explicitly means none)."""
    from feeds.sources import SOURCES
    rules = json.loads((ROOT / "feeds" / "triage_rules.json").read_text(encoding="utf-8"))
    if mutation == "rule-missing":
        rules.pop("fca", None)
    ok = set(rules) == set(SOURCES) and all(isinstance(v, str) for v in rules.values())
    return [(ok, "feeds/triage_rules.json has exactly one string rule per live source",
             sorted(set(SOURCES) ^ set(rules)))]
```
  Call it from `main()`; register `rule-missing` like `hand-list`. Ensure `import json`.

- [ ] **Step 2: Run; expect FAIL** (no file).

- [ ] **Step 3: Implement.** Create `feeds/triage_rules.json` (keys in `ORDER`, the OFAC text copied VERBATIM from
  `OFAC_DESIGNATION_RULE`, the six drafts from the spec §3 marked for the owner):

```json
{
  "ofsi": "",
  "fincen": "",
  "ofac": "<OFAC_DESIGNATION_RULE's text, verbatim>",
  "otsi": "DRAFT (owner to edit): An OTSI page is relevant when it describes how trade sanctions are evaded or breached. Licence notices and procedural updates are not relevant.",
  "fca": "DRAFT (owner to edit): An FCA page is relevant when it is a final notice, an enforcement action or a fine that describes a control failure or a laundering or fraud method. Consultations, speeches and corporate news are not relevant.",
  "nca": "DRAFT (owner to edit): An NCA page is relevant when it describes a laundering, fraud or sanctions-evasion method. An arrest or a sentence alone is not relevant.",
  "eu_council": "DRAFT (owner to edit): An EU Council press release is relevant when it is in the Sanctions category or describes how sanctions are evaded. Other policy news is not relevant.",
  "eba": "DRAFT (owner to edit): An EBA page is relevant when it is an AML/CFT guideline, risk opinion or peer review. Procedural, staffing and non-AML items are not relevant.",
  "amla": "DRAFT (owner to edit): An AMLA page is relevant when it is a risk assessment, guidance or a supervisory finding. Institutional and recruitment news is not relevant."
}
```
  In `agents/orchestrate_feeds.py`, replace the `OFAC_DESIGNATION_RULE` constant's use (keep its comment block, now
  above the loader):

```python
RULES_FILE = ROOT / "feeds" / "triage_rules.json"     # use the module's existing repo-root variable
SOURCE_RULES = "\n\n".join(r for r in (json.loads(RULES_FILE.read_text(encoding="utf-8"))[s] for s in ORDER) if r)
FULL_PROMPT = TRIAGE_PROMPT + "\n\n" + SOURCE_RULES + "\n\n" + EXTRACTION_SECTION
```
  (Import `ORDER` with `named`. Delete `OFAC_DESIGNATION_RULE` only if nothing else imports it:
  `grep -rn OFAC_DESIGNATION_RULE --include=*.py .`; if an eval names it, point that eval at the JSON's "ofac" entry.)

- [ ] **Step 4: Prove the mechanism is byte-identical with the drafts blanked**, then restore them:

```bash
cd ~/fc-08-scan-mechanics && cp feeds/triage_rules.json /tmp/rules.json && ~/fc-08-schedule/.venv/bin/python - <<'EOF'
import json; p="feeds/triage_rules.json"; r=json.load(open(p))
for k in ("otsi","fca","nca","eu_council","eba","amla"): r[k]=""
json.dump(r, open(p,"w"), indent=2)
EOF
PYTHONPYCACHEPREFIX=/tmp/rules-blank ~/fc-08-schedule/.venv/bin/python -c "import sys; sys.path.insert(0,'.'); import agents.orchestrate_feeds as o; print(o.FULL_PROMPT.count('An OFAC designation page'))"
cp /tmp/rules.json feeds/triage_rules.json
```
  Expected `1`: with only the OFAC rule non-empty, the rules block is exactly the old constant. (The TRIAGE_PROMPT
  itself now names nine sources, so the hashes move -- plan R3.)

- [ ] **Step 5: Run the guard and `rule-missing`.** Expected: HELD; `rule-missing` fails exactly the rules clause.

### Task 4: budget and the dry run

**Files:** `agents/orchestrate_feeds.py`, `evals/check_feeds_orchestrator.py`, `tools/count_new.py` (new).

- [ ] **Step 1: Find the limits.** `grep -n "RUN_CEILING_USD\s*=\|MAX_BUDGET_USD\s*=\|MAX_TURNS\s*=\|EXTRACTION_BUDGET_USD\s*=" agents/orchestrate_feeds.py`
  and the triage item cap: `grep -rn "10" feeds/triage.py mcp_server/feeds_server.py agents/orchestrate_feeds.py | grep -i "max\|cap\|limit"`.
  Report each constant's name, value and file:line before changing anything.
- [ ] **Step 2: Update the pins first** in `evals/check_feeds_orchestrator.py` (where it pins these values): ceiling
  10.00, triage cap 20, `MAX_BUDGET_USD` and `MAX_TURNS` doubled (plan R2), extraction unchanged. Run it; expect FAIL.
- [ ] **Step 3: Change the constants**; run; expect HELD. Mutation: if the guard has a `--mutate` facility, add
  `ceiling-5` (ceiling back to 5.00) and confirm it fails; if it has none, run the check once with the constant
  temporarily at 5.00 in a scratch copy (`PYTHONPYCACHEPREFIX` set) and report the FAIL line.
- [ ] **Step 4: The dry run.** Find how an item key is made (`grep -rn "hexdigest()\[:16\]" feeds mcp_server`). If it
  is inline in `feeds_server.py`, move it into a function in `feeds/model.py` (`item_key(item) -> str`) used by both,
  behaviour unchanged. Then create `tools/count_new.py`:

```python
"""
Listing-only dry run (spec §6): fetch every source's listing, parse it, and count the items not yet in
data/feeds/seen.json. No agent runs, nothing is spent, nothing is written.

    python tools/count_new.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from feeds import http as feeds_http  # noqa: E402
from feeds.model import item_key  # noqa: E402
from feeds.sources import MAX_LISTING_BYTES, ORDER, SOURCES  # noqa: E402


def main() -> int:
    seen = set(json.loads((ROOT / "data" / "feeds" / "seen.json").read_text(encoding="utf-8")))
    total = 0
    for name in ORDER:
        src = SOURCES[name]
        got = feeds_http.get(src.listing_url, allowed_hosts=src.hosts, allowed_types=src.listing_types,
                             max_bytes=MAX_LISTING_BYTES)
        items = src.parse(got.body)
        new = [i for i in items if item_key(i) not in seen]
        total += len(new)
        print("%-11s listed %3d  new %3d" % (name, len(items), len(new)))
    print("%-11s           new %3d" % ("all", total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
  Match `feeds_http.get`'s real signature and return shape (read `feeds/http.py:41`), and `seen.json`'s real shape
  (a list or a dict of keys); adjust these two lines only. Run it once; paste the table in the report. It must leave
  `git status` unchanged.

### Task 5: the scan page

**Files:** `tools/build_scan_demo.py`, `evals/check_scan_demo.py`.

- [ ] **Step 1:** `DISPLAY` gains `"otsi": "OTSI", "eu_council": "EU Council", "eba": "EBA", "amla": "AMLA"`.
- [ ] **Step 2:** Europol's reason. Add `NOT_YET_REASON = {"europol": "its articles render only with JavaScript"}`
  beside `DISPLAY`; the payload's `coverage.not_yet` entries become `{"name": DISPLAY.get(s, s), "why":
  NOT_YET_REASON.get(s, "")}` and the chip renders `name · not yet` with `title` and a visible `(why)` when `why` is
  set. Guard clause: the not-yet list equals the `SourceType` values minus live, manual and `NOT_A_FEED`, and
  Europol's chip carries its reason. Mutation `europol-silent`: `NOT_YET_REASON` emptied in `_page()`.
- [ ] **Step 3:** The triage-band line names its prompt (plan R3): where the page states the measured triage band,
  append "measured on the three-source triage prompt" whenever the live `PROMPT_SHA256` differs from the one the
  measurement recorded (read the recorded hash from the measurement's own file the page already parses; if it records
  none, state the measurement date and "before the 2026-10-31 sources were added"). Guard: the note appears exactly
  when the hashes differ.
- [ ] **Step 4:** Rebuild; `evals/check_scan_demo.py` HELD; run the new mutation; run the scan page JS in node with the
  stub from the three-paths plan (task 5 step 1) and confirm the coverage block renders nine live chips.

### Task 6: verify, publish, commit (owner's go)

- [ ] **Step 1:** `tools/check_all.py` -- every guard passes except the scan page's two publish staleness gates.
- [ ] **Step 2:** Render the scan page coverage panel at 375 px and desktop; screenshot.
- [ ] **Step 3: Owner gates, in order:** (a) the owner edits the six rule drafts in `feeds/triage_rules.json` (or
  approves them; "DRAFT (owner to edit): " is removed from each approved rule); (b) the owner reads the dry-run table;
  (c) the owner's go to publish.
- [ ] **Step 4:** Republish the scan page (`tools/publish_scan_demo.py`), commit the portfolio, verify the hash, then
  ONE fc-08 commit of tasks 2-5 plus `site/SCAN_PUBLISHED` and this plan; the hook must print `PASS ... 0 failed`.
- [ ] **Step 5:** Hand the owner the pushes (the branch with `-u origin sdd/six-regulators`, then the portfolio) and
  open a PR. It lands after `sdd/scan-page-three-paths`, before Thursday 2026-11-05; the schedule clone then
  fast-forwards (`git checkout main && git merge --ff-only origin/main`), so the 06 November run reads all nine.
