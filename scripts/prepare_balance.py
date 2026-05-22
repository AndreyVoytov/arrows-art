from __future__ import annotations

import sys

from run_pipeline import run_script


def main(argv: list[str] | None = None) -> None:
    args = argv or []
    run_script("load-sheet.py", args)
    run_script("prepare_balance_local.py")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"prepare-balance failed: {error}", file=sys.stderr)
        raise
