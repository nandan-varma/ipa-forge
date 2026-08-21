# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge analysis diff` CLI: the general version-to-version porting
survey, distinct from `forge hooks diff`'s hook-regression gate."""

from __future__ import annotations

import plistlib
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.cli.main import app

runner = CliRunner()


def _pack_ipa(objc_binary: Path, dest: Path, *, bundle_id: str = "com.example.testapp", version: str = "1.0.0") -> Path:
    app_dir = dest / "Payload" / "Test.app"
    app_dir.mkdir(parents=True)
    (app_dir / "Test").write_bytes(objc_binary.read_bytes())
    info = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": "1",
        "CFBundleExecutable": "Test",
    }
    (app_dir / "Info.plist").write_bytes(plistlib.dumps(info))
    ipa = dest / "app.ipa"
    with zipfile.ZipFile(ipa, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in app_dir.rglob("*"):
            zf.write(f, f.relative_to(dest))
    return ipa


def test_diff_identical_reports_no_differences(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    ipa = _pack_ipa(objc_rich_macho_binary, old_dir)
    result = runner.invoke(app, ["analysis", "diff", "--old", str(ipa), "--new", str(ipa)])
    assert result.exit_code == 0
    assert "no differences found" in result.stdout


def test_diff_reports_class_and_plist_changes(
    objc_macho_binary: Path, objc_rich_macho_binary: Path, tmp_path: Path
) -> None:
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    old_ipa = _pack_ipa(objc_macho_binary, old_dir, version="1.0.0")
    new_ipa = _pack_ipa(objc_rich_macho_binary, new_dir, version="2.0.0")

    result = runner.invoke(app, ["analysis", "diff", "--old", str(old_ipa), "--new", str(new_ipa)])
    assert result.exit_code == 0
    assert "1.0.0 -> 2.0.0" in result.stdout
    assert "Bar" in result.stdout  # new class only in the rich binary
    assert "CFBundleShortVersionString" in result.stdout


def test_diff_app_dir_skips_ipa(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
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
    result = runner.invoke(app, ["analysis", "diff", "--old-app-dir", str(app_dir), "--new-app-dir", str(app_dir)])
    assert result.exit_code == 0
    assert "no differences found" in result.stdout
