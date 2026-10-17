# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-identify an app and its nested bundles the way AltStore does at install.

AltStore installs `com.example.app` as `com.example.app.<TEAMID>` and moves
every nested bundle id under the new prefix (`com.example.app.Widget` ->
`com.example.app.<TEAMID>.Widget`). Tweaks are tested against exactly that
shape, so a locally signed build that copies it behaves like an AltStore
install -- and never collides with the App Store copy of the same app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ipa_forge.bundle.plist import read_plist, write_plist

_BUNDLE_SUFFIXES = (".app", ".appex")


def _reprefix(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str) and (value == old or value.startswith(old + ".")):
        return new + value[len(old) :]
    return value


def rename_bundle_ids(app_root: Path, old: str, new: str) -> list[Path]:
    """Rewrite `old`-prefixed ids in the app's and every nested bundle's
    Info.plist. Returns the plists that changed."""
    plists = [app_root / "Info.plist"] + [
        p / "Info.plist" for p in app_root.rglob("*") if p.is_dir() and p.name.endswith(_BUNDLE_SUFFIXES)
    ]
    changed = []
    for path in plists:
        if not path.is_file():
            continue
        data = read_plist(path)
        before = repr(data)
        for key in ("CFBundleIdentifier", "WKCompanionAppBundleIdentifier"):
            if key in data:
                data[key] = _reprefix(data[key], old, new)
        attrs = data.get("NSExtension", {}).get("NSExtensionAttributes", {})
        if isinstance(attrs, dict) and "WKAppBundleIdentifier" in attrs:
            attrs["WKAppBundleIdentifier"] = _reprefix(attrs["WKAppBundleIdentifier"], old, new)
        if repr(data) != before:
            write_plist(path, data)
            changed.append(path)
    return changed
