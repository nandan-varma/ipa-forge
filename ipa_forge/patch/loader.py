# SPDX-License-Identifier: GPL-3.0-or-later
"""Loads patch-definition YAML/JSON files and builds concrete PatchOperation instances."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from ipa_forge.patch.base import PatchOperation
from ipa_forge.patch.binary import BinaryReplaceOp
from ipa_forge.patch.dylib import DylibInjectOp
from ipa_forge.patch.plist import PlistEditOp
from ipa_forge.patch.resource import ResourceAddOp, ResourceRemoveOp, ResourceReplaceOp
from ipa_forge.patch.schema import (
    BinaryReplaceSpec,
    DylibInjectSpec,
    PatchDefinition,
    PlistEditSpec,
    ResourceAddSpec,
    ResourceRemoveSpec,
    ResourceReplaceSpec,
)


class PatchLoadError(Exception):
    """Raised when the patch-definition file cannot be read, parsed as YAML, or validated."""


def _validation_error_details(error: ValidationError) -> str:
    """Compact single-line summary of a pydantic ValidationError."""
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or '<root>'}: {err['msg']}" for err in error.errors())


def load_patch_definition(path: Path) -> PatchDefinition:
    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except OSError as e:
        raise PatchLoadError(f"cannot read patch definition '{path}': {e}") from e
    except yaml.YAMLError as e:
        raise PatchLoadError(f"patch definition '{path}' is not valid YAML: {e}") from e
    try:
        return PatchDefinition.model_validate(raw)
    except ValidationError as e:
        # Surface schema violations as a single-line actionable error rather
        # than letting pydantic's multi-line ValidationError escape as a
        # traceback (F2).
        raise PatchLoadError(f"patch definition '{path}' is invalid: {_validation_error_details(e)}") from e


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
                    install_name=spec.install_name,
                    arch=spec.arch,
                    load_command=spec.load_command,
                )
            )
        elif isinstance(spec, PlistEditSpec):
            ops.append(PlistEditOp(op_id=spec.id, action=spec.action, key=spec.key, value=spec.value, path=spec.path))
        else:
            # Unreachable via the pydantic discriminated union in patch/schema.py
            raise TypeError(f"unknown patch spec type: {spec!r}")
    return ops
