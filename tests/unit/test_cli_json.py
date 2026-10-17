# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from ipa_forge.cli.main import app

ROOT = Path(__file__).resolve().parents[2]
IPA = ROOT / "fixtures/synthetic_app.ipa"
PATCHES = ROOT / "fixtures/patches/example.yaml"
runner = CliRunner()


@pytest.mark.parametrize("command", ["inspect", "validate"])
def test_bundle_json_has_no_human_output_or_temporary_paths(command):
    result = runner.invoke(app, [command, str(IPA), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["schema_version"] == 1 and data["ok"]
    assert result.stderr == ""
    if command == "inspect":
        assert data["bundle_id"] == "com.example.synthetic"
        assert {t["kind"] for t in data["executables"]} == {"main", "framework", "dylib"}
        assert all(t["path"].startswith("Payload/") for t in data["executables"])


@pytest.mark.parametrize("command", ["inspect", "validate"])
def test_invalid_ipa_is_json_on_stderr(command, tmp_path):
    invalid = tmp_path / "invalid.ipa"
    invalid.write_bytes(b"not a zip")
    result = runner.invoke(app, [command, str(invalid), "--json"])
    assert result.exit_code == 1
    assert not result.stdout
    assert json.loads(result.stderr)["error"]["code"] == "invalid_ipa"


def test_missing_bundle_metadata_is_clean_json(tmp_path):
    broken = tmp_path / "broken.ipa"
    with ZipFile(IPA) as original, ZipFile(broken, "w") as target:
        for item in original.infolist():
            if item.filename != "Payload/TestApp.app/Info.plist":
                target.writestr(item, original.read(item))
    result = runner.invoke(app, ["inspect", str(broken), "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "invalid_ipa"


def test_lint_json_success_and_failure(tmp_path):
    result = runner.invoke(app, ["lint", str(PATCHES), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"]
    result = runner.invoke(app, ["lint", str(tmp_path / "missing.yaml"), "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "invalid_definition"


@pytest.mark.parametrize("mode", ["--dry-run", "--no-sign"])
def test_patch_json_preserves_manifest_and_verification(mode, tmp_path):
    output = tmp_path / "output.ipa"
    manifest = tmp_path / "manifest.json"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(IPA),
            "--patches",
            str(PATCHES),
            "--output",
            str(output),
            mode,
            "--json",
            "--verbose",
            "--manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["ok"]
    assert data["manifest"] == json.loads(manifest.read_text())
    assert data["dry_run"] == (mode == "--dry-run")
    assert output.exists() == (mode != "--dry-run")
    if output.exists():
        verified = runner.invoke(
            app, ["verify-output", "--base", str(IPA), "--output", str(output), "--manifest", str(manifest), "--json"]
        )
        assert verified.exit_code == 0, verified.output
        assert json.loads(verified.stdout)["ok"]
        manifest.write_text("{}")
        verified = runner.invoke(
            app, ["verify-output", "--base", str(IPA), "--output", str(output), "--manifest", str(manifest), "--json"]
        )
        assert verified.exit_code == 1
        assert json.loads(verified.stderr)["error"]["code"] == "verification_failed"


def test_patch_json_missing_identity_is_structured(tmp_path):
    result = runner.invoke(
        app, ["patch", "--ipa", str(IPA), "--patches", str(PATCHES), "--output", str(tmp_path / "out.ipa"), "--json"]
    )
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "invalid_arguments"


def test_cache_json_and_clear(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path))
    result = runner.invoke(app, ["cache", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["entries"] == 0
    assert not (tmp_path / "objc").exists()
    result = runner.invoke(app, ["cache", "--clear", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["removed"] == 0


def test_export_json(tmp_path):
    output = tmp_path / "source.json"
    result = runner.invoke(
        app,
        [
            "export-source",
            "--ipa",
            str(IPA),
            "--download-url",
            "https://example.com/app.ipa",
            "--output",
            str(output),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["entry"] == json.loads(output.read_text())["apps"][0]


@pytest.mark.parametrize("destination", ["patched.ipa", "results/patched.ipa"])
def test_unsigned_patch_relative_output_stays_in_callers_directory(monkeypatch, tmp_path, destination):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(IPA),
            "--patches",
            str(PATCHES),
            "--output",
            destination,
            "--no-sign",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / destination).is_file()
    assert json.loads(result.stdout)["ok"]


def test_native_archive_failure_keeps_json_stdout_clean(monkeypatch, tmp_path):
    import subprocess

    real_run = subprocess.run

    def failed_zip(args, **kwargs):
        if args[0] == "zip":
            assert kwargs["capture_output"]
            raise subprocess.CalledProcessError(15, args, output="native stdout diagnostic", stderr="")
        return real_run(args, **kwargs)

    monkeypatch.setattr("ipa_forge.bundle.ipa.subprocess.run", failed_zip)
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(IPA),
            "--patches",
            str(PATCHES),
            "--output",
            str(tmp_path / "out.ipa"),
            "--no-sign",
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "native stdout diagnostic" in json.loads(result.stderr)["error"]["message"]
