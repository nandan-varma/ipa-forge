# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from ipa_forge.altstore.source import build_app_entry, write_source_json

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_build_app_entry_reflects_bundle_metadata():
    entry = build_app_entry(FIXTURES / "synthetic_app.ipa", download_url="https://example.com/app.ipa")

    assert entry["bundleIdentifier"] == "com.example.synthetic"
    assert entry["version"] == "1.0.0"
    assert entry["buildVersion"] == "1"
    assert entry["downloadURL"] == "https://example.com/app.ipa"
    assert entry["size"] == (FIXTURES / "synthetic_app.ipa").stat().st_size
    assert len(entry["sha256"]) == 64


def test_write_source_json_wraps_entry_in_apps_list(tmp_path: Path):
    entry = build_app_entry(FIXTURES / "synthetic_app.ipa", download_url="https://example.com/app.ipa")
    out = tmp_path / "source.json"

    write_source_json(entry, out)

    import json

    data = json.loads(out.read_text())
    assert data["apps"] == [entry]
    assert "name" in data
