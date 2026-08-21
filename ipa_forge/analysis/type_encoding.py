# SPDX-License-Identifier: GPL-3.0-or-later
"""Best-effort Objective-C type-encoding decoder.

Turns runtime type-encoding strings (as found on ivars, properties, and
method ``types`` fields -- see ``@encode`` in the Objective-C runtime) into
readable pseudo-header text for `class-dump`-style output. This is
deliberately not a full encoder/decoder round-trip: structs/unions render as
just their tag name (no field expansion) and bitfields fall back to the raw
encoding. Good enough to read a class-dump header; not good enough to
regenerate a compilable one.
"""

from __future__ import annotations

import re

_MODIFIERS = "rnNoORV"  # const, in, inout, out, bycopy, byref, oneway

_SIMPLE = {
    "c": "char",
    "i": "int",
    "s": "short",
    "l": "long",
    "q": "long long",
    "C": "unsigned char",
    "I": "unsigned int",
    "S": "unsigned short",
    "L": "unsigned long",
    "Q": "unsigned long long",
    "f": "float",
    "d": "double",
    "B": "BOOL",
    "v": "void",
    "*": "char *",
    "#": "Class",
    ":": "SEL",
    "?": "void /* unknown type (block/fn ptr) */",
}

_ARRAY_RE = re.compile(r"^\[(\d+)(.*)\]$")


def read_one_type(encoding: str, i: int) -> tuple[str, int]:
    """Read a single type-encoding token starting at `i`. Returns the token
    text and the index just past it -- callers use this to walk a method's
    full ``types`` string one argument at a time."""
    start = i
    while i < len(encoding) and encoding[i] in _MODIFIERS:
        i += 1
    if i >= len(encoding):
        return encoding[start:i], i
    c = encoding[i]
    if c == "@":
        i += 1
        if i < len(encoding) and encoding[i] == '"':
            end = encoding.find('"', i + 1)
            i = (end + 1) if end != -1 else len(encoding)
        return encoding[start:i], i
    if c in "{(":
        close = "}" if c == "{" else ")"
        open_c = c
        depth = 1
        i += 1
        while i < len(encoding) and depth:
            if encoding[i] == open_c:
                depth += 1
            elif encoding[i] == close:
                depth -= 1
            i += 1
        return encoding[start:i], i
    if c == "[":
        depth = 1
        i += 1
        while i < len(encoding) and depth:
            if encoding[i] == "[":
                depth += 1
            elif encoding[i] == "]":
                depth -= 1
            i += 1
        return encoding[start:i], i
    if c == "^":
        i += 1
        _, i = read_one_type(encoding, i)
        return encoding[start:i], i
    return encoding[start : i + 1], i + 1


def decode_type(encoding: str) -> str:
    """Render one type-encoding token as a readable C/Objective-C type."""
    encoding = encoding.lstrip(_MODIFIERS)
    if not encoding:
        return "?"
    c = encoding[0]
    if c in _SIMPLE:
        return _SIMPLE[c]
    if c == "@":
        if encoding.startswith('@"'):
            end = encoding.find('"', 2)
            cls = encoding[2:end] if end != -1 else ""
            if cls.startswith("<") and cls.endswith(">"):
                return f"id<{cls[1:-1]}>"
            return f"{cls} *" if cls else "id"
        return "id"
    if c == "^":
        inner = decode_type(encoding[1:])
        return inner if inner.endswith("*") else f"{inner} *"
    if c == "{":
        name = encoding[1:].split("=", 1)[0].split("}", 1)[0]
        return f"struct {name}" if name else "struct"
    if c == "(":
        name = encoding[1:].split("=", 1)[0].split(")", 1)[0]
        return f"union {name}" if name else "union"
    if c == "[":
        m = _ARRAY_RE.match(encoding)
        if m:
            count, inner = m.groups()
            return f"{decode_type(inner)}[{count}]"
    return encoding  # fallback: bitfields and anything else unrecognized


def decode_method_signature(selector: str, encoding: str) -> str:
    """Render `- (returnType)part1:(argType1)arg1 part2:(argType2)arg2` from
    a selector and its method ``types`` encoding. Falls back to an untyped
    signature (every arg as `id`) when the encoding is missing/unparseable --
    e.g. a hook target the walker found via a string cross-check rather than
    a fully decoded method list."""
    parts = selector.split(":")
    is_multi_arg = selector.endswith(":")
    arg_labels = [p for p in parts if p] if is_multi_arg else []

    if not encoding:
        if not is_multi_arg:
            return f"(id){selector}"
        return " ".join(f"{label}:(id)arg{i + 1}" for i, label in enumerate(arg_labels))

    i = 0
    ret_tok, i = read_one_type(encoding, i)
    ret = decode_type(ret_tok)
    j = i
    while j < len(encoding) and (encoding[j].isdigit() or encoding[j] == "-"):
        j += 1
    i = j

    arg_types: list[str] = []
    while i < len(encoding):
        tok, i = read_one_type(encoding, i)
        j = i
        while j < len(encoding) and (encoding[j].isdigit() or encoding[j] == "-"):
            j += 1
        i = j
        arg_types.append(tok)

    real_args = arg_types[2:]  # skip self (@) and _cmd (:)
    if not is_multi_arg:
        return f"({ret}){selector}"
    if len(real_args) != len(arg_labels):
        # types string didn't decode cleanly (e.g. truncated data) -- keep the
        # return type but fall back to untyped args rather than mismatching
        return f"({ret})" + " ".join(f"{label}:(id)arg{i + 1}" for i, label in enumerate(arg_labels))
    pieces = [
        f"{label}:({decode_type(tok)})arg{i + 1}"
        for i, (label, tok) in enumerate(zip(arg_labels, real_args, strict=True))
    ]
    return f"({ret})" + " ".join(pieces)
