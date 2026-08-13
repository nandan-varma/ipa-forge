# SPDX-License-Identifier: GPL-3.0-or-later
"""Resource file replace/add/remove operations, sandboxed to the app bundle root.

Trusted-input model: `source:` paths resolve relative to the patch definition
file and are intentionally *not* sandboxed -- the definition, the IPA, and the
signing credentials are all supplied by the same trusted user, so a definition
may reference an absolute path or sibling directory (F9). Revisit if the GUI
ever serves untrusted/multi-user uploads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ipa_forge.patch.base import PatchContext, PatchResult
from ipa_forge.patch.paths import BundlePathError, resolve_bundle_path


@dataclass
class ResourceReplaceOp:
    op_id: str
    path: str
    source: str

    def _resolve(self, ctx: PatchContext) -> tuple[Path, Path]:
        dest = resolve_bundle_path(ctx.bundle.root, self.path)
        src = (ctx.patch_source_dir / self.source).resolve()
        return dest, src

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            dest, src = self._resolve(ctx)
        except BundlePathError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))
        if not src.is_file():
            return PatchResult(op_id=self.op_id, status="failed", message=f"source '{src}' does not exist")
        if not dest.is_file():
            return PatchResult(
                op_id=self.op_id,
                status="failed",
                message=f"destination '{dest}' does not exist (use resource_add to create new files)",
            )
        return PatchResult(op_id=self.op_id, status="dry_run_ok")

    def apply(self, ctx: PatchContext) -> PatchResult:
        dry = self.dry_run(ctx)
        if dry.status != "dry_run_ok":
            return dry
        dest, src = self._resolve(ctx)
        try:
            dest.write_bytes(src.read_bytes())
        except OSError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=f"failed to replace '{dest}': {e}")
        return PatchResult(
            op_id=self.op_id, status="applied", message=f"replaced {dest}", files_touched=[dest], category="modified"
        )


@dataclass
class ResourceAddOp:
    op_id: str
    path: str
    source: str

    def _resolve(self, ctx: PatchContext) -> tuple[Path, Path]:
        dest = resolve_bundle_path(ctx.bundle.root, self.path)
        src = (ctx.patch_source_dir / self.source).resolve()
        return dest, src

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            dest, src = self._resolve(ctx)
        except BundlePathError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))
        if not src.is_file():
            return PatchResult(op_id=self.op_id, status="failed", message=f"source '{src}' does not exist")
        if dest.exists():
            return PatchResult(
                op_id=self.op_id,
                status="failed",
                message=f"destination '{dest}' already exists (use resource_replace to overwrite)",
            )
        return PatchResult(op_id=self.op_id, status="dry_run_ok")

    def apply(self, ctx: PatchContext) -> PatchResult:
        dry = self.dry_run(ctx)
        if dry.status != "dry_run_ok":
            return dry
        dest, src = self._resolve(ctx)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
        except OSError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=f"failed to add '{dest}': {e}")
        return PatchResult(
            op_id=self.op_id, status="applied", message=f"added {dest}", files_touched=[dest], category="added"
        )


@dataclass
class ResourceRemoveOp:
    op_id: str
    path: str

    def _resolve(self, ctx: PatchContext) -> Path:
        return resolve_bundle_path(ctx.bundle.root, self.path)

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            dest = self._resolve(ctx)
        except BundlePathError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))
        if not dest.exists():
            return PatchResult(op_id=self.op_id, status="failed", message=f"destination '{dest}' does not exist")
        if not dest.is_file():
            return PatchResult(
                op_id=self.op_id,
                status="failed",
                message=f"destination '{dest}' is not a file (only files can be removed)",
            )
        return PatchResult(op_id=self.op_id, status="dry_run_ok")

    def apply(self, ctx: PatchContext) -> PatchResult:
        dry = self.dry_run(ctx)
        if dry.status != "dry_run_ok":
            return dry
        dest = self._resolve(ctx)
        try:
            dest.unlink()
        except OSError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=f"failed to remove '{dest}': {e}")
        return PatchResult(
            op_id=self.op_id, status="applied", message=f"removed {dest}", files_touched=[dest], category="removed"
        )
