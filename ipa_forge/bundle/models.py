"""Core bundle data model shared by the patch engine and the signing subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

MachOKind = Literal["main", "framework", "dylib", "appex", "watch_app", "other"]


@dataclass
class MachOTarget:
    """A single executable within the bundle (main binary, framework, dylib, extension, watch app)."""

    path: Path
    """Absolute path on disk, inside the extraction working directory."""

    bundle_relative: str
    """Path relative to the extraction root (e.g. "Payload/App.app/Frameworks/Foo.framework/Foo"),
    used to address this target from patch definitions and the manifest."""

    kind: MachOKind

    depth: int
    """Number of path components below the top-level app root; used to derive bottom-up sign order."""


@dataclass
class AppBundle:
    """In-memory representation of an extracted .app, with its nested executable inventory."""

    root: Path
    """Path to Payload/<App>.app."""

    extraction_root: Path
    """Path to the temp directory containing Payload/, i.e. root.parent.parent."""

    info_plist: dict[str, Any]
    bundle_id: str
    version: str
    build: str

    executables: list[MachOTarget] = field(default_factory=list)
    """Populated by the inventory walker, ordered bottom-up (deepest-nested first, main app last)."""

    entitlements: dict[str, Any] | None = None
    """Populated during the signing stage; None until then."""

    @property
    def main_executable_name(self) -> str:
        return self.info_plist["CFBundleExecutable"]
