# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.cli.main import app

runner = CliRunner()


def test_core_doctor_does_not_require_apple_tools(monkeypatch):
    monkeypatch.setattr(
        "ipa_forge.cli.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}" if tool in {"zip", "unzip"} else None
    )
    monkeypatch.setattr("ipa_forge.cli.doctor.platform.system", lambda: "Linux")
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["ok"]
    assert {c["name"] for c in data["checks"]} == {"zip", "unzip"}


def test_doctor_explains_missing_requested_tools(monkeypatch):
    monkeypatch.setattr("ipa_forge.cli.doctor.shutil.which", lambda tool: None)
    result = runner.invoke(app, ["doctor", "--objc", "--signing", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert not data["ok"]
    assert any(c["name"] == "otool" and c["remedy"] for c in data["checks"])
    assert any(c["name"] == "codesign" and not c["ok"] for c in data["checks"])


def test_doctor_gui_reports_empty_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("IPA_FORGE_PATCHES_DIR", str(tmp_path))
    result = runner.invoke(app, ["doctor", "--gui", "--json"])
    assert result.exit_code == 1
    check = next(c for c in json.loads(result.stdout)["checks"] if c["name"] == "patch_sets")
    assert not check["ok"]
    assert "IPA_FORGE_PATCHES_DIR" in check["remedy"]


def test_doctor_definition_requires_hook_tools(monkeypatch, tmp_path: Path):
    definition = tmp_path / "patch.yaml"
    definition.write_text(
        "target: {bundle_id: example, version: {exact: '1'}}\npatches:\n"
        "  - {id: remove, type: resource_remove, path: file}\nhooks:\n"
        "  - {class: Example, selector: method}\n"
    )
    monkeypatch.setattr(
        "ipa_forge.cli.doctor.shutil.which", lambda tool: None if tool == "otool" else f"/usr/bin/{tool}"
    )
    result = runner.invoke(app, ["doctor", "--definition", str(definition), "--json"])
    assert result.exit_code == 1
    assert any(c["name"] == "otool" and not c["ok"] for c in json.loads(result.stdout)["checks"])


def test_doctor_missing_definition_is_structured(tmp_path: Path):
    result = runner.invoke(app, ["doctor", "--definition", str(tmp_path / "missing.yaml"), "--json"])
    assert result.exit_code == 1
    assert not json.loads(result.stdout)["checks"][0]["ok"]
