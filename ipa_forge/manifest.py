# SPDX-License-Identifier: GPL-3.0-or-later
"""Structured manifest emitted after patch application, before signing --
makes debugging a failed install possible independent of signing outcome.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ipa_forge.patch.base import PatchResult


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ProfileManifestEntry:
    uuid: str
    team_id: str
    expiration: str


@dataclass
class Manifest:
    input_sha256: str
    bundle_id: str
    version: str
    build: str
    patches_applied: list[dict[str, Any]] = field(default_factory=list)
    files_added: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    files_removed: list[str] = field(default_factory=list)
    macho_modified: list[str] = field(default_factory=list)
    profile: ProfileManifestEntry | None = None
    output_sha256: str | None = None

    @classmethod
    def from_patch_results(
        cls,
        input_ipa: Path,
        bundle_id: str,
        version: str,
        build: str,
        results: list[PatchResult],
    ) -> Manifest:
        manifest = cls(input_sha256=sha256_of(input_ipa), bundle_id=bundle_id, version=version, build=build)
        for result in results:
            manifest.patches_applied.append({"id": result.op_id, "status": result.status, "message": result.message})
            touched = [str(p) for p in result.files_touched]
            if result.category == "added":
                manifest.files_added.extend(touched)
            elif result.category == "removed":
                manifest.files_removed.extend(touched)
            elif result.category == "modified":
                manifest.files_modified.extend(touched)
            if result.macho_modified:
                manifest.macho_modified.extend(touched)
        return manifest

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def write(self, path: Path) -> None:
        path.write_text(self.to_json())
