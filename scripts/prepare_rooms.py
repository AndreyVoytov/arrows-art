from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
    from psd_tools import PSDImage
except ImportError as error:
    raise SystemExit(
        "prepare-rooms requires Python packages `psd-tools` and `Pillow`."
    ) from error


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "images" / "src"
IMAGES_DIR = ROOT / "images"
ROOM_IMAGES_DIR = IMAGES_DIR / "rooms"
CONFIG_DIR = ROOT / "config"
DEFAULT_PRICE = 99999

ANGLE_SUFFIX_RE = re.compile(r"\[-?\d+\]$")
ROOM_FILE_RE = re.compile(r"^room(\d+)\.psd$", re.IGNORECASE)
VARIANT_SUFFIX_RE = re.compile(r"_(?:[A-Z])(?:_\d+)?$")
NUMBER_SUFFIX_RE = re.compile(r"_\d+$")
VARIANT_LETTER_RE = re.compile(r"_([A-Z])(?:_\d+)?$")
MULTIOBJECT_VARIANT_RE = re.compile(r"_variant_(\d+)$")


@dataclass
class ExportedObject:
    id: str
    image_id: str
    group: str
    phase: str
    x: int | float
    y: int | float
    width: int
    height: int
    angle: int


@dataclass(frozen=True)
class ExportScale:
    x: float
    y: float


TARGET_ROOM_WIDTH = 720
TARGET_ROOM_HEIGHT = 960


def main(argv: list[str] | None = None) -> None:
    logging.getLogger("psd_tools").setLevel(logging.ERROR)
    args = parse_args(argv)
    src_dir = resolve_path(args.src_dir)

    if not src_dir.exists():
        raise SystemExit(f"PSD source directory does not exist: {relative(src_dir)}")

    psd_paths = sorted(src_dir.glob("room*.psd"))
    if not psd_paths:
        raise SystemExit(f"No room PSD files found in {relative(src_dir)}")

    room_filter = parse_room_filter(args.rooms)
    if room_filter is not None:
        psd_paths = [
            psd_path for psd_path in psd_paths
            if room_number(psd_path) in room_filter
        ]

    if not psd_paths:
        raise SystemExit("No room PSD files match the requested room filter")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    write_images = not args.config_only
    write_config = not args.images_only

    for psd_path in psd_paths:
        prepare_room(psd_path, write_images=write_images, write_config=write_config)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    argv = normalize_cli_args(argv or [])
    parser = argparse.ArgumentParser(
        description="Export room PSD layers and generate room config JSON files."
    )
    parser.add_argument(
        "--src-dir",
        default=str(SRC_DIR),
        help="Directory with room*.psd files. Defaults to images/src.",
    )
    parser.add_argument(
        "rooms",
        nargs="?",
        default=room_filter_from_npm_env(),
        help="Room number or inclusive range, for example 2 or 1:2.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--images-only",
        action="store_true",
        help="Export room PNG files without writing room config JSON.",
    )
    mode.add_argument(
        "--config-only",
        action="store_true",
        help="Write room config JSON without updating room PNG files.",
    )
    return parser.parse_args(argv)


def normalize_cli_args(argv: list[str]) -> list[str]:
    normalized = []

    for arg in argv:
        match = re.fullmatch(r"--(\d+(?::\d+)?)", arg)
        normalized.append(match.group(1) if match else arg)

    return normalized


def room_filter_from_npm_env() -> str | None:
    for key, value in os.environ.items():
        normalized_key = key.lower()
        if not normalized_key.startswith("npm_config_") or value.lower() != "true":
            continue

        maybe_filter = normalized_key.removeprefix("npm_config_")
        if re.fullmatch(r"\d+(?::\d+)?", maybe_filter):
            return maybe_filter

    return None


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


def room_number(path: Path) -> int | None:
    match = ROOM_FILE_RE.match(path.name)
    return int(match.group(1)) if match else None


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def prepare_room(
    psd_path: Path,
    *,
    write_images: bool = True,
    write_config: bool = True,
) -> None:
    room_id = psd_path.stem
    phase_image_dirs = {
        "repair": room_phase_image_dir(room_id, "repair"),
        "decor": room_phase_image_dir(room_id, "decor"),
    }
    if write_images:
        for image_dir in phase_image_dirs.values():
            image_dir.mkdir(parents=True, exist_ok=True)

    psd = PSDImage.open(psd_path)
    export_scale = room_export_scale(psd)
    existing_order = load_existing_order(room_id)
    price_config = load_price_config() if write_config else {"rooms": {}}
    objects: list[ExportedObject] = []
    exported_pngs: dict[str, set[str]] = {
        phase: set()
        for phase in phase_image_dirs
    }
    object_count = 0

    for layer, phase in iter_export_layers(psd):
        source_id = normalize_id(layer.name)
        layer_id = strip_angle(source_id)
        angle = angle_from_id(source_id)

        if layer_id == "room_bg":
            if write_images:
                output_path = phase_image_dirs["repair"] / f"{room_key(room_id, 'room_bg')}.png"
                export_room_bg(psd, layer, output_path, export_scale)
                exported_pngs["repair"].add(output_path.name)
            continue

        if phase is None:
            phase = infer_phase(normalize_group(layer_id), existing_order)

        if phase is None:
            continue

        exported_image, left, top = export_layer_from_scaled_room(psd, layer, export_scale)
        x = center_coordinate(left, exported_image.width)
        y = center_coordinate(top, exported_image.height)
        image_id = room_key(room_id, layer_id)
        object_count += 1
        if write_images:
            output_path = phase_image_dirs[phase] / f"{image_id}.png"
            save_png(exported_image, output_path)
            exported_pngs[phase].add(output_path.name)

        if write_config:
            objects.append(
                ExportedObject(
                    id=layer_id,
                    image_id=image_id,
                    group=normalize_group(layer_id),
                    phase=phase,
                    x=x,
                    y=y,
                    width=exported_image.width,
                    height=exported_image.height,
                    angle=angle,
                )
            )

    if write_config:
        write_room_config(room_id, objects, existing_order, price_config)
        remove_legacy_room_order(room_id)
    if write_images:
        for phase, image_dir in phase_image_dirs.items():
            remove_stale_pngs(image_dir, exported_pngs[phase])
        remove_legacy_room_image_dir(room_id)

    actions = []
    if write_images:
        actions.append("images")
    if write_config:
        actions.append("config")
    print(f"prepared {room_id} {'+'.join(actions)}: {object_count} objects")


def room_phase_image_dir(room_id: str, phase: str) -> Path:
    return ROOM_IMAGES_DIR / f"{room_id}-{phase}"


def room_export_scale(psd: PSDImage) -> ExportScale:
    return ExportScale(
        x=TARGET_ROOM_WIDTH / psd.width,
        y=TARGET_ROOM_HEIGHT / psd.height,
    )


def iter_export_layers(psd: PSDImage) -> Iterable[tuple[object, str | None]]:
    def walk(layers: Iterable[object], phase: str | None) -> Iterable[tuple[object, str | None]]:
        for layer in layers:
            if layer.is_group():
                next_phase = phase_for_group(layer.name) or phase
                yield from walk(layer, next_phase)
                continue

            if layer.name.startswith("</"):
                continue

            if not layer.has_pixels():
                continue

            yield layer, phase

    yield from walk(psd, None)


def phase_for_group(group_name: str) -> str | None:
    name = group_name.lower()

    if name in {"broken_equipment", "repair", "repairs", "broken"}:
        return "repair"

    if name in {"equipment", "decor", "decoration", "decorations"}:
        return "decor"

    if "broken" in name or "repair" in name:
        return "repair"

    return None


def normalize_group(layer_name: str) -> str:
    name = strip_angle(layer_name)
    name = VARIANT_SUFFIX_RE.sub("", name)
    return NUMBER_SUFFIX_RE.sub("", name)


def normalize_id(layer_name: str) -> str:
    return layer_name.strip()


def strip_angle(layer_name: str) -> str:
    return ANGLE_SUFFIX_RE.sub("", normalize_id(layer_name))


def angle_from_id(layer_name: str) -> int:
    match = ANGLE_SUFFIX_RE.search(normalize_id(layer_name))
    return int(match.group(0)[1:-1]) if match else 0


def export_layer_from_scaled_room(
    psd: PSDImage,
    layer: object,
    export_scale: ExportScale,
) -> tuple[Image.Image, int, int]:
    image = layer.composite(force=True).convert("RGBA")
    left, top, right, bottom = map(int, layer.bbox)

    canvas_left = max(0, left)
    canvas_top = max(0, top)
    canvas_right = min(psd.width, right)
    canvas_bottom = min(psd.height, bottom)

    canvas = Image.new("RGBA", (psd.width, psd.height), (0, 0, 0, 0))
    if canvas_left < canvas_right and canvas_top < canvas_bottom:
        clipped = image.crop(
            (
                canvas_left - left,
                canvas_top - top,
                canvas_right - left,
                canvas_bottom - top,
            )
        )
        scrub_transparent_pixels(clipped)
        canvas.alpha_composite(clipped, (canvas_left, canvas_top))

    canvas = resize_for_export(canvas, export_scale)
    alpha_bounds = canvas.getchannel("A").getbbox()
    if alpha_bounds is None:
        transparent = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return transparent, 0, 0

    cropped = canvas.crop(alpha_bounds)
    scrub_transparent_pixels(cropped)

    return cropped, alpha_bounds[0], alpha_bounds[1]


def export_room_bg(
    psd: PSDImage,
    layer: object,
    output_path: Path,
    export_scale: ExportScale,
) -> None:
    viewport = (0, 0, psd.width, psd.height)
    image = layer.composite(viewport=viewport).convert("RGBA")
    scrub_transparent_pixels(image)
    image = resize_for_export(image, export_scale)
    save_png(image, output_path)


def resize_for_export(image: Image.Image, export_scale: ExportScale) -> Image.Image:
    size = scaled_size(image.size, export_scale)
    if image.size == size:
        return image

    resized = image.resize(size, Image.Resampling.LANCZOS)
    scrub_transparent_pixels(resized)
    return resized


def scaled_size(size: tuple[int, int], export_scale: ExportScale) -> tuple[int, int]:
    width, height = size
    return (
        max(1, round(width * export_scale.x)),
        max(1, round(height * export_scale.y)),
    )


def scrub_transparent_pixels(image: Image.Image) -> None:
    pixels = image.load()

    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0 and (red != 0 or green != 0 or blue != 0):
                pixels[x, y] = (0, 0, 0, 0)


def save_png(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if png_matches(output_path, image):
        return

    image.save(output_path)


def png_matches(output_path: Path, image: Image.Image) -> bool:
    if not output_path.exists():
        return False

    try:
        existing = Image.open(output_path).convert("RGBA")
    except OSError:
        return False

    if existing.size != image.size:
        return False

    return existing.tobytes() == image.tobytes()


def remove_stale_pngs(room_image_dir: Path, exported_pngs: set[str]) -> None:
    for png_path in room_image_dir.glob("*.png"):
        if png_path.name not in exported_pngs:
            png_path.unlink()


def remove_legacy_room_image_dir(room_id: str) -> None:
    legacy_dir = ROOM_IMAGES_DIR / room_id
    if not legacy_dir.exists():
        return

    room_images_root = ROOM_IMAGES_DIR.resolve()
    legacy_path = legacy_dir.resolve()
    try:
        legacy_path.relative_to(room_images_root)
    except ValueError as error:
        raise RuntimeError(f"Refusing to remove path outside images/rooms: {legacy_path}") from error

    if legacy_dir.name != room_id:
        raise RuntimeError(f"Refusing to remove unexpected legacy room directory: {legacy_path}")

    shutil.rmtree(legacy_path)


def load_existing_order(room_id: str) -> dict[str, list[str]]:
    order_path = CONFIG_DIR / f"{room_id}_order.json"
    if order_path.exists():
        with order_path.open("r", encoding="utf-8") as file:
            order = json.load(file)

        return {
            "repair": [normalize_group(str(group)) for group in order.get("repair", [])],
            "decor": [normalize_group(str(group)) for group in order.get("decor", [])],
        }

    config_path = CONFIG_DIR / f"{room_id}.json"
    if not config_path.exists():
        return {"repair": [], "decor": []}

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    content = config.get("content") if isinstance(config, dict) else None
    if not isinstance(content, dict):
        return {"repair": [], "decor": []}

    return {
        "repair": [
            normalize_group(roomless_key(room_id, str(group)))
            for group in content.get("repairActionPoint", [])
        ],
        "decor": [
            normalize_group(roomless_key(room_id, str(group)))
            for group in content.get("decorActionPoint", [])
        ],
    }


def infer_phase(group: str, existing_order: dict[str, list[str]]) -> str | None:
    if group in existing_order["repair"]:
        return "repair"

    if group in existing_order["decor"]:
        return "decor"

    return None


def load_price_config() -> dict[str, object]:
    try:
        from export_google_sheets import build_price_config, parse_equipment_rows
        from sheet_cache import read_local_table
    except ImportError:
        return {"rooms": {}}

    try:
        equipment_items, _rooms = parse_equipment_rows(read_local_table("equipment"))
    except SystemExit:
        return {"rooms": {}}

    return build_price_config(equipment_items)


def write_room_config(
    room_id: str,
    objects: list[ExportedObject],
    existing_order: dict[str, list[str]],
    price_config: dict[str, object],
) -> None:
    groups = group_objects(objects)
    order = {
        "repair": merge_existing_order(
            existing_order["repair"],
            unique_groups(item for item in objects if item.phase == "repair"),
        ),
        "decor": merge_existing_order(
            existing_order["decor"],
            unique_groups(item for item in objects if item.phase == "decor"),
        ),
    }
    price_lookup = build_price_lookup(price_config, room_id)
    all_parts: list[dict[str, object]] = []
    all_multiobjects: list[dict[str, object]] = []
    all_action_points: list[dict[str, object]] = []

    for phase in ("repair", "decor"):
        for group_id in order[phase]:
            items = groups.get(group_id, [])
            if not items:
                continue

            multiobjects = build_multiobjects(room_id, group_id, items, price_lookup)
            action_bounds = bounds_for(items)
            action_point_key = room_key(room_id, group_id)
            all_action_points.append(
                compact_dict(
                    {
                        "key": action_point_key,
                        "name_key": f"{action_point_key}_loc",
                        "multiobjects": [multiobject["key"] for multiobject in multiobjects],
                        "x": round((action_bounds["left"] + action_bounds["right"]) / 2),
                        "y": round((action_bounds["top"] + action_bounds["bottom"]) / 2),
                    }
                )
            )

            for multiobject in multiobjects:
                all_multiobjects.append(multiobject)
                all_parts.extend(part_for(item, room_id) for item in multiobject.pop("_items"))

    all_parts = sort_parts_by_z_index(room_id, all_parts, objects)

    config = {
        "key": room_id,
        "name_key": f"{room_id}_loc",
        "background": room_key(room_id, "room_bg"),
        "content": {
            "repairActionPoint": [
                room_key(room_id, group)
                for group in order["repair"]
                if group in groups
            ],
            "decorActionPoint": [
                room_key(room_id, group)
                for group in order["decor"]
                if group in groups
            ],
        },
        "allActionPoints": all_action_points,
        "allMultiobjects": all_multiobjects,
        "allParts": all_parts,
    }

    write_json(CONFIG_DIR / f"{room_id}.json", config)


def group_objects(objects: Iterable[ExportedObject]) -> dict[str, list[ExportedObject]]:
    groups: dict[str, list[ExportedObject]] = {}

    for item in objects:
        groups.setdefault(item.group, []).append(item)

    return groups


def build_multiobjects(
    room_id: str,
    group_id: str,
    items: list[ExportedObject],
    price_lookup: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    variant_groups = group_by_variant(items)
    if variant_groups:
        multiobjects = []

        for index, (_variant, variant_items) in enumerate(variant_groups, start=1):
            key = room_key(room_id, group_id) if index == 1 else room_key(room_id, f"{group_id}_variant_{index}")
            multiobjects.append(
                multiobject_for(
                    key=key,
                    room_id=room_id,
                    group_id=group_id,
                    items=variant_items,
                    price=price_for(price_lookup, [key, group_id], index - 1),
                )
            )

        return multiobjects

    key = room_key(room_id, group_id)
    return [
        multiobject_for(
            key=key,
            room_id=room_id,
            group_id=group_id,
            items=items,
            price=price_for(price_lookup, [key, group_id], None),
        )
    ]


def group_by_variant(items: list[ExportedObject]) -> list[tuple[str, list[ExportedObject]]]:
    groups: dict[str, list[ExportedObject]] = {}
    has_variants = False

    for item in items:
        variant = variant_letter(item.id)
        if variant is not None:
            has_variants = True
        groups.setdefault(variant or "A", []).append(item)

    if not has_variants:
        return []

    return sorted(groups.items(), key=lambda entry: variant_sort_key(entry[0]))


def variant_letter(value: str) -> str | None:
    match = VARIANT_LETTER_RE.search(strip_angle(value).strip())
    return match.group(1) if match else None


def variant_sort_key(value: str) -> tuple[int, str]:
    if len(value) == 1 and "A" <= value <= "Z":
        return (ord(value) - ord("A"), value)

    return (999, value)


def multiobject_for(
    *,
    key: str,
    room_id: str,
    group_id: str,
    items: list[ExportedObject],
    price: int | float,
) -> dict[str, object]:
    return compact_dict(
        {
            "key": key,
            "parts": [part_key(item, room_id) for item in items],
            "price": price,
            "_items": items,
        }
    )


def part_for(item: ExportedObject, room_id: str) -> dict[str, object]:
    return {
        "key": part_key(item, room_id),
        "type": item.phase,
        "x": item.x,
        "y": item.y,
        "angle": item.angle,
    }


def part_key(item: ExportedObject, room_id: str) -> str:
    return room_key(room_id, item.id)


def sort_parts_by_z_index(
    room_id: str,
    parts: list[dict[str, object]],
    objects: list[ExportedObject],
) -> list[dict[str, object]]:
    order = {part_key(item, room_id): index for index, item in enumerate(objects)}
    fallback = len(order)
    return sorted(parts, key=lambda part: order.get(str(part.get("key")), fallback))


def bounds_for(items: list[ExportedObject]) -> dict[str, int | float]:
    left = min(item.x - item.width / 2 for item in items)
    top = min(item.y - item.height / 2 for item in items)
    right = max(item.x + item.width / 2 for item in items)
    bottom = max(item.y + item.height / 2 for item in items)
    return {
        "left": json_number(left),
        "top": json_number(top),
        "right": json_number(right),
        "bottom": json_number(bottom),
        "width": json_number(right - left),
        "height": json_number(bottom - top),
    }


def center_coordinate(start: int | float, size: int) -> int | float:
    return json_number(start + size / 2)


def json_number(value: int | float) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def build_price_lookup(
    price_config: dict[str, object],
    room_id: str,
) -> dict[str, dict[str, object]]:
    prices: dict[str, dict[str, object]] = {}
    rooms = price_config.get("rooms") if isinstance(price_config, dict) else None
    if not isinstance(rooms, dict):
        return prices

    room_prices = rooms.get(room_id)
    if not isinstance(room_prices, dict):
        return prices

    for object_id, raw_entry in room_prices.items():
        if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get("prices"), list):
            continue

        entry = {
            "objectId": str(object_id),
            "prices": [normalize_price_value(value) for value in raw_entry["prices"]],
        }
        if not any(value is not None for value in entry["prices"]):
            continue

        for key in price_config_keys(str(object_id)):
            prices[key] = entry

    return prices


def price_for(
    price_lookup: dict[str, dict[str, object]],
    candidates: list[str],
    variant_index: int | None,
) -> int | float:
    entry = find_price_entry(price_lookup, candidates)
    if entry is None:
        return DEFAULT_PRICE

    prices = entry["prices"]
    if (
        variant_index is not None
        and variant_index < len(prices)
        and prices[variant_index] is not None
    ):
        return prices[variant_index]

    return next((price for price in prices if price is not None), DEFAULT_PRICE)


def find_price_entry(
    price_lookup: dict[str, dict[str, object]],
    candidates: list[str],
) -> dict[str, object] | None:
    for candidate in candidates:
        for key in price_lookup_keys(candidate):
            for alias in price_lookup_aliases(key):
                entry = price_lookup.get(alias)
                if entry is not None:
                    return entry

    return None


def price_config_keys(value: str) -> list[str]:
    keys: set[str] = set()
    raw = strip_angle(value)
    add_price_key(keys, raw)
    add_price_key(keys, normalize_group(raw))
    return list(keys)


def price_lookup_keys(value: str) -> list[str]:
    keys: set[str] = set()
    raw = strip_angle(roomless_any_key(value))
    add_price_key(keys, raw)
    add_price_key(keys, normalize_group(raw))
    add_price_key(keys, strip_multiobject_variant(raw))
    return list(keys)


def add_price_key(keys: set[str], value: str) -> None:
    key = normalize_price_key(value)
    if key:
        keys.add(key)


def normalize_price_key(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def price_lookup_aliases(key: str) -> list[str]:
    aliases = [key]
    without_side = re.sub(r"(?:left|right)$", "", key)
    if without_side and without_side != key:
        aliases.append(without_side)

    if "plant" in key and "plant" not in aliases:
        aliases.append("plant")

    return aliases


def normalize_price_value(value: object) -> int | float | None:
    if value is None or value == "":
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return int(number) if number.is_integer() else number


def strip_multiobject_variant(value: str) -> str:
    return MULTIOBJECT_VARIANT_RE.sub("", value)


def room_key(room_id: str, key: str) -> str:
    return key if key == room_id or key.startswith(f"{room_id}_") else f"{room_id}_{key}"


def roomless_key(room_id: str, key: str) -> str:
    prefix = f"{room_id}_"
    return key.removeprefix(prefix)


def roomless_any_key(key: str) -> str:
    return re.sub(r"^room\d+_", "", key)


def compact_dict(data: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in data.items()
        if value is not None
    }


def remove_legacy_room_order(room_id: str) -> None:
    order_path = CONFIG_DIR / f"{room_id}_order.json"
    if order_path.exists():
        order_path.unlink()


def write_room_order(
    room_id: str,
    objects: list[ExportedObject],
    existing_order: dict[str, list[str]],
) -> None:
    available = {
        "repair": unique_groups(item for item in objects if item.phase == "repair"),
        "decor": unique_groups(item for item in objects if item.phase == "decor"),
    }
    order = {
        "repair": merge_existing_order(existing_order["repair"], available["repair"]),
        "decor": merge_existing_order(existing_order["decor"], available["decor"]),
    }

    write_json(CONFIG_DIR / f"{room_id}_order.json", order)


def unique_groups(objects: Iterable[ExportedObject]) -> list[str]:
    groups: list[str] = []
    seen: set[str] = set()

    for item in objects:
        if item.group in seen:
            continue

        seen.add(item.group)
        groups.append(item.group)

    return groups


def merge_existing_order(existing: list[str], available: list[str]) -> list[str]:
    available_set = set(available)
    order: list[str] = []
    seen: set[str] = set()

    for group in existing:
        if group not in available_set or group in seen:
            continue

        order.append(group)
        seen.add(group)

    for group in available:
        if group not in seen:
            order.append(group)

    return order


def write_json(path: Path, data: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"prepare-rooms failed: {error}", file=sys.stderr)
        raise
