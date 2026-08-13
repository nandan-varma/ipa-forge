# SPDX-License-Identifier: GPL-3.0-or-later
"""Mach-O Objective-C runtime analysis: class table + method lists + selectors.

Parses the ``__objc_classlist``/``__objc_classname``/``__objc_selrefs``
sections of an arm64 Mach-O (chained-fixup aware), producing the ground
truth the hook verifier needs: does this class exist and does it implement
this selector? Catches the silent hook no-ops that version drift causes.

Fat binaries are thinned to the arm64 slice first (lipo); section file
offsets are then correct for direct data reads.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MachOClass:
    name: str
    super_name: str | None = None  # None = root; "«external»" = defined in another image
    inst: set[str] = field(default_factory=set)
    cls: set[str] = field(default_factory=set)  # class (metaclass) methods


@dataclass
class MachOAnalysis:
    classes: dict[str, MachOClass]
    classnames: set[str]  # every class-name string defined in the image
    selectors: set[str]  # every selector the image references (selrefs + method lists)
    main_executable: Path


def _run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def analyze_macho(path: Path) -> MachOAnalysis:
    """Analyze a Mach-O executable (thin or fat; fat gets thinned to arm64)."""
    with tempfile.TemporaryDirectory(prefix="ipa_forge_hooks_") as tmp:
        info = _run("lipo", "-info", str(path))
        bin_path = path
        if "are:" in info and "arm64" in info:
            bin_path = Path(tmp) / f"{path.name}.arm64"
            _run("lipo", "-thin", "arm64", str(path), "-output", str(bin_path))
        return _analyze_thin(bin_path, original=path)


def _analyze_thin(bin_path: Path, original: Path) -> MachOAnalysis:
    otool = _run("otool", "-l", str(bin_path))

    sections: dict[str, tuple[int, int, int]] = {}
    cur: str | None = None
    addr = size = off = 0
    seg_bases: list[int] = []
    for line in otool.splitlines():
        s = line.strip()
        if s.startswith("vmaddr 0x") and "segment" not in s:
            seg_bases.append(int(s.split()[1], 16))
        if s.startswith("sectname "):
            cur = s.split()[1]
        elif s.startswith("addr 0x") and cur:
            addr = int(s.split()[1], 16)
        elif s.startswith("size 0x") and cur:
            size = int(s.split()[1], 16)
        elif s.startswith("offset ") and cur:
            off = int(s.split()[1], 10)
            sections[cur] = (addr, size, off)
            cur = None
    if not seg_bases:
        raise ValueError("no __TEXT segment found (not a Mach-O?)")
    ib = min(b for b in seg_bases if b)

    data = bin_path.read_bytes()

    def vm2off(a: int) -> int | None:
        for _n, (va, sz, fo) in sections.items():
            if va <= a < va + sz:
                return fo + (a - va)
        return None

    def rd64(a: int) -> int | None:
        o = vm2off(a)
        if o is None or o + 8 > len(data):
            return None
        return struct.unpack_from("<Q", data, o)[0]

    def cstr(a: int) -> str | None:
        o = vm2off(a)
        if o is None:
            return None
        e = data.find(b"\x00", o)
        if e <= o or e - o > 4000:
            return None
        try:
            return data[o:e].decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return None

    def chained(raw: int | None) -> tuple[str, int | None]:
        if raw is None:
            return "none", None
        if raw >> 32 == 0:
            return "plain", raw
        if raw & (1 << 63):
            return "bind", None
        return "rebase", (raw & 0xFFFFFFFFF) + ib

    classnames: set[str] = set()
    if "__objc_classname" in sections:
        _a, sz, o = sections["__objc_classname"]
        classnames.update(s.decode("utf-8", "replace") for s in data[o : o + sz].split(b"\x00") if s)

    # ---- pass 1: class table (name, superclass, ro ptr, metaclass ptr) ----
    ro_by_name: dict[str, int] = {}
    meta_by_name: dict[str, int] = {}
    if "__objc_classlist" in sections:
        _a, sz, o = sections["__objc_classlist"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            if raw >> 32 == 0 or raw & (1 << 63):
                continue
            p = (raw & 0xFFFFFFFFF) + ib
            _dk, dp = chained(rd64(p + 32))
            if not dp:
                continue
            _nk, np = chained(rd64(dp + 24))
            if not np:
                continue
            name = cstr(np)
            if not name:
                continue
            ro_by_name[name] = dp
            _ik, ip_ = chained(rd64(p))  # isa -> metaclass
            if ip_:
                meta_by_name[name] = ip_

    classes: dict[str, MachOClass] = {n: MachOClass(name=n) for n in ro_by_name}

    if "__objc_classlist" in sections:
        _a, sz, o = sections["__objc_classlist"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            if raw >> 32 == 0 or raw & (1 << 63):
                continue
            p = (raw & 0xFFFFFFFFF) + ib
            _dk, dp = chained(rd64(p + 32))
            if not dp:
                continue
            _nk, np = chained(rd64(dp + 24))
            if not np:
                continue
            name = cstr(np)
            if not name or name not in classes:
                continue
            sk, sp = chained(rd64(p + 8))
            super_name: str | None = None
            if sk == "rebase" and sp:
                sdk, sdp = chained(rd64(sp + 32))
                if sdk == "rebase" and sdp:
                    snk, snp = chained(rd64(sdp + 24))
                    if snk == "rebase" and snp:
                        super_name = cstr(snp)
            elif sk == "bind":
                super_name = "«external»"
            classes[name].super_name = super_name

    # ---- pass 2: method lists ----
    def parse_methods(list_raw: int | None) -> set[str]:
        if not list_raw:
            return set()
        _lk, lp = chained(list_raw)
        if not lp:
            return set()
        eo = vm2off(lp)
        if eo is None or eo + 8 > len(data):
            return set()
        eaf = struct.unpack_from("<I", data, eo)[0]
        entsize = eaf & 0xFFFF or eaf & 0x3FFFFF
        rel = bool(eaf & 0x80000000)
        count = struct.unpack_from("<I", data, eo + 4)[0]
        if count > 5_000_000:
            return set()
        sels: set[str] = set()
        for i in range(count):
            e = lp + 8 + i * entsize
            eo_i = vm2off(e)
            if eo_i is None or eo_i + 12 > len(data):
                break
            if rel and entsize == 12:
                rel_off = struct.unpack_from("<i", data, eo_i)[0]
                _sk, sp = chained(rd64(e + rel_off))
                sel = cstr(sp) if sp else None
            elif not rel:
                ptr = rd64(e)
                sel = cstr(ptr) if ptr else None
            else:
                continue
            if sel:
                sels.add(sel)
        return sels

    for name, ro in ro_by_name.items():
        cls = classes[name]
        cls.inst = parse_methods(rd64(ro + 32))  # ro.baseMethods
        meta = meta_by_name.get(name)
        if meta:
            _mdk, mdp = chained(rd64(meta + 32))
            if mdp:
                cls.cls = parse_methods(rd64(mdp + 32))  # metaclass ro.baseMethods

    # ---- pass 3: selrefs (every selector the image references) ----
    selectors: set[str] = set()
    if "__objc_selrefs" in sections:
        _a, sz, o = sections["__objc_selrefs"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            _k, sp = chained(raw)
            if sp:
                sel_str = cstr(sp)
                if sel_str:
                    selectors.add(sel_str)
    for cls in classes.values():
        selectors |= cls.inst | cls.cls

    return MachOAnalysis(classes=classes, classnames=classnames, selectors=selectors, main_executable=original)
