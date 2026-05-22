from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from export_google_sheets import (
    DEFAULT_SPREADSHEET_URL,
    extract_spreadsheet_id,
    read_csv_table,
    read_google_values,
    resolve_path,
)


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SHEET_DIR = ROOT / "tmp" / "sheets"

SHEET_FILES = {
    "equipment": "equipment.csv",
    "levels": "levels.csv",
    "dialogs": "dialogs.csv",
}


def add_google_sheet_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--spreadsheet-id",
        default=(
            os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
            or os.environ.get("GOOGLE_SHEETS_SPREADSHEET_URL")
            or DEFAULT_SPREADSHEET_URL
        ),
        help="Google Spreadsheet id or URL.",
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
    )
    parser.add_argument(
        "--levels-sheet",
        default=os.environ.get("LEVEL_REWARDS_SHEET_NAME", "Levels"),
    )
    parser.add_argument(
        "--dialogs-sheet",
        default=os.environ.get("DIALOGS_SHEET_NAME", "dialogs"),
    )
    parser.add_argument(
        "--equipment-range",
        default=os.environ.get("EQUIPMENT_SHEET_RANGE"),
    )
    parser.add_argument(
        "--levels-range",
        default=os.environ.get("LEVEL_REWARDS_SHEET_RANGE"),
    )
    parser.add_argument(
        "--dialogs-range",
        default=os.environ.get("DIALOGS_SHEET_RANGE"),
    )


def download_sheet_cache(args: argparse.Namespace) -> list[Path]:
    spreadsheet_id = extract_spreadsheet_id(args.spreadsheet_id)
    if not spreadsheet_id:
        raise SystemExit("No spreadsheet id provided")

    LOCAL_SHEET_DIR.mkdir(parents=True, exist_ok=True)
    written = []

    for key, sheet_name, value_range in (
        ("equipment", args.equipment_sheet, args.equipment_range),
        ("levels", args.levels_sheet, args.levels_range),
        ("dialogs", args.dialogs_sheet, args.dialogs_range),
    ):
        values = read_google_values(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            value_range=value_range,
            credentials_path=args.credentials,
            api_key=args.api_key,
        )
        path = local_sheet_path(key)
        write_csv_values(path, values)
        written.append(path)

    return written


def local_sheet_path(key: str) -> Path:
    return LOCAL_SHEET_DIR / SHEET_FILES[key]


def require_local_tables(keys: tuple[str, ...] = ("equipment", "levels", "dialogs")) -> None:
    missing = [local_sheet_path(key) for key in keys if not local_sheet_path(key).exists()]
    if missing:
        joined = ", ".join(path.relative_to(ROOT).as_posix() for path in missing)
        raise SystemExit(f"Local sheet cache is missing: {joined}. Run prepare-balance or prepare-rooms first.")


def read_local_table(key: str) -> list[dict[str, str]]:
    require_local_tables((key,))
    return read_csv_table(resolve_path(local_sheet_path(key)))


def write_csv_values(path: Path, values: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(values)
