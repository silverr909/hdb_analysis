"""Every check this project runs: `python scripts/check.py [static|test|fix]`.

Config only. The logic lives in scripts/check_core.py, generated from
general_ai/_template/scripts/check_core.py by `sync.ps1 checks`: never edit it here.
Config keys and defaults: check_core.Config.
"""

import sys

import check_core

CONFIG = check_core.Config(
    targets=["."],
    runner="unittest",
    types=False,
    imports=False,
)

if __name__ == "__main__":
    sys.exit(check_core.main(CONFIG, sys.argv[1:]))
