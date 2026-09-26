# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from ipa_forge.cli.main import app

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def patched(tmp_path):
    output = tmp_path / "out.ipa"
    manifest = tmp_path / "manifest.json"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(FIXTURES / "synthetic_app.ipa"),
            "--patches",
            str(FIXTURES / "patches/example.yaml"),
            "--output",
            str(output),
            "--no-sign",
            "--manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    return output, manifest


def verify(output, manifest):
    return runner.invoke(
        app,
        [
            "verify-output",
            "--base",
            str(FIXTURES / "synthetic_app.ipa"),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
    )


def rewrite(output, transform):
    with ZipFile(output) as archive:
        entries = {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()}
    transform(entries)
    with ZipFile(output, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def test_verify_output_exact_patch(tmp_path):
    output, manifest = patched(tmp_path)
    result = verify(output, manifest)
    assert result.exit_code == 0, result.output
    assert "OK" in result.stdout
    data = json.loads(manifest.read_text())
    assert "TestApp" in data["files_modified"]
    assert next(p for p in data["patches_applied"] if "offsets" in p)["file"] == "TestApp"


@pytest.mark.parametrize("target", ["binary", "resource", "added", "removed"])
def test_verify_output_rejects_unreviewed_change(tmp_path, target):
    output, manifest = patched(tmp_path)
    data = json.loads(manifest.read_text())
    # Exercise byte/inventory validation independently of the output hash.
    data["output_sha256"] = None
    manifest.write_text(json.dumps(data))

    def mutate(entries):
        prefix = next(n.rsplit("/", 1)[0] for n in entries if len(Path(n).parts) == 3 and n.endswith("/Info.plist"))
        if target == "added":
            entries[prefix + "/unexpected"] = b"extra"
        elif target == "removed":
            del entries[prefix + "/Info.plist"]
        else:
            name = prefix + ("/TestApp" if target == "binary" else "/Info.plist")
            value = bytearray(entries[name])
            value[0] ^= 1
            entries[name] = bytes(value)

    rewrite(output, mutate)
    result = verify(output, manifest)
    assert result.exit_code == 1, result.output
    assert "error:" in result.stderr


def test_verify_output_wrong_base_hash(tmp_path):
    output, manifest = patched(tmp_path)
    data = json.loads(manifest.read_text())
    data["input_sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    result = verify(output, manifest)
    assert result.exit_code == 1
    assert "base IPA SHA-256" in result.stderr


def test_verify_output_without_manifest_identical(tmp_path):
    base = FIXTURES / "synthetic_app.ipa"
    result = runner.invoke(app, ["verify-output", "--base", str(base), "--output", str(base)])
    assert result.exit_code == 0, result.output


def test_verify_output_invalid_manifest_shape_is_clean(tmp_path):
    base = FIXTURES / "synthetic_app.ipa"
    manifest = tmp_path / "invalid.json"
    manifest.write_text("[]")
    result = verify(base, manifest)
    assert result.exit_code == 1
    assert "manifest" in result.stderr
    assert "Traceback" not in result.output


def test_verify_output_bad_recorded_offset(tmp_path):
    output, manifest = patched(tmp_path)
    data = json.loads(manifest.read_text())
    next(p for p in data["patches_applied"] if "offsets" in p)["offsets"] = ["0xffffffff"]
    manifest.write_text(json.dumps(data))
    result = verify(output, manifest)
    assert result.exit_code == 1
    assert "invalid binary edit range" in result.stderr


def test_verify_output_directory_add_remove(tmp_path):
    import yaml

    patches = tmp_path / "patches.yaml"
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "new.txt").write_text("new resource")
    patches.write_text(
        yaml.safe_dump(
            {
                "target": {"bundle_id": "com.example.synthetic", "version": {"exact": "1.0.0"}},
                "patches": [
                    {"id": "add", "type": "resource_add", "path": "New", "source": "staged"},
                    {"id": "remove", "type": "resource_remove", "path": "Frameworks"},
                ],
            }
        )
    )
    output = tmp_path / "output.ipa"
    manifest = tmp_path / "manifest.json"
    result = runner.invoke(
        app,
        [
            "patch",
            "--ipa",
            str(FIXTURES / "synthetic_app.ipa"),
            "--patches",
            str(patches),
            "--output",
            str(output),
            "--no-sign",
            "--manifest",
            str(manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    result = verify(output, manifest)
    assert result.exit_code == 0, result.output
