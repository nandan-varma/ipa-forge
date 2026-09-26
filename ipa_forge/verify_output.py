# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare Payload inventories and replay the manifest's recorded binary edits."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from ipa_forge.manifest import sha256_of


def _inventory(archive: ZipFile) -> set[str]:
    names = [i.filename for i in archive.infolist() if not i.is_dir() and i.filename.startswith("Payload/")]
    if len(names) != len(set(names)):
        raise ValueError("duplicate Payload archive entries")
    return set(names)


def _archive_path(path: str, prefix: str) -> str:
    # Older manifests recorded temporary extraction paths. New ones are app-relative.
    if path.startswith("Payload/"):
        return path
    if ".app/" in path:
        path = path.split(".app/", 1)[1]
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"invalid manifest file path: {path}")
    return prefix + path


def verify_output(base: Path, output: Path, manifest_path: Path | None = None) -> None:
    manifest = json.loads(manifest_path.read_text()) if manifest_path else {}
    if manifest and manifest.get("input_sha256") != sha256_of(base):
        raise ValueError("base IPA SHA-256 does not match manifest")
    if manifest.get("output_sha256") and manifest["output_sha256"] != sha256_of(output):
        raise ValueError("output IPA SHA-256 does not match manifest")
    with ZipFile(base) as old, ZipFile(output) as new:
        old_names, new_names = _inventory(old), _inventory(new)
        infos = [n for n in old_names if len(PurePosixPath(n).parts) == 3 and n.endswith(".app/Info.plist")]
        if len(infos) != 1:
            raise ValueError("base must contain exactly one Payload app")
        prefix = infos[0].removesuffix("Info.plist")
        if new.testzip() is not None:
            raise ValueError("output ZIP CRC failure")
        added, removed, modified = (
            {_archive_path(p, prefix) for p in manifest.get(key, [])}
            for key in ("files_added", "files_removed", "files_modified")
        )
        added = {n for p in added for n in new_names if n == p or n.startswith(p.rstrip("/") + "/")}
        removed = {n for p in removed for n in old_names if n == p or n.startswith(p.rstrip("/") + "/")}
        if new_names - old_names != added or old_names - new_names != removed:
            raise ValueError("Payload inventory differs from manifest")
        if not modified <= old_names & new_names:
            raise ValueError("manifest modified files are absent from Payload")
        binary_ops: dict[str, list[dict]] = {}
        for op in manifest.get("patches_applied", []):
            if "offsets" in op:
                if op.get("status") != "applied" or not op.get("file"):
                    raise ValueError(f"{op.get('id')}: binary evidence requires an applied manifest with a file path")
                name = _archive_path(op["file"], prefix)
                if name not in modified:
                    raise ValueError(f"{name}: binary edit is not declared modified")
                binary_ops.setdefault(name, []).append(op)
        for name in sorted(old_names & new_names):
            before, after = old.read(name), new.read(name)
            if name in binary_ops:
                expected = bytearray(before)
                for op in binary_ops[name]:
                    replacement = bytes.fromhex(op["after"])
                    windows = op.get("before_by_offset", [op["before"]] * len(op["offsets"]))
                    if len(windows) != len(op["offsets"]):
                        raise ValueError(f"{op['id']}: inconsistent binary evidence")
                    for offset, window in zip(op["offsets"], windows, strict=True):
                        start = int(offset, 16)
                        original = bytes.fromhex(window)
                        if len(original) != len(replacement) or not 0 <= start <= len(expected) - len(original):
                            raise ValueError(f"{op['id']}: invalid binary edit range")
                        if expected[start : start + len(original)] != original:
                            raise ValueError(f"{op['id']}: original bytes differ at {offset}")
                        expected[start : start + len(replacement)] = replacement
                if after != expected:
                    raise ValueError(f"{name}: output binary differs from recorded edits")
            elif name not in modified and before != after:
                raise ValueError(f"unexpected file change: {name}")
