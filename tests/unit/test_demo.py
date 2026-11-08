# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.cli.main import app


def test_demo_exercises_real_pipeline_offline_and_cleans_up(monkeypatch):
    import ipa_forge.cli.demo as module
    from ipa_forge.pipeline import run_pipeline

    paths = []

    def track(*args, **kwargs):
        paths.append(args[4].parent)
        result = run_pipeline(*args, **kwargs)
        if kwargs.get("dry_run"):
            assert not args[4].exists()
        return result

    monkeypatch.setattr(module, "run_pipeline", track)
    result = CliRunner().invoke(app, ["demo", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["ok"]
    assert data["operations"] == 2
    assert data["checks"] == ["lint", "dry_run", "unsigned_patch", "verify_output"]
    assert len(paths) == 2
    assert all(not path.exists() for path in paths)


def test_demo_missing_tool_has_actionable_structured_error(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError(2, "No such file", "unzip")

    monkeypatch.setattr("ipa_forge.cli.demo.run_pipeline", missing)
    result = CliRunner().invoke(app, ["demo", "--json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "demo_failed"
    assert "forge doctor" in error["message"]


def test_packaged_demo_matches_canonical_fixtures():
    root = Path(__file__).resolve().parents[2]
    pairs = {
        "synthetic_app.ipa": "synthetic_app.ipa",
        "example.yaml": "patches/example.yaml",
        "assets/patched_asset.txt": "patches/assets/patched_asset.txt",
    }
    for packaged, fixture in pairs.items():
        assert (root / "ipa_forge/demo_data" / packaged).read_bytes() == (root / "fixtures" / fixture).read_bytes()
