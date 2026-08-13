from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.validators.bundle_validator import validate_bundle

app = typer.Typer(help="Generic, data-driven iOS IPA patcher with AltStore Classic re-signing support.")


@app.command()
def inspect(ipa: Path = typer.Argument(..., exists=True, help="Path to the .ipa to inspect")) -> None:
    """Print bundle id, version, and the bottom-up executable inventory for an IPA."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_inspect_") as tmp:
        app_path = extract_ipa(ipa, Path(tmp))
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
        app_path = extract_ipa(ipa, Path(tmp))
        bundle = load_bundle(app_path)
        validate_bundle(bundle)
    typer.echo("OK")


@app.command()
def patch(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition YAML/JSON file"),
    identity: str = typer.Option(..., "--identity", help="Codesigning identity: SHA-1 hash or unique name substring"),
    profile: Path = typer.Option(..., "--profile", exists=True, help="Provisioning profile (.mobileprovision)"),
    output: Path = typer.Option(..., "--output", help="Output .ipa path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate patches without mutating or signing anything"),
    verbose: bool = typer.Option(False, "--verbose", help="Print the full manifest on success"),
) -> None:
    """Extract, patch, re-sign, and repackage an IPA for AltStore Classic sideloading."""
    try:
        result = run_pipeline(ipa, patches, identity, profile, output, dry_run=dry_run)
    except PipelineError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo("Dry run OK -- no files were modified.")
    else:
        typer.echo(f"Wrote {result.output_path}")

    if verbose:
        typer.echo(result.manifest.to_json())


if __name__ == "__main__":
    app()
