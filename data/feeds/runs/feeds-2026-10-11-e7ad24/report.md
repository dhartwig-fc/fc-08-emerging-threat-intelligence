# Friday run feeds-2026-10-11-e7ad24: UNFINISHED

11 new item(s), 1 kept, 9 dropped by triage, 1 extracted, 1 unfinished; US$0.42 spent of the US$5.00 ceiling.

## Sources

| source | status | listed | already decided | new |
|---|---|---|---|---|
| ofsi | ok | 20 | 17 | 3 |
| fincen | ok | 15 | 15 | 0 |
| ofac | ok | 10 | 2 | 8 |

## Kept by triage (relevant): 1

- `ofac:67443fcb784dba53` Settlement Agreement between the U.S. Department of the Treasury's Office of Foreign Assets Control and Pegasus Worldwid -- Settlement describes enforcement case: freight forwarder dealt in blocked property by facilitating importation of a machine from a designated company, and stonewalled a subpoena for six months. Quote (p.1): "Between September 2023 and February 2024, Pegasus dealt in blocked property by facilitating the importation of a machine supplied by a designated company. Pegasus also failed to respond fully for six "

## Dropped by triage (not relevant), with the reason and the quote: 9

- `ofac:7c79f8bed47fc571` Issuance of Russia-related General License -- Bare notice issuing a general license for diesel fuel transactions; no method, red flag or case content. Quote (p.1): "The Department of the Treasury's Office of Foreign Assets Control (OFAC) is issuing Russia-related General License 135, "Authorizing Transactions Related to the Sale, Delivery, Offloading, and Importa"
- `ofac:aadbaddff9b290c6` Iran-related Designations; Issuance of Iran-related General License; Issuance of Amended Russia-related General License -- Bare SDN designation list (shadow-fleet individuals/entities) plus general license notices; no narrative of methods beyond identifying details. Quote (p.1): "Specially Designated Nationals List The following individuals have been added to OFAC's SDN List:"
- `ofac:ce5ba6b58a11204c` Designations Removals; Designations Updates; Publication of Iran-related OFAC Alert; Publication of Amended Iran-related -- Bare designation removals/updates list; referenced Alert and FAQ are not reproduced in the document itself. Quote (p.1): "The following deletions have been made to OFAC's SDN List:"
- `ofac:0868dd93bc51b8da` Counter Terrorism Designations -- Bare SDN designation list naming individuals/charities linked to Hamas financing; no description of the financing method itself. Quote (p.1): "The following entities have been added to OFAC's SDN List:"
- `ofac:94d34cd7226d01c2` Iran-related Designations and Designations Updates; Transnational Criminal Organizations Designation; Publication of Ira -- Bare SDN designation list of Iran-linked shell companies/individuals; no narrative of the evasion method. Quote (p.1): "The following entities have been added to OFAC's SDN List:"
- `ofac:dc63a1c2b84a58f7` Counter Terrorism and Transnational Criminal Organizations Designations; Belarus, Counter Narcotics, and Libya Designati -- Bare SDN designation/removal list for Tren de Aragua and other regimes; no narrative description of the bank-theft or laundering method. Quote (p.1): "Specially Designated Nationals List Updates The following individuals have been added to OFAC's SDN List:"
- `ofsi:bd73b8e3b0c6fcc2` Guidance: UK Financial Sanctions FAQs -- FAQ guidance update log; restates sanctions obligations/process without describing a method, red flag or case. Quote (p.1,2): "OFSI publishes FAQs providing short-form guidance and technical information on financial sanctions."
- `ofsi:5bf3cdb7659fe36b` Guidance: OFSI General Licence - INT/2026/11080040 -- Notice of a general licence permitting wind-down transactions; no typology content. Quote (p.1): "On 8 October 2026, OFSI issued General Licence INT/2026/11080040 under regulation 64 of The Russia (Sanctions) (EU Exit) Regulations 2019 (“the Russia Regulations”) which allows for Persons to wind do"
- `ofsi:1e49c49ca389ac5c` Guidance: OFSI General Licence INT/2026/8893924 -- Notice of an amended/extended general licence for insurance wind-down; no method or case described. Quote (p.1): "On 24 February 2026, OFSI issued General Licence INT/2026/8893924 under regulation 64 of the Russia (Sanctions) (EU Exit) Regulations 2019 (“the Russia Regulations”) which allows for the winding down "

## Unfinished: 1 (they return next Friday unless dropped)

- `ofac:528a733c96bd988a` Counter Narcotics, Counter Terrorism, Iran-related, and Non-Proliferation Designations: no verdict

## Extraction: 1 queued, 1 extracted, 0 failed, 0 deferred for budget

| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable | citations not on their page | cost |
|---|---|---|---|---|---|---|---|
| `ofac:67443fcb784dba53` | ADV-2026-0026 | extracted | 2 | 3 (0) | 0 of 4 | 0 of 8 | US$0.16 |

## Reconciliation: clean

| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |
|---|---|---|---|---|---|---|---|---|
| adv-2026-0026-extractor-3e5c8263f4 | extractor | SUCCESS | US$0.16 | 20 | 19 | 0 | 0 | 0 |
| feeds-2026-10-11-e7ad24 | orchestrator | SUCCESS | US$0.26 | 43 | 42 | 0 | 0 | 0 |

## Cost

US$0.42 counted against the US$5.00 ceiling (a session whose cost never arrived is counted at its cap); US$0.42 reported by the sessions' own telemetry.

## Next

`python tools/accept_run.py feeds-2026-10-11-e7ad24` -- accept, drop or defer each item.
