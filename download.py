"""Download HDB datasets from data.gov.sg into data/raw/.

Files are named <name>_<YYYY-MM-DD>.csv, where the date is the download date.
Idempotent: a dataset already downloaded today is skipped unless --force.

Usage: python download.py [rental|resale ...] [--force]
"""

import argparse
import datetime as dt
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DATASETS = {
    "rental": "d_c9f57187485a850908655db0e8cfe651",  # Renting Out of Flats from Jan 2021
    "resale": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",  # Resale flat prices, registration date from Jan-2017
}
API = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/{action}"
RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
HEADERS = {"User-Agent": "hdb_analysis/0.1"}


def target_path(raw_dir: Path, name: str, day: dt.date) -> Path:
    return raw_dir / f"{name}_{day.isoformat()}.csv"


def retry_on_429(fn, *args, sleep=time.sleep, attempts: int = 5, wait: float = 15):
    """Anonymous data.gov.sg calls are rate-limited (HTTP 429). Back off linearly and retry."""
    for i in range(1, attempts + 1):
        try:
            return fn(*args)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == attempts:
                raise
            sleep(wait * i)


def _open_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _get_json(url: str) -> dict:
    body = retry_on_429(_open_json, url)
    if body.get("code") != 0:
        raise RuntimeError(f"data.gov.sg error for {url}: {body.get('errorMsg')}")
    return body["data"]


def _fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def resolve_url(dataset_id: str, get_json=_get_json, sleep=time.sleep, attempts: int = 10) -> str:
    """Ask data.gov.sg to prepare the CSV, then poll until it hands back a signed URL."""
    get_json(API.format(id=dataset_id, action="initiate-download"))
    for _ in range(attempts):
        data = get_json(API.format(id=dataset_id, action="poll-download"))
        if data.get("status") == "DOWNLOAD_SUCCESS":
            return data["url"]
        sleep(3)
    raise RuntimeError(f"{dataset_id}: download not ready after {attempts} polls")


def download(
    name: str,
    raw_dir: Path = RAW_DIR,
    today: dt.date | None = None,
    force: bool = False,
    get_json=_get_json,
    fetch=_fetch,
    sleep=time.sleep,
) -> tuple[Path, bool]:
    """Return (path, downloaded). downloaded is False when today's file already exists."""
    dest = target_path(raw_dir, name, today or dt.date.today())
    if dest.exists() and not force:
        return dest, False
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = resolve_url(DATASETS[name], get_json, sleep)
    tmp = dest.with_suffix(".csv.part")
    fetch(url, tmp)
    tmp.replace(dest)  # atomic: a crash never leaves a half-written <name>_<date>.csv
    return dest, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help=f"subset of {list(DATASETS)}; default all")
    parser.add_argument("--force", action="store_true", help="re-download even if today's file exists")
    args = parser.parse_args(argv)
    unknown = set(args.names) - set(DATASETS)
    if unknown:
        parser.error(f"unknown dataset(s): {sorted(unknown)}")
    for name in args.names or list(DATASETS):
        path, downloaded = download(name, force=args.force)
        status = "downloaded" if downloaded else "already present, skipped"
        print(f"{name}: {path.relative_to(RAW_DIR.parent.parent)} ({status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
