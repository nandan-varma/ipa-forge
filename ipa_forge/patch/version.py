# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal dotted-version comparison for CFBundleShortVersionString matching.

Non-numeric segments are stripped ("1.0.0-beta" parses to (1, 0, 0)), so
range matching treats suffixed and clean versions as equal. `VersionExact` in
patch/schema.py deliberately uses raw string equality instead -- exact:
"1.0.0" will not match a bundle whose version is "1.0.0-beta".
"""

from __future__ import annotations


def _parse_segment(digits: str) -> int:
    try:
        return int(digits)
    except ValueError:  # unreachable: digits is already filtered to [0-9]
        return 0


def parse_version(v: str) -> tuple[int, ...]:
    parts = []
    for segment in v.split("."):
        digits = "".join(ch for ch in segment if ch.isdigit())
        parts.append(_parse_segment(digits))
    return tuple(parts)
