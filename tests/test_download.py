import contextlib
import datetime as dt
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import download

DAY = dt.date(2026, 10, 6)
SIGNED_URL = "https://s3.example/file.csv"
CSV = b"a,b\n1,2\n"


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
        return {"status": "DOWNLOAD_SUCCESS", "url": SIGNED_URL}

    def fetch(self, url: str, dest: Path) -> None:
        self.fetched.append(url)
        dest.write_text("a,b\n1,2\n", encoding="utf-8")


def fake_urlopen(api_body: dict):
    """Patch for urllib.request.urlopen: every API call returns `api_body`, the signed URL returns CSV."""
    poll_ok = {"code": 0, "data": {"status": "DOWNLOAD_SUCCESS", "url": SIGNED_URL}}

    def urlopen(req, timeout):
        if req.full_url == SIGNED_URL:
            return io.BytesIO(CSV)
        body = poll_ok if req.full_url.endswith("poll-download") else api_body
        return io.BytesIO(json.dumps(body).encode())

    return mock.patch("urllib.request.urlopen", urlopen)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "data" / "raw"

    def tearDown(self):
        self.tmp.cleanup()

    def run_download(self, api: FakeApi, **kw):
        args = {
            "raw_dir": self.raw,
            "today": DAY,
            "get_json": api.get_json,
            "fetch": api.fetch,
            "sleep": lambda s: None,
        }
        return download.download("rental", **(args | kw))

    def test_download_writes_dated_file_only_after_fetch_completes(self):
        def broken_fetch(url, dest):
            dest.write_bytes(b"a,b\n1,")
            raise ConnectionResetError("dropped")

        api = FakeApi()
        with self.assertRaises(ConnectionResetError):
            self.run_download(api, fetch=broken_fetch)
        self.assertFalse(download.target_path(self.raw, "rental", DAY).exists())

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

    def test_download_over_http_unwraps_data_or_raises_api_error(self):
        cases = [
            ("ok", {"code": 0, "data": {"message": "initiated"}}, None),
            ("api error", {"code": 1, "errorMsg": "bad id"}, "bad id"),
        ]
        for label, initiate_body, error in cases:
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp, fake_urlopen(initiate_body):
                raw = Path(tmp)
                if error:
                    with self.assertRaisesRegex(RuntimeError, error):
                        download.download("rental", raw_dir=raw, today=DAY, sleep=lambda s: None)
                    self.assertEqual(list(raw.iterdir()), [])
                else:
                    path, downloaded = download.download("rental", raw_dir=raw, today=DAY, sleep=lambda s: None)
                    self.assertTrue(downloaded)
                    self.assertEqual(path.read_bytes(), CSV)

    def test_resolve_url_polls_until_ready_or_gives_up(self):
        cases = [
            ("ready after 2 pending", 2, 10, None),
            ("never ready", 99, 3, "3 polls"),
        ]
        for label, pending, attempts, error in cases:
            with self.subTest(label):
                api = FakeApi(pending=pending)
                kw = {"get_json": api.get_json, "sleep": lambda s: None, "attempts": attempts}
                if error:
                    with self.assertRaisesRegex(RuntimeError, error):
                        download.resolve_url("d_x", **kw)
                else:
                    self.assertEqual(download.resolve_url("d_x", **kw), SIGNED_URL)
                self.assertEqual(sum(u.endswith("poll-download") for u in api.calls), 3)

    def test_main_downloads_all_datasets_by_default(self):
        with (
            mock.patch.object(download, "RAW_DIR", self.raw),
            fake_urlopen({"code": 0, "data": {"message": "initiated"}}),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(download.main([]), 0)
        for name in download.DATASETS:
            self.assertEqual(len(list(self.raw.glob(f"{name}_????-??-??.csv"))), 1, name)
        self.assertEqual(out.getvalue().count("(downloaded)"), len(download.DATASETS))

    def test_unknown_dataset_name_rejected(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            download.main(["rentals"])


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", None, None)


class Scripted:
    """Callable that returns or raises (HTTP status int) the next outcome, counting calls."""

    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, int):
            raise http_error(out)
        return out


class RetryTest(unittest.TestCase):
    def test_retry_on_429_backs_off_then_succeeds_or_raises(self):
        cases = [
            ("429 twice then ok", [429, 429, "ok"], 5, "ok", 3, [1, 2]),
            ("429 until attempts run out", [429, 429, 429], 3, None, 3, [1, 2]),
            ("non-429 error", [500, "ok"], 5, None, 1, []),
        ]
        for label, outcomes, attempts, expected, calls, waits in cases:
            with self.subTest(label):
                fn, slept = Scripted(outcomes), []
                kw = {"sleep": slept.append, "attempts": attempts, "wait": 1}
                if expected is None:
                    with self.assertRaises(urllib.error.HTTPError):
                        download.retry_on_429(fn, **kw)
                else:
                    self.assertEqual(download.retry_on_429(fn, **kw), expected)
                self.assertEqual(fn.calls, calls)
                self.assertEqual(slept, waits)


if __name__ == "__main__":
    unittest.main()
