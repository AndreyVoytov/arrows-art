from __future__ import annotations

import sys

from run_pipeline import run_script


def main(argv: list[str] | None = None) -> None:
    args = argv or []
    run_script("prepare_rooms_pipeline.py", args)
    run_script("prepare_balance_local.py")
    run_script("build_atlases.py")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"prepare-all failed: {error}", file=sys.stderr)
        raise
