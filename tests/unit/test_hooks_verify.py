# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook verification: status classification against a synthetic MachOAnalysis."""

import pytest

from ipa_forge.hooks.binary import MachOAnalysis, MachOClass
from ipa_forge.hooks.verify import HookDecl, failing, verify_hooks


def _analysis() -> MachOAnalysis:
    return MachOAnalysis(
        classes={
            "YTThing": MachOClass(name="YTThing", super_name=None, inst={"doIt:"}, cls={"makeIt"}),
            "YTChild": MachOClass(name="YTChild", super_name="YTThing"),
            "YTCustom": MachOClass(name="YTCustom", super_name="«external»"),
            "YTView": MachOClass(name="YTView", super_name="«external»", inst={"setHidden:"}),
        },
        classnames={"YTThing", "YTChild", "YTGone", "YTWalkMissed"},
        selectors={"doIt:", "makeIt", "setHidden:", "playerAdsArray", "orphan:", "externalOnly:"},
        main_executable=None,
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
    from ipa_forge.patch.loader import load_patch_definition
    from pathlib import Path
    import tempfile

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
    from ipa_forge.patch.loader import PatchLoadError, load_patch_definition
    from pathlib import Path
    import tempfile

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
