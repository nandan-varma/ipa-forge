# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook verification: status classification against a synthetic MachOAnalysis."""

import pytest

from ipa_forge.hooks.verify import HookDecl, failing, verify_hooks
from ipa_forge.machO.objc import MachOAnalysis, MachOClass


def _analysis() -> MachOAnalysis:
    return MachOAnalysis(
        classes={
            "YTThing": MachOClass(name="YTThing", super_name=None, inst={"doIt:"}, cls={"makeIt"}),
            "YTChild": MachOClass(name="YTChild", super_name="YTThing"),
            "YTCustom": MachOClass(name="YTCustom", super_name="«external»"),
            "YTView": MachOClass(name="YTView", super_name="«external»", inst={"setHidden:"}),
        },
        classnames={"YTThing", "YTChild", "YTGone", "YTWalkMissed"},
        selectors={
            "doIt:",
            "makeIt",
            "setHidden:",
            "playerAdsArray",
            "orphan:",
            "externalOnly:",
            "declaredButUnparsed:",
        },
        # methnames = selectors DECLARED as methods somewhere (protocols etc.);
        # a selector referenced but absent here is dead (no IMP to swizzle).
        methnames={"doIt:", "makeIt", "setHidden:", "playerAdsArray", "declaredButUnparsed:"},
        main_executable=None,
        # raw bytes: the name/selector cstrings the verifier cross-checks
        raw_data=[b"\x00YTBytePresent\x00\x00YTByteSelector:\x00\x00other\x00"],
    )


def _statuses(analysis, hooks) -> dict[tuple[str, str], str]:
    return {(r.class_name, r.selector): r.status for r in verify_hooks(analysis, hooks)}


def test_direct_hook_ok():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTThing", "doIt:")])
    assert r[0].status == "ok" and r[0].ok


def test_inherited_hook_ok():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTChild", "doIt:")])
    assert r[0].status == "ok-inherited" and r[0].ok


def test_class_method_kind():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTThing", "makeIt", kind="class")])
    assert r[0].status == "ok"
    r2 = verify_hooks(a, [HookDecl("YTThing", "makeIt", kind="instance")])
    assert r2[0].status != "ok"  # instance pool has no makeIt


def test_absent_class_fails():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTMissing", "x")])
    assert r[0].status == "missing-class" and not r[0].ok


def test_absent_class_with_raw_string_is_unverified():
    # the class name exists as a cstring in the binary but the class-table
    # walk missed it: a parser gap, so soft-fail instead of missing-class
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTBytePresent", "doIt:")])
    assert r[0].status == "unverified" and not r[0].ok
    assert "string present" in r[0].detail


def test_absent_class_without_raw_string_is_missing():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTAbsentEverywhere", "doIt:")])
    assert r[0].status == "missing-class"


def test_missing_selector_with_raw_string_is_unverified():
    # the selector string exists in the binary but in no parsed method list
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTThing", "YTByteSelector:")])
    assert r[0].status == "unverified" and not r[0].ok
    assert "string present" in r[0].detail


def test_swift_class_absent_is_unverified_not_ok_system():
    # a Swift-mangled class the walk missed must not be labelled a system
    # class — that would hide drift
    a = _analysis()
    r = verify_hooks(a, [HookDecl("_TtC12SomeModule15SomeView", "doIt:")])
    assert r[0].status == "unverified" and not r[0].ok


def test_system_class_with_referenced_selector_still_ok_system():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("UIView", "setHidden:")])
    assert r[0].status == "ok-system" and r[0].ok


def test_classname_only_is_unverified_not_missing():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTWalkMissed", "any")])
    assert r[0].status == "unverified"


def test_selector_nowhere_fails():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTThing", "nope:")])
    assert r[0].status == "missing-selector" and not r[0].ok


def test_selector_only_on_other_class_is_elsewhere():
    a = _analysis()
    # "setHidden:" exists on YTView, not YTThing -> real no-op risk
    r = verify_hooks(a, [HookDecl("YTThing", "setHidden:")])
    assert r[0].status == "elsewhere" and not r[0].ok


def test_system_superclass_method_is_ok_inherited():
    a = _analysis()
    # YTCustom's super is external; setHidden: is a UIKit method -> attaches
    r = verify_hooks(a, [HookDecl("YTCustom", "setHidden:")])
    assert r[0].status == "ok-inherited" and r[0].ok


def test_system_class_referenced_selector():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("NSView", "setHidden:")])
    assert r[0].status == "ok-system" and r[0].ok


def test_system_class_unreferenced_selector_unverified():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("NSView", "secretPrivate:")])
    assert r[0].status == "unverified" and not r[0].ok


def test_added_hook_referenced_is_ok():
    a = _analysis()
    # app calls playerAdsArray (selrefs) but no class implements it -> the add fills a hole
    r = verify_hooks(a, [HookDecl("YTPlayerResponse", "playerAdsArray", added=True)])
    assert r[0].status == "ok" and r[0].ok


def test_added_hook_absent_is_ok():
    a = _analysis()
    r = verify_hooks(a, [HookDecl("YTPlayerResponse", "brandNewThing", added=True)])
    assert r[0].status == "added" and r[0].ok


def test_required_failure_is_failing():
    a = _analysis()
    hooks = [
        HookDecl("YTThing", "doIt:", required=True),
        HookDecl("YTMissing", "x", required=True),
    ]
    results = verify_hooks(a, hooks)
    assert [r.class_name for r in failing(results)] == ["YTMissing"]


def test_pipeline_hook_report_shape():
    """The pipeline serializes HookResult to dicts; verify the shape here."""
    from ipa_forge.hooks.verify import HookResult

    r = HookResult("YTThing", "doIt:", "instance", "ok", "on YTThing", required=False)
    d = {
        "class": r.class_name,
        "selector": r.selector,
        "kind": r.kind,
        "status": r.status,
        "detail": r.detail,
        "required": r.required,
    }
    assert d["status"] == "ok" and d["required"] is False


def test_hook_spec_yaml_roundtrip():
    """A patch definition with a `hooks:` section parses (schema integration)."""
    import tempfile
    from pathlib import Path

    from ipa_forge.patch.loader import load_patch_definition

    yaml_text = """
target:
  bundle_id: "com.example.synthetic"
  version: { exact: "1.0.0" }
patches:
  - id: "rename"
    type: plist_edit
    action: "set"
    key: "CFBundleDisplayName"
    value: "Patched"
hooks:
  - class: "YTThing"
    selector: "doIt:"
    required: true
  - class: "YTColdConfig"
    selector: "iosEnableMuteButtonPlayerControl"
    kind: class
    added: true
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "def.yaml"
        p.write_text(yaml_text)
        d = load_patch_definition(p)
    assert d.hooks is not None and len(d.hooks) == 2
    assert d.hooks[0].class_name == "YTThing"
    assert d.hooks[0].selector == "doIt:"
    assert d.hooks[0].required is True
    assert d.hooks[1].kind == "class" and d.hooks[1].added is True


def test_hook_spec_rejects_bad_kind():
    import tempfile
    from pathlib import Path

    from ipa_forge.patch.loader import PatchLoadError, load_patch_definition

    yaml_text = """
target:
  bundle_id: "com.example.synthetic"
  version: { exact: "1.0.0" }
patches:
  - id: "rename"
    type: plist_edit
    action: "set"
    key: "CFBundleDisplayName"
    value: "Patched"
hooks:
  - class: "YTThing"
    selector: "doIt:"
    kind: "bogus"
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "bad.yaml"
        p.write_text(yaml_text)
        with pytest.raises(PatchLoadError):
            load_patch_definition(p)


def test_referenced_only_selector_is_dead():
    """A selector in selrefs but NOT declared as any method name cannot be
    swizzled (no IMP exists) — the hook cannot attach. This is the
    didPressVarispeed:/selectItemWithPivotIdentifier: class of bug."""
    a = _analysis()  # "orphan:" is referenced but absent from methnames
    r = verify_hooks(a, [HookDecl("YTThing", "orphan:")])
    assert r[0].status == "referenced-only"
    assert not r[0].ok


def test_methname_declared_selector_stays_unverified():
    """Declared as a method somewhere (protocol/category/undecoded list) but
    not in any parsed class method list — a parser gap, kept soft."""
    a = _analysis()  # "declaredButUnparsed:" is in methnames but no class has it
    r = verify_hooks(a, [HookDecl("YTThing", "declaredButUnparsed:")])
    assert r[0].status == "unverified"
