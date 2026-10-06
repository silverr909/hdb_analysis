"""Load the latest raw CSVs from data/raw/ into an in-memory DuckDB connection.

Tables (types are explicit, nothing is sniffed):
  rental  rent_approval_date DATE (1st of the month), town, block, street_name,
          flat_type ('4-ROOM'), monthly_rent INTEGER
  resale  month DATE (1st of the month), town, flat_type ('4 ROOM'), block,
          street_name, storey_range, floor_area_sqm DOUBLE, flat_model,
          lease_commence_date INTEGER, remaining_lease, resale_price INTEGER

block stays VARCHAR on purpose: '627B' exists, and sniffing it as an integer
would silently drop the letter or fail on a later row.

Usage: python db.py   prints source file, row count, schema and date range per table.
"""

from pathlib import Path

import duckdb

RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"

# Raw columns read as text, cast below. Order matches the CSV header.
RAW_COLUMNS = {
    "rental": ["rent_approval_date", "town", "block", "street_name", "flat_type", "monthly_rent"],
    "resale": [
        "month", "town", "flat_type", "block", "street_name", "storey_range",
        "floor_area_sqm", "flat_model", "lease_commence_date", "remaining_lease", "resale_price",
    ],
}

SELECT = {
    "rental": """
        SELECT CAST(strptime(rent_approval_date, '%Y-%m') AS DATE) AS rent_approval_date,
               town, block, street_name, flat_type,
               CAST(monthly_rent AS INTEGER) AS monthly_rent
        FROM {src}
    """,
    "resale": """
        SELECT CAST(strptime(month, '%Y-%m') AS DATE) AS month,
               town, flat_type, block, street_name, storey_range,
               CAST(floor_area_sqm AS DOUBLE) AS floor_area_sqm,
               flat_model,
               CAST(lease_commence_date AS INTEGER) AS lease_commence_date,
               remaining_lease,
               CAST(resale_price AS INTEGER) AS resale_price
        FROM {src}
    """,
}

DATE_COLUMN = {"rental": "rent_approval_date", "resale": "month"}


def latest_csv(raw_dir: Path, name: str) -> Path:
    """Newest <name>_<YYYY-MM-DD>.csv. ISO dates sort correctly as strings."""
    files = sorted(raw_dir.glob(f"{name}_????-??-??.csv"))
    if not files:
        raise FileNotFoundError(f"no {name}_<date>.csv in {raw_dir}; run: python download.py {name}")
    return files[-1]


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def load_table(con: duckdb.DuckDBPyConnection, name: str, csv_path: Path) -> None:
    columns = "{" + ", ".join(f"{_sql_str(c)}: 'VARCHAR'" for c in RAW_COLUMNS[name]) + "}"
    src = f"read_csv({_sql_str(csv_path.as_posix())}, header = true, columns = {columns})"
    con.execute(f"CREATE OR REPLACE TABLE {name} AS {SELECT[name].format(src=src)}")


def connect(raw_dir: Path = RAW_DIR, tables: tuple[str, ...] = ("rental", "resale")) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one table per dataset, loaded from the newest raw CSV."""
    con = duckdb.connect()
    for name in tables:
        load_table(con, name, latest_csv(raw_dir, name))
    return con


def summary(con: duckdb.DuckDBPyConnection, raw_dir: Path = RAW_DIR) -> str:
    lines = []
    for name in RAW_COLUMNS:
        date_col = DATE_COLUMN[name]
        rows, first, last = con.execute(
            f"SELECT count(*), min({date_col}), max({date_col}) FROM {name}"
        ).fetchone()
        lines.append(f"== {name}  ({latest_csv(raw_dir, name).name})")
        lines.append(f"rows: {rows:,}   {date_col}: {first} .. {last}")
        for col, dtype, *_ in con.execute(f"DESCRIBE {name}").fetchall():
            lines.append(f"  {col:<22} {dtype}")
        flat_types = [r[0] for r in con.execute(f"SELECT DISTINCT flat_type FROM {name} ORDER BY 1").fetchall()]
        lines.append(f"  flat_type values: {flat_types}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(connect()))
