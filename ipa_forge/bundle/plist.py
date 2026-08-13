"""Info.plist read/write helpers (binary or XML plist, transparently)."""
from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any


def read_plist(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return plistlib.load(f)


def write_plist(path: Path, data: dict[str, Any]) -> None:
    with open(path, "wb") as f:
        plistlib.dump(data, f)
