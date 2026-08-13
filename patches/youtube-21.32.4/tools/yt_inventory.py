#!/usr/bin/env python3
"""Definitive checks against YouTube 21.32.4: class existence (from __objc_classname)
and per-class method lists (selref two-level decode). Prints compact reports."""
import struct, subprocess, re, sys

BIN = "/tmp/verify/Payload/YouTube.app/YouTube"
SRC = "/Users/nandan/dev/ytlite-ipa/YTLite"

out = subprocess.run(["otool", "-l", BIN], capture_output=True, text=True).stdout
seg_bases = [int(l.split()[1], 16) for l in out.splitlines() if l.strip().startswith("vmaddr 0x")]
IB = min(b for b in seg_bases if b)
sections = {}
cur = None
for line in out.splitlines():
    s = line.strip()
    if s.startswith("sectname "):
        cur = s.split()[1]
    elif s.startswith("addr 0x") and cur:
        addr = int(s.split()[1], 16)
    elif s.startswith("size 0x") and cur:
        size = int(s.split()[1], 16)
    elif s.startswith("offset ") and cur:
        sections[cur] = (addr, size, int(s.split()[1], 10))
        cur = None
data = open(BIN, "rb").read()

def vm2off(a):
    for n, (va, sz, fo) in sections.items():
        if va <= a < va + sz:
            return fo + (a - va)
    return None

def rd64(a):
    o = vm2off(a)
    return struct.unpack_from("<Q", data, o)[0] if o is not None and o + 8 <= len(data) else None

def cstr(a):
    o = vm2off(a)
    if o is None:
        return None
    e = data.find(b"\x00", o)
    if e <= o or e - o > 4000:
        return None
    try:
        return data[o:e].decode("utf-8")
    except Exception:
        return None

def chained(raw):
    if raw is None:
        return ("none", None)
    if raw >> 32 == 0:
        return ("plain", raw)
    if raw & (1 << 63):
        return ("bind", None)
    return ("rebase", (raw & 0xFFFFFFFFF) + IB)

# --- classname section (definitive existence) ---
a, sz, o = sections["__objc_classname"]
classnames = set()
for s in data[o:o + sz].split(b"\x00"):
    if s:
        classnames.add(s.decode("utf-8", "replace"))

# --- full class walk (superclass + methods) ---
classes = {}
a, sz, o = sections["__objc_classlist"]
for i in range(sz // 8):
    raw = struct.unpack_from("<Q", data, o + i * 8)[0]
    if raw >> 32 == 0 or raw & (1 << 63):
        continue
    p = (raw & 0xFFFFFFFFF) + IB
    dk, dp = chained(rd64(p + 32))
    if dk != "rebase" or not dp:
        continue
    nk, np = chained(rd64(dp + 24))
    if nk != "rebase" or not np:
        continue
    name = cstr(np)
    if not name:
        continue
    sk, sp = chained(rd64(p + 8))
    super_name = None
    if sk == "rebase" and sp:
        sdk, sdp = chained(rd64(sp + 32))
        if sdk == "rebase" and sdp:
            snk, snp = chained(rd64(sdp + 24))
            if snk == "rebase" and snp:
                super_name = cstr(snp)
    elif sk == "bind":
        super_name = "«external»"
    classes[name] = {"super": super_name, "inst": set(), "cls": set()}

def parse_methods(list_raw):
    lk, lp = chained(list_raw)
    if lk != "rebase" or not lp:
        return set()
    eaf = struct.unpack_from("<I", data, vm2off(lp))[0] if vm2off(lp) else None
    if eaf is None:
        return set()
    entsize = eaf & 0xFFFF or eaf & 0x3FFFFF
    REL = bool(eaf & 0x80000000)
    o = vm2off(lp)
    count = struct.unpack_from("<I", data, o + 4)[0] if o else 0
    if count is None or count > 5_000_000:
        return set()
    base = lp + 8
    s = set()
    for i in range(count):
        e = base + i * entsize
        eo = vm2off(e)
        if eo is None or eo + 12 > len(data):
            break
        if REL and entsize == 12:
            rel = struct.unpack_from("<i", data, eo)[0]
            sk, sp = chained(rd64(e + rel))
            sel = cstr(sp) if sp else None
        elif not REL:
            sel = cstr(rd64(e))
        else:
            continue
        if sel:
            s.add(sel)
    return s

# rebuild with ptr kept
classes2 = {}
a, sz, o = sections["__objc_classlist"]
for i in range(sz // 8):
    raw = struct.unpack_from("<Q", data, o + i * 8)[0]
    if raw >> 32 == 0 or raw & (1 << 63):
        continue
    p = (raw & 0xFFFFFFFFF) + IB
    dk, dp = chained(rd64(p + 32))
    if dk != "rebase" or not dp:
        continue
    nk, np = chained(rd64(dp + 24))
    if nk != "rebase" or not np:
        continue
    name = cstr(np)
    if not name:
        continue
    sk, sp = chained(rd64(p + 8))
    super_name = None
    if sk == "rebase" and sp:
        sdk, sdp = chained(rd64(sp + 32))
        if sdk == "rebase" and sdp:
            snk, snp = chained(rd64(sdp + 24))
            if snk == "rebase" and snp:
                super_name = cstr(snp)
    elif sk == "bind":
        super_name = "«external»"
    classes2[name] = {"super": super_name, "ptr": p, "inst": set(), "cls": set()}

for name, c in classes2.items():
    dp_ = None
    dk, dp_ = chained(rd64(c["ptr"] + 32))
    if dp_:
        c["inst"] = parse_methods(rd64(dp_ + 32))
    ik, ip_ = chained(rd64(c["ptr"]))
    if ip_:
        mdk, mdp_ = chained(rd64(ip_ + 32))
        if mdp_:
            c["cls"] = parse_methods(rd64(mdp_ + 32))

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

mode = sys.argv[1] if len(sys.argv) > 1 else "summary"

if mode == "summary":
    hook_re = re.compile(r"%hook\s+(\w+)")
    files = ["YTLite.x", "Settings.x", "YTNativeShare.x", "Sideloading.x"]
    hooks = []
    for fn in files:
        text = open(SRC + "/" + fn).read()
        for m in hook_re.finditer(text):
            cls = m.group(1)
            end = text.find("%end", m.end())
            block = text[m.end():end if end != -1 else len(text)]
            lines = block.splitlines()
            is_new = False
            i = 0
            while i < len(lines):
                ls = lines[i].strip()
                if ls == "%new":
                    is_new = True
                    i += 1
                    continue
                mm = re.match(r"^([-+])\s*\(", ls)
                if mm:
                    sig = ls
                    while "{" not in sig and not sig.rstrip().endswith(";"):
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
                        sel = m2.group(1)
                        for tok in re.findall(r"[\w]+\s*:", parts[m2.end():]):
                            sel += ":"
                        hooks.append((fn, cls, sel, mm.group(1) == "+", is_new, "%orig" in block))
                    is_new = False
                i += 1
    any_inst = set().union(*[c["inst"] for c in classes2.values()]) if classes2 else set()
    any_cls = set().union(*[c["cls"] for c in classes2.values()]) if classes2 else set()

    print(f"classes: {len(classes2)}  (classname strings: {len(classnames)})  inst={len(any_inst)} cls={len(any_cls)}")
    by_class = {}
    ok_c = miss_c = 0
    for fn, cls, sel, is_cls, is_new, has_orig in hooks:
        if is_new:
            by_class.setdefault(cls, {"ok": [], "miss": [], "missing_class": False, "new": 0})["new"] += 1
            continue
        if cls not in classes2:
            # definitive check
            if cls in classnames:
                by_class.setdefault(cls, {"ok": [], "miss": [], "missing_class": True, "new": 0})
                by_class[cls]["miss"].append((sel, "class-in-classname-but-not-parsed"))
                miss_c += 1
            else:
                by_class.setdefault(cls, {"ok": [], "miss": [], "missing_class": True, "new": 0})
                by_class[cls]["miss"].append((sel, "class-absent"))
                miss_c += 1
            continue
        chain = [c for c in ancestry(cls) if isinstance(c, str) and c in classes2]
        found = any(sel in classes2[c]["cls"] if is_cls else sel in classes2[c]["inst"] for c in chain)
        ext = "EXTERNAL" in list(ancestry(cls))
        if not found and ext and (sel in (any_cls if is_cls else any_inst)):
            found = True
        e = by_class.setdefault(cls, {"ok": [], "miss": [], "missing_class": False, "new": 0})
        if found:
            e["ok"].append(sel); ok_c += 1
        else:
            tag = "sel-elsewhere" if sel in (any_cls if is_cls else any_inst) else "sel-absent"
            e["miss"].append((sel, tag)); miss_c += 1
    print(f"methods OK: {ok_c}   issues: {miss_c}")
    print("\n== classes fully missing from 21.32.4 (classname section) ==")
    for cls, e in sorted(by_class.items()):
        if e["missing_class"] and cls not in classes2 and cls not in classnames:
            print(f"  {cls}")
    print("\n== classes present but with missing methods ==")
    for cls, e in sorted(by_class.items()):
        if e["missing_class"] and cls in classnames and cls not in classes2:
            print(f"  {cls}  (in classname, walk missed — recheck)")
            continue
        if not e["missing_class"] and e["miss"]:
            print(f"  {cls}: {len(e['ok'])} ok / {len(e['miss'])} miss")
            for sel, tag in e["miss"][:8]:
                print(f"      - {sel}  [{tag}]")
elif mode == "inventory":
    kws = sys.argv[2] if len(sys.argv) > 2 else "Player|Setting|Ad|Sponsor|Premium|Offline|Download|Reel|Shorts|Pivot"
    pat = re.compile(kws)
    hits = []
    for name, c in classes2.items():
        if pat.search(name) and len(name) < 70 and not name.startswith(("_Tt", "Tt", "Swift", "U_")):
            inst = sorted(c["inst"])[:40]
            cls_ = sorted(c["cls"])[:10]
            hits.append((name, c["super"], len(c["inst"]), inst, cls_))
    print(f"classes matching /{kws}/: {len(hits)}")
    for name, sup, n, inst, cls_ in sorted(hits)[:60]:
        print(f"\n{name} : {sup}  ({n} methods)")
        if inst:
            print("   " + ", ".join(inst))
elif mode == "class":
    target = sys.argv[2]
    if target in classes2:
        c = classes2[target]
        print(f"{target} : {c['super']}  inst={len(c['inst'])} cls={len(c['cls'])}")
        print("instance:", ", ".join(sorted(c["inst"])))
        print("class:   ", ", ".join(sorted(c["cls"])))
    else:
        print(f"{target}: {'in classname section' if target in classnames else 'NOT in classname section'}")

# mode "imp": print imp address for (class, selector)
elif mode == "imp":
    target_cls, target_sel = sys.argv[2], sys.argv[3]
    for name, c in classes2.items():
        if name != target_cls:
            continue
        # walk the method list again, capturing (sel, imp)
        dp_ = None
        dk, dp_ = chained(rd64(c["ptr"] + 32))
        if not dp_:
            continue
        list_raw = rd64(dp_ + 32)
        lk, lp = chained(list_raw)
        if lk != "rebase" or not lp:
            continue
        eaf = struct.unpack_from("<I", data, vm2off(lp))[0]
        entsize = eaf & 0xFFFF or eaf & 0x3FFFFF
        REL = bool(eaf & 0x80000000)
        o = vm2off(lp)
        count = struct.unpack_from("<I", data, o + 4)[0]
        base = lp + 8
        for i in range(count):
            e = base + i * entsize
            eo = vm2off(e)
            if eo is None or eo + 12 > len(data):
                break
            if REL and entsize == 12:
                rel = struct.unpack_from("<i", data, eo)[0]
                sk, sp = chained(rd64(e + rel))
                sel = cstr(sp) if sp else None
                imp_raw = struct.unpack_from("<i", data, eo + 8)[0]
                ik, ip_ = chained(e + 8 + imp_raw)
                if sel == target_sel:
                    print(f"{name} {sel} IMP = {ip_ and hex(ip_)}")
            elif not REL:
                continue
        # also check metaclass for class methods
        break
