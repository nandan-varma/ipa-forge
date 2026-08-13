# SPDX-License-Identifier: GPL-3.0-or-later
"""Bottom-up nested-executable inventory walker.

Classification is purely structural (by containing directory suffix), never
by bundle/app identifier -- this keeps the core engine app-agnostic per the
architecture's core rule.
"""
from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.models import AppBundle, MachOKind, MachOTarget
from ipa_forge.bundle.plist import read_plist
from ipa_forge.machO.detect import is_macho_file

_OWNING_BUNDLE_SUFFIX: dict[MachOKind, str] = {"appex": ".appex", "watch_app": ".app"}


def _classify(rel: Path, main_executable_name: str) -> MachOKind:
    parts = rel.parts

    if len(parts) == 1 and parts[0] == main_executable_name:
        return "main"

    # Innermost containing directory determines kind: a dylib inside a
    # .framework is still a "framework" executable, a framework nested
    # inside a watch app is still a "framework", etc.
    for name in reversed(parts[:-1]):
        if name.endswith(".appex"):
            return "appex"
        if name.endswith(".app"):
            return "watch_app"
        if name.endswith(".framework"):
            return "framework"

    if rel.suffix == ".dylib":
        return "dylib"

    return "other"


def _owning_bundle_dir(app_root: Path, rel: Path, kind: MachOKind) -> Path | None:
    """Directory of the bundle (.appex/.app) that owns this target's own
    Info.plist, for kinds that can carry their own provisioning profile."""
    suffix = _OWNING_BUNDLE_SUFFIX.get(kind)
    if suffix is None:
        return None
    parts = rel.parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].endswith(suffix):
            return app_root.joinpath(*parts[: i + 1])
    return None


def _read_bundle_id(bundle_dir: Path) -> str | None:
    try:
        plist = read_plist(bundle_dir / "Info.plist")
    except (OSError, ValueError):
        return None
    bundle_id = plist.get("CFBundleIdentifier")
    return bundle_id if isinstance(bundle_id, str) else None


def build_inventory(bundle: AppBundle) -> list[MachOTarget]:
    """Walk bundle.root for Mach-O executables, returned in bottom-up sign order
    (deepest-nested first; the top-level main executable always last)."""
    app_root = bundle.root
    main_name = bundle.main_executable_name

    targets: list[MachOTarget] = []
    for path in app_root.rglob("*"):
        if not is_macho_file(path):
            continue
        rel = path.relative_to(app_root)
        kind = _classify(rel, main_name)

        if kind == "main":
            target_bundle_id = bundle.bundle_id
        else:
            owning_dir = _owning_bundle_dir(app_root, rel, kind)
            target_bundle_id = _read_bundle_id(owning_dir) if owning_dir else None

        targets.append(
            MachOTarget(
                path=path,
                bundle_relative=str(Path("Payload") / app_root.name / rel),
                kind=kind,
                depth=len(rel.parts),
                bundle_id=target_bundle_id,
            )
        )

    targets.sort(key=lambda t: (t.kind == "main", -t.depth))
    return targets
