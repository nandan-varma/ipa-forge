# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ipa_forge.cli.main import app
from ipa_forge.patch.loader import PatchLoadError, load_patch_definition

runner = CliRunner()


def definition(tmp_path: Path, patches=None, hooks=None) -> Path:
    data = {
        "target": {"bundle_id": "com.example.test", "version": {"exact": "1"}},
        "patches": patches if patches is not None else [{"type": "resource_remove", "id": "remove", "path": "x"}],
    }
    if hooks is not None:
        data["hooks"] = hooks
    path = tmp_path / "patch.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def assert_failure(path: Path, message: str):
    result = runner.invoke(app, ["lint", str(path)])
    assert result.exit_code == 1, result.output
    assert message in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert "Traceback" not in result.output


def test_lint_valid_without_ipa(tmp_path):
    result = runner.invoke(app, ["lint", str(definition(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "OK" in result.stdout


@pytest.mark.parametrize("content", ["", "patches: []", "target: [broken"])
def test_lint_invalid_schema_or_yaml(tmp_path, content):
    path = tmp_path / "bad.yaml"
    path.write_text(content)
    assert_failure(path, "patch definition")


def test_duplicate_ids_rejected_by_loader_and_lint(tmp_path):
    op = {"type": "resource_remove", "id": "dup", "path": "x"}
    path = definition(tmp_path, [op, op])
    with pytest.raises(PatchLoadError, match="duplicate patch id 'dup'"):
        load_patch_definition(path)
    assert_failure(path, "duplicate patch id 'dup'")


@pytest.mark.parametrize(
    ("pattern", "replacement", "message"),
    [
        ("gg", "00", "invalid hex"),
        ("00", "gg", "invalid hex"),
        ("00 01", "00", "replacement length"),
        ("00", "??", "wildcards"),
        ("", "00", "empty pattern"),
    ],
)
def test_lint_binary_patterns(tmp_path, pattern, replacement, message):
    path = definition(
        tmp_path,
        [
            {
                "type": "binary_replace",
                "id": "bytes",
                "executable": "App",
                "pattern": pattern,
                "replacement": replacement,
            }
        ],
    )
    assert_failure(path, message)


@pytest.mark.parametrize("kind", ["resource_add", "resource_replace"])
def test_lint_missing_source(tmp_path, kind):
    path = definition(tmp_path, [{"type": kind, "id": "copy", "path": "x", "source": "missing"}])
    assert_failure(path, "source")


def test_lint_sources_relative_to_definition(tmp_path, monkeypatch):
    (tmp_path / "asset").write_text("hello")
    path = definition(tmp_path, [{"type": "resource_add", "id": "copy", "path": "x", "source": "asset"}])
    monkeypatch.chdir(tmp_path.parent)
    result = runner.invoke(app, ["lint", str(path)])
    assert result.exit_code == 0, result.output


def test_lint_duplicate_hooks(tmp_path):
    hook = {"class": "Foo", "selector": "bar:"}
    path = definition(tmp_path, hooks=[hook, {**hook, "kind": "class"}])
    assert_failure(path, "duplicate hook Foo bar:")


def test_lint_distinct_hooks(tmp_path):
    path = definition(tmp_path, hooks=[{"class": "Foo", "selector": "bar:"}, {"class": "Foo", "selector": "baz:"}])
    result = runner.invoke(app, ["lint", str(path)])
    assert result.exit_code == 0, result.output
