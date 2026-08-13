# SPDX-License-Identifier: GPL-3.0-or-later
"""Upload handling for the GUI's /patch endpoint.

Resolves a single YAML/JSON upload, or a zip of a whole patch directory
(definition file + an assets/ directory alongside it), into a real on-disk
patch-definition path the pipeline can consume -- this is what lets
resource_replace/resource_add operations (which need external source files)
work from the GUI, not just the CLI.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

_PATCH_DEFINITION_SUFFIXES = {".yaml", ".yml", ".json"}

# Generous caps for a patch-directory upload: a real patch bundle is a few
# small YAML files plus assets. Anything near these limits is hostile or
# broken, and unbounded extraction is a zip-bomb risk.
_MAX_ZIP_MEMBERS = 10_000
_MAX_ZIP_UNCOMPRESSED = 512 * 1024 * 1024


class UploadError(Exception):
    """Malformed or unsafe upload -- client input, surfaced as HTTP 400."""


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract zip_path into dest_dir, rejecting any entry that would escape it.

    zipfile.extractall() alone is not a reliable guard against zip-slip
    (entries containing `../` or absolute paths) across all versions, so
    every member's resolved destination is checked before anything is
    written. Extraction failures are translated to UploadError so callers
    surface a 400, never a 500.
    """
    dest_dir = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        if len(members) > _MAX_ZIP_MEMBERS:
            raise UploadError(f"zip contains {len(members)} entries; limit is {_MAX_ZIP_MEMBERS}")
        total_size = sum(m.file_size for m in members)
        if total_size > _MAX_ZIP_UNCOMPRESSED:
            raise UploadError(f"zip uncompressed size {total_size} bytes exceeds limit of {_MAX_ZIP_UNCOMPRESSED}")
        for member in members:
            target = (dest_dir / member.filename).resolve()
            if target != dest_dir and dest_dir not in target.parents:
                raise UploadError(f"zip entry '{member.filename}' escapes the extraction directory")
        try:
            zf.extractall(dest_dir)
        except (OSError, zipfile.BadZipFile) as e:
            raise UploadError(f"failed to extract zip: {e}") from e


def resolve_patch_definition(upload_path: Path, dest_dir: Path) -> Path:
    """upload_path is either a single .yaml/.yml/.json patch definition, or a
    .zip containing one alongside its assets. Returns the path to the patch
    definition file to hand to the pipeline -- its parent directory is where
    resource_replace/resource_add `source:` paths resolve from.
    """
    suffix = upload_path.suffix.lower()
    if suffix in _PATCH_DEFINITION_SUFFIXES:
        return upload_path

    if suffix != ".zip":
        raise UploadError(f"patch upload must be .yaml/.yml/.json or .zip, got '{upload_path.name}'")

    extract_dir = dest_dir / "patches_bundle"
    extract_dir.mkdir()
    safe_extract_zip(upload_path, extract_dir)

    candidates = [p for p in extract_dir.iterdir() if p.suffix.lower() in _PATCH_DEFINITION_SUFFIXES]
    if len(candidates) == 0:
        raise UploadError("zip did not contain a top-level .yaml/.yml/.json patch definition")
    if len(candidates) > 1:
        raise UploadError(
            f"zip contains multiple top-level patch definitions ({[c.name for c in candidates]}); "
            "it must contain exactly one"
        )
    return candidates[0]
