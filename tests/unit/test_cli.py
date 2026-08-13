# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI coverage: the `forge` command surface (inspect/validate/patch/export-source).

These exercise the Typer app through its own CliRunner, against the checked-in
synthetic fixture. None of them reach the signing stages (patch is always
--dry-run here), so they run on Linux too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ipa_forge.cli.main import app

runner = CliRunner()

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
_FIXTURE_IPA = _FIXTURES / "synthetic_app.ipa"
_FIXTURE_PATCH = _FIXTURES / "patches" / "example.yaml"


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("inspect", "validate", "patch", "export-source", "gui"):
        assert command in result.stdout


def test_inspect_reports_bundle_metadata():
    result = runner.invoke(app, ["inspect", str(_FIXTURE_IPA)])
    assert result.exit_code == 0, result.output
    assert "com.example.synthetic" in result.stdout
    assert "1.0.0" in result.stdout
    assert "TestApp" in result.stdout


def test_validate_ok_on_valid_ipa():
    result = runner.invoke(app, ["validate", str(_FIXTURE_IPA)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.stdout


def test_inspect_rejects_non_ipa_with_clean_error(tmp_path: Path):
    bogus = tmp_path / "not_an_ipa.ipa"
    bogus.write_text("this is not a zip archive")
    result = runner.invoke(app, ["inspect", str(bogus)])
    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_patch_dry_run_succeeds_without_touching_signing(tmp_path: Path):
    dummy_profile = tmp_path / "dummy.mobileprovision"
    dummy_profile.write_bytes(b"not read in dry-run mode")
    out = tmp_path / "out.ipa"

    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(_FIXTURE_PATCH),
            "--identity",
            "Apple Development",
            "--profile",
            str(dummy_profile),
            "--output",
            str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Dry run OK" in result.stdout
    assert not out.exists()


def test_patch_failing_dry_run_exits_1_with_error(tmp_path: Path):
    dummy_profile = tmp_path / "dummy.mobileprovision"
    dummy_profile.write_bytes(b"not read in dry-run mode")
    bad_patch = tmp_path / "bad.yaml"
    bad_patch.write_text(
        "target:\n"
        "  bundle_id: com.example.synthetic\n"
        "  version: {exact: '1.0.0'}\n"
        "patches:\n"
        "  - id: missing-source\n"
        "    type: resource_replace\n"
        "    path: asset.txt\n"
        "    source: does_not_exist.txt\n"
    )
    out = tmp_path / "out.ipa"

    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(bad_patch),
            "--identity",
            "Apple Development",
            "--profile",
            str(dummy_profile),
            "--output",
            str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "missing-source" in result.stderr
    assert not out.exists()


def test_export_source_writes_source_json(tmp_path: Path):
    out = tmp_path / "source.json"
    result = runner.invoke(
        app,
        [
            "export-source",
            "--ipa",
            str(_FIXTURE_IPA),
            "--download-url",
            "https://example.com/patched.ipa",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["apps"][0]["bundleIdentifier"] == "com.example.synthetic"
    assert data["apps"][0]["downloadURL"] == "https://example.com/patched.ipa"


# --- F4: dry-run must not demand signing inputs ---


def test_patch_dry_run_without_identity_or_profile(tmp_path: Path):
    out = tmp_path / "out.ipa"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(_FIXTURE_PATCH),
            "--output",
            str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Dry run OK" in result.stdout


def test_patch_real_run_requires_identity(tmp_path: Path):
    dummy_profile = tmp_path / "dummy.mobileprovision"
    dummy_profile.write_bytes(b"x")
    out = tmp_path / "out.ipa"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(_FIXTURE_PATCH),
            "--profile",
            str(dummy_profile),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert "--identity is required" in result.stderr


def test_patch_real_run_requires_profile(tmp_path: Path):
    out = tmp_path / "out.ipa"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(_FIXTURE_PATCH),
            "--identity",
            "Apple Development",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert "--profile is required" in result.stderr


# --- F1: a definition that matches nothing must not silently succeed ---


def _non_matching_patch(tmp_path: Path) -> Path:
    p = tmp_path / "wrong_target.yaml"
    p.write_text(
        "target:\n"
        "  bundle_id: com.example.wrong\n"
        "  version: {exact: '1.0.0'}\n"
        "patches:\n"
        "  - id: x\n"
        "    type: resource_remove\n"
        "    path: nope.txt\n"
    )
    return p


def test_patch_non_matching_definition_warns_in_dry_run(tmp_path: Path):
    out = tmp_path / "out.ipa"
    # warnings.warn does not route through click's captured stderr -- assert
    # on pytest's own warning capture instead.
    with pytest.warns(UserWarning, match="matches 0 patch operations"):
        result = runner.invoke(
            app,
            [
                "patch",
                "--ipa",
                str(_FIXTURE_IPA),
                "--patches",
                str(_non_matching_patch(tmp_path)),
                "--output",
                str(out),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "Dry run OK" in result.stdout


def test_patch_non_matching_definition_fails_real_run(tmp_path: Path):
    dummy_profile = tmp_path / "dummy.mobileprovision"
    dummy_profile.write_bytes(b"x")
    out = tmp_path / "out.ipa"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(_non_matching_patch(tmp_path)),
            "--identity",
            "Apple Development",
            "--profile",
            str(dummy_profile),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 1
    assert "refusing to produce an unpatched IPA" in result.stderr
    assert not out.exists()


# --- F2: schema violations are clean errors, never tracebacks ---


def test_patch_empty_definition_is_a_clean_error(tmp_path: Path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    out = tmp_path / "out.ipa"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(empty),
            "--output",
            str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_patch_wrong_shape_definition_is_a_clean_error(tmp_path: Path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a\n- list\n")
    out = tmp_path / "out.ipa"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(_FIXTURE_IPA),
            "--patches",
            str(bad),
            "--output",
            str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
