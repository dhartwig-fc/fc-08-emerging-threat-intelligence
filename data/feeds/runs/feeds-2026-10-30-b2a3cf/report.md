# Friday run feeds-2026-10-30-b2a3cf: COMPLETE

9 new item(s), 3 kept, 6 dropped by triage, 3 extracted, 0 unfinished; US$1.41 spent of the US$5.00 ceiling.

## Sources

| source | status | listed | already decided | new | carried forward |
|---|---|---|---|---|---|
| ofsi | ok | 20 | 16 | 4 | 0 |
| fincen | ok | 15 | 15 | 0 | 0 |
| ofac | ok | 10 | 5 | 5 | 0 |

## Kept by triage (relevant): 3

- `ofac:37c7a48086d7a376` North Korea Designations; Democratic Republic of the Congo-related Designations -- Designates DPRK IT-worker fraud facilitation network and Rwandan MOD/bank supporting M23, listing digital currency wallet addresses used by facilitators moving illicit IT-worker proceeds. Quote (p.1): "BOYKOV, Ilya Aleksandrovich ... Digital Currency Address - ETH 0x12Ea80238C7d805D003ce793594e92d84A6f4E8d; alt. Digital Currency Address - ETH 0x761edd5e4546229a0bd35ae99b4d3d01cf4a3510 ... Digital Cu"
- `ofac:6a05e5175268a818` Iran-related Designations; Belarus and North Korea Designations Removals; Issuance of Iran-related and Russia-related Ge -- Designates an Iran shadow-fleet sanctions-evasion network of shipping/legal front companies and flagged vessels used to move Iranian petroleum, describing the structure and roles used to evade sanctions. Quote (p.2): "KARNAKIS AND KARNAKIS, Global Plaza Building, Calle 50, Floor 21, Panama City, Panama... ROXETTE MARITIME SHIPPING AND TRADING S.A., Panama...Identification Number IMO 6385886 [IRAN-EO13902]... ANEMOS"
- `ofac:69dba911486675f1` Settlement Agreement between the U.S. Department of the Treasury's Office of Foreign Assets Control and Extreme Networks -- Settlement describes how Extreme Networks exported networking equipment to a blocked Russian defense manufacturer over multiple shipments, a sanctions evasion/export control case. Quote (p.1): "Between September 2018 and March 2022, Extreme exported networking equipment and related services on nine occasions from the United States to Joint Stock Company (JSC) Moskovskiy Mashinostroitelniy Za"

## Dropped by triage (not relevant), with the reason and the quote: 6

- `ofac:2d4eaee2ca90d6ef` Issuance of Amended Iran-related General License -- Notice of issuance of an amended general licence authorizing wind-down of transactions; no method or case described. Quote (p.1): "The Department of the Treasury's Office of Foreign Assets Control (OFAC) is issuing Iran General License FF-1, "Authorizing the Wind Down of Transactions Involving International Development Bank for I"
- `ofac:1e6fd612bca589c8` Issuance of Amended Frequently Asked Questions Regarding Blocking and Rejecting Transactions and Filing Reports with OFA -- Notice of amended FAQs on blocking/rejecting transactions and filing reports; guidance update only, no method or case described. Quote (p.1): "The Department of the Treasury's Office of Foreign Assets Control (OFAC) is amending several Frequently Asked Questions (FAQs) today (10, 32, 33, 34, 35, 36, 41, 42, 49, 50, and 53) as part of its ong"
- `ofsi:31cead5f20d59e51` Guidance: OFSI General Licence INT/2025/7895596 -- General licence permitting continuation of business with Lukoil Bulgaria entities; no method or typology described. Quote (p.1): "On 14 November 2025, OFSI issued General Licence INT/2025/7895596 under regulation 64 of the Russia (Sanctions) (EU Exit) Regulations 2019 ("the Russia Regulations") which allows for the continuation "
- `ofsi:d19286cea6e47ab5` Guidance: UK Financial Sanctions FAQs -- FAQ guidance page listing update history to FAQ numbers; restates obligations/licence mechanics without describing a crime method or case. Quote (p.1): "26 October 2026 New FAQ 206 added, FAQs 64, 71 and 75 amended. FAQ 184 withdrawn."
- `ofsi:8b4ab1b458a2d282` Guidance: Legal Services General Licence -- General licence guidance page tracking legal fees general licences and reporting forms; procedural licence details only, no method or case described. Quote (p.1): "Legal Services General Licence INT/2026/11112108 and Legal Fees General Licence Reporting form"
- `ofsi:b449a79412985cef` Guidance: OFSI General Licence INT/2026/11112108 -- New general licence for legal services payments; purely procedural licence notice, no method or case described. Quote (p.1): "OFSI has issued a new Legal Services General Licence INT/2026/11112108 under most UK Autonomous Sanctions Regimes (see Annex 1 of the General Licence for the list of regimes covered) which will take e"

## Unfinished: 0 (they return next Friday unless dropped)

None.

## Extraction: 3 queued, 3 extracted, 0 failed, 0 deferred for budget

| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable | citations not on their page | cost |
|---|---|---|---|---|---|---|---|
| `ofac:37c7a48086d7a376` | ADV-2026-0033 | extracted | 4 | 16 (0) | 0 of 16 | 0 of 33 | US$0.61 |
| `ofac:6a05e5175268a818` | ADV-2026-0034 | extracted | 1 | 18 (0) | 0 of 18 | 0 of 25 | US$0.42 |
| `ofac:69dba911486675f1` | ADV-2026-0035 | extracted | 1 | 3 (0) | 0 of 3 | 0 of 7 | US$0.16 |

## Reconciliation: clean

| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |
|---|---|---|---|---|---|---|---|---|
| adv-2026-0033-extractor-a09f2f0d33 | extractor | SUCCESS | US$0.61 | 69 | 68 | 0 | 0 | 0 |
| adv-2026-0034-extractor-86f8c3e32a | extractor | SUCCESS | US$0.42 | 48 | 47 | 0 | 0 | 0 |
| adv-2026-0035-extractor-e0a757ac2c | extractor | SUCCESS | US$0.16 | 20 | 19 | 0 | 0 | 0 |
| feeds-2026-10-30-b2a3cf | orchestrator | SUCCESS | US$0.22 | 40 | 39 | 0 | 0 | 0 |

## Cost

US$1.41 counted against the US$5.00 ceiling (a session whose cost never arrived is counted at its cap); US$1.41 reported by the sessions' own telemetry.

## Next

`python tools/accept_run.py feeds-2026-10-30-b2a3cf` -- accept, drop or defer each item.
