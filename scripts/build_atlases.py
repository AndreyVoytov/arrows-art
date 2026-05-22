from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image, features
except ImportError as error:
    raise SystemExit(
        "build-atlases requires Python package `Pillow`."
    ) from error


ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "images"
ATLASES_DIR = IMAGES_DIR / "atlases"
CACHE_PATH = ATLASES_DIR / ".atlas-cache.json"

SCRIPT_VERSION = 1
SUPPORTED_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}
IGNORED_TOP_LEVEL_DIRS = {"atlases", "src"}
DEFAULT_MAX_SIZE = 4096
DEFAULT_PADDING = 2


@dataclass(frozen=True)
class SourceImage:
    path: Path
    frame_name: str
    digest: str
    width: int
    height: int


@dataclass(frozen=True)
class PlacedFrame:
    source: SourceImage
    x: int
    y: int
    width: int
    height: int


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    validate_webp_support()

    ATLASES_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_cache()
    next_cache = {
        "version": SCRIPT_VERSION,
        "atlases": {},
    }

    built = 0
    skipped = 0

    for source_dir in discover_source_dirs():
        images = load_source_images(source_dir)
        if not images:
            continue

        atlas_name = atlas_name_for(source_dir)
        digest = atlas_digest(source_dir, images, args.padding, args.max_size)
        outputs = atlas_outputs(atlas_name)
        cache_entry = cache.get("atlases", {}).get(atlas_name)

        if (
            not args.force
            and cache_entry
            and cache_entry.get("digest") == digest
            and outputs_exist(outputs)
        ):
            next_cache["atlases"][atlas_name] = cache_entry
            skipped += 1
            print(f"skip {atlas_name}")
            continue

        build_atlas(source_dir, atlas_name, images, outputs, args.padding, args.max_size)
        next_cache["atlases"][atlas_name] = {
            "sourceDir": relative_posix(source_dir),
            "digest": digest,
            "outputs": [relative_posix(path) for path in outputs.values()],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        built += 1
        print(f"built {atlas_name}")

    remove_stale_outputs(cache, next_cache)
    write_json(CACHE_PATH, next_cache)
    print(f"atlases: {built} built, {skipped} skipped")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build Phaser 3 JSON atlases for second-level image directories, "
            "for example images/rooms/room1."
        )
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=DEFAULT_MAX_SIZE,
        help=f"Maximum atlas width/height. Default: {DEFAULT_MAX_SIZE}.",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=DEFAULT_PADDING,
        help=f"Pixels between frames. Default: {DEFAULT_PADDING}.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild all atlases even when input hashes did not change.",
    )
    args = parser.parse_args(argv)

    if args.max_size <= 0:
        raise SystemExit("--max-size must be greater than zero")

    if args.padding < 0:
        raise SystemExit("--padding cannot be negative")

    return args


def validate_webp_support() -> None:
    if not features.check("webp"):
        raise SystemExit("Pillow was built without WebP support.")


def discover_source_dirs() -> Iterable[Path]:
    if not IMAGES_DIR.exists():
        return []

    source_dirs: list[Path] = []
    for parent in sorted(path for path in IMAGES_DIR.iterdir() if path.is_dir()):
        if parent.name in IGNORED_TOP_LEVEL_DIRS:
            continue

        for child in sorted(path for path in parent.iterdir() if path.is_dir()):
            if contains_supported_image(child):
                source_dirs.append(child)

    return source_dirs


def contains_supported_image(directory: Path) -> bool:
    return any(
        path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        for path in directory.iterdir()
    )


def load_source_images(source_dir: Path) -> list[SourceImage]:
    paths = [
        path
        for path in sorted(source_dir.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    frame_names = unique_frame_names(paths)
    images: list[SourceImage] = []

    for path in paths:
        with Image.open(path) as image:
            width, height = image.size

        images.append(
            SourceImage(
                path=path,
                frame_name=frame_names[path],
                digest=file_sha256(path),
                width=width,
                height=height,
            )
        )

    return images


def unique_frame_names(paths: list[Path]) -> dict[Path, str]:
    stem_counts: dict[str, int] = {}
    for path in paths:
        stem_counts[path.stem] = stem_counts.get(path.stem, 0) + 1

    return {
        path: path.stem if stem_counts[path.stem] == 1 else path.name
        for path in paths
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def atlas_digest(source_dir: Path, images: list[SourceImage], padding: int, max_size: int) -> str:
    payload = {
        "scriptVersion": SCRIPT_VERSION,
        "sourceDir": relative_posix(source_dir),
        "padding": padding,
        "maxSize": max_size,
        "images": [
            {
                "path": relative_posix(image.path),
                "frameName": image.frame_name,
                "sha256": image.digest,
                "width": image.width,
                "height": image.height,
            }
            for image in images
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atlas_outputs(atlas_name: str) -> dict[str, Path]:
    return {
        "png": ATLASES_DIR / f"{atlas_name}.png",
        "pngJson": ATLASES_DIR / f"{atlas_name}.json",
        "webp": ATLASES_DIR / f"{atlas_name}.webp",
        "webpJson": ATLASES_DIR / f"{atlas_name}.webp.json",
    }


def outputs_exist(outputs: dict[str, Path]) -> bool:
    return all(path.exists() for path in outputs.values())


def build_atlas(
    source_dir: Path,
    atlas_name: str,
    images: list[SourceImage],
    outputs: dict[str, Path],
    padding: int,
    max_size: int,
) -> None:
    placements, width, height = pack_images(images, padding, max_size)
    atlas_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for placement in placements:
        with Image.open(placement.source.path) as source:
            atlas_image.alpha_composite(source.convert("RGBA"), (placement.x, placement.y))

    atlas_image.save(outputs["png"], optimize=True)
    atlas_image.save(outputs["webp"], lossless=True, method=6)

    png_data = phaser_json(
        source_dir=source_dir,
        image_name=outputs["png"].name,
        placements=placements,
        width=width,
        height=height,
    )
    webp_data = phaser_json(
        source_dir=source_dir,
        image_name=outputs["webp"].name,
        placements=placements,
        width=width,
        height=height,
    )

    write_json(outputs["pngJson"], png_data)
    write_json(outputs["webpJson"], webp_data)


def pack_images(
    images: list[SourceImage],
    padding: int,
    max_size: int,
) -> tuple[list[PlacedFrame], int, int]:
    min_width = max(image.width for image in images)
    total_area = sum((image.width + padding) * (image.height + padding) for image in images)
    width = max(next_power_of_two(max(min_width, int(total_area ** 0.5))), 1)
    width = min(width, max_size)

    while width <= max_size:
        placements, height = try_pack(images, width, padding)
        if placements and height <= max_size:
            return placements, width, max(1, height)

        width *= 2

    largest = max(images, key=lambda image: image.width * image.height)
    raise SystemExit(
        "Could not pack atlas. "
        f"Try a larger --max-size. Largest frame: {largest.path.name} "
        f"({largest.width}x{largest.height})."
    )


def try_pack(
    images: list[SourceImage],
    atlas_width: int,
    padding: int,
) -> tuple[list[PlacedFrame], int]:
    sorted_images = sorted(
        images,
        key=lambda image: (image.height, image.width, image.path.name.lower()),
        reverse=True,
    )
    shelves: list[dict[str, int]] = []
    placements: list[PlacedFrame] = []

    for image in sorted_images:
        if image.width > atlas_width:
            return [], 0

        shelf = first_shelf_that_fits(shelves, image, atlas_width, padding)
        if shelf is None:
            y = shelves[-1]["y"] + shelves[-1]["height"] + padding if shelves else 0
            shelf = {
                "x": 0,
                "y": y,
                "height": image.height,
            }
            shelves.append(shelf)

        placements.append(
            PlacedFrame(
                source=image,
                x=shelf["x"],
                y=shelf["y"],
                width=image.width,
                height=image.height,
            )
        )
        shelf["x"] += image.width + padding

    atlas_height = max(
        placement.y + placement.height
        for placement in placements
    )
    return placements, atlas_height


def first_shelf_that_fits(
    shelves: list[dict[str, int]],
    image: SourceImage,
    atlas_width: int,
    padding: int,
) -> dict[str, int] | None:
    for shelf in shelves:
        if image.height <= shelf["height"] and shelf["x"] + image.width <= atlas_width:
            return shelf

    return None


def phaser_json(
    source_dir: Path,
    image_name: str,
    placements: list[PlacedFrame],
    width: int,
    height: int,
) -> dict[str, object]:
    frames = {}
    for placement in sorted(placements, key=lambda item: item.source.frame_name):
        frames[placement.source.frame_name] = {
            "frame": {
                "x": placement.x,
                "y": placement.y,
                "w": placement.width,
                "h": placement.height,
            },
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {
                "x": 0,
                "y": 0,
                "w": placement.width,
                "h": placement.height,
            },
            "sourceSize": {
                "w": placement.width,
                "h": placement.height,
            },
        }

    return {
        "frames": frames,
        "meta": {
            "app": "scripts/build_atlases.py",
            "version": str(SCRIPT_VERSION),
            "image": image_name,
            "format": "RGBA8888",
            "size": {
                "w": width,
                "h": height,
            },
            "scale": "1",
            "sourceDir": relative_posix(source_dir),
        },
    }


def next_power_of_two(value: int) -> int:
    result = 1
    while result < value:
        result *= 2

    return result


def atlas_name_for(source_dir: Path) -> str:
    relative = source_dir.relative_to(IMAGES_DIR)
    raw = "_".join(relative.parts)
    return sanitize_name(raw)


def sanitize_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "atlas"


def load_cache() -> dict[str, object]:
    if not CACHE_PATH.exists():
        return {"version": SCRIPT_VERSION, "atlases": {}}

    with CACHE_PATH.open("r", encoding="utf-8") as file:
        cache = json.load(file)

    if not isinstance(cache, dict) or not isinstance(cache.get("atlases"), dict):
        return {"version": SCRIPT_VERSION, "atlases": {}}

    return cache


def remove_stale_outputs(
    previous_cache: dict[str, object],
    next_cache: dict[str, object],
) -> None:
    active_outputs = {
        output
        for entry in next_cache.get("atlases", {}).values()
        for output in entry.get("outputs", [])
    }

    for entry in previous_cache.get("atlases", {}).values():
        for output in entry.get("outputs", []):
            if output in active_outputs:
                continue

            path = ROOT / output
            if is_atlas_output(path) and path.exists():
                path.unlink()


def is_atlas_output(path: Path) -> bool:
    try:
        path.resolve().relative_to(ATLASES_DIR.resolve())
    except ValueError:
        return False

    return path.suffix.lower() in {".png", ".webp", ".json"}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def relative_posix(path: Path) -> str:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        relative = path

    return relative.as_posix()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"build-atlases failed: {error}", file=sys.stderr)
        raise
