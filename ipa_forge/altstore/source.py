# SPDX-License-Identifier: GPL-3.0-or-later
"""AltStore Classic source.json app-entry export.

A distribution metadata layer, deliberately kept separate from the signing
engine (see the architecture doc's AltStore-source-is-optional note) -- it
only describes an already-patched-and-signed .ipa, it never produces one.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.manifest import sha256_of


def build_app_entry(ipa_path: Path, download_url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ipa_forge_export_") as tmp:
        app_path = extract_ipa(ipa_path, Path(tmp))
        bundle = load_bundle(app_path)
        name = bundle.info_plist.get("CFBundleName", bundle.main_executable_name)
        bundle_id = bundle.bundle_id
        version = bundle.version
        build = bundle.build

    return {
        "name": name,
        "bundleIdentifier": bundle_id,
        "version": version,
        "buildVersion": build,
        "downloadURL": download_url,
        "size": ipa_path.stat().st_size,
        "sha256": sha256_of(ipa_path),
    }


def write_source_json(entry: dict[str, Any], path: Path, source_name: str = "ipa-forge patched apps") -> None:
    source = {"name": source_name, "apps": [entry]}
    path.write_text(json.dumps(source, indent=2))
