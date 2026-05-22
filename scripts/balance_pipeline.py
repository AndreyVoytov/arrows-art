from __future__ import annotations

import re
from pathlib import Path

from export_google_sheets import (
    CONFIG_DIR,
    TEXT_SRC_DIR,
    build_level_rewards,
    build_objects_ru,
    build_rooms_ru,
    parse_dialog_rows,
    parse_equipment_rows,
    parse_level_rows,
    update_room_configs,
    write_json,
)
from sheet_cache import read_local_table, require_local_tables


RU_OUTPUT = TEXT_SRC_DIR / "ru.json"


def load_local_equipment() -> tuple[list[dict[str, object]], dict[str, str]]:
    return parse_equipment_rows(read_local_table("equipment"))


def load_filtered_equipment_from_local_sheet(room_filter: str | None = None) -> tuple[list[dict[str, object]], dict[str, str]]:
    equipment_items, rooms = load_local_equipment()
    return filter_equipment_by_rooms(equipment_items, rooms, room_filter)


def update_prices_from_local_sheet(room_filter: str | None = None) -> list[str]:
    require_local_tables(("equipment",))
    equipment_items, rooms = load_filtered_equipment_from_local_sheet(room_filter)

    room_configs = [
        path for path in CONFIG_DIR.glob("room*.json")
        if not path.name.endswith("_order.json")
    ]
    if room_filter is not None:
        allowed = room_ids_from_filter(room_filter)
        room_configs = [path for path in room_configs if path.stem in allowed]

    if not room_configs:
        raise SystemExit("No room config JSON files found to update")

    updated_rooms = update_room_configs(equipment_items, rooms)
    if not updated_rooms:
        raise SystemExit("No room config JSON files were updated from local sheet")

    print(f"updated room prices: {', '.join(updated_rooms)}")
    return updated_rooms


def prepare_balance_local() -> None:
    require_local_tables()

    equipment_items, rooms = load_local_equipment()
    level_rewards, levels_ru = parse_level_rows(read_local_table("levels"))
    dialogs_config, dialogs_ru = parse_dialog_rows(read_local_table("dialogs"))

    write_json(CONFIG_DIR / "level_rewards.json", build_level_rewards(level_rewards))
    write_json(CONFIG_DIR / "dialogs.json", dialogs_config)
    ru = build_ru(equipment_items, rooms, levels_ru, dialogs_ru)
    write_json(RU_OUTPUT, ru)

    room_configs = [
        path for path in CONFIG_DIR.glob("room*.json")
        if not path.name.endswith("_order.json")
    ]
    if not room_configs:
        raise SystemExit("No room config JSON files found to update")

    updated_rooms = update_room_configs(equipment_items, rooms)
    if not updated_rooms:
        raise SystemExit("No room config JSON files were updated from local sheet")

    print(f"updated room prices: {', '.join(updated_rooms)}")
    print(f"dialogs: {len(dialogs_config['dialogs'])}")
    print(f"level rewards: {len(level_rewards['levels'])}")
    print(f"ru localization keys: {len(ru)}")


def build_ru(
    equipment_items: list[dict[str, object]],
    rooms: dict[str, str],
    levels_ru: dict[str, str],
    dialogs_ru: dict[str, str],
) -> dict[str, str]:
    ru = {}
    ru.update(build_objects_ru(equipment_items))
    ru.update(build_rooms_ru(rooms))
    ru.update(levels_ru)
    ru.update(dialogs_ru)
    return dict(sorted(ru.items()))


def filter_equipment_by_rooms(
    equipment_items: list[dict[str, object]],
    rooms: dict[str, str],
    room_filter: str | None,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    if room_filter is None:
        return equipment_items, rooms

    allowed = room_ids_from_filter(room_filter)
    return (
        [item for item in equipment_items if str(item["roomId"]) in allowed],
        {room_id: room_name for room_id, room_name in rooms.items() if room_id in allowed},
    )


def room_ids_from_filter(room_filter: str) -> set[str]:
    return {f"room{number}" for number in parse_room_filter(room_filter) or set()}


def parse_room_filter(value: str | None) -> set[int] | None:
    if value is None:
        return None

    normalized = value.strip().lstrip("-")
    if not normalized:
        return None

    if re.fullmatch(r"\d+", normalized):
        return {int(normalized)}

    match = re.fullmatch(r"(\d+):(\d+)", normalized)
    if match is None:
        raise SystemExit(f"Invalid room filter: {value}")

    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        start, end = end, start

    return set(range(start, end + 1))


def normalize_room_filter_arg(argv: list[str]) -> str | None:
    for arg in argv:
        normalized = arg.strip().lstrip("-")
        if re.fullmatch(r"\d+(?::\d+)?", normalized):
            return normalized

    return None
