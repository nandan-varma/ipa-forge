# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge analysis strings/symbols/security` CLI, end-to-end against the
synthetic fixture IPA (main + linked framework + standalone dylib)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.cli.main import app

runner = CliRunner()

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
SYNTHETIC_IPA = FIXTURES / "synthetic_app.ipa"


def test_strings_reports_matches_and_count() -> None:
    result = runner.invoke(app, ["analysis", "strings", "--ipa", str(SYNTHETIC_IPA), "--min-len", "4"])
    assert result.exit_code == 0
    assert "[TestApp]" in result.stdout
    assert "string(s)" in result.stderr


def test_strings_search_filters() -> None:
    result = runner.invoke(
        app, ["analysis", "strings", "--ipa", str(SYNTHETIC_IPA), "--search", "^ZZZ_definitely_absent_ZZZ$"]
    )
    assert result.exit_code == 0
    assert "-- 0 string(s)" in result.stderr


def test_symbols_lists_libraries_and_imports() -> None:
    result = runner.invoke(app, ["analysis", "symbols", "--ipa", str(SYNTHETIC_IPA)])
    assert result.exit_code == 0
    assert "linked libraries" in result.stdout
    assert "imported symbols" in result.stdout
    assert "exported symbols" in result.stdout


def test_symbols_binary_selects_framework() -> None:
    result = runner.invoke(app, ["analysis", "symbols", "--ipa", str(SYNTHETIC_IPA), "--binary", "TestFramework"])
    assert result.exit_code == 0
    assert "TestFramework" in result.stdout


def test_symbols_unknown_binary_fails() -> None:
    result = runner.invoke(app, ["analysis", "symbols", "--ipa", str(SYNTHETIC_IPA), "--binary", "NoSuchBinary"])
    assert result.exit_code == 1
    assert "no executable matching" in result.stderr


def test_security_reports_posture() -> None:
    result = runner.invoke(app, ["analysis", "security", "--ipa", str(SYNTHETIC_IPA)])
    assert result.exit_code == 0
    assert "PIE:" in result.stdout
    assert "Encrypted:" in result.stdout
    assert "Stack protector:" in result.stdout
