# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ipa_forge.signing.reconcile import reconcile_entitlements


def test_drops_entitlement_not_authorized_by_profile():
    app = {"com.apple.developer.healthkit": True, "get-task-allow": True}
    profile = {"application-identifier": "TEAM.com.example.app", "get-task-allow": True}
    reconciled = reconcile_entitlements(app, profile)
    assert "com.apple.developer.healthkit" not in reconciled
    assert reconciled["get-task-allow"] is True


def test_never_adds_entitlement_the_app_did_not_claim():
    app = {}
    profile = {
        "application-identifier": "TEAM.com.example.app",
        "keychain-access-groups": ["TEAM.*"],
        "aps-environment": "production",
    }
    reconciled = reconcile_entitlements(app, profile)
    assert "aps-environment" not in reconciled
    assert "keychain-access-groups" not in reconciled


def test_application_identifier_and_team_identifier_always_come_from_profile():
    app = {"application-identifier": "OLDTEAM.com.example.app", "com.apple.developer.team-identifier": "OLDTEAM"}
    profile = {
        "application-identifier": "NEWTEAM.com.example.app",
        "com.apple.developer.team-identifier": "NEWTEAM",
    }
    reconciled = reconcile_entitlements(app, profile)
    assert reconciled["application-identifier"] == "NEWTEAM.com.example.app"
    assert reconciled["com.apple.developer.team-identifier"] == "NEWTEAM"


def test_profile_may_authorize_more_than_app_claims():
    app = {"get-task-allow": True}
    profile = {"get-task-allow": True, "aps-environment": "development", "application-identifier": "T.x"}
    reconciled = reconcile_entitlements(app, profile)
    # aps-environment is authorized by the profile but never claimed by the
    # app, so it must not appear -- only entitlements the app actually
    # requested (plus the always-profile-authoritative keys) survive.
    assert reconciled == {"get-task-allow": True, "application-identifier": "T.x"}
