# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge analysis` subcommands: general-purpose reverse engineering of an
IPA, built on the same Mach-O/ObjC analysis engine `forge hooks` uses for
hook verification (see `ipa_forge.machO.objc`).

Every command accepts ``--app-dir`` in place of the IPA, same as
`forge hooks` — point it at an already-extracted ``Payload/<App>.app``
directory to skip re-extraction when iterating.
"""

from __future__ import annotations

import json
import re as _re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from ipa_forge.analysis.classdump import render_analysis, select_analysis
from ipa_forge.analysis.diff import diff_analyses, render_diff
from ipa_forge.analysis.il2cpp import Il2CppError, index_for_app
from ipa_forge.analysis.security import analyze_security, render_security_posture
from ipa_forge.analysis.strings import strings_in_bundle
from ipa_forge.analysis.symbols import analyze_symbols
from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.bundle.models import AppBundle
from ipa_forge.cli.common import extract_or_use, resolve_app_path
from ipa_forge.machO.arch import AmbiguousArchError, ArchNotFoundError, NotMachOError
from ipa_forge.machO.detect import bundle_executable_paths
from ipa_forge.machO.objc import analyze_bundle

app = typer.Typer(help="General-purpose IPA reverse engineering: class-dump, strings, symbols, security, diff, IL2CPP.")


@app.command("il2cpp")
def analysis_il2cpp(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa"),
    app_dir: Path | None = typer.Option(None, "--app-dir", exists=True, help="Extracted Payload/<App>.app"),
    methods: str | None = typer.Option(None, "--methods", help="Regex matching method names"),
    literal: str | None = typer.Option(None, "--literal", help="Regex matching string literals"),
    callers: str | None = typer.Option(None, "--callers", help="Regex matching methods whose callers to show"),
    limit: int = typer.Option(100, "--limit", min=1, help="Maximum matches to print"),
    json_output: bool = typer.Option(False, "--json", help="Print structured results"),
) -> None:
    """Find compiled Unity IL2CPP methods, string users, and direct callers."""
    if sum(x is not None for x in (methods, literal, callers)) != 1:
        typer.secho("error: select exactly one of --methods, --literal, or --callers", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        with tempfile.TemporaryDirectory(prefix="ipa_forge_il2cpp_") as tmp:
            app_path = extract_or_use(ipa, app_dir, Path(tmp))
            bundle = load_bundle(app_path)
            index = index_for_app(app_path, bundle.main_executable_name)
        rows: list[dict[str, Any]]
        if methods is not None:
            rows = [
                {
                    "address": a,
                    "method": name,
                    "references": [asdict(r) for r in index.functions[a].refs] if a in index.functions else [],
                }
                for a, name in index.find_methods(methods)[:limit]
            ]
        elif literal is not None:
            rows = [
                {
                    "literal": value,
                    "users": [{"address": a, "method": index.name_of(a), "site": site} for a, site in users],
                }
                for value, users in list(index.literal_users(literal).items())[:limit]
            ]
        else:
            targets = {a for a, _ in index.find_methods(callers or "")}
            rows = [
                {
                    "address": a,
                    "method": index.name_of(a),
                    "target": c.target,
                    "target_method": index.name_of(c.target),
                    "site": c.site,
                }
                for a, c in index.callers(targets)[:limit]
            ]
    except (Il2CppError, ValueError, _re.error) as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
    else:
        for row in rows:
            if "literal" in row:
                typer.echo(f"{row['literal']!r}")
                for user in row["users"]:
                    typer.echo(f"  {user['address']:#x} {user['method']} (load {user['site']:#x})")
            elif "target" in row:
                typer.echo(f"{row['address']:#x} {row['method']} -> {row['target_method']} ({row['site']:#x})")
            else:
                typer.echo(f"{row['address']:#x} {row['method']}")
                for ref in row["references"]:
                    typer.echo(f"  {ref['site']:#x} {ref['kind']}: {ref['value']}")
    typer.echo(f"-- {len(rows)} result(s) (limit {limit})", err=True)


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
    json_output: bool = typer.Option(False, "--json", help="Emit structured class/protocol/category metadata"),
    names_only: bool = typer.Option(False, "--names-only", help="Print only matching class names"),
    methods_matching: str | None = typer.Option(None, "--methods-matching", help="Only methods matching this regex"),
) -> None:
    """Dump the app's Objective-C runtime metadata as `.h`-style class-dump
    text: every class (superclass, protocol conformance, ivars, properties,
    method signatures), protocol declarations, and categories. `--class`/
    `--search` restrict output to matching classes only (protocols and
    categories are omitted in that case)."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_analysis_") as tmp:
        app_path = extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)

    if class_name and class_name not in analysis.classes and not json_output:
        typer.secho(f"class '{class_name}' not found", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    try:
        analysis = select_analysis(analysis, class_filter=class_name, search=search, methods_matching=methods_matching)
    except _re.error as e:
        typer.secho(f"error: invalid regex: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    if names_only:
        text = json.dumps(sorted(analysis.classes), indent=2) if json_output else "\n".join(analysis.classes)
    elif json_output:
        text = json.dumps(
            {
                "classes": {n: asdict(c) for n, c in analysis.classes.items()},
                "protocols": {n: asdict(p) for n, p in analysis.protocols.items()},
                "categories": [asdict(c) for c in analysis.categories],
            },
            default=sorted,
            indent=2,
        )
    else:
        text = render_analysis(analysis)
    if not text:
        typer.echo("no matching classes/protocols/categories found")
        raise typer.Exit(code=1)

    empty = not analysis.classes if names_only else not (analysis.classes or analysis.protocols or analysis.categories)
    if output:
        output.write_text(text + "\n")
        typer.echo(f"wrote {output}")
    else:
        typer.echo(text)
    if empty:
        raise typer.Exit(code=1)


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


@app.command("diff")
def analysis_diff(
    old_ipa: Path | None = typer.Option(
        None, "--old", exists=True, help="Previous-version .ipa (not needed with --old-app-dir)"
    ),
    new_ipa: Path | None = typer.Option(
        None, "--new", exists=True, help="New-version .ipa (not needed with --new-app-dir)"
    ),
    old_app_dir: Path | None = typer.Option(
        None, "--old-app-dir", exists=True, help="Extracted Payload/<App>.app of the old build"
    ),
    new_app_dir: Path | None = typer.Option(
        None, "--new-app-dir", exists=True, help="Extracted Payload/<App>.app of the new build"
    ),
) -> None:
    """Survey what changed between two builds of the same app: classes and
    protocols added/removed, per-class method churn, and Info.plist key
    changes. Broader and purely informational compared to `forge hooks
    diff`, which only re-checks one patch definition's declared hook
    targets and fails the exit code on a required-hook regression."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_analysis_") as tmp:
        try:
            old_path = resolve_app_path(old_ipa, old_app_dir, Path(tmp) / "old")
            new_path = resolve_app_path(new_ipa, new_app_dir, Path(tmp) / "new")
        except ValueError as e:
            typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        bundle_old = load_bundle(old_path)
        bundle_new = load_bundle(new_path)
        diff = diff_analyses(
            analyze_bundle(bundle_old),
            analyze_bundle(bundle_new),
            bundle_old.info_plist,
            bundle_new.info_plist,
        )

    typer.echo(f"{bundle_old.bundle_id} {bundle_old.version} -> {bundle_new.version}")
    typer.echo(render_diff(diff))
