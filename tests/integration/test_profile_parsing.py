# SPDX-License-Identifier: GPL-3.0-or-later
"""Provisioning-profile parsing against real, locally-installed profiles.

Skips gracefully if no profile is present rather than hardcoding any
personal profile UUID/team id into the test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.signing.profile import parse_provisioning_profile

pytestmark = pytest.mark.macos

_PROFILES_DIR = Path.home() / "Library" / "MobileDevice" / "Provisioning Profiles"


def _any_local_profile() -> Path:
    if not _PROFILES_DIR.is_dir():
        pytest.skip(f"no provisioning profiles directory at {_PROFILES_DIR}")
    profiles = list(_PROFILES_DIR.glob("*.mobileprovision"))
    if not profiles:
        pytest.skip(f"no .mobileprovision files found under {_PROFILES_DIR}")
    return profiles[0]


def test_parse_real_provisioning_profile():
    profile_path = _any_local_profile()
    profile = parse_provisioning_profile(profile_path)

    assert profile.uuid
    assert profile.name
    assert profile.team_identifier
    assert "application-identifier" in profile.entitlements
    assert profile.expiration_date is not None
    # bundle_id_pattern should have the team-id prefix stripped
    assert not profile.bundle_id_pattern.startswith(profile.team_identifier)
