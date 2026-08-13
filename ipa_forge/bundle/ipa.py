# SPDX-License-Identifier: GPL-3.0-or-later
"""IPA extraction and repackaging.

Uses the platform `zip`/`unzip` CLI tools rather than Python's `zipfile`
module because Apple bundles routinely contain symlinks (e.g.
`Foo.framework/Foo -> Versions/Current/Foo`), and `zip -y` / `unzip` round-trip
those correctly while `zipfile` does not preserve them by default.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ipa_forge.bundle.models import AppBundle
from ipa_forge.bundle.inventory import build_inventory
from ipa_forge.bundle.plist import read_plist
from ipa_forge.validators.ipa_validator import validate_ipa_structure


def extract_ipa(ipa_path: Path, dest_dir: Path) -> Path:
    """Extract ipa_path into dest_dir. Returns the path to Payload/<App>.app."""
    app_dir_name = validate_ipa_structure(ipa_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["unzip", "-qq", "-o", str(ipa_path), "-d", str(dest_dir)],
        check=True,
    )
    app_path = dest_dir / "Payload" / app_dir_name
    if not app_path.is_dir():
        raise FileNotFoundError(f"Expected extracted app bundle at {app_path}")
    return app_path


def repack_ipa(extraction_root: Path, output_path: Path) -> Path:
    """Zip extraction_root/Payload back into a standard-structure .ipa at output_path."""
    payload_dir = extraction_root / "Payload"
    if not payload_dir.is_dir():
        raise FileNotFoundError(f"No Payload/ directory under {extraction_root}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    subprocess.run(
        ["zip", "-qq", "-r", "-y", str(output_path), "Payload"],
        cwd=extraction_root,
        check=True,
    )
    return output_path


def load_bundle(app_path: Path) -> AppBundle:
    """Build an AppBundle model (with full inventory) from an already-extracted .app."""
    info_plist_path = app_path / "Info.plist"
    info_plist = read_plist(info_plist_path)

    bundle = AppBundle(
        root=app_path,
        extraction_root=app_path.parent.parent,
        info_plist=info_plist,
        bundle_id=info_plist["CFBundleIdentifier"],
        version=info_plist.get("CFBundleShortVersionString", ""),
        build=info_plist.get("CFBundleVersion", ""),
    )
    bundle.executables = build_inventory(bundle)
    return bundle
