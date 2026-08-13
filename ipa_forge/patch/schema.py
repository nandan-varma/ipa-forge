"""Pydantic schema for the external YAML/JSON patch-definition contract.

The core engine understands these operation *types* but never a specific
bundle id or byte pattern -- those only ever live in user-supplied definition
files.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


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
    dylib: str
    arch: str | None = None
    load_command: Literal["LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB"] = "LC_LOAD_DYLIB"


PatchSpec = Annotated[
    Union[
        BinaryReplaceSpec,
        ResourceReplaceSpec,
        ResourceAddSpec,
        ResourceRemoveSpec,
        DylibInjectSpec,
    ],
    Field(discriminator="type"),
]


class PatchDefinition(BaseModel):
    target: TargetSpec
    patches: list[PatchSpec]
