# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline first-run smoke test using only the project's synthetic fixture."""

from __future__ import annotations

import json
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

import typer

from ipa_forge.patch.lint import lint_definition
from ipa_forge.patch.loader import PatchLoadError
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.verify_output import verify_output


def demo(
    json_output: bool = typer.Option(False, "--json", help="Emit a structured demo result"),
) -> None:
    """Lint, dry-run, apply unsigned patches, and verify a bundled synthetic IPA.

    Runs offline in a temporary directory. No input IPA, signing credentials,
    or device is needed. All demo files are removed on completion.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="ipa_forge_demo_") as tmp:
            root = Path(tmp)
            data = files("ipa_forge").joinpath("demo_data")
            for name in ("synthetic_app.ipa", "example.yaml", "assets/patched_asset.txt"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data.joinpath(name).read_bytes())
            definition = root / "example.yaml"
            ipa = root / "synthetic_app.ipa"
            output = root / "patched.ipa"
            manifest = root / "manifest.json"
            lint_definition(definition)
            run_pipeline(ipa, definition, "", [], output, dry_run=True)
            result = run_pipeline(ipa, definition, "", [], output, no_sign=True)
            manifest.write_text(result.manifest.to_json())
            verify_output(ipa, output, manifest)
            count = len(result.manifest.patches_applied)
    except (OSError, ValueError, PatchLoadError, PipelineError, subprocess.CalledProcessError) as e:
        message = " ".join(str(e).splitlines())
        if isinstance(e, FileNotFoundError) and e.filename in {"zip", "unzip"}:
            message += "; run forge doctor to check archive tools"
        typer.echo(
            json.dumps({"error": {"code": "demo_failed", "message": message}}) if json_output else f"error: {message}",
            err=True,
        )
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            {
                "schema_version": 1,
                "ok": True,
                "operations": count,
                "checks": ["lint", "dry_run", "unsigned_patch", "verify_output"],
            },
            indent=2,
        )
        if json_output
        else f"Demo OK -- {count} operations linted, dry-run, applied unsigned, and verified. Temporary files removed."
    )
