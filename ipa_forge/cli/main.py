# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import tempfile
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path

import typer

from ipa_forge.altstore.source import build_app_entry, write_source_json
from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.hooks.binary import analyze_bundle
from ipa_forge.hooks.verify import HookDecl, verify_hooks
from ipa_forge.patch.loader import PatchLoadError, load_patch_definition
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.validators.bundle_validator import validate_bundle
from ipa_forge.validators.ipa_validator import IpaValidationError, validate_ipa_structure

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
            ok = sum(1 for h in hook_report if h["status"] in ("ok", "ok-system", "ok-inherited", "added"))
            typer.echo(f"Hooks: {ok}/{len(hook_report)} attach ({len(hook_report) - ok} issue(s))")
            for h in hook_report:
                if h["status"] not in ("ok", "ok-system", "ok-inherited", "added"):
                    typer.secho(
                        f"  ! {h['class']} {'+' if h['kind'] == 'class' else '-'}[{h['selector']}]: "
                        f"{h['status']} -- {h['detail']}",
                        fg=typer.colors.YELLOW,
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


@app.command()
def gui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Launch the local web GUI (wraps the same pipeline as `forge patch`)."""
    import uvicorn

    uvicorn.run("ipa_forge.gui.app:app", host=host, port=port)


hooks_app = typer.Typer(help="Mach-O Objective-C hook verification (catches silent no-ops on version drift).")
app.add_typer(hooks_app, name="hooks")


@hooks_app.command("verify")
def hooks_verify(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition with a `hooks:` section"),
    required_only: bool = typer.Option(False, "--required-only", help="Only print hooks that fail to attach"),
) -> None:
    """Verify every declared hook in the patch definition against the app binary.
    Exit code 0 = all required hooks attach; 1 = a required hook is missing."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        try:
            app_path = _validated_extract(ipa, Path(tmp))
            bundle = load_bundle(app_path)
            definition = load_patch_definition(patches)
        except (IpaValidationError, PatchLoadError, PipelineError) as e:
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
            typer.secho(
                f"[{r.status:16}] {r.class_name} {'+' if r.kind == 'class' else '-'}[{r.selector}]{flag}", fg=color
            )
        bad = [r for r in results if not r.ok and r.required]
        ok = sum(1 for r in results if r.ok)
        typer.echo(f"{ok}/{len(results)} hooks attach; {len(bad)} required hook(s) failing.")
        raise typer.Exit(code=1 if bad else 0)


@hooks_app.command("extract")
def hooks_extract(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    class_name: str | None = typer.Option(None, "--class", help="Restrict to one class"),
    search: str | None = typer.Option(None, "--search", help="Only classes whose name matches this regex"),
    limit: int = typer.Option(60, "--limit", help="Max classes to print (0 = no limit)"),
) -> None:
    """Dump the Objective-C class table of the app's main binary: class names,
    superclasses, and instance/class method lists (chained-fixup aware)."""
    import re as _re

    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = _validated_extract(ipa, Path(tmp))
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


@hooks_app.command("audit")
def scan_hook_sources(dylib_src: Path) -> list[HookDecl]:
    """Scan ObjC tweak sources for runtime hook calls. Any
    ``<prefix>HookInstance/HookClass/AddInstanceMethod(NSClassFromString(...), @selector(...))``
    pattern is recognized (ytfHook*, sptHook*, ...), so the same scanner
    serves every patch set."""
    import re as _re

    pattern = _re.compile(
        r"([A-Za-z_][A-Za-z0-9_]*)Hook(Instance|Class|AddInstanceMethod)\("
        r"\s*(?:NSClassFromString\(@?\"([^\"]+)\"\)|\[\s*(\w+)\s*class\]|(\w+))"
        r"\s*,\s*(?:@selector\(([^)]+)\)|sel_registerName\(\"([^\"]+)\"\))"
    )
    var_re = _re.compile(r"(\w+)\s*=\s*NSClassFromString\(@?\"([^\"]+)\"\)")
    decls: list[HookDecl] = []
    for f in sorted(dylib_src.glob("*.m")):
        text = f.read_text(errors="replace")
        var_class: dict[str, str] = {}
        var_classes: dict[str, set[str]] = {}
        for m in var_re.finditer(text):
            var_classes.setdefault(m.group(1), set()).add(m.group(2))
        for var, classes in var_classes.items():
            if len(classes) == 1:
                var_class[var] = next(iter(classes))
        for m in pattern.finditer(text):
            prefix, kind, cls, cls2, clsvar, sel, sel2 = m.groups()
            cls = cls or cls2 or var_class.get(clsvar or "")
            sel = sel or sel2
            if not cls or not sel:
                continue
            hook_kind = "class" if kind == "Class" else "instance"
            decls.append(HookDecl(cls, sel, hook_kind, added=(kind == "AddInstanceMethod")))  # type: ignore[arg-type]
    # de-duplicate, keep order
    seen: set[tuple[str, str]] = set()
    unique: list[HookDecl] = []
    for d in decls:
        if (d.class_name, d.selector) in seen:
            continue
        seen.add((d.class_name, d.selector))
        unique.append(d)
    return unique


def hooks_audit(
    ipa: Path = typer.Option(..., "--ipa", exists=True, help="Input .ipa"),
    dylib_src: Path = typer.Option(..., "--dir", exists=True, help="Directory of tweak sources (*.m/*.h) to scan"),
) -> None:
    """Scan ObjC tweak sources for NSClassFromString + selector hook calls and
    verify each target against the app binary. Catches hooks the author wrote
    but a newer app version broke."""
    decls = scan_hook_sources(dylib_src)
    if not decls:
        typer.echo("No hook calls found in the sources.")
        raise typer.Exit(code=0)
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = _validated_extract(ipa, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)
    results = verify_hooks(analysis, decls)
    from collections import Counter

    statuses = Counter(r.status for r in results)
    typer.echo(f"{len(results)} hooks found in sources: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    for r in results:
        if not r.ok:
            typer.secho(
                f"[{r.status:16}] {r.class_name} {'+' if r.kind == 'class' else '-'}[{r.selector}]  {r.detail}",
                fg=typer.colors.YELLOW,
            )


@hooks_app.command("manifest")
def hooks_manifest(
    dylib_src: Path = typer.Option(..., "--dir", exists=True, help="Directory of tweak sources (*.m)"),
    required: Path | None = typer.Option(None, "--required", exists=True,
        help="Optional file with 'ClassName selector' lines to mark required: true"),
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


@hooks_app.command("diff")
def hooks_diff(
    old_ipa: Path = typer.Option(..., "--old", exists=True, help="Previously-working .ipa"),
    new_ipa: Path = typer.Option(..., "--new", exists=True, help="New .ipa"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition with a `hooks:` section"),
) -> None:
    """Compare hook attachment between two IPAs — the porting aid. Shows every
    hook whose status changed, highlighting ones that regressed (would no-op
    on the new version). Exit 1 if a required hook regressed."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_old = _validated_extract(old_ipa, Path(tmp) / "old")
        bundle_old = load_bundle(app_old)
        app_new = _validated_extract(new_ipa, Path(tmp) / "new")
        bundle_new = load_bundle(app_new)
        definition = load_patch_definition(patches)
        decls = [
            HookDecl(h.class_name, h.selector, h.kind, h.added, h.required)
            for h in (definition.hooks or [])
        ]
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
        changed = old.status != new.status
        if old.ok and not new.ok:
            regressed += 1
            typer.secho(
                f"[{old.status:14} -> {new.status:14}] {d.class_name} "
                f"{'+' if d.kind == 'class' else '-'}[{d.selector}]  REGRESSED",
                fg=typer.colors.RED,
            )
        elif changed:
            typer.secho(
                f"[{old.status:14} -> {new.status:14}] {d.class_name} "
                f"{'+' if d.kind == 'class' else '-'}[{d.selector}]",
                fg=typer.colors.YELLOW,
            )
    typer.echo(f"{regressed} hook(s) regressed" + (" — required hook broken" if regressed else "."))
    raise typer.Exit(code=1 if regressed else 0)


if __name__ == "__main__":
    app()
