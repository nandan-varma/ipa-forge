# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI tests: the novice flow — /detect analyzes an IPA and returns the
matching patch set (with a non-blocking version-mismatch warning), and
/patch produces an unsigned IPA by patch-set name."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ipa_forge.gui.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_patches_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the GUI at a temporary patch-set tree with a synthetic patch set."""

    # build a canonical patches/<name>/<name>.yaml for the synthetic fixture
    ps_dir = tmp_path / "patches"
    (ps_dir / "synthetic").mkdir(parents=True)
    definition = (
        "target:\n"
        "  bundle_id: com.example.testapp\n"
        "  version: { exact: 1.0.0 }\n"
        "patches:\n"
        "  - id: rename\n"
        "    type: plist_edit\n"
        "    action: set\n"
        "    key: CFBundleDisplayName\n"
        "    value: Patched\n"
    )
    (ps_dir / "synthetic" / "synthetic.yaml").write_text(definition)
    monkeypatch.setenv("IPA_FORGE_PATCHES_DIR", str(ps_dir))
    yield


def _upload_ipa(tmp_path: Path, fake_ipa: Path) -> dict:
    return {"ipa": ("app.ipa", fake_ipa.read_bytes(), "application/octet-stream")}


def test_index_serves_the_novice_form():
    res = client.get("/")
    assert res.status_code == 200
    assert "Patch an IPA" in res.text
    assert "/detect" in res.text


def test_detect_returns_bundle_and_patch_set(tmp_path: Path, fake_ipa: Path):
    res = client.post("/detect", files=_upload_ipa(tmp_path, fake_ipa))
    assert res.status_code == 200
    data = res.json()
    assert data["bundle_id"] == "com.example.testapp"
    assert data["version"] == "1.0.0"
    assert data["patch_sets"] == [{"name": "synthetic", "target_version": "1.0.0", "matches": True}]
    assert data["mismatch"] is False


def test_detect_reports_version_mismatch(tmp_path: Path, fake_ipa: Path):
    """A patch set targeting a different version -> warning, but the set is
    still returned so patching stays possible."""
    ps_dir = Path(os.environ["IPA_FORGE_PATCHES_DIR"])
    (ps_dir / "synthetic" / "synthetic.yaml").write_text(
        "target:\n  bundle_id: com.example.testapp\n  version: { exact: 9.9.9 }\n"
        "patches:\n  - id: rename\n    type: plist_edit\n    action: set\n"
        "    key: CFBundleDisplayName\n    value: Patched\n"
    )
    res = client.post("/detect", files=_upload_ipa(tmp_path, fake_ipa))
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "1.0.0"
    assert data["mismatch"] is True
    assert data["patch_sets"][0]["matches"] is False


def test_patch_unknown_patch_set_returns_400(tmp_path: Path, fake_ipa: Path):
    res = client.post(
        "/patch",
        files=_upload_ipa(tmp_path, fake_ipa),
        data={"patch_set": "nope"},
    )
    assert res.status_code == 400
    assert "unknown patch set" in res.json()["error"]


def test_patch_no_sign_produces_download(tmp_path: Path, fake_ipa: Path):
    res = client.post(
        "/patch",
        files=_upload_ipa(tmp_path, fake_ipa),
        data={"patch_set": "synthetic", "no_sign": "true"},
    )
    assert res.status_code == 200
    data = res.json()
    manifest = data["manifest"]
    assert manifest["bundle_id"] == "com.example.testapp"
    assert data["download_url"].startswith("/download/")
    dl = client.get(data["download_url"])
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/octet-stream"
