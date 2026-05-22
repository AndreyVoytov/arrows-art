from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(script_name: str, args: list[str] | None = None) -> None:
    command = [sys.executable, str(SCRIPT_DIR / script_name), *(args or [])]
    subprocess.run(command, check=True)
