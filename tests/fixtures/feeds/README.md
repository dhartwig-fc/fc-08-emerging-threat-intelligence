# Feed fixtures (slice 2, sub-project A)

Fetched 2026-09-26 with a descriptive user agent, one request each. Public government pages, kept
byte-for-byte because the guards pin their sha256; never edit them. A new snapshot is a new file
and a deliberate re-pin in the guard that reads it.

| File | Source URL | Read by |
|---|---|---|
| `ofsi.atom` | https://www.gov.uk/government/organisations/office-of-financial-sanctions-implementation.atom (GOV.UK, Open Government Licence v3.0) | `evals/check_feed_adapters.py`, `evals/check_feeds_server.py` |
| `fincen_advisories.html` | https://www.fincen.gov/resources/advisoriesbulletinsfact-sheets/advisories (US government work) | same |
| `ofac_recent_actions.html` | https://ofac.treasury.gov/recent-actions (US government work) | same |
| `../html/ofsi_uk_financial_sanctions_faqs.html` | https://www.gov.uk/government/publications/uk-financial-sanctions-faqs (GOV.UK, Open Government Licence v3.0) | `evals/check_html_pages.py`, `evals/check_feeds_server.py` |
