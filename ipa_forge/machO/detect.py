# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight Mach-O detection by magic number, used by the bundle inventory walker."""

from __future__ import annotations

import struct
from pathlib import Path

from ipa_forge.bundle.models import AppBundle, MachOKind

_MACHO_MAGICS = {
    0xFEEDFACE,  # MH_MAGIC (32-bit)
    0xFEEDFACF,  # MH_MAGIC_64
    0xCEFAEDFE,  # MH_CIGAM (32-bit, byte-swapped)
    0xCFFAEDFE,  # MH_CIGAM_64
    0xCAFEBABE,  # FAT_MAGIC
    0xBEBAFECA,  # FAT_CIGAM
}


def is_macho_file(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with open(path, "rb") as f:
            header = f.read(4)
    except OSError:
        return False
    if len(header) < 4:
        return False
    (magic,) = struct.unpack(">I", header)
    return magic in _MACHO_MAGICS


def bundle_executable_paths(bundle: AppBundle, kinds: set[MachOKind] | None = None) -> list[Path]:
    """Every on-disk executable in the bundle, main binary first: the main
    executable plus each `MachOTarget` whose `kind` is in `kinds` (default:
    every kind -- main, framework, dylib, appex, watch_app, other). Callers
    doing a narrower analysis (e.g. hook verification, which only cares
    about app code) pass an explicit, smaller `kinds` set."""
    paths = [bundle.root / bundle.main_executable_name]
    for target in bundle.executables:
        # the main executable is always target.kind == "main" and already
        # covered by the first line above -- skip it here or it'd be listed
        # (and analyzed) twice.
        if target.kind == "main":
            continue
        if kinds is None or target.kind in kinds:
            paths.append(bundle.extraction_root / Path(target.bundle_relative))
    return [p for p in paths if p.is_file()]
