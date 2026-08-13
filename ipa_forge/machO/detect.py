"""Lightweight Mach-O detection by magic number, used by the bundle inventory walker."""
from __future__ import annotations

import struct
from pathlib import Path

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
