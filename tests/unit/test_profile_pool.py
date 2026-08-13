# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from ipa_forge.signing.profile import ProfileError, ProfilePool, ProvisioningProfile


def _profile(bundle_id_or_wildcard: str, team_id: str = "TEAM1") -> ProvisioningProfile:
    app_id = bundle_id_or_wildcard if bundle_id_or_wildcard == "*" else f"{team_id}.{bundle_id_or_wildcard}"
    return ProvisioningProfile(
        uuid=f"uuid-{bundle_id_or_wildcard}",
        name=f"profile for {bundle_id_or_wildcard}",
        team_identifier=team_id,
        application_identifier=app_id,
        expiration_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=7),
        entitlements={"application-identifier": app_id},
    )


def test_single_profile_is_always_used_regardless_of_bundle_id():
    """Backward-compat: one supplied profile signs every target, matching
    pre-per-extension-profile behavior exactly."""
    pool = ProfilePool([(_profile("com.example.app"), Path("a.mobileprovision"))])

    profile, path = pool.select_for("com.example.app.NotificationService")
    assert profile.bundle_id_pattern == "com.example.app"
    assert path == Path("a.mobileprovision")


def test_exact_match_is_preferred_among_multiple_profiles():
    pool = ProfilePool(
        [
            (_profile("com.example.app"), Path("app.mobileprovision")),
            (_profile("com.example.app.NotificationService"), Path("ext.mobileprovision")),
        ]
    )

    profile, path = pool.select_for("com.example.app.NotificationService")
    assert profile.bundle_id_pattern == "com.example.app.NotificationService"
    assert path == Path("ext.mobileprovision")

    profile, path = pool.select_for("com.example.app")
    assert profile.bundle_id_pattern == "com.example.app"
    assert path == Path("app.mobileprovision")


def test_wildcard_profile_is_used_when_no_exact_match():
    pool = ProfilePool(
        [
            (_profile("com.example.app"), Path("app.mobileprovision")),
            (_profile("*", team_id="TEAM1"), Path("wildcard.mobileprovision")),
        ]
    )

    profile, path = pool.select_for("com.example.app.NotificationService")
    assert profile.bundle_id_pattern == "*"
    assert path == Path("wildcard.mobileprovision")


def test_multiple_profiles_with_no_match_raises_actionable_error():
    pool = ProfilePool(
        [
            (_profile("com.example.app"), Path("app.mobileprovision")),
            (_profile("com.example.other"), Path("other.mobileprovision")),
        ]
    )

    with pytest.raises(ProfileError, match="com.example.app.NotificationService"):
        pool.select_for("com.example.app.NotificationService")
