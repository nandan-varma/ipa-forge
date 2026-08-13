"""Dylib injection patch operation.

Placeholder for Phase 1-3 wiring; the real LIEF-backed implementation with
the INJECTED/INJECTION_SKIPPED/INJECTION_UNSUPPORTED/INJECTION_FAILED status
model lands in Phase 4 (see ipa_forge.machO.injector).
"""
from __future__ import annotations

from dataclasses import dataclass

from ipa_forge.patch.base import PatchContext, PatchResult


@dataclass
class DylibInjectOp:
    op_id: str
    executable: str
    dylib: str
    arch: str | None = None
    load_command: str = "LC_LOAD_DYLIB"

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        return PatchResult(op_id=self.op_id, status="failed", message="dylib_inject not yet implemented (Phase 4)")

    def apply(self, ctx: PatchContext) -> PatchResult:
        return PatchResult(op_id=self.op_id, status="failed", message="dylib_inject not yet implemented (Phase 4)")
