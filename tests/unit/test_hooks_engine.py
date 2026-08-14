# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook analyzer tests against a real compiled ObjC Mach-O: class walk,
method lists, selrefs, and the CLI commands built on them."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.hooks.binary import analyze_macho
from ipa_forge.hooks.scan import scan_hook_sources

runner = CliRunner()


def test_analyze_objc_binary_class_methods(objc_macho_binary: Path):
    analysis = analyze_macho(objc_macho_binary)
    foo = analysis.classes.get("Foo")
    assert foo is not None
    assert "doIt:" in foo.inst
    assert "makeIt" in foo.cls
    # Foo's superclass (NSObject) lives in Foundation — external to this
    # binary, so it either stays None or resolves to the external marker
    assert foo.super_name in (None, "«external»")
    assert "doIt:" in analysis.selectors  # selrefs ground truth


def test_analyze_fat_binary_thins_to_arm64(fat_macho_binary: Path):
    # lipo thinning must not crash; a C-only binary has no classes but parses
    analysis = analyze_macho(fat_macho_binary)
    assert analysis.main_executable is not None


def test_scan_hook_sources_direct_and_variable(tmp_path: Path):
    (tmp_path / "tweak.m").write_text(
        "#import <Foundation/Foundation.h>\n"
        "static void a(void) {\n"
        '    ytfHookInstance(NSClassFromString(@"Thing"), @selector(doIt:), ^void(id self) {});\n'
        "}\n"
        "static void b(void) {\n"
        '    Class c = NSClassFromString(@"Other");\n'
        "    ytfHookClass(c, @selector(makeIt), ^id(id self){return nil;});\n"
        "}\n"
        "static void c(void) {\n"
        '    ytfAddInstanceMethod(NSClassFromString(@"Third"),\n'
        '        sel_registerName("addedThing"), ^id(id self){return nil;}, "@@:");\n'
        "}\n"
    )
    decls = scan_hook_sources(tmp_path)
    by = {(d.class_name, d.selector): d for d in decls}
    assert ("Thing", "doIt:") in by
    assert ("Other", "makeIt") in by and by[("Other", "makeIt")].kind == "class"
    assert ("Third", "addedThing") in by and by[("Third", "addedThing")].added


def _pack_ipa(objc_binary: Path, tmp_path: Path) -> Path:
    """Wrap a raw Mach-O into a minimal IPA (Payload/Test.app/Test) so the
    CLI commands (which validate IPA structure first) can consume it."""
    import plistlib
    import zipfile

    app_dir = tmp_path / "Payload" / "Test.app"
    app_dir.mkdir(parents=True)
    (app_dir / "Test").write_bytes(objc_binary.read_bytes())
    info = {
        "CFBundleIdentifier": "com.example.testapp",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "CFBundleExecutable": "Test",
    }
    (app_dir / "Info.plist").write_bytes(plistlib.dumps(info))
    ipa = tmp_path / "app.ipa"
    with zipfile.ZipFile(ipa, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in app_dir.rglob("*"):
            zf.write(f, f.relative_to(tmp_path))
    return ipa


def _hooks_yaml(tmp_path: Path, target: str, selector: str, **extra) -> Path:
    lines = [
        "target:",
        "  bundle_id: com.example.testapp",
        "  version: { exact: 1.0.0 }",
        "patches:",
        "  - id: p",
        "    type: plist_edit",
        "    action: set",
        "    key: CFBundleDisplayName",
        "    value: X",
        "hooks:",
        f'  - class: "{target}"',
        f'    selector: "{selector}"',
    ]
    for k, v in extra.items():
        lines.append(f"    {k}: {v}")
    p = tmp_path / "hooks.yaml"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_cli_extract_dumps_class(objc_macho_binary: Path, tmp_path: Path):
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["extract", "--ipa", str(ipa), "--class", "Foo"],
    )
    assert result.exit_code == 0
    assert "Foo" in result.stdout
    assert "doIt:" in result.stdout


def test_cli_verify_reports_ok(objc_macho_binary: Path, tmp_path: Path):
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Foo", "doIt:")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["verify", "--ipa", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 0
    assert "1/1 hooks attach" in result.stdout


def test_cli_verify_required_missing_fails(objc_macho_binary: Path, tmp_path: Path):
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Gone", "nope:", required="true")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["verify", "--ipa", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 1
    assert "missing-class" in result.stdout


def test_cli_diff_identical_no_regressions(objc_macho_binary: Path, tmp_path: Path):
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Foo", "doIt:")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["diff", "--old", str(ipa), "--new", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 0
    assert "0 hook(s) regressed" in result.stdout


def test_cli_manifest_emits_block(tmp_path: Path):
    (tmp_path / "tweak.m").write_text(
        'static void a(void) { ytfHookInstance(NSClassFromString(@"Thing"), @selector(doIt:), ^void(id self) {}); }\n'
    )
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["manifest", "--dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert 'class: "Thing"' in result.stdout
    assert 'selector: "doIt:"' in result.stdout
