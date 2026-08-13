# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from ipa_forge.altstore.source import build_app_entry, write_source_json
from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.validators.bundle_validator import validate_bundle
from ipa_forge.validators.ipa_validator import IpaValidationError, validate_ipa_structure

app = typer.Typer(help="Generic, data-driven iOS IPA patcher with AltStore Classic re-signing support.")


def _validated_extract(ipa: Path, dest: Path) -> Path:
    """Structure-validate (pipeline stage 1), then extract -- surfacing a clean
    CLI error instead of a traceback for malformed input."""
    try:
        validate_ipa_structure(ipa)
    except IpaValidationError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    return extract_ipa(ipa, dest)


@app.command()
def inspect(ipa: Path = typer.Argument(..., exists=True, help="Path to the .ipa to inspect")) -> None:
    """Print bundle id, version, and the bottom-up executable inventory for an IPA."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_inspect_") as tmp:
        app_path = _validated_extract(ipa, Path(tmp))
        bundle = load_bundle(app_path)
        typer.echo(f"Bundle ID:  {bundle.bundle_id}")
        typer.echo(f"Version:    {bundle.version} (build {bundle.build})")
        typer.echo(f"Main exec:  {bundle.main_executable_name}")
        typer.echo("Executables (bottom-up sign order):")
        for target in bundle.executables:
            typer.echo(f"  [{target.kind:10}] {target.bundle_relative}")


@app.command()
def validate(ipa: Path = typer.Argument(..., exists=True, help="Path to the .ipa to validate")) -> None:
    """Validate IPA structure and Info.plist without patching or signing anything."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_validate_") as tmp:
        app_path = _validated_extract(ipa, Path(tmp))
        bundle = load_bundle(app_path)
        validate_bundle(bundle)
    typer.echo("OK")


@app.command()
def patch(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition YAML/JSON file"),
    identity: str | None = typer.Option(
        None,
        "--identity",
        help="Codesigning identity: SHA-1 hash or unique name substring (not needed for --dry-run)",
    ),
    profile: list[Path] | None = typer.Option(
        None,
        "--profile",
        exists=True,
        help="Provisioning profile (.mobileprovision), repeatable; not needed for --dry-run. Repeat to "
        "supply one per app extension/watch app -- each is matched to its own bundle id; a single "
        "profile signs everything, as before.",
    ),
    output: Path = typer.Option(..., "--output", help="Output .ipa path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate patches without mutating or signing anything"),
    verbose: bool = typer.Option(False, "--verbose", help="Print the full manifest on success"),
) -> None:
    """Extract, patch, re-sign, and repackage an IPA for AltStore Classic sideloading."""
    if not dry_run:
        if not identity:
            typer.secho("error: --identity is required unless --dry-run is set", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        if not profile:
            typer.secho(
                "error: at least one --profile is required unless --dry-run is set", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(code=1) from None
    try:
        result = run_pipeline(ipa, patches, identity or "", profile or [], output, dry_run=dry_run)
    except PipelineError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    if dry_run:
        typer.echo("Dry run OK -- no files were modified.")
    else:
        typer.echo(f"Wrote {result.output_path}")

    if verbose:
        typer.echo(result.manifest.to_json())


@app.command("export-source")
def export_source(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Patched, signed .ipa to describe"),
    download_url: str = typer.Option(..., "--download-url", help="URL this IPA will be hosted at"),
    output: Path = typer.Option(..., "--output", help="Output source.json path"),
) -> None:
    """Emit an AltStore Classic source.json entry for an already-patched IPA."""
    entry = build_app_entry(ipa, download_url)
    write_source_json(entry, output)
    typer.echo(f"Wrote {output}")


@app.command()
def gui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Launch the local web GUI (wraps the same pipeline as `forge patch`)."""
    import uvicorn

    uvicorn.run("ipa_forge.gui.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
