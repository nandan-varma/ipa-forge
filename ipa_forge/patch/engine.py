# SPDX-License-Identifier: GPL-3.0-or-later
"""Dry-run gate + ordered apply for a resolved set of patch operations.

Enforces pipeline stages 5-8: every operation must report dry_run_ok before
anything mutates, then mutations run resource ops -> binary ops -> dylib
injection last (LIEF load-command rewrites can shift byte offsets binary
patches depend on, so injection must never run before binary patching).
"""
from __future__ import annotations

from ipa_forge.patch.base import PatchContext, PatchOperation, PatchResult
from ipa_forge.patch.binary import BinaryReplaceOp
from ipa_forge.patch.dylib import DylibInjectOp
from ipa_forge.patch.resource import ResourceAddOp, ResourceRemoveOp, ResourceReplaceOp


class PatchValidationError(Exception):
    def __init__(self, results: list[PatchResult]):
        self.results = results
        failures = "; ".join(f"{r.op_id}: {r.message}" for r in results if r.status == "failed")
        super().__init__(f"patch dry-run validation failed: {failures}")


def dry_run_all(ops: list[PatchOperation], ctx: PatchContext) -> list[PatchResult]:
    return [op.dry_run(ctx) for op in ops]


def _apply_order_rank(op: PatchOperation) -> int:
    if isinstance(op, (ResourceReplaceOp, ResourceAddOp, ResourceRemoveOp)):
        return 0
    if isinstance(op, BinaryReplaceOp):
        return 1
    if isinstance(op, DylibInjectOp):
        return 2
    return 3


def apply_all(ops: list[PatchOperation], ctx: PatchContext) -> list[PatchResult]:
    dry_results = dry_run_all(ops, ctx)
    if any(r.status != "dry_run_ok" for r in dry_results):
        raise PatchValidationError(dry_results)

    ordered = sorted(ops, key=_apply_order_rank)
    return [op.apply(ctx) for op in ordered]
