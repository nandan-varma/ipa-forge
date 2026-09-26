# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tempfile
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path

import typer

from ipa_forge.altstore.source import build_app_entry, write_source_json
from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.cli import analysis as _analysis  # `forge analysis` subcommands
from ipa_forge.cli import hooks as _hooks  # `forge hooks` subcommands
from ipa_forge.cli.common import validated_extract
from ipa_forge.hooks.verify import BLOCKING_STATUSES, OK_STATUSES
from ipa_forge.machO import cache as objc_cache
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.validators.bundle_validator import validate_bundle

app = typer.Typer()


def _package_version() -> str:
    try:
        return _installed_version("ipa-forge")
    except PackageNotFoundError:  # not installed (e.g. run from a source checkout)
        return "0.1.0"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ipa-forge {_package_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, help="Show version and exit."),
) -> None:
    """Generic, data-driven iOS IPA patcher with AltStore Classic re-signing support."""


def _validated_extract(ipa: Path, dest: Path) -> Path:
    """Alias of cli.common.validated_extract with a clean CLI error."""
    try:
        return validated_extract(ipa, dest)
    except ValueError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


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
    no_sign: bool = typer.Option(
        False,
        "--no-sign",
        help="Apply patches and repackage without codesigning (for AltStore, which signs at install)",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Print the full manifest on success"),
) -> None:
    """Extract, patch, re-sign, and repackage an IPA for AltStore Classic sideloading."""
    if not dry_run and not no_sign:
        if not identity:
            typer.secho("error: --identity is required unless --dry-run is set", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        if not profile:
            typer.secho(
                "error: at least one --profile is required unless --dry-run is set", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(code=1) from None
    try:
        result = run_pipeline(ipa, patches, identity or "", profile or [], output, dry_run=dry_run, no_sign=no_sign)
    except PipelineError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    if dry_run:
        count = len(result.manifest.patches_applied)
        typer.echo(f"Dry run OK -- {count} operation(s) would apply.")
        hook_report = result.manifest.hook_report
        if hook_report:
            attach = sum(1 for h in hook_report if h["status"] in OK_STATUSES)
            broken = [h for h in hook_report if h["status"] in BLOCKING_STATUSES]
            unknown = [h for h in hook_report if h["status"] not in OK_STATUSES and h not in broken]
            # Three-way, not "N issue(s)": lumping parser gaps in with real drift
            # meant a healthy patch set permanently reported issues it should not
            # have (YouTube 21.38.2 showed 8, all benign), so the number stopped
            # carrying information.
            summary = f"Hooks: {attach}/{len(hook_report)} attach"
            if unknown:
                summary += f", {len(unknown)} unverified (parser gap -- check on device)"
            summary += f", {len(broken)} failing"
            typer.echo(summary)
            for h in broken + unknown:
                typer.secho(
                    f"  {'!' if h in broken else '?'} {h['class']} "
                    f"{'+' if h['kind'] == 'class' else '-'}[{h['selector']}]: "
                    f"{h['status']} -- {h['detail']}",
                    fg=typer.colors.RED if h in broken else typer.colors.YELLOW,
                )
    else:
        manifest = result.manifest
        applied = sum(1 for p in manifest.patches_applied if p["status"] == "applied")
        typer.echo(
            f"Applied {applied} operation(s) to {manifest.bundle_id} v{manifest.version} -> {result.output_path}"
        )

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


@app.command("cache")
def cache_command(
    clear: bool = typer.Option(False, "--clear", help="Delete every cached Mach-O analysis"),
) -> None:
    """Show or clear the Mach-O analysis cache.

    Analyses are cached by binary content hash, so repeated `hooks`/`analysis`
    queries against the same IPA parse it once. Entries are large (tens of MB
    for a big app) and capped; set `FORGE_NO_CACHE=1` to bypass the cache
    entirely for one command.
    """
    directory = objc_cache.cache_dir() / "objc"
    if clear:
        typer.echo(f"Removed {objc_cache.clear()} cached analysis/analyses from {directory}")
        return
    entries = sorted(directory.glob("*.pickle")) if directory.is_dir() else []
    total = sum(e.stat().st_size for e in entries)
    typer.echo(f"Cache:   {directory}")
    typer.echo(f"Entries: {len(entries)} ({total / 1e6:.1f} MB)")
    if objc_cache.disabled():
        typer.secho("FORGE_NO_CACHE is set -- the cache is bypassed", fg=typer.colors.YELLOW)


@app.command()
def gui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Launch the local web GUI (wraps the same pipeline as `forge patch`)."""
    import uvicorn

    uvicorn.run("ipa_forge.gui.app:app", host=host, port=port)


app.add_typer(_hooks.app, name="hooks")
app.add_typer(_analysis.app, name="analysis")


if __name__ == "__main__":
    app()
