# SPDX-License-Identifier: GPL-3.0-or-later
"""Bundle-relative path resolution shared by patch operations that touch
files inside the app bundle (resource_replace/add/remove, plist_edit)."""
from __future__ import annotations

from pathlib import Path


class BundlePathError(Exception):
    """Raised when a bundle-relative path would escape the app bundle root."""


def resolve_bundle_path(bundle_root: Path, relative: str) -> Path:
    bundle_root = bundle_root.resolve()
    candidate = (bundle_root / relative).resolve()
    if candidate != bundle_root and bundle_root not in candidate.parents:
        raise BundlePathError(f"destination '{relative}' escapes the app bundle root")
    return candidate
