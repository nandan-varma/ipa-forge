# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge analysis` subcommands: general-purpose reverse engineering of an
IPA, built on the same Mach-O/ObjC analysis engine `forge hooks` uses for
hook verification (see `ipa_forge.machO.objc`).

Every command accepts ``--app-dir`` in place of the IPA, same as
`forge hooks` — point it at an already-extracted ``Payload/<App>.app``
directory to skip re-extraction when iterating.
"""

from __future__ import annotations

import re as _re
import tempfile
from pathlib import Path

import typer

from ipa_forge.analysis.classdump import render_analysis
from ipa_forge.analysis.security import analyze_security, render_security_posture
from ipa_forge.analysis.strings import strings_in_bundle
from ipa_forge.analysis.symbols import analyze_symbols
from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.bundle.models import AppBundle
from ipa_forge.cli.common import extract_or_use
from ipa_forge.machO.arch import AmbiguousArchError, ArchNotFoundError, NotMachOError
from ipa_forge.machO.detect import bundle_executable_paths
from ipa_forge.machO.objc import analyze_bundle

app = typer.Typer(help="General-purpose IPA reverse engineering: class-dump, strings, symbols, security, diff.")


def _select_binary(bundle: AppBundle, binary: str | None) -> Path:
    """Resolve --binary to one executable path: the main executable when
    omitted, otherwise the unique path whose bundle-relative string contains
    the given substring."""
    if binary is None:
        return bundle.root / bundle.main_executable_name
    matches = [p for p in bundle_executable_paths(bundle) if binary in str(p)]
    if not matches:
        typer.secho(f"error: no executable matching '{binary}' found in the bundle", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if len(matches) > 1:
        typer.secho(
            f"error: '{binary}' matches multiple executables: {[str(p) for p in matches]} -- be more specific",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    return matches[0]


@app.command("classdump")
def analysis_classdump(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
    class_name: str | None = typer.Option(None, "--class", help="Restrict to one class"),
    search: str | None = typer.Option(None, "--search", help="Only classes whose name matches this regex"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to a file instead of stdout"),
) -> None:
    """Dump the app's Objective-C runtime metadata as `.h`-style class-dump
    text: every class (superclass, protocol conformance, ivars, properties,
    method signatures), protocol declarations, and categories. `--class`/
    `--search` restrict output to matching classes only (protocols and
    categories are omitted in that case, matching `forge hooks extract`)."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_analysis_") as tmp:
        app_path = extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)

    if class_name and class_name not in analysis.classes:
        typer.secho(f"class '{class_name}' not found", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    text = render_analysis(analysis, class_filter=class_name, search=search)
    if not text:
        typer.echo("no matching classes/protocols/categories found")
        raise typer.Exit(code=1)

    if output:
        output.write_text(text + "\n")
        typer.echo(f"wrote {output}")
    else:
        typer.echo(text)


@app.command("strings")
def analysis_strings(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
    min_len: int = typer.Option(4, "--min-len", help="Minimum printable-ASCII run length to report"),
    search: str | None = typer.Option(None, "--search", help="Only strings matching this regex"),
    binary: str | None = typer.Option(None, "--binary", help="Restrict to one executable (bundle-relative substring)"),
) -> None:
    """Extract printable strings from every executable in the bundle (main +
    frameworks + dylibs + extensions), tagged with which binary each string
    came from. Pipe to grep for anything not covered by --search."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_analysis_") as tmp:
        app_path = extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        found = strings_in_bundle(bundle, min_len=min_len)

    if binary:
        found = [s for s in found if binary in s.binary]
    if search:
        pat = _re.compile(search)
        found = [s for s in found if pat.search(s.value)]

    for s in found:
        typer.echo(f"[{s.binary}] {s.value}")
    typer.echo(f"-- {len(found)} string(s)", err=True)


@app.command("symbols")
def analysis_symbols(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
    binary: str | None = typer.Option(None, "--binary", help="Which executable to inspect; default: main executable"),
    arch: str | None = typer.Option(None, "--arch", help="Architecture slice, required for a universal binary"),
) -> None:
    """Linked libraries and imported/exported symbols for one Mach-O
    executable in the bundle (`otool -L` + `nm`, structured)."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_analysis_") as tmp:
        app_path = extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        target = _select_binary(bundle, binary)
        try:
            result = analyze_symbols(target, arch)
        except (AmbiguousArchError, ArchNotFoundError, NotMachOError) as e:
            typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None

    typer.echo(f"{result.binary} ({result.arch})")
    typer.echo(f"linked libraries ({len(result.linked_libraries)}):")
    for lib in result.linked_libraries:
        typer.echo(f"  {lib}")
    typer.echo(f"imported symbols ({len(result.imported_symbols)}):")
    for sym in result.imported_symbols:
        typer.echo(f"  {sym}")
    typer.echo(f"exported symbols ({len(result.exported_symbols)}):")
    for sym in result.exported_symbols:
        typer.echo(f"  {sym}")


@app.command("security")
def analysis_security(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
    binary: str | None = typer.Option(None, "--binary", help="Which executable to inspect; default: main executable"),
    arch: str | None = typer.Option(None, "--arch", help="Architecture slice, required for a universal binary"),
) -> None:
    """PIE, encryption-flag (detection only, never decrypted), stack
    protector, an ARC heuristic, min-OS, and platform for one executable."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_analysis_") as tmp:
        app_path = extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        target = _select_binary(bundle, binary)
        try:
            posture = analyze_security(target, arch)
        except (AmbiguousArchError, ArchNotFoundError, NotMachOError) as e:
            typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None

    typer.echo(render_security_posture(posture))
