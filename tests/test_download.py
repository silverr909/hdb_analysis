import contextlib
import datetime as dt
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path

import download

DAY = dt.date(2026, 10, 6)


class FakeApi:
    """Stands in for data.gov.sg: poll returns 'pending' `pending` times, then success."""

    def __init__(self, pending: int = 0):
        self.pending = pending
        self.calls: list[str] = []
        self.fetched: list[str] = []

    def get_json(self, url: str) -> dict:
        self.calls.append(url)
        if url.endswith("initiate-download"):
            return {"message": "initiated"}
        if self.pending:
            self.pending -= 1
            return {"status": "DOWNLOAD_IN_PROGRESS"}
        return {"status": "DOWNLOAD_SUCCESS", "url": "https://s3.example/file.csv"}

    def fetch(self, url: str, dest: Path) -> None:
        self.fetched.append(url)
        dest.write_text("a,b\n1,2\n", encoding="utf-8")


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"

    def tearDown(self):
        self.tmp.cleanup()

    def run_download(self, api: FakeApi, **kw):
        return download.download(
            "rental", raw_dir=self.raw, today=DAY,
            get_json=api.get_json, fetch=api.fetch, sleep=lambda s: None, **kw,
        )

    def test_writes_dated_file_and_no_part_file(self):
        api = FakeApi()
        path, downloaded = self.run_download(api)
        self.assertTrue(downloaded)
        self.assertEqual(path.name, "rental_2026-10-06.csv")
        self.assertEqual(path.read_text(encoding="utf-8"), "a,b\n1,2\n")
        self.assertEqual([p.name for p in self.raw.iterdir()], ["rental_2026-10-06.csv"])
        self.assertIn(download.DATASETS["rental"], api.calls[0])

    def test_second_run_same_day_is_skipped(self):
        self.run_download(FakeApi())
        api = FakeApi()
        path, downloaded = self.run_download(api)
        self.assertFalse(downloaded)
        self.assertEqual(api.calls, [])
        self.assertEqual(api.fetched, [])

    def test_force_redownloads(self):
        self.run_download(FakeApi())
        api = FakeApi()
        _, downloaded = self.run_download(api, force=True)
        self.assertTrue(downloaded)
        self.assertEqual(len(api.fetched), 1)

    def test_polls_until_ready(self):
        api = FakeApi(pending=2)
        self.run_download(api)
        self.assertEqual(sum(u.endswith("poll-download") for u in api.calls), 3)

    def test_gives_up_after_max_polls(self):
        with self.assertRaises(RuntimeError):
            download.resolve_url("d_x", get_json=FakeApi(pending=99).get_json, sleep=lambda s: None, attempts=3)

    def test_unknown_dataset_name_rejected(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            download.main(["rentals"])


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", None, None)


class RetryTest(unittest.TestCase):
    def test_retries_429_then_succeeds(self):
        outcomes = [http_error(429), http_error(429), "ok"]
        waits = []

        def fn():
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return out

        self.assertEqual(download.retry_on_429(fn, sleep=waits.append, wait=1), "ok")
        self.assertEqual(waits, [1, 2])

    def test_gives_up_after_attempts(self):
        def fn():
            raise http_error(429)

        with self.assertRaises(urllib.error.HTTPError):
            download.retry_on_429(fn, sleep=lambda s: None, attempts=3)

    def test_other_http_errors_not_retried(self):
        calls = []

        def fn():
            calls.append(1)
            raise http_error(500)

        with self.assertRaises(urllib.error.HTTPError):
            download.retry_on_429(fn, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
