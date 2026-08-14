# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI integration smoke test via FastAPI's TestClient — exercises the
novice flow (/detect -> /patch with a discovered patch set) through the real
pipeline against the synthetic fixture. Browser-level rendering is not
automated; see docs/altstore_device_testing.md for what is manual."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ipa_forge.gui.app import app

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture()
def _patches_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ps_dir = tmp_path / "patches"
    (ps_dir / "synthetic").mkdir(parents=True)
    (ps_dir / "synthetic" / "synthetic.yaml").write_text(
        "target:\n"
        "  bundle_id: com.example.synthetic\n"
        "  version: { exact: 1.0.0 }\n"
        "patches:\n"
        "  - id: rename\n"
        "    type: plist_edit\n"
        "    action: set\n"
        "    key: CFBundleDisplayName\n"
        "    value: Patched\n"
    )
    monkeypatch.setenv("IPA_FORGE_PATCHES_DIR", str(ps_dir))
    return ps_dir


def test_novice_flow_detect_and_unsigned_patch(_patches_dir: Path):
    """Select an IPA -> detect matches the patch set -> patch produces an
    unsigned download (no identity/profile needed)."""
    client = TestClient(app)
    ipa_bytes = (FIXTURES / "synthetic_app.ipa").read_bytes()

    res = client.post("/detect", files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")})
    assert res.status_code == 200
    data = res.json()
    assert data["bundle_id"] == "com.example.synthetic"
    assert data["version"] == "1.0.0"
    assert data["patch_sets"][0]["name"] == "synthetic"
    assert data["mismatch"] is False

    res = client.post(
        "/patch",
        files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")},
        data={"patch_set": "synthetic", "no_sign": "true"},
    )
    assert res.status_code == 200
    manifest = res.json()["manifest"]
    assert manifest["bundle_id"] == "com.example.synthetic"
    assert any(p["id"] == "rename" and p["status"] == "applied" for p in manifest["patches_applied"])
    dl = client.get(res.json()["download_url"])
    assert dl.status_code == 200
    assert dl.content[:4] == b"PK\x03\x04"  # zip/IPA magic


def test_detect_warns_on_version_mismatch(_patches_dir: Path):
    (Path(_patches_dir) / "synthetic" / "synthetic.yaml").write_text(
        "target:\n  bundle_id: com.example.synthetic\n  version: { exact: 9.9.9 }\n"
        "patches:\n  - id: rename\n    type: plist_edit\n    action: set\n"
        "    key: CFBundleDisplayName\n    value: Patched\n"
    )
    client = TestClient(app)
    ipa_bytes = (FIXTURES / "synthetic_app.ipa").read_bytes()
    res = client.post("/detect", files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")})
    assert res.status_code == 200
    data = res.json()
    assert data["mismatch"] is True
    # patching is still allowed (non-blocking warning)
    res = client.post(
        "/patch",
        files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")},
        data={"patch_set": "synthetic", "no_sign": "true"},
    )
    assert res.status_code == 200
