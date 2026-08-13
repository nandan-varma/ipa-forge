# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ipa_forge.gui.uploads import UploadError, resolve_patch_definition, safe_extract_zip


def test_single_yaml_upload_is_returned_as_is(tmp_path: Path):
    upload = tmp_path / "patches.yaml"
    upload.write_text("target: {}\npatches: []\n")

    resolved = resolve_patch_definition(upload, tmp_path / "dest")
    assert resolved == upload


def test_zip_upload_extracts_and_finds_the_definition(tmp_path: Path):
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("patches.yaml", "target: {}\npatches: []\n")
        zf.writestr("assets/logo.png", b"fake png bytes")

    dest = tmp_path / "dest"
    dest.mkdir()
    resolved = resolve_patch_definition(zip_path, dest)

    assert resolved.name == "patches.yaml"
    assert resolved.read_text() == "target: {}\npatches: []\n"
    assert (resolved.parent / "assets" / "logo.png").is_file()


def test_zip_with_no_definition_file_raises_upload_error(tmp_path: Path):
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("assets/logo.png", b"fake png bytes")

    dest = tmp_path / "dest2"
    dest.mkdir()
    with pytest.raises(UploadError, match="did not contain"):
        resolve_patch_definition(zip_path, dest)


def test_zip_with_multiple_definition_files_raises_upload_error(tmp_path: Path):
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.yaml", "target: {}\npatches: []\n")
        zf.writestr("b.yaml", "target: {}\npatches: []\n")

    dest = tmp_path / "dest3"
    dest.mkdir()
    with pytest.raises(UploadError, match="multiple top-level"):
        resolve_patch_definition(zip_path, dest)


def test_unsupported_extension_raises_upload_error(tmp_path: Path):
    upload = tmp_path / "patches.txt"
    upload.write_text("not a real patch file")

    with pytest.raises(UploadError, match="must be"):
        resolve_patch_definition(upload, tmp_path / "dest4")


def test_safe_extract_rejects_zip_slip(tmp_path: Path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../escaped.txt", "pwned")

    dest = tmp_path / "dest5"
    dest.mkdir()
    with pytest.raises(UploadError, match="escapes"):
        safe_extract_zip(zip_path, dest)

    assert not (tmp_path / "escaped.txt").exists()
