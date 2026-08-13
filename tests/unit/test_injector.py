# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import lief

from ipa_forge.machO.injector import InjectionStatus, inject_dylib


def test_inject_into_fresh_binary_returns_injected(compiled_macho_binary: Path):
    result = inject_dylib(compiled_macho_binary, "@rpath/libFoo.dylib")
    assert result.status is InjectionStatus.INJECTED

    reparsed = lief.MachO.parse(str(compiled_macho_binary)).at(0)
    assert "@rpath/libFoo.dylib" in {lib.name for lib in reparsed.libraries}


def test_inject_already_loaded_returns_skipped(compiled_macho_binary: Path):
    first = inject_dylib(compiled_macho_binary, "@rpath/libFoo.dylib")
    assert first.status is InjectionStatus.INJECTED

    second = inject_dylib(compiled_macho_binary, "@rpath/libFoo.dylib")
    assert second.status is InjectionStatus.INJECTION_SKIPPED


def test_inject_into_non_macho_file_returns_unsupported(tmp_path: Path):
    not_macho = tmp_path / "not_a_binary.txt"
    not_macho.write_text("hello world\n")

    result = inject_dylib(not_macho, "@rpath/libFoo.dylib")
    assert result.status is InjectionStatus.INJECTION_UNSUPPORTED


def test_inject_with_unknown_load_command_returns_failed(compiled_macho_binary: Path):
    result = inject_dylib(compiled_macho_binary, "@rpath/libFoo.dylib", load_command="LC_BOGUS")
    assert result.status is InjectionStatus.INJECTION_FAILED


def test_inject_requires_explicit_arch_for_universal_binary(fat_macho_binary: Path):
    result = inject_dylib(fat_macho_binary, "@rpath/libFoo.dylib")
    assert result.status is InjectionStatus.INJECTION_FAILED
    assert "arch" in result.message.lower()


def test_inject_rejects_unknown_arch_for_universal_binary(fat_macho_binary: Path):
    result = inject_dylib(fat_macho_binary, "@rpath/libFoo.dylib", arch="armv7")
    assert result.status is InjectionStatus.INJECTION_FAILED


def test_inject_into_specific_arch_of_universal_binary(fat_macho_binary: Path):
    result = inject_dylib(fat_macho_binary, "@rpath/libFoo.dylib", arch="arm64")
    assert result.status is InjectionStatus.INJECTED

    fat = lief.MachO.parse(str(fat_macho_binary))
    arm64_slice = next(b for b in fat if b.header.cpu_type == lief.MachO.Header.CPU_TYPE.ARM64)
    x86_64_slice = next(b for b in fat if b.header.cpu_type == lief.MachO.Header.CPU_TYPE.X86_64)
    assert "@rpath/libFoo.dylib" in {lib.name for lib in arm64_slice.libraries}
    assert "@rpath/libFoo.dylib" not in {lib.name for lib in x86_64_slice.libraries}
