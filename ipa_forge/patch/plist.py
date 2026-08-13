# SPDX-License-Identifier: GPL-3.0-or-later
"""Info.plist key set/remove operation, following the same single-file,
single-responsibility pattern as the resource operations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ipa_forge.bundle.plist import read_plist, write_plist
from ipa_forge.patch.base import PatchContext, PatchResult
from ipa_forge.patch.paths import BundlePathError, resolve_bundle_path


@dataclass
class PlistEditOp:
    op_id: str
    action: Literal["set", "remove"]
    key: str
    value: Any = None
    path: str = "Info.plist"

    def _resolve(self, ctx: PatchContext) -> Path:
        return resolve_bundle_path(ctx.bundle.root, self.path)

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            target = self._resolve(ctx)
        except BundlePathError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))
        if not target.is_file():
            return PatchResult(op_id=self.op_id, status="failed", message=f"plist '{target}' does not exist")
        try:
            plist = read_plist(target)
        except Exception as e:
            return PatchResult(op_id=self.op_id, status="failed", message=f"failed to parse '{target}': {e}")
        if self.action == "remove" and self.key not in plist:
            return PatchResult(
                op_id=self.op_id, status="failed", message=f"key '{self.key}' not present in {target}"
            )
        return PatchResult(op_id=self.op_id, status="dry_run_ok")

    def apply(self, ctx: PatchContext) -> PatchResult:
        dry = self.dry_run(ctx)
        if dry.status != "dry_run_ok":
            return dry

        target = self._resolve(ctx)
        plist = read_plist(target)
        if self.action == "set":
            plist[self.key] = self.value
        else:
            del plist[self.key]
        write_plist(target, plist)

        return PatchResult(
            op_id=self.op_id,
            status="applied",
            message=f"{self.action} '{self.key}' in {target}",
            files_touched=[target],
            category="modified",
        )
