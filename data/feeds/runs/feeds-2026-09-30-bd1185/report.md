# Friday run feeds-2026-09-30-bd1185: COMPLETE

5 new item(s), 2 kept, 3 dropped by triage, 2 extracted, 0 unfinished; US$1.02 spent of the US$5.00 ceiling.

## Sources

| source | status | listed | already decided | new |
|---|---|---|---|---|
| ofsi | ok | 20 | 18 | 2 |
| fincen | ok | 15 | 15 | 0 |
| ofac | ok | 10 | 7 | 3 |

## Kept by triage (relevant): 2

- `ofac:528a733c96bd988a` Counter Narcotics, Counter Terrorism, Iran-related, and Non-Proliferation Designations -- Designation action describing a Sinaloa Cartel corruption/money-laundering network using front businesses (entertainment promoters, real estate, casa de cambio) to launder proceeds. Quote (p.5): "GALERIAS CENTRO CAMBIARIO, S.A. DE C.V. (a.k.a. MAGIC CASA DE CAMBIO), Tijuana, Baja California, Mexico; ... Organization Type: Other financial service activities, except insurance and pension funding"
- `ofac:dc63a1c2b84a58f7` Counter Terrorism and Transnational Criminal Organizations Designations; Belarus, Counter Narcotics, and Libya Designati -- Designation action tied to a described case of theft of millions from U.S. banks by a Tren de Aragua financial network, listing digital currency (TRX) addresses used to move stolen funds. Quote (p.1): "Secondary sanctions risk: section 1(b) of Executive Order 13224, as amended by Executive Order 13886; Digital Currency Address - TRX TJjRAn9kLiyh8h6gjBjaYjkfDkskgZfyW9; Cedula No. V-13126628 (Venezuel"

## Dropped by triage (not relevant), with the reason and the quote: 3

- `ofac:ee1214479fbfe752` Publication of Regulatory Amendments; Publication of Cuba Sanctions Regulations; Issuance of New and Amended Cuba-relate -- Announces regulatory reorganization, new Cuba sanctions regulations, and FAQ issuance; procedural/regulatory notice without describing a method, red flag or case. Quote (p.1): "The Department of the Treasury's Office of Foreign Assets Control (OFAC) is issuing a rule removing duplicative regulatory provisions and reorganizing multiple parts within the Code of Federal Regulat"
- `ofsi:ce2f4cbd203e01ee` Guidance: Annual frozen asset review: guidance and reporting form -- Annual procedural reporting exercise notice for frozen asset holders; no methods, red flags or case detail. Quote (p.1): "The notice provides background and guidance for the 2026 frozen asset reporting exercise, which HM Treasury carries out every year to update our records to reflect any changes to accounts during the r"
- `ofsi:3e4b35d8597a4187` Guidance: UK Financial Sanctions FAQs -- FAQ guidance page listing procedural updates to licensing and definitions FAQs; restates obligations without describing a laundering/evasion method or case. Quote (p.1): "OFSI publishes FAQs providing short-form guidance and technical information on financial sanctions."

## Unfinished: 0 (they return next Friday unless dropped)

None.

## Extraction: 2 queued, 2 extracted, 0 failed, 0 deferred for budget

| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable | cost |
|---|---|---|---|---|---|---|
| `ofac:528a733c96bd988a` | ADV-2026-0021 | extracted | 1 | 10 (2) | 2 of 5 | US$0.41 |
| `ofac:dc63a1c2b84a58f7` | ADV-2026-0022 | extracted | 2 | 17 (0) | 0 of 17 | US$0.45 |

## Reconciliation: clean

| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |
|---|---|---|---|---|---|---|---|---|
| adv-2026-0021-extractor-e8fd77548f | extractor | SUCCESS | US$0.41 | 24 | 23 | 0 | 0 | 0 |
| adv-2026-0022-extractor-897e5288f9 | extractor | SUCCESS | US$0.45 | 42 | 41 | 0 | 0 | 1 |
| feeds-2026-09-30-bd1185 | orchestrator | SUCCESS | US$0.15 | 25 | 24 | 0 | 0 | 0 |

## Cost

US$1.02 counted against the US$5.00 ceiling (a session whose cost never arrived is counted at its cap); US$1.02 reported by the sessions' own telemetry.

## Next

`python tools/accept_run.py feeds-2026-09-30-bd1185` -- accept, drop or defer each item.
