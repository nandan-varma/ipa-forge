# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.cli.main import app


def test_schema_export_matches_published_editor_contract():
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.stdout)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    variants = schema["properties"]["patches"]["items"]["discriminator"]["mapping"]
    assert set(variants) == {
        "binary_replace",
        "dylib_inject",
        "plist_edit",
        "resource_add",
        "resource_remove",
        "resource_replace",
    }
    assert schema["$defs"]["HookSpec"]["required"] == ["class", "selector"]
    published = Path(__file__).resolve().parents[2] / "docs/public/schema/patch-definition.json"
    # docs/ is excluded from sdists; a packaged test run can still check the command.
    if published.exists():
        assert json.loads(published.read_text()) == schema
