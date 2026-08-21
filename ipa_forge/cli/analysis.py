# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge analysis` subcommands: general-purpose reverse engineering of an
IPA, built on the same Mach-O/ObjC analysis engine `forge hooks` uses for
hook verification (see `ipa_forge.machO.objc`).

Every command accepts ``--app-dir`` in place of the IPA, same as
`forge hooks` — point it at an already-extracted ``Payload/<App>.app``
directory to skip re-extraction when iterating.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from ipa_forge.analysis.classdump import render_analysis
from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.cli.common import extract_or_use
from ipa_forge.machO.objc import analyze_bundle

app = typer.Typer(help="General-purpose IPA reverse engineering: class-dump, strings, symbols, security, diff.")


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
