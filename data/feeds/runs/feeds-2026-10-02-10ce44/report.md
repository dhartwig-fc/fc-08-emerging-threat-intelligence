# Friday run feeds-2026-10-02-10ce44: COMPLETE

5 new item(s), 3 kept, 2 dropped by triage, 3 extracted, 0 unfinished; US$1.96 spent of the US$5.00 ceiling; 3 record(s) cite text not on the page named -- accept_run will refuse.

**CITATIONS: ofac:528a733c96bd988a ADV-2026-0023: 1 of 21 citation(s) are not on the page they name (first: indicators p4); accept_run will refuse this item -- defer or drop it**
**CITATIONS: ofac:dc63a1c2b84a58f7 ADV-2026-0024: 1 of 19 citation(s) are not on the page they name (first: actors p3); accept_run will refuse this item -- defer or drop it**
**CITATIONS: ofac:94d34cd7226d01c2 ADV-2026-0025: 26 of 46 citation(s) are not on the page they name (first: typologies p4); accept_run will refuse this item -- defer or drop it**

## Sources

| source | status | listed | already decided | new |
|---|---|---|---|---|
| ofsi | ok | 20 | 18 | 2 |
| fincen | ok | 15 | 15 | 0 |
| ofac | ok | 10 | 7 | 3 |

## Kept by triage (relevant): 3

- `ofac:528a733c96bd988a` Counter Narcotics, Counter Terrorism, Iran-related, and Non-Proliferation Designations -- Covers Sinaloa Cartel narco-corruption network in Baja California and Iranian military procurement network, describing illicit networks and corruption linkages that inform typologies. Quote (p.1): "Treasury Sanctions Sinaloa Cartel Leadership and Corruption Networks"
- `ofac:dc63a1c2b84a58f7` Counter Terrorism and Transnational Criminal Organizations Designations; Belarus, Counter Narcotics, and Libya Designati -- Press release describes a Tren de Aragua TCO financial network that stole millions from U.S. banks, with designees linked via crypto addresses, indicating a fraud/laundering typology. Quote (p.1): "Treasury Sanctions Financial Network of Foreign Terrorist Organization, Tren de Aragua, After Theft of Millions from U.S. Banks"
- `ofac:94d34cd7226d01c2` Iran-related Designations and Designations Updates; Transnational Criminal Organizations Designation; Publication of Ira -- Describes a sanctions evasion network used by Iran including shell companies in Hong Kong tied to specific individuals, giving typology-relevant structures and linkages. Quote (p.1): "Operation Economic Outcast Takes Unprecedented Action Against Sanctions Evasion Network Used by Iran"

## Dropped by triage (not relevant), with the reason and the quote: 2

- `ofsi:2a536bfa411d1703` Guidance: OFSI General licence INT/2025/5635700 -- General licence detail page listing scope and amendment history of an exempt-projects licence; no method, red flag, or case described. Quote (p.1): "On 10 January 2025, OFSI issued General Licence INT/2025/5635700 under regulation 64 of the Russia (Sanctions) (EU Exit) Regulations 2019"
- `ofsi:25f1f5c678b4baeb` Guidance: Maritime Services Ban and Oil Price Cap: licences and reporting forms -- Hub page listing general licences, reporting forms and links to guidance/advisory documents; the page itself only lists documents, does not describe methods or red flags. Quote (p.3): "General Licences and Reporting Forms GENERAL LICENCE – Oil Price Cap INT/2024/4423849"

## Unfinished: 0 (they return next Friday unless dropped)

None.

## Extraction: 3 queued, 3 extracted, 0 failed, 0 deferred for budget

| item | advisory id | status | proposals | resolver calls (resolved) | record actors resolvable | citations not on their page | cost |
|---|---|---|---|---|---|---|---|
| `ofac:528a733c96bd988a` | ADV-2026-0023 | extracted | 1 | 11 (2) | 2 of 11 | 1 of 21 | US$0.86 |
| `ofac:dc63a1c2b84a58f7` | ADV-2026-0024 | extracted | 2 | 11 (0) | 0 of 11 | 1 of 19 | US$0.36 |
| `ofac:94d34cd7226d01c2` | ADV-2026-0025 | extracted | 3 | 34 (0) | 0 of 34 | 26 of 46 | US$0.64 |

## Reconciliation: clean

| session | agent | status | cost | turns | calls | unterminated | duplicated | from transcript |
|---|---|---|---|---|---|---|---|---|
| adv-2026-0023-extractor-4b22b96178 | extractor | SUCCESS | US$0.86 | 40 | 39 | 0 | 0 | 0 |
| adv-2026-0024-extractor-9365d59054 | extractor | SUCCESS | US$0.36 | 36 | 35 | 0 | 0 | 0 |
| adv-2026-0025-extractor-8981040562 | extractor | SUCCESS | US$0.64 | 56 | 55 | 0 | 0 | 0 |
| feeds-2026-10-02-10ce44 | orchestrator | SUCCESS | US$0.10 | 24 | 23 | 0 | 0 | 0 |

## Cost

US$1.96 counted against the US$5.00 ceiling (a session whose cost never arrived is counted at its cap); US$1.96 reported by the sessions' own telemetry.

## Next

`python tools/accept_run.py feeds-2026-10-02-10ce44` -- accept, drop or defer each item.
