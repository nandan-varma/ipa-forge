# SPDX-License-Identifier: GPL-3.0-or-later
"""Linked libraries + imported/exported symbols for a Mach-O executable --
`otool -L` + `nm`, backed by LIEF's structured symbol table instead of
shelling out and parsing text."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import lief

from ipa_forge.machO.arch import arch_name, load_macho


@dataclass
class BinarySymbols:
    binary: str
    arch: str
    linked_libraries: list[str] = field(default_factory=list)
    imported_symbols: list[str] = field(default_factory=list)
    exported_symbols: list[str] = field(default_factory=list)


def analyze_symbols(path: Path, arch: str | None = None) -> BinarySymbols:
    """Fat binaries require an explicit `arch` -- same rule `forge patch`'s
    binary operations follow (see `machO/arch.py::load_macho`); a thin
    binary needs none."""
    binary = load_macho(path, arch)
    # CATEGORY.UNDEFINED: referenced here, defined in another image (an
    # import). CATEGORY.EXTERNAL: defined in this image and globally
    # visible (an export). CATEGORY.LOCAL: internal-only, not exported.
    imported = sorted({str(s.name) for s in binary.symbols if s.category == lief.MachO.Symbol.CATEGORY.UNDEFINED})
    exported = sorted({str(s.name) for s in binary.symbols if s.category == lief.MachO.Symbol.CATEGORY.EXTERNAL})
    libraries = sorted({str(lib.name) for lib in binary.libraries})
    return BinarySymbols(
        binary=path.name,
        arch=arch_name(binary),
        linked_libraries=libraries,
        imported_symbols=imported,
        exported_symbols=exported,
    )
