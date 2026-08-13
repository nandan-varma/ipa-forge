# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.inventory import build_inventory
from ipa_forge.bundle.models import AppBundle
from ipa_forge.bundle.plist import write_plist


def _base_bundle(app_root: Path) -> AppBundle:
    return AppBundle(
        root=app_root,
        extraction_root=app_root.parent.parent,
        info_plist={"CFBundleExecutable": "TestApp", "CFBundleIdentifier": "com.example.app"},
        bundle_id="com.example.app",
        version="1.0.0",
        build="1",
    )


def test_main_target_gets_the_app_bundle_id(tmp_path: Path, compiled_macho_binary: Path):
    app_root = tmp_path / "Payload" / "TestApp.app"
    app_root.mkdir(parents=True)
    (app_root / "TestApp").write_bytes(compiled_macho_binary.read_bytes())

    bundle = _base_bundle(app_root)
    targets = build_inventory(bundle)

    main = next(t for t in targets if t.kind == "main")
    assert main.bundle_id == "com.example.app"


def test_appex_target_gets_its_own_bundle_id_from_its_own_info_plist(tmp_path: Path, compiled_macho_binary: Path):
    app_root = tmp_path / "Payload" / "TestApp.app"
    appex_dir = app_root / "PlugIns" / "NotificationService.appex"
    appex_dir.mkdir(parents=True)
    (app_root / "TestApp").write_bytes(compiled_macho_binary.read_bytes())
    (appex_dir / "NotificationService").write_bytes(compiled_macho_binary.read_bytes())
    write_plist(
        appex_dir / "Info.plist",
        {"CFBundleIdentifier": "com.example.app.NotificationService", "CFBundleExecutable": "NotificationService"},
    )

    bundle = _base_bundle(app_root)
    targets = build_inventory(bundle)

    appex = next(t for t in targets if t.kind == "appex")
    assert appex.bundle_id == "com.example.app.NotificationService"


def test_appex_without_readable_info_plist_gets_none_bundle_id(tmp_path: Path, compiled_macho_binary: Path):
    app_root = tmp_path / "Payload" / "TestApp.app"
    appex_dir = app_root / "PlugIns" / "Broken.appex"
    appex_dir.mkdir(parents=True)
    (app_root / "TestApp").write_bytes(compiled_macho_binary.read_bytes())
    (appex_dir / "Broken").write_bytes(compiled_macho_binary.read_bytes())
    # No Info.plist written for this one.

    bundle = _base_bundle(app_root)
    targets = build_inventory(bundle)

    appex = next(t for t in targets if t.kind == "appex")
    assert appex.bundle_id is None


def test_framework_target_has_no_bundle_id(tmp_path: Path, compiled_macho_binary: Path):
    app_root = tmp_path / "Payload" / "TestApp.app"
    fw_dir = app_root / "Frameworks" / "Foo.framework"
    fw_dir.mkdir(parents=True)
    (app_root / "TestApp").write_bytes(compiled_macho_binary.read_bytes())
    (fw_dir / "Foo").write_bytes(compiled_macho_binary.read_bytes())

    bundle = _base_bundle(app_root)
    targets = build_inventory(bundle)

    framework = next(t for t in targets if t.kind == "framework")
    assert framework.bundle_id is None
