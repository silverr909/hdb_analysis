# Stack

## Language / framework

Python 3.13, venv at `.venv/`, pinned `requirements.txt`. DuckDB (in-memory) for all
analysis SQL, pandas for results, matplotlib for charts, Jupyter for the notebook.

## Setup

```
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Run

```
.venv/Scripts/python download.py          # idempotent, skips if today's file exists; --force to refetch
.venv/Scripts/python db.py                # row counts, schema, date range
.venv/Scripts/jupyter lab notebooks/01_rental.ipynb
```

## Test

```
.venv/Scripts/python -m unittest discover tests
```

## Lint

None configured.

## Deploy

None. Public GitHub repo is the deliverable.

## Code map

`download.py` — dataset IDs, data.gov.sg initiate/poll download, writes `data/raw/<name>_<YYYY-MM-DD>.csv` atomically.
`db.py` — `connect()` loads newest raw CSV per dataset into DuckDB tables `rental`, `resale` with explicit types.
`notebooks/01_rental.ipynb` — Q1-Q4: SQL cell, chart cell (`save()` to `charts/`), finding.
`tests/` — unittest, no network (fake API, tmp CSVs).

## Conventions

- Dates: `rental.rent_approval_date` and `resale.month` are DATE, first of the month.
  Source has month granularity only. "Last N months" anchors on `max(date)` in the
  data, not on today.
- Flat type labels differ: rental `4-ROOM`, resale `4 ROOM`.
- `block` is VARCHAR (`627B` exists).
- Chart file names: `charts/q<N>_<slug>.png`.
