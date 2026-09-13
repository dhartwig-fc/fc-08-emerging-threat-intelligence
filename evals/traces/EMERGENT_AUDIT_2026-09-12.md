# Emergent audit: is 0.208 a defect or an artefact?

Analysis only. No model was run; everything below is derived by importing
`evals/score.py` unmodified and re-deriving its own pairing logic against the
committed `evals/golden/ADV-*.json` (20 labels) and `data/records/ADV-*.json`
(20 predicted records). `evals/score.py --json` was run once, cold, to confirm
the published baseline reproduces exactly (15 TP / 19 FP / 95 FN on emergent,
precision 0.441, recall 0.136, F1 0.208) before anything else was touched.
Everything after that point re-uses `score.emergent_labels`, `score.tokens`,
`score.containment`, `score.emergent_score` and `score.match_by_score`
directly, so every number here was produced by the shipped matcher, not a
reimplementation of it.

`score.py` itself is unmodified. No branch, commit or push was made.

## Method note on the two sides

The 19 false positives and 95 false negatives are not independent lists. Ten
of the twenty advisories predicted **zero** emergent labels at all (see
below), and several of the FP/FN pairs below are the FP and FN halves of the
exact same near-miss (agent wrote X, golden wrote Y, `emergent_score(X,Y)` is
just under 0.60). Where that happens it is cross-referenced rather than
re-argued.

---

## 1. Threshold sweep

Re-scored emergent only, golden and predicted held fixed, only
`DEFAULT_EMERGENT_THRESHOLD` varied. `evals/score.py` was not edited — the
sweep script imports `score.match_by_score` and calls it with each threshold.

| threshold | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|
| 0.40 | 24 | 10 | 86 | 0.706 | 0.218 | 0.333 |
| 0.50 | 22 | 12 | 88 | 0.647 | 0.200 | 0.306 |
| **0.60 (shipped)** | 15 | 19 | 95 | 0.441 | 0.136 | 0.208 |
| 0.70 | 13 | 21 | 97 | 0.382 | 0.118 | 0.181 |

F1 does rise as the threshold falls — 0.208 to 0.333, +60% relative, moving
from 0.60 to 0.40 — but recall barely moves (0.136 to 0.218) because the
overwhelming majority of false negatives are not near-misses sitting just
below the boundary (see Part 3). The threshold sweep recovers precision much
more than recall.

### What lowering the threshold from 0.60 costs, pair by pair

**0.60 -> 0.50 gains 7 true positives, all of them content-verified, real
paraphrases of the same underlying fact.** No entity merge, no cross-technique
merge, observed in this data at 0.50:

| gold | predicted | score |
|---|---|---|
| Account settlement mechanism netting cash against bank balances between criminal clients | Account Settlement Mechanism (Cross-Border Netting via OCG Accounts) | 0.500 |
| Cyber-enabled fraud predicates: BEC, phishing, impersonation, online trading platform, romance and employment scams | Cyber-Enabled Fraud (CEF) Money Laundering | 0.500 |
| Black market peso exchange and three-way exchange exploiting capital controls | Black Market Peso Exchange (BMPE) Trade-Based Settlement | 0.500 |
| Terrorist financing through hawala networks | Underground Banking / HOSSP Nexus with Terrorist Financing | 0.500 |
| Export of purchased luxury goods as value exchange in place of a mirror transfer | CMLN Goods-Based Trade Value Transfer (Purchase and Export) | 0.500 |
| Intermediation through an offshore broker's omnibus account with settlement in another jurisdiction and currency | Omnibus/Reliance Intermediation Opacity | 0.500 |
| Cryptocurrency laundering through mixers, chain hopping, privacy coins and DeFi | Cryptocurrency Layering via Mixing Services, Chain-Hopping and DeFi | 0.571 |

Each pair was read against its citations (Part 2 below has the full text for
the FP side). All seven cite the same underlying fact on both sides. This is
the strongest evidence that 0.50 is not, in this real data, the entity-merge
trap the docstring warns about — that trap is empirically real (see next) but
did not fire on these seven.

**0.50 -> 0.40 gains 2 more, and one of them IS the trap, found empirically
rather than synthetically.** The docstring's own worked example ("2Rivers
DMCC" / "2Rivers PTE") is from **actor** scoring, not emergent — it does not
recur verbatim in the emergent data. But the same *class* of defect —
distinct concepts sharing enough generic vocabulary to clear a low bar — does
occur here, in a real advisory:

| gold | predicted | score | verdict |
|---|---|---|---|
| Trusts and legal arrangements interposed to separate legal from beneficial ownership | Professional Intermediary (TCSP/Legal/Accounting) Gatekeeper Complicity in Beneficial Ownership Concealment | 0.429 | **false merge.** ADV-2026-0004's golden label separately and distinctly carries "Professional intermediary facilitation by lawyers, accountants and TCSPs" — the label this predicted string is actually about. The wrong golden entry wins because "legal", "beneficial" and "ownership" are shared tokens between the PREDICTED label and the WRONG gold entry, while the CORRECT gold entry only scores 0.333 against it (see below — a tokenizer defect, not a content defect: "TCSPs" vs "TCSP" doesn't collapse). Lowering to 0.40 would count this as a correct match while leaving the actually-correct pairing an FN and consuming a different golden item that means something else. |
| Account funding abuse: over-collateralisation and cash parked without trading then withdrawn to a third party | Capital Markets Account Funding Layering | 0.400 | genuine, same mechanism, safe. |

So the answer to "what does 0.50 cost" in this real data is **nothing
measured** — seven clean recoveries, zero merges. The answer to "what does
0.40 cost beyond that" is **one wrong pairing that reads as a correct match**,
which is exactly the failure class the 0.60 choice exists to prevent, just
not the literal case in the docstring. **0.60 -> 0.40 is not free; 0.60 ->
0.50 empirically was, in this run.**

**0.60 -> 0.70 is strictly worse and buys nothing.** It loses two already-good
matches:

| gold | predicted | score |
|---|---|---|
| Mirror-transaction currency swap through Chinese underground banking (BMPE-style, no cross-border movement) | Chinese Underground Banking Mirror Transactions (IVTS) | 0.667 |
| Free-of-payment movement of securities of unverified ownership between brokers before sale | Free of Payment Securities Transfer Laundering | 0.600 |

Both are unambiguous same-technique paraphrases (compare the strings). Raising
the bar removes real recall and real precision (FP rises too, since the
now-unmatched predicted label becomes spurious) for no benefit. There is no
case for 0.70.

---

## 2. All 19 false positives, classified

Classification key (per the brief):

- **A** — paraphrase of a golden emergent label that fell below 0.60: the
  scorer's threshold is the defect, not the agent.
- **B** — duplicate of a GOVERNED typology the record already carries as a
  `typology_id`.
- **C** — genuinely not in the document, OR not a distinct extractable
  technique even though the citation is accurate (a theme restatement, or a
  fact that belongs in the `actors` field, not `typologies`).
- **D** — a real technique the golden label missed.

Two items force a **B** and a **C-variant** not explicitly in the brief's four
buckets but each is folded into the nearest bucket and flagged explicitly, per
instruction to force exactly one letter per item.

| # | Advisory | Predicted label | Class | Score vs nearest gold |
|---|---|---|---|---|
| 1 | 0003 | Professional Money Laundering (Third-Party PML Organisations/Networks) | C | 0.14 |
| 2 | 0003 | Virtual Currency / Digital Money Laundering Networks | A | 0.33 |
| 3 | 0003 | Account Settlement Mechanism (Cross-Border Netting via OCG Accounts) | A | 0.50 |
| 4 | 0003 | Complicit Financial Service Providers and Professional Gatekeepers | C | 0.33 |
| 5 | 0004 | Professional Intermediary (TCSP/Legal/Accounting) Gatekeeper Complicity in Beneficial Ownership Concealment | B | 0.43 |
| 6 | 0006 | Money Laundering from Environmental Crime | C | 0.00 |
| 7 | 0007 | Cyber-Enabled Fraud (CEF) Money Laundering | A | 0.50 |
| 8 | 0007 | DPRK Proliferation Financing via Cyber-Enabled Fraud Tools | D | 0.43 |
| 9 | 0008 | Underground Banking and HOSSP-Based Professional Money Laundering | C | 0.29 |
| 10 | 0008 | Underground Banking / HOSSP Nexus with Terrorist Financing | A | 0.50 |
| 11 | 0008 | Black Market Peso Exchange (BMPE) Trade-Based Settlement | A | 0.50 |
| 12 | 0008 | High-Capacity Transnational PML Networks / International Controller Networks (ICN) | C | 0.25 |
| 13 | 0011 | CMLN Goods-Based Trade Value Transfer (Purchase and Export) | A | 0.50 |
| 14 | 0018 | Medium-Term Note / Debt Issuance Layering | A | 0.33 |
| 15 | 0018 | Omnibus/Reliance Intermediation Opacity | A | 0.50 |
| 16 | 0018 | Capital Markets Account Funding Layering | A | 0.40 |
| 17 | 0019 | Cryptocurrency Layering via Mixing Services, Chain-Hopping and DeFi | A | 0.57 |
| 18 | 0019 | Corruption Brokers and Digitalised Corruption-as-a-Service | D | 0.25 |
| 19 | 0019 | Hybrid Threat Actor Use of Criminal Networks as Proxies (Woodpecker Modus Operandi) | C | 0.17 |

**Tally: A = 10, B = 1, C = 6, D = 2** (19 total).

### A — paraphrase, threshold is the defect (10)

Items 3, 7, 10, 11, 13, 15, 16, 17 all clear 0.50 and are listed with their
gold counterpart in Part 1's table above — content-verified there, not
repeated.

Two of the ten do **not** recover even at 0.40, and matter for the "just lower
the threshold" argument:

- **#2**, ADV-2026-0003. Predicted: *"Virtual Currency / Digital Money
  Laundering Networks"*, cited to *"virtual currency is transferred through a
  complex chain of e-wallets, which may include the use of mixers and
  tumblers to further enhance the anonymity."* Golden: *"Virtual currency
  cash-out through straw-man e-wallets, mixers and complicit exchangers"* —
  **the same citation, the same fact.** Score 0.333. The agent's label is so
  much more abstract ("digital money laundering networks") than the golden's
  specific mechanism description that almost no content tokens survive
  containment. No threshold in the tested range (0.40-0.70) recovers this.
  This is real evidence the scorer's problem is not only the threshold value
  — abstraction level breaks token containment independent of where the bar
  sits.
- **#14**, ADV-2026-0018. Predicted: *"Medium-Term Note / Debt Issuance
  Layering"*. Golden: *"Debt issuance: loan repackaged as an MTN with coupons
  routed through an offshore agent to connected holders"*. Score 0.333. Same
  mechanism (MTN = Medium Term Note), same document, same case. Not
  recoverable at 0.40 either.

### B — duplicate of a governed typology already asserted (1)

- **#5**, ADV-2026-0004. Predicted governed set for this record is `FND003,
  PAT003, PAT007, PAT010, PAT004`. FND003 is "Beneficial Ownership
  Intelligence." The predicted emergent label *"Professional Intermediary
  (TCSP/Legal/Accounting) Gatekeeper Complicity in Beneficial Ownership
  Concealment"* scores 0.667 containment against FND003's own label — the
  emergent entry restates, in prose, the same subject the record already
  claims a governed id for. **This is compounded, not simple B**: FND003 is a
  foundation capability, not a describable typology (the golden README states
  this explicitly for all five FND ids — "their absence is correct"), so the
  governed assertion the emergent label duplicates is *itself* wrong. This is
  a genuine agent-quality defect on two axes at once — a foundation-pipe id
  asserted as if it were a document-typology, then re-described as prose in a
  second field — not a scorer artefact.

### C — not a distinct technique, or wrong field (6)

Two structurally identical sub-patterns account for four of these six.

**Sub-pattern: the label names an actor class, not a technique**, and in two
cases the agent's OWN record already extracted that actor separately —
literal self-duplication across fields within one predicted record:

- **#12**, ADV-2026-0008. Predicted emergent: *"High-Capacity Transnational
  PML Networks / International Controller Networks (ICN)"*, cited to
  *"controllers... trusted individuals who arrange the collection of criminal
  proceeds"*. The SAME record's `actors` list already contains **"Controllers
  / International Controller Networks (ICN)"** with alias `ICNs`. The
  emergent entry adds nothing the record does not already assert elsewhere.
- **#1**, ADV-2026-0003. Predicted emergent: *"Professional Money Laundering
  (Third-Party PML Organisations/Networks)"*. The SAME record's `actors` list
  already contains **"Professional money launderers"** with aliases `PMLs,
  PMLOs, PMLNs`. Same self-duplication.
- **#4**, ADV-2026-0003. Predicted emergent: *"Complicit Financial Service
  Providers and Professional Gatekeepers"*, cited to *"PMLs may occupy
  positions within the financial services industry... and DNFBP sectors"* and
  the PacNet case. This one is **not** a self-duplicate — the agent's own
  actors list has no such entry — but it is a near-verbatim match to the
  **golden set's actor** "Complicit financial service providers and
  professional gatekeepers." The underlying fact is real and the agent found
  it; it filed it as a typology instead of an actor, and never filed it as an
  actor at all (a separate, uncounted miss on the actors field). Genuinely
  ambiguous whether this is "the document's content" (yes) or "an emergent
  typology" (no) — filed under C because it is not a distinct technique
  regardless of which field it belongs in.

**Sub-pattern: the label restates the document's whole subject rather than
naming a technique within it:**

- **#6**, ADV-2026-0006 (a FATF report on environmental-crime laundering).
  The agent's *only* emergent entry is *"Money Laundering from Environmental
  Crime"* — cited to *"This FATF report shows the significant role of
  trade-based fraud and misuse of shell and front companies to launder gains
  from illegal logging, illegal mining, and waste trafficking."* That
  sentence supports the label as a description of the *document*, not as a
  specific mechanism. Golden's four emergent entries for this advisory are
  all specific techniques (co-mingling of legal/illegal goods, hawala,
  bulk-cash/gold couriers, PEP-linked concession licensing) — none of which
  the agent's single generic label overlaps with (all score 0.00 against it).
- **#9**, ADV-2026-0008. *"Underground Banking and HOSSP-Based Professional
  Money Laundering"* — cited to the report's own opening definitional
  sentences about what underground banking is. Same pattern: restates the
  report's title-level subject rather than any one of its ten specific
  settlement mechanisms.

**Sub-pattern: a real sentence, reified as a typology it isn't:**

- **#19**, ADV-2026-0019. *"Hybrid Threat Actor Use of Criminal Networks as
  Proxies (Woodpecker Modus Operandi)"*, cited to *"hybrid threats...
  encompass a broad range of criminal activities and tactics operated via
  criminal proxies"* and the report's own woodpecker metaphor for sustained
  low-level erosion of institutional trust. This is a strategic/geopolitical
  framing statement about a threat actor's posture, not a laundering
  mechanism with indicators — there is no fact pattern here an investigator
  could act on the way they could on, say, "MTIC VAT fraud." Citation
  accurate; label over-reified.

### D — real technique the golden label missed (2)

- **#8**, ADV-2026-0007. *"DPRK Proliferation Financing via Cyber-Enabled
  Fraud Tools"*, cited to *"cybercrime reported as a major source of illicit
  income generation for the Democratic People's Republic of Korea (DPRK)"*
  and *"information technology (IT) workers of the... DPRK linked to the
  Munitions Industry Department have been earning foreign currency by selling
  voice phishing hacking applications."* Golden's emergent list for this
  advisory has ten entries, all about the cyber-fraud/mule/laundering
  mechanics — nothing about the DPRK/proliferation-financing angle the
  document separately and explicitly develops over two cited pages. This is
  a real, specific, well-cited finding the review missed, not an
  over-generation.
- **#18**, ADV-2026-0019. *"Corruption Brokers and Digitalised
  Corruption-as-a-Service"*, cited to *"the elevated role of corruption
  brokers"* and *"Bribes are transferred by criminally exploiting
  cryptocurrencies or fintech."* Golden has no corruption/bribery-specific
  entry for this advisory at all. Flagged D rather than C because the golden
  README's own labelling rule ("a single bullet is sufficient evidence" in an
  indicator-shaped document) would admit this if a labeller had seen it — but
  the two citations are short (six and ten words of actual content), so this
  is the weaker of the two D calls: real, but thinly evidenced.

---

## 3. False-negative triage

**The single largest fact in this whole audit: 10 of the 20 predicted records
contain zero emergent labels.** Not low-scoring ones — zero entries in the
`typologies` list with no `typology_id`, for the entire document:

```
ADV-2026-0002, 0005, 0010, 0012, 0013, 0014, 0015, 0016, 0017, 0020
```

Those ten advisories carry **39 of the 110 golden emergent labels (35%)**.
Every one of those 39 is a false negative by construction — there is no
threshold, however low, that recovers a match against a record with nothing
in it. This is not a scoring artefact in any sense; it is the agent declining
to propose *anything* emergent for half the set, while still asserting
governed typologies for the same documents (`ADV-2026-0002` alone asserts 8
governed ids and 0 emergent). Two of these ten (`ADV-2026-0012`, shadow-fleet
vessel-identity indicators; `ADV-2026-0005`, an 11-entry crypto-typology red
alert) are exactly the indicator-list document shape the golden README says
is richest in single-bullet-supported typologies — precisely where the agent
produces the least.

### Sample: all 56 false negatives from the ten advisories that DID predict
something emergent

This exceeds the 25-item floor and was chosen this way deliberately: the ten
zero-prediction advisories contribute nothing to distinguish "paraphrase
below threshold" from "never proposed" — every one of their 39 FNs is
trivially the latter. All of the triage-worthy nuance lives in the other ten
advisories, so all 56 of their false negatives were classified, in full, not
sampled.

Buckets, per the brief:

- **paraphrase below threshold** — a real predicted counterpart exists and
  the fact matches; already covered as the FP-side of an A pair in Part 2, or
  newly identified here.
- **never proposed at all** — no predicted label addresses this content; the
  nearest predicted string overlaps only by coincidental generic vocabulary
  (containment score driven by stopword-adjacent tokens, not shared facts).
- **matched to a different golden label by the greedy pairing** — a real
  predicted counterpart exists, the fact plausibly matches, but a *different*
  golden label with a higher score against the same predicted string won the
  one-to-one slot.

| Advisory | FN | class | note |
|---|---|---|---|
| 0001 | Offsetting or compensation schemes between criminal groups | never proposed | score 0.00 |
| 0001 | Exploitation of MVTS and hawala for trade settlement | never proposed | score 0.25, incidental |
| 0003 | Account settlement mechanism netting cash... | **paraphrase (A)** | = FP #3, score 0.50 |
| 0003 | Fictitious contracts and false documentation to justify transfers | never proposed | score 0.00 |
| 0003 | Virtual currency cash-out through straw-man e-wallets, mixers and complicit exchangers | **paraphrase (A)** | = FP #2, score 0.33, same citation |
| 0003 | Black Market Peso Exchange and money brokering of drug proceeds | never proposed | score 0.20, agent produced no BMPE label for this advisory at all |
| 0003 | Complicit insider and institutional compromise of financial businesses | never proposed (weak) | score 0.33; nearest predicted item is the actor-shaped FP #4, adjacent theme, not this fact |
| 0003 | Mirror trading through securities markets to move value abroad | never proposed | score 0.00 |
| 0004 | Formal and informal nominee directors and shareholders | never proposed | score 0.00 |
| 0004 | Professional intermediary facilitation by lawyers, accountants and TCSPs | never proposed (tokenizer-blocked) | score 0.333 — this IS what the agent's one label is actually about; blocked by "TCSP" vs "TCSPs" not stemming (see Part 1) |
| 0004 | False loans (loan-back) disguising the return of own funds | never proposed | score 0.00 |
| 0004 | Trusts and legal arrangements interposed to separate legal from beneficial ownership | never proposed (coincidental) | score 0.429 from shared generic tokens only — this is the false-merge risk at 0.40 from Part 1, not a real paraphrase |
| 0004 | Bearer shares and bearer share warrants | never proposed | score 0.00 |
| 0004 | Shelf companies sold with pre-established bank accounts and nominee directors | never proposed | score 0.00 |
| 0004 | Professional trust, client and escrow accounts used to place and pass through funds | never proposed | score 0.12 |
| 0004 | Real estate acquired through nominees, companies or trusts | never proposed | score 0.00 |
| 0006 | Co-mingling of illegal and legal goods early in the resource supply chain | never proposed | score 0.00, only predicted item is the theme label FP #6 |
| 0006 | Informal value transfer via hawala and underground exchange dealers | never proposed | score 0.00 |
| 0006 | Bulk cash and hand-carried gold moved by couriers | never proposed | score 0.00 |
| 0006 | PEP-linked corporate structures and corrupt concession licensing | never proposed | score 0.00 |
| 0007 | Fictitious and overpriced invoicing for IT and consultancy services | never proposed | score 0.00 |
| 0007 | Cyber-enabled fraud predicates: BEC, phishing... | **paraphrase (A)** | = FP #7, score 0.50 |
| 0007 | Mule herding: online recruitment and remote control of mule account networks | never proposed | score 0.00 |
| 0007 | Virtual-asset laundering of fraud proceeds via unhosted wallets, peel chains, mixers, Bitcoin ATMs | never proposed | score 0.33, incidental ("money laundering" tokens only) |
| 0007 | Laundering through social media, streaming and gaming platform credits and gifts | never proposed | score 0.17 |
| 0007 | Stolen, synthetic and relinquished digital identities | never proposed | score 0.00 |
| 0007 | Small-value test transactions before moving the bulk of proceeds | never proposed | score 0.00 |
| 0007 | Cash-out by ATM withdrawal and cross-border cash couriers after layering | never proposed | score 0.00 |
| 0008 | Hawala net settlement by compensation between counterpart operators | **stolen by greedy pairing** | score 0.571 vs "Digital Hawala / Virtual-Asset..."; that predicted label is correctly taken instead by "Virtual-asset and stablecoin settlement..." at 0.875. No threshold recovers this — it is a 1:many cardinality problem, not a boundary problem: one broad predicted label, five related golden sub-mechanisms |
| 0008 | Triangular or multi-node settlement through third jurisdictions | never proposed | score 0.17 |
| 0008 | Cash-courier and bulk-cash settlement between service providers | never proposed | score 0.29 |
| 0008 | Commodity and gold-backed settlement, including luxury-goods repurchase | never proposed | score 0.12 |
| 0008 | Cuckoo smurfing through unwitting legitimate remitters | never proposed | score 0.00 |
| 0008 | Black market peso exchange and three-way exchange exploiting capital controls | **paraphrase (A)** | = FP #11, score 0.50 |
| 0008 | Digital hawala: encrypted-messaging co-ordination, hawala apps and AI-driven routing | never proposed | score 0.25 |
| 0008 | Mobile-money integration with hawala for cash-in and cash-out | never proposed | score 0.17 |
| 0008 | Terrorist financing through hawala networks | **paraphrase (A)** | = FP #10, score 0.50 |
| 0009 | Fictitious invoices for services never provided, disguising bribe payments | never proposed | score 0.00 |
| 0009 | Professional service providers and complicit intermediaries enabling laundering | never proposed | score 0.22 |
| 0011 | Export of purchased luxury goods as value exchange | **paraphrase (A)** | = FP #13, score 0.50 |
| 0011 | Surrogate shopping (daigou) straw buyers | never proposed | score 0.12 |
| 0011 | Convertible virtual currency as an alternative settlement rail | never proposed | score 0.33 |
| 0011 | Counterfeit passports and fake identity documents supplied to mules | never proposed | score 0.00 |
| 0018 | Mirror trading: associates transfer value through offsetting trades | never proposed | score 0.20; nearest predicted label is already correctly bound elsewhere |
| 0018 | Equity placement: convertible debt converted into shares | never proposed | score 0.17 |
| 0018 | Debt issuance: loan repackaged as an MTN... | **paraphrase (A)** | = FP #14, score 0.33, not recoverable at any tested threshold |
| 0018 | Intermediation through an offshore broker's omnibus account | **paraphrase (A)** | = FP #15, score 0.50 |
| 0018 | Neutralising FX option positions through a prime brokerage account | never proposed | score 0.20 |
| 0018 | Account funding abuse: over-collateralisation and cash parked | **paraphrase (A)** | = FP #16, score 0.40, recovers at 0.40 |
| 0019 | Criminal infiltration and abuse of legal business structures | never proposed | score 0.17, nearest predicted item is the reified-metaphor FP #19 |
| 0019 | Cryptocurrency laundering through mixers, chain hopping, privacy coins and DeFi | **paraphrase (A)** | = FP #17, score 0.57 |
| 0019 | Professional money laundering as a service through parallel underground financial systems | never proposed | score 0.25, nearest predicted item is the separately-real FP #18 (D) |
| 0019 | Missing trader intra-community (MTIC) VAT fraud | never proposed | score 0.00 |
| 0019 | Free trade zone abuse for illicit trade and financial crime | never proposed | score 0.00 |
| 0019 | Informal value transfer systems (hawala) | never proposed | score 0.00 |
| 0019 | Shared professional launderers linking organised-crime proceeds to terrorist financing | never proposed | score 0.00 |

### Counts

| class | count (of 56 sampled) | count (extrapolated to all 95, adding the 39 trivial zero-prediction FNs) |
|---|---|---|
| paraphrase below threshold | 11 | 11 (11.6%) |
| matched to a different golden label by greedy pairing | 1 | 1 (1.1%) |
| never proposed at all | 44 | 83 (87.4%) |

**Recall's problem is overwhelmingly that the agent does not write the item,
not that the scorer fails to credit it when it does.** Even restricting to
just the 56 non-trivial cases (excluding the ten zero-prediction advisories
entirely, the fairest comparison to the threshold sweep), "never proposed" is
78.6% of the sample. Lowering the threshold cannot touch this bucket by
definition — there is no predicted string to match against.

---

## 4. Verdict

**0.208 is mostly real, with a precision-side artefact worth roughly 60%
relative F1 and a recall-side artefact worth roughly nothing.**

The two sides of the score behave completely differently and must be read
separately — collapsing them into one F1 number is exactly how the earlier
six-advisory partial (F1 0.571, precision 1.000) went so wrong so fast at
full scale.

### Precision (0.441): substantially an artefact, and the threshold is fixable

Of 19 false positives:

- **10 (53%)** are genuine paraphrases the 0.60 threshold is too strict to
  credit (class A). Seven of these ten recover cleanly at 0.50 with **zero**
  observed entity- or technique-merges in this real data. Two more never
  recover at any threshold tested, because the defect is abstraction level,
  not proximity to a boundary — no threshold change fixes those two.
- **2 (11%)** are the agent being right and the golden label being incomplete
  (class D) — genuine extraction wins that the current scorer counts as
  errors.
- **7 (37%)** are real agent defects independent of the scorer: one governed-
  id duplication compounded with an inapplicable foundation-capability
  assertion (class B), and six cases of writing a document-theme restatement
  or an actor description into the `typologies` field instead of a specific
  technique (class C, two of which are literal self-duplicates against the
  same record's own `actors` list).

So of the 0.441 precision figure, moving the threshold to 0.50 would lift it
to 0.647 (+47% relative) on data that has already been read and verified
clean of merges. That is a real, checked, non-hand-wavy number, not a hope.

### Recall (0.136): overwhelmingly real, and no threshold fixes it

Of the 95 false negatives, 87% are cases where the agent proposed **nothing**
that addresses the golden fact — not a low-scoring near-miss, a genuine
absence. The single dominant cause is that **10 of 20 predicted records carry
zero emergent labels at all**, accounting for 39 of the 95 on their own,
before any threshold question even applies. Within the other ten records, the
agent tends to write one or a handful of broad, catch-all emergent labels
where the golden set has decomposed the same territory into many specific
sub-mechanisms (ADV-2026-0004: 1 predicted label against 8 golden; ADV-
2026-0008: 5 against 10; ADV-2026-0006: 1 against 4). This produces false
negatives that no threshold change touches, and a smaller number (1 confirmed
here, likely more at scale) that are capped by the greedy matcher's
one-to-one cardinality rather than by the score itself — the correct
predicted counterpart exists but is already spoken for by a better-scoring
different golden item.

This matches, exactly, the shape of the recall constraint `FULL_BASELINE_
2026-09-12.md` already found on the *typologies* field: **a near-fixed
assertion budget that does not scale with document content.** The emergent
field shows the same behaviour, more extreme — for half the set, the budget
is zero.

### What this means for the threshold decision

**Move `DEFAULT_EMERGENT_THRESHOLD` to 0.50, not lower, and say plainly what
it buys and what it does not.**

- It buys: precision 0.441 -> 0.647, recall 0.136 -> 0.200, F1 0.208 -> 0.306
  (+47%), against verified real paraphrases with zero observed merges in this
  dataset.
- It does not buy: any material recall recovery, because recall's problem is
  almost entirely absence, not proximity. Do not present a 0.50 rerun as
  "fixed the emergent field" — present it as "removed the part of the number
  that was measuring the scorer instead of the agent."
- It should **not** go to 0.40. The one real merge found in this real data
  (Part 1) occurs exactly there, and it is the same *class* of failure the
  0.60 choice was set to prevent, just a different pair than the docstring's
  example. 0.50 is the floor with verified evidence behind it; 0.40 is not.

### What this means for week 4

Do not spend week 4 effort on the scorer. Even a perfectly-tuned threshold
tops out around F1 0.31 on this data, because the binding constraint is on
the agent's side: it declines to write emergent labels for half the set, and
where it does write them, it writes fewer and broader ones than the golden
set's granularity. That is the same "assertion budget" finding
`FULL_BASELINE_2026-09-12.md` already made for governed typologies,
now shown to be worse, not better, on the emergent field specifically. The
question worth answering next is why the agent treats emergent labelling as
optional for half the documents — the two-review-cycle prompt discipline
that produced 4.5 asserted typologies against 5-20 golden ones may be
suppressing "flag something with no governed id" even harder than it
suppresses "flag a governed id."

### Where normalisation would still help, separately from the threshold

Two specific, non-threshold defects surfaced during this audit and are worth
fixing whether or not the threshold moves:

1. **No stemming/pluralisation.** "TCSP" vs "TCSPs" is the entire reason a
   correct paraphrase (FN 0004, "Professional intermediary facilitation by
   lawyers, accountants and TCSPs") scores lower (0.333) than the WRONG
   pairing that generic-token overlap produces (0.429, "Trusts and legal
   arrangements..."). A lemmatiser or a simple plural-strip on the token set
   would fix this specific case without touching the threshold at all, and
   would do so without reopening the corporate-suffix question the docstring
   already settled (BA-family entity suffixes should stay unstemmed; this is
   about grammatical plurals of common nouns, a different axis).
2. **No distinction between "typology" and "actor" in what the agent is
   willing to write to the `typologies` list.** Three of the six class-C false
   positives (two of them literal self-duplicates against the same record's
   own `actors` field) are the agent describing a network/actor class as if
   it were a technique. This is a governance question for `agents/
   extract_advisory.py`'s prompt or schema guidance, not a scoring question —
   raising or lowering the threshold cannot distinguish an actor description
   from a technique description; only the extractor can.

Neither of these requires touching `evals/score.py` to observe; both are
documented here as proposed follow-ups, per the hard rule against editing the
scorer mid-measurement.
