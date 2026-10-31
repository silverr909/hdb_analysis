# Generated from general_ai/_template/scripts/check_core.py by sync.ps1 checks. Do not edit.
"""Every check a project runs. CI, the workspace QA gate and humans call scripts/check.py,
which holds the project's Config and calls main() here.

  python scripts/check.py           static, then test
  python scripts/check.py static    format, lint, types, imports, test hygiene
  python scripts/check.py test      tests with coverage, extra tests, slow-test budget,
                                    diff coverage
  python scripts/check.py fix       apply ruff format + safe ruff fixes, then exit

Stdlib only. Every tool runs with this interpreter (local .venv or CI python), with
PYTHONIOENCODING=utf-8. Exit 0 only when every step passed.
Diff-coverage base: origin/main, moved past unpushed commits listed in
.git-blame-ignore-revs (style-only) that sit directly on top of it. CHECK_DIFF_BASE=<ref>
overrides it.
Test hygiene (`.claude/testing.md`) checks only test lines added vs that base.
Slow tests (pytest runner): over slow_test_s fails unless marked `@pytest.mark.slow`
(register the marker in pyproject `[tool.pytest.ini_options] markers`). Over budget in the
parallel run: re-run once serially, fails only if still over.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
RUNNERS = ("pytest", "unittest")


@dataclass(frozen=True)
class Tool:
    """Extra test step. argv[0] is resolved on PATH; a missing exe or `requires` path (under
    ROOT) fails the step with `hint`, never skips it."""

    name: str
    argv: list[str]
    requires: list[str] = field(default_factory=list)
    hint: str = ""


@dataclass(frozen=True)
class Config:
    targets: list[str] = field(default_factory=lambda: ["src", "tests"])  # ruff paths
    package: str | None = None  # pytest --cov=<package>; None: bare --cov (coverage config)
    test_dir: str = "tests"
    runner: str = "pytest"  # or "unittest": coverage run -m unittest discover -s test_dir
    types: bool = True  # mypy
    imports: bool = True  # lint-imports
    diff_fail_under: int = 80  # % of changed lines covered
    slow_test_s: float = 5.0  # call phase of one test (fixture setup not counted)
    extra_tests: list[Tool] = field(default_factory=list)  # after tests, before slow-tests

    def __post_init__(self) -> None:
        if self.runner not in RUNNERS:
            raise ValueError(f"runner must be one of {RUNNERS}, got {self.runner!r}")


CFG = Config()
DIFF_BASE = os.environ.get("CHECK_DIFF_BASE", "origin/main")
JUNIT = ROOT / ".pytest_cache" / "check-junit.xml"
# Spec or finding ids in test names/comments: test_ac12_x, test_q3_x, QaFixTest, # QA 5.
ID_NAME = re.compile(r"(?:^|_)(?:ac|qa|q|audit|finding|round)\d+(?:_|$)|qa_?fix", re.I)
DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)")
ID_COMMENT = re.compile(r"#.*?(?:\b(?:QA|Q|AC)[ -]?\d|\b(?i:qa|audit|finding)\b[ -]+\w*\d)")
# Real sleeps only: `sleep(`, `time.sleep(`, `asyncio.sleep(`; a fake `clock.sleep(` is fine.
SLEEP = re.compile(r"(?<![\w.])(?:time\.|asyncio\.)?sleep\(\s*(\d+(?:\.\d+)?)\s*[,)]")
SLEEP_MAX = 0.5


def tool(name):
    """Console script installed next to this interpreter (venv Scripts/ or bin/)."""
    found = shutil.which(name, path=str(Path(PY).parent))
    return found or name


def has_module(name):
    return importlib.util.find_spec(name) is not None


def pytest_args():
    xdist = ["-n", "auto"] if has_module("xdist") else []
    JUNIT.parent.mkdir(exist_ok=True)
    JUNIT.unlink(missing_ok=True)
    cov = f"--cov={CFG.package}" if CFG.package else "--cov"
    # Call phase only: a shared fixture's setup lands on whichever test uses it first.
    return [PY, "-m", "pytest", "-q", *xdist, "--tb=line", f"--junitxml={JUNIT}",
            "-o", "junit_duration_report=call", cov, "--cov-report=xml"]


def tool_step(t):
    """Step of an extra Tool: its argv with argv[0] resolved, or rc 1 when something is
    missing."""

    def step():
        exe = shutil.which(t.argv[0])
        missing = [t.argv[0]] if exe is None else []
        missing += [p for p in t.requires if not (ROOT / p).exists()]
        if missing:
            print(f"{t.name}: {', '.join(missing)} missing: {t.hint}")
            return 1
        return [exe, *t.argv[1:]]

    return step


def has_ref(ref):
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref], cwd=ROOT, capture_output=True
    )
    return r.returncode == 0


def git_ok(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def git_out(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout


def rev_parse(ref):
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref], cwd=ROOT, capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else None


def diff_base():
    """DIFF_BASE, moved past unpushed style-only commits in .git-blame-ignore-revs, but only
    while each sits directly on top of the base: a feature commit before a style commit stays
    in the diff."""
    if "CHECK_DIFF_BASE" in os.environ:
        return DIFF_BASE
    revs_file = ROOT / ".git-blame-ignore-revs"
    lines = revs_file.read_text(encoding="utf-8").splitlines() if revs_file.is_file() else []
    revs = [ln.split()[0] for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    children = {}  # first parent -> [style rev]; missing revs are dropped
    if revs:
        r = subprocess.run(["git", "rev-list", "--no-walk", "--parents", "--ignore-missing",
                            "--stdin"], cwd=ROOT, input="\n".join(revs) + "\n",
                           capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            rev, *parents = ln.split()
            if parents:
                children.setdefault(parents[0], []).append(rev)
    base = DIFF_BASE
    head = rev_parse(base)
    while True:
        nxt = next((rev for rev in children.get(head, [])
                    if git_ok("merge-base", "--is-ancestor", rev, "HEAD")), None)
        if nxt is None:
            return base
        base = head = nxt


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
            f"--fail-under={CFG.diff_fail_under}",
        ],
    )


def added_lines():
    """{test .py path: set of added line numbers, or None = whole file (untracked)}."""
    out = {}
    path = None
    test_dir = CFG.test_dir
    for line in git_out("diff", "-U0", "--no-color", diff_base(), "--", test_dir).splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and path:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
            out.setdefault(path, set()).update(range(start, start + count))
    for p in git_out("ls-files", "--others", "--exclude-standard", "--", test_dir).split():
        out[p] = None
    return {p: v for p, v in out.items() if p.endswith(".py") and (ROOT / p).is_file()}


def in_code(text, pos):
    """`pos` is outside string quotes (one-line heuristic)."""
    quote = None
    for ch in text[:pos]:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
    return quote is None


def line_problems(text):
    """Test-hygiene problems of one added line. Text inside string literals is data."""
    found = []
    m = DEF.match(text)
    if m and ID_NAME.search(m[1]):
        found.append(f"id in name `{m[1]}`: name the behavior")
    hashes = [i for i, ch in enumerate(text) if ch == "#" and in_code(text, i)]
    if any(ID_COMMENT.match(text, i) for i in hashes[:1]):
        found.append("spec/finding id in a comment")
    for m in SLEEP.finditer(text):
        if in_code(text, m.start()) and float(m[1]) >= SLEEP_MAX:
            found.append(f"real sleep({m[1]}): inject the clock or patch the timeout")
            break
    return found


def private_access(paths):
    """{(path, line)} of ruff SLF001 hits in `paths`."""
    if not paths:
        return set()
    r = subprocess.run([PY, "-m", "ruff", "check", "--select", "SLF001", "--output-format",
                        "json", "--exit-zero", "--no-cache", *paths],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    hits = set()
    for item in json.loads(r.stdout or "[]"):
        rel = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
        hits.add((rel, item["location"]["row"]))
    return hits


def test_hygiene():
    """Return code: 1 if any added test line breaks a `.claude/testing.md` machine rule."""
    if not has_ref(DIFF_BASE):
        print(f"skipped: no {DIFF_BASE} ref")
        return 0
    added = added_lines()
    problems = []
    for path, lines in sorted(added.items()):
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()
        for n, line in enumerate(text, 1):
            if lines is None or n in lines:
                problems += [f"{path}:{n}: {p}" for p in line_problems(line)]
    for path, n in sorted(private_access(sorted(added))):
        if added[path] is None or n in added[path]:
            problems.append(f"{path}:{n}: private member access (SLF001): test the public API")
    print("\n".join(problems) or "OK")
    return 1 if problems else 0


def node_key(nodeid):
    """`tests/a/test_x.py::Cls::test_y[p]` -> ('tests.a.test_x.Cls', 'test_y[p]') (junit)."""
    parts = nodeid.split("::")
    module = parts[0].removesuffix(".py").replace("/", ".")
    return ".".join([module, *parts[1:-1]]), parts[-1]


def node_id(classname, name):
    """Junit ('tests.a.test_x.Cls', 'test_y[p]') -> 'tests/a/test_x.py::Cls::test_y[p]', or
    None when no test file under ROOT matches."""
    parts = classname.split(".")
    for i in range(len(parts), 0, -1):
        path = "/".join(parts[:i]) + ".py"
        if (ROOT / path).is_file():
            return "::".join([path, *parts[i:], name])
    return None


def junit_times(path):
    """{(classname, name): call seconds} of a junit report; {} when missing or broken."""
    try:
        cases = ET.parse(path).iter("testcase")
        return {(tc.get("classname", ""), tc.get("name", "")): float(tc.get("time") or 0)
                for tc in cases}
    except (OSError, ET.ParseError):
        return {}


def serial_times(keys):
    """Call seconds of `keys` re-run once, serially, in one pytest process without coverage."""
    rerun = JUNIT.with_name("check-junit-serial.xml")
    rerun.unlink(missing_ok=True)
    ids = [i for i in (node_id(*k) for k in keys) if i]
    if not ids:
        return {}
    serial = ["-n", "0"] if has_module("xdist") else []
    no_random = ["-p", "no:randomly"] if has_module("pytest_randomly") else []
    no_cov = ["--no-cov"] if has_module("pytest_cov") else []
    subprocess.run([PY, "-m", "pytest", "-q", "--tb=no", *serial, *no_random, *no_cov,
                    f"--junitxml={rerun}", "-o", "junit_duration_report=call", *ids],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return junit_times(rerun)


def slow_tests():
    """Return code: 1 if a test not marked slow ran over slow_test_s, also when re-run serially
    (a parallel run on a loaded machine alone does not fail)."""
    if CFG.runner == "unittest":
        print("skipped: unittest runner writes no junit report")
        return 0
    if os.environ.get("CI"):
        print("skipped: CI runner timing (the local gate enforces it)")
        return 0
    if not JUNIT.is_file():
        print("skipped: no junit report")
        return 0
    budget = CFG.slow_test_s
    slow = sorted(((t, key) for key, t in junit_times(JUNIT).items() if t > budget),
                  reverse=True)
    if not slow:
        print("OK")
        return 0
    no_cov = ["--no-cov"] if has_module("pytest_cov") else []
    listed = subprocess.run([PY, "-m", "pytest", "--collect-only", "-q", "-m", "slow", *no_cov],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    marked = {node_key(ln.strip()) for ln in listed.splitlines() if "::" in ln}
    over = [(t, key) for t, key in slow if key not in marked]
    serial = serial_times([key for _, key in over]) if over else {}
    failed = 0
    for t, key in over:
        s = serial.get(key)
        still = s is None or s > budget
        failed += still
        verdict = (f"over {budget}s, speed it up or mark it slow" if still
                   else "under budget serially: machine load, passed")
        times = f"{t:.1f}s parallel, " + ("no serial result" if s is None else f"{s:.1f}s serial")
        print(f"{times}: {key[0]}::{key[1]}: {verdict}")
    print(f"{failed} slow test(s)" if failed else "OK")
    return 1 if failed else 0


def static_steps():
    steps = [
        ("format", [PY, "-m", "ruff", "format", "--check", *CFG.targets]),
        ("lint", [PY, "-m", "ruff", "check", *CFG.targets]),
    ]
    if CFG.types:
        steps.append(("types", [PY, "-m", "mypy"]))
    if CFG.imports:
        steps.append(("imports", [tool("lint-imports")]))
    steps.append(("test-hygiene", test_hygiene))
    return steps


def test_steps():
    if CFG.runner == "unittest":
        steps = [
            ("tests", [PY, "-m", "coverage", "run", "-m", "unittest", "discover",
                       "-s", CFG.test_dir]),
            ("coverage-xml", [PY, "-m", "coverage", "xml", "-q"]),
        ]
    else:
        steps = [("tests", pytest_args)]
    steps += [(t.name, tool_step(t)) for t in CFG.extra_tests]
    steps.append(("slow-tests", slow_tests))
    return steps


def fix_steps():
    return [
        ("format", [PY, "-m", "ruff", "format", *CFG.targets]),
        ("lint-fix", [PY, "-m", "ruff", "check", "--fix", *CFG.targets]),
    ]


def run(steps):
    """A step is an argv list, a function returning an argv list, or a check returning rc.
    Every subprocess step runs with PYTHONIOENCODING=utf-8."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    failed = []
    for name, step in steps:
        print(f"== {name}", flush=True)
        if callable(step):
            step = step()
        rc = step if isinstance(step, int) else subprocess.run(step, cwd=ROOT, env=env).returncode
        if rc:
            failed.append(name)
    return failed


def main(config: Config, argv: list[str]) -> int:
    global CFG
    CFG = config
    mode = argv[0] if argv else "all"
    if mode == "fix":
        return 1 if run(fix_steps()) else 0
    steps: list = []
    if mode in ("all", "static"):
        steps += static_steps()
    if mode in ("all", "test"):
        steps += test_steps()
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
