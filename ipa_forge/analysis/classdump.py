# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a `MachOAnalysis` as `.h`-style class-dump text: `@interface`,
`@protocol`, and `@interface (Category)` blocks with method signatures,
ivars, and properties -- the general-purpose reverse-engineering view built
on the same class table `ipa_forge.hooks` uses for hook verification.
"""

from __future__ import annotations

from ipa_forge.analysis.type_encoding import decode_method_signature, decode_type, read_one_type
from ipa_forge.machO.objc import MachOAnalysis, MachOCategory, MachOClass, MachOProtocol


def _method_lines(methods: dict[str, str], prefix: str) -> list[str]:
    return [f"{prefix} {decode_method_signature(sel, enc)};" for sel, enc in sorted(methods.items())]


def _decl(type_str: str, name: str) -> str:
    """`Type name;` for a value type, `Type *name;` for a pointer type --
    decode_type() already renders the trailing `*`, so avoid a stray space
    between it and the identifier."""
    sep = "" if type_str.endswith("*") else " "
    return f"{type_str}{sep}{name}"


def render_class(cls: MachOClass) -> str:
    conforms = f" <{', '.join(sorted(cls.protocols))}>" if cls.protocols else ""
    header = f"@interface {cls.name} : {cls.super_name or 'NSObject'}{conforms}"
    lines = [header]

    if cls.ivars:
        lines.append("{")
        for iv in cls.ivars:
            lines.append(f"    {_decl(decode_type(iv.type_encoding), iv.name)};")
        lines.append("}")

    for prop in cls.properties:
        # attribute string: "T<type-encoding>,<flag>,<flag>,..." (e.g.
        # 'T@"NSString",C,N,V_label') -- a naive split(",") would break on a
        # comma inside a generic-collection class name, so tokenize the type
        # encoding itself rather than string-splitting the whole attribute.
        type_enc = prop.attributes[1:] if prop.attributes.startswith("T") else prop.attributes
        tok, _ = read_one_type(type_enc, 0) if type_enc else ("", 0)
        decoded = decode_type(tok) if tok else "id"
        lines.append(f"@property {_decl(decoded, prop.name)}; // {prop.attributes}")

    if cls.properties and (cls.inst or cls.cls):
        lines.append("")

    lines.extend(_method_lines(cls.cls, "+"))
    lines.extend(_method_lines(cls.inst, "-"))

    lines.append("")
    lines.append("@end")
    return "\n".join(lines)


def render_protocol(proto: MachOProtocol) -> str:
    conforms = f" <{', '.join(sorted(proto.protocols))}>" if proto.protocols else ""
    lines = [f"@protocol {proto.name}{conforms}"]
    lines.extend(_method_lines(proto.cls, "+"))
    lines.extend(_method_lines(proto.inst, "-"))
    if proto.opt_cls or proto.opt_inst:
        lines.append("@optional")
        lines.extend(_method_lines(proto.opt_cls, "+"))
        lines.extend(_method_lines(proto.opt_inst, "-"))
    lines.append("@end")
    return "\n".join(lines)


def render_category(cat: MachOCategory) -> str:
    lines = [f"@interface {cat.class_name} ({cat.name})"]
    lines.extend(_method_lines(cat.cls, "+"))
    lines.extend(_method_lines(cat.inst, "-"))
    lines.append("@end")
    return "\n".join(lines)


def render_analysis(
    analysis: MachOAnalysis,
    *,
    class_filter: str | None = None,
    search: str | None = None,
) -> str:
    """Render every class/protocol/category in `analysis` as class-dump text,
    optionally restricted to one class name or a substring/regex search over
    class names (matches `forge hooks extract`'s --class/--search)."""
    import re as _re

    classes = sorted(analysis.classes.values(), key=lambda c: c.name)
    if class_filter:
        classes = [c for c in classes if c.name == class_filter]
    elif search:
        pat = _re.compile(search)
        classes = [c for c in classes if pat.search(c.name)]

    blocks: list[str] = []
    if not class_filter and not search:
        blocks.extend(render_protocol(p) for p in sorted(analysis.protocols.values(), key=lambda p: p.name))
    blocks.extend(render_class(c) for c in classes)
    if not class_filter and not search:
        blocks.extend(render_category(cat) for cat in sorted(analysis.categories, key=lambda c: (c.class_name, c.name)))
    return "\n\n".join(blocks)
