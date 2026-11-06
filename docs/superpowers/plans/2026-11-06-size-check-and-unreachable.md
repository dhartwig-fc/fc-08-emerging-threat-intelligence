# Size check before extraction, and unreachable items on a bot check

Owner decision 2026-11-06, after the 2026-11-06 Friday run (`feeds-2026-11-06-389ebb`, RECONCILIATION_FAILED):
"size check, and A for the EU Council". Branch `sdd/size-check-unreachable`, cut from origin/main 9dd86f3.

## Why

1. **The 264-page document.** `ofac:1037f2edb4912104` (OFAC Iran alert, 4 Nov) was pinned as 264 pages. The
   extractor receives the WHOLE document inlined in its first prompt (`agents/extract_advisory.py`: `extract` ->
   `build_prompt` over `document_pages`, no size cap, no page tool), so two turns cost US$1.55 against the US$1.00
   per-extraction cap (`agents/orchestrate_feeds.py` `EXTRACTION_BUDGET_USD`). The SDK stopped it mid tool call; the
   unterminated call failed reconciliation.
2. **The EU Council.** All 16 new `eu_council` items were unfinished with no verdict. The RSS listing loads, but every
   article page answers HTTP 403 from Cloudflare, `Server: cloudflare`, a `cf-ray` header and a page titled
   "Browser check - Consilium" (measured 2026-11-06, one request with fc-08's own client and user agent). fc-08 does not
   get past bot checks, so these items come back every Friday and fail again.

## Measured basis for the size limit

`len(build_prompt(...))` over every pinned document fc-08 has ever extracted (14 distinct documents, all inbox runs):

| | prompt characters |
| --- | --- |
| largest successful extraction (`ofac:528a733c96bd988a`, 11 pages, US$0.60) | 27,679 |
| the failed 2026-11-06 extraction (264 pages, US$1.55 in 2 turns) | 702,970 |

`MAX_EXTRACTION_PROMPT_CHARS = 100_000`: 3.6x the largest success, 7x below the failure. A named constant beside
`EXTRACTION_BUDGET_USD`, with this measurement in its comment. It is a guard against the pathological case, not a cost
guarantee: extraction cost is driven by turns as much as size.

## Task A: the size check

- `agents/orchestrate_feeds.py`: add `MAX_EXTRACTION_PROMPT_CHARS = 100_000` next to `EXTRACTION_BUDGET_USD`.
- `tools/friday_run.py`, the extraction loop in `_locked_friday` (~line 246): a new branch AFTER the "no document"
  branch and BEFORE `may_start`. Measure the prompt with the extractor's OWN functions
  (`extract_advisory.document_pages` + `extract_advisory.build_prompt`, one shared helper, never a reimplementation)
  on the request's pinned document. Over the limit -> outcome
  `{"key", "status": "deferred_size", "cost_usd": 0.0, "error": "the extraction prompt is N characters; the limit is M ..."}`.
  No advisory id is allocated and no session is started. A document that cannot be measured is `failed` with the reason.
- `feeds/extraction.py`: add `deferred_size` to the outcome vocabulary documented at the top.
- `feeds/reconcile.py`: `deferred_size` is its own list in the reconciliation (`too_long`), not `deferred` (that one means
  the run ceiling) and not `failed`. It never makes reconciliation fail.
- `feeds/report.py`: the Extraction heading counts it ("N too long for one extraction"); its Unfinished line says why and
  that it returns next Friday.
- `tools/accept_run.py`: `default_decision` already defers any status it does not name; confirm `deferred_size` cannot be
  accepted (only `extracted` can) and defaults to defer.
- Guards (`evals/`, house pattern, mutation anchors per `evals/check_mutation_anchors.py`): over the limit -> deferred_size,
  no allocation, the extractor NOT called, cost 0; just under -> extracted as before; the report and reconciliation
  carry it. Each new clause mutation-verified (break it, see red, restore, see green).

Out of scope: `tools/intake_document.py` (the manual FATF path) is NOT gated in this branch. FATF reports run long and a
100,000-character limit would refuse most of them; that is an owner question, recorded in the PR.

## Task B: unreachable on a bot check (option A)

- `feeds/http.py`: `class BotCheck(FetchRefused)`. In `get`, catch `urllib.error.HTTPError` BEFORE `URLError`, read at
  most 4,096 bytes of its body, and raise `BotCheck` only when `_is_bot_check(code, headers, body)` holds:
  code in (403, 429, 503) AND (header `cf-mitigated: challenge`, OR `Server` contains "cloudflare" AND the body's
  `<title>` matches `Browser check|Just a moment|Attention Required`). Any other HTTPError stays a plain `FetchRefused`,
  now naming its status code. **Detection only: never retry, never change the user agent or headers** (the
  `check_no_disguised_automation` rule stands).
- `mcp_server/feeds_server.py` `_fetch`: catch `BotCheck` before `FetchRefused`; set
  `item["unreachable"] = {"reason": "bot_check", "detail": str(exc)}` and `item["fetch_error"]`; save; return
  `"Unreachable: <key>: the site answered a bot check ..."` telling the orchestrator not to triage it.
- `feeds/reconcile.py`: `unreachable` = listed keys whose item carries `unreachable`; `unfinished` excludes them.
  Reconciliation never fails on them.
- `feeds/report.py`: an "Unreachable (the site answered a bot check): N -- dropped at acceptance" section listing key
  and title; the summary line counts them; they leave the Unfinished section.
- `tools/accept_run.py`: `default_decision` gains `unreachable: bool = False`; status None + unreachable -> `drop`.
  `default_decisions` passes it from the run's items. A `--decisions` file may still say anything `plan()` allows.
- Guards: `_is_bot_check` on the measured Consilium response (403, `Server: cloudflare`, title "Browser check -
  Consilium") -> True; a plain 403 from a non-Cloudflare server -> False; a 404 -> False. `_fetch` marks only a BotCheck
  unreachable. Reconcile/report move the item out of Unfinished. `default_decision` drops unreachable and still defers a
  plain fetch failure. Each clause mutation-verified.

## Working rules

Commit from this FULL clone (`~/fc-08-scan-mechanics`), never a linked worktree; stage explicitly, never `-a`; run with
`env -u ANTHROPIC_API_KEY` and `PATH=~/fc-08-schedule/.venv/bin:$PATH`; never `--no-verify`. No Co-Authored-By trailer.
The pre-commit hook runs the guard suite; it must report 0 failed. Nothing is pushed without the owner.
