"""Minimal dotted-version comparison for CFBundleShortVersionString matching."""
from __future__ import annotations


def parse_version(v: str) -> tuple[int, ...]:
    parts = []
    for segment in v.split("."):
        digits = "".join(ch for ch in segment if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)
