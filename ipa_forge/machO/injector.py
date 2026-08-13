"""LIEF-backed dylib load-command injection.

Modifies the target Mach-O's load commands only -- copying the dylib file
into the bundle (if it isn't already present) is a separate `resource_add`
patch operation, and re-signing (required because LIEF's rewrite invalidates
any existing code signature) happens later in the pipeline's signing stage.
Never silently continues past a load-command failure: every outcome maps to
one of the four explicit statuses below.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

import lief

from ipa_forge.machO.arch import AmbiguousArchError, ArchNotFoundError, NotMachOError, arch_name


class InjectionStatus(enum.Enum):
    INJECTED = "INJECTED"
    INJECTION_SKIPPED = "INJECTION_SKIPPED"
    INJECTION_UNSUPPORTED = "INJECTION_UNSUPPORTED"
    INJECTION_FAILED = "INJECTION_FAILED"


@dataclass
class InjectionResult:
    status: InjectionStatus
    message: str = ""


_FACTORY_BY_LOAD_COMMAND = {
    "LC_LOAD_DYLIB": lief.MachO.DylibCommand.load_dylib,
    "LC_LOAD_WEAK_DYLIB": lief.MachO.DylibCommand.weak_lib,
}


def _select_slice(fat: lief.MachO.FatBinary, arch: str | None) -> lief.MachO.Binary:
    """Like machO.arch.load_macho, but keeps the FatBinary container so the
    caller can write it back whole -- writing an individually-selected slice
    directly (`binary.write(path)`) discards every *other* slice in a
    universal binary, silently corrupting it."""
    if len(fat) == 1:
        return fat.at(0)

    available = [arch_name(fat.at(i)) for i in range(len(fat))]
    if arch is None:
        raise AmbiguousArchError(
            f"universal binary with architectures {available}; an explicit `arch:` selector is required"
        )
    for i in range(len(fat)):
        binary = fat.at(i)
        if arch_name(binary) == arch:
            return binary
    raise ArchNotFoundError(f"architecture '{arch}' not found; available: {available}")


def inject_dylib(
    target_path: Path,
    dylib_install_name: str,
    arch: str | None = None,
    load_command: str = "LC_LOAD_DYLIB",
) -> InjectionResult:
    if load_command not in _FACTORY_BY_LOAD_COMMAND:
        return InjectionResult(InjectionStatus.INJECTION_FAILED, f"unknown load_command '{load_command}'")

    fat = lief.MachO.parse(str(target_path))
    if fat is None or len(fat) == 0:
        return InjectionResult(InjectionStatus.INJECTION_UNSUPPORTED, f"{target_path} is not a valid Mach-O file")

    try:
        binary = _select_slice(fat, arch)
    except NotMachOError as e:
        return InjectionResult(InjectionStatus.INJECTION_UNSUPPORTED, str(e))
    except (AmbiguousArchError, ArchNotFoundError) as e:
        return InjectionResult(InjectionStatus.INJECTION_FAILED, str(e))

    if dylib_install_name in {lib.name for lib in binary.libraries}:
        return InjectionResult(InjectionStatus.INJECTION_SKIPPED, f"{dylib_install_name} is already loaded")

    try:
        command = _FACTORY_BY_LOAD_COMMAND[load_command](dylib_install_name)
        if binary.add(command) is None:
            return InjectionResult(InjectionStatus.INJECTION_FAILED, "LIEF failed to add the load command")
        fat.write(str(target_path))
    except Exception as e:  # LIEF raises broad/internal exception types on malformed input
        return InjectionResult(InjectionStatus.INJECTION_FAILED, f"LIEF injection failed: {e}")

    return InjectionResult(InjectionStatus.INJECTED, f"added {load_command} {dylib_install_name}")
