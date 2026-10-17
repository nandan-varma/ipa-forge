# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import plistlib
from pathlib import Path

from ipa_forge.bundle.rename import rename_bundle_ids


def _plist(path: Path, data: dict) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "Info.plist").write_bytes(plistlib.dumps(data))
    return path / "Info.plist"


def test_renames_main_and_nested_bundles_altstore_style(tmp_path: Path) -> None:
    app = tmp_path / "App.app"
    _plist(app, {"CFBundleIdentifier": "com.example.app"})
    ext = _plist(
        app / "PlugIns" / "Widget.appex",
        {
            "CFBundleIdentifier": "com.example.app.Widget",
            "NSExtension": {"NSExtensionAttributes": {"WKAppBundleIdentifier": "com.example.app.watchkitapp"}},
        },
    )
    other = _plist(app / "PlugIns" / "Foreign.appex", {"CFBundleIdentifier": "com.other.thing"})
    _plist(app / "Frameworks" / "Lib.framework", {"CFBundleIdentifier": "com.example.app.framework"})

    changed = rename_bundle_ids(app, "com.example.app", "com.example.app.TEAM")

    assert plistlib.loads((app / "Info.plist").read_bytes())["CFBundleIdentifier"] == "com.example.app.TEAM"
    ext_data = plistlib.loads(ext.read_bytes())
    assert ext_data["CFBundleIdentifier"] == "com.example.app.TEAM.Widget"
    assert (
        ext_data["NSExtension"]["NSExtensionAttributes"]["WKAppBundleIdentifier"] == "com.example.app.TEAM.watchkitapp"
    )
    assert plistlib.loads(other.read_bytes())["CFBundleIdentifier"] == "com.other.thing"
    # Frameworks are not bundles AltStore re-identifies.
    assert len(changed) == 2


def test_prefix_match_is_on_dot_boundary(tmp_path: Path) -> None:
    app = tmp_path / "App.app"
    _plist(app, {"CFBundleIdentifier": "com.example.app"})
    sibling = _plist(app / "PlugIns" / "X.appex", {"CFBundleIdentifier": "com.example.application"})
    rename_bundle_ids(app, "com.example.app", "com.example.app.TEAM")
    assert plistlib.loads(sibling.read_bytes())["CFBundleIdentifier"] == "com.example.application"
