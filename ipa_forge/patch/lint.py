# SPDX-License-Identifier: GPL-3.0-or-later
"""IPA-free patch definition checks."""

from pathlib import Path

from ipa_forge.patch.binary import BinaryReplaceOp, PatternError
from ipa_forge.patch.loader import PatchLoadError, build_operations, load_patch_definition
from ipa_forge.patch.schema import ResourceAddSpec, ResourceReplaceSpec


def lint_definition(definition: Path) -> None:
    loaded = load_patch_definition(definition)
    for op in build_operations(loaded):
        if isinstance(op, BinaryReplaceOp):
            try:
                op.validate_patterns()
            except PatternError as e:
                raise PatchLoadError(f"{op.op_id}: {e}") from e
    for spec in loaded.patches:
        if isinstance(spec, (ResourceAddSpec, ResourceReplaceSpec)):
            source = (definition.parent / spec.source).resolve()
            if not source.exists():
                raise PatchLoadError(f"{spec.id}: source '{source}' does not exist")
            if isinstance(spec, ResourceReplaceSpec) and not source.is_file():
                raise PatchLoadError(f"{spec.id}: source '{source}' is not a file")
    seen: set[tuple[str, str]] = set()
    for hook in loaded.hooks or []:
        key = (hook.class_name, hook.selector)
        if key in seen:
            raise PatchLoadError(f"duplicate hook {hook.class_name} {hook.selector}")
        seen.add(key)
