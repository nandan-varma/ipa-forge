"""End-to-end pipeline test against the checked-in synthetic app fixture:
extract -> patch -> sign -> repackage -> re-validate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.bundle.ipa import extract_ipa
from ipa_forge.pipeline import run_pipeline

pytestmark = pytest.mark.macos

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_full_pipeline_against_synthetic_app(tmp_path: Path, synthetic_profile: Path):
    output = tmp_path / "patched.ipa"

    result = run_pipeline(
        ipa_path=FIXTURES / "synthetic_app.ipa",
        patch_definition_path=FIXTURES / "patches" / "example.yaml",
        identity_query="Apple Development",
        profile_paths=[synthetic_profile],
        output_path=output,
    )

    assert result.output_path == output
    assert output.is_file()

    manifest = result.manifest
    assert manifest.bundle_id == "com.example.synthetic"
    assert manifest.version == "1.0.0"
    assert {p["id"] for p in manifest.patches_applied} == {"zero-marker-bytes", "swap-asset"}
    assert all(p["status"] == "applied" for p in manifest.patches_applied)
    assert any("TestApp" in f for f in manifest.macho_modified)
    assert any("asset.txt" in f for f in manifest.files_modified)
    assert manifest.profile.uuid == "11111111-2222-3333-4444-555555555555"
    assert manifest.output_sha256

    assert all(v.ok for v in result.verify_results)

    # Re-extract the produced IPA and confirm the patches actually landed.
    extracted = extract_ipa(output, tmp_path / "recheck")
    assert (extracted / "asset.txt").read_text() == "patched synthetic resource\n"
    assert (extracted / "embedded.mobileprovision").is_file()

    marker = bytes([0xCA, 0xFE, 0xF0, 0x0D])
    assert marker not in (extracted / "TestApp").read_bytes()


def test_dry_run_does_not_mutate_or_sign(tmp_path: Path, synthetic_profile: Path):
    output = tmp_path / "should_not_exist.ipa"

    result = run_pipeline(
        ipa_path=FIXTURES / "synthetic_app.ipa",
        patch_definition_path=FIXTURES / "patches" / "example.yaml",
        identity_query="Apple Development",
        profile_paths=[synthetic_profile],
        output_path=output,
        dry_run=True,
    )

    assert result.output_path is None
    assert not output.exists()
    assert {p["id"] for p in result.manifest.patches_applied} == {"zero-marker-bytes", "swap-asset"}
