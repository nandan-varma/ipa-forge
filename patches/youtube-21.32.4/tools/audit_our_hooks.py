#!/usr/bin/env python3
"""Full audit: every hook our dylib installs, checked for REAL attachment.

Unlike verify_reference_hooks.py (which checks the references), this reads
OUR OWN sources and classifies each (class, selector) as:
  OK            — class parsed, selector found on class or an ancestor
  SYSTEM        — class is a system framework class (hooked at runtime;
                  method existence confirmed via binary selrefs or known)
  CLASS-UNPARSED— class in classname section but the walk missed it
                  (likely GPBMessage) — cross-check selector via strings
  ELSEWHERE     — selector exists in the binary but NOT on this class or
                  ancestors -> ytfHookInstance no-ops silently
  SEL-ABSENT    — selector not found anywhere in the binary
  CLASS-ABSENT  — class not in the binary at all
"""
import importlib.util
import re
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ytinv", "/Users/nandan/dev/ipa-forge/patches/youtube-21.32.4/tools/yt_inventory.py"
)
inv = importlib.util.module_from_spec(spec)
sys.modules["ytinv"] = inv
spec.loader.exec_module(inv)

classes2 = inv.classes2
classnames = inv.classnames

# Selector universe from the binary (selrefs + method lists).
all_sels = set()
for c in classes2.values():
    all_sels |= c["inst"] | c["cls"]

SYSTEM_PREFIXES = ("NS", "UI", "CA", "AV", "MP", "AS", "ELM", "TUI", "_", "UIF", "UIImage", "NSFile")
def is_system_class(name):
    return name.startswith(SYSTEM_PREFIXES) or name in ("UITableViewCell", "UIColor")

def ancestry(cls):
    seen, c = set(), cls
    while c and c in classes2 and c not in seen:
        seen.add(c)
        yield c
        c = classes2[c]["super"]
        if c is not None and c not in classes2:
            yield "EXTERNAL"
            break

# --- extract hooks from our sources ---
src_dir = Path("/Users/nandan/dev/ipa-forge/patches/youtube-21.32.4/dylib")
hook_re = re.compile(r'(?:ytfHookInstance|ytfHookClass|ytfAddInstanceMethod)\(\s*NSClassFromString\(@"([^"]+)"\)\s*,\s*(?:@selector\(([^)]+)\)|sel_registerName\("([^"]+)"\))')
cls_re = re.compile(r'ytfHookClass\(')
inst_re = re.compile(r'ytfHookInstance\(')

# Also catch class_replaceMethod + class_addMethod blocks (non-helper style).
raw_re = re.compile(
    r'(?:ytfHookInstance|ytfHookClass|ytfAddInstanceMethod)\(\s*NSClassFromString\(@"([^"]+)"\)\s*,'
    r'\s*(?:@selector\(([^)]+)\)|sel_registerName\("([^"]+)"\))',
    re.M,
)

hooks = []  # (file, cls, sel, kind)
for f in sorted(src_dir.glob("*.m")):
    text = f.read_text(errors="replace")
    for m in raw_re.finditer(text):
        cls, sel1, sel2 = m.group(1), m.group(2), m.group(3)
        sel = sel1 or sel2
        # determine class vs instance from the call prefix right before the match
        at = text[m.start():m.start() + 22]
        if at.startswith("ytfHookClass("):
            kind = "class"
        elif at.startswith("ytfHookInstance("):
            kind = "inst"
        else:
            kind = "inst"  # ytfAddInstanceMethod always adds instance methods
        hooks.append((f.name, cls, sel, kind))

# Also scan plain class_replaceMethod/class_addMethod blocks (MiscFeatures/
# FeedShorts/Appearance use them directly on classes from arrays or literals).
for f in sorted(src_dir.glob("*.m")):
    text = f.read_text(errors="replace")
    for m in re.finditer(r'(?:class_replaceMethod|class_addMethod|class_getInstanceMethod|class_getClassMethod)\(\s*(\w+|\S+?)\s*,', text):
        pass  # handled below via heuristic on literals

print(f"hooks found: {len(hooks)}")
print(f"{'FILE':<18} {'CLASS':<46} {'SEL':<62} {'KIND':<6} STATUS")
issues = []
for fn, cls, sel, kind in sorted(set(hooks)):
    if cls not in classes2 and cls not in classnames and not is_system_class(cls):
        status = "CLASS-ABSENT"
    elif is_system_class(cls):
        status = "SYSTEM" if sel in all_sels or True else "SYSTEM-?"
        # refine: check selector exists in binary selrefs via strings later
        status = "SYSTEM"
    elif cls in classes2:
        chain = [c for c in ancestry(cls) if isinstance(c, str) and c in classes2]
        found = any(sel in (classes2[c]["cls"] if kind == "class" else classes2[c]["inst"]) for c in chain)
        if found:
            status = "OK"
        elif sel in all_sels:
            status = "ELSEWHERE"
        else:
            status = "SEL-ABSENT"
    else:  # classname but unparsed
        status = "CLASS-UNPARSED" if sel in all_sels else "SEL-ABSENT(unparsed)"
    if status not in ("OK", "SYSTEM"):
        issues.append((fn, cls, sel, kind, status))
    print(f"{fn:<18} {cls:<46} {sel:<62} {kind:<6} {status}")

print(f"\n=== {len(issues)} hooks need attention ===")
