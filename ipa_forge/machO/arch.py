# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only fat/universal Mach-O architecture selection, backed by LIEF."""

from __future__ import annotations

from pathlib import Path

import lief

_ARCH_NAMES: dict[lief.MachO.Header.CPU_TYPE, str] = {
    lief.MachO.Header.CPU_TYPE.ARM64: "arm64",
    lief.MachO.Header.CPU_TYPE.ARM: "armv7",
    lief.MachO.Header.CPU_TYPE.X86_64: "x86_64",
    lief.MachO.Header.CPU_TYPE.X86: "i386",
}


class NotMachOError(Exception):
    """Raised when the target file cannot be parsed as Mach-O at all."""


class AmbiguousArchError(Exception):
    """Raised when a fat/universal binary is targeted without an explicit `arch:` selector."""


class ArchNotFoundError(Exception):
    """Raised when an explicit `arch:` selector does not match any slice in the binary."""


def arch_name(binary: lief.MachO.Binary) -> str:
    """Canonical arch name (e.g. "arm64") for a parsed Mach-O slice."""
    return _ARCH_NAMES.get(binary.header.cpu_type, str(binary.header.cpu_type))


def require_slice(fat: lief.MachO.FatBinary, index: int) -> lief.MachO.Binary:
    """LIEF's FatBinary.at() is typed as Optional; callers only use it after a
    non-empty length check, so a None here means the file changed under us."""
    binary = fat.at(index)
    if binary is None:
        raise NotMachOError(f"Mach-O slice {index} unexpectedly missing")
    return binary


def load_macho(path: Path, arch: str | None = None) -> lief.MachO.Binary:
    """Return the single Mach-O slice to operate on.

    Thin binaries are returned directly. Fat/universal binaries require an
    explicit `arch` selector -- silently picking "the first slice" would make
    patches applied to the wrong architecture on a per-device basis.
    """
    fat = lief.MachO.parse(str(path))
    if fat is None or len(fat) == 0:
        raise NotMachOError(f"{path} is not a valid Mach-O file")

    if len(fat) == 1:
        return require_slice(fat, 0)

    available = [arch_name(require_slice(fat, i)) for i in range(len(fat))]
    if arch is None:
        raise AmbiguousArchError(
            f"{path} is a universal binary with architectures {available}; "
            "an explicit `arch:` selector is required in the patch definition"
        )
    for i in range(len(fat)):
        binary = require_slice(fat, i)
        if arch_name(binary) == arch:
            return binary
    raise ArchNotFoundError(f"Architecture '{arch}' not found in {path}; available: {available}")


def available_archs(path: Path) -> list[str]:
    fat = lief.MachO.parse(str(path))
    if fat is None or len(fat) == 0:
        raise NotMachOError(f"{path} is not a valid Mach-O file")
    return [arch_name(require_slice(fat, i)) for i in range(len(fat))]


def slice_byte_range(path: Path, arch: str | None = None) -> tuple[int, int]:
    """Return the (start, end) byte offsets of the selected arch's slice within
    the on-disk file. For thin (non-fat) binaries this is the whole file --
    used to bound binary-pattern search/replace to the correct architecture
    so a patch never silently lands in the wrong slice of a universal binary.
    """
    fat = lief.MachO.parse(str(path))
    if fat is None or len(fat) == 0:
        raise NotMachOError(f"{path} is not a valid Mach-O file")

    if len(fat) == 1:
        return 0, path.stat().st_size

    binary = load_macho(path, arch)
    return binary.fat_offset, binary.fat_offset + binary.original_size
