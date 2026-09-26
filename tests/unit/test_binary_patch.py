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
    format_offsets,
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


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [(0, 5, [0, 1, 2]), (1, 4, [1]), (2, 4, []), (0, 2, []), (4, 4, [])],
)
def test_exact_matches_keep_overlaps_and_slice_boundaries(start, end, expected):
    assert find_matches(b"aaaaa", b"aaa", b"\xff\xff\xff", start, end) == expected


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


# --- the dry-run gate must catch every failure `apply` can hit (A1) ---------
# A malformed or wrong-length `replacement` used to slip past dry_run: the
# length check lived only in apply(), and a bad hex token raised PatternError
# straight out of apply() -- a traceback, raised after earlier operations in
# the same run had already mutated the extracted tree.


@pytest.mark.parametrize(
    ("replacement", "expected_text"),
    [
        ("00 00", "length"),
        ("zz zz zz zz zz zz zz zz", "invalid hex byte token"),
        ("?? ?? 00 00 00 00 00 00", "wildcards are not allowed"),
    ],
)
def test_binary_replace_dry_run_rejects_bad_replacement(
    compiled_macho_binary: Path, tmp_path: Path, replacement: str, expected_text: str
):
    header_hex = " ".join(f"{b:02x}" for b in compiled_macho_binary.read_bytes()[:8])
    ctx = PatchContext(bundle=_bundle_for(compiled_macho_binary, tmp_path), patch_source_dir=tmp_path)

    op = BinaryReplaceOp(
        op_id="bad-replacement",
        executable=compiled_macho_binary.name,
        pattern=header_hex,
        replacement=replacement,
    )
    result = op.dry_run(ctx)
    assert result.status == "failed"
    assert expected_text in result.message
    # apply() must report the same failure as a PatchResult, never raise
    assert op.apply(ctx).status == "failed"


def test_binary_replace_apply_leaves_file_untouched_on_bad_replacement(compiled_macho_binary: Path, tmp_path: Path):
    before = compiled_macho_binary.read_bytes()
    header_hex = " ".join(f"{b:02x}" for b in before[:8])
    ctx = PatchContext(bundle=_bundle_for(compiled_macho_binary, tmp_path), patch_source_dir=tmp_path)

    op = BinaryReplaceOp(op_id="bad-hex", executable=compiled_macho_binary.name, pattern=header_hex, replacement="zz")
    assert op.apply(ctx).status == "failed"
    assert compiled_macho_binary.read_bytes() == before


def test_format_offsets_caps_the_list():
    """A bare `00` pattern matches tens of thousands of times; the full offset
    list made the error message (which lands in PipelineError and the manifest)
    megabytes long."""
    assert format_offsets([0x10, 0x20]) == "[0x10, 0x20]"
    capped = format_offsets(list(range(500)))
    assert capped.endswith("... and 490 more]")
    assert len(capped) < 120


def test_binary_replace_over_broad_pattern_message_stays_short(compiled_macho_binary: Path, tmp_path: Path):
    ctx = PatchContext(bundle=_bundle_for(compiled_macho_binary, tmp_path), patch_source_dir=tmp_path)
    op = BinaryReplaceOp(op_id="broad", executable=compiled_macho_binary.name, pattern="00", replacement="01")
    result = op.dry_run(ctx)
    assert result.status == "failed"
    assert "and" in result.message and "more" in result.message
    assert len(result.message) < 200


# --- byte-level evidence in the manifest (C1) ------------------------------


def test_binary_replace_records_offsets_bytes_and_note(compiled_macho_binary: Path, tmp_path: Path):
    data = compiled_macho_binary.read_bytes()
    header_hex = " ".join(f"{b:02x}" for b in data[:8])
    replacement_hex = " ".join(f"{b ^ 0xFF:02x}" for b in data[:8])
    ctx = PatchContext(bundle=_bundle_for(compiled_macho_binary, tmp_path), patch_source_dir=tmp_path)

    op = BinaryReplaceOp(
        op_id="evidence",
        executable=compiled_macho_binary.name,
        pattern=header_hex,
        replacement=replacement_hex,
        note="flip the header bytes",
        symbol="SomeClass.someMethod()",
    )
    # the same evidence is available before anything mutates
    assert op.dry_run(ctx).details == {
        "offsets": ["0x0"],
        "before": header_hex,
        "after": replacement_hex,
        "file": compiled_macho_binary.name,
        "note": "flip the header bytes",
        "symbol": "SomeClass.someMethod()",
    }
    assert op.apply(ctx).details["before"] == header_hex


def test_binary_replace_details_omit_absent_note_and_symbol(compiled_macho_binary: Path, tmp_path: Path):
    header_hex = " ".join(f"{b:02x}" for b in compiled_macho_binary.read_bytes()[:8])
    ctx = PatchContext(bundle=_bundle_for(compiled_macho_binary, tmp_path), patch_source_dir=tmp_path)
    op = BinaryReplaceOp(
        op_id="no-note", executable=compiled_macho_binary.name, pattern=header_hex, replacement=header_hex
    )
    assert set(op.dry_run(ctx).details) == {"offsets", "before", "after", "file"}
