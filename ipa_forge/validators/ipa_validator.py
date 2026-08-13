# SPDX-License-Identifier: GPL-3.0-or-later
"""Validates raw .ipa structure before extraction (stage 1 of the pipeline)."""

from __future__ import annotations

import zipfile
from pathlib import Path


class IpaValidationError(Exception):
    pass


def validate_ipa_structure(ipa_path: Path) -> str:
    """Validate that ipa_path is a well-formed zip with exactly one Payload/*.app.

    Returns the app bundle's directory name (e.g. "MyApp.app").
    """
    if not ipa_path.is_file():
        raise IpaValidationError(f"{ipa_path} does not exist")
    if not zipfile.is_zipfile(ipa_path):
        raise IpaValidationError(f"{ipa_path} is not a valid zip archive")

    with zipfile.ZipFile(ipa_path) as zf:
        names = zf.namelist()
        if not any(n.startswith("Payload/") for n in names):
            raise IpaValidationError("IPA does not contain a Payload/ directory")

        app_dirs = {
            parts[1]
            for n in names
            if (parts := n.split("/"))[0] == "Payload" and len(parts) > 1 and parts[1].endswith(".app")
        }
        if len(app_dirs) == 0:
            raise IpaValidationError("No Payload/*.app found in IPA")
        if len(app_dirs) > 1:
            raise IpaValidationError(f"Expected exactly one Payload/*.app, found {len(app_dirs)}: {sorted(app_dirs)}")

        return next(iter(app_dirs))
