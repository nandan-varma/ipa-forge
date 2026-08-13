# SPDX-License-Identifier: GPL-3.0-or-later
"""Dylib load-command injection patch operation.

Assumes the dylib file is already present in the bundle (placed there by a
separate resource_add operation, or shipped in the original app) -- this
operation's only job is the Mach-O load-command edit itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ipa_forge.machO.injector import InjectionStatus, inject_dylib
from ipa_forge.patch.base import PatchContext, PatchResult


@dataclass
class DylibInjectOp:
    op_id: str
    executable: str
    install_name: str
    arch: str | None = None
    load_command: str = "LC_LOAD_DYLIB"

    def _resolve_target(self, ctx: PatchContext) -> Path:
        for target in ctx.bundle.executables:
            if Path(target.bundle_relative).name == self.executable:
                return target.path
        raise FileNotFoundError(f"executable '{self.executable}' not found in bundle inventory")

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            self._resolve_target(ctx)
        except FileNotFoundError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))
        return PatchResult(op_id=self.op_id, status="dry_run_ok")

    def apply(self, ctx: PatchContext) -> PatchResult:
        try:
            target_path = self._resolve_target(ctx)
        except FileNotFoundError as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))

        result = inject_dylib(target_path, self.install_name, arch=self.arch, load_command=self.load_command)

        if result.status == InjectionStatus.INJECTED:
            return PatchResult(
                op_id=self.op_id,
                status="applied",
                message=result.message,
                files_touched=[target_path],
                macho_modified=True,
                category="modified",
            )
        if result.status == InjectionStatus.INJECTION_SKIPPED:
            return PatchResult(op_id=self.op_id, status="skipped", message=result.message)
        # INJECTION_UNSUPPORTED and INJECTION_FAILED both mean the patch did not apply.
        return PatchResult(op_id=self.op_id, status="failed", message=f"{result.status.value}: {result.message}")
