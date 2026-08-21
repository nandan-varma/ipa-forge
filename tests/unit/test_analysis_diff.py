# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-to-version diffing: added/removed classes, per-class method
churn, and Info.plist key changes."""

from __future__ import annotations

from ipa_forge.analysis.diff import diff_analyses, diff_classes, diff_plists, render_diff
from ipa_forge.machO.objc import MachOAnalysis, MachOClass, MachOProtocol


def _analysis(classes: dict[str, MachOClass], protocols: dict[str, MachOProtocol] | None = None) -> MachOAnalysis:
    return MachOAnalysis(
        classes=classes, classnames=set(classes), selectors=set(), main_executable=None, protocols=protocols or {}
    )


def test_diff_classes_detects_added_and_removed() -> None:
    old = _analysis({"Foo": MachOClass(name="Foo")})
    new = _analysis({"Bar": MachOClass(name="Bar")})
    added, removed, changed = diff_classes(old, new)
    assert added == {"Bar"}
    assert removed == {"Foo"}
    assert changed == {}


def test_diff_classes_detects_method_churn_on_shared_class() -> None:
    old = _analysis({"Foo": MachOClass(name="Foo", inst={"a:": "v@:@"}, cls={"b": "v@:"})})
    new = _analysis({"Foo": MachOClass(name="Foo", inst={"a:": "v@:@", "c:": "v@:@"}, cls={})})
    added, removed, changed = diff_classes(old, new)
    assert added == set() and removed == set()
    assert changed["Foo"] == ({"c:"}, {"b"})


def test_diff_classes_no_changes_when_identical() -> None:
    old = _analysis({"Foo": MachOClass(name="Foo", inst={"a:": ""})})
    new = _analysis({"Foo": MachOClass(name="Foo", inst={"a:": ""})})
    added, removed, changed = diff_classes(old, new)
    assert not added and not removed and not changed


def test_diff_plists_detects_added_removed_changed() -> None:
    old_plist = {"CFBundleShortVersionString": "1.0.0", "Removed": "x"}
    new_plist = {"CFBundleShortVersionString": "1.1.0", "Added": "y"}
    changed = diff_plists(old_plist, new_plist)
    assert changed["CFBundleShortVersionString"] == ("1.0.0", "1.1.0")
    assert changed["Removed"] == ("x", None)
    assert changed["Added"] == (None, "y")


def test_diff_analyses_combines_everything() -> None:
    old = _analysis({"Foo": MachOClass(name="Foo")}, protocols={"P1": MachOProtocol(name="P1")})
    new = _analysis(
        {"Foo": MachOClass(name="Foo"), "Bar": MachOClass(name="Bar")}, protocols={"P2": MachOProtocol(name="P2")}
    )
    diff = diff_analyses(old, new, {"V": "1.0"}, {"V": "2.0"})
    assert diff.added_classes == {"Bar"}
    assert diff.added_protocols == {"P2"}
    assert diff.removed_protocols == {"P1"}
    assert diff.changed_plist_keys == {"V": ("1.0", "2.0")}
    assert diff.has_changes


def test_render_diff_reports_no_differences() -> None:
    old = _analysis({"Foo": MachOClass(name="Foo")})
    new = _analysis({"Foo": MachOClass(name="Foo")})
    diff = diff_analyses(old, new, {}, {})
    assert render_diff(diff) == "no differences found"


def test_render_diff_lists_classes_protocols_methods_plist() -> None:
    old = _analysis({"Foo": MachOClass(name="Foo", inst={"a:": ""})}, protocols={"P1": MachOProtocol(name="P1")})
    new = _analysis(
        {"Foo": MachOClass(name="Foo", inst={"b:": ""}), "Bar": MachOClass(name="Bar")},
        protocols={"P2": MachOProtocol(name="P2")},
    )
    diff = diff_analyses(old, new, {"V": "1.0"}, {"V": "2.0"})
    text = render_diff(diff)
    assert "Bar" in text
    assert "P2" in text and "P1" in text
    assert "Foo: + b:" in text and "Foo: - a:" in text
    assert "V:" in text
