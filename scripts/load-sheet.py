from __future__ import annotations

import argparse
import sys

from sheet_cache import ROOT, add_google_sheet_args, download_sheet_cache


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download Google Sheet tabs into local CSV cache.")
    add_google_sheet_args(parser)
    args = parser.parse_args(argv)

    written = download_sheet_cache(args)
    for path in written:
        print(f"saved {path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"load-sheet failed: {error}", file=sys.stderr)
        raise
