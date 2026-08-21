# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-to-version diffing for porting: what changed between two builds
of the same app -- classes/protocols added or removed, per-class method
churn, and Info.plist key changes.

Distinct from `forge hooks diff`, which only re-checks a patch definition's
*declared* hook targets and is a pass/fail gate (did a required hook
regress?). This is the broader, informational survey: what changed at all,
independent of any particular patch set. Entitlements are deliberately not
diffed here -- reading them requires shelling out to `codesign`/`security`,
and `signing/backend.py` is the only module allowed to do that (see
architecture.md's hard constraint); a real entitlements diff belongs there,
not in this read-only static-analysis package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ipa_forge.machO.objc import MachOAnalysis

_MISSING = object()


@dataclass
class AnalysisDiff:
    added_classes: set[str] = field(default_factory=set)
    removed_classes: set[str] = field(default_factory=set)
    added_protocols: set[str] = field(default_factory=set)
    removed_protocols: set[str] = field(default_factory=set)
    # class name -> (added selectors, removed selectors); instance + class
    # methods combined, only for classes present in both builds.
    changed_class_methods: dict[str, tuple[set[str], set[str]]] = field(default_factory=dict)
    changed_plist_keys: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_classes
            or self.removed_classes
            or self.added_protocols
            or self.removed_protocols
            or self.changed_class_methods
            or self.changed_plist_keys
        )


def diff_classes(
    old: MachOAnalysis, new: MachOAnalysis
) -> tuple[set[str], set[str], dict[str, tuple[set[str], set[str]]]]:
    old_names = set(old.classes)
    new_names = set(new.classes)
    added = new_names - old_names
    removed = old_names - new_names

    changed: dict[str, tuple[set[str], set[str]]] = {}
    for name in old_names & new_names:
        old_methods = set(old.classes[name].inst) | set(old.classes[name].cls)
        new_methods = set(new.classes[name].inst) | set(new.classes[name].cls)
        added_m = new_methods - old_methods
        removed_m = old_methods - new_methods
        if added_m or removed_m:
            changed[name] = (added_m, removed_m)
    return added, removed, changed


def diff_plists(old_plist: dict[str, Any], new_plist: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Key -> (old value, new value); a key present on only one side reports
    `None` for the side it's missing from."""
    changed: dict[str, tuple[Any, Any]] = {}
    for key in set(old_plist) | set(new_plist):
        old_val = old_plist.get(key, _MISSING)
        new_val = new_plist.get(key, _MISSING)
        if old_val != new_val:
            changed[key] = (
                None if old_val is _MISSING else old_val,
                None if new_val is _MISSING else new_val,
            )
    return changed


def diff_analyses(
    old: MachOAnalysis,
    new: MachOAnalysis,
    old_plist: dict[str, Any],
    new_plist: dict[str, Any],
) -> AnalysisDiff:
    added_classes, removed_classes, changed_methods = diff_classes(old, new)
    return AnalysisDiff(
        added_classes=added_classes,
        removed_classes=removed_classes,
        added_protocols=set(new.protocols) - set(old.protocols),
        removed_protocols=set(old.protocols) - set(new.protocols),
        changed_class_methods=changed_methods,
        changed_plist_keys=diff_plists(old_plist, new_plist),
    )


def render_diff(diff: AnalysisDiff) -> str:
    if not diff.has_changes:
        return "no differences found"

    lines: list[str] = []
    if diff.added_classes:
        lines.append(f"+ {len(diff.added_classes)} new class(es):")
        lines.extend(f"    {c}" for c in sorted(diff.added_classes))
    if diff.removed_classes:
        lines.append(f"- {len(diff.removed_classes)} removed class(es):")
        lines.extend(f"    {c}" for c in sorted(diff.removed_classes))
    if diff.added_protocols:
        lines.append(f"+ {len(diff.added_protocols)} new protocol(s): {', '.join(sorted(diff.added_protocols))}")
    if diff.removed_protocols:
        removed_names = ", ".join(sorted(diff.removed_protocols))
        lines.append(f"- {len(diff.removed_protocols)} removed protocol(s): {removed_names}")
    if diff.changed_class_methods:
        lines.append(f"~ {len(diff.changed_class_methods)} class(es) with method changes:")
        for cls, (added_m, removed_m) in sorted(diff.changed_class_methods.items()):
            if added_m:
                lines.append(f"    {cls}: + {', '.join(sorted(added_m))}")
            if removed_m:
                lines.append(f"    {cls}: - {', '.join(sorted(removed_m))}")
    if diff.changed_plist_keys:
        lines.append(f"~ {len(diff.changed_plist_keys)} Info.plist key(s) changed:")
        for key, (old_v, new_v) in sorted(diff.changed_plist_keys.items()):
            lines.append(f"    {key}: {old_v!r} -> {new_v!r}")
    return "\n".join(lines)
