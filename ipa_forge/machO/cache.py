# SPDX-License-Identifier: GPL-3.0-or-later
"""Content-addressed disk cache for `MachOAnalysis`.

Parsing the Objective-C class table of a real app binary costs seconds
(measured: 7.6s for a 228MB main executable), and a porting session runs
dozens of queries against the *same* unchanged binary -- `forge hooks
find`/`verify`, `forge analysis classdump`, and every `--dry-run`.
Each one re-did the identical parse.

Entries are keyed by the SHA-256 of the binary file, so a cache hit survives
re-extracting the same IPA into a different temporary directory, and a
changed binary can never hit a stale entry. The key also carries a format
version: when the dataclasses in `objc.py` change shape, old entries become
unreadable rather than wrong.

`raw_data` (the binary's full bytes) is deliberately *not* stored -- it is
the bulk of the object and re-reading it from disk costs ~0.07s, while
turning it into something smaller (a set of cstrings) costs 7s, i.e. as much
as the parse being avoided. The caller restores it on a hit.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ipa_forge.machO.objc import MachOAnalysis

_FORMAT_VERSION = 1
"""Bump when MachOAnalysis or any dataclass it holds changes shape."""

_MAX_ENTRIES = 16
"""Entries are large (tens of MB for a big app). Cap the directory and evict
the least recently used, so iterating over many app versions cannot grow the
cache without bound."""


def disabled() -> bool:
    """True when ``FORGE_NO_CACHE`` is set to anything non-empty.

    An environment variable rather than a `--no-cache` flag on all eight
    analysis-backed commands: the cache is keyed by content hash, so a stale
    hit is not a failure mode a user has to defend against day to day. The
    escape hatch exists for working on the parser itself and for read-only
    filesystems -- `forge cache --clear` covers "I want the disk back".
    """
    return bool(os.environ.get("FORGE_NO_CACHE"))


def cache_dir() -> Path:
    """Cache location: ``$FORGE_CACHE_DIR``, else ``$XDG_CACHE_HOME/ipa-forge``,
    else ``~/.cache/ipa-forge``. Tests point FORGE_CACHE_DIR at a tmpdir."""
    override = os.environ.get("FORGE_CACHE_DIR")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "ipa-forge"


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _entry_path(path: Path) -> Path:
    return cache_dir() / "objc" / f"v{_FORMAT_VERSION}-{_sha256_of(path)}.pickle"


def _evict_over_cap(directory: Path) -> None:
    entries = sorted(directory.glob("*.pickle"), key=lambda p: p.stat().st_mtime)
    for stale in entries[:-_MAX_ENTRIES]:
        stale.unlink(missing_ok=True)


def load(path: Path) -> MachOAnalysis | None:
    """Return the cached analysis for `path`, or None on a miss.

    Any failure -- unreadable entry, a pickle written by an incompatible
    version, a truncated file from an interrupted write -- is a miss, never an
    error: a broken cache must not break the command.
    """
    if disabled():
        return None
    try:
        entry = _entry_path(path)
        with open(entry, "rb") as f:
            analysis: MachOAnalysis = pickle.load(f)
    except (OSError, pickle.UnpicklingError, AttributeError, EOFError, ValueError):
        return None
    # Mark the entry as recently used, for the eviction order.
    with contextlib.suppress(OSError):
        entry.touch()
    return analysis


def store(path: Path, analysis: MachOAnalysis) -> None:
    """Cache `analysis` for `path`. Best-effort: a full disk or a read-only
    cache directory must not fail the command that produced the analysis."""
    if disabled():
        return
    raw_data, main_executable = analysis.raw_data, analysis.main_executable
    try:
        entry = _entry_path(path)
        entry.parent.mkdir(parents=True, exist_ok=True)
        # raw_data is restored by the caller from disk; main_executable is a
        # path into a temporary extraction directory that will not exist next
        # run, so neither belongs in a shared entry.
        analysis.raw_data = []
        analysis.main_executable = None
        tmp = entry.with_suffix(".pickle.tmp")
        with open(tmp, "wb") as f:
            pickle.dump(analysis, f, protocol=pickle.HIGHEST_PROTOCOL)
        # Atomic publish: a reader never sees a half-written entry.
        tmp.replace(entry)
        _evict_over_cap(entry.parent)
    except (OSError, pickle.PicklingError):
        pass
    finally:
        analysis.raw_data, analysis.main_executable = raw_data, main_executable


def clear() -> int:
    """Delete every cached entry, returning how many were removed."""
    removed = 0
    for entry in cache_dir().glob("objc/*.pickle"):
        entry.unlink(missing_ok=True)
        removed += 1
    return removed
