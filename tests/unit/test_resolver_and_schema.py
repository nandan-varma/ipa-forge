# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ipa_forge.bundle.models import AppBundle
from ipa_forge.patch.loader import PatchLoadError, load_patch_definition
from ipa_forge.patch.resolver import resolve_definitions, target_matches
from ipa_forge.patch.schema import BinaryReplaceSpec, PatchDefinition


def _bundle(bundle_id: str, version: str) -> AppBundle:
    return AppBundle(
        root=Path("unused.app"),  # resolver-only tests never touch the filesystem
        extraction_root=Path("."),
        info_plist={},
        bundle_id=bundle_id,
        version=version,
        build="1",
    )


def test_exact_version_match():
    definition = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"exact": "1.2.3"}},
            "patches": [{"type": "resource_remove", "id": "x", "path": "a.txt"}],
        }
    )
    assert target_matches(_bundle("com.example.test", "1.2.3"), definition)
    assert not target_matches(_bundle("com.example.test", "1.2.4"), definition)
    assert not target_matches(_bundle("com.other.app", "1.2.3"), definition)


def test_range_version_match():
    definition = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"min": "1.0.0", "max": "2.0.0"}},
            "patches": [{"type": "resource_remove", "id": "x", "path": "a.txt"}],
        }
    )
    assert target_matches(_bundle("com.example.test", "1.5.0"), definition)
    assert not target_matches(_bundle("com.example.test", "2.0.0"), definition)  # max is exclusive
    assert not target_matches(_bundle("com.example.test", "0.9.0"), definition)


def test_resolve_definitions_filters_list():
    d1 = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"exact": "1.0.0"}},
            "patches": [{"type": "resource_remove", "id": "x", "path": "a.txt"}],
        }
    )
    d2 = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.other.app", "version": {"exact": "1.0.0"}},
            "patches": [{"type": "resource_remove", "id": "y", "path": "b.txt"}],
        }
    )
    matched = resolve_definitions(_bundle("com.example.test", "1.0.0"), [d1, d2])
    assert matched == [d1]


def test_binary_replace_spec_defaults():
    definition = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"exact": "1.0.0"}},
            "patches": [
                {
                    "type": "binary_replace",
                    "id": "b1",
                    "executable": "App",
                    "pattern": "AA BB",
                    "replacement": "00 00",
                }
            ],
        }
    )
    spec = definition.patches[0]
    assert isinstance(spec, BinaryReplaceSpec)
    assert spec.expected_matches == 1
    assert spec.arch is None


def test_patch_definition_requires_at_least_one_operation():
    with pytest.raises(ValidationError):
        PatchDefinition.model_validate(
            {"target": {"bundle_id": "com.example.test", "version": {"exact": "1.0.0"}}, "patches": []}
        )


def test_load_patch_definition_empty_file_raises_patch_load_error(tmp_path: Path):
    """F2: schema violations surface as PatchLoadError, not raw ValidationError."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(PatchLoadError, match="is invalid"):
        load_patch_definition(empty)


def test_load_patch_definition_wrong_shape_raises_patch_load_error(tmp_path: Path):
    """F2: a YAML list instead of a mapping is a clean PatchLoadError too."""
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n")
    with pytest.raises(PatchLoadError, match="is invalid"):
        load_patch_definition(bad)


def test_load_patch_definition_missing_file_raises_patch_load_error(tmp_path: Path):
    with pytest.raises(PatchLoadError, match="cannot read"):
        load_patch_definition(tmp_path / "nope.yaml")
