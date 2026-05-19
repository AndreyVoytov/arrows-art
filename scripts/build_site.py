from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "_site"
ROOM_CONFIG_RE = re.compile(r"^room(\d+)\.json$", re.IGNORECASE)


def main() -> None:
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)

    SITE_DIR.mkdir()

    for filename in ("index.html", "styles.css", "game.js"):
        shutil.copy2(ROOT / filename, SITE_DIR / filename)

    copy_config()
    copy_images()
    write_rooms_manifest()


def copy_config() -> None:
    target = SITE_DIR / "config"
    target.mkdir()

    for source in (ROOT / "config").glob("*.json"):
        if source.name == "rooms.json":
            continue

        shutil.copy2(source, target / source.name)


def copy_images() -> None:
    source = ROOT / "images"
    target = SITE_DIR / "images"

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {"src"} if "src" in names else set()

    shutil.copytree(source, target, ignore=ignore)


def write_rooms_manifest() -> None:
    rooms = []

    for config_path in sorted((SITE_DIR / "config").glob("room*.json")):
        if config_path.name.endswith("_order.json"):
            continue

        match = ROOM_CONFIG_RE.match(config_path.name)
        if match is None:
            continue

        number = int(match.group(1))
        rooms.append({"id": f"room{number}", "number": number})

    rooms.sort(key=lambda room: room["number"])

    with (SITE_DIR / "config" / "rooms.json").open("w", encoding="utf-8", newline="\n") as file:
        json.dump({"rooms": rooms}, file, ensure_ascii=False, indent=2)
        file.write("\n")


if __name__ == "__main__":
    main()
