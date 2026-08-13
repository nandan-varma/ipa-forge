from __future__ import annotations

import datetime
import plistlib
import re
import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def compiled_macho_binary(tmp_path: Path) -> Path:
    """A real, thin, host-arch Mach-O executable, compiled with clang."""
    src = tmp_path / "main.c"
    src.write_text("int main(void) { return 42; }\n")
    out = tmp_path / "compiled_binary"
    subprocess.run(["clang", "-o", str(out), str(src)], check=True)
    return out


@pytest.fixture
def fat_macho_binary(tmp_path: Path) -> Path:
    """A real universal (arm64 + x86_64) Mach-O binary, for arch-selection tests."""
    src = tmp_path / "fat_main.c"
    src.write_text("int main(void) { return 0; }\n")
    arm64_bin = tmp_path / "fat_arm64"
    x86_64_bin = tmp_path / "fat_x86_64"
    subprocess.run(["clang", "-arch", "arm64", "-o", str(arm64_bin), str(src)], check=True)
    subprocess.run(["clang", "-arch", "x86_64", "-o", str(x86_64_bin), str(src)], check=True)
    out = tmp_path / "fat_universal"
    subprocess.run(["lipo", "-create", str(arm64_bin), str(x86_64_bin), "-output", str(out)], check=True)
    return out


@pytest.fixture
def fake_ipa(tmp_path: Path, compiled_macho_binary: Path) -> Path:
    """A minimal, hand-built .ipa: Payload/TestApp.app/{Info.plist, TestApp, resource.txt}."""
    ipa_path = tmp_path / "TestApp.ipa"
    app_dir = "Payload/TestApp.app"

    info_plist = {
        "CFBundleIdentifier": "com.example.testapp",
        "CFBundleExecutable": "TestApp",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
    }

    with zipfile.ZipFile(ipa_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{app_dir}/Info.plist", plistlib.dumps(info_plist))
        zf.write(compiled_macho_binary, f"{app_dir}/TestApp")
        zf.writestr(f"{app_dir}/resource.txt", "original resource content\n")

    return ipa_path


@pytest.fixture
def synthetic_profile(tmp_path: Path) -> Path:
    """A self-signed .mobileprovision (CMS-signed with a real local Keychain
    identity) authorizing com.example.synthetic -- there's no real Apple-issued
    profile for a made-up bundle id, and codesign's own verification doesn't
    check the app-identifier entitlement against the cert, so a self-signed
    CMS envelope is sufficient to exercise the real `security cms -D -i`
    decode path end-to-end."""
    from ipa_forge.signing.provider import LocalIdentityProvider

    identities = LocalIdentityProvider().list_identities()
    dev_identity = next((i for i in identities if "Apple Development" in i.name), None)
    if dev_identity is None:
        pytest.skip("no local Apple Development identity available")

    m = re.search(r"\(([A-Z0-9]+)\)", dev_identity.name)
    team_id = m.group(1) if m else "TESTTEAM1"

    plist_path = tmp_path / "profile_source.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "UUID": "11111111-2222-3333-4444-555555555555",
                "Name": "ipa-forge test profile",
                "TeamIdentifier": [team_id],
                "ExpirationDate": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30),
                "Entitlements": {
                    "application-identifier": f"{team_id}.com.example.synthetic",
                    "com.apple.developer.team-identifier": team_id,
                    "get-task-allow": True,
                },
            }
        )
    )

    out_path = tmp_path / "test.mobileprovision"
    subprocess.run(
        ["security", "cms", "-S", "-N", dev_identity.name, "-i", str(plist_path), "-o", str(out_path)],
        check=True,
    )
    return out_path
