#!/usr/bin/env python3
"""Verify every %hook target from reference tweaks against the 21.32.4 binary.

Reuses yt_inventory.py's binary parsing (imported as a module; it builds
`classes2` at import time against BIN=/tmp/verify/...). Extracts
(class, selector, is_class_method, source_file) from all reference .x files
and reports which targets exist in the 21.32.4 binary.
"""
import importlib.util
import re
import sys
from pathlib import Path

BIN = "/tmp/verify/Payload/YouTube.app/YouTube"
spec = importlib.util.spec_from_file_location(
    "ytinv", "/Users/nandan/dev/ipa-forge/patches/youtube-21.32.4/tools/yt_inventory.py"
)
inv = importlib.util.module_from_spec(spec)
sys.modules["ytinv"] = inv
spec.loader.exec_module(inv)

classes2 = inv.classes2
classnames = inv.classnames


def ancestry(class_name):
    seen = set()
    c = class_name
    ext = False
    while c and c in classes2 and c not in seen:
        seen.add(c)
        yield c
        c = classes2[c]["super"]
        if c is not None and c not in classes2:
            ext = True
            break
    if ext:
        yield "EXTERNAL"


def method_exists(cls, sel, is_cls):
    if cls not in classes2:
        return "class-absent" if cls not in classnames else "class-unparsed"
    chain = [c for c in ancestry(cls) if isinstance(c, str) and c in classes2]
    found = any(sel in classes2[c]["cls"] if is_cls else sel in classes2[c]["inst"] for c in chain)
    if found:
        return "ok"
    any_inst = set().union(*[c["inst"] for c in classes2.values()]) if classes2 else set()
    any_cls = set().union(*[c["cls"] for c in classes2.values()]) if classes2 else set()
    pool = any_cls if is_cls else any_inst
    return "sel-elsewhere" if sel in pool else "sel-absent"


# --- extract hooks from all reference .x files ---
SOURCES = [
    ("youmod", "/tmp/youmod-src/Files"),
    ("ytlite", "/Users/nandan/dev/ytlite-ipa/YTLite"),
]
hook_re = re.compile(r"%hook\s+(\w+)")
method_re = re.compile(r"^([-+])\s*\([^)]*\)\s*([A-Za-z_][A-Za-z0-9_]*)")

targets = []  # (src, file, cls, sel, is_cls, is_new, has_orig)
for src, base in SOURCES:
    for f in sorted(Path(base).glob("*.x")):
        text = f.read_text(errors="replace")
        for m in hook_re.finditer(text):
            cls = m.group(1)
            end = text.find("%end", m.end())
            block = text[m.end(): end if end != -1 else len(text)]
            lines = block.splitlines()
            is_new = False
            i = 0
            while i < len(lines):
                ls = lines[i].strip()
                if ls.startswith("%new"):
                    is_new = True
                    i += 1
                    continue
                mm = re.match(r"^([-+])\s*\(", ls)
                if mm:
                    had_brace = "{" in ls
                    sig = ls.split("{")[0]  # inline bodies confound selector parsing
                    if not had_brace:
                        while not sig.rstrip().endswith(";"):
                            i += 1
                            if i >= len(lines):
                                break
                            nxt = lines[i].strip()
                            if re.match(r"^[-+]\s*\(", nxt) or nxt.startswith("%"):
                                break
                            sig += " " + nxt
                    parts = re.sub(r"[{};]", "", sig).strip()
                    m2 = re.match(r"^[-+]\s*\([^)]*\)\s*([A-Za-z_][A-Za-z0-9_]*)", parts)
                    if m2:
                        # selector = method name + every word that ends in ':'
                        # ("decorateContext:(id)c" -> "decorateContext:")
                        words = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", parts)
                        sel = ":".join(words) + ":" if words else m2.group(1)
                        targets.append((src, f.name, cls, sel, mm.group(1) == "+", is_new,
                                        "%orig" in block, block.count("\n") + 1))
                    is_new = False
                i += 1

# --- report ---
rows = []
for src, fn, cls, sel, is_cls, is_new, has_orig, nlines in targets:
    status = "new" if is_new else method_exists(cls, sel, is_cls)
    rows.append((src, fn, cls, sel, "class" if is_cls else "inst", status, has_orig, nlines))

# Summary per status
from collections import Counter
cnt = Counter(r[5] for r in rows)
print(f"total hook methods: {len(rows)}  status: {dict(cnt)}")
print()

# Missing/absent targets grouped by file
print("=== targets that need attention (not 'ok'/'new') ===")
for src, fn, cls, sel, kind, status, has_orig, nlines in sorted(rows):
    if status not in ("ok", "new"):
        print(f"  [{src}/{fn}] {cls} {'+' if kind=='class' else '-'}[{sel}] -> {status}")

# Class-level absence for %hook classes not in binary at all
hook_classes = {r[2] for r in rows}
absent_classes = sorted(c for c in hook_classes if c not in classes2 and c not in classnames)
print(f"\n=== %hook classes entirely absent from 21.32.4 ({len(absent_classes)}) ===")
print("  " + ", ".join(absent_classes))
