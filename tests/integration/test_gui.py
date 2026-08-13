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

    # A self-contained binary_replace-only definition, uploaded as a plain
    # .yaml with no assets -- the simplest supported upload shape.
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


def test_patch_endpoint_accepts_a_zip_with_resource_assets(tmp_path: Path, synthetic_profile: Path):
    """The gap this closes: resource_replace/resource_add need an external
    source file, which a single-file upload has no way to carry. Zipping the
    definition together with its assets/ directory is how the GUI now
    supports them."""
    import zipfile

    client = TestClient(app)

    zip_path = tmp_path / "patches_bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(FIXTURES / "patches" / "example.yaml", "example.yaml")
        zf.write(FIXTURES / "patches" / "assets" / "patched_asset.txt", "assets/patched_asset.txt")

    with (
        open(FIXTURES / "synthetic_app.ipa", "rb") as ipa_f,
        open(zip_path, "rb") as zip_f,
        open(synthetic_profile, "rb") as profile_f,
    ):
        response = client.post(
            "/patch",
            files={
                "ipa": ("synthetic_app.ipa", ipa_f, "application/octet-stream"),
                "patches": ("patches_bundle.zip", zip_f, "application/zip"),
                "profile": (synthetic_profile.name, profile_f, "application/octet-stream"),
            },
            data={"identity": "Apple Development"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    patch_status = {p["id"]: p["status"] for p in body["manifest"]["patches_applied"]}
    assert patch_status == {"zero-marker-bytes": "applied", "swap-asset": "applied"}

    download = client.get(body["download_url"])
    assert download.status_code == 200

    import io
    import zipfile as zf_module

    with zf_module.ZipFile(io.BytesIO(download.content)) as out_zip:
        content = out_zip.read("Payload/TestApp.app/asset.txt")
    assert content == b"patched synthetic resource\n"


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
