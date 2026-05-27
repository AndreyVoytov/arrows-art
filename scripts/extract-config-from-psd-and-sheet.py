from __future__ import annotations

import sys

from balance_pipeline import (
    normalize_room_filter_arg,
    update_dialogs_from_local_sheet,
    update_prices_from_local_sheet,
)
from prepare_rooms import main as prepare_rooms_main
from sheet_cache import require_local_tables


def main(argv: list[str] | None = None) -> None:
    args = argv or []
    room_filter = normalize_room_filter_arg(args)

    # Fail before touching generated room configs if the local sheet cache is absent.
    require_local_tables(("equipment", "dialogs"))
    prepare_rooms_main(["--config-only", *args])
    update_prices_from_local_sheet(room_filter)
    update_dialogs_from_local_sheet(room_filter)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"extract-config-from-psd-and-sheet failed: {error}", file=sys.stderr)
        raise
