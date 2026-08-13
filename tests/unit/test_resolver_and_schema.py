# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ipa_forge.bundle.models import AppBundle
from ipa_forge.patch.resolver import resolve_definitions, target_matches
from ipa_forge.patch.schema import PatchDefinition


def _bundle(bundle_id: str, version: str) -> AppBundle:
    return AppBundle(
        root=None,  # not needed for resolver-only tests
        extraction_root=None,
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
    assert spec.expected_matches == 1
    assert spec.arch is None
