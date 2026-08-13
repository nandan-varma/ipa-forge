# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared patch-operation contract. The core engine only knows this interface --
never a specific app, bundle id, or byte pattern."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from ipa_forge.bundle.models import AppBundle

PatchStatus = Literal["applied", "skipped", "failed", "dry_run_ok"]


@dataclass
class PatchContext:
    bundle: AppBundle
    patch_source_dir: Path
    """Directory that a patch definition's `source:`/`dylib:` fields resolve relative to."""


FileCategory = Literal["added", "modified", "removed"]


@dataclass
class PatchResult:
    op_id: str
    status: PatchStatus
    message: str = ""
    files_touched: list[Path] = field(default_factory=list)
    macho_modified: bool = False
    category: FileCategory | None = None
    """How files_touched changed, for the manifest's added/modified/removed breakdown."""


@runtime_checkable
class PatchOperation(Protocol):
    op_id: str

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        """Validate the operation can be applied without mutating anything."""
        ...

    def apply(self, ctx: PatchContext) -> PatchResult:
        """Perform the mutation. Callers must have already run dry_run and
        confirmed dry_run_ok across all operations before calling this."""
        ...
