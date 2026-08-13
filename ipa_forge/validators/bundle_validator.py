# SPDX-License-Identifier: GPL-3.0-or-later
"""Validates an extracted AppBundle's Info.plist and main executable presence."""

from __future__ import annotations

from ipa_forge.bundle.models import AppBundle


class BundleValidationError(Exception):
    pass


def validate_bundle(bundle: AppBundle) -> None:
    if "CFBundleIdentifier" not in bundle.info_plist:
        raise BundleValidationError("Info.plist is missing CFBundleIdentifier")
    if "CFBundleExecutable" not in bundle.info_plist:
        raise BundleValidationError("Info.plist is missing CFBundleExecutable")

    main_executable = bundle.root / bundle.main_executable_name
    if not main_executable.is_file():
        raise BundleValidationError(f"Main executable not found at {main_executable}")

    if not any(t.kind == "main" for t in bundle.executables):
        raise BundleValidationError(
            f"Main executable '{bundle.main_executable_name}' was not classified as 'main' "
            "by the inventory walker -- check CFBundleExecutable against the on-disk layout"
        )
