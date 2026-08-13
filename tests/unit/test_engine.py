from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.patch.base import PatchContext
from ipa_forge.patch.binary import BinaryReplaceOp
from ipa_forge.patch.engine import PatchValidationError, apply_all
from ipa_forge.patch.resource import ResourceReplaceOp


def test_apply_all_raises_before_mutating_when_any_op_fails_dry_run(tmp_path: Path, fake_ipa: Path):
    app_path = extract_ipa(fake_ipa, tmp_path / "extract")
    bundle = load_bundle(app_path)
    ctx = PatchContext(bundle=bundle, patch_source_dir=tmp_path)

    good_op = ResourceReplaceOp(op_id="good", path="resource.txt", source="missing_source.txt")
    bad_op = BinaryReplaceOp(op_id="bad", executable="TestApp", pattern="DE AD BE EF", replacement="00 00 00 00", expected_matches=1)

    original_contents = (bundle.root / "resource.txt").read_bytes()

    with pytest.raises(PatchValidationError):
        apply_all([good_op, bad_op], ctx)

    # Nothing should have mutated -- the dry-run gate ran for both ops first.
    assert (bundle.root / "resource.txt").read_bytes() == original_contents


def test_apply_all_applies_resources_before_binary_patches(tmp_path: Path, fake_ipa: Path):
    app_path = extract_ipa(fake_ipa, tmp_path / "extract")
    bundle = load_bundle(app_path)

    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "new.txt").write_text("patched\n")

    ctx = PatchContext(bundle=bundle, patch_source_dir=source_dir)

    binary_data = (bundle.root / "TestApp").read_bytes()
    header_hex = " ".join(f"{b:02x}" for b in binary_data[:8])

    resource_op = ResourceReplaceOp(op_id="res", path="resource.txt", source="new.txt")
    binary_op = BinaryReplaceOp(op_id="bin", executable="TestApp", pattern=header_hex, replacement=header_hex, expected_matches=1)

    results = apply_all([binary_op, resource_op], ctx)  # declared out of order on purpose
    statuses = {r.op_id: r.status for r in results}
    assert statuses == {"res": "applied", "bin": "applied"}
    # Engine reorders: resource ops always applied before binary ops.
    assert [r.op_id for r in results] == ["res", "bin"]
