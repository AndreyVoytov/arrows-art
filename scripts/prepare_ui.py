from __future__ import annotations

import argparse
import logging
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from math import ceil, cos, radians, sin
from pathlib import Path
from typing import Iterable, Iterator

try:
    from PIL import Image, ImageFilter
    from psd_tools import PSDImage
    from psd_tools.api.effects import DropShadow
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
        image = export_layer(layer, scale)
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


def export_layer(layer: object, scale: float) -> Image.Image | None:
    viewport = layer_export_viewport(layer)

    with temporary_visibility(layer_visibility_chain(layer), visible=True):
        canvas = layer.composite(viewport=viewport, force=True)

    if canvas is None:
        return None

    canvas = canvas.convert("RGBA")
    canvas = apply_drop_shadows(canvas, layer)

    canvas = resize_image(canvas, scale)
    alpha_bounds = canvas.getchannel("A").getbbox()
    if alpha_bounds is None:
        return None

    cropped = canvas.crop(alpha_bounds)
    scrub_transparent_pixels(cropped)
    return cropped


def layer_export_viewport(layer: object) -> tuple[int, int, int, int]:
    left, top, right, bottom = map(int, layer.bbox)
    margin_left, margin_top, margin_right, margin_bottom = effect_margins(layer)
    return (
        left - margin_left,
        top - margin_top,
        right + margin_right,
        bottom + margin_bottom,
    )


def effect_margins(layer: object) -> tuple[int, int, int, int]:
    margins = [0, 0, 0, 0]
    effects = getattr(layer, "effects", None)
    if not effects:
        return tuple(margins)

    for effect in effects:
        if not getattr(effect, "enabled", False):
            continue

        if isinstance(effect, DropShadow):
            dx, dy = shadow_offset(effect)
            blur_margin = ceil(shadow_blur_radius(effect) * 3) + 2
            margins[0] = max(margins[0], ceil(max(0, -dx)) + blur_margin)
            margins[1] = max(margins[1], ceil(max(0, -dy)) + blur_margin)
            margins[2] = max(margins[2], ceil(max(0, dx)) + blur_margin)
            margins[3] = max(margins[3], ceil(max(0, dy)) + blur_margin)
            continue

        margins = [max(value, 64) for value in margins]

    return tuple(margins)


def apply_drop_shadows(image: Image.Image, layer: object) -> Image.Image:
    effects = getattr(layer, "effects", None)
    if not effects:
        return image

    shadows = []
    for effect in effects:
        if isinstance(effect, DropShadow) and getattr(effect, "enabled", False):
            shadow = render_drop_shadow(image, effect)
            if shadow is not None:
                shadows.append(shadow)

    if not shadows:
        return image

    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for shadow in shadows:
        result.alpha_composite(shadow)

    result.alpha_composite(image)
    return result


def render_drop_shadow(image: Image.Image, effect: DropShadow) -> Image.Image | None:
    alpha = image.getchannel("A")
    if alpha.getbbox() is None:
        return None

    alpha = apply_shadow_choke(alpha, effect)
    blur_radius = shadow_blur_radius(effect)
    if blur_radius > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(blur_radius))

    dx, dy = shadow_offset(effect)
    alpha = offset_alpha(alpha, round(dx), round(dy))
    alpha = alpha.point(lambda value: round(value * shadow_opacity(effect)))

    color = shadow_color(effect)
    shadow = Image.new("RGBA", image.size, (*color, 0))
    shadow.putalpha(alpha)
    return shadow


def apply_shadow_choke(alpha: Image.Image, effect: DropShadow) -> Image.Image:
    choke = max(0.0, float(getattr(effect, "choke", 0.0) or 0.0))
    if choke <= 0:
        return alpha

    radius = max(1, round(shadow_blur_radius(effect) * choke / 100))
    kernel_size = radius * 2 + 1
    return alpha.filter(ImageFilter.MaxFilter(kernel_size))


def offset_alpha(alpha: Image.Image, dx: int, dy: int) -> Image.Image:
    shifted = Image.new("L", alpha.size, 0)
    source_left = max(0, -dx)
    source_top = max(0, -dy)
    source_right = min(alpha.width, alpha.width - dx)
    source_bottom = min(alpha.height, alpha.height - dy)

    if source_left >= source_right or source_top >= source_bottom:
        return shifted

    target_left = max(0, dx)
    target_top = max(0, dy)
    source = alpha.crop((source_left, source_top, source_right, source_bottom))
    shifted.paste(source, (target_left, target_top))
    return shifted


def shadow_offset(effect: DropShadow) -> tuple[float, float]:
    angle = radians(float(getattr(effect, "angle", 0.0) or 0.0))
    distance = float(getattr(effect, "distance", 0.0) or 0.0)
    return cos(angle) * distance, sin(angle) * distance


def shadow_blur_radius(effect: DropShadow) -> float:
    return max(0.0, float(getattr(effect, "size", 0.0) or 0.0))


def shadow_opacity(effect: DropShadow) -> float:
    return max(0.0, min(1.0, float(getattr(effect, "opacity", 0.0) or 0.0) / 100))


def shadow_color(effect: DropShadow) -> tuple[int, int, int]:
    color = getattr(effect, "color", {}) or {}
    return (
        round(float(color.get(b"Rd  ", 0))),
        round(float(color.get(b"Grn ", 0))),
        round(float(color.get(b"Bl  ", 0))),
    )


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
