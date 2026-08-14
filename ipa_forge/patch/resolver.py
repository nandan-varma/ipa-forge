# SPDX-License-Identifier: GPL-3.0-or-later
"""Selects which patch definitions apply to a given bundle, by bundle_id + version."""

from __future__ import annotations

from ipa_forge.bundle.models import AppBundle
from ipa_forge.patch.schema import PatchDefinition, VersionExact
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
    return version_spec.max is None or v < parse_version(version_spec.max)


def resolve_definitions(
    bundle: AppBundle, definitions: list[PatchDefinition], *, ignore_version: bool = False
) -> list[PatchDefinition]:
    """Select definitions whose bundle id matches; version must match unless
    ``ignore_version`` (used by the GUI's non-blocking mismatch path — the
    hooks gate still guards what actually attaches)."""
    result = []
    for d in definitions:
        if bundle.bundle_id != d.target.bundle_id:
            continue
        if ignore_version or target_matches(bundle, d):
            result.append(d)
    return result
