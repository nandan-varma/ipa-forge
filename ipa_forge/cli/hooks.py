# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge hooks` subcommands: verify / extract / audit / manifest / diff.

Hook verification catches the silent no-ops that version drift causes: a
class/selector rename in a newer app build and the dylib hook just stops
firing. These commands turn that into a checkable report against the actual
binary (main executable + every embedded framework).
"""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import typer

from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.cli.common import validated_extract
from ipa_forge.hooks.binary import analyze_bundle
from ipa_forge.hooks.scan import scan_hook_sources
from ipa_forge.hooks.verify import HookDecl, verify_hooks
from ipa_forge.patch.loader import load_patch_definition

app = typer.Typer(help="Mach-O Objective-C hook verification (catches silent no-ops on version drift).")


@app.command("verify")
def hooks_verify(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition with a `hooks:` section"),
    required_only: bool = typer.Option(False, "--required-only", help="Only print hooks that fail to attach"),
) -> None:
    """Verify every declared hook in the patch definition against the app binary.
    Exit code 0 = all required hooks attach; 1 = a required hook is missing."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        try:
            app_path = validated_extract(ipa, Path(tmp))
            bundle = load_bundle(app_path)
            definition = load_patch_definition(patches)
        except ValueError as e:
            typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        decls = [HookDecl(h.class_name, h.selector, h.kind, h.added, h.required) for h in (definition.hooks or [])]
        if not decls:
            typer.echo("No hooks declared in this definition (add a `hooks:` section).")
            raise typer.Exit(code=0)
        analysis = analyze_bundle(bundle)
        results = verify_hooks(analysis, decls)
        for r in results:
            if required_only and r.ok:
                continue
            color = typer.colors.GREEN if r.ok else typer.colors.YELLOW
            flag = "" if r.ok else f"  ({r.detail})"
            label = f"[{r.status:16}] {r.class_name} "
            label += f"{'+' if r.kind == 'class' else '-'}[{r.selector}]{flag}"
            typer.secho(label, fg=color)
        bad = [r for r in results if not r.ok and r.required]
        ok = sum(1 for r in results if r.ok)
        typer.echo(f"{ok}/{len(results)} hooks attach; {len(bad)} required hook(s) failing.")
        raise typer.Exit(code=1 if bad else 0)


@app.command("extract")
def hooks_extract(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    class_name: str | None = typer.Option(None, "--class", help="Restrict to one class"),
    search: str | None = typer.Option(None, "--search", help="Only classes whose name matches this regex"),
    limit: int = typer.Option(60, "--limit", help="Max classes to print (0 = no limit)"),
) -> None:
    """Dump the Objective-C class table of the app's binaries: class names,
    superclasses, and instance/class method lists (chained-fixup aware)."""
    import re as _re

    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = validated_extract(ipa, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)
    if class_name:
        cls = analysis.classes.get(class_name)
        if not cls:
            in_names = class_name in analysis.classnames
            typer.secho(f"class '{class_name}' not parsed (classname string: {in_names})", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        targets = [cls]
    elif search:
        pat = _re.compile(search)
        targets = [c for c in analysis.classes.values() if pat.search(c.name)]
        targets.sort(key=lambda c: c.name)
    else:
        targets = sorted(analysis.classes.values(), key=lambda c: c.name)
    if limit:
        targets = targets[:limit]
    for cls in targets:
        typer.echo(f"{cls.name} : {cls.super_name}  (inst={len(cls.inst)} cls={len(cls.cls)})")
        if cls.inst:
            typer.echo("  inst: " + ", ".join(sorted(cls.inst)[:40]))
        if cls.cls:
            typer.echo("  class: " + ", ".join(sorted(cls.cls)[:12]))


@app.command("audit")
def hooks_audit(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    dylib_src: Path = typer.Option(..., "--dir", exists=True, help="Directory of tweak sources (*.m/*.h) to scan"),
) -> None:
    """Scan ObjC tweak sources for hook calls and verify each target against
    the app binary. Catches hooks the author wrote but a newer app version
    broke."""
    decls = scan_hook_sources(dylib_src)
    if not decls:
        typer.echo("No hook calls found in the sources.")
        raise typer.Exit(code=0)
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = validated_extract(ipa, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)
    results = verify_hooks(analysis, decls)
    statuses = Counter(r.status for r in results)
    typer.echo(f"{len(results)} hooks found in sources: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    for r in results:
        if not r.ok:
            typer.secho(
                f"[{r.status:16}] {r.class_name} {'+' if r.kind == 'class' else '-'}[{r.selector}]  {r.detail}",
                fg=typer.colors.YELLOW,
            )


@app.command("manifest")
def hooks_manifest(
    dylib_src: Path = typer.Option(..., "--dir", exists=True, help="Directory of tweak sources (*.m)"),
    required: Path | None = typer.Option(
        None, "--required", exists=True, help="Optional file with 'ClassName selector' lines to mark required: true"
    ),
) -> None:
    """Emit a `hooks:` YAML block from the hook calls in tweak sources — the
    block goes into the patch definition's `hooks:` section so dry-run
    verifies every hook against the real binary."""
    decls = scan_hook_sources(dylib_src)
    if not decls:
        typer.echo("No hook calls found in the sources.")
        raise typer.Exit(code=0)

    required_set: set[tuple[str, str]] = set()
    if required:
        for line in required.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                required_set.add((parts[0], parts[1]))

    typer.echo("hooks:")
    for d in decls:
        typer.echo(f'  - class: "{d.class_name}"')
        typer.echo(f'    selector: "{d.selector}"')
        typer.echo(f"    kind: {d.kind}")
        if d.added:
            typer.echo("    added: true")
        if (d.class_name, d.selector) in required_set:
            typer.echo("    required: true")
    typer.secho(f"# {len(decls)} hooks ({len(required_set)} required)", fg=typer.colors.BRIGHT_BLACK)


@app.command("diff")
def hooks_diff(
    old_ipa: Path = typer.Option(..., "--old", exists=True, help="Previously-working .ipa"),
    new_ipa: Path = typer.Option(..., "--new", exists=True, help="New .ipa"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition with a `hooks:` section"),
) -> None:
    """Compare hook attachment between two IPAs — the porting aid. Shows every
    hook whose status changed, highlighting ones that regressed (would no-op
    on the new version). Exit 1 if a required hook regressed."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        bundle_old = load_bundle(validated_extract(old_ipa, Path(tmp) / "old"))
        bundle_new = load_bundle(validated_extract(new_ipa, Path(tmp) / "new"))
        definition = load_patch_definition(patches)
        decls = [HookDecl(h.class_name, h.selector, h.kind, h.added, h.required) for h in (definition.hooks or [])]
        if not decls:
            typer.echo("No hooks declared in the definition (add a `hooks:` section).")
            raise typer.Exit(code=0)
        old_results = {r.class_name + r.selector: r for r in verify_hooks(analyze_bundle(bundle_old), decls)}
        new_results = {r.class_name + r.selector: r for r in verify_hooks(analyze_bundle(bundle_new), decls)}

    regressed = 0
    for d in decls:
        key = d.class_name + d.selector
        old = old_results.get(key)
        new = new_results.get(key)
        if old is None or new is None:
            continue
        if old.ok and not new.ok:
            regressed += 1
            typer.secho(
                f"[{old.status:14} -> {new.status:14}] {d.class_name} "
                f"{'+' if d.kind == 'class' else '-'}[{d.selector}]  REGRESSED",
                fg=typer.colors.RED,
            )
        elif old.status != new.status:
            typer.secho(
                f"[{old.status:14} -> {new.status:14}] {d.class_name} "
                f"{'+' if d.kind == 'class' else '-'}[{d.selector}]",
                fg=typer.colors.YELLOW,
            )
    typer.echo(f"{regressed} hook(s) regressed" + (" — required hook broken" if regressed else "."))
    raise typer.Exit(code=1 if regressed else 0)
