# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-references for Unity IL2CPP apps: which compiled methods load which
C# string literals, types, methods and fields, and who calls whom.

A Unity app ships its C# as AOT-compiled ARM64 in ``UnityFramework`` (or the
main executable on old Unity versions) plus ``Data/Managed/Metadata/
global-metadata.dat``. Since metadata v27 there is no usage table: every
method that touches metadata lazily initializes per-method *usage slots* in
``__DATA``, each holding an encoded token until first use --
``(kind << 29) | (index << 1) | 1`` with kind 1 TypeInfo, 2 Il2CppType,
3 MethodDef, 4 FieldRef, 5 StringLiteral, 6 MethodSpec. Code reaches a slot
with an ``adrp``+``ldr``/``add`` pair, so decoding the slots and matching
those pairs gives a literal/type/method -> caller index without running the
app. Direct ``bl``/``b`` targets give the call graph.

Method addresses come from the binary itself: the IL2CPP code registration's
per-assembly ``methodPointers`` arrays are indexed by each method's metadata
token, and ``LC_FUNCTION_STARTS`` bounds every function (including generic
instantiations and runtime helpers, which are reported as ``sub_<addr>``).
Names are whatever the metadata holds -- obfuscated builds keep obfuscated
names; Cpp2IL's ``diffable-cs`` output adds signatures and field offsets.

Scope, deliberately narrow: metadata v31 (Unity 2022.3) only, thin or fat
arm64. This decodes exactly five instruction forms (adrp, add/ldr immediate,
b, bl) to recover references -- it is not a disassembler; see the package
docstring. Register tracking is per-function and approximate, so a missing
reference is possible; a reported one points at a real slot load.
"""

from __future__ import annotations

import bisect
import contextlib
import hashlib
import pickle
import re
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ipa_forge.machO import cache as objc_cache

METADATA_RELATIVE_PATH = Path("Data/Managed/Metadata/global-metadata.dat")
UNITY_FRAMEWORK_RELATIVE_PATH = Path("Frameworks/UnityFramework.framework/UnityFramework")

SUPPORTED_METADATA_VERSIONS = (31,)

_METADATA_SANITY = 0xFAB11BAF
_CPU_TYPE_ARM64 = 0x0100000C
_LC_SEGMENT_64 = 0x19
_LC_FUNCTION_STARTS = 0x26
_S_ATTR_PURE_INSTRUCTIONS = 0x80000000
_ZEROFILL_TYPES = {0x1, 0xC, 0x12}  # S_ZEROFILL, S_GB_ZEROFILL, S_THREAD_LOCAL_ZEROFILL
_POINTER_MASK = (1 << 36) - 1  # plain pointers and chained-fixup rebases both fit

# Metadata v31 section order (pairs of int32 offset/size after sanity+version)
# and the struct sizes this module relies on. Validated against the file.
_SECTIONS = (
    "string_literals",
    "string_literal_data",
    "strings",
    "events",
    "properties",
    "methods",
    "parameter_default_values",
    "field_default_values",
    "field_and_parameter_default_value_data",
    "field_marshaled_sizes",
    "parameters",
    "fields",
    "generic_parameters",
    "generic_parameter_constraints",
    "generic_containers",
    "nested_types",
    "interfaces",
    "vtable_methods",
    "interface_offsets",
    "type_definitions",
    "images",
    "assemblies",
    "field_refs",
)
_STRUCT_SIZES = {
    "string_literals": 8,
    "methods": 36,
    "fields": 12,
    "generic_parameters": 12,
    "type_definitions": 88,
    "images": 40,
    "field_refs": 8,
}

USAGE_KINDS = {1: "type", 2: "type", 3: "method", 4: "field", 5: "string", 6: "method"}
_PRIMITIVES = {
    0x01: "void",
    0x02: "bool",
    0x03: "char",
    0x04: "sbyte",
    0x05: "byte",
    0x06: "short",
    0x07: "ushort",
    0x08: "int",
    0x09: "uint",
    0x0A: "long",
    0x0B: "ulong",
    0x0C: "float",
    0x0D: "double",
    0x0E: "string",
    0x16: "TypedReference",
    0x18: "IntPtr",
    0x19: "UIntPtr",
    0x1C: "object",
}


class Il2CppError(Exception):
    """The app is not an IL2CPP build this module can read."""


# --------------------------------------------------------------------------
# Mach-O


@dataclass(frozen=True)
class Section:
    segname: str
    sectname: str
    addr: int
    size: int
    offset: int
    flags: int

    @property
    def is_zerofill(self) -> bool:
        return (self.flags & 0xFF) in _ZEROFILL_TYPES or self.offset == 0

    @property
    def is_code(self) -> bool:
        return bool(self.flags & _S_ATTR_PURE_INSTRUCTIONS)


class MachOImage:
    """The arm64 slice of a Mach-O file, addressable by VM address."""

    def __init__(self, data: bytes) -> None:
        self.data = _arm64_slice(data)
        magic, cputype, _, _, ncmds, _, _, _ = struct.unpack_from("<8I", self.data, 0)
        if magic != 0xFEEDFACF or cputype != _CPU_TYPE_ARM64:
            raise Il2CppError("not a 64-bit arm64 Mach-O")
        self.segments: list[tuple[str, int, int, int, int]] = []  # name, vmaddr, vmsize, fileoff, filesize
        self.sections: list[Section] = []
        self.function_starts: list[int] = []
        function_starts_cmd: tuple[int, int] | None = None
        off = 32
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack_from("<2I", self.data, off)
            if cmd == _LC_SEGMENT_64:
                segname = _cstr16(self.data, off + 8)
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<4Q", self.data, off + 24)
                nsects = struct.unpack_from("<I", self.data, off + 64)[0]
                self.segments.append((segname, vmaddr, vmsize, fileoff, filesize))
                for i in range(nsects):
                    s = off + 72 + i * 80
                    addr, size = struct.unpack_from("<2Q", self.data, s + 32)
                    offset = struct.unpack_from("<I", self.data, s + 48)[0]
                    flags = struct.unpack_from("<I", self.data, s + 64)[0]
                    self.sections.append(
                        Section(_cstr16(self.data, s + 16), _cstr16(self.data, s), addr, size, offset, flags)
                    )
            elif cmd == _LC_FUNCTION_STARTS:
                function_starts_cmd = struct.unpack_from("<2I", self.data, off + 8)
            off += cmdsize
        self.base = next((vm for name, vm, _, _, _ in self.segments if name == "__TEXT"), 0)
        if function_starts_cmd is not None:
            self.function_starts = decode_function_starts(self.data, *function_starts_cmd, self.base)

    def offset_of(self, addr: int) -> int | None:
        for _, vmaddr, _, fileoff, filesize in self.segments:
            if vmaddr <= addr < vmaddr + filesize:
                return fileoff + addr - vmaddr
        return None

    def is_mapped(self, addr: int) -> bool:
        return addr != 0 and self.offset_of(addr) is not None

    def unpack(self, fmt: str, addr: int) -> tuple[int, ...]:
        off = self.offset_of(addr)
        if off is None:
            raise Il2CppError(f"address {addr:#x} is not file-backed")
        return struct.unpack_from(fmt, self.data, off)

    def u32(self, addr: int) -> int:
        return int(self.unpack("<I", addr)[0])

    def u64(self, addr: int) -> int:
        return int(self.unpack("<Q", addr)[0])

    def pointer(self, addr: int) -> int:
        """Dereference a pointer slot, normalizing chained-fixup rebases."""
        return self.decode_pointer(self.u64(addr))

    def decode_pointer(self, value: int) -> int:
        if value == 0:
            return 0
        target = value & _POINTER_MASK
        # DYLD_CHAINED_PTR_64_OFFSET stores an offset from the image base.
        return target + self.base if target < self.base else target

    def cstring(self, addr: int, limit: int = 512) -> str | None:
        off = self.offset_of(addr)
        if off is None:
            return None
        end = self.data.find(b"\0", off, off + limit)
        if end < 0:
            return None
        return self.data[off:end].decode("utf-8", "replace")

    def data_sections(self) -> Iterator[Section]:
        for s in self.sections:
            if s.segname.startswith("__DATA") and not s.is_zerofill:
                yield s


def _arm64_slice(data: bytes) -> bytes:
    magic = struct.unpack_from(">I", data, 0)[0]
    if magic not in (0xCAFEBABE, 0xCAFEBABF):
        return data
    nfat = struct.unpack_from(">I", data, 4)[0]
    for i in range(nfat):
        if magic == 0xCAFEBABE:
            cputype, _, offset, size, _ = struct.unpack_from(">5I", data, 8 + i * 20)
        else:
            cputype, _, offset, size, _, _ = struct.unpack_from(">2I2Q2I", data, 8 + i * 32)
        if cputype == _CPU_TYPE_ARM64:
            return data[offset : offset + size]
    raise Il2CppError("universal binary has no arm64 slice")


def _cstr16(data: bytes, off: int) -> str:
    return data[off : off + 16].split(b"\0", 1)[0].decode("ascii", "replace")


def decode_function_starts(data: bytes, dataoff: int, datasize: int, base: int) -> list[int]:
    """Decode LC_FUNCTION_STARTS: ULEB128 deltas, the first relative to the
    __TEXT segment start, terminated by a zero delta."""
    starts: list[int] = []
    addr = base
    i, end = dataoff, dataoff + datasize
    while i < end:
        value = shift = 0
        while True:
            byte = data[i]
            i += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        if value == 0:
            break
        addr += value
        starts.append(addr)
    return starts


# --------------------------------------------------------------------------
# global-metadata.dat


@dataclass(frozen=True)
class TypeDefinition:
    name: str
    namespace: str
    declaring_type_index: int  # index into the registration's Il2CppType table, -1 if top level
    field_start: int


@dataclass(frozen=True)
class MethodDefinition:
    name: str
    declaring_type: int  # TypeDefinitionIndex
    token: int


@dataclass(frozen=True)
class ImageDefinition:
    name: str
    type_start: int
    type_count: int


class Metadata:
    """The parts of global-metadata.dat needed to name code and decode slots."""

    def __init__(self, data: bytes) -> None:
        if len(data) < 0x100:
            raise Il2CppError("global-metadata.dat is truncated")
        sanity, version = struct.unpack_from("<2I", data, 0)
        if sanity != _METADATA_SANITY:
            raise Il2CppError("global-metadata.dat has a bad magic (encrypted or not IL2CPP metadata)")
        if version not in SUPPORTED_METADATA_VERSIONS:
            raise Il2CppError(
                f"IL2CPP metadata v{version} is not supported (supported: "
                f"{', '.join(map(str, SUPPORTED_METADATA_VERSIONS))}); use Cpp2IL for other versions"
            )
        self.version = version
        self.data = data
        pairs = struct.unpack_from(f"<{2 * len(_SECTIONS)}i", data, 8)
        self._sections = {name: (pairs[2 * i], pairs[2 * i + 1]) for i, name in enumerate(_SECTIONS)}
        for name, size in _STRUCT_SIZES.items():
            off, length = self._sections[name]
            if off < 0 or length < 0 or off + length > len(data) or length % size:
                raise Il2CppError(f"metadata section {name} does not match the v{version} layout")

        lit_off, lit_size = self._sections["string_literals"]
        data_off = self._sections["string_literal_data"][0]
        self.string_literals = [
            data[data_off + index : data_off + index + length].decode("utf-8", "replace")
            for length, index in struct.iter_unpack("<Ii", data[lit_off : lit_off + lit_size])
        ]
        self.type_definitions = [
            TypeDefinition(self.string(f[0]), self.string(f[1]), f[3], f[8])
            for f in self._records("type_definitions", "<16i8H2I")
        ]
        self.methods = [MethodDefinition(self.string(f[0]), f[1], f[6]) for f in self._records("methods", "<7i4H")]
        self.images = [ImageDefinition(self.string(f[0]), f[2], f[3]) for f in self._records("images", "<10i")]
        self.field_refs = list(self._records("field_refs", "<2i"))
        self.field_names = [self.string(f[0]) for f in self._records("fields", "<3i")]
        self.generic_parameter_names = [self.string(f[1]) for f in self._records("generic_parameters", "<2i2h2H")]
        if sum(i.type_count for i in self.images) != len(self.type_definitions):
            raise Il2CppError("metadata images do not cover the type definitions (unsupported layout)")
        self._image_starts = sorted((img.type_start, n) for n, img in enumerate(self.images))

    def _records(self, name: str, fmt: str) -> Iterator[tuple[int, ...]]:
        off, length = self._sections[name]
        return struct.iter_unpack(fmt, self.data[off : off + length])

    def string(self, index: int) -> str:
        off = self._sections["strings"][0] + index
        end = self.data.find(b"\0", off)
        return self.data[off:end].decode("utf-8", "replace")

    def image_of_type(self, type_index: int) -> ImageDefinition | None:
        pos = bisect.bisect_right(self._image_starts, (type_index, len(self.images))) - 1
        if pos < 0:
            return None
        image = self.images[self._image_starts[pos][1]]
        return image if image.type_start <= type_index < image.type_start + image.type_count else None


# --------------------------------------------------------------------------
# Registrations


@dataclass
class MetadataRegistration:
    address: int
    generic_insts: int
    generic_method_table_count: int
    generic_method_table: int
    types_count: int
    types: int
    method_specs_count: int
    method_specs: int


def find_metadata_registration(image: MachOImage, type_definition_count: int) -> MetadataRegistration:
    """Locate Il2CppMetadataRegistration: fieldOffsetsCount and
    typeDefinitionsSizesCount (qwords 10 and 12) both equal the number of type
    definitions, with valid pointers beside them."""
    needle = struct.pack("<Q", type_definition_count)
    for section in image.data_sections():
        blob = image.data[section.offset : section.offset + section.size]
        pos = blob.find(needle)
        while pos >= 0:
            start = pos - 80
            if start >= 0 and start % 8 == 0 and start + 128 <= len(blob):
                q = struct.unpack_from("<16Q", blob, start)
                if (
                    q[10] == q[12] == type_definition_count
                    and 0 < q[6] < 10_000_000
                    and all(image.is_mapped(image.decode_pointer(q[i])) for i in (3, 7, 9, 11, 13) if q[i - 1])
                ):
                    return MetadataRegistration(
                        address=section.addr + start,
                        generic_insts=image.decode_pointer(q[3]),
                        generic_method_table_count=int(q[4] & 0xFFFFFFFF),
                        generic_method_table=image.decode_pointer(q[5]),
                        types_count=int(q[6] & 0xFFFFFFFF),
                        types=image.decode_pointer(q[7]),
                        method_specs_count=int(q[8] & 0xFFFFFFFF),
                        method_specs=image.decode_pointer(q[9]),
                    )
            pos = blob.find(needle, pos + 8)
    raise Il2CppError("IL2CPP metadata registration not found in the binary")


@dataclass(frozen=True)
class CodeGenModule:
    name: str
    method_pointer_count: int
    method_pointers: int


def find_code_gen_modules(image: MachOImage, image_names: list[str]) -> tuple[dict[str, CodeGenModule], int]:
    """Locate Il2CppCodeRegistration.codeGenModules: a count equal to the
    number of metadata images followed by a pointer to that many
    Il2CppCodeGenModule pointers, each module starting with a pointer to its
    assembly name."""
    names = set(image_names)
    needle = struct.pack("<Q", len(image_names))
    for section in image.data_sections():
        blob = image.data[section.offset : section.offset + section.size]
        pos = blob.find(needle)
        while pos >= 0:
            if pos % 8 == 0 and pos + 16 <= len(blob):
                array = image.decode_pointer(struct.unpack_from("<Q", blob, pos + 8)[0])
                modules = _read_modules(image, array, len(image_names), names)
                if modules is not None:
                    return modules, section.addr + pos - 120
            pos = blob.find(needle, pos + 8)
    raise Il2CppError("IL2CPP code registration (codeGenModules) not found in the binary")


def _read_modules(image: MachOImage, array: int, count: int, names: set[str]) -> dict[str, CodeGenModule] | None:
    if not image.is_mapped(array):
        return None
    modules: dict[str, CodeGenModule] = {}
    try:
        for i in range(count):
            module = image.pointer(array + 8 * i)
            name = image.cstring(image.pointer(module)) if image.is_mapped(module) else None
            if name is None or name not in names:
                return None
            modules[name] = CodeGenModule(name, image.u32(module + 8), image.pointer(module + 16))
    except Il2CppError:
        return None
    return modules


# --------------------------------------------------------------------------
# Index


@dataclass(frozen=True)
class Reference:
    site: int
    kind: str  # "string", "type", "method", "field"
    value: str


@dataclass(frozen=True)
class Call:
    site: int
    target: int
    tail: bool  # `b` rather than `bl`


@dataclass
class FunctionXrefs:
    address: int
    refs: list[Reference] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)


@dataclass
class Il2CppIndex:
    binary: str
    metadata_version: int
    method_names: dict[int, str]  # function address -> "Type.Method" (+ shared-body note)
    namespaces: dict[int, str]
    function_starts: list[int]
    functions: dict[int, FunctionXrefs]
    string_literal_count: int
    method_count: int

    def name_of(self, address: int) -> str:
        return self.method_names.get(address, f"sub_{address:x}")

    def function_containing(self, address: int) -> int | None:
        pos = bisect.bisect_right(self.function_starts, address) - 1
        return self.function_starts[pos] if pos >= 0 else None

    def find_methods(self, pattern: str) -> list[tuple[int, str]]:
        rx = re.compile(pattern)
        return sorted(((a, n) for a, n in self.method_names.items() if rx.search(n)), key=lambda x: x[1])

    def literal_users(self, pattern: str) -> dict[str, list[tuple[int, int]]]:
        """Matching string literals -> [(function address, load site)]."""
        rx = re.compile(pattern)
        out: dict[str, list[tuple[int, int]]] = {}
        for fn in self.functions.values():
            for ref in fn.refs:
                if ref.kind == "string" and rx.search(ref.value):
                    users = out.setdefault(ref.value, [])
                    if not users or users[-1][0] != fn.address:
                        users.append((fn.address, ref.site))
        return out

    def callers(self, targets: set[int]) -> list[tuple[int, Call]]:
        """[(calling function, call)] for direct calls into `targets`."""
        return [(fn.address, c) for fn in self.functions.values() for c in fn.calls if c.target in targets]


def build_index(binary_path: Path, metadata_path: Path) -> Il2CppIndex:
    metadata = Metadata(metadata_path.read_bytes())
    image = MachOImage(binary_path.read_bytes())
    registration = find_metadata_registration(image, len(metadata.type_definitions))
    modules, code_registration = find_code_gen_modules(image, [img.name for img in metadata.images])
    names = _Namer(image, metadata, registration)

    method_names: dict[int, str] = {}
    namespaces: dict[int, str] = {}
    shared: dict[int, int] = {}
    for method in metadata.methods:
        img = metadata.image_of_type(method.declaring_type)
        module = modules.get(img.name) if img else None
        rid = method.token & 0xFFFFFF
        if module is None or not 1 <= rid <= module.method_pointer_count:
            continue
        slot = module.method_pointers + 8 * (rid - 1)
        # Assemblies without compiled bodies have a null or zero-filled table.
        address = image.pointer(slot) if image.is_mapped(slot) else 0
        if not address:
            continue  # abstract, extern or generic definition: no body
        if address in method_names:
            shared[address] = shared.get(address, 0) + 1
            continue
        method_names[address] = f"{names.type_name(method.declaring_type)}.{method.name}"
        namespaces[address] = metadata.type_definitions[method.declaring_type].namespace
    for address, extra in shared.items():
        method_names[address] += f" (+{extra} sharing this body)"

    # Generic instantiations have no body in per-assembly methodPointers.
    # MetadataRegistration.genericMethodTable maps a MethodSpec index to an
    # index in CodeRegistration.genericMethodPointers (16-byte entries).
    generic_count = image.u32(code_registration + 16)
    generic_pointers = image.pointer(code_registration + 24)
    for i in range(registration.generic_method_table_count):
        spec_index, pointer_index, _, _ = image.unpack("<4i", registration.generic_method_table + 16 * i)
        if not (0 <= spec_index < registration.method_specs_count and 0 <= pointer_index < generic_count):
            continue
        address = image.pointer(generic_pointers + 8 * pointer_index)
        if not address or address in method_names:
            continue
        method_names[address] = names.method_spec(spec_index)

    starts = sorted(set(image.function_starts) | set(method_names))
    slots = _usage_slots(image, metadata, registration)
    # Only sections holding IL2CPP method bodies: runtime/SDK code never
    # touches metadata usage slots, and skipping it halves the scan.
    code = [s for s in image.sections if s.is_code and any(s.addr <= a < s.addr + s.size for a in method_names)]
    functions = _scan_code(image, code, starts, slots, names)
    return Il2CppIndex(
        binary=binary_path.name,
        metadata_version=metadata.version,
        method_names=method_names,
        namespaces=namespaces,
        function_starts=starts,
        functions=functions,
        string_literal_count=len(metadata.string_literals),
        method_count=len(metadata.methods),
    )


class _Namer:
    """Render metadata indices (types, methods, fields, slots) as text."""

    def __init__(self, image: MachOImage, metadata: Metadata, registration: MetadataRegistration) -> None:
        self.image = image
        self.metadata = metadata
        self.registration = registration
        self._type_names: dict[int, str] = {}

    def type_name(self, index: int) -> str:
        cached = self._type_names.get(index)
        if cached is not None:
            return cached
        td = self.metadata.type_definitions[index]
        name = td.name
        if td.declaring_type_index >= 0:
            outer = self._typedef_of_type(td.declaring_type_index)
            if outer is not None and outer != index:
                name = f"{self.type_name(outer)}.{name}"
        self._type_names[index] = name
        return name

    def _type_pointer(self, type_index: int) -> int | None:
        if not 0 <= type_index < self.registration.types_count:
            return None
        return self.image.pointer(self.registration.types + 8 * type_index)

    def _typedef_of_type(self, type_index: int) -> int | None:
        ptr = self._type_pointer(type_index)
        if not ptr:
            return None
        data, bits = self.image.u64(ptr), self.image.u32(ptr + 8)
        kind = (bits >> 16) & 0xFF
        if kind in (0x11, 0x12):
            return data & 0xFFFFFFFF
        if kind == 0x15:  # generic instance: Il2CppGenericClass.type
            inner = self.image.pointer(self.image.decode_pointer(data))
            inner_kind = (self.image.u32(inner + 8) >> 16) & 0xFF
            return self.image.u64(inner) & 0xFFFFFFFF if inner_kind in (0x11, 0x12) else None
        return None

    def il2cpp_type(self, ptr: int, depth: int = 0) -> str:
        if not ptr or depth > 8:
            return "?"
        data, bits = self.image.u64(ptr), self.image.u32(ptr + 8)
        kind = (bits >> 16) & 0xFF
        if kind in (0x11, 0x12):
            index = data & 0xFFFFFFFF
            return self.type_name(index) if index < len(self.metadata.type_definitions) else f"type#{index}"
        if kind == 0x1D:
            return self.il2cpp_type(self.image.decode_pointer(data), depth + 1) + "[]"
        if kind == 0x0F:
            return self.il2cpp_type(self.image.decode_pointer(data), depth + 1) + "*"
        if kind == 0x14:  # Il2CppArrayType: element type first
            return self.il2cpp_type(self.image.pointer(self.image.decode_pointer(data)), depth + 1) + "[,]"
        if kind == 0x15:
            generic_class = self.image.decode_pointer(data)
            base = self.il2cpp_type(self.image.pointer(generic_class), depth + 1)
            return base + self.generic_inst(self.image.pointer(generic_class + 8), depth + 1)
        if kind in (0x13, 0x1E):
            index = data & 0xFFFFFFFF
            names = self.metadata.generic_parameter_names
            return names[index] if index < len(names) else f"T{index}"
        return _PRIMITIVES.get(kind, f"type{kind:#x}")

    def generic_inst(self, inst: int, depth: int = 0) -> str:
        if not inst:
            return ""
        argc, argv = self.image.u64(inst), self.image.pointer(inst + 8)
        if not 0 < argc < 32:
            return "<?>"
        args = [self.il2cpp_type(self.image.pointer(argv + 8 * i), depth) for i in range(argc)]
        return "<" + ", ".join(args) + ">"

    def method_def(self, index: int) -> str:
        method = self.metadata.methods[index]
        return f"{self.type_name(method.declaring_type)}.{method.name}"

    def method_spec(self, index: int) -> str:
        reg = self.registration
        method_index, class_inst, method_inst = self.image.unpack("<3i", reg.method_specs + 12 * index)
        method = self.metadata.methods[method_index]
        owner = self.type_name(method.declaring_type)
        if class_inst >= 0:
            owner += self.generic_inst(self.image.pointer(reg.generic_insts + 8 * class_inst))
        suffix = self.generic_inst(self.image.pointer(reg.generic_insts + 8 * method_inst)) if method_inst >= 0 else ""
        return f"{owner}.{method.name}{suffix}"

    def field_ref(self, index: int) -> str:
        type_index, field_index = self.metadata.field_refs[index]
        typedef = self._typedef_of_type(type_index)
        if typedef is None:
            return f"field#{index}"
        td = self.metadata.type_definitions[typedef]
        names = self.metadata.field_names
        position = td.field_start + field_index
        field_name = names[position] if 0 <= position < len(names) else f"field{field_index}"
        return f"{self.type_name(typedef)}.{field_name}"

    def slot(self, kind: int, index: int) -> str:
        try:
            if kind == 5:
                return self.metadata.string_literals[index]
            if kind in (1, 2):
                return self.il2cpp_type(self._type_pointer(index) or 0)
            if kind == 3:
                return self.method_def(index)
            if kind == 6:
                return self.method_spec(index)
            return self.field_ref(index)
        except (Il2CppError, IndexError, struct.error):
            return f"{USAGE_KINDS[kind]}#{index}"


def decode_usage_token(value: int) -> tuple[int, int] | None:
    """Split an encoded metadata-usage slot value into (kind, index), or
    None when the value is not an unresolved usage token."""
    if value >> 32 or not value & 1:
        return None
    kind = value >> 29
    if kind not in USAGE_KINDS:
        return None
    return kind, (value & 0x1FFFFFFE) >> 1


def _usage_slots(
    image: MachOImage, metadata: Metadata, registration: MetadataRegistration
) -> dict[int, tuple[int, int]]:
    limits = {
        1: registration.types_count,
        2: registration.types_count,
        3: len(metadata.methods),
        4: len(metadata.field_refs),
        5: len(metadata.string_literals),
        6: registration.method_specs_count,
    }
    slots: dict[int, tuple[int, int]] = {}
    for section in image.data_sections():
        blob = image.data[section.offset : section.offset + (section.size & ~7)]
        for i, (value,) in enumerate(struct.iter_unpack("<Q", blob)):
            decoded = decode_usage_token(value)
            if decoded and decoded[1] < limits[decoded[0]]:
                slots[section.addr + 8 * i] = decoded
    return slots


_CALLER_SAVED = tuple(range(19)) + (30,)


def _scan_code(
    image: MachOImage,
    sections: list[Section],
    starts: list[int],
    slots: dict[int, tuple[int, int]],
    namer: _Namer,
) -> dict[int, FunctionXrefs]:
    """Walk code once, attributing slot loads and direct calls to the
    function (by LC_FUNCTION_STARTS) that contains them."""
    start_set = set(starts)
    rendered: dict[int, tuple[str, str]] = {}  # slot -> (kind, text); shared strings keep the index small
    functions: dict[int, FunctionXrefs] = {}

    for section in sections:
        words = struct.unpack_from(f"<{section.size // 4}I", image.data, section.offset)
        pos = bisect.bisect_right(starts, section.addr) - 1
        current = starts[pos] if pos >= 0 else section.addr
        next_start = starts[pos + 1] if pos + 1 < len(starts) else 1 << 64
        pages: dict[int, int] = {}
        fn: FunctionXrefs | None = None
        for k, w in enumerate(words):
            pc = section.addr + 4 * k
            if pc >= next_start:
                pos = bisect.bisect_right(starts, pc) - 1
                current = starts[pos]
                next_start = starts[pos + 1] if pos + 1 < len(starts) else 1 << 64
                pages = {}
                fn = None
            if w & 0x9F000000 == 0x90000000:  # adrp
                imm = ((w >> 29) & 3) | (((w >> 5) & 0x7FFFF) << 2)
                if imm & (1 << 20):
                    imm -= 1 << 21
                pages[w & 31] = (pc & ~0xFFF) + (imm << 12)
                continue
            target = None
            if w & 0xFFC00000 == 0xF9400000:  # ldr xT, [xN, #imm12*8]
                base = pages.get((w >> 5) & 31)
                if base is not None:
                    target = base + ((w >> 10) & 0xFFF) * 8
                pages.pop(w & 31, None)
            elif w & 0xFFC00000 == 0x91000000:  # add xD, xN, #imm12
                base = pages.get((w >> 5) & 31)
                if base is not None:
                    target = base + ((w >> 10) & 0xFFF)
                pages.pop(w & 31, None)
            elif w & 0x7C000000 == 0x14000000:  # b / bl
                imm26 = w & 0x3FFFFFF
                if imm26 & 0x2000000:
                    imm26 -= 0x4000000
                dest = pc + imm26 * 4
                is_bl = bool(w & 0x80000000)
                if dest in start_set and (is_bl or not current <= dest < next_start):
                    if fn is None:
                        fn = functions.setdefault(current, FunctionXrefs(current))
                    fn.calls.append(Call(pc, dest, not is_bl))
                if is_bl:
                    for r in _CALLER_SAVED:
                        pages.pop(r, None)
                continue
            elif w & 0x1C000000 == 0x14000000:  # other branches write no register
                if w & 0xFFFFFC1F == 0xD63F0000:  # blr
                    for r in _CALLER_SAVED:
                        pages.pop(r, None)
                continue
            elif w & 0x0A000000 == 0x08000000:  # loads and stores
                if w & 0x00400000:  # L bit: loads write Rt (and Rt2 for pairs)
                    pages.pop(w & 31, None)
                    pages.pop((w >> 10) & 31, None)
                continue
            else:
                pages.pop(w & 31, None)
            if target is not None and target in slots:
                if fn is None:
                    fn = functions.setdefault(current, FunctionXrefs(current))
                described = rendered.get(target)
                if described is None:
                    kind, index = slots[target]
                    described = rendered[target] = (USAGE_KINDS[kind], namer.slot(kind, index))
                fn.refs.append(Reference(pc, *described))
    return functions


# --------------------------------------------------------------------------
# Bundle entry point + cache

_CACHE_FORMAT = 1
_CACHE_MAX_ENTRIES = 4


def find_il2cpp_files(app_root: Path, main_executable: str) -> tuple[Path, Path]:
    """(code binary, global-metadata.dat) for an extracted .app, or raise."""
    metadata = app_root / METADATA_RELATIVE_PATH
    if not metadata.is_file():
        raise Il2CppError(f"not a Unity IL2CPP app: {METADATA_RELATIVE_PATH} is missing")
    framework = app_root / UNITY_FRAMEWORK_RELATIVE_PATH
    return (framework if framework.is_file() else app_root / main_executable), metadata


def index_for_app(app_root: Path, main_executable: str) -> Il2CppIndex:
    """Build (or load from the content-addressed cache) the index for an app.
    Shares the Mach-O analysis cache's location and ``FORGE_NO_CACHE`` switch."""
    binary, metadata = find_il2cpp_files(app_root, main_executable)
    entry: Path | None = None
    if not objc_cache.disabled():
        digest = hashlib.sha256()
        for path in (binary, metadata):
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 22), b""):
                    digest.update(chunk)
        entry = cache_directory() / f"v{_CACHE_FORMAT}-{digest.hexdigest()}.pickle"
        with contextlib.suppress(OSError, pickle.UnpicklingError, AttributeError, EOFError, ValueError):
            with open(entry, "rb") as f:
                cached: Il2CppIndex = pickle.load(f)
            entry.touch()
            return cached
    index = build_index(binary, metadata)
    if entry is not None:
        with contextlib.suppress(OSError, pickle.PicklingError):
            entry.parent.mkdir(parents=True, exist_ok=True)
            tmp = entry.with_suffix(".pickle.tmp")
            with open(tmp, "wb") as f:
                pickle.dump(index, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(entry)
            stale = sorted(entry.parent.glob("*.pickle"), key=lambda p: p.stat().st_mtime)
            for path in stale[:-_CACHE_MAX_ENTRIES]:
                path.unlink(missing_ok=True)
    return index


def cache_directory() -> Path:
    return objc_cache.cache_dir() / "il2cpp"


def clear_cache() -> int:
    removed = 0
    for entry in cache_directory().glob("*.pickle"):
        entry.unlink(missing_ok=True)
        removed += 1
    return removed


__all__ = [
    "Il2CppError",
    "Il2CppIndex",
    "Metadata",
    "MachOImage",
    "build_index",
    "clear_cache",
    "decode_function_starts",
    "decode_usage_token",
    "find_il2cpp_files",
    "index_for_app",
]
