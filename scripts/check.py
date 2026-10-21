"""Every check this project runs. CI, the workspace QA gate and humans all call this file.

  python scripts/check.py           static, then test
  python scripts/check.py static    format, lint
  python scripts/check.py test      tests with coverage, then diff coverage
  python scripts/check.py fix       apply ruff format + safe ruff fixes, then exit

Stdlib only. Every tool runs with this interpreter (local .venv or CI python).
Exit 0 only when every step passed. Edit the CONFIG block per project.
Diff-coverage base: origin/main, moved past unpushed commits listed in
.git-blame-ignore-revs (style-only). CHECK_DIFF_BASE=<ref> overrides it.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# --- CONFIG ---------------------------------------------------------------
TARGETS = ["."]  # ruff format/check paths (notebooks excluded in pyproject)
DIFF_BASE = os.environ.get("CHECK_DIFF_BASE", "origin/main")
DIFF_FAIL_UNDER = 80  # % of changed lines covered
# ---------------------------------------------------------------------------


def tool(name):
    """Console script installed next to this interpreter (venv Scripts/ or bin/)."""
    found = shutil.which(name, path=str(Path(PY).parent))
    return found or name


STATIC = [
    ("format", [PY, "-m", "ruff", "format", "--check", *TARGETS]),
    ("lint", [PY, "-m", "ruff", "check", *TARGETS]),
]
TEST = [
    ("tests", [PY, "-m", "coverage", "run", "-m", "unittest", "discover", "tests"]),
    ("coverage-xml", [PY, "-m", "coverage", "xml", "-q"]),
]
FIX = [
    ("format", [PY, "-m", "ruff", "format", *TARGETS]),
    ("lint-fix", [PY, "-m", "ruff", "check", "--fix", *TARGETS]),
]


def has_ref(ref):
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=ROOT, capture_output=True)
    return r.returncode == 0


def git_ok(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def diff_base():
    """DIFF_BASE, moved past any unpushed style-only commit in .git-blame-ignore-revs."""
    if "CHECK_DIFF_BASE" in os.environ:
        return DIFF_BASE
    revs_file = ROOT / ".git-blame-ignore-revs"
    lines = revs_file.read_text(encoding="utf-8").splitlines() if revs_file.is_file() else []
    revs = [ln.split()[0] for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    base = DIFF_BASE
    for rev in revs:
        if (
            git_ok("merge-base", "--is-ancestor", rev, "HEAD")
            and git_ok("merge-base", "--is-ancestor", base, rev)
            and not git_ok("merge-base", "--is-ancestor", rev, base)
        ):
            base = rev
    return base


def diff_cover_step():
    if not has_ref(DIFF_BASE):
        return None  # shallow CI checkout: the local gate enforces it
    return (
        "diff-cover",
        [
            tool("diff-cover"),
            "coverage.xml",
            f"--compare-branch={diff_base()}",
            "--include-untracked",
            f"--fail-under={DIFF_FAIL_UNDER}",
        ],
    )


def run(steps):
    failed = []
    for name, argv in steps:
        print(f"== {name}", flush=True)
        r = subprocess.run(argv, cwd=ROOT)
        if r.returncode:
            failed.append(name)
    return failed


def main(argv):
    mode = argv[0] if argv else "all"
    if mode == "fix":
        run(FIX)
        return 0
    steps = []
    if mode in ("all", "static"):
        steps += STATIC
    if mode in ("all", "test"):
        steps += TEST
    if not steps:
        print(__doc__)
        return 2
    failed = run(steps)
    if mode in ("all", "test") and "tests" not in failed:
        step = diff_cover_step()
        if step:
            failed += run([step])
        else:
            print(f"== diff-cover skipped: no {DIFF_BASE} ref")
    print(f"check {mode}: {'FAIL ' + ', '.join(failed) if failed else 'OK'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
