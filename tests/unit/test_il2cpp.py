# SPDX-License-Identifier: GPL-3.0-or-later
"""Small instruction fixtures for the IL2CPP reference index."""

from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ipa_forge.analysis import il2cpp
from ipa_forge.cli.main import app as cli_app


def test_usage_token_kinds_and_rejections() -> None:
    for kind in range(1, 7):
        token = (kind << 29) | (42 << 1) | 1
        assert il2cpp.decode_usage_token(token) == (kind, 42)
    assert il2cpp.decode_usage_token(0) is None
    assert il2cpp.decode_usage_token(2) is None
    assert il2cpp.decode_usage_token(1 << 32) is None
    assert il2cpp.decode_usage_token(7 << 29 | 1) is None


def test_function_starts_uleb_deltas() -> None:
    assert il2cpp.decode_function_starts(bytes([0x80, 0x01, 0x04, 0]), 0, 4, 0x1000) == [0x1080, 0x1084]


def test_arm64_fat_slice_and_missing_arch() -> None:
    header = struct.pack(">II", 0xCAFEBABE, 1)
    arch = struct.pack(">5I", 0x0100000C, 0, 28, 4, 0)
    assert il2cpp._arm64_slice(header + arch + b"ARM!") == b"ARM!"
    with pytest.raises(il2cpp.Il2CppError, match="no arm64"):
        il2cpp._arm64_slice(header + struct.pack(">5I", 7, 0, 28, 4, 0) + b"x86!")


def test_scan_slot_load_and_direct_call() -> None:
    # adrp x0, page; ldr x1, [x0, #0x80]; bl 0x1020
    words = [0x90000000, 0xF9404001, 0x94000006]
    data = struct.pack("<3I", *words) + bytes(0x20)
    image = il2cpp.MachOImage.__new__(il2cpp.MachOImage)
    image.data = data
    section = il2cpp.Section("__TEXT", "__text", 0x1000, len(data), 0, 0x80000000)

    class Namer:
        def slot(self, kind: int, index: int) -> str:
            assert (kind, index) == (5, 3)
            return "hello"

    functions = il2cpp._scan_code(image, [section], [0x1000, 0x1020], {0x1080: (5, 3)}, Namer())  # type: ignore[arg-type]
    assert functions[0x1000].refs == [il2cpp.Reference(0x1004, "string", "hello")]
    assert functions[0x1000].calls == [il2cpp.Call(0x1008, 0x1020, False)]


def test_missing_il2cpp_metadata(tmp_path: Path) -> None:
    with pytest.raises(il2cpp.Il2CppError, match="not a Unity IL2CPP app"):
        il2cpp.find_il2cpp_files(tmp_path, "Game")


def test_metadata_header_and_empty_tables() -> None:
    data = bytearray(0x200)
    struct.pack_into("<2I", data, 0, 0xFAB11BAF, 31)
    for i in range(len(il2cpp._SECTIONS)):
        struct.pack_into("<2i", data, 8 + 8 * i, 0x180, 0)
    metadata = il2cpp.Metadata(bytes(data))
    assert metadata.version == 31
    assert metadata.methods == []
    assert metadata.images == []
    assert metadata.image_of_type(0) is None
    with pytest.raises(il2cpp.Il2CppError, match="bad magic"):
        il2cpp.Metadata(bytes(len(data)))
    struct.pack_into("<I", data, 4, 29)
    with pytest.raises(il2cpp.Il2CppError, match="not supported"):
        il2cpp.Metadata(bytes(data))


def test_macho_sections_and_function_starts() -> None:
    data = bytearray(0x200)
    struct.pack_into("<8I", data, 0, 0xFEEDFACF, 0x0100000C, 0, 2, 2, 0, 0, 0)
    struct.pack_into("<2I16s4Q4I", data, 32, 0x19, 152, b"__TEXT", 0x1000, 0x200, 0, 0x200, 0, 0, 1, 0)
    struct.pack_into(
        "<16s16s2QIIIIIIII", data, 104, b"__text", b"__TEXT", 0x1040, 16, 0x40, 0, 0, 0, 0x80000000, 0, 0, 0
    )
    struct.pack_into("<4I", data, 184, 0x26, 16, 0x1F0, 3)
    data[0x1F0:0x1F3] = bytes([0x40, 0x10, 0])
    image = il2cpp.MachOImage(bytes(data))
    assert image.function_starts == [0x1040, 0x1050]
    assert image.offset_of(0x1040) == 0x40
    assert image.offset_of(0x2000) is None
    assert image.u32(0x1000) == 0xFEEDFACF
    assert image.pointer(0x1000) != 0
    assert image.cstring(0x2000) is None
    assert image.sections[0].is_code
    assert list(image.data_sections()) == []


def test_il2cpp_cli_queries(tmp_path: Path) -> None:
    index = il2cpp.Il2CppIndex(
        binary="Game",
        metadata_version=31,
        method_names={0x1000: "Shop.Enchant", 0x1020: "UI.Confirm"},
        namespaces={},
        function_starts=[0x1000, 0x1020],
        functions={
            0x1000: il2cpp.FunctionXrefs(0x1000, [il2cpp.Reference(0x1004, "string", "enchantments")]),
            0x1020: il2cpp.FunctionXrefs(0x1020, calls=[il2cpp.Call(0x1024, 0x1000, False)]),
        },
        string_literal_count=1,
        method_count=2,
    )
    runner = CliRunner()
    with (
        patch("ipa_forge.cli.analysis.load_bundle") as bundle,
        patch("ipa_forge.cli.analysis.index_for_app", return_value=index),
    ):
        bundle.return_value.main_executable_name = "Game"
        for option, value, expected in (
            ("--methods", "Enchant", "Shop.Enchant"),
            ("--literal", "enchant", "enchantments"),
            ("--callers", "Enchant", "UI.Confirm"),
        ):
            result = runner.invoke(cli_app, ["analysis", "il2cpp", "--app-dir", str(tmp_path), option, value])
            assert result.exit_code == 0, result.output
            assert expected in result.output
        result = runner.invoke(cli_app, ["analysis", "il2cpp", "--app-dir", str(tmp_path), "--methods", "["])
        assert result.exit_code == 1
