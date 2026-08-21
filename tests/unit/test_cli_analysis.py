# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge analysis classdump` CLI: end-to-end against a real compiled ObjC
Mach-O wrapped in a minimal IPA."""

from __future__ import annotations

import plistlib
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.cli.main import app

runner = CliRunner()


def _pack_ipa(objc_binary: Path, tmp_path: Path) -> Path:
    app_dir = tmp_path / "Payload" / "Test.app"
    app_dir.mkdir(parents=True)
    (app_dir / "Test").write_bytes(objc_binary.read_bytes())
    info = {
        "CFBundleIdentifier": "com.example.testapp",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "CFBundleExecutable": "Test",
    }
    (app_dir / "Info.plist").write_bytes(plistlib.dumps(info))
    ipa = tmp_path / "app.ipa"
    with zipfile.ZipFile(ipa, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in app_dir.rglob("*"):
            zf.write(f, f.relative_to(tmp_path))
    return ipa


def test_classdump_dumps_everything(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_rich_macho_binary, tmp_path)
    result = runner.invoke(app, ["analysis", "classdump", "--ipa", str(ipa)])
    assert result.exit_code == 0
    assert "@protocol Greeter" in result.stdout
    assert "@interface Bar" in result.stdout
    assert "(Extras)" in result.stdout


def test_classdump_class_filter(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_rich_macho_binary, tmp_path)
    result = runner.invoke(app, ["analysis", "classdump", "--ipa", str(ipa), "--class", "Bar"])
    assert result.exit_code == 0
    assert "@interface Bar" in result.stdout
    assert "@protocol Greeter" not in result.stdout


def test_classdump_unknown_class_fails(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_rich_macho_binary, tmp_path)
    result = runner.invoke(app, ["analysis", "classdump", "--ipa", str(ipa), "--class", "Nope"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_classdump_writes_to_output_file(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_rich_macho_binary, tmp_path)
    out = tmp_path / "dump.h"
    result = runner.invoke(app, ["analysis", "classdump", "--ipa", str(ipa), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "@interface Bar" in out.read_text()


def test_classdump_app_dir_skips_ipa(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    app_dir = tmp_path / "Payload" / "Test.app"
    app_dir.mkdir(parents=True)
    (app_dir / "Test").write_bytes(objc_rich_macho_binary.read_bytes())
    info = {
        "CFBundleIdentifier": "com.example.testapp",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "CFBundleExecutable": "Test",
    }
    (app_dir / "Info.plist").write_bytes(plistlib.dumps(info))
    result = runner.invoke(app, ["analysis", "classdump", "--app-dir", str(app_dir)])
    assert result.exit_code == 0
    assert "@interface Bar" in result.stdout
