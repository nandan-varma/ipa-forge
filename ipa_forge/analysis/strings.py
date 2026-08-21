# SPDX-License-Identifier: GPL-3.0-or-later
"""Printable-string extraction from Mach-O binaries -- `strings <binary>`,
but IPA-aware: runs over every executable in the bundle (main + frameworks +
dylibs + extensions) in one pass, tagging each string with the binary it
came from."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ipa_forge.bundle.models import AppBundle
from ipa_forge.machO.detect import bundle_executable_paths


@dataclass
class ExtractedString:
    value: str
    binary: str  # file name of the executable it was found in


def extract_strings(data: bytes, min_len: int = 4) -> list[str]:
    """Printable-ASCII runs at least `min_len` bytes long, terminated by a
    non-printable/NUL byte -- the same definition classic `strings` uses.
    Wide (UTF-16) string literals are not decoded; documented limitation."""
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % max(min_len, 1))
    return [m.group().decode("ascii") for m in pattern.finditer(data)]


def strings_in_bundle(bundle: AppBundle, min_len: int = 4) -> list[ExtractedString]:
    """Extract strings from every executable in the bundle, main binary
    first, in inventory order thereafter."""
    out: list[ExtractedString] = []
    for path in bundle_executable_paths(bundle):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        out.extend(ExtractedString(s, path.name) for s in extract_strings(data, min_len))
    return out
