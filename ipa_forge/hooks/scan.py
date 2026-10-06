# SPDX-License-Identifier: GPL-3.0-or-later
"""Scan ObjC tweak sources for runtime hook calls.

Recognizes ``<prefix>HookInstance/HookClass/AddInstanceMethod`` calls with an
inline ``NSClassFromString(@"X")`` (or a file-scoped, unambiguous
``cls = NSClassFromString(@"X")`` assignment), plus class names passed
through a resolver helper — any function whose body calls
``NSClassFromString``, defined in any scanned file, and invoked as
``resolver("X")`` at the hook call site (e.g.
``myHookInstance(myClass("SomeClass"), ...)``) or assigned to a variable
(``cls = myClass("SomeClass")``).

Helper/loop-based hooks whose class is *passed into another function* before
reaching the hook call (``resolverHelper(myClass("X"))`` → ``myHookInstance(cls,
...)`` inside ``resolverHelper``) are not traced across function boundaries —
declare those manually in the definition's ``hooks:`` block, exactly as the
docs say.
"""

from __future__ import annotations

import re
from pathlib import Path

from ipa_forge.hooks.verify import HookDecl

_PATTERN = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)?(?:Hook(Instance|Class|ConfigBool)|AddInstanceMethod)"
    r"\("
    r"\s*(?:NSClassFromString\(@?\"([^\"]+)\"\)|\[\s*(\w+)\s*class\]|(\w+)|(\w+)\(@?\"([^\"]+)\"\))"
    r"\s*,\s*(?:@selector\(([^)]+)\)|sel_registerName\(\"([^\"]+)\"\))"
)
# ``var = fn(@"X")`` — counted when fn is NSClassFromString or a resolver.
_VAR_RE = re.compile(r"(\w+)\s*=\s*(\w+)\(@?\"([^\"]+)\"\)")
# A class-resolver helper: a function returning Class whose body calls
# NSClassFromString before any nested block. Calls like ``resolver("X")``
# resolve X to a class name at the hook call site.
_RESOLVER_RE = re.compile(r"(?:\bstatic\s+)?Class\s+(\w+)\s*\([^)]*\)\s*\{[^{}]*NSClassFromString")


def _split_top_level(params: str) -> list[str]:
    """Split a parameter list on commas outside nested ()/<> (block-typed
    params like ``void (^done)(BOOL, NSError *)`` contain commas)."""
    out: list[str] = []
    depth = 0
    cur = ""
    for ch in params:
        if ch in "(<":
            depth += 1
        elif ch in ")>":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_block_literal(text: str, pos: int) -> tuple[str | None, list[str]] | None:
    """Parse ``, ^ret(params) {`` starting at ``pos`` (just after a hook
    call's selector argument). Returns (return type or None, params) or None
    when the next argument is not an inline block literal."""
    m = re.match(r"\s*,\s*\^\s*", text[pos:])
    if not m:
        return None
    i = pos + m.end()
    paren = text.find("(", i)
    brace = text.find("{", i)
    if paren == -1 or (brace != -1 and brace < paren):
        return None  # ^{ ... } -- no parameter list
    ret = text[i:paren].strip() or None
    if ret is not None and not re.fullmatch(r"[A-Za-z_][\w\s\*<>]*", ret):
        return None
    depth = 0
    j = paren
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    else:
        return None
    return ret, _split_top_level(text[paren + 1 : j])


def scan_hook_sources(dylib_src: Path) -> list[HookDecl]:
    """Scan ``*.m`` files under ``dylib_src`` and return hook declarations."""
    decls: list[HookDecl] = []
    sources = {f: f.read_text(errors="replace") for f in sorted(dylib_src.glob("*.m"))}
    # resolver helpers are collected across every file: a shared resolver is
    # typically defined once (declared in a header) and used everywhere
    resolvers = {"NSClassFromString"}
    for text in sources.values():
        resolvers.update(m.group(1) for m in _RESOLVER_RE.finditer(text))
    for text in sources.values():
        # map NSClassFromString assignments to their variable (file-scoped),
        # only when unambiguous (a var assigned two different classes is
        # untrustworthy — skip it)
        var_class: dict[str, str] = {}
        var_classes: dict[str, set[str]] = {}
        for m in _VAR_RE.finditer(text):
            if m.group(2) in resolvers:
                var_classes.setdefault(m.group(1), set()).add(m.group(3))
        for var, classes in var_classes.items():
            if len(classes) == 1:
                var_class[var] = next(iter(classes))

        for m in _PATTERN.finditer(text):
            _prefix, kind, cls, cls2, clsvar, clsfn, clsarg, sel, sel2 = m.groups()
            is_add = kind is None  # AddInstanceMethod branch
            via_resolver = clsarg if clsfn in resolvers else ""
            cls = cls or cls2 or var_class.get(clsvar or "") or via_resolver
            sel = sel or sel2
            if not cls or not sel:
                continue
            hook_kind = "class" if kind == "Class" else "instance"  # ConfigBool hooks the getter -> instance
            block = parse_block_literal(text, m.end())
            decls.append(
                HookDecl(
                    cls,
                    sel,
                    hook_kind,  # type: ignore[arg-type]
                    added=is_add,
                    block_return=block[0] if block else None,
                    block_params=block[1] if block else None,
                )
            )

    # de-duplicate, keep first-seen order
    seen: set[tuple[str, str]] = set()
    unique: list[HookDecl] = []
    for d in decls:
        if (d.class_name, d.selector) in seen:
            continue
        seen.add((d.class_name, d.selector))
        unique.append(d)
    return unique
