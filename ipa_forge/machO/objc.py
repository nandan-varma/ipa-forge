# SPDX-License-Identifier: GPL-3.0-or-later
"""Mach-O Objective-C runtime analysis: classes, protocols, categories,
ivars, properties, method lists, and selectors.

Parses the ``__objc_classlist``/``__objc_protolist``/``__objc_catlist``/
``__objc_classname``/``__objc_selrefs`` sections of an arm64 Mach-O
(chained-fixup aware). This is the shared ground truth for two consumers:
``ipa_forge.hooks`` (does this hook target exist and attach?) and
``ipa_forge.analysis`` (class-dump/strings/diff — general reverse
engineering of an IPA).

Fat binaries are thinned to the arm64 slice first (lipo); section file
offsets are then correct for direct data reads.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ipa_forge.bundle.models import AppBundle
from ipa_forge.machO.detect import bundle_executable_paths


@dataclass
class MachOIvar:
    name: str
    type_encoding: str  # raw Objective-C type-encoding string, e.g. '@"NSString"', 'i', 'q'


@dataclass
class MachOProperty:
    name: str
    attributes: str  # raw property attribute string, e.g. 'T@"NSString",C,N'


@dataclass
class MachOProtocol:
    name: str
    protocols: set[str] = field(default_factory=set)  # inherited protocols
    inst: dict[str, str] = field(default_factory=dict)  # required instance methods -> type encoding
    cls: dict[str, str] = field(default_factory=dict)  # required class methods -> type encoding
    opt_inst: dict[str, str] = field(default_factory=dict)  # @optional instance methods -> type encoding
    opt_cls: dict[str, str] = field(default_factory=dict)  # @optional class methods -> type encoding


@dataclass
class MachOCategory:
    name: str
    class_name: str  # class being extended; "«external»" for a system-class
    # category (Foundation/UIKit); "" only if the pointer itself is absent
    inst: dict[str, str] = field(default_factory=dict)  # instance methods -> type encoding
    cls: dict[str, str] = field(default_factory=dict)  # class (metaclass) methods -> type encoding
    protocols: set[str] = field(default_factory=set)


@dataclass
class MachOClass:
    name: str
    super_name: str | None = None  # None = root; "«external»" = defined in another image
    inst: dict[str, str] = field(default_factory=dict)  # instance methods -> type encoding
    cls: dict[str, str] = field(default_factory=dict)  # class (metaclass) methods -> type encoding
    protocols: set[str] = field(default_factory=set)
    ivars: list[MachOIvar] = field(default_factory=list)
    properties: list[MachOProperty] = field(default_factory=list)


@dataclass
class MachOAnalysis:
    classes: dict[str, MachOClass]
    classnames: set[str]  # every class-name string defined in the image
    selectors: set[str]  # every selector the image references (selrefs + method lists)
    main_executable: Path | None
    methnames: set[str] = field(default_factory=set)  # every selector DECLARED as a method name (__objc_methname)
    protocols: dict[str, MachOProtocol] = field(default_factory=dict)  # __objc_protolist, by name
    categories: list[MachOCategory] = field(default_factory=list)  # __objc_catlist
    # Raw bytes of every analyzed binary, kept so the verifier can cross-check
    # a missing class/selector against the actual string table (a class name or
    # selector present as a cstring but absent from the parsed method lists is
    # a parser gap, not a rename — see verify.py). Short-lived per-command
    # data; held in memory only for the duration of the analysis.
    raw_data: list[bytes] = field(default_factory=list)


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


def analyze_bundle(bundle: AppBundle) -> MachOAnalysis:
    """Analyze every executable in an AppBundle (main binary + embedded
    frameworks/dylibs) and merge the results. Hook targets routinely live in
    frameworks (Spotify's SPTDataLoaderService is in SpotifyShared.framework),
    so verification must cover all of them, not just the main executable."""
    paths = bundle_executable_paths(bundle, kinds={"framework"})

    merged: MachOAnalysis | None = None
    for binary_path in paths:
        try:
            analysis = analyze_macho(binary_path)
        except (ValueError, OSError, subprocess.CalledProcessError):
            continue  # not a Mach-O or unreadable; skip
        if merged is None:
            merged = analysis
        else:
            merged.classes.update(analysis.classes)
            merged.classnames |= analysis.classnames
            merged.selectors |= analysis.selectors
            merged.methnames |= analysis.methnames
            merged.protocols.update(analysis.protocols)
            merged.categories.extend(analysis.categories)
            merged.raw_data.extend(analysis.raw_data)
    if merged is None:
        raise ValueError("no analyzable Mach-O found in the app bundle")
    return merged


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
        return "rebase", raw & 0xFFFFFFFFF

    def resolve_ptr(raw: int | None) -> int | None:
        """Resolve a (possibly chained) pointer to a vm address.

        Three addressing modes occur in the wild:
          - PIE executables: chained rebase targets (and plain small pointers)
            are offsets from the image base (ib) -- add ib.
          - Mergeable/zero-based dylibs: targets are already absolute vms.
          - Plain absolute pointers: already complete.
        Try absolute first (cheap section lookup), then offset-from-base.
        """
        kind, val = chained(raw)
        if kind == "plain":
            val = raw
        if val is None:
            return None
        if vm2off(val) is not None:
            return val
        return val + ib

    classnames: set[str] = set()
    if "__objc_classname" in sections:
        _a, sz, o = sections["__objc_classname"]
        classnames.update(s.decode("utf-8", "replace") for s in data[o : o + sz].split(b"\x00") if s)

    # ---- pass 1: class table (name, superclass, ro ptr, metaclass ptr) ----
    ro_by_name: dict[str, int] = {}
    meta_by_name: dict[str, int] = {}

    def class_ptr(raw: int) -> int | None:
        return resolve_ptr(raw)

    if "__objc_classlist" in sections:
        _a, sz, o = sections["__objc_classlist"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            p = class_ptr(raw)
            if p is None:
                continue
            dp = resolve_ptr(rd64(p + 32))
            if not dp:
                continue
            np = resolve_ptr(rd64(dp + 24))
            if not np:
                continue
            name = cstr(np)
            if not name:
                continue
            ro_by_name[name] = dp
            ip_ = resolve_ptr(rd64(p))  # isa -> metaclass
            if ip_:
                meta_by_name[name] = ip_

    classes: dict[str, MachOClass] = {n: MachOClass(name=n) for n in ro_by_name}

    if "__objc_classlist" in sections:
        _a, sz, o = sections["__objc_classlist"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            p = class_ptr(raw)
            if p is None:
                continue
            dp = resolve_ptr(rd64(p + 32))
            if not dp:
                continue
            np = resolve_ptr(rd64(dp + 24))
            if not np:
                continue
            name = cstr(np)
            if not name or name not in classes:
                continue
            sp = resolve_ptr(rd64(p + 8))
            super_name: str | None = None
            if sp:
                sdp = resolve_ptr(rd64(sp + 32))
                if sdp:
                    snp = resolve_ptr(rd64(sdp + 24))
                    if snp:
                        super_name = cstr(snp)
                if super_name is None:
                    # Superclass pointer exists but the name could not be
                    # resolved (external bind, chained-fixup variant we do not
                    # decode) — the class still inherits from SOMETHING, so
                    # mark it external rather than pretending it is a root.
                    super_name = "«external»"
            else:
                # a NULL/absent superclass pointer means it binds to an external
                # superclass (defined in another image)
                super_name = "«external»"
            classes[name].super_name = super_name

    # ---- pass 2: method lists ----
    # Returns {selector: type_encoding} rather than a bare set of selectors --
    # `sel in methods` still works unchanged (dict key containment), but the
    # type encoding lets class-dump reconstruct full method signatures
    # instead of bare selector names.
    def parse_methods(list_raw: int | None) -> dict[str, str]:
        if not list_raw:
            return {}
        lp = resolve_ptr(list_raw)
        if not lp:
            return {}
        eo = vm2off(lp)
        if eo is None or eo + 8 > len(data):
            return {}
        eaf = struct.unpack_from("<I", data, eo)[0]
        entsize = eaf & 0xFFFF or eaf & 0x3FFFFF
        rel = bool(eaf & 0x80000000)
        count = struct.unpack_from("<I", data, eo + 4)[0]
        if count > 5_000_000:
            return {}
        methods: dict[str, str] = {}
        for i in range(count):
            e = lp + 8 + i * entsize
            eo_i = vm2off(e)
            if eo_i is None or eo_i + 12 > len(data):
                break
            if rel and entsize == 12:
                # name/types are self-relative: a signed 32-bit offset from
                # the FIELD's own address. `name` additionally indirects
                # through a selector-reference slot (uniquing); `types`
                # points straight at the encoding cstring (no uniquing table
                # exists for them), no second resolve_ptr needed.
                name_off = struct.unpack_from("<i", data, eo_i)[0]
                sel_ptr = resolve_ptr(rd64(e + name_off))
                sel = cstr(sel_ptr) if sel_ptr else None
                types_off = struct.unpack_from("<i", data, eo_i + 4)[0]
                types = cstr(e + 4 + types_off)
            elif not rel:
                sel_ptr = resolve_ptr(rd64(e))
                sel = cstr(sel_ptr) if sel_ptr else None
                types_ptr = resolve_ptr(rd64(e + 8))
                types = cstr(types_ptr) if types_ptr else None
            else:
                continue
            if sel:
                methods[sel] = types or ""
        return methods

    # ---- pass 2b: protocol/ivar/property lists shared by classes, protocols,
    # and categories (protocol_list_t / ivar_list_t / property_list_t) ----
    def parse_ptr_list(list_raw: int | None) -> list[int]:
        """protocol_list_t: a size_t count followed by `count` pointers."""
        if not list_raw:
            return []
        lp = resolve_ptr(list_raw)
        if not lp:
            return []
        co = vm2off(lp)
        if co is None or co + 8 > len(data):
            return []
        count = struct.unpack_from("<Q", data, co)[0]
        if count > 100_000:
            return []
        ptrs: list[int] = []
        for i in range(count):
            raw = rd64(lp + 8 + i * 8)
            p = resolve_ptr(raw) if raw else None
            if p:
                ptrs.append(p)
        return ptrs

    def protocol_name(proto_ptr: int) -> str | None:
        np = resolve_ptr(rd64(proto_ptr + 8))  # protocol_t.name
        return cstr(np) if np else None

    def parse_protocol_names(list_raw: int | None) -> set[str]:
        return {n for p in parse_ptr_list(list_raw) if (n := protocol_name(p))}

    def parse_ivars(list_raw: int | None) -> list[MachOIvar]:
        if not list_raw:
            return []
        lp = resolve_ptr(list_raw)
        if not lp:
            return []
        ho = vm2off(lp)
        if ho is None or ho + 8 > len(data):
            return []
        entsize = struct.unpack_from("<I", data, ho)[0]
        count = struct.unpack_from("<I", data, ho + 4)[0]
        if entsize == 0 or count > 100_000:
            return []
        ivars: list[MachOIvar] = []
        for i in range(count):
            eo = vm2off(lp + 8 + i * entsize)
            if eo is None or eo + 24 > len(data):
                break
            name_ptr = resolve_ptr(rd64(lp + 8 + i * entsize + 8))  # ivar_t.name
            type_ptr = resolve_ptr(rd64(lp + 8 + i * entsize + 16))  # ivar_t.type
            name = cstr(name_ptr) if name_ptr else None
            if name:
                ivars.append(MachOIvar(name, (cstr(type_ptr) if type_ptr else None) or ""))
        return ivars

    def parse_properties(list_raw: int | None) -> list[MachOProperty]:
        if not list_raw:
            return []
        lp = resolve_ptr(list_raw)
        if not lp:
            return []
        ho = vm2off(lp)
        if ho is None or ho + 8 > len(data):
            return []
        entsize = struct.unpack_from("<I", data, ho)[0]
        count = struct.unpack_from("<I", data, ho + 4)[0]
        if entsize == 0 or count > 100_000:
            return []
        props: list[MachOProperty] = []
        for i in range(count):
            eo = vm2off(lp + 8 + i * entsize)
            if eo is None or eo + 16 > len(data):
                break
            name_ptr = resolve_ptr(rd64(lp + 8 + i * entsize))  # property_t.name
            attr_ptr = resolve_ptr(rd64(lp + 8 + i * entsize + 8))  # property_t.attributes
            name = cstr(name_ptr) if name_ptr else None
            if name:
                props.append(MachOProperty(name, (cstr(attr_ptr) if attr_ptr else None) or ""))
        return props

    def class_name_from_ptr(raw: int | None) -> str | None:
        """Resolve a class_t* (isa/superclass/cache/vtable/data) to its name,
        for category_t.cls -- the same chain pass 1 walks for the classlist.
        Returns "«external»" (not None) when the pointer is a bind to a class
        defined in another image -- routine for a category on a system class
        (NSObject, UIView, ...) and distinct from a genuinely absent pointer."""
        if not raw:
            return None
        p = resolve_ptr(raw)
        if not p:
            return "«external»"
        dp = resolve_ptr(rd64(p + 32))
        if not dp:
            return "«external»"
        np = resolve_ptr(rd64(dp + 24))
        name = cstr(np) if np else None
        return name or "«external»"

    for name, ro in ro_by_name.items():
        cls = classes[name]
        cls.inst = parse_methods(rd64(ro + 32))  # ro.baseMethods
        cls.protocols = parse_protocol_names(rd64(ro + 40))  # ro.baseProtocols
        cls.ivars = parse_ivars(rd64(ro + 48))  # ro.ivars
        cls.properties = parse_properties(rd64(ro + 64))  # ro.baseProperties
        meta = meta_by_name.get(name)
        if meta:
            mdp = resolve_ptr(rd64(meta + 32))
            if mdp:
                cls.cls = parse_methods(rd64(mdp + 32))  # metaclass ro.baseMethods

    # ---- pass 3: selrefs (every selector the image references) ----
    selectors: set[str] = set()
    if "__objc_selrefs" in sections:
        _a, sz, o = sections["__objc_selrefs"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            sp = resolve_ptr(raw)
            if sp:
                sel_str = cstr(sp)
                if sel_str:
                    selectors.add(sel_str)
    for cls in classes.values():
        selectors |= set(cls.inst) | set(cls.cls)

    # ---- pass 4: methname (every selector DECLARED as a method name) ----
    # Distinct from selrefs: a selector can be *referenced* (NSSelectorFromString,
    # performSelector, optional protocol sends) without being declared as a
    # method anywhere. A hook on such a selector cannot attach (no IMP exists to
    # swizzle) — the verifier uses methnames to distinguish that dead case from
    # a parser gap on a real method.
    methnames: set[str] = set()
    if "__objc_methname" in sections:
        _a, sz, o = sections["__objc_methname"]
        methnames.update(s.decode("utf-8", "replace") for s in data[o : o + sz].split(b"\x00") if s)

    # ---- pass 5: protocol table (__objc_protolist) ----
    # protocol_t: isa@0, name@8, protocols(protocol_list_t*)@16,
    # instanceMethods@24, classMethods@32, optionalInstanceMethods@40,
    # optionalClassMethods@48.
    protocols: dict[str, MachOProtocol] = {}
    if "__objc_protolist" in sections:
        _a, sz, o = sections["__objc_protolist"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            pp = resolve_ptr(raw)
            if not pp:
                continue
            name = protocol_name(pp)
            if not name:
                continue
            protocols[name] = MachOProtocol(
                name=name,
                protocols=parse_protocol_names(rd64(pp + 16)),
                inst=parse_methods(rd64(pp + 24)),
                cls=parse_methods(rd64(pp + 32)),
                opt_inst=parse_methods(rd64(pp + 40)),
                opt_cls=parse_methods(rd64(pp + 48)),
            )

    # ---- pass 6: categories (__objc_catlist) ----
    # category_t: name@0, cls(class_t*)@8, instanceMethods@16, classMethods@24,
    # protocols(protocol_list_t*)@32, instanceProperties@40.
    categories: list[MachOCategory] = []
    if "__objc_catlist" in sections:
        _a, sz, o = sections["__objc_catlist"]
        for i in range(sz // 8):
            raw = struct.unpack_from("<Q", data, o + i * 8)[0]
            cp = resolve_ptr(raw)
            if not cp:
                continue
            name_ptr = resolve_ptr(rd64(cp))
            cat_name = cstr(name_ptr) if name_ptr else None
            if not cat_name:
                continue
            categories.append(
                MachOCategory(
                    name=cat_name,
                    class_name=class_name_from_ptr(rd64(cp + 8)) or "",
                    inst=parse_methods(rd64(cp + 16)),
                    cls=parse_methods(rd64(cp + 24)),
                    protocols=parse_protocol_names(rd64(cp + 32)),
                )
            )

    return MachOAnalysis(
        classes=classes,
        classnames=classnames,
        selectors=selectors,
        methnames=methnames,
        protocols=protocols,
        categories=categories,
        main_executable=original,
        raw_data=[data],
    )


def contains_string(analysis: MachOAnalysis, s: str) -> bool:
    """True when ``s`` appears as a standalone cstring (\0-delimited) in any
    analyzed image — i.e. the string is *present* in the binary even if the
    class-table/method-list walk missed it. The \0-preceded, \0-terminated
    pattern matches how string tables lay consecutive cstrings out, so a match
    means the string exists on its own rather than inside a longer name."""
    if not s:
        return False
    target = b"\x00" + s.encode("utf-8") + b"\x00"
    return any(target in data for data in analysis.raw_data)
