from __future__ import annotations

import argparse
import logging
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

try:
    from PIL import Image
    from psd_tools import PSDImage
except ImportError as error:
    raise SystemExit(
        "prepare-ui requires Python packages `psd-tools` and `Pillow`."
    ) from error


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "images" / "src" / "ui"
OUTPUT_DIR = ROOT / "images" / "ui"
TARGET_WIDTH = 720
HIDDEN_LAYER_PREFIX = "_"
PREVIEW_NAME = "_preview.png"
LOBBY_PREVIEW_WITHOUT_SECOND_GROUP_NAME = "_preview2.png"
LOBBY_PSD_NAME = "lobby"
PANEL_DIR_NAME = "panel"
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


@dataclass
class OutputState:
    exported: set[str] = field(default_factory=set)
    used_names: set[str] = field(default_factory=set)
    layer_count: int = 0


def main(argv: list[str] | None = None) -> None:
    logging.getLogger("psd_tools").setLevel(logging.ERROR)
    args = parse_args(argv)
    src_dir = resolve_path(args.src_dir)
    output_dir = resolve_path(args.output_dir)

    if not src_dir.exists():
        raise SystemExit(f"PSD source directory does not exist: {relative(src_dir)}")

    psd_paths = sorted(path for path in src_dir.glob("*.psd") if path.is_file())
    if not psd_paths:
        raise SystemExit(f"No PSD files found in {relative(src_dir)}")

    states: dict[Path, OutputState] = {}
    for psd_path in psd_paths:
        target_dir = output_dir / target_dir_name(psd_path)
        state = states.setdefault(target_dir, OutputState())
        export_ui_psd(psd_path, target_dir, state)

    for target_dir, state in states.items():
        remove_stale_pngs(target_dir, output_dir, state.exported)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export lobby UI assets into images/ui/lobby and other UI assets into images/ui/panel."
    )
    parser.add_argument(
        "--src-dir",
        default=str(SRC_DIR),
        help="Directory with UI PSD files. Defaults to images/src/ui.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory for exported UI PNGs. Defaults to images/ui.",
    )
    return parser.parse_args(argv)


def target_dir_name(psd_path: Path) -> str:
    return LOBBY_PSD_NAME if psd_path.stem == LOBBY_PSD_NAME else PANEL_DIR_NAME


def export_ui_psd(psd_path: Path, output_dir: Path, state: OutputState) -> None:
    psd = PSDImage.open(psd_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    scale = TARGET_WIDTH / psd.width

    preview_names = preview_file_names(psd_path)
    for preview_name in preview_names:
        preview = preview_image(psd, preview_name).convert("RGBA")
        preview = resize_image(preview, scale)
        preview_path = output_dir / preview_name
        save_png(preview, preview_path)
        state.exported.add(preview_path.name)
        state.used_names.add(preview_path.stem)

    layer_count = 0
    for layer in iter_export_layers(psd):
        image = export_layer(layer, psd.width, psd.height, scale)
        if image is None:
            continue

        name = unique_file_stem(sanitize_file_stem(layer.name), state.used_names)
        state.used_names.add(name)
        output_path = output_dir / f"{name}.png"
        save_png(image, output_path)
        state.exported.add(output_path.name)
        layer_count += 1

    state.layer_count += layer_count
    print(f"prepared ui {psd_path.stem}: {layer_count} layers + {len(preview_names)} preview")


def preview_file_names(psd_path: Path) -> list[str]:
    if psd_path.stem == LOBBY_PSD_NAME:
        return [PREVIEW_NAME, LOBBY_PREVIEW_WITHOUT_SECOND_GROUP_NAME]

    return [f"_{psd_path.stem}_preview.png"]


def preview_image(psd: PSDImage, preview_name: str) -> Image.Image:
    if preview_name != LOBBY_PREVIEW_WITHOUT_SECOND_GROUP_NAME:
        return psd.composite(ignore_preview=True)

    group = second_top_level_group(psd)
    if group is None:
        return psd.composite(ignore_preview=True)

    with temporary_visibility([group], visible=False):
        return psd.composite(ignore_preview=True)


def second_top_level_group(psd: PSDImage) -> object | None:
    groups = [layer for layer in psd if layer.is_group()]
    return groups[1] if len(groups) > 1 else None


def iter_export_layers(psd: PSDImage) -> Iterable[object]:
    def walk(layers: Iterable[object], skipped: bool = False) -> Iterable[object]:
        for layer in layers:
            layer_name = normalized_layer_name(layer.name)
            layer_skipped = skipped or layer_name.startswith(HIDDEN_LAYER_PREFIX)

            if layer.is_group():
                yield from walk(layer, layer_skipped)
                continue

            if layer_skipped or not layer.has_pixels():
                continue

            yield layer

    yield from walk(psd)


def export_layer(layer: object, psd_width: int, psd_height: int, scale: float) -> Image.Image | None:
    with temporary_visibility(layer_visibility_chain(layer), visible=True):
        canvas = layer.composite(viewport=(0, 0, psd_width, psd_height), force=True)

    if canvas is None:
        return None

    canvas = canvas.convert("RGBA")

    canvas = resize_image(canvas, scale)
    alpha_bounds = canvas.getchannel("A").getbbox()
    if alpha_bounds is None:
        return None

    cropped = canvas.crop(alpha_bounds)
    scrub_transparent_pixels(cropped)
    return cropped


def layer_visibility_chain(layer: object) -> list[object]:
    layers = []
    current = layer

    while current is not None and hasattr(current, "visible"):
        layers.append(current)
        current = getattr(current, "parent", None)

    return layers


@contextmanager
def temporary_visibility(layers: object | Iterable[object], *, visible: bool) -> Iterator[None]:
    layer_list = layers if isinstance(layers, list) else [layers]
    previous: list[tuple[object, bool]] = []

    try:
        for layer in layer_list:
            if not hasattr(layer, "visible"):
                continue

            previous.append((layer, layer.visible))
            try:
                layer.visible = visible
            except AttributeError:
                previous.pop()

        yield
    finally:
        for layer, was_visible in reversed(previous):
            layer.visible = was_visible


def resize_image(image: Image.Image, scale: float) -> Image.Image:
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    if image.size == size:
        return image

    resized = image.resize(size, Image.Resampling.LANCZOS)
    scrub_transparent_pixels(resized)
    return resized


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


def remove_stale_pngs(output_dir: Path, output_root: Path, exported: set[str]) -> None:
    output_root = output_root.resolve()
    resolved_output = output_dir.resolve()
    try:
        resolved_output.relative_to(output_root)
    except ValueError as error:
        raise RuntimeError(f"Refusing to clean path outside images/ui: {resolved_output}") from error

    for png_path in output_dir.glob("*.png"):
        if png_path.name not in exported:
            png_path.unlink()


def normalized_layer_name(name: object) -> str:
    return str(name).strip()


def sanitize_file_stem(name: object) -> str:
    normalized = normalized_layer_name(name)
    normalized = INVALID_FILENAME_CHARS_RE.sub("_", normalized)
    normalized = re.sub(r"\s+", "_", normalized).strip(" ._")
    return normalized or "layer"


def unique_file_stem(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        return name

    index = 2
    while f"{name}_{index}" in used_names:
        index += 1

    return f"{name}_{index}"


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"prepare-ui failed: {error}", file=sys.stderr)
        raise
