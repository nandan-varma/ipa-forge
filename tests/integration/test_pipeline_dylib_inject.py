# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end pipeline test for the dylib_inject patch type: inject a load
command, re-sign, and confirm the produced IPA still passes codesign
verification and actually carries the new load command."""

from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.bundle.ipa import extract_ipa
from ipa_forge.pipeline import run_pipeline

pytestmark = pytest.mark.macos

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_dylib_injection_survives_signing_and_repackaging(tmp_path: Path, synthetic_profile: Path):
    output = tmp_path / "injected.ipa"

    result = run_pipeline(
        ipa_path=FIXTURES / "synthetic_app.ipa",
        patch_definition_path=FIXTURES / "patches" / "example_dylib_inject.yaml",
        identity_query="Apple Development",
        profile_paths=[synthetic_profile],
        output_path=output,
    )

    assert result.output_path == output
    assert all(v.ok for v in result.verify_results)

    patch_status = {p["id"]: p["status"] for p in result.manifest.patches_applied}
    assert patch_status == {"inject-hook-lib": "applied"}
    assert any("TestApp" in f for f in result.manifest.macho_modified)

    extracted = extract_ipa(output, tmp_path / "recheck")
    import lief

    binary = lief.MachO.parse(str(extracted / "TestApp")).at(0)
    assert "@rpath/libInjectable.dylib" in {lib.name for lib in binary.libraries}
