"""Real-signing integration tests. Require macOS + a local codesigning identity
in Keychain (both already confirmed present in this dev environment)."""
from __future__ import annotations

from pathlib import Path

import pytest

from ipa_forge.bundle.models import AppBundle, MachOTarget
from ipa_forge.bundle.plist import write_plist
from ipa_forge.signing.profile import ProvisioningProfile
from ipa_forge.signing.provider import LocalIdentityProvider
from ipa_forge.signing.pipeline import sign_bundle, sign_target_path

pytestmark = pytest.mark.macos


def _first_apple_development_identity() -> str:
    identities = LocalIdentityProvider().list_identities()
    if not identities:
        pytest.skip("no local codesigning identities available")
    for identity in identities:
        if "Apple Development" in identity.name:
            return identity.sha1
    return identities[0].sha1


def _fake_profile(bundle_id: str, team_id: str = "TESTTEAM1") -> ProvisioningProfile:
    import datetime

    return ProvisioningProfile(
        uuid="test-uuid",
        name="test profile",
        team_identifier=team_id,
        application_identifier=f"{team_id}.{bundle_id}",
        expiration_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
        entitlements={
            "application-identifier": f"{team_id}.{bundle_id}",
            "com.apple.developer.team-identifier": team_id,
            "get-task-allow": True,
        },
    )


def test_sign_and_verify_a_single_binary(compiled_macho_binary: Path):
    identity = _first_apple_development_identity()
    provider = LocalIdentityProvider()

    entitlements = {"get-task-allow": True}
    provider.sign(compiled_macho_binary, entitlements, identity)

    result = provider.verify(compiled_macho_binary, deep=True)
    assert result.ok, result.message

    dumped = provider.dump_entitlements(compiled_macho_binary)
    assert dumped == entitlements


def test_sign_bundle_recursive_bottom_up(tmp_path: Path, compiled_macho_binary: Path):
    identity = _first_apple_development_identity()
    provider = LocalIdentityProvider()
    profile = _fake_profile("com.example.testapp")

    app_root = tmp_path / "Payload" / "TestApp.app"
    (app_root / "Frameworks" / "Foo.framework").mkdir(parents=True)
    main_exec = app_root / "TestApp"
    main_exec.write_bytes(compiled_macho_binary.read_bytes())
    main_exec.chmod(0o755)
    write_plist(app_root / "Info.plist", {"CFBundleIdentifier": "com.example.testapp", "CFBundleExecutable": "TestApp"})
    fw_exec = app_root / "Frameworks" / "Foo.framework" / "Foo"
    fw_exec.write_bytes(compiled_macho_binary.read_bytes())
    fw_exec.chmod(0o755)
    write_plist(
        app_root / "Frameworks" / "Foo.framework" / "Info.plist",
        {"CFBundleIdentifier": "com.example.testapp.Foo", "CFBundleExecutable": "Foo", "CFBundlePackageType": "FMWK"},
    )

    bundle = AppBundle(
        root=app_root,
        extraction_root=tmp_path,
        info_plist={"CFBundleExecutable": "TestApp", "CFBundleIdentifier": "com.example.testapp"},
        bundle_id="com.example.testapp",
        version="1.0.0",
        build="1",
        executables=[
            MachOTarget(path=fw_exec, bundle_relative="Payload/TestApp.app/Frameworks/Foo.framework/Foo", kind="framework", depth=3),
            MachOTarget(path=main_exec, bundle_relative="Payload/TestApp.app/TestApp", kind="main", depth=1),
        ],
    )

    results = sign_bundle(bundle, provider, identity, profile)
    assert len(results) == 2

    for target in bundle.executables:
        verify_result = provider.verify(sign_target_path(target))
        assert verify_result.ok, verify_result.message

    assert bundle.entitlements["application-identifier"] == "TESTTEAM1.com.example.testapp"
