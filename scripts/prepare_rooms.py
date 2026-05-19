from __future__ import annotations

import argparse
import json
import logging
import os
import re
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
CONFIG_DIR = ROOT / "config"

ANGLE_SUFFIX_RE = re.compile(r"\[-?\d+\]$")
ROOM_FILE_RE = re.compile(r"^room(\d+)\.psd$", re.IGNORECASE)
ROOM_CONFIG_RE = re.compile(r"^room(\d+)\.json$", re.IGNORECASE)
VARIANT_SUFFIX_RE = re.compile(r"_(?:[A-Z])(?:_\d+)?$")
NUMBER_SUFFIX_RE = re.compile(r"_\d+$")


@dataclass
class ExportedObject:
    id: str
    group: str
    phase: str
    x: int
    y: int
    width: int
    height: int


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

    for psd_path in psd_paths:
        prepare_room(psd_path)

    write_rooms_manifest()


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


def prepare_room(psd_path: Path) -> None:
    room_id = psd_path.stem
    room_image_dir = IMAGES_DIR / room_id
    room_image_dir.mkdir(parents=True, exist_ok=True)

    psd = PSDImage.open(psd_path)
    existing_order = load_existing_order(room_id)
    objects: list[ExportedObject] = []
    exported_pngs: set[str] = set()

    for layer, phase in iter_export_layers(psd):
        layer_id = normalize_id(layer.name)

        if layer_id == "room_bg":
            output_path = room_image_dir / "room_bg.png"
            export_room_bg(psd, layer, output_path)
            exported_pngs.add(output_path.name)
            continue

        if phase is None:
            phase = infer_phase(normalize_group(layer_id), existing_order)

        if phase is None:
            continue

        exported_image, x, y = export_layer(psd, layer)
        output_path = room_image_dir / f"{layer_id}.png"
        save_png(exported_image, output_path)
        exported_pngs.add(output_path.name)

        objects.append(
            ExportedObject(
                id=layer_id,
                group=normalize_group(layer_id),
                phase=phase,
                x=x,
                y=y,
                width=exported_image.width,
                height=exported_image.height,
            )
        )

    write_room_config(room_id, objects)
    write_room_order(room_id, objects, existing_order)
    remove_stale_pngs(room_image_dir, exported_pngs)

    print(f"prepared {room_id}: {len(objects)} objects")


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
    name = ANGLE_SUFFIX_RE.sub("", normalize_id(layer_name))
    name = VARIANT_SUFFIX_RE.sub("", name)
    return NUMBER_SUFFIX_RE.sub("", name)


def normalize_id(layer_name: str) -> str:
    return layer_name.strip()


def export_layer(psd: PSDImage, layer: object) -> tuple[Image.Image, int, int]:
    image = layer.composite(force=True).convert("RGBA")
    left, top, right, bottom = map(int, layer.bbox)

    canvas_left = max(0, left)
    canvas_top = max(0, top)
    canvas_right = min(psd.width, right)
    canvas_bottom = min(psd.height, bottom)

    clipped = image.crop(
        (
            canvas_left - left,
            canvas_top - top,
            canvas_right - left,
            canvas_bottom - top,
        )
    )

    alpha_bounds = clipped.getchannel("A").getbbox()
    if alpha_bounds is None:
        transparent = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return transparent, canvas_left, canvas_top

    cropped = clipped.crop(alpha_bounds)
    scrub_transparent_pixels(cropped)

    return cropped, canvas_left + alpha_bounds[0], canvas_top + alpha_bounds[1]


def export_room_bg(psd: PSDImage, layer: object, output_path: Path) -> None:
    left, top, _right, _bottom = map(int, layer.bbox)
    viewport_top = max(0, top)
    viewport = (0, viewport_top, psd.width, psd.height)
    image = layer.composite(viewport=viewport).convert("RGBA")
    scrub_transparent_pixels(image)
    save_png(image, output_path)


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


def load_existing_order(room_id: str) -> dict[str, list[str]]:
    order_path = CONFIG_DIR / f"{room_id}_order.json"
    if not order_path.exists():
        return {"repair": [], "decor": []}

    with order_path.open("r", encoding="utf-8") as file:
        order = json.load(file)

    return {
        "repair": [normalize_group(str(group)) for group in order.get("repair", [])],
        "decor": [normalize_group(str(group)) for group in order.get("decor", [])],
    }


def infer_phase(group: str, existing_order: dict[str, list[str]]) -> str | None:
    if group in existing_order["repair"]:
        return "repair"

    if group in existing_order["decor"]:
        return "decor"

    return None


def write_room_config(room_id: str, objects: list[ExportedObject]) -> None:
    config = {
        "objects": [
            {
                "id": item.id,
                "group": item.group,
                "x": item.x,
                "y": item.y,
                "width": item.width,
                "height": item.height,
            }
            for item in objects
        ]
    }

    write_json(CONFIG_DIR / f"{room_id}.json", config)


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


def write_rooms_manifest() -> None:
    rooms = []

    for config_path in sorted(CONFIG_DIR.glob("room*.json")):
        if config_path.name.endswith("_order.json") or config_path.name == "rooms.json":
            continue

        match = ROOM_CONFIG_RE.match(config_path.name)
        if match is None:
            continue

        room_number_value = int(match.group(1))
        rooms.append(
            {
                "id": f"room{room_number_value}",
                "number": room_number_value,
            }
        )

    rooms.sort(key=lambda room: room["number"])
    write_json(CONFIG_DIR / "rooms.json", {"rooms": rooms})


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
