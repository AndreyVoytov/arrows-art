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

SCRIPT_VERSION = 6
SUPPORTED_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}
IGNORED_TOP_LEVEL_DIRS = {"atlases", "src"}
MAX_ATLAS_SIZE = 2048
DEFAULT_MAX_SIZE = MAX_ATLAS_SIZE
DEFAULT_PADDING = 2
DEFAULT_PNG_COMPRESS_LEVEL = 9
DEFAULT_PNG_QUANTIZE_COLORS = 256
DEFAULT_WEBP_QUALITY = 85


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


@dataclass(frozen=True)
class AtlasPage:
    index: int
    placements: list[PlacedFrame]
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
        digest = atlas_digest(
            source_dir=source_dir,
            images=images,
            padding=args.padding,
            max_size=args.max_size,
            png_compress_level=args.png_compress_level,
            png_quantize_colors=args.png_quantize_colors,
            webp_quality=args.webp_quality,
            webp_lossless=args.webp_lossless,
        )
        cache_entry = cache.get("atlases", {}).get(atlas_name)

        if (
            not args.force
            and cache_entry
            and cache_entry.get("digest") == digest
            and cached_outputs_exist(cache_entry)
        ):
            next_cache["atlases"][atlas_name] = cache_entry
            skipped += 1
            print(f"skip {atlas_name}")
            continue

        previous_sizes = output_sizes(cached_output_paths(cache_entry))
        outputs = build_atlas(
            source_dir=source_dir,
            atlas_name=atlas_name,
            images=images,
            padding=args.padding,
            max_size=args.max_size,
            png_compress_level=args.png_compress_level,
            png_quantize_colors=args.png_quantize_colors,
            webp_quality=args.webp_quality,
            webp_lossless=args.webp_lossless,
        )
        current_sizes = output_sizes(outputs)
        next_cache["atlases"][atlas_name] = {
            "sourceDir": relative_posix(source_dir),
            "digest": digest,
            "outputs": [relative_posix(path) for path in outputs],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        built += 1
        print(f"built {atlas_name}: {format_size_changes(previous_sizes, current_sizes)}")

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
        help=f"Maximum atlas width/height, up to {MAX_ATLAS_SIZE}. Default: {DEFAULT_MAX_SIZE}.",
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
    parser.add_argument(
        "--png-compress-level",
        type=int,
        default=DEFAULT_PNG_COMPRESS_LEVEL,
        help=f"PNG zlib compression level from 0 to 9. Default: {DEFAULT_PNG_COMPRESS_LEVEL}.",
    )
    parser.add_argument(
        "--png-quantize-colors",
        type=int,
        default=DEFAULT_PNG_QUANTIZE_COLORS,
        help=(
            "Quantize PNG atlases to this many palette colors. "
            f"Use 0 for lossless RGBA PNG. Default: {DEFAULT_PNG_QUANTIZE_COLORS}."
        ),
    )
    parser.add_argument(
        "--webp-quality",
        type=int,
        default=DEFAULT_WEBP_QUALITY,
        help=f"Lossy WebP quality from 1 to 100. Default: {DEFAULT_WEBP_QUALITY}.",
    )
    parser.add_argument(
        "--webp-lossless",
        action="store_true",
        help="Write lossless WebP atlases instead of the default compressed lossy WebP.",
    )
    args = parser.parse_args(argv)

    if not 1 <= args.max_size <= MAX_ATLAS_SIZE:
        raise SystemExit(f"--max-size must be between 1 and {MAX_ATLAS_SIZE}")

    if args.padding < 0:
        raise SystemExit("--padding cannot be negative")

    if not 0 <= args.png_compress_level <= 9:
        raise SystemExit("--png-compress-level must be between 0 and 9")

    if args.png_quantize_colors != 0 and not 2 <= args.png_quantize_colors <= 256:
        raise SystemExit("--png-quantize-colors must be 0 or between 2 and 256")

    if not 1 <= args.webp_quality <= 100:
        raise SystemExit("--webp-quality must be between 1 and 100")

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


def atlas_digest(
    *,
    source_dir: Path,
    images: list[SourceImage],
    padding: int,
    max_size: int,
    png_compress_level: int,
    png_quantize_colors: int,
    webp_quality: int,
    webp_lossless: bool,
) -> str:
    payload = {
        "scriptVersion": SCRIPT_VERSION,
        "sourceDir": relative_posix(source_dir),
        "padding": padding,
        "maxSize": max_size,
        "pngCompressLevel": png_compress_level,
        "pngQuantizeColors": png_quantize_colors,
        "webpQuality": webp_quality,
        "webpLossless": webp_lossless,
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


def atlas_index_path(atlas_name: str, extension: str) -> Path:
    if extension == "png":
        return ATLASES_DIR / f"{atlas_name}.json"

    return ATLASES_DIR / f"{atlas_name}.{extension}.json"


def atlas_page_image_path(
    atlas_name: str,
    extension: str,
    page_index: int,
    page_count: int,
) -> Path:
    suffix = "" if page_count == 1 else f"_{page_index}"
    return ATLASES_DIR / f"{atlas_name}{suffix}.{extension}"


def cached_outputs_exist(cache_entry: object) -> bool:
    paths = cached_output_paths(cache_entry)
    return bool(paths) and all(path.exists() for path in paths)


def cached_output_paths(cache_entry: object) -> list[Path]:
    if not isinstance(cache_entry, dict):
        return []

    outputs = cache_entry.get("outputs")
    if not isinstance(outputs, list):
        return []

    return [ROOT / str(output) for output in outputs]


def output_sizes(outputs: Iterable[Path]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for path in outputs:
        if not path.exists() or path.suffix.lower() not in {".png", ".webp"}:
            continue

        key = path.suffix.lower().lstrip(".")
        sizes[key] = sizes.get(key, 0) + path.stat().st_size

    return sizes


def format_size_changes(previous: dict[str, int], current: dict[str, int]) -> str:
    parts = []
    for name in ("png", "webp"):
        size = current.get(name)
        if size is None:
            continue

        old_size = previous.get(name)
        if old_size is not None and old_size != size:
            parts.append(f"{name} {format_file_size(old_size)} -> {format_file_size(size)}")
        else:
            parts.append(f"{name} {format_file_size(size)}")

    return ", ".join(parts)


def format_file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"

    if size >= 1024:
        return f"{size / 1024:.0f} KB"

    return f"{size} B"


def build_atlas(
    source_dir: Path,
    atlas_name: str,
    images: list[SourceImage],
    padding: int,
    max_size: int,
    png_compress_level: int,
    png_quantize_colors: int,
    webp_quality: int,
    webp_lossless: bool,
) -> list[Path]:
    pages = pack_images(images, padding, max_size)
    page_count = len(pages)
    output_paths: list[Path] = []
    page_paths: dict[str, list[Path]] = {"png": [], "webp": []}

    for page in pages:
        atlas_image = render_atlas_page(page)
        png_path = atlas_page_image_path(atlas_name, "png", page.index, page_count)
        webp_path = atlas_page_image_path(atlas_name, "webp", page.index, page_count)

        png_image = optimize_png_image(atlas_image, png_quantize_colors)
        png_image.save(png_path, optimize=True, compress_level=png_compress_level)
        if webp_lossless:
            atlas_image.save(webp_path, lossless=True, method=6)
        else:
            atlas_image.save(webp_path, quality=webp_quality, method=6)

        page_paths["png"].append(png_path)
        page_paths["webp"].append(webp_path)
        output_paths.extend([png_path, webp_path])

    png_index_path = atlas_index_path(atlas_name, "png")
    webp_index_path = atlas_index_path(atlas_name, "webp")
    write_json(
        png_index_path,
        atlas_json(
            source_dir=source_dir,
            image_paths=page_paths["png"],
            pages=pages,
            max_size=max_size,
        ),
    )
    write_json(
        webp_index_path,
        atlas_json(
            source_dir=source_dir,
            image_paths=page_paths["webp"],
            pages=pages,
            max_size=max_size,
        ),
    )
    output_paths.extend([png_index_path, webp_index_path])

    return output_paths


def render_atlas_page(page: AtlasPage) -> Image.Image:
    atlas_image = Image.new("RGBA", (page.width, page.height), (0, 0, 0, 0))

    for placement in page.placements:
        with Image.open(placement.source.path) as source:
            atlas_image.alpha_composite(source.convert("RGBA"), (placement.x, placement.y))

    return atlas_image


def atlas_json(
    source_dir: Path,
    image_paths: list[Path],
    pages: list[AtlasPage],
    max_size: int,
) -> dict[str, object]:
    if len(pages) == 1:
        page = pages[0]
        return phaser_json(
            source_dir=source_dir,
            image_name=image_paths[0].name,
            placements=page.placements,
            width=page.width,
            height=page.height,
        )

    return multi_page_json(
        source_dir=source_dir,
        image_paths=image_paths,
        pages=pages,
        max_size=max_size,
    )


def optimize_png_image(image: Image.Image, quantize_colors: int) -> Image.Image:
    if quantize_colors == 0:
        return image

    return image.quantize(
        colors=quantize_colors,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.NONE,
    )


def pack_images(
    images: list[SourceImage],
    padding: int,
    max_size: int,
) -> list[AtlasPage]:
    too_large = [
        image
        for image in images
        if image.width > max_size or image.height > max_size
    ]
    if too_large:
        largest = max(too_large, key=lambda image: image.width * image.height)
        raise SystemExit(
            f"Frame is larger than {max_size}x{max_size}: "
            f"{largest.path.name} ({largest.width}x{largest.height})."
        )

    remaining = sorted(images, key=image_sort_key, reverse=True)
    pages: list[AtlasPage] = []

    while remaining:
        placements, width, height = try_pack_page(remaining, max_size, padding)
        if not placements:
            largest = max(remaining, key=lambda image: image.width * image.height)
            raise SystemExit(
                "Could not pack atlas page. "
                f"Largest remaining frame: {largest.path.name} "
                f"({largest.width}x{largest.height})."
            )

        pages.append(
            AtlasPage(
                index=len(pages) + 1,
                placements=placements,
                width=width,
                height=height,
            )
        )
        used_paths = {placement.source.path for placement in placements}
        remaining = [image for image in remaining if image.path not in used_paths]

    return pages


def try_pack_page(
    images: list[SourceImage],
    max_size: int,
    padding: int,
) -> tuple[list[PlacedFrame], int, int]:
    shelves: list[dict[str, int]] = []
    placements: list[PlacedFrame] = []

    for image in sorted(images, key=image_sort_key, reverse=True):
        shelf = first_shelf_that_fits(shelves, image, max_size, padding)
        if shelf is None:
            y = shelves[-1]["y"] + shelves[-1]["height"] + padding if shelves else 0
            if y + image.height > max_size:
                continue

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

    if not placements:
        return [], 0, 0

    atlas_width = min(
        max_size,
        next_power_of_two(max(placement.x + placement.width for placement in placements)),
    )
    atlas_height = max(placement.y + placement.height for placement in placements)
    return placements, atlas_width, max(1, atlas_height)


def image_sort_key(image: SourceImage) -> tuple[int, int, int, str]:
    return (
        image.height,
        image.width,
        image.width * image.height,
        image.path.name.lower(),
    )


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


def multi_page_json(
    source_dir: Path,
    image_paths: list[Path],
    pages: list[AtlasPage],
    max_size: int,
) -> dict[str, object]:
    return {
        "pages": [
            {
                "image": image_path.name,
                "frames": frames_json(page.placements),
                "size": {
                    "w": page.width,
                    "h": page.height,
                },
            }
            for image_path, page in zip(image_paths, pages)
        ],
        "meta": {
            "app": "scripts/build_atlases.py",
            "version": str(SCRIPT_VERSION),
            "format": "RGBA8888",
            "scale": "1",
            "sourceDir": relative_posix(source_dir),
            "pageCount": len(pages),
            "maxSize": max_size,
        },
    }


def phaser_json(
    source_dir: Path,
    image_name: str,
    placements: list[PlacedFrame],
    width: int,
    height: int,
) -> dict[str, object]:
    return {
        "frames": frames_json(placements),
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


def frames_json(placements: list[PlacedFrame]) -> dict[str, object]:
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

    return frames


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
