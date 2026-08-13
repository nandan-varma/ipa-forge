# SPDX-License-Identifier: GPL-3.0-or-later
"""Pydantic schema for the external YAML/JSON patch-definition contract.

The core engine understands these operation *types* but never a specific
bundle id or byte pattern -- those only ever live in user-supplied definition
files.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator


class VersionExact(BaseModel):
    exact: str


class VersionRange(BaseModel):
    min: str | None = None
    max: str | None = None


class TargetSpec(BaseModel):
    bundle_id: str
    version: VersionExact | VersionRange


class BinaryReplaceSpec(BaseModel):
    type: Literal["binary_replace"]
    id: str
    executable: str
    pattern: str
    replacement: str
    expected_matches: int = 1
    arch: str | None = None


class ResourceReplaceSpec(BaseModel):
    type: Literal["resource_replace"]
    id: str
    path: str
    source: str


class ResourceAddSpec(BaseModel):
    type: Literal["resource_add"]
    id: str
    path: str
    source: str


class ResourceRemoveSpec(BaseModel):
    type: Literal["resource_remove"]
    id: str
    path: str


class DylibInjectSpec(BaseModel):
    type: Literal["dylib_inject"]
    id: str
    executable: str
    # The load path to add as an LC_LOAD_DYLIB/LC_LOAD_WEAK_DYLIB entry (e.g.
    # "@rpath/libFoo.dylib"), not a source file to copy in -- getting the
    # dylib itself into the bundle is a separate resource_add operation, so
    # this stays a single-responsibility Mach-O load-command edit.
    install_name: str
    arch: str | None = None
    load_command: Literal["LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB"] = "LC_LOAD_DYLIB"


class PlistEditSpec(BaseModel):
    type: Literal["plist_edit"]
    id: str
    action: Literal["set", "remove"]
    key: str
    value: Any = None
    path: str = "Info.plist"

    @model_validator(mode="after")
    def _value_required_for_set(self) -> "PlistEditSpec":
        if self.action == "set" and self.value is None:
            raise ValueError("plist_edit with action 'set' requires a non-null 'value'")
        return self


PatchSpec = Annotated[
    Union[
        BinaryReplaceSpec,
        ResourceReplaceSpec,
        ResourceAddSpec,
        ResourceRemoveSpec,
        DylibInjectSpec,
        PlistEditSpec,
    ],
    Field(discriminator="type"),
]


class PatchDefinition(BaseModel):
    target: TargetSpec
    patches: list[PatchSpec]
