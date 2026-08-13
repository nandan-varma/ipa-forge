from __future__ import annotations

import plistlib
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
