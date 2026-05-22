from __future__ import annotations

import sys

from prepare_rooms import main as prepare_rooms_main


def main(argv: list[str] | None = None) -> None:
    prepare_rooms_main(["--images-only", *(argv or [])])


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"extract-images-from-psd failed: {error}", file=sys.stderr)
        raise
