# SPDX-License-Identifier: GPL-3.0-or-later
"""Scan ObjC tweak sources for runtime hook calls.

Recognizes ``<prefix>HookInstance/HookClass/AddInstanceMethod`` calls with an
inline ``NSClassFromString(@"X")`` (or a file-scoped, unambiguous
``cls = NSClassFromString(@"X")`` assignment), plus class names passed
through a local resolver helper — any function whose body calls
``NSClassFromString`` and that is invoked as ``resolver("X")`` at the hook
call site (e.g. ``igHookInstance(igClass("YTSettings"), ...)``).

Helper/loop-based hooks whose class is *passed into another function* before
reaching the hook call (``hookParserNil(igClass("X"))`` → ``igHookInstance(cls,
...)`` inside ``hookParserNil``) are not traced across function boundaries —
declare those manually in the definition's ``hooks:`` block, exactly as the
docs say.
"""

from __future__ import annotations

import re
from pathlib import Path

from ipa_forge.hooks.verify import HookDecl

_PATTERN = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)?(?:Hook(Instance|Class)|AddInstanceMethod)"
    r"\("
    r"\s*(?:NSClassFromString\(@?\"([^\"]+)\"\)|\[\s*(\w+)\s*class\]|(\w+)|(\w+)\(@?\"([^\"]+)\"\))"
    r"\s*,\s*(?:@selector\(([^)]+)\)|sel_registerName\(\"([^\"]+)\"\))"
)
_VAR_RE = re.compile(r"(\w+)\s*=\s*NSClassFromString\(@?\"([^\"]+)\"\)")
# A class-resolver helper: a function returning Class whose body calls
# NSClassFromString (simple single-expression bodies). Calls like
# ``resolver("X")`` resolve X to a class name at the hook call site.
_RESOLVER_RE = re.compile(r"(?:\bstatic\s+)?Class\s+(\w+)\s*\([^)]*\)\s*\{[^{}]*NSClassFromString")
_RESOLVER_CALL_RE = re.compile(r"(\w+)\s*\(\s*@?\"([^\"]+)\"\s*\)")


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

        # resolver helpers: functions whose body calls NSClassFromString
        resolvers = {m.group(1) for m in _RESOLVER_RE.finditer(text)}
        resolver_class: dict[str, str] = {}
        if resolvers:
            for m in _RESOLVER_CALL_RE.finditer(text):
                if m.group(1) in resolvers:
                    resolver_class[m.group(1)] = m.group(2)

        for m in _PATTERN.finditer(text):
            _prefix, kind, cls, cls2, clsvar, clsfn, clsarg, sel, sel2 = m.groups()
            is_add = kind is None  # AddInstanceMethod branch
            cls = cls or cls2 or var_class.get(clsvar or "") or (resolver_class.get(clsfn or "") if clsfn else "")
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
