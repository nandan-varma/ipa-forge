# SPDX-License-Identifier: GPL-3.0-or-later
"""F4 (GUI side): the /patch endpoint accepts dry-run requests without any
signing inputs, and rejects real runs that lack them. Dry-run never reaches
the signing stages, so these tests need no Keychain identity (not macOS).
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from ipa_forge.gui.app import app

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

# A self-contained definition with no external assets (binary_replace only),
# matching the synthetic fixture -- same shape as the macos-marked GUI tests.
_BINARY_ONLY = (
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


def _post(client: TestClient, patches: Path, data: dict) -> httpx.Response:
    ipa_bytes = (_FIXTURES / "synthetic_app.ipa").read_bytes()
    return client.post(
        "/patch",
        files={
            "ipa": ("synthetic_app.ipa", io.BytesIO(ipa_bytes), "application/octet-stream"),
            "patches": ("binary_only.yaml", io.BytesIO(patches.read_bytes()), "application/x-yaml"),
        },
        data=data,
    )


def test_index_serves_the_fetch_based_form():
    """UI: the form must be enhanced by the inline fetch flow, not the raw
    JSON navigation it replaced."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'id="patch-form"' in html
    assert 'id="result"' in html
    assert "fetch(" in html


def test_patch_dry_run_without_profile_or_identity(tmp_path: Path):
    client = TestClient(app)
    patches = tmp_path / "binary_only.yaml"
    patches.write_text(_BINARY_ONLY)

    response = _post(client, patches, data={"dry_run": "1"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["bundle_id"] == "com.example.synthetic"
    assert "download_url" not in body  # dry run produces no artifact


def test_patch_real_run_without_profile_returns_400(tmp_path: Path):
    client = TestClient(app)
    patches = tmp_path / "binary_only.yaml"
    patches.write_text(_BINARY_ONLY)

    response = _post(client, patches, data={"identity": "Apple Development"})  # profile missing

    assert response.status_code == 400
    assert "provisioning profile" in response.json()["error"]


def test_patch_real_run_without_identity_returns_400(tmp_path: Path):
    client = TestClient(app)
    patches = tmp_path / "binary_only.yaml"
    patches.write_text(_BINARY_ONLY)

    response = _post(client, patches, data={})  # neither identity nor dry_run

    assert response.status_code == 400
    assert response.json()["error"].startswith("identity")
