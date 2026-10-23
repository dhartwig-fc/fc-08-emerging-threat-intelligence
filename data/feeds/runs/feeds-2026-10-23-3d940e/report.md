# Friday run feeds-2026-10-23-3d940e: UNFINISHED

6 new item(s), 4 kept, 2 dropped by triage, 3 extracted, 1 unfinished; US$1.96 spent of the US$5.00 ceiling.

## Sources

| source | status | listed | already decided | new | carried forward |
|---|---|---|---|---|---|
| ofsi | ok | 20 | 20 | 0 | 0 |
| fincen | ok | 15 | 15 | 0 | 0 |
| ofac | ok | 10 | 6 | 4 | 2 |

## Carried forward: 2 (deferred in an earlier run, no longer on the listing)

- `ofac:528a733c96bd988a` Counter Narcotics, Counter Terrorism, Iran-related, and Non-Proliferation Designations -- deferred in feeds-2026-10-11-e7ad24
- `ofac:dc63a1c2b84a58f7` Counter Terrorism and Transnational Criminal Organizations Designations; Belarus, Counter Narcotics, and Libya Designations Removals -- deferred in feeds-2026-10-11-e7ad24

## Kept by triage (relevant): 4

- `ofac:528a733c96bd988a` Counter Narcotics, Counter Terrorism, Iran-related, and Non-Proliferation Designations -- Designates Sinaloa Cartel leadership and a narco-corruption network in Baja California, describing cartel hierarchy and corruption roles tied to drug trafficking. Quote (p.1): "CHART - The Sinaloa Cartel's Los Mayos Faction - September 2026 CHART - Los Mayos Narco-Corruption in Baja California - September 2026"
- `ofac:dc63a1c2b84a58f7` Counter Terrorism and Transnational Criminal Organizations Designations; Belarus, Counter Narcotics, and Libya Designati -- Designates Tren de Aragua members tied to theft of millions from US banks, listing TRX digital-currency addresses used to launder stolen funds plus shell entities. Quote (p.1): "Digital Currency Address - TRX TJjRAn9kLiyh8h6gjBjaYjkfDkskgZfyW9; Cedula No. V-13126628 (Venezuela) (individual) [SDGT] [TCO] (Linked To: TREN DE ARAGUA)."
- `ofac:17287d3622d0d858` Iran-related Designations; Cuba Designation; Issuance of New and Amended General Licenses and Frequently Asked Questions -- Designates Iranian exchange/money-service companies and a Cuban state bank as part of Iran's shadow banking network used to move funds for sanctioned individuals, evading sanctions. Quote (p.3): "ABOLHASAN JALALI AND PARTNERS EXCHANGE COMPANY ... Organization Type: Other monetary intermediation; National ID No. 14005814280 (Iran); Registration Number 14150 (Iran) [IRAN-EO13902]."
- `ofac:6a05e5175268a818` Iran-related Designations; Belarus and North Korea Designations Removals; Issuance of Iran-related and Russia-related Ge -- Designates an Iran shadow fleet network: shipping/management shell companies and tankers used to move Iranian oil evading sanctions. Quote (p.2): "ROXETTE MARITIME SHIPPING AND TRADING S.A., Panama; 5th Floor, 90 Iroon Politechneiou Avenue, Piraeus 185 36, Greece; Organization Established Date 03 Jan 2023; RUC # 155731846-2-2023 (Panama); Identi"

## Dropped by triage (not relevant), with the reason and the quote: 2

- `ofac:a1a5b81d7d18cf50` Protecting American Intellectual Property Act of 2022 (PAIPA) Designations; Issuance of Associated General Licenses -- Bare list of Chinese venture-capital entities added to the NS-MBS list with standard PAIPA restrictions; no description of how IP theft occurred or network method. Quote (p.1): "BEIJING QIJI CHUANGTAN PHASE I VENTURE CAPITAL CENTER LIMITED PARTNERSHIP ... PAIPA Section 2 Information: BLOCKING OF PROPERTY (entity)."
- `ofac:5296f6b0f92e0c28` Issuance of Amended Venezuela-related General License and Frequently Asked Question -- Only issuance of an amended Venezuela general license and FAQ; no method, red flag or case described. Quote (p.1): "OFAC is issuing Venezuela-related General License 60A, "Authorizing Transactions Related to Earthquake Relief Efforts in Venezuela.""

## Unfinished: 1 (they return next Friday unless dropped)

- `ofac:6a05e5175268a818` Iran-related Designations; Belarus and North Korea Designations Removals; Issuance of Iran-related and Russia-related Ge: relevant, not queued for extraction

## Extraction: 3 queued, 3 extracted, 0 failed, 0 deferred for budget

| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable | citations not on their page | cost |
|---|---|---|---|---|---|---|---|
| `ofac:528a733c96bd988a` | ADV-2026-0030 | extracted | 1 | 12 (2) | 2 of 12 | 0 of 30 | US$0.60 |
| `ofac:dc63a1c2b84a58f7` | ADV-2026-0031 | extracted | 2 | 17 (0) | 0 of 17 | 0 of 30 | US$0.44 |
| `ofac:17287d3622d0d858` | ADV-2026-0032 | extracted | 1 | 28 (0) | 0 of 28 | 0 of 37 | US$0.69 |

## Reconciliation: clean

| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |
|---|---|---|---|---|---|---|---|---|
| adv-2026-0030-extractor-c15deb8448 | extractor | SUCCESS | US$0.60 | 57 | 56 | 0 | 0 | 0 |
| adv-2026-0031-extractor-ecb11dbd4f | extractor | SUCCESS | US$0.44 | 58 | 57 | 0 | 0 | 0 |
| adv-2026-0032-extractor-157e111999 | extractor | SUCCESS | US$0.69 | 78 | 77 | 0 | 0 | 0 |
| feeds-2026-10-23-3d940e | orchestrator | SUCCESS | US$0.23 | 36 | 35 | 0 | 0 | 2 |

## Cost

US$1.96 counted against the US$5.00 ceiling (a session whose cost never arrived is counted at its cap); US$1.96 reported by the sessions' own telemetry.

## Next

`python tools/accept_run.py feeds-2026-10-23-3d940e` -- accept, drop or defer each item.
