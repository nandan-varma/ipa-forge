# SPDX-License-Identifier: GPL-3.0-or-later
"""`bundle_executable_paths`: the shared main+framework+dylib+... enumeration
used by both hook verification (main+framework only) and the general-purpose
analysis commands (every executable in the IPA)."""

from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.machO.detect import bundle_executable_paths

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_default_kinds_includes_every_executable(tmp_path: Path) -> None:
    app_path = extract_ipa(FIXTURES / "synthetic_app.ipa", tmp_path / "extracted")
    bundle = load_bundle(app_path)
    paths = bundle_executable_paths(bundle)
    names = {p.name for p in paths}
    # main executable + the linked framework + the standalone injectable dylib
    assert "TestApp" in names
    assert "TestFramework" in names
    assert "libInjectable.dylib" in names


def test_kinds_filter_restricts_to_framework_only(tmp_path: Path) -> None:
    app_path = extract_ipa(FIXTURES / "synthetic_app.ipa", tmp_path / "extracted")
    bundle = load_bundle(app_path)
    paths = bundle_executable_paths(bundle, kinds={"framework"})
    names = {p.name for p in paths}
    assert names == {"TestApp", "TestFramework"}


def test_main_executable_never_duplicated(tmp_path: Path) -> None:
    app_path = extract_ipa(FIXTURES / "synthetic_app.ipa", tmp_path / "extracted")
    bundle = load_bundle(app_path)
    paths = bundle_executable_paths(bundle)
    assert sum(1 for p in paths if p.name == "TestApp") == 1
