# Charter

## Purpose

Answer four concrete questions about the Singapore HDB rental market from official
data, to inform the user's own rental decision (Dec 2026) and to serve as a SQL +
Python portfolio piece. Finished in 1-2 days. Not a platform.

## Scope

- Rental questions Q1-Q4 (listed in `README.md`), in order, in `notebooks/01_rental.ipynb`.
- Resale prices: loaded, not analysed until Q1-Q4 are done. Stretch goal only.

## Out of scope

- Any data source other than data.gov.sg. Never 99.co, PropertyGuru, Carousell, or any scraping.
- Dashboards, web apps, scheduled jobs, databases beyond in-memory DuckDB.

## Invariants

- Data comes from data.gov.sg only, via its official API or CSV download.
- The user writes the analysis SQL. The agent reviews it and flags mistakes. The agent
  writes analysis queries only when explicitly asked, and then explains each clause.
- Every chart and finding traces back to a SQL cell in the repo. Every PNG in `charts/`
  is produced by a `save()` call in the notebook.
- Interpretation text in the notebook and README is in the user's own words.
- Public-safe: no personal info, no credentials, nothing unfit to show an employer.
- Dependencies: pandas, duckdb, matplotlib, jupyter, stdlib. Anything else needs a
  stated reason.
