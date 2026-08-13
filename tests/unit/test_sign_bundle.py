# SPDX-License-Identifier: GPL-3.0-or-later
"""F6: single-profile mode warns when a nested target's bundle id isn't
authorized by the lone profile, but still signs it (legacy behavior).

Uses a stub SigningProvider so no codesign/Keychain is involved -- these
tests run on Linux too.
"""

from __future__ import annotations

import datetime
import warnings
from pathlib import Path
from typing import Any

from ipa_forge.bundle.models import AppBundle, MachOTarget
from ipa_forge.signing.pipeline import sign_bundle
from ipa_forge.signing.profile import ProfilePool, ProvisioningProfile
from ipa_forge.signing.provider import SigningProvider, SignResult, VerifyResult


class _StubProvider(SigningProvider):
    def __init__(self) -> None:
        self.signed: list[Path] = []

    def list_identities(self):
        return []

    def sign(self, target: Path, entitlements: dict[str, Any], identity: str) -> SignResult:
        self.signed.append(target)
        return SignResult(target=target, identity=identity, entitlements=entitlements)

    def verify(self, target: Path, deep: bool = False) -> VerifyResult:
        return VerifyResult(target=target, ok=True)

    def dump_entitlements(self, target: Path) -> dict[str, Any]:
        return {}


def _profile(bundle_id_or_wildcard: str, team_id: str = "TEAM1") -> ProvisioningProfile:
    app_id = bundle_id_or_wildcard if bundle_id_or_wildcard == "*" else f"{team_id}.{bundle_id_or_wildcard}"
    return ProvisioningProfile(
        uuid=f"uuid-{bundle_id_or_wildcard}",
        name=f"profile for {bundle_id_or_wildcard}",
        team_identifier=team_id,
        application_identifier=app_id,
        expiration_date=datetime.datetime(2099, 1, 1, tzinfo=datetime.UTC),
        entitlements={"application-identifier": app_id},
    )


def _bundle_with_appex(tmp_path: Path) -> AppBundle:
    root = tmp_path / "App.app"
    (root / "PlugIns" / "Ext.appex").mkdir(parents=True)
    (root / "TestApp").write_bytes(b"\xcf\xfa\xed\xfe")
    (root / "PlugIns" / "Ext.appex" / "Ext").write_bytes(b"\xcf\xfa\xed\xfe")
    return AppBundle(
        root=root,
        extraction_root=tmp_path,
        info_plist={"CFBundleIdentifier": "com.x.app", "CFBundleExecutable": "TestApp"},
        bundle_id="com.x.app",
        version="1.0.0",
        build="1",
        executables=[
            MachOTarget(
                path=root / "TestApp",
                bundle_relative="Payload/App.app/TestApp",
                kind="main",
                depth=1,
                bundle_id="com.x.app",
            ),
            MachOTarget(
                path=root / "PlugIns" / "Ext.appex" / "Ext",
                bundle_relative="Payload/App.app/PlugIns/Ext.appex/Ext",
                kind="appex",
                depth=3,
                bundle_id="com.x.other",
            ),
        ],
    )


def test_single_profile_mismatch_for_extension_warns_but_still_signs(tmp_path: Path):
    bundle = _bundle_with_appex(tmp_path)
    profile_path = tmp_path / "p.mobileprovision"
    profile_path.write_bytes(b"dummy")
    pool = ProfilePool(entries=[(_profile("com.x.app"), profile_path)])

    provider = _StubProvider()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sign_bundle(bundle, provider, "ident", pool)

    mismatches = [w for w in caught if "does not authorize" in str(w.message)]
    assert len(mismatches) == 1
    assert "com.x.other" in str(mismatches[0].message)
    # Legacy permissive mode: both targets still get signed.
    assert len(provider.signed) == 2


def test_single_wildcard_profile_covers_extension_without_warning(tmp_path: Path):
    bundle = _bundle_with_appex(tmp_path)
    profile_path = tmp_path / "p.mobileprovision"
    profile_path.write_bytes(b"dummy")
    pool = ProfilePool(entries=[(_profile("*"), profile_path)])

    provider = _StubProvider()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sign_bundle(bundle, provider, "ident", pool)

    assert not [w for w in caught if "does not authorize" in str(w.message)]
    assert len(provider.signed) == 2
