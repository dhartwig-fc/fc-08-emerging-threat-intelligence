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

Fetched 2026-10-31 through feeds.http.get (fc-08's own user agent), one request each:

| File | Source URL | Read by |
|---|---|---|
| `wolfsberg_news.html` | https://wolfsberg-group.org/news (The Wolfsberg Group) | `evals/check_feed_adapters.py` |
| `wolfsberg_item_rba.html` | https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach | `evals/check_document_hop.py` |
| `wolfsberg_resource_rba_205.html` | https://wolfsberg-group.org/resources/rba/205 | `evals/check_document_hop.py` |
