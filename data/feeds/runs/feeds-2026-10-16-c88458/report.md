# Friday run feeds-2026-10-16-c88458: UNFINISHED

6 new item(s), 4 kept, 2 dropped by triage, 3 extracted, 1 unfinished; US$1.65 spent of the US$5.00 ceiling.

## Sources

| source | status | listed | already decided | new |
|---|---|---|---|---|
| ofsi | ok | 20 | 19 | 1 |
| fincen | ok | 15 | 15 | 0 |
| ofac | ok | 10 | 5 | 5 |

## Kept by triage (relevant): 4

- `ofac:a716c3bc129fae43` Counter Narcotics and Counter Terrorism Designations -- Cartel del Noreste network laundering drug proceeds through front companies: construction firms, fuel distributors, a horse-racing track/stable and a transport logistics company, all linked to designated facilitators. Quote (p.1): "CLUB LA MOLIENDA (a.k.a. LA MOLIENDA RACE TRACK...) Organization Type: Operation of sports facilities... [SDGT] [ILLICIT-DRUGS-EO14059] (Linked To: CARTEL DEL NORESTE)"
- `ofac:94d34cd7226d01c2` Iran-related Designations and Designations Updates; Transnational Criminal Organizations Designation; Publication of Ira -- Iran sanctions-evasion network using Hong Kong/Shanghai shell and trading companies linked to Iranian heavy-equipment manufacturer to procure goods for Iran's automotive/rail sector, evading secondary sanctions. Quote (p.2): "Block E, 16 F, Huadu Mansion, No. 858 Zhangyang Rd., Shanghai 200135, China; Organization Established Date 31 May 2011; Enterprise Number 3100574132491 (China); Registration Number 310115400269442 (Ch"
- `ofac:5b0db35c6f75d3f9` Settlement Agreement between the U.S. Department of the Treasury's Office of Foreign Assets Control and Bank of America, -- Enforcement case describing specific sanctions-compliance failures (processing payments via blocked banks, poor alert prioritization, slow watchlist updates, mishandled accounts) that led to violations. Quote (p.1): "The apparent violations occurred when Bank of America processed payments involving blocked banks, failed to appropriately prioritize alerts for customers who were exact name- and date of birth-matches"
- `ofac:17287d3622d0d858` Iran-related Designations; Cuba Designation; Issuance of New and Amended General Licenses and Frequently Asked Questions -- Network of Iranian exchange companies (monetary intermediation) linked to designated individuals, used to move funds/evade sanctions; part of operation targeting abuse of religious charity networks. Quote (p.3): "ABOLHASAN JALALI AND PARTNERS EXCHANGE COMPANY (Arabic: شرکت صرافی ابوالحسن جلالی و شرکا) (a.k.a. JALALI AND PARTNERS GENERAL PARTNERSHIP COMPANY), Ground Floor, Salarieh Commercial Complex, No. 0, Mo"

## Dropped by triage (not relevant), with the reason and the quote: 2

- `ofac:42ae5e4320ec6866` Venezuela-related Designation Removal -- Pure SDN delisting notice (name removals only), no method or typology described. Quote (p.1): "The following deletions have been made to OFAC's SDN List"
- `ofsi:d2fae94673b893f9` Guidance: OFSI General Licence - INT/2026/10050568 -- General licence authorizing specific payment category (ground rent/service charges); procedural notice, no method or case described. Quote (p.1): "OFSI issued General Licence INT/2026/10050568 under the 26 UK Autonomous Regulations listed in Annex I, which allows for DPs or Persons acting on behalf of DPs to make payments to a UK Bank Account he"

## Unfinished: 1 (they return next Friday unless dropped)

- `ofac:17287d3622d0d858` Iran-related Designations; Cuba Designation; Issuance of New and Amended General Licenses and Frequently Asked Questions: relevant, not queued for extraction

## Extraction: 3 queued, 3 extracted, 0 failed, 0 deferred for budget

| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable | citations not on their page | cost |
|---|---|---|---|---|---|---|---|
| `ofac:a716c3bc129fae43` | ADV-2026-0027 | extracted | 1 | 16 (0) | 0 of 16 | 0 of 22 | US$0.39 |
| `ofac:94d34cd7226d01c2` | ADV-2026-0028 | extracted | 2 | 18 (0) | 0 of 18 | 0 of 29 | US$0.79 |
| `ofac:5b0db35c6f75d3f9` | ADV-2026-0029 | extracted | 1 | 2 (0) | 0 of 1 | 0 of 11 | US$0.18 |

## Reconciliation: clean

| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |
|---|---|---|---|---|---|---|---|---|
| adv-2026-0027-extractor-0cd9e5eb76 | extractor | SUCCESS | US$0.39 | 50 | 49 | 0 | 0 | 0 |
| adv-2026-0028-extractor-846449976d | extractor | SUCCESS | US$0.79 | 63 | 62 | 0 | 0 | 0 |
| adv-2026-0029-extractor-983efa3eb1 | extractor | SUCCESS | US$0.18 | 24 | 23 | 0 | 0 | 0 |
| feeds-2026-10-16-c88458 | orchestrator | SUCCESS | US$0.29 | 37 | 36 | 0 | 0 | 2 |

## Cost

US$1.65 counted against the US$5.00 ceiling (a session whose cost never arrived is counted at its cap); US$1.65 reported by the sessions' own telemetry.

## Next

`python tools/accept_run.py feeds-2026-10-16-c88458` -- accept, drop or defer each item.
