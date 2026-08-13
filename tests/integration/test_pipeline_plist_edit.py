"""End-to-end pipeline test for the plist_edit patch type: edit Info.plist,
re-sign, and confirm the produced IPA passes codesign verification and
actually carries the edited plist."""
from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.bundle.ipa import extract_ipa
from ipa_forge.bundle.plist import read_plist
from ipa_forge.pipeline import run_pipeline

pytestmark = pytest.mark.macos

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_plist_edit_survives_signing_and_repackaging(tmp_path: Path, synthetic_profile: Path):
    output = tmp_path / "plist_edited.ipa"

    result = run_pipeline(
        ipa_path=FIXTURES / "synthetic_app.ipa",
        patch_definition_path=FIXTURES / "patches" / "example_plist_edit.yaml",
        identity_query="Apple Development",
        profile_path=synthetic_profile,
        output_path=output,
    )

    assert all(v.ok for v in result.verify_results)
    patch_status = {p["id"]: p["status"] for p in result.manifest.patches_applied}
    assert patch_status == {"bump-min-os": "applied", "drop-ipad-support": "applied"}

    extracted = extract_ipa(output, tmp_path / "recheck")
    plist = read_plist(extracted / "Info.plist")
    assert plist["MinimumOSVersion"] == "14.0"
    assert "UIDeviceFamily" not in plist
