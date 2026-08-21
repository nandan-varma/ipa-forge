# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only Mach-O security/build posture: PIE, encryption-flag detection
(never decryption -- see the module docstring boundary in
`ipa_forge.analysis`), stack protector, an ARC heuristic, min-OS, and
platform. The same kind of static check `otool -l`/jtool2's `--sig` print,
as structured data instead of text to grep."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lief

from ipa_forge.machO.arch import arch_name, load_macho


@dataclass
class SecurityPosture:
    binary: str
    arch: str
    pie: bool
    # True when LC_ENCRYPTION_INFO(_64)'s cryptid != 0 -- an App Store binary
    # pulled without prior decryption. Detection only; this tool never
    # decrypts it (see ROADMAP.md for why that is out of scope).
    encrypted: bool
    stack_protector: bool  # ___stack_chk_fail imported
    arc_heuristic: bool  # _objc_storeStrong/_objc_release imported (best-effort, not definitive)
    min_os: str | None
    platform: str | None


def analyze_security(path: Path, arch: str | None = None) -> SecurityPosture:
    binary = load_macho(path, arch)
    imported = {str(s.name) for s in binary.symbols if s.category == lief.MachO.Symbol.CATEGORY.UNDEFINED}

    enc = binary.encryption_info
    encrypted = enc is not None and enc.crypt_id != 0

    min_os: str | None = None
    platform: str | None = None
    bv = binary.build_version
    vm = binary.version_min
    if bv is not None:
        min_os = ".".join(str(n) for n in bv.minos)
        platform = str(bv.platform).rsplit(".", 1)[-1]
    elif vm is not None:
        min_os = ".".join(str(n) for n in vm.version)

    return SecurityPosture(
        binary=path.name,
        arch=arch_name(binary),
        pie=lief.MachO.Header.FLAGS.PIE in binary.header.flags_list,
        encrypted=encrypted,
        stack_protector="___stack_chk_fail" in imported,
        arc_heuristic=bool({"_objc_storeStrong", "_objc_release"} & imported),
        min_os=min_os,
        platform=platform,
    )


def render_security_posture(posture: SecurityPosture) -> str:
    """A short human-readable summary for the CLI."""
    os_bit = f", min {posture.platform} {posture.min_os}" if posture.min_os else ""
    lines = [
        f"{posture.binary} ({posture.arch}){os_bit}",
        f"  PIE:             {'yes' if posture.pie else 'NO'}",
        f"  Encrypted:       {'yes (App Store, undecrypted)' if posture.encrypted else 'no'}",
        f"  Stack protector: {'yes' if posture.stack_protector else 'no'}",
        f"  ARC (heuristic): {'likely' if posture.arc_heuristic else 'unclear / MRC'}",
    ]
    return "\n".join(lines)
