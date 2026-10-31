# Stack

## Language / framework

Python 3.13, venv at `.venv/`, pinned `requirements.txt`. DuckDB (in-memory) for all
analysis SQL, pandas for results, matplotlib for charts, Jupyter for the notebook.

## Setup

```
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` = runtime + dev-only gate tools (ruff, coverage, diff-cover); not analysis deps.

## Run

```
.venv/Scripts/python download.py          # idempotent, skips if today's file exists; --force to refetch
.venv/Scripts/python db.py                # row counts, schema, date range
.venv/Scripts/jupyter lab notebooks/01_rental.ipynb
```

## Test + lint

One entry point, also run by CI (`.github/workflows/ci.yml`) and the QA gate:

```
.venv/Scripts/python scripts/check.py [static|test|fix]
```

- `static`: `ruff format --check` + `ruff check` (line length 120, `notebooks/` excluded),
  test-hygiene (`.claude/testing.md` rules on test lines added vs `origin/main`).
- `test`: unittest under coverage, coverage.xml, then diff-cover ≥80% of lines changed vs
  `origin/main`. No slow-test budget (unittest writes no junit report).
- `fix`: apply ruff format + safe fixes. A workspace hook also does this on every edit.
- Single test: `.venv/Scripts/python -m unittest tests.test_db.<Class>.<test>`.

## Deploy

None. Public GitHub repo is the deliverable.

## Code map

`download.py` — dataset IDs, data.gov.sg initiate/poll download, writes `data/raw/<name>_<YYYY-MM-DD>.csv` atomically.
`db.py` — `connect()` loads newest raw CSV per dataset into DuckDB tables `rental`, `resale` with explicit types.
`notebooks/01_rental.ipynb` — Q1-Q4: SQL cell, chart cell (`save()` to `charts/`), finding.
`tests/` — unittest, no network (fake API, tmp CSVs).
`scripts/check.py` — check config (`check_core.Config`); `scripts/check_core.py` — check logic, generated from general_ai `_template`: do not edit.

## Conventions

- Dates: `rental.rent_approval_date` and `resale.month` are DATE, first of the month.
  Source has month granularity only. "Last N months" anchors on `max(date)` in the
  data, not on today.
- Flat type labels differ: rental `4-ROOM`, resale `4 ROOM`.
- `block` is VARCHAR (`627B` exists).
- Chart file names: `charts/q<N>_<slug>.png`.
