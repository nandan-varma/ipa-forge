# SPDX-License-Identifier: GPL-3.0-or-later
"""Protocol/ivar/property/category parsing in `machO.objc` -- the metadata
class-dump needs beyond what hook verification (class/method/selref) uses."""

from __future__ import annotations

from pathlib import Path

from ipa_forge.machO.objc import analyze_macho


def test_analyze_protocol_conformance_and_methods(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    bar = analysis.classes.get("Bar")
    assert bar is not None
    assert "Greeter" in bar.protocols

    greeter = analysis.protocols.get("Greeter")
    assert greeter is not None
    assert "greet" in greeter.inst
    assert "wave" in greeter.opt_inst


def test_analyze_method_type_encoding(objc_rich_macho_binary: Path) -> None:
    """Methods map selector -> type encoding now, not just a bare selector
    set -- class-dump needs the encoding to render argument/return types."""
    analysis = analyze_macho(objc_rich_macho_binary)
    bar = analysis.classes["Bar"]
    # -(void)greet -- v (void return), @ (self), : (_cmd); no args beyond that
    assert bar.inst["greet"] == "v16@0:8"


def test_analyze_ivars_and_properties(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    bar = analysis.classes["Bar"]
    ivar_names = {iv.name for iv in bar.ivars}
    assert "_count" in ivar_names

    prop_names = {p.name for p in bar.properties}
    assert "label" in prop_names
    label = next(p for p in bar.properties if p.name == "label")
    assert label.attributes  # raw attribute string, e.g. 'T@"NSString",C,N,V_label'


def test_analyze_category(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    assert len(analysis.categories) == 1
    cat = analysis.categories[0]
    assert cat.name == "Extras"
    # NSObject is defined in Foundation, not this image, so the cls pointer is
    # an external bind -- reported as "«external»", never a silently wrong name
    assert cat.class_name == "«external»"
    assert "extraThing" in cat.inst


def test_analyze_bundle_merges_protocols_and_categories(objc_rich_macho_binary: Path, tmp_path: Path) -> None:
    import plistlib
    import zipfile

    from ipa_forge.bundle.ipa import load_bundle

    app_dir = tmp_path / "Payload" / "Test.app"
    app_dir.mkdir(parents=True)
    (app_dir / "Test").write_bytes(objc_rich_macho_binary.read_bytes())
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

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(ipa) as zf:
        zf.extractall(extract_dir)
    bundle = load_bundle(extract_dir / "Payload" / "Test.app")

    from ipa_forge.machO.objc import analyze_bundle

    analysis = analyze_bundle(bundle)
    assert "Greeter" in analysis.protocols
    assert any(c.name == "Extras" for c in analysis.categories)
