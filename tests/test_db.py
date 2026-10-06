import datetime as dt
import tempfile
import unittest
from pathlib import Path

import db

RENTAL_CSV = """rent_approval_date,town,block,street_name,flat_type,monthly_rent
2021-01,ANG MO KIO,105,ANG MO KIO AVE 4,4-ROOM,2000
2026-09,TAMPINES,627B,TAMPINES ST 61,4-ROOM,3500
"""
RESALE_CSV = """month,town,flat_type,block,street_name,storey_range,floor_area_sqm,flat_model,lease_commence_date,remaining_lease,resale_price
2017-01,ANG MO KIO,2 ROOM,406,ANG MO KIO AVE 10,10 TO 12,44,Improved,1979,61 years 04 months,232000
"""


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)
        (self.raw / "rental_2026-10-06.csv").write_text(RENTAL_CSV, encoding="utf-8")
        (self.raw / "resale_2026-10-06.csv").write_text(RESALE_CSV, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rental_types_and_values(self):
        con = db.connect(self.raw)
        types = dict((r[0], r[1]) for r in con.execute("DESCRIBE rental").fetchall())
        self.assertEqual(types["rent_approval_date"], "DATE")
        self.assertEqual(types["block"], "VARCHAR")
        self.assertEqual(types["monthly_rent"], "INTEGER")
        rows = con.execute("SELECT rent_approval_date, block, monthly_rent FROM rental ORDER BY 1").fetchall()
        self.assertEqual(rows, [(dt.date(2021, 1, 1), "105", 2000), (dt.date(2026, 9, 1), "627B", 3500)])

    def test_resale_types(self):
        con = db.connect(self.raw)
        row = con.execute("SELECT month, floor_area_sqm, lease_commence_date, resale_price FROM resale").fetchone()
        self.assertEqual(row, (dt.date(2017, 1, 1), 44.0, 1979, 232000))

    def test_latest_csv_picks_newest_date(self):
        (self.raw / "rental_2026-09-30.csv").write_text(RENTAL_CSV, encoding="utf-8")
        (self.raw / "rental_2026-10-06.csv.part").write_text("junk", encoding="utf-8")
        self.assertEqual(db.latest_csv(self.raw, "rental").name, "rental_2026-10-06.csv")

    def test_missing_file_names_the_fix(self):
        with self.assertRaisesRegex(FileNotFoundError, "download.py rental"):
            db.latest_csv(self.raw / "empty", "rental")

    def test_bad_rent_fails_loudly(self):
        (self.raw / "rental_2026-10-07.csv").write_text(RENTAL_CSV + "2026-09,BEDOK,1,X,3-ROOM,n/a\n", encoding="utf-8")
        with self.assertRaises(Exception):
            db.connect(self.raw, tables=("rental",))

    def test_summary_lists_both_tables(self):
        out = db.summary(db.connect(self.raw), self.raw)
        self.assertIn("rows: 2", out)
        self.assertIn("'4-ROOM'", out)
        self.assertIn("== resale", out)


if __name__ == "__main__":
    unittest.main()
