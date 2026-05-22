from __future__ import annotations

import sys

from balance_pipeline import normalize_room_filter_arg, update_prices_from_local_sheet


def main(argv: list[str] | None = None) -> None:
    update_prices_from_local_sheet(normalize_room_filter_arg(argv or []))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"update-prices-from-sheet failed: {error}", file=sys.stderr)
        raise
