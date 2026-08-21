# SPDX-License-Identifier: GPL-3.0-or-later
"""`forge hooks` subcommands: verify / extract / audit / manifest / diff.

Hook verification catches the silent no-ops that version drift causes: a
class/selector rename in a newer app build and the dylib hook just stops
firing. These commands turn that into a checkable report against the actual
binary (main executable + every embedded framework).

Every command accepts ``--app-dir`` in place of the IPA: point it at an
already-extracted ``Payload/<App>.app`` directory to skip the (potentially
slow) re-extraction when iterating on the same app — e.g. after one
``forge patch`` run the working bundle can be reused for the whole
verify/fix/verify loop.
"""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import typer

from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.cli.common import extract_or_use as _extract_or_use
from ipa_forge.cli.common import resolve_app_path
from ipa_forge.hooks.scan import scan_hook_sources
from ipa_forge.hooks.verify import HookDecl, verify_hooks
from ipa_forge.machO.objc import analyze_bundle
from ipa_forge.patch.loader import load_patch_definition

app = typer.Typer(help="Mach-O Objective-C hook verification (catches silent no-ops on version drift).")


@app.command("verify")
def hooks_verify(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition with a `hooks:` section"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
    required_only: bool = typer.Option(False, "--required-only", help="Only print hooks that fail to attach"),
) -> None:
    """Verify every declared hook in the patch definition against the app binary.
    Exit code 0 = all required hooks attach; 1 = a required hook is missing."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = _extract_or_use(ipa, app_dir, Path(tmp))
        try:
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
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
    class_name: str | None = typer.Option(None, "--class", help="Restrict to one class"),
    search: str | None = typer.Option(None, "--search", help="Only classes whose name matches this regex"),
    limit: int = typer.Option(60, "--limit", help="Max classes to print (0 = no limit)"),
) -> None:
    """Dump the Objective-C class table of the app's binaries: class names,
    superclasses, and instance/class method lists (chained-fixup aware)."""
    import re as _re

    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = _extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)
    if class_name:
        cls = analysis.classes.get(class_name)
        if not cls:
            in_names = class_name in analysis.classnames
            present = any((b"\x00" + class_name.encode("utf-8") + b"\x00") in data for data in analysis.raw_data)
            typer.secho(
                f"class '{class_name}' not parsed (classname string: {in_names}; raw string present: {present})",
                fg=typer.colors.YELLOW,
            )
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
        # Full method lists, not truncated: a `[:40]` slice silently hid real
        # methods on large config classes (e.g. YTColdConfig's 7k getters) and
        # sent users greping for selectors that WERE there. Pipe to grep.
        if cls.inst:
            typer.echo("  inst: " + ", ".join(sorted(cls.inst)))
        if cls.cls:
            typer.echo("  class: " + ", ".join(sorted(cls.cls)))


@app.command("audit")
def hooks_audit(
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    dylib_src: Path = typer.Option(..., "--dir", exists=True, help="Directory of tweak sources (*.m/*.h) to scan"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
) -> None:
    """Scan ObjC tweak sources for hook calls and verify each target against
    the app binary. Catches hooks the author wrote but a newer app version
    broke."""
    decls = scan_hook_sources(dylib_src)
    if not decls:
        typer.echo("No hook calls found in the sources.")
        raise typer.Exit(code=0)
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = _extract_or_use(ipa, app_dir, Path(tmp))
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


@app.command("find")
def hooks_find(
    selector: str = typer.Argument(..., help="Selector to look up, e.g. 'didPressVarispeed:'"),
    ipa: Path | None = typer.Option(None, "--ipa", exists=True, help="Input .ipa (not needed when --app-dir is given)"),
    app_dir: Path | None = typer.Option(
        None,
        "--app-dir",
        exists=True,
        help="Already-extracted Payload/<App>.app directory to analyze instead of re-extracting the IPA",
    ),
) -> None:
    """Reverse lookup: which classes implement a selector? Distinguishes a real
    method (swizzle-able) from a bare reference (referenced-only — no IMP
    exists, the hook cannot attach). This is the first check when a hook
    'attaches per verify' but does nothing on device."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        app_path = _extract_or_use(ipa, app_dir, Path(tmp))
        bundle = load_bundle(app_path)
        analysis = analyze_bundle(bundle)

    inst: list[str] = []
    cls: list[str] = []
    for name, c in analysis.classes.items():
        if selector in c.inst:
            inst.append(name)
        if selector in c.cls:
            cls.append(name)

    if inst:
        typer.echo(f"instance method on {len(inst)} class(es):")
        for n in sorted(inst):
            typer.echo(f"  -[{n} {selector}]")
    if cls:
        typer.echo(f"class method on {len(cls)} class(es):")
        for n in sorted(cls):
            typer.echo(f"  +[{n} {selector}]")

    if not inst and not cls:
        if selector in analysis.methnames:
            typer.secho(
                f"declared as a method name somewhere (protocol/category) but no parsed class implements "
                f"{selector} — the hook may attach if a class you did not scan provides it",
                fg=typer.colors.YELLOW,
            )
        elif selector in analysis.selectors:
            typer.secho(
                f"REFERENCED-ONLY: the binary references {selector} but no class declares it — "
                f"there is no IMP to swizzle, so a hook on it cannot attach",
                fg=typer.colors.RED,
            )
        else:
            typer.secho(f"{selector} not found anywhere in the binary", fg=typer.colors.RED)

    # similar selectors, to catch renames
    similar = sorted(s for s in analysis.selectors if selector in s and s != selector)[:10]
    if similar:
        typer.echo("\nselectors containing the lookup text:")
        for s in similar:
            typer.echo(f"  {s}")


@app.command("manifest")
def hooks_manifest(
    dylib_src: Path = typer.Option(..., "--dir", exists=True, help="Directory of tweak sources (*.m)"),
    required: Path | None = typer.Option(
        None, "--required", exists=True, help="Optional file with 'ClassName selector' lines to mark required: true"
    ),
    inplace: Path | None = typer.Option(
        None,
        "--inplace",
        exists=False,
        help="Patch definition YAML to update in place: replace its `hooks:` block with the generated one",
    ),
) -> None:
    """Emit a `hooks:` YAML block from the hook calls in tweak sources — the
    block goes into the patch definition's `hooks:` section so dry-run
    verifies every hook against the real binary. With --inplace the block is
    written straight into the patch definition (replacing the old hooks).
    Covers ytfHookInstance/ytfHookClass/ytfHookConfigBool/ytfAddInstanceMethod."""
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

    lines = ["hooks:"]
    for d in decls:
        lines.append(f'  - class: "{d.class_name}"')
        lines.append(f'    selector: "{d.selector}"')
        lines.append(f"    kind: {d.kind}")
        if d.added:
            lines.append("    added: true")
        if (d.class_name, d.selector) in required_set:
            lines.append("    required: true")
    block = "\n".join(lines) + "\n"

    if inplace:
        text = inplace.read_text()
        head = text.split("\nhooks:\n", 1)[0]
        inplace.write_text(head + "\n" + block)
        typer.echo(f"wrote {len(decls)} hooks into {inplace}")
        raise typer.Exit(code=0)

    typer.echo(block.rstrip("\n"))
    typer.secho(f"# {len(decls)} hooks ({len(required_set)} required)", fg=typer.colors.BRIGHT_BLACK)


@app.command("diff")
def hooks_diff(
    old_ipa: Path | None = typer.Option(
        None, "--old", exists=True, help="Previously-working .ipa (not needed with --old-app-dir)"
    ),
    new_ipa: Path | None = typer.Option(None, "--new", exists=True, help="New .ipa (not needed with --new-app-dir)"),
    patches: Path = typer.Option(..., "--patches", exists=True, help="Patch definition with a `hooks:` section"),
    old_app_dir: Path | None = typer.Option(
        None, "--old-app-dir", exists=True, help="Extracted Payload/<App>.app of the old build"
    ),
    new_app_dir: Path | None = typer.Option(
        None, "--new-app-dir", exists=True, help="Extracted Payload/<App>.app of the new build"
    ),
) -> None:
    """Compare hook attachment between two IPAs — the porting aid. Shows every
    hook whose status changed, highlighting ones that regressed (would no-op
    on the new version). Exit 1 if a required hook regressed."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        try:
            old_path = resolve_app_path(old_ipa, old_app_dir, Path(tmp) / "old")
            new_path = resolve_app_path(new_ipa, new_app_dir, Path(tmp) / "new")
        except ValueError as e:
            typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        bundle_old = load_bundle(old_path)
        bundle_new = load_bundle(new_path)
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
