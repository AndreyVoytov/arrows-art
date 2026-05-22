from __future__ import annotations

import sys

from run_pipeline import run_script


def main(argv: list[str] | None = None) -> None:
    args = argv or []
    run_script("load-sheet.py")
    run_script("extract-images-from-psd.py", args)
    run_script("extract-config-from-psd-and-sheet.py", args)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"prepare-rooms failed: {error}", file=sys.stderr)
        raise
