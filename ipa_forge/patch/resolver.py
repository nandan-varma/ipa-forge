# SPDX-License-Identifier: GPL-3.0-or-later
"""Selects which patch definitions apply to a given bundle, by bundle_id + version."""
from __future__ import annotations

from ipa_forge.bundle.models import AppBundle
from ipa_forge.patch.schema import PatchDefinition, VersionExact, VersionRange
from ipa_forge.patch.version import parse_version


def target_matches(bundle: AppBundle, definition: PatchDefinition) -> bool:
    if bundle.bundle_id != definition.target.bundle_id:
        return False

    version_spec = definition.target.version
    if isinstance(version_spec, VersionExact):
        return bundle.version == version_spec.exact

    v = parse_version(bundle.version)
    if version_spec.min is not None and v < parse_version(version_spec.min):
        return False
    if version_spec.max is not None and v >= parse_version(version_spec.max):
        return False
    return True


def resolve_definitions(bundle: AppBundle, definitions: list[PatchDefinition]) -> list[PatchDefinition]:
    return [d for d in definitions if target_matches(bundle, d)]
