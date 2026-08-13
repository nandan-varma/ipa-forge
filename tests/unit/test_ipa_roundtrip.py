# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa, load_bundle, repack_ipa
from ipa_forge.validators.bundle_validator import validate_bundle


def test_extract_repack_roundtrip_is_byte_identical(tmp_path: Path, fake_ipa: Path):
    extract_dir_1 = tmp_path / "extract1"
    app_path_1 = extract_ipa(fake_ipa, extract_dir_1)
    bundle = load_bundle(app_path_1)
    validate_bundle(bundle)

    repacked = repack_ipa(extract_dir_1, tmp_path / "repacked.ipa")

    extract_dir_2 = tmp_path / "extract2"
    extract_ipa(repacked, extract_dir_2)

    files_1 = sorted(p.relative_to(extract_dir_1) for p in extract_dir_1.rglob("*") if p.is_file())
    files_2 = sorted(p.relative_to(extract_dir_2) for p in extract_dir_2.rglob("*") if p.is_file())
    assert files_1 == files_2

    for rel in files_1:
        assert (extract_dir_1 / rel).read_bytes() == (extract_dir_2 / rel).read_bytes()


def test_load_bundle_populates_inventory(tmp_path: Path, fake_ipa: Path):
    app_path = extract_ipa(fake_ipa, tmp_path / "extract")
    bundle = load_bundle(app_path)

    assert bundle.bundle_id == "com.example.testapp"
    assert bundle.version == "1.0.0"
    assert len(bundle.executables) == 1
    assert bundle.executables[0].kind == "main"
    assert bundle.executables[0].bundle_relative == "Payload/TestApp.app/TestApp"
