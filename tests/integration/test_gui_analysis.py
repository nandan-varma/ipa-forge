# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI reverse-engineering endpoints (/analysis/*): read-only class-dump,
strings, security, and diff views, same engine as `forge analysis ...` but
browsable without the CLI. Browser-level rendering is not automated here;
see docs/altstore_device_testing.md for what remains manual."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ipa_forge.gui.app import app

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_analysis_page_serves_html() -> None:
    client = TestClient(app)
    res = client.get("/analysis")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Reverse Engineering" in res.text


def test_classdump_endpoint_returns_dump() -> None:
    client = TestClient(app)
    ipa_bytes = (FIXTURES / "synthetic_app.ipa").read_bytes()
    res = client.post("/analysis/classdump", files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")})
    assert res.status_code == 200
    assert "text" in res.json()


def test_classdump_endpoint_bad_ipa_returns_400() -> None:
    client = TestClient(app)
    res = client.post("/analysis/classdump", files={"ipa": ("bad.ipa", b"not a zip", "application/octet-stream")})
    assert res.status_code == 400
    assert "error" in res.json()


def test_strings_endpoint_returns_matches() -> None:
    client = TestClient(app)
    ipa_bytes = (FIXTURES / "synthetic_app.ipa").read_bytes()
    res = client.post(
        "/analysis/strings",
        files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")},
        data={"min_len": "4"},
    )
    assert res.status_code == 200
    assert res.json()["text"]


def test_security_endpoint_returns_posture() -> None:
    client = TestClient(app)
    ipa_bytes = (FIXTURES / "synthetic_app.ipa").read_bytes()
    res = client.post("/analysis/security", files={"ipa": ("app.ipa", ipa_bytes, "application/octet-stream")})
    assert res.status_code == 200
    assert "PIE:" in res.json()["text"]


def test_diff_endpoint_identical_reports_no_differences() -> None:
    client = TestClient(app)
    ipa_bytes = (FIXTURES / "synthetic_app.ipa").read_bytes()
    res = client.post(
        "/analysis/diff",
        files={
            "old": ("old.ipa", ipa_bytes, "application/octet-stream"),
            "new": ("new.ipa", ipa_bytes, "application/octet-stream"),
        },
    )
    assert res.status_code == 200
    assert "no differences found" in res.json()["text"]
