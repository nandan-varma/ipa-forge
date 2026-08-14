# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook analyzer tests against a real compiled ObjC Mach-O: class walk,
method lists, selrefs, and the CLI commands built on them."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ipa_forge.hooks.binary import analyze_macho
from ipa_forge.hooks.scan import scan_hook_sources

runner = CliRunner()


def test_analyze_objc_binary_class_methods(objc_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_macho_binary)
    foo = analysis.classes.get("Foo")
    assert foo is not None
    assert "doIt:" in foo.inst
    assert "makeIt" in foo.cls
    # Foo's superclass (NSObject) lives in Foundation — external to this
    # binary, so it either stays None or resolves to the external marker
    assert foo.super_name in {None, "«external»"}
    assert "doIt:" in analysis.selectors  # selrefs ground truth


def test_analyze_fat_binary_thins_to_arm64(fat_macho_binary: Path) -> None:
    # lipo thinning must not crash; a C-only binary has no classes but parses
    analysis = analyze_macho(fat_macho_binary)
    assert analysis.main_executable is not None


def test_scan_hook_sources_direct_and_variable(tmp_path: Path) -> None:
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
    thing = ("Thing", "doIt:")
    other = ("Other", "makeIt")
    third = ("Third", "addedThing")
    assert thing in by
    assert other in by and by[other].kind == "class"
    assert third in by and by[third].added


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


def _hooks_yaml(tmp_path: Path, target: str, selector: str, **extra: object) -> Path:
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


def test_cli_extract_dumps_class(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["extract", "--ipa", str(ipa), "--class", "Foo"],
    )
    assert result.exit_code == 0
    assert "Foo" in result.stdout
    assert "doIt:" in result.stdout


def test_cli_verify_reports_ok(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Foo", "doIt:")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["verify", "--ipa", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 0
    assert "1/1 hooks attach" in result.stdout


def test_cli_verify_required_missing_fails(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Gone", "nope:", required="true")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["verify", "--ipa", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 1
    assert "missing-class" in result.stdout


def test_cli_diff_identical_no_regressions(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Foo", "doIt:")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["diff", "--old", str(ipa), "--new", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 0
    assert "0 hook(s) regressed" in result.stdout


def test_cli_manifest_emits_block(tmp_path: Path) -> None:
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


def test_cli_extract_class_not_found(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["extract", "--ipa", str(ipa), "--class", "Nope"],
    )
    assert result.exit_code == 1
    assert "not parsed" in result.stdout


def test_cli_extract_search_regex(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["extract", "--ipa", str(ipa), "--search", "^Foo"],
    )
    assert result.exit_code == 0
    assert "Foo" in result.stdout


def test_cli_verify_no_hooks_declared(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = tmp_path / "nohooks.yaml"
    hooks.write_text(
        "target:\n"
        "  bundle_id: com.example.testapp\n"
        "  version: { exact: 1.0.0 }\n"
        "patches:\n"
        "  - id: p\n"
        "    type: plist_edit\n"
        "    action: set\n"
        "    key: CFBundleDisplayName\n"
        "    value: X\n"
    )
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["verify", "--ipa", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 0
    assert "No hooks declared" in result.stdout


def test_cli_verify_bad_ipa_clean_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ipa"
    bad.write_text("not a zip")
    hooks = _hooks_yaml(tmp_path, "Foo", "doIt:")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["verify", "--ipa", str(bad), "--patches", str(hooks)],
    )
    assert result.exit_code == 1
    assert "error:" in result.stderr


def test_cli_audit_reports_statuses(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    (tmp_path / "tweak.m").write_text(
        'static void a(void) { ytfHookInstance(NSClassFromString(@"Foo"), @selector(doIt:), ^void(id self) {}); }\n'
    )
    src_dir = tmp_path / "tweak_src"
    src_dir.mkdir()
    (src_dir / "tweak.m").write_text((tmp_path / "tweak.m").read_text())
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["audit", "--ipa", str(ipa), "--dir", str(src_dir)],
    )
    assert result.exit_code == 0
    assert "1 hooks found in sources: ok=1" in result.stdout


def test_cli_audit_no_hook_calls(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    src_dir = tmp_path / "empty_src"
    src_dir.mkdir()
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["audit", "--ipa", str(ipa), "--dir", str(src_dir)],
    )
    assert result.exit_code == 0
    assert "No hook calls found" in result.stdout


def test_cli_manifest_marks_required(tmp_path: Path) -> None:
    (tmp_path / "tweak.m").write_text(
        'static void a(void) { ytfHookInstance(NSClassFromString(@"Thing"), @selector(doIt:), ^void(id self) {}); }\n'
    )
    required = tmp_path / "required.txt"
    required.write_text("# comment\nThing doIt:\n\nOther makeIt\n")
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["manifest", "--dir", str(tmp_path), "--required", str(required)],
    )
    assert result.exit_code == 0
    assert "required: true" in result.stdout


def test_cli_manifest_no_hook_calls(tmp_path: Path) -> None:
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["manifest", "--dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "No hook calls found" in result.stdout


def test_cli_diff_regression_fails(objc_macho_binary: Path, tmp_path: Path, fake_ipa: Path) -> None:
    objc_ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = _hooks_yaml(tmp_path, "Foo", "doIt:", required="true")
    # old attaches the hook, new (plain C binary) does not -> required regression
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["diff", "--old", str(objc_ipa), "--new", str(fake_ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 1
    assert "REGRESSED" in result.stdout
    assert "1 hook(s) regressed" in result.stdout


def test_cli_diff_no_hooks_declared(objc_macho_binary: Path, tmp_path: Path) -> None:
    ipa = _pack_ipa(objc_macho_binary, tmp_path)
    hooks = tmp_path / "nohooks.yaml"
    hooks.write_text(
        "target:\n"
        "  bundle_id: com.example.testapp\n"
        "  version: { exact: 1.0.0 }\n"
        "patches:\n"
        "  - id: p\n"
        "    type: plist_edit\n"
        "    action: set\n"
        "    key: CFBundleDisplayName\n"
        "    value: X\n"
    )
    result = runner.invoke(
        __import__("ipa_forge.cli.hooks", fromlist=["app"]).app,
        ["diff", "--old", str(ipa), "--new", str(ipa), "--patches", str(hooks)],
    )
    assert result.exit_code == 0
    assert "No hooks declared" in result.stdout
