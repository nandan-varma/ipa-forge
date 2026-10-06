# SPDX-License-Identifier: GPL-3.0-or-later
"""Check a hook block's C signature against the hooked method's type encoding.

A hook installed with ``imp_implementationWithBlock`` compiles no matter what
types its block declares, but the runtime calls it with the ORIGINAL method's
calling convention. A mismatch corrupts memory instead of failing loudly:

- an ``NSInteger`` argument (``q``) typed as ``id`` is retained/released by
  ARC as if it were an object pointer — a crash on first call;
- a ``BOOL``-returning method (``B``) hooked with a ``void`` block hands the
  caller whatever is left in the return register;
- an ``unsigned char`` (``C``) read as a 64-bit integer has undefined upper
  bits, so comparisons on it fail at random.

All three shipped in a real tweak and passed every existence check. This
module classifies both sides into coarse ABI categories (object, block,
integer-of-width-N, BOOL, float, void, other) and reports only combinations
that are wrong at the ABI level — never style (``id`` vs ``NSString *`` is
fine; both are object pointers).
"""

from __future__ import annotations

import re

from ipa_forge.analysis.type_encoding import read_one_type

# --- encoding side ---------------------------------------------------------------

_ENC_INT_WIDTH = {"c": 1, "C": 1, "s": 2, "S": 2, "i": 4, "I": 4, "l": 8, "L": 8, "q": 8, "Q": 8}


def _enc_kind(tok: str) -> tuple[str, int]:
    """(category, integer width) for one encoding token."""
    tok = tok.lstrip("rnNoORV")
    if not tok:
        return "other", 0
    c = tok[0]
    if tok.startswith("@?"):
        return "block", 0
    if c in "@#":
        return "object", 0
    if c == "B":
        return "bool", 1
    if c in _ENC_INT_WIDTH:
        return "integer", _ENC_INT_WIDTH[c]
    if c in "fd":
        return "float", 4 if c == "f" else 8
    if c == "v":
        return "void", 0
    return "other", 0  # SEL, pointers, structs, unions, arrays


def split_encoding(encoding: str) -> tuple[str, list[str]]:
    """Return (return token, argument tokens AFTER self and _cmd)."""
    toks: list[str] = []
    i = 0
    while i < len(encoding):
        tok, i = read_one_type(encoding, i)
        toks.append(tok)
        while i < len(encoding) and (encoding[i].isdigit() or encoding[i] == "-"):
            i += 1
    if not toks:
        return "", []
    return toks[0], toks[3:]  # ret, self, _cmd, args...


# --- source (C) side -------------------------------------------------------------

_C_INT_WIDTH = {
    "char": 1, "signed char": 1, "unsigned char": 1, "int8_t": 1, "uint8_t": 1,
    "short": 2, "unsigned short": 2, "int16_t": 2, "uint16_t": 2, "unichar": 2,
    "int": 4, "unsigned": 4, "unsigned int": 4, "int32_t": 4, "uint32_t": 4,
    "long": 8, "unsigned long": 8, "long long": 8, "unsigned long long": 8,
    "int64_t": 8, "uint64_t": 8, "size_t": 8, "ssize_t": 8, "intptr_t": 8, "uintptr_t": 8,
    "NSInteger": 8, "NSUInteger": 8,
}  # fmt: skip
_C_FLOAT = {"float": 4, "double": 8, "CGFloat": 8, "NSTimeInterval": 8}
_OBJECT_NAMES = {"id", "instancetype", "Class"}


def _c_kind(ctype: str) -> tuple[str, int]:
    t = re.sub(r"\b(const|__unsafe_unretained|__strong|__weak|__autoreleasing|_Nullable|_Nonnull|"
               r"__nullable|__nonnull|nullable|nonnull)\b", "", ctype).strip()  # fmt: skip
    t = re.sub(r"\s+", " ", t)
    if "(^" in t or t.endswith("^)"):
        return "block", 0
    if t in ("void", ""):
        return ("void", 0) if t == "void" else ("other", 0)
    if t in ("BOOL", "bool", "_Bool"):
        return "bool", 1
    if t in _C_FLOAT:
        return "float", _C_FLOAT[t]
    if t in _C_INT_WIDTH:
        return "integer", _C_INT_WIDTH[t]
    base = t.split("<", 1)[0].strip()
    if base in _OBJECT_NAMES:
        return "object", 0
    if t.endswith("*"):
        name = t[:-1].strip()
        # an ObjC class pointer (NSString *, UIView *, SPTFoo *); C pointers
        # (char *, void *, struct x *) are "other" and never flagged
        if re.fullmatch(r"[A-Z_][A-Za-z0-9_]*(<[^>]*>)?", name):
            return "object", 0
        return "other", 0
    return "other", 0  # enums/typedefs we can't size, structs


def param_type(param: str) -> str:
    """'NSData *data' -> 'NSData *'; 'void (^h)(BOOL)' -> 'void (^h)(BOOL)'."""
    p = param.strip()
    if "(^" in p:
        return p
    m = re.match(r"^(.*?[\s\*])([A-Za-z_][A-Za-z0-9_]*)$", p)
    return m.group(1).strip() if m else p


# --- comparison -------------------------------------------------------------------


def _incompatible(src: tuple[str, int], enc: tuple[str, int]) -> str | None:
    s, sw = src
    e, ew = enc
    if "other" in (s, e):
        return None  # can't judge (struct, SEL, C pointer, unsized typedef)
    pointerish = {"object", "block"}
    if s in pointerish and e in pointerish:
        return None
    if (s in pointerish) != (e in pointerish):
        return "object vs scalar"
    if s == "void" or e == "void":
        return None if s == e else "void vs value"
    if s == e == "integer" and sw != ew:
        return f"integer width {sw * 8}-bit vs {ew * 8}-bit"
    if {s, e} == {"integer", "bool"}:
        return None if sw == ew else f"integer width {sw * 8}-bit vs BOOL"
    if s != e:
        return f"{s} vs {e}"
    return None


def check_block_signature(encoding: str, block_return: str | None, block_params: list[str]) -> list[str]:
    """Problems with a hook block whose declared signature is
    ``block_return (^)(block_params...)`` hooking a method with ``encoding``.
    ``block_params`` includes the leading ``self``; ``block_return`` is None
    when the block literal omits it (inferred — not checked)."""
    if not encoding:
        return []
    ret_tok, arg_toks = split_encoding(encoding)
    issues: list[str] = []
    args = block_params[1:] if block_params else []
    if args and args[0].strip() == "void":
        args = []
    # Omitting trailing arguments is ABI-safe on arm64 (the block just never
    # reads those registers) and common in tweaks; declaring MORE reads garbage.
    if len(args) > len(arg_toks):
        issues.append(f"block declares {len(args)} argument(s) after self, method only passes {len(arg_toks)}")
    for idx, (src, tok) in enumerate(zip(args, arg_toks, strict=False), start=1):
        why = _incompatible(_c_kind(param_type(src)), _enc_kind(tok))
        if why:
            issues.append(f"argument {idx}: block declares `{param_type(src)}`, method has `{tok}` ({why})")
    if block_return is not None:
        why = _incompatible(_c_kind(block_return), _enc_kind(ret_tok))
        if why:
            issues.append(f"return: block returns `{block_return.strip()}`, method returns `{ret_tok}` ({why})")
    return issues
