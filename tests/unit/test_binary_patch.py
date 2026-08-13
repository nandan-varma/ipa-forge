# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.bundle.models import AppBundle, MachOTarget
from ipa_forge.patch.base import PatchContext
from ipa_forge.patch.binary import (
    BinaryReplaceOp,
    PatternError,
    find_matches,
    parse_hex_pattern,
)


def test_parse_hex_pattern_with_wildcard():
    data, mask = parse_hex_pattern("AA BB ?? CC")
    assert data == bytes([0xAA, 0xBB, 0x00, 0xCC])
    assert mask == bytes([0xFF, 0xFF, 0x00, 0xFF])


def test_parse_hex_pattern_rejects_bad_token():
    with pytest.raises(PatternError):
        parse_hex_pattern("ZZ")


def test_find_matches_respects_wildcard_and_window():
    haystack = bytes([0xAA, 0xBB, 0x11, 0xCC, 0xAA, 0xBB, 0x22, 0xCC])
    pattern, mask = parse_hex_pattern("AA BB ?? CC")
    offsets = find_matches(haystack, pattern, mask)
    assert offsets == [0, 4]


def _bundle_for(binary_path: Path, tmp_path: Path) -> AppBundle:
    bundle = AppBundle(
        root=tmp_path,
        extraction_root=tmp_path,
        info_plist={"CFBundleExecutable": binary_path.name, "CFBundleIdentifier": "com.example.test"},
        bundle_id="com.example.test",
        version="1.0.0",
        build="1",
    )
    bundle.executables = [
        MachOTarget(path=binary_path, bundle_relative=f"Payload/App.app/{binary_path.name}", kind="main", depth=1)
    ]
    return bundle


def test_binary_replace_dry_run_ok_on_unique_header_match(compiled_macho_binary: Path, tmp_path: Path):
    data = compiled_macho_binary.read_bytes()
    header_hex = " ".join(f"{b:02x}" for b in data[:8])

    bundle = _bundle_for(compiled_macho_binary, tmp_path)
    ctx = PatchContext(bundle=bundle, patch_source_dir=tmp_path)

    op = BinaryReplaceOp(
        op_id="t1",
        executable=compiled_macho_binary.name,
        pattern=header_hex,
        replacement=header_hex,
        expected_matches=1,
    )
    result = op.dry_run(ctx)
    assert result.status == "dry_run_ok"


def test_binary_replace_fails_on_zero_matches(compiled_macho_binary: Path, tmp_path: Path):
    bundle = _bundle_for(compiled_macho_binary, tmp_path)
    ctx = PatchContext(bundle=bundle, patch_source_dir=tmp_path)

    op = BinaryReplaceOp(
        op_id="t2",
        executable=compiled_macho_binary.name,
        pattern="DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF",
        replacement="00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
        expected_matches=1,
    )
    result = op.dry_run(ctx)
    assert result.status == "failed"
    assert "found 0" in result.message


def test_binary_replace_fails_on_more_than_expected_matches(compiled_macho_binary: Path, tmp_path: Path):
    bundle = _bundle_for(compiled_macho_binary, tmp_path)
    ctx = PatchContext(bundle=bundle, patch_source_dir=tmp_path)

    # A single zero byte occurs far more than once in any real Mach-O binary.
    op = BinaryReplaceOp(
        op_id="t3", executable=compiled_macho_binary.name, pattern="00", replacement="00", expected_matches=1
    )
    result = op.dry_run(ctx)
    assert result.status == "failed"
    assert "expected 1 match" in result.message


def test_binary_replace_apply_mutates_file(compiled_macho_binary: Path, tmp_path: Path):
    data = compiled_macho_binary.read_bytes()
    header_hex = " ".join(f"{b:02x}" for b in data[:8])
    replacement_bytes = bytes([b ^ 0xFF for b in data[:8]])
    replacement_hex = " ".join(f"{b:02x}" for b in replacement_bytes)

    bundle = _bundle_for(compiled_macho_binary, tmp_path)
    ctx = PatchContext(bundle=bundle, patch_source_dir=tmp_path)

    op = BinaryReplaceOp(
        op_id="t4",
        executable=compiled_macho_binary.name,
        pattern=header_hex,
        replacement=replacement_hex,
        expected_matches=1,
    )
    result = op.apply(ctx)
    assert result.status == "applied"
    assert compiled_macho_binary.read_bytes()[:8] == replacement_bytes


def test_binary_replace_rejects_mismatched_replacement_length(compiled_macho_binary: Path, tmp_path: Path):
    data = compiled_macho_binary.read_bytes()
    header_hex = " ".join(f"{b:02x}" for b in data[:8])

    bundle = _bundle_for(compiled_macho_binary, tmp_path)
    ctx = PatchContext(bundle=bundle, patch_source_dir=tmp_path)

    op = BinaryReplaceOp(
        op_id="t5", executable=compiled_macho_binary.name, pattern=header_hex, replacement="00 00", expected_matches=1
    )
    result = op.apply(ctx)
    assert result.status == "failed"
    assert "length" in result.message
