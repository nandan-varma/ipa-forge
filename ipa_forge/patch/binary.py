# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic byte-pattern binary patching, bounded to a specific arch slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ipa_forge.machO.arch import (
    AmbiguousArchError,
    ArchNotFoundError,
    NotMachOError,
    slice_byte_range,
)
from ipa_forge.patch.base import PatchContext, PatchResult


class PatternError(Exception):
    pass


def parse_hex_pattern(pattern: str) -> tuple[bytes, bytes]:
    """Parse a space-separated hex byte pattern with `??` as a wildcard byte.

    Returns (bytes, mask) where mask[i] == 0xFF means that byte must match
    exactly and mask[i] == 0x00 means "don't care".
    """
    tokens = pattern.split()
    if not tokens:
        raise PatternError("empty pattern")
    data = bytearray()
    mask = bytearray()
    for tok in tokens:
        if tok == "??":
            data.append(0)
            mask.append(0)
            continue
        try:
            value = int(tok, 16)
        except ValueError as e:
            raise PatternError(f"invalid hex byte token '{tok}'") from e
        if not 0 <= value <= 0xFF:
            raise PatternError(f"byte token '{tok}' out of range")
        data.append(value)
        mask.append(0xFF)
    return bytes(data), bytes(mask)


def find_matches(haystack: bytes, pattern: bytes, mask: bytes, start: int = 0, end: int | None = None) -> list[int]:
    """Return absolute offsets in `haystack` where `pattern` (respecting `mask`)
    matches, restricted to the [start, end) window."""
    end = len(haystack) if end is None else end
    plen = len(pattern)
    offsets = []
    for i in range(start, end - plen + 1):
        window = haystack[i : i + plen]
        if all((b & m) == (p & m) for b, p, m in zip(window, pattern, mask, strict=True)):
            offsets.append(i)
    return offsets


@dataclass
class BinaryReplaceOp:
    op_id: str
    executable: str
    pattern: str
    replacement: str
    expected_matches: int = 1
    arch: str | None = None

    def _resolve_target(self, ctx: PatchContext) -> Path:
        for target in ctx.bundle.executables:
            if Path(target.bundle_relative).name == self.executable:
                return target.path
        raise FileNotFoundError(f"executable '{self.executable}' not found in bundle inventory")

    def _plan(self, ctx: PatchContext) -> tuple[Path, bytes, bytes, bytes, list[int]]:
        target_path = self._resolve_target(ctx)
        start, end = slice_byte_range(target_path, self.arch)
        data = target_path.read_bytes()
        pattern, mask = parse_hex_pattern(self.pattern)
        offsets = find_matches(data, pattern, mask, start=start, end=end)
        return target_path, data, pattern, mask, offsets

    def _check_match_count(self, offsets: list[int]) -> str | None:
        if len(offsets) != self.expected_matches:
            return f"expected {self.expected_matches} match(es), found {len(offsets)} at offsets {offsets}"
        return None

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            _, _, _, _, offsets = self._plan(ctx)
        except (FileNotFoundError, PatternError, NotMachOError, AmbiguousArchError, ArchNotFoundError) as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))

        error = self._check_match_count(offsets)
        if error:
            return PatchResult(op_id=self.op_id, status="failed", message=error)
        return PatchResult(op_id=self.op_id, status="dry_run_ok")

    def apply(self, ctx: PatchContext) -> PatchResult:
        try:
            target_path, data, pattern, _, offsets = self._plan(ctx)
        except (FileNotFoundError, PatternError, NotMachOError, AmbiguousArchError, ArchNotFoundError) as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))

        error = self._check_match_count(offsets)
        if error:
            return PatchResult(op_id=self.op_id, status="failed", message=error)

        replacement, _ = parse_hex_pattern(self.replacement)
        if len(replacement) != len(pattern):
            return PatchResult(
                op_id=self.op_id,
                status="failed",
                message=f"replacement length ({len(replacement)}) must equal pattern length ({len(pattern)})",
            )

        buf = bytearray(data)
        for offset in offsets:
            buf[offset : offset + len(replacement)] = replacement
        target_path.write_bytes(bytes(buf))

        return PatchResult(
            op_id=self.op_id,
            status="applied",
            message=f"replaced {len(offsets)} match(es) at {offsets}",
            files_touched=[target_path],
            macho_modified=True,
            category="modified",
        )
