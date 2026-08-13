"""Loads patch-definition YAML/JSON files and builds concrete PatchOperation instances."""
from __future__ import annotations

from pathlib import Path

import yaml

from ipa_forge.patch.base import PatchOperation
from ipa_forge.patch.binary import BinaryReplaceOp
from ipa_forge.patch.dylib import DylibInjectOp
from ipa_forge.patch.resource import ResourceAddOp, ResourceRemoveOp, ResourceReplaceOp
from ipa_forge.patch.schema import (
    BinaryReplaceSpec,
    DylibInjectSpec,
    PatchDefinition,
    ResourceAddSpec,
    ResourceRemoveSpec,
    ResourceReplaceSpec,
)


def load_patch_definition(path: Path) -> PatchDefinition:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return PatchDefinition.model_validate(raw)


def build_operations(definition: PatchDefinition) -> list[PatchOperation]:
    ops: list[PatchOperation] = []
    for spec in definition.patches:
        if isinstance(spec, BinaryReplaceSpec):
            ops.append(
                BinaryReplaceOp(
                    op_id=spec.id,
                    executable=spec.executable,
                    pattern=spec.pattern,
                    replacement=spec.replacement,
                    expected_matches=spec.expected_matches,
                    arch=spec.arch,
                )
            )
        elif isinstance(spec, ResourceReplaceSpec):
            ops.append(ResourceReplaceOp(op_id=spec.id, path=spec.path, source=spec.source))
        elif isinstance(spec, ResourceAddSpec):
            ops.append(ResourceAddOp(op_id=spec.id, path=spec.path, source=spec.source))
        elif isinstance(spec, ResourceRemoveSpec):
            ops.append(ResourceRemoveOp(op_id=spec.id, path=spec.path))
        elif isinstance(spec, DylibInjectSpec):
            ops.append(
                DylibInjectOp(
                    op_id=spec.id,
                    executable=spec.executable,
                    dylib=spec.dylib,
                    arch=spec.arch,
                    load_command=spec.load_command,
                )
            )
        else:
            raise ValueError(f"unknown patch spec type: {spec!r}")
    return ops
