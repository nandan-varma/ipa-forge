# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook verification: classify each declared hook against a MachOAnalysis.

Statuses:

- ``ok`` — class parsed and selector found on the class or an ancestor.
- ``ok-system`` — class is a system-framework class (not in the app's
  classlist) and the selector is referenced somewhere in the app binary.
- ``added`` — declared ``added: true`` (the tweak adds the method); absence
  is the expected state and counts as a pass.
- ``missing-class`` — class absent from the app entirely (renamed/removed).
- ``missing-selector`` — class present but the selector is nowhere in the
  binary: the hook would attach but never fire.
- ``elsewhere`` — selector exists in the binary but not on this class or its
  ancestors: the hook would silently no-op on this class.

``required`` hooks that resolve to a failure status fail the run; the rest
are reported as warnings so porting to a new version is guided, not blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ipa_forge.machO.objc import MachOAnalysis, contains_string

HookStatus = Literal[
    "ok",
    "ok-system",
    "ok-inherited",
    "added",
    "missing-class",
    "missing-selector",
    "elsewhere",
    "referenced-only",
    "unverified",
]

_SYSTEM_PREFIXES = ("NS", "UI", "CA", "AV", "MP", "CF", "CG", "SK", "_", "TUI")

# Selectors hooks commonly target that are defined on system superclasses
# (UIView/UIButton/UIViewController etc.) — not visible in the app's class
# method lists, but inherited at runtime, so the hook attaches fine.
_SYSTEM_SELECTORS = {
    "init",
    "dealloc",
    "layoutSubviews",
    "didMoveToWindow",
    "viewDidAppear:",
    "viewDidLoad",
    "viewDidDisappear:",
    "setHidden:",
    "setFrame:",
    "setBackgroundColor:",
    "setEnabled:",
    "sizeThatFits:",
    "titleLabel",
    "setTitle:forState:",
    "addGestureRecognizer:",
    "setDelegate:",
    "setUserInteractionEnabled:",
    "setAlpha:",
    "setNeedsLayout",
    "removeFromSuperview",
    "setText:",
    "setOn:",
    "setAccessibilityIdentifier:",
    "setValue:forKey:",
    "didMoveToSuperview",
}


@dataclass
class HookDecl:
    class_name: str
    selector: str
    kind: Literal["instance", "class"] = "instance"
    added: bool = False
    required: bool = False


@dataclass
class HookResult:
    class_name: str
    selector: str
    kind: Literal["instance", "class"]
    status: HookStatus
    detail: str = ""
    required: bool = False

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "ok-system", "ok-inherited", "added")


def _is_system_class(name: str) -> bool:
    return name.startswith(_SYSTEM_PREFIXES) or name in (
        "UITableViewCell",
        "UIColor",
        "UIFont",
        "UIWindow",
        "UIView",
        "UIViewController",
    )


def _ancestry(analysis: MachOAnalysis, name: str) -> list[str]:
    chain: list[str] = []
    seen: set[str] = set()
    cur: str | None = name
    while cur and cur in analysis.classes and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = analysis.classes[cur].super_name
        if cur is None:
            break
    return chain


def verify_hooks(analysis: MachOAnalysis, hooks: list[HookDecl]) -> list[HookResult]:
    results: list[HookResult] = []
    for hook in hooks:
        cls = hook.class_name
        sel = hook.selector
        mc = analysis.classes.get(cls)

        if hook.added:
            # The tweak ADDS the method. If the binary references the selector
            # (selrefs) but no class implements it, the app is calling into a
            # hole that this add fills — exactly the intended state.
            if sel in analysis.selectors:
                results.append(
                    HookResult(
                        cls, sel, hook.kind, "ok", "app references this selector; the tweak provides it", hook.required
                    )
                )
            else:
                results.append(
                    HookResult(
                        cls, sel, hook.kind, "added", "method added by the tweak; absence expected", hook.required
                    )
                )
            continue

        if mc is None:
            if cls in analysis.classnames:
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "unverified",
                        "class exists (classname section) but the walk missed it (likely attaches)",
                        hook.required,
                    )
                )
            elif cls.startswith("_Tt"):
                # Swift-mangled class absent from the parsed table. Not a
                # system class — labelling it ok-system would hide drift. The
                # hook may well attach (the walk misses Swift classes too), so
                # report honestly instead.
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "unverified",
                        "Swift class not in the parsed class table (mangled name; the walk missed it)",
                        hook.required,
                    )
                )
            elif _is_system_class(cls):
                if sel in analysis.selectors or sel in _SYSTEM_SELECTORS:
                    results.append(
                        HookResult(
                            cls,
                            sel,
                            hook.kind,
                            "ok-system",
                            "system class; selector referenced by the app or a known system API",
                            hook.required,
                        )
                    )
                else:
                    results.append(
                        HookResult(
                            cls,
                            sel,
                            hook.kind,
                            "unverified",
                            "system class; selector not referenced by the app binary",
                            hook.required,
                        )
                    )
            else:
                if contains_string(analysis, cls):
                    # The name exists as a standalone cstring in some image but
                    # the class-table walk missed it — a parser gap, not a
                    # rename. Soft-fail instead of calling it missing.
                    results.append(
                        HookResult(
                            cls,
                            sel,
                            hook.kind,
                            "unverified",
                            "class-name string present in a binary image but the class-table walk missed "
                            "it (likely attaches)",
                            hook.required,
                        )
                    )
                else:
                    results.append(
                        HookResult(cls, sel, hook.kind, "missing-class", "class not found in the binary", hook.required)
                    )
            continue

        # class present — walk the ancestry for the selector
        chain = _ancestry(analysis, cls)
        pool = "cls" if hook.kind == "class" else "inst"
        found = False
        found_at: str | None = None
        for ancestor in chain:
            methods = getattr(analysis.classes[ancestor], pool)
            if sel in methods:
                found = True
                found_at = ancestor
                break
        if found:
            if found_at == cls:
                results.append(HookResult(cls, sel, hook.kind, "ok", f"on {cls}", hook.required))
            else:
                results.append(
                    HookResult(cls, sel, hook.kind, "ok-inherited", f"inherited from {found_at}", hook.required)
                )
            continue

        # Not in the parsed hierarchy. Two soft cases before we call it broken:
        # (a) a system superclass method (UIView etc.) — attaches via inheritance;
        # (b) the selector exists in the binary but the parser missed the method
        #     list entry (chained-fixup decode gaps) — likely on this class.
        chain_classes = [analysis.classes[c] for c in chain]
        ends_in_system = any(
            (c.super_name == "«external»" or (c.super_name or "").startswith(("NS", "UI"))) for c in chain_classes
        )
        if sel in _SYSTEM_SELECTORS and ends_in_system:
            results.append(
                HookResult(
                    cls,
                    sel,
                    hook.kind,
                    "ok-inherited",
                    "system superclass method (attaches via inheritance)",
                    hook.required,
                )
            )
            continue
        if sel in analysis.selectors:
            pool_of = "cls" if hook.kind == "class" else "inst"
            parsed_anywhere = any(sel in getattr(c, pool_of) for c in analysis.classes.values())
            if parsed_anywhere:
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "elsewhere",
                        "selector exists in the binary but not on this class/ancestors (hook would no-op)",
                        hook.required,
                    )
                )
            elif sel in analysis.methnames:
                # Declared as a method name somewhere (a protocol, category or a
                # method list the walker did not decode) — the hook may well
                # attach; keep it soft.
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "unverified",
                        "selector declared as a method somewhere (protocol/category/undecoded list) "
                        "but not in any parsed class method list (likely attaches)",
                        hook.required,
                    )
                )
            else:
                # Referenced (NSSelectorFromString/performSelector/optional
                # protocol sends) but declared as NO method anywhere in the
                # binary — no IMP exists to swizzle, so class_getInstanceMethod
                # returns NULL and the hook cannot attach.
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "referenced-only",
                        "selector referenced by the binary but not declared as a method anywhere "
                        "(no IMP to swizzle; the hook cannot attach unless a system superclass provides it)",
                        hook.required,
                    )
                )
        else:
            if contains_string(analysis, sel):
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "unverified",
                        "selector string present in a binary image but not in any parsed method list "
                        "(parser may have missed it)",
                        hook.required,
                    )
                )
            else:
                results.append(
                    HookResult(
                        cls,
                        sel,
                        hook.kind,
                        "missing-selector",
                        "selector not found anywhere in the binary",
                        hook.required,
                    )
                )
    return results


def failing(results: list[HookResult]) -> list[HookResult]:
    return [r for r in results if not r.ok]
