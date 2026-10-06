# HDB rental market analysis

What does it cost to rent an HDB flat in Singapore, where is it cheapest, and which
way is it moving? Four questions, answered in SQL (DuckDB) against official
government data.

## Data

[HDB Renting Out of Flats from Jan 2021](https://data.gov.sg/datasets/d_c9f57187485a850908655db0e8cfe651/view),
data.gov.sg, published by the Housing & Development Board. One row per approved
rental application: month, town, block, street, flat type, monthly rent. Rents are
owner-declared and not verified by HDB.

## Questions

1. Median monthly rent by town and flat type over the last 12 months. Which towns are cheapest for a given flat type?
2. How has median rent moved over the last 24-36 months, overall and in selected towns?
3. Within a town, how much does rent vary by flat type, and is the spread stable or widening?
4. Rent per room as a value measure: which town / flat-type combos give the best value?

## Key findings

(to come, one per question, with chart)

## How to run

Requires Python 3.13.

```
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python download.py
.venv/Scripts/python db.py
.venv/Scripts/jupyter lab notebooks/01_rental.ipynb
```

Every chart in `charts/` is exported by the notebook cell directly below the SQL that
produced it.

## Next

(to come)
