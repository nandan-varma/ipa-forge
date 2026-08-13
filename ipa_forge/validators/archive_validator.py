# SPDX-License-Identifier: GPL-3.0-or-later
"""Final validation (pipeline stage 17): re-extract the produced IPA from
scratch and re-run structural validation, to catch corruption introduced by
the repackaging step itself rather than trusting the in-memory state."""

from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.validators.bundle_validator import validate_bundle


class ArchiveValidationError(Exception):
    pass


def validate_final_archive(ipa_path: Path, tmp_dir: Path, *, expect_profile: bool = True) -> None:
    app_path = extract_ipa(ipa_path, tmp_dir)
    bundle = load_bundle(app_path)
    validate_bundle(bundle)

    profile_path = bundle.root / "embedded.mobileprovision"
    if expect_profile and not profile_path.is_file():
        raise ArchiveValidationError(f"final archive is missing embedded.mobileprovision at {profile_path}")
