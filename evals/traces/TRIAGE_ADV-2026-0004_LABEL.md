# Triage: ADV-2026-0004 label (FATF/Egmont, Concealment of Beneficial Ownership, 2018, 190pp)

STATUS: COMPLETE — all 20 governed typologies assessed, 2026-09-13.

This is triage, not a verdict. The labels being assessed here were drafted by
Claude and reviewed by Claude (see `evals/golden/README.md`, "State of the
set"); this assessment is Claude assessing Claude's own work, which is the
same known limitation, not an escape from it. Nothing here should be read as
an independent adjudication — it is a prioritised, evidence-quoted shortlist
for the owner to adjudicate. Classifications and judgement calls below are
this session's reading of the mechanism test, not a ruling.

Purpose: test the alternative explanation for the 0.357 full-set typology
recall (`evals/traces/FULL_BASELINE_2026-09-12.md`) — that ADV-2026-0004's 20
claimed governed typologies (the highest count in the set, agent recall 0.15,
second worst) may include label inflation rather than pure agent suppression.

Method: mechanism test per typology — "a quote that exists is not a quote
that supports." For each typology: doctrine summary from `data/typologies.json`,
every citation (page/folio/quote/length), the `check_citations.py` location
verdict, and a SUPPORTED/THIN/UNSUPPORTED/BOILERPLATE judgement with reasoning,
plus structural flags (short quotes, mid-sentence cuts, shared citations).

`evals/check_citations.py` result for the whole record (run first, before any
per-typology judgement): **64 citations checked, 62 exact-on-page, 2
OK-SPACING (pypdf mid-word spacing only), 0 off-page, 0 missing.** Every
citation in this label is real text on the page it names. That is the
mechanical half only — it says nothing about whether the quote supports the
mechanism claimed.

---

## Summary table

(Filled in as each typology is assessed below. Confidence and citation count
are from the golden label; min quote length is the shorter of the typology's
citations, counted in characters after whitespace collapse.)

| # | Typology | Citations | Min quote len | Confidence | Classification |
|---|---|---|---|---|---|
| 1 | PAT007 Shell Company Network | 2 | 128 | high | SUPPORTED |
| 2 | PAT003 Layered Ownership | 2 | 204 | high | SUPPORTED |
| 3 | PAT010 Hidden Controller | 2 | 130 | high | SUPPORTED |
| 4 | PAT005 Common Address | 2 | 98 | medium | SUPPORTED |
| 5 | PAT001 Shared Director | 2 | 65 | medium | SUPPORTED (one weak citation) |
| 6 | PAT002 Shared Beneficial Owner | 2 | 98 | medium | SUPPORTED (one boilerplate citation) |
| 7 | PAT009 Related Party Trading | 2 | 97 | medium | SUPPORTED (one boilerplate citation) |
| 8 | BA004 Circular Funds Flow | 2 | 159 | high | SUPPORTED |
| 9 | BA008 Layering | 2 | 60 | high | SUPPORTED (single case study) |
| 10 | BA007 Cash Intensive Activity | 2 | 92 | medium | SUPPORTED |
| 11 | BA005 Rapid Movement | 2 | 71 | medium | SUPPORTED |
| 12 | BA003 Mule Accounts | 2 | 107 | medium | SUPPORTED |
| 13 | TBML004 Phantom Shipping | **1** | 183 | medium | **THIN** |
| 14 | TBML001 Over Invoicing | 2 | 108 | medium | **UNSUPPORTED** |
| 15 | TBML008 Third Party Payment Abuse | 2 | 86 | medium | SUPPORTED |
| 16 | TBML009 Shell Company Trading | 2 | 203 | medium | SUPPORTED |
| 17 | CM002 Market Manipulation | 2 | 52 | medium | SUPPORTED (contestable, fragment) |
| 18 | SAN004 Front Companies | 2 | 89 | medium | SUPPORTED |
| 19 | SAN001 Ownership Evasion | **1** | 187 | low | **THIN** |
| 20 | SAN008 High Risk Jurisdictions | 2 | 153 | medium | **UNSUPPORTED** |

**Tally: 16 SUPPORTED, 2 THIN, 2 UNSUPPORTED, 0 pure BOILERPLATE at the
typology level** (two typologies carry one boilerplate-grade citation each but
have a second, strong citation that carries the typology).

Single-citation typologies: **2 of 20** (TBML004, SAN001) — both land in THIN,
not SUPPORTED. Confidence distribution: 5 `high`, 14 `medium`, 1 `low`. All 5
`high`s carry 2 citations; none of the single-citation typologies is `high`,
which is the README's own rule holding. One `high` (BA008) is flagged below
for a narrower issue: both its citations, though two sentences, come from the
same single case study rather than two independent document locations.

---

## Per-typology detail

### PAT007 Shell Company Network — SUPPORTED
- p31/f29 (128 chars): "shell companies are the most common type of legal
  person used in schemes and structures designed to obscure beneficial
  ownership" — general prevalence statement, not network-specific on its own.
- p140/f138 (132 chars): "A network of 42 shell companies with different lines
  of business was dismantled, with companies located in Mexico and others
  abroad." (Case Study 51, Mexico)
- Location check: both OK.
- Judgement: the second citation names a "network" of shell companies
  directly and is decisive on its own; doctrine matches (network of entities
  exhibiting shell-company characteristics). The first citation is weaker
  (general prevalence, not a network claim) but the pairing is fine — one
  strong quote is enough per the set's own convention.

### PAT003 Layered Ownership — SUPPORTED
- p28/f26 (204 chars): "Adding numerous layers of ownership between an asset
  and the beneficial owner in different jurisdictions, and using different
  types of legal structures, can prevent detection and frustrate
  investigations."
- p64/f62 (225 chars): "often a chain of companies was established, with one
  company the shareholder of another, which was the shareholder of another,
  which added complexity to the structure, and further removed the beneficial
  owner from the assets." (Case Study 78, a New Zealand law-firm chain)
- Location check: both OK.
- Judgement: both quotes describe the exact mechanism (intermediate entities
  between UBO and subject), one as doctrine statement, one as a worked case.
  Strongest pairing in the set — general statement plus a concrete instance.

### PAT010 Hidden Controller — SUPPORTED
- p8/f6 (139 chars): "The role of the nominee, in many cases, is to protect or
  conceal the identity of the beneficial owner and controller of a company or
  asset."
- p85/f83 (130 chars): "This effectively disguises the beneficial owner of the
  account and allows the controller to circumvent CDD obligations
  altogether." — full context (para 218): straw men are coerced to open bank
  accounts, then hand over login credentials to the real controller, who
  operates the account without ever appearing on it.
- Location check: both OK.
- Judgement: p85 in full context is a clean match — effective control
  exercised by someone who never appears as the declared owner/controller,
  which is exactly PAT010's doctrine. SUPPORTED, and the fuller context
  (not visible from the 130-char quote alone) makes it stronger than the
  quote alone suggests.

### PAT005 Common Address — SUPPORTED
- p181/f179 (145 chars): "large numbers of shell companies, particularly those
  with foreign beneficial owners, will be registered to the same address and
  telephone number." — from Annex D (Detection Techniques), explaining why
  shared TCSP mailbox addresses occur.
- p42/f40 (98 chars): "The address listed on the companies' register was the
  same virtual office in Auckland as the TCSP." (Case Study 77, New Zealand)
- Location check: both OK.
- Judgement: p181 is methodological/explanatory rather than a case example,
  but it directly names the mechanism (shared registration address across
  shell companies); p42 supplies the concrete instance. Net SUPPORTED.

### PAT001 Shared Director — SUPPORTED (one weak citation)
- p39/f37 (65 chars): "or by creating false links between companies that share
  nominees." — a sentence fragment (lowercase start); full sentence is "The
  presence of nominee directors and shareholders in company records can also
  affect law enforcement investigations by delaying the identification of the
  beneficial owner, or by creating false links between companies that share
  nominees." This is framed as an investigative HAZARD (shared nominees can
  mislead investigators), not a description of the technique being used to
  conceal ownership — it is adjacent to PAT001's mechanism rather than a
  clean statement of it.
- p42/f40 (101 chars): "using the same nominee director, nominee shareholder
  and virtual office address as the shell company." (Case Study 77) — this is
  the tail clause of the SAME sentence TBML009 also cites in full (see
  overlap note below).
- Location check: both OK.
- Judgement: p39 is THIN on its own — short (65 chars, under the ~90-char
  flag threshold), a mid-sentence fragment, and describes a risk of false
  linkage rather than the technique. p42 is a clean, concrete match (a shared
  nominee director across four shell companies in one case). Net SUPPORTED
  on the strength of p42; p39 does little work and would not carry the
  typology alone.

### PAT002 Shared Beneficial Owner — SUPPORTED (one boilerplate citation)
- p45/f43 (132 chars): "the scheme serves the purpose of disguising the fact
  that the lender and borrower are beneficially owned by the same natural
  person." (Case Study 5/6, Australia loan-back scheme) — direct, strong.
- p188/f186 (98 chars): "involves two legal persons with similar or identical
  directors, shareholders, or beneficial owners" — **this is Annex E, the
  generic red-flag checklist**, not case narrative. It is bullet 22 of a
  numbered list of transaction red flags ("The transaction: ... involves two
  legal persons with similar or identical directors, shareholders, or
  beneficial owners"). It restates the typology's own definition as a
  checklist item rather than evidencing that this document develops the
  technique.
- Location check: both OK.
- Judgement: SUPPORTED on p45 alone, which is a clean case-specific match.
  p188 is BOILERPLATE-grade — a definitional checklist bullet, structurally
  the same class of citation the task brief calls out for ADV-2026-0016's
  SAN006. It happens not to sink this typology only because it isn't the
  sole citation.

### PAT009 Related Party Trading — SUPPORTED (one boilerplate citation)
- p81/f79 (97 chars): "The two companies traded with each other exclusively
  and did not have any other source of income." (Case Study 40, Israel) — the
  two companies were both set up and controlled by the same suspects via one
  TCSP, so "traded exclusively with each other" is a real related-party
  trading fact, not just relatedness in the abstract.
- p187/f185 (107 chars): "is occurring between two or more parties that are
  connected without an apparent business or trade rationale" — **also Annex
  E**, bullet 22's first sub-item, a lowercase-start fragment ("The
  transaction: [bullet] is occurring between...").
- Location check: both OK.
- Judgement: same pattern as PAT002 — one genuine case citation (p81, strong)
  plus one Annex E checklist fragment that adds nothing beyond restating the
  definition. Net SUPPORTED via p81.

### BA004 Circular Funds Flow — SUPPORTED
- p45/f43 (159 chars): "principally involves money being sent to companies
  which are owned or controlled by, or on behalf of, the same individual, and
  returned in the guise of a loan." — doctrine statement, para 97.
- p72/f70 (169 chars): "This 'round robin' scheme aimed to make funds
  movements appear as payments to other parties while, in reality, the funds
  ultimately returned to the original beneficiary." (Case Study 5, Australia)
- Location check: both OK.
- Judgement: textbook match on both — general definition plus a literal
  "round robin" case in which funds return to the originator. Strongest
  correspondent-banking mapping in the set.

### BA008 Layering — SUPPORTED (single case study underlies both citations)
- p43/f41 (137 chars): "channelled funds to a shadow financial scheme
  consisting of multiple layers of shell companies. The funds were finally
  withdrawn in cash."
- p43/f41 (60 chars): "indicating a co-ordinated layering process being
  undertaken." — lowercase-start fragment, short.
- Both citations are from Case Study 87 (Russia) on the same page.
- Location check: both OK.
- Judgement: the mechanism match is genuine — a chain of shell companies
  moving funds with an explicit "layering process" callout in the text.
  SUPPORTED. Flagged structurally because BOTH citations are two sentences of
  ONE case study rather than a general-statement-plus-example pairing like
  PAT003/BA004 above; for a `high`-confidence label the README's rule wants
  the document to "develop the technique," and this is one developed
  instance rather than the technique recurring across the document. Not a
  mechanism failure, but a narrower evidentiary base than its `high`
  confidence and its two-citation appearance suggest.

### BA007 Cash Intensive Activity — SUPPORTED
- p32/f30 (178 chars): "the most common form of front company is one that
  operates in the customer service industry (such as a restaurant, night
  club, or salon) as these businesses commonly handle cash."
- p32/f30 (92 chars): "often by disguising the illegitimate funds as cash
  sales made during the course of business." — lowercase-start fragment of
  the same paragraph.
- Location check: both OK.
- Judgement: matches BA007's doctrine (cash-intensive front business as cover
  for placing illicit cash) directly. The golden label's own
  `extraction_notes` already flags this as deliberately correct here "unlike
  in ADV-2026-0001," which this reading confirms.

### BA005 Rapid Movement — SUPPORTED
- p35/f33 (161 chars): "several accounts were opened in different countries
  for companies incorporated in foreign jurisdictions, enabling rapid
  movement of funds over numerous frontiers" — general paragraph (para 74).
- p141/f139 (71 chars): "The funds were generally withdrawn in less than 48
  hours after deposit." (Case Study 53, Namibia — funds routed through
  accounts and re-routed to other jurisdictions within 48 hours).
- Location check: p35 OK-SPACING (pypdf mid-word split only), p141 OK.
- Judgement: strong, direct match — velocity is BA005's defining signal and
  the case gives a concrete number (48 hours).

### BA003 Mule Accounts — SUPPORTED
- p85/f83 (107 chars): "criminals will often coerce 'straw men' to establish
  bank accounts for use by the criminal at a later time."
- p167/f165 (129 chars): "The straw men are paid a certain amount of money
  for the use of their accounts. The intermediary accounts are changed
  constantly." (Case Study 97, Turkey — illegal betting proceeds moved
  through paid straw-man accounts, rotated constantly)
- Location check: both OK.
- Judgement: p167 is a clean match to BA003's doctrine (personal account,
  paid for use, controller-directed, rotated). SUPPORTED.

### TBML004 Phantom Shipping — THIN (single citation)
- p79/f77 (183 chars, only citation): "including those that do not result in
  the actual movement of goods, or which purport to involve the provision
  and/or acquisition of services to or from other international businesses."
- Full context (para 206): "legal persons can facilitate trade-based money
  laundering (TBML) typologies, **including** those that do not result in the
  actual movement of goods..." — this is the report's own SCOPING sentence,
  introducing a category of TBML techniques in general, immediately followed
  by a pointer to Case Study 40 (Israel) — which is a shell-company trading
  and tax-evasion scheme (already cited for TBML009/PAT009 above) and does
  **not** itself describe goods that failed to ship.
- Location check: OK.
- Judgement: THIN, not SUPPORTED or UNSUPPORTED. The exact vocabulary of
  TBML004's doctrine appears verbatim ("do not result in the actual movement
  of goods"), so this is not a vocabulary-only match — but it is the
  document's abstract framing sentence, not a developed example, and the
  case study it introduces doesn't itself instantiate the mechanism. The
  golden label's own `extraction_notes` records that a second, weaker
  citation (p44, "the use of false loans and invoices to fraudulently
  disguise the beneficial ownership of a transaction") was already stripped
  from this typology on the mechanism test during the 2026-09-11 review —
  which means this typology has already been through one round of citation
  pruning and is now down to its last, thinnest citation. `medium` confidence
  is defensible under the README's single-bullet rule, but the single bullet
  here is a scope statement, not a technique statement.

### TBML001 Over Invoicing — UNSUPPORTED
- p66/f64 (108 chars): "The managers approved inflated invoices for
  maintenance work to be carried out by the construction companies" (Case
  Study 3, Australia).
- p70/f68 (128 chars): "the defendant altered invoices directed to one of the
  entities by inflating the cost of the work listed on the original
  invoices" (Case Study 101, United States).
- Location check: both OK.
- Judgement: **UNSUPPORTED.** TBML001's doctrine is specifically inflating
  the price of **traded goods** to move value across borders in international
  trade. Neither cited case is that. Case Study 3 is a domestic Australian
  kickback scheme — a university and construction companies inflating
  invoices for **maintenance work** (a service, not traded goods), with
  proceeds laundered into racehorses; there is no import/export of goods
  described at all in the cited passage. Case Study 101 is a **mortgage
  fraud** scheme — inflating invoices for property "improvements" (again a
  service, not goods) specifically to overstate collateral value on
  fraudulent loan applications; this is loan/collateral fraud, not trade
  value transfer. Both quotes share TBML001's vocabulary ("inflated
  invoices") while describing a different mechanism entirely — exactly the
  failure class the mechanism test exists to catch, and the same class of
  error the golden-set review already found and removed once on a different
  advisory (ADV-2026-0013's TBML002U, per `evals/golden/README.md`'s "First
  baseline" section) and that the extraction agent independently made too on
  that same advisory. This is the same error, unremoved, on this one.

### TBML008 Third Party Payment Abuse — SUPPORTED
- p42/f40 (105 chars): "The majority of transactions were payments being made
  on behalf of Vietnamese entities for imported goods" (Case Study 80, New
  Zealand).
- p152/f150 (86 chars): "However, the cash flow goes through a Panamanian
  entity with a bank account in Latvia." (Case Study 73, Netherlands — a
  Dutch company ships goods directly to Ukrainian buyers, but the payment for
  those goods is routed through an unrelated Panamanian/Latvian entity).
- Location check: both OK.
- Judgement: p152 in full context is a clean, textbook third-party-payment
  case — goods flow one path, payment flows through a different, unrelated
  entity. SUPPORTED.

### TBML009 Shell Company Trading — SUPPORTED
- p81/f79 (256 chars): "The suspects used a TCSP to register and operate two
  international shell companies (Company A and Company B) to create the
  false appearance that the revenues from their international trading did
  not belong to the local Israeli company which they controlled" (Case
  Study 40).
- p42/f40 (203 chars): "Transactions were also made with three other New
  Zealand shell companies registered by the same TCSP, using the same
  nominee director, nominee shareholder and virtual office address as the
  shell company." (Case Study 77) — **overlaps with PAT001's p42 citation**;
  see cross-typology overlap note below.
- Location check: both OK.
- Judgement: both describe shell counterparties with no substance used to
  give real trade a legitimate face — matches doctrine directly. SUPPORTED.

### CM002 Market Manipulation — SUPPORTED (contestable parent choice; one very short fragment)
- p120/f118 (86 chars): "who manipulated the stock price by making misleading
  representations and/or omissions." (Case Study 12, Canada — a promotional
  pump scheme with nominee shareholders, bearer-form shares and a reverse
  merger).
- p170/f168 (52 chars): "1) fraudulent stock promotion and price manipulation"
  — the **shortest quote in this label** and a numbered-list fragment (item
  "1)" of "There were 3 inter-related schemes: 1) ... 2) ... 3) ...", Case
  Study 102, Annex C repeat of the case already narrated at page 66).
- Location check: both OK.
- Judgement: both cases are real securities-promotion/price-manipulation
  schemes, so the mechanism is genuinely present in the document — SUPPORTED.
  Two flags worth the owner's attention: (1) the p170 quote is a 52-character
  list-item fragment with no verb of its own outside the enclosing sentence —
  it reads fine because "manipulation" is unambiguous, but it is well under
  the ~90-char threshold and a clean example of a cut mid-list; (2) the
  golden label's own `extraction_notes` calls this mapping "contestable" —
  CM007 Pump and Dump is arguably the more precise doctrine fit for a
  stock-promotion scheme, with CM002 kept as the broader parent. That is a
  legitimate labelling judgement call, not a mechanism failure, but it means
  this typology's presence in the "37 of 57 exercised" count is doing some
  work that a narrower, sibling typology could have done instead.

### SAN004 Front Companies — SUPPORTED
- p34/f32 (161 chars): "U.S. authorities identified front companies used to
  conceal the ownership of certain U.S. assets by Bank Melli, which was
  previously designated by US authorities" (Case Study 99).
- p172/f170 (89 chars): "OFAC designated shell companies tied to the straw
  man that were used to hold real estate." (Case Study 105 — OFAC designated
  a foreign PEP under the Kingpin Act, a straw man acting for him, AND shell
  companies tied to the straw man).
- Location check: both OK.
- Judgement: both are squarely sanctions-designation cases (OFAC/UNSCR),
  front/shell companies concealing a designated party's assets — exactly
  SAN004's doctrine. Strongest sanctions mapping in the set.

### SAN001 Ownership Evasion — THIN (single citation)
- p138/f136 (187 chars, only citation, `low` confidence): "the designated
  individual was the holder of assets and economic resources in his own name
  or otherwise available through corporate vehicles that had been under
  freezing orders since 2014."
- Location check: OK.
- Judgement: THIN. The quote is compound and only half of it is SAN001's
  mechanism. "Holder of assets... in his own name" describes a **freezing
  order violation** (openly continuing to hold frozen assets), which is not
  ownership *evasion* at all — it is the opposite, a failure to conceal
  anything. Only the second clause ("otherwise available through corporate
  vehicles") touches SAN001's actual doctrine (layered structures concealing
  a designated party's control). The label picked a real designated-party
  case but the cited sentence does not cleanly develop the evasion mechanism
  on its own; a cleaner quote describing the corporate-vehicle layering
  specifically may exist elsewhere in this case's fuller writeup and was not
  located in this pass. `low` confidence on a single citation is consistent
  with the README's own rule, which is the one thing this citation gets
  structurally right.

### SAN008 High Risk Jurisdictions — UNSUPPORTED
- p81/f79 (159 chars): "FIUs, law enforcement, and other competent
  authorities regularly identify criminals using legal persons and bank
  accounts established in low-tax jurisdictions."
- p79/f77 (153 chars): "criminals will often establish legal persons and bank
  accounts in cities that are considered to be major regional and global
  trade and financial centres."
- Location check: both OK.
- Judgement: **UNSUPPORTED.** SAN008's doctrine is exposure to *sanctioned,
  embargoed or high-risk* jurisdictions as a sanctions-relevant finding in
  its own right — "the jurisdiction... IS the finding." Both cited sections
  ("Low-Tax Jurisdictions," para 211-212, and "Trade and Financial Centres,"
  para 206-210) are about tax-haven and secrecy-jurisdiction shopping used to
  **conceal beneficial ownership** — a distinct concealment mechanism, not a
  sanctions/embargo exposure signal. Neither passage names a sanctioned or
  embargoed jurisdiction, an entity's sanctions-relevant footprint, or a
  designated party's jurisdictional exposure; both are generic exposition
  about why criminals like low-tax financial hubs, illustrated by cases about
  ownership concealment (Case Study 12's securities fraud, Case Study 3's
  invoice fraud) that have nothing to do with sanctions. This is vocabulary
  overlap ("jurisdiction," and the document elsewhere clearly is
  sanctions-adjacent via Bank Melli/Iran) without mechanism overlap — the
  document's actual sanctions-jurisdiction material (Bank Melli/Iran, UNSCR
  1803) is cited elsewhere for SAN004, not here.

---

## Structural findings across the twenty

- **Single-citation typologies: 2 of 20** (TBML004, SAN001) — both are THIN,
  not SUPPORTED, in this review. Neither is `high` confidence, so the
  README's single-bullet rule is formally respected, but both single
  citations are compound/scoping sentences rather than clean technique
  statements, which is a weaker floor than "one bullet is enough" implies in
  practice.
- **Quotes under ~90 characters:** PAT001's first (65), BA008's second (60),
  BA007's second (92, borderline), BA005's second (71), TBML008's second (86),
  CM002's second (52, the shortest in the label). Four of these six turned
  out fine on inspection because the surrounding case narrative (read
  separately in this pass) supports them; two (PAT001's first, and to a
  lesser extent CM002's second) are doing close to no independent work.
- **Quotes cut mid-sentence (lowercase start / list-fragment):** PAT001's
  first ("or by creating..."), BA008's second ("indicating a
  co-ordinated..."), BA007's second ("often by disguising..."), PAT002's
  second ("involves two legal persons..."), PAT009's second ("is
  occurring..."), SAN001's only citation ("the designated individual..."),
  CM002's second ("1) fraudulent..."). Seven of twenty typologies carry at
  least one fragment-style citation. None of these were fatal on their own in
  this review (the ones attached to Annex E in particular were fatal only in
  the sense of contributing nothing, not in the sense of being wrong), but
  the pattern recurs across roughly a third of the label, and it is exactly
  the shape the task brief warned about (ADV-2026-0016's SAN006 case).
- **Citations drawn from Annex E (the generic red-flag checklist) rather
  than case narrative:** PAT002's p188 citation and PAT009's p187 citation.
  Both are numbered-list items that restate each typology's own definition
  in the abstract, not case-specific evidence. This document's own
  `extraction_notes` says "Annex E (red flags) hold no typology beyond those
  cited" — true in the sense that no NEW typology rests solely on Annex E,
  but two already-cited typologies partly rest on it anyway. Structurally
  this is the same failure mode as "boilerplate" — generic list text passing
  a location check while evidencing nothing beyond the definition itself —
  just embedded inside an otherwise-adequate label rather than standing
  alone.
- **Two typologies overlap on the same underlying sentence:** PAT001's p42
  citation ("using the same nominee director, nominee shareholder and
  virtual office address as the shell company") is the exact tail clause of
  TBML009's p42 citation, which quotes the full sentence including that
  clause. Same case study (Case Study 77, New Zealand), same page, same
  sentence, split across two typologies. Three typologies in total (PAT001,
  PAT005, TBML009) draw citations from Case Study 77 — a legitimately rich
  case study, but one that is underwriting a disproportionate share of the
  network/TBML mappings in this label.
- **The one `high`-confidence label resting on a single case study:** BA008
  Layering's two citations are both sentences from Case Study 87 (Russia).
  Every other `high`-confidence typology pairs a general/doctrinal statement
  with a separate case example from a different part of the document; BA008
  pairs two sentences of the same case. Not a mechanism failure, but the
  narrowest evidentiary base among the five `high` typologies.

## Closing estimate

**Of the 20 claimed governed typologies: 16 SUPPORTED, 2 THIN, 2
UNSUPPORTED, 0 pure BOILERPLATE.** That is 80% clean, 10% present-but-weakly-
cited, 10% mismatched mechanism.

Treating the 2 UNSUPPORTED (TBML001, SAN008) as label inflation that should
be removed, and being agnostic about the 2 THIN ones (TBML004, SAN001 —
plausibly real but not decisively evidenced by the cited quote), the honest
range for this document's true governed-typology count is **16 to 18**, not
20. That would move this document's typology recall denominator from 20 down
to somewhere in that range.

**What that does and does not explain.** `data/records/ADV-2026-0004.json`
(the agent's actual run for this advisory, read for this triage; not a golden
label and not something this triage was asked to score) asserted 5 governed
typologies: FND003 (excluded from golden by design — a foundation capability,
not a behaviour), PAT003, PAT007, PAT010 (all three SUPPORTED above, and among
the *strongest*-cited typologies in the label), and PAT004 (not in golden at
all). That is 3 true positives against the 20-typology golden set, i.e. the
documented recall of 3/20 = 0.15.

- Against a corrected denominator of 18 (removing only the 2 UNSUPPORTED),
  recall becomes 3/18 = 0.167.
- Against a corrected denominator of 16 (removing UNSUPPORTED and THIN),
  recall becomes 3/16 = 0.188.

Either way, **label inflation on this document is real but small**: it moves
recall from 0.15 to roughly 0.17-0.19, not to anything close to the 0.5+ that
would make this document look like the rest of the set. The agent's 3 hits
land exactly on the 3 most strongly, multiply-evidenced typologies in the
label (general-statement-plus-case-example pairs); it did not almost-get any
of the 4 flagged typologies, nor did it get close on the two Annex-E-assisted
ones. That is consistent with the full-baseline finding that the agent
asserts a near-fixed small number of typologies regardless of document size —
inflation in this one label does not, on this evidence, explain why the
number stayed at 5.

**Uncertainty and scope, stated plainly.** This is one document, hand-checked
by the same kind of process (Claude reading a PDF and applying a mechanism
test) that produced the label being checked — the correlation the brief warns
about is fully present here too. The THIN/UNSUPPORTED calls above are this
session's judgement, not a ruling; in particular:
- TBML004 and SAN001 could reasonably be argued back to SUPPORTED by someone
  who reads the compound sentences more charitably, or who finds a better
  quote elsewhere in the document (190 pages were not exhaustively re-read
  end-to-end looking for uncited alternative evidence for every typology —
  only the pages the existing citations pointed at, plus immediate
  surrounding context, were read).
- SAN008 is the call most likely to be disputed: "high-risk jurisdiction" is
  a broader idea in AML practice than "sanctioned jurisdiction," and a reader
  who treats FATF-style low-tax/secrecy jurisdictions as inherently
  "high-risk" for SAN008's purposes would score this SUPPORTED. This triage
  reads SAN008's own doctrine text ("sanctioned, embargoed or high-risk...
  the jurisdiction IS the finding") as requiring something closer to
  sanctions/embargo exposure than tax-haven shopping, and neither cited
  passage nor its surrounding case studies mentions a sanctioned or embargoed
  jurisdiction.
- This triage did not attempt to re-derive whether the 37 emergent labels or
  the actor entries for this document hold up under the same test — only the
  20 governed typologies named in the task.

**Recommendation for the owner:** adjudicate TBML001 and SAN008 first (the 2
UNSUPPORTED calls) — these are the clearest candidates for removal or
re-citation. TBML004 and SAN001 are lower-priority calls (THIN, single
citation, but not clearly wrong) worth a second look if time allows. The two
Annex-E-assisted citations (PAT002's p188, PAT009's p187) don't need action —
each typology already stands on its other citation — but could be swapped for
better case-specific quotes if this label is revised for other reasons.
