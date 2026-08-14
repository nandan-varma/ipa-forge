# SPDX-License-Identifier: GPL-3.0-or-later
"""Scan ObjC tweak sources for runtime hook calls.

Recognizes any ``<prefix>HookInstance/HookClass/AddInstanceMethod`` call with
an inline ``NSClassFromString(@"X")`` (or a file-scoped, unambiguous
``cls = NSClassFromString(@"X")`` assignment). Helper/loop-based hooks (a
class passed as a parameter, or a ``for (NSString *sel in @[...])`` swizzle
loop) are not traced — declare those manually in the definition's ``hooks:``
block.
"""

from __future__ import annotations

import re
from pathlib import Path

from ipa_forge.hooks.verify import HookDecl

_PATTERN = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)?(?:Hook(Instance|Class)|AddInstanceMethod)"
    r"\("
    r"\s*(?:NSClassFromString\(@?\"([^\"]+)\"\)|\[\s*(\w+)\s*class\]|(\w+))"
    r"\s*,\s*(?:@selector\(([^)]+)\)|sel_registerName\(\"([^\"]+)\"\))"
)
_VAR_RE = re.compile(r"(\w+)\s*=\s*NSClassFromString\(@?\"([^\"]+)\"\)")


def scan_hook_sources(dylib_src: Path) -> list[HookDecl]:
    """Scan ``*.m`` files under ``dylib_src`` and return hook declarations."""
    decls: list[HookDecl] = []
    for f in sorted(dylib_src.glob("*.m")):
        text = f.read_text(errors="replace")
        # map NSClassFromString assignments to their variable (file-scoped),
        # only when unambiguous (a var assigned two different classes is
        # untrustworthy — skip it)
        var_class: dict[str, str] = {}
        var_classes: dict[str, set[str]] = {}
        for m in _VAR_RE.finditer(text):
            var_classes.setdefault(m.group(1), set()).add(m.group(2))
        for var, classes in var_classes.items():
            if len(classes) == 1:
                var_class[var] = next(iter(classes))

        for m in _PATTERN.finditer(text):
            _prefix, kind, cls, cls2, clsvar, sel, sel2 = m.groups()
            is_add = kind is None  # AddInstanceMethod branch
            cls = cls or cls2 or var_class.get(clsvar or "")
            sel = sel or sel2
            if not cls or not sel:
                continue
            hook_kind = "class" if kind == "Class" else "instance"
            decls.append(HookDecl(cls, sel, hook_kind, added=is_add))  # type: ignore[arg-type]

    # de-duplicate, keep first-seen order
    seen: set[tuple[str, str]] = set()
    unique: list[HookDecl] = []
    for d in decls:
        if (d.class_name, d.selector) in seen:
            continue
        seen.add((d.class_name, d.selector))
        unique.append(d)
    return unique
