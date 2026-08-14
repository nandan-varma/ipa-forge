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


def _write_patch_set(patches_dir: Path, name: str, bundle_id: str, version_block: str) -> Path:
    """Write patches/<name>/<name>.yaml and return its path."""
    app_dir = patches_dir / name
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / f"{name}.yaml"
    path.write_text(
        "target:\n"
        f'  bundle_id: "{bundle_id}"\n'
        f"  version:\n{version_block}"
        "patches:\n"
        "  - type: resource_remove\n"
        "    id: x\n"
        "    path: a.txt\n"
    )
    return path


def test_exact_version_match() -> None:
    definition = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"exact": "1.2.3"}},
            "patches": [{"type": "resource_remove", "id": "x", "path": "a.txt"}],
        }
    )
    assert target_matches(_bundle("com.example.test", "1.2.3"), definition)
    assert not target_matches(_bundle("com.example.test", "1.2.4"), definition)
    assert not target_matches(_bundle("com.other.app", "1.2.3"), definition)


def test_range_version_match() -> None:
    definition = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"min": "1.0.0", "max": "2.0.0"}},
            "patches": [{"type": "resource_remove", "id": "x", "path": "a.txt"}],
        }
    )
    assert target_matches(_bundle("com.example.test", "1.5.0"), definition)
    assert not target_matches(_bundle("com.example.test", "2.0.0"), definition)  # max is exclusive
    assert not target_matches(_bundle("com.example.test", "0.9.0"), definition)


def test_resolve_definitions_filters_list() -> None:
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


def test_binary_replace_spec_defaults() -> None:
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


def test_patch_definition_requires_at_least_one_operation() -> None:
    with pytest.raises(ValidationError):
        PatchDefinition.model_validate(
            {"target": {"bundle_id": "com.example.test", "version": {"exact": "1.0.0"}}, "patches": []}
        )


def test_load_patch_definition_empty_file_raises_patch_load_error(tmp_path: Path) -> None:
    """F2: schema violations surface as PatchLoadError, not raw ValidationError."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(PatchLoadError, match="is invalid"):
        load_patch_definition(empty)


def test_load_patch_definition_wrong_shape_raises_patch_load_error(tmp_path: Path) -> None:
    """F2: a YAML list instead of a mapping is a clean PatchLoadError too."""
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n")
    with pytest.raises(PatchLoadError, match="is invalid"):
        load_patch_definition(bad)


def test_load_patch_definition_missing_file_raises_patch_load_error(tmp_path: Path) -> None:
    with pytest.raises(PatchLoadError, match="cannot read"):
        load_patch_definition(tmp_path / "nope.yaml")


def test_discover_patch_sets_formats_exact_and_range_specs(tmp_path: Path) -> None:
    from ipa_forge.patches import discover_patch_sets

    _write_patch_set(tmp_path, "appone", "com.example.one", '    exact: "1.2.3"\n')
    _write_patch_set(tmp_path, "apptwo", "com.example.two", '    min: "1.0.0"\n    max: "2.0.0"\n')

    sets = discover_patch_sets(tmp_path)
    assert [s.name for s in sets] == ["appone", "apptwo"]
    by_name = {s.name: s for s in sets}
    assert by_name["appone"].version_spec == "exact: 1.2.3"
    assert by_name["appone"].version_exact == "1.2.3"
    assert by_name["apptwo"].version_spec == "min: 1.0.0 max: 2.0.0"
    assert by_name["apptwo"].version_exact is None


def test_discover_patch_sets_skips_non_definitions(tmp_path: Path) -> None:
    from ipa_forge.patches import discover_patch_sets

    # valid definition, a dir with no yaml, and an unparseable yaml
    _write_patch_set(tmp_path, "good", "com.example.good", '    exact: "1.0.0"\n')
    (tmp_path / "noyaml").mkdir()
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "bad.yaml").write_text("target: [not, valid\n")

    sets = discover_patch_sets(tmp_path)
    assert [s.name for s in sets] == ["good"]


def test_find_patch_sets_for_bundle_filters(tmp_path: Path) -> None:
    from ipa_forge.patches import find_patch_sets_for_bundle

    _write_patch_set(tmp_path, "wanted", "com.example.wanted", '    exact: "1.0.0"\n')
    _write_patch_set(tmp_path, "other", "com.example.other", '    exact: "2.0.0"\n')

    matches = find_patch_sets_for_bundle("com.example.wanted", tmp_path)
    assert [s.name for s in matches] == ["wanted"]
