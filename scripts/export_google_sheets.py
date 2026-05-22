from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from urllib.parse import quote
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
TEXT_TEMP_DIR = CONFIG_DIR / "text" / "temp"

DEFAULT_LEVEL_REWARDS_OUTPUT = CONFIG_DIR / "level_rewards.json"
DEFAULT_DIALOGS_OUTPUT = CONFIG_DIR / "dialogs.json"
DEFAULT_RU_OUTPUT = TEXT_TEMP_DIR / "ru.json"
DEFAULT_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "11iMe9LPLHdsm9DpV66A9HJhyzm37fpf3KdmCBJ3d6HE/edit?usp=sharing"
)

GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    equipment_rows = read_table(
        csv_path=args.equipment_csv,
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.equipment_sheet,
        value_range=args.equipment_range,
        credentials_path=args.credentials,
        api_key=args.api_key,
    )
    level_rows = read_table(
        csv_path=args.levels_csv,
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.levels_sheet,
        value_range=args.levels_range,
        credentials_path=args.credentials,
        api_key=args.api_key,
    )
    dialog_rows = read_optional_table(
        csv_path=args.dialogs_csv,
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.dialogs_sheet,
        value_range=args.dialogs_range,
        credentials_path=args.credentials,
        api_key=args.api_key,
        label="dialogs",
    )

    equipment_items, rooms = parse_equipment_rows(equipment_rows)
    level_rewards, levels_ru = parse_level_rows(level_rows)
    dialogs_config, dialogs_ru = parse_dialog_rows(dialog_rows)

    write_json(args.level_rewards_output, build_level_rewards(level_rewards))
    write_json(args.dialogs_output, dialogs_config)
    write_json(args.ru_output, build_ru(equipment_items, rooms, levels_ru, dialogs_ru))
    if not args.skip_room_config_update:
        update_room_configs(equipment_items, rooms)

    print(f"equipment: {len(equipment_items)} items")
    print(f"level rewards: {len(level_rewards['levels'])} levels")
    print(f"dialogs: {len(dialogs_config['dialogs'])} dialogs")
    print(f"rooms: {len(rooms)} rooms")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Google Sheets balance/localization data into game configs."
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=(
            os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
            or os.environ.get("GOOGLE_SHEETS_SPREADSHEET_URL")
            or DEFAULT_SPREADSHEET_URL
        ),
        help=(
            "Google Spreadsheet id or URL. Can also be set with "
            "GOOGLE_SHEETS_SPREADSHEET_ID or GOOGLE_SHEETS_SPREADSHEET_URL."
        ),
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        help="Path to a Google service account JSON file.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GOOGLE_API_KEY"),
        help="Google API key for public sheets.",
    )
    parser.add_argument(
        "--equipment-sheet",
        default=os.environ.get("EQUIPMENT_SHEET_NAME", "Equipment"),
        help="Sheet/tab name with Room_ID, Room_name, Object_ID, Object_name, Price1..3.",
    )
    parser.add_argument(
        "--levels-sheet",
        default=os.environ.get("LEVEL_REWARDS_SHEET_NAME", "Levels"),
        help="Sheet/tab name with Level, Compexity/Complexity, Award, Bonus_hint.",
    )
    parser.add_argument(
        "--dialogs-sheet",
        default=os.environ.get("DIALOGS_SHEET_NAME", "dialogs"),
        help=(
            "Sheet/tab name with Room_ID, Dialog_ID, Replica_ID, Position, "
            "Portrait, Text, Character_ID, Character_name, Character_portrait."
        ),
    )
    parser.add_argument(
        "--equipment-range",
        default=os.environ.get("EQUIPMENT_SHEET_RANGE"),
        help="Optional A1 range for equipment, for example Equipment!A:G.",
    )
    parser.add_argument(
        "--levels-range",
        default=os.environ.get("LEVEL_REWARDS_SHEET_RANGE"),
        help="Optional A1 range for levels, for example Levels!A:D.",
    )
    parser.add_argument(
        "--dialogs-range",
        default=os.environ.get("DIALOGS_SHEET_RANGE"),
        help="Optional A1 range for dialogs, for example dialogs!A:J.",
    )
    parser.add_argument(
        "--equipment-csv",
        type=Path,
        help="Local CSV fallback for equipment sheet.",
    )
    parser.add_argument(
        "--levels-csv",
        type=Path,
        help="Local CSV fallback for level rewards sheet.",
    )
    parser.add_argument(
        "--dialogs-csv",
        type=Path,
        help="Local CSV fallback for dialogs sheet.",
    )
    parser.add_argument(
        "--level-rewards-output",
        type=Path,
        default=DEFAULT_LEVEL_REWARDS_OUTPUT,
    )
    parser.add_argument(
        "--dialogs-output",
        type=Path,
        default=DEFAULT_DIALOGS_OUTPUT,
    )
    parser.add_argument(
        "--ru-output",
        type=Path,
        default=DEFAULT_RU_OUTPUT,
    )
    parser.add_argument(
        "--skip-room-config-update",
        action="store_true",
        help="Do not update config/room*.json while exporting sheet data.",
    )
    args = parser.parse_args(argv)
    args.spreadsheet_id = extract_spreadsheet_id(args.spreadsheet_id)

    if args.equipment_csv is None or args.levels_csv is None:
        if not args.spreadsheet_id:
            raise SystemExit(
                "Provide --spreadsheet-id or both --equipment-csv and --levels-csv."
            )

    return args


def extract_spreadsheet_id(value: str | None) -> str:
    raw = normalize_cell(value)
    if not raw:
        return ""

    match = re.search(r"/spreadsheets/d/([^/?#]+)", raw)
    if match:
        return match.group(1)

    return raw


def read_table(
    *,
    csv_path: Path | None,
    spreadsheet_id: str | None,
    sheet_name: str,
    value_range: str | None,
    credentials_path: str | None,
    api_key: str | None,
) -> list[dict[str, str]]:
    if csv_path is not None:
        return read_csv_table(resolve_path(csv_path))

    values = read_google_values(
        spreadsheet_id=spreadsheet_id or "",
        sheet_name=sheet_name,
        value_range=value_range,
        credentials_path=credentials_path,
        api_key=api_key,
    )
    return values_to_dicts(values)


def read_optional_table(
    *,
    csv_path: Path | None,
    spreadsheet_id: str | None,
    sheet_name: str,
    value_range: str | None,
    credentials_path: str | None,
    api_key: str | None,
    label: str,
) -> list[dict[str, str]]:
    if csv_path is None and not spreadsheet_id:
        return []

    try:
        return read_table(
            csv_path=csv_path,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            value_range=value_range,
            credentials_path=credentials_path,
            api_key=api_key,
        )
    except Exception as error:
        warn(f"{label} table skipped: {error}")
        return []


def read_csv_table(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return values_to_dicts([list(row) for row in csv.reader(file)])


def read_google_values(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    value_range: str | None,
    credentials_path: str | None,
    api_key: str | None,
) -> list[list[str]]:
    if credentials_path:
        return read_google_values_with_service_account(
            spreadsheet_id=spreadsheet_id,
            value_range=value_range or quoted_range(sheet_name),
            credentials_path=credentials_path,
        )

    if api_key:
        return read_google_values_with_api_key(
            spreadsheet_id=spreadsheet_id,
            value_range=value_range or quoted_range(sheet_name),
            api_key=api_key,
        )

    return read_public_google_csv(spreadsheet_id, sheet_name)


def read_google_values_with_service_account(
    *,
    spreadsheet_id: str,
    value_range: str,
    credentials_path: str,
) -> list[list[str]]:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as error:
        raise SystemExit(
            "Install Google client packages first: "
            "pip install google-api-python-client google-auth"
        ) from error

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=[GOOGLE_SHEETS_SCOPE],
    )
    service = build("sheets", "v4", credentials=credentials)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=value_range)
        .execute()
    )
    return result.get("values", [])


def read_google_values_with_api_key(
    *,
    spreadsheet_id: str,
    value_range: str,
    api_key: str,
) -> list[list[str]]:
    url = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        f"{quote(spreadsheet_id)}/values/{quote(value_range, safe='!')}"
        f"?key={quote(api_key)}"
    )
    with urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data.get("values", [])


def read_public_google_csv(spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
    url = (
        f"https://docs.google.com/spreadsheets/d/{quote(spreadsheet_id)}"
        f"/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}"
    )
    with urlopen(url) as response:
        text = response.read().decode("utf-8-sig")

    rows = csv.reader(text.splitlines())
    return [list(row) for row in rows]


def quoted_range(sheet_name: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!A:Z"


def values_to_dicts(values: list[list[str]]) -> list[dict[str, str]]:
    if not values:
        return []

    headers = unique_headers([normalize_header(value) for value in values[0]])
    rows: list[dict[str, str]] = []
    for row in values[1:]:
        item = {}
        for index, header in enumerate(headers):
            item[header] = normalize_cell(row[index] if index < len(row) else "")

        rows.append(item)

    return rows


def unique_headers(headers: list[str]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    unique: list[str] = []

    for index, header in enumerate(headers, start=1):
        base = header or f"column_{index}"
        counts[base] += 1
        unique.append(base if counts[base] == 1 else f"{base}_{counts[base]}")

    return unique


def parse_equipment_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, str]]:
    items: list[dict[str, object]] = []
    rooms: dict[str, str] = {}
    current_room_id = ""
    current_room_name = ""
    current_section = ""

    for row_number, row in enumerate(rows, start=2):
        room_id = cell(row, "room_id", "room id")
        room_name = cell(row, "room_name", "room name")
        object_id = cell(row, "object_id", "object id")
        object_name = cell(row, "object_name", "object name")
        prices = [parse_number(cell(row, f"price{index}")) for index in range(1, 4)]

        if room_id:
            current_room_id = room_id
        if room_name:
            current_room_name = room_name
        if current_room_id and current_room_name:
            rooms[current_room_id] = current_room_name

        has_prices = any(price is not None for price in prices)
        if not object_id and object_name and not has_prices:
            current_section = object_name
            continue

        if not object_id and not object_name and not has_prices:
            continue

        if not current_room_id:
            warn(f"equipment row {row_number}: skipped object without Room_ID")
            continue

        if not object_id:
            warn(f"equipment row {row_number}: skipped object without Object_ID")
            continue

        items.append(
            {
                "roomId": current_room_id,
                "roomName": current_room_name,
                "objectId": object_id,
                "objectName": object_name,
                "section": current_section,
                "prices": prices,
            }
        )

    return items, rooms


COMPLEXITY_NAME_TO_ID = {
    "обучающий": "Educational",
    "легкий": "Easy",
    "лёгкий": "Easy",
    "средний": "Medium",
    "сложный": "Hard",
    "легендарный": "Legendary",
}


def parse_level_rows(rows: list[dict[str, str]]) -> tuple[dict[str, object], dict[str, str]]:
    complexities, translations = parse_level_complexities(rows)
    levels: list[dict[str, object]] = []

    for row_number, row in enumerate(rows, start=2):
        level = parse_int(cell(row, "level"))
        if level is None:
            continue

        raw_complexity = cell(row, "complexity", "compexity")
        complexity_id = complexity_id_from_value(raw_complexity)
        if raw_complexity and complexity_id not in complexities:
            complexity_name_key = complexity_key(complexity_id)
            complexities[complexity_id] = {
                "id": complexity_id,
                "name_key": complexity_name_key,
            }
            translations.setdefault(complexity_name_key, raw_complexity)

        levels.append(
            {
                "level": level,
                "complexity": complexity_id,
                "award": parse_number(cell(row, "award")),
                "bonusHint": cell(row, "bonus_hint", "bonus hint") or None,
            }
        )

        if levels[-1]["award"] is None:
            warn(f"level row {row_number}: Award is empty or invalid")

    return {
        "complexities": list(complexities.values()),
        "levels": sorted(levels, key=lambda item: item["level"]),
    }, translations


def parse_level_complexities(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    complexities: dict[str, dict[str, str]] = {}
    translations: dict[str, str] = {}

    for row in rows:
        complexity_id = complexity_id_from_value(
            cell(row, "complexity_type", "compexity_type")
        )
        complexity_name = cell(row, "complexity_name", "compexity_name")
        if not complexity_id or not complexity_name:
            continue

        name_key = complexity_key(complexity_id)
        complexities.setdefault(
            complexity_id,
            {
                "id": complexity_id,
                "name_key": name_key,
            },
        )
        translations[name_key] = complexity_name

    return complexities, translations


def parse_dialog_rows(
    rows: list[dict[str, str]],
) -> tuple[dict[str, object], dict[str, str]]:
    state_to_character_key, characters, translations = parse_dialog_characters(rows)
    dialogs: list[dict[str, object]] = []
    dialogs_by_id: dict[str, dict[str, object]] = {}
    current_room_id = ""
    current_dialog_id = ""

    for row_number, row in enumerate(rows, start=2):
        room_id = cell(row, "room_id", "room id")
        dialog_id = cell(row, "dialog_id", "dialog id")
        replica_id = cell(row, "replica_id", "replica id", "replica")
        position = cell(row, "position")
        char_state = cell(row, "portrait")
        text = cell(row, "text")

        if room_id:
            current_room_id = room_id
        if dialog_id:
            if not current_room_id:
                warn(f"dialogs row {row_number}: Dialog_ID without Room_ID")
                continue
            current_dialog_id = dialog_key(current_room_id, dialog_id)

        if not replica_id and not position and not char_state and not text:
            continue

        if not current_room_id or not current_dialog_id:
            warn(f"dialogs row {row_number}: skipped replica without room/dialog id")
            continue

        if not replica_id:
            warn(f"dialogs row {row_number}: skipped replica without Replica_ID")
            continue

        if not char_state:
            warn(f"dialogs row {row_number}: skipped replica without Portrait")
            continue

        full_replica_id = replica_key(current_dialog_id, replica_id)
        char_key = state_to_character_key.get(char_state)
        if char_key is None:
            char_key = inferred_character_key(char_state)
            warn(
                f"dialogs row {row_number}: Portrait={char_state} is not in "
                f"character mapping, inferred {char_key}"
            )

        dialog = dialogs_by_id.get(current_dialog_id)
        if dialog is None:
            dialog = {
                "id": current_dialog_id,
                "roomId": current_room_id,
                "roomIndex": room_index_from_id(current_room_id),
                "conditions": [
                    {"trigger": "roomEntered"}
                ],
                "replicas": [],
            }
            dialogs_by_id[current_dialog_id] = dialog
            dialogs.append(dialog)

        dialog["replicas"].append(
            {
                "id": full_replica_id,
                "char_key": char_key,
                "char_state": char_state,
                "position": "right" if position == "right" else "left",
                "text_key": f"{full_replica_id}_loc",
            }
        )

        if text:
            translations[f"{full_replica_id}_loc"] = text

    config = {
        "characters": [
            {
                "id": character["id"],
                "name_key": key,
                "states": character["states"],
            }
            for key, character in characters.items()
        ],
        "dialogs": dialogs,
    }
    return config, translations


def parse_dialog_characters(
    rows: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, dict[str, object]], dict[str, str]]:
    state_to_character_key: dict[str, str] = {}
    characters: dict[str, dict[str, object]] = {}
    translations: dict[str, str] = {}
    current_character_id = ""
    current_character_name = ""

    for row_number, row in enumerate(rows, start=2):
        character_id = cell(row, "character_id", "character id")
        character_name = cell(row, "character_name", "character name")
        char_state = cell(row, "character_portrait", "character portrait")

        if character_id:
            current_character_id = character_id
        if character_name:
            current_character_name = character_name

        if not char_state:
            continue

        if not current_character_id:
            warn(f"dialogs row {row_number}: Character_portrait without Character_ID")
            continue

        char_key = character_name_key(current_character_id)
        character = characters.setdefault(
            char_key,
            {
                "id": current_character_id,
                "states": [],
            },
        )
        if char_state not in character["states"]:
            character["states"].append(char_state)

        state_to_character_key[char_state] = char_key

        if current_character_name:
            translations[char_key] = current_character_name

    return state_to_character_key, characters, translations


def build_price_config(items: list[dict[str, object]]) -> dict[str, object]:
    rooms: dict[str, dict[str, object]] = defaultdict(dict)

    for item in items:
        object_id = str(item["objectId"])
        rooms[str(item["roomId"])][object_id] = {
            "prices": item["prices"],
        }

        if item["section"]:
            rooms[str(item["roomId"])][object_id]["section"] = item["section"]

    return {"rooms": dict(sorted(rooms.items()))}


def build_level_rewards(level_rewards: dict[str, object]) -> dict[str, object]:
    return level_rewards


def build_objects_ru(items: list[dict[str, object]]) -> dict[str, str]:
    translations = {}
    for item in items:
        object_name = str(item["objectName"]).strip()
        if object_name:
            translations[object_key(str(item["roomId"]), str(item["objectId"]))] = object_name

    return dict(sorted(translations.items()))


def build_rooms_ru(rooms: dict[str, str]) -> dict[str, str]:
    return {
        room_key(room_id): room_name
        for room_id, room_name in sorted(rooms.items())
        if room_name.strip()
    }


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


def update_room_configs(
    items: list[dict[str, object]],
    rooms: dict[str, str],
) -> list[str]:
    items_by_room: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        items_by_room[str(item["roomId"])].append(item)

    updated_rooms: list[str] = []
    for room_id, room_name in rooms.items():
        room_config_path = CONFIG_DIR / f"{room_id}.json"
        if not room_config_path.exists():
            warn(f"{room_config_path.relative_to(ROOT)} does not exist")
            continue

        with room_config_path.open("r", encoding="utf-8") as file:
            room_config = json.load(file)

        if is_new_room_config(room_config):
            room_config["key"] = room_id
            room_config["name_key"] = room_key(room_id)
            normalize_new_room_config_names(room_config)
        else:
            room_config["roomId"] = room_id
            room_config["nameKey"] = room_key(room_id)

        object_index = index_room_objects(room_config, room_id)
        matched_keys: set[str] = set()

        for item in items_by_room.get(room_id, []):
            object_id = str(item["objectId"])
            key = normalized_id(object_id)
            matches = object_index.get(key, [])

            if not matches:
                warn(f"{room_id}: no config object matched Object_ID={object_id}")
                continue

            for match in matches:
                match_key = str(match.get("key") or match.get("id") or object_id)
                if is_new_room_config(room_config):
                    match["price"] = price_for_match(item, match_key)
                else:
                    match["name_key"] = object_key(room_id, object_id)

            matched_keys.add(key)

        write_json(room_config_path, room_config)
        updated_rooms.append(room_id)
        print(
            f"updated {room_config_path.relative_to(ROOT).as_posix()} "
            f"({len(matched_keys)} object ids, room name: {room_name})"
        )

    return updated_rooms


def is_new_room_config(room_config: dict[str, object]) -> bool:
    return isinstance(room_config.get("allMultiobjects"), list)


def normalize_new_room_config_names(room_config: dict[str, object]) -> None:
    for action_point in room_config.get("allActionPoints", []):
        if not isinstance(action_point, dict):
            continue

        key = str(action_point.get("key") or "").strip()
        if key:
            action_point["name_key"] = f"{key}_loc"

    for multiobject in room_config.get("allMultiobjects", []):
        if isinstance(multiobject, dict):
            multiobject.pop("name_key", None)


def index_room_objects(
    room_config: dict[str, object],
    room_id: str,
) -> dict[str, list[dict[str, object]]]:
    index: dict[str, list[dict[str, object]]] = defaultdict(list)

    if is_new_room_config(room_config):
        for multiobject in room_config.get("allMultiobjects", []):
            if not isinstance(multiobject, dict):
                continue

            multiobject_key = str(multiobject.get("key", ""))
            base_key = strip_room_prefix(room_id, multiobject_key)
            keys = {
                normalized_id(base_key),
                normalized_id(strip_variant(base_key)),
                normalized_id(strip_multiobject_variant(base_key)),
                normalized_id(normalize_generated_part_id(base_key)),
            }

            for part_key in multiobject.get("parts", []):
                part_base = strip_room_prefix(room_id, str(part_key))
                keys.update(
                    {
                        normalized_id(part_base),
                        normalized_id(strip_variant(part_base)),
                        normalized_id(normalize_generated_part_id(part_base)),
                    }
                )

            for key in keys:
                if key:
                    index[key].append(multiobject)

        dedupe_index(index)
        return index

    for group in room_config.get("groups", []):
        if not isinstance(group, dict):
            continue

        group_id = str(group.get("groupId") or group.get("id") or "")
        for obj in group.get("objects", []):
            if not isinstance(obj, dict):
                continue

            keys = {
                normalized_id(group_id),
                normalized_id(str(obj.get("id", ""))),
                normalized_id(str(obj.get("imageId", ""))),
                normalized_id(strip_variant(str(obj.get("id", "")))),
                normalized_id(strip_variant(str(obj.get("imageId", "")))),
            }

            for key in keys:
                if key:
                    index[key].append(obj)

    dedupe_index(index)
    return index


def dedupe_index(index: dict[str, list[dict[str, object]]]) -> None:
    for objects in index.values():
        unique_objects = []
        seen = set()
        for obj in objects:
            marker = id(obj)
            if marker not in seen:
                unique_objects.append(obj)
                seen.add(marker)

        objects[:] = unique_objects


def strip_variant(value: str) -> str:
    return re.sub(r"_[A-Z](?:_\d+)?$", "", value)


def strip_multiobject_variant(value: str) -> str:
    return re.sub(r"_variant_\d+$", "", value)


def strip_room_prefix(room_id: str, value: str) -> str:
    return value.removeprefix(f"{room_id}_")


def normalize_generated_part_id(value: str) -> str:
    return re.sub(r"_(\d+)$", r"\1", value)


def normalized_id(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def object_key(room_id: str, object_id: str) -> str:
    return f"{room_id}_{object_id}_loc"


def room_key(room_id: str) -> str:
    return f"{room_id}_loc"


def complexity_key(complexity_id: str) -> str:
    return f"complexity_{slug_key(complexity_id)}_loc"


def complexity_id_from_value(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""

    return COMPLEXITY_NAME_TO_ID.get(normalized.casefold(), normalized)


def slug_key(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def dialog_key(room_id: str, dialog_id: str) -> str:
    return dialog_id if dialog_id.startswith(f"{room_id}_") else f"{room_id}_{dialog_id}"


def replica_key(dialog_id: str, replica_id: str) -> str:
    return replica_id if replica_id.startswith(f"{dialog_id}_") else f"{dialog_id}_{replica_id}"


def inferred_character_key(char_state: str) -> str:
    character_id = char_state.split("_", 1)[0].strip()
    return character_name_key(character_id or "unknown")


def character_name_key(character_id: str) -> str:
    return f"{character_id}_loc"


def room_index_from_id(room_id: str) -> int:
    match = re.search(r"(\d+)$", room_id)
    return int(match.group(1)) if match else 1


def price_for_match(item: dict[str, object], match_key: str) -> int | float:
    prices = item["prices"]
    if not isinstance(prices, list):
        return 99999

    variant_index = variant_index_for_key(match_key)
    if variant_index is not None and variant_index < len(prices):
        price = prices[variant_index]
        if isinstance(price, (int, float)):
            return price

    return next((price for price in prices if isinstance(price, (int, float))), 99999)


def variant_index_for_key(value: str) -> int | None:
    match = re.search(r"_variant_(\d+)$", value)
    if match:
        return max(0, int(match.group(1)) - 1)

    if re.search(r"_[A-Z](?:_\d+)?$", value):
        letter = re.search(r"_([A-Z])(?:_\d+)?$", value).group(1)
        return ord(letter) - ord("A")

    return 0


def cell(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(normalize_header(name), "")
        if value:
            return value

    return ""


def parse_number(value: str) -> int | float | None:
    if not value:
        return None

    normalized = value.replace(" ", "").replace(",", ".")
    try:
        number = float(normalized)
    except ValueError:
        return None

    return int(number) if number.is_integer() else number


def parse_int(value: str) -> int | None:
    number = parse_number(value)
    return int(number) if isinstance(number, (int, float)) else None


def normalize_header(value: str | None) -> str:
    return normalize_cell(value).lower().replace(" ", "_")


def normalize_cell(value: str | None) -> str:
    return str(value or "").strip()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def write_json(path: Path, data: object) -> None:
    output_path = resolve_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"export-google-sheets failed: {error}", file=sys.stderr)
        raise
