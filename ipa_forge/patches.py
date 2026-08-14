# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch-set registry: one canonical definition per app.

The layout convention: ``patches/<app>/<app>.yaml`` (version lives *inside*
the definition's ``target.version``, not in the directory name). The GUI and
CLI use this to discover which patch set applies to a given IPA and to warn
on version mismatch without blocking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ipa_forge.patch.loader import PatchLoadError, load_patch_definition

_DEFAULT_PATCHES_DIR = Path(__file__).resolve().parent.parent / "patches"


def patches_root() -> Path:
    """The patch-set root; overridable via IPA_FORGE_PATCHES_DIR (tests use
    a temporary tree instead of the repo's patch sets)."""
    import os

    override = os.environ.get("IPA_FORGE_PATCHES_DIR")
    return Path(override) if override else _DEFAULT_PATCHES_DIR


@dataclass(frozen=True)
class PatchSet:
    name: str  # directory name, e.g. "youtube"
    definition: Path  # path to the canonical <app>.yaml
    bundle_id: str
    version_spec: str  # "exact: 21.32.4" or "min: … max: …" summary

    @property
    def version_exact(self) -> str | None:
        # only exact specs are interesting for the GUI warning
        spec = self.version_spec
        return spec.split("exact: ", 1)[1].strip("'\"") if "exact:" in spec else None


def discover_patch_sets(patches_dir: Path | None = None) -> list[PatchSet]:
    """Scan ``patches/*/<name>.yaml`` (the canonical definition per app)."""
    base = patches_dir or patches_root()
    if not base.is_dir():
        return []
    sets: list[PatchSet] = []
    for app_dir in sorted(base.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("."):
            continue
        candidate = app_dir / f"{app_dir.name}.yaml"
        if not candidate.is_file():
            continue
        try:
            definition = load_patch_definition(candidate)
        except PatchLoadError:
            continue  # not a definition we can parse; skip
        version = definition.target.version
        spec = f"exact: {version.exact}" if hasattr(version, "exact") else f"min: {version.min} max: {version.max}"
        sets.append(
            PatchSet(
                name=app_dir.name,
                definition=candidate,
                bundle_id=definition.target.bundle_id,
                version_spec=spec,
            )
        )
    return sets


def find_patch_sets_for_bundle(bundle_id: str, patches_dir: Path | None = None) -> list[PatchSet]:
    return [p for p in discover_patch_sets(patches_dir) if p.bundle_id == bundle_id]
