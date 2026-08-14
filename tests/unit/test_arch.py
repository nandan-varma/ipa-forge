# SPDX-License-Identifier: GPL-3.0-or-later
"""Mach-O arch selection edge cases: thin vs fat, explicit-arch enforcement,
and every error path in ipa_forge.machO.arch."""

from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.machO.arch import (
    AmbiguousArchError,
    ArchNotFoundError,
    NotMachOError,
    arch_name,
    available_archs,
    load_macho,
    slice_byte_range,
)

_HOST_ARCHES = {"arm64", "x86_64"}


def _garbage_file(tmp_path: Path) -> Path:
    bogus = tmp_path / "not_macho"
    bogus.write_bytes(b"definitely not a mach-o file" * 100)
    return bogus


def test_load_macho_thin_returns_slice(compiled_macho_binary: Path) -> None:
    binary = load_macho(compiled_macho_binary)
    assert arch_name(binary) in _HOST_ARCHES


def test_load_macho_thin_ignores_arch_arg(compiled_macho_binary: Path) -> None:
    """A thin binary is returned as-is even when an arch is requested."""
    binary = load_macho(compiled_macho_binary, arch="arm64")
    assert arch_name(binary) in _HOST_ARCHES


def test_load_macho_invalid_file_raises(tmp_path: Path) -> None:
    with pytest.raises(NotMachOError):
        load_macho(_garbage_file(tmp_path))


def test_load_macho_universal_requires_explicit_arch(fat_macho_binary: Path) -> None:
    with pytest.raises(AmbiguousArchError, match="arm64"):
        load_macho(fat_macho_binary)
    with pytest.raises(AmbiguousArchError, match="x86_64"):
        load_macho(fat_macho_binary)


def test_load_macho_universal_unknown_arch_raises(fat_macho_binary: Path) -> None:
    with pytest.raises(ArchNotFoundError, match="armv7"):
        load_macho(fat_macho_binary, arch="armv7")


def test_load_macho_universal_selects_arch(fat_macho_binary: Path) -> None:
    arm = load_macho(fat_macho_binary, arch="arm64")
    assert arch_name(arm) == "arm64"
    x86 = load_macho(fat_macho_binary, arch="x86_64")
    assert arch_name(x86) == "x86_64"


def test_available_archs_lists_all_slices(fat_macho_binary: Path) -> None:
    assert set(available_archs(fat_macho_binary)) == {"arm64", "x86_64"}


def test_available_archs_invalid_file_raises(tmp_path: Path) -> None:
    with pytest.raises(NotMachOError):
        available_archs(_garbage_file(tmp_path))


def test_slice_byte_range_thin_is_whole_file(compiled_macho_binary: Path) -> None:
    start, end = slice_byte_range(compiled_macho_binary)
    assert start == 0
    assert end == compiled_macho_binary.stat().st_size


def test_slice_byte_range_fat_bounds_each_slice(fat_macho_binary: Path) -> None:
    size = fat_macho_binary.stat().st_size
    arm64_range = slice_byte_range(fat_macho_binary, arch="arm64")
    x86_64_range = slice_byte_range(fat_macho_binary, arch="x86_64")
    for start, end in (arm64_range, x86_64_range):
        assert 0 <= start < end <= size
    # the two slices occupy distinct byte ranges
    assert arm64_range != x86_64_range
