"""GUI smoke test via FastAPI's TestClient -- exercises the real pipeline
(real codesign signing) through the HTTP layer. Browser-level rendering is
not automated in this sandbox; see docs/altstore_device_testing.md for what
is manual by necessity."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ipa_forge.gui.app import app

pytestmark = pytest.mark.macos

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_index_serves_the_upload_form():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "form" in response.text.lower()


def test_patch_endpoint_runs_the_real_pipeline(tmp_path: Path, synthetic_profile: Path):
    client = TestClient(app)

    # The GUI accepts a single patch-definition file upload with no sibling
    # assets directory (unlike the CLI, which reads --patches off a real
    # filesystem path with its assets/ alongside it) -- a self-contained
    # binary_replace-only definition exercises the real pipeline without
    # requiring multi-file asset upload, which is out of scope for v1.
    binary_only_patches = tmp_path / "binary_only.yaml"
    binary_only_patches.write_text(
        "target:\n"
        "  bundle_id: com.example.synthetic\n"
        "  version: {exact: '1.0.0'}\n"
        "patches:\n"
        "  - id: zero-marker-bytes\n"
        "    type: binary_replace\n"
        "    executable: TestApp\n"
        "    arch: arm64\n"
        "    pattern: 'ca fe f0 0d de ad be ef 13 37 c0 de ab cd ef 01'\n"
        "    replacement: '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'\n"
        "    expected_matches: 1\n"
    )

    with (
        open(FIXTURES / "synthetic_app.ipa", "rb") as ipa_f,
        open(binary_only_patches, "rb") as patches_f,
        open(synthetic_profile, "rb") as profile_f,
    ):
        response = client.post(
            "/patch",
            files={
                "ipa": ("synthetic_app.ipa", ipa_f, "application/octet-stream"),
                "patches": ("binary_only.yaml", patches_f, "application/x-yaml"),
                "profile": (synthetic_profile.name, profile_f, "application/octet-stream"),
            },
            data={"identity": "Apple Development", "dry_run": ""},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["bundle_id"] == "com.example.synthetic"
    assert "download_url" in body

    download = client.get(body["download_url"])
    assert download.status_code == 200
    assert download.content[:2] == b"PK"  # zip magic


def test_patch_endpoint_surfaces_pipeline_errors_as_400(synthetic_profile: Path, tmp_path: Path):
    client = TestClient(app)

    bad_patches = tmp_path / "bad.yaml"
    bad_patches.write_text(
        "target:\n"
        "  bundle_id: com.example.synthetic\n"
        "  version: {exact: '1.0.0'}\n"
        "patches:\n"
        "  - id: bad\n"
        "    type: resource_remove\n"
        "    path: does_not_exist.txt\n"
    )

    with (
        open(FIXTURES / "synthetic_app.ipa", "rb") as ipa_f,
        open(bad_patches, "rb") as patches_f,
        open(synthetic_profile, "rb") as profile_f,
    ):
        response = client.post(
            "/patch",
            files={
                "ipa": ("synthetic_app.ipa", ipa_f, "application/octet-stream"),
                "patches": ("bad.yaml", patches_f, "application/x-yaml"),
                "profile": (synthetic_profile.name, profile_f, "application/octet-stream"),
            },
            data={"identity": "Apple Development"},
        )

    assert response.status_code == 400
    assert "error" in response.json()
