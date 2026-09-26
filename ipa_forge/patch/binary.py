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


_MAX_REPORTED_OFFSETS = 10


def format_offsets(offsets: list[int]) -> str:
    """Render match offsets for an error message, capped.

    An over-broad pattern can match tens of thousands of times (a bare `00`
    matches ~64k times in a small binary); the full list made a single-line
    error message megabytes long, and that message travels into PipelineError
    and the manifest verbatim.
    """
    shown = ", ".join(hex(o) for o in offsets[:_MAX_REPORTED_OFFSETS])
    remaining = len(offsets) - _MAX_REPORTED_OFFSETS
    if remaining > 0:
        return f"[{shown}, ... and {remaining} more]"
    return f"[{shown}]"


def find_matches(haystack: bytes, pattern: bytes, mask: bytes, start: int = 0, end: int | None = None) -> list[int]:
    """Return absolute offsets in `haystack` where `pattern` (respecting `mask`)
    matches, restricted to the [start, end) window."""
    end = len(haystack) if end is None else end
    plen = len(pattern)
    offsets = []
    # Exact instruction windows are common in large game binaries. Keep the
    # masked path for wildcards, but let bytes.find scan exact patterns in C.
    if plen and len(mask) == plen and all(m == 0xFF for m in mask) and 0 <= start <= end <= len(haystack):
        offset = haystack.find(pattern, start, end)
        while offset != -1:
            offsets.append(offset)
            offset = haystack.find(pattern, offset + 1, end)
        return offsets
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
    note: str = ""
    """Why this patch exists, in the author's words -- carried into the manifest
    so a build records its own rationale."""
    symbol: str | None = None
    """The function this window lives in, when known (e.g. a demangled name from
    a disassembler). Recorded in the manifest; never used for matching."""

    def _resolve_target(self, ctx: PatchContext) -> Path:
        for target in ctx.bundle.executables:
            if Path(target.bundle_relative).name == self.executable:
                return target.path
        raise FileNotFoundError(f"executable '{self.executable}' not found in bundle inventory")

    def validate_patterns(self) -> bytes:
        """Parse `pattern`/`replacement` and check they agree, returning the
        replacement bytes.

        Runs from `_plan`, so `dry_run` sees every malformed-input failure that
        `apply` would: a bad hex token used to raise PatternError straight out
        of `apply` (a traceback, after earlier operations had already mutated
        the tree) and a length mismatch used to pass the gate and fail on apply.
        Needs no bundle, so `forge lint` can call it without an IPA.
        """
        pattern, _ = parse_hex_pattern(self.pattern)
        replacement, replacement_mask = parse_hex_pattern(self.replacement)
        if 0 in replacement_mask:
            raise PatternError(
                "'??' wildcards are not allowed in a replacement -- a wildcard there would write 0x00 "
                "rather than keep the original byte; spell out the byte you want"
            )
        if len(replacement) != len(pattern):
            raise PatternError(f"replacement length ({len(replacement)}) must equal pattern length ({len(pattern)})")
        return replacement

    def _plan(self, ctx: PatchContext) -> tuple[Path, bytes, bytes, list[int]]:
        replacement = self.validate_patterns()
        target_path = self._resolve_target(ctx)
        start, end = slice_byte_range(target_path, self.arch)
        data = target_path.read_bytes()
        pattern, mask = parse_hex_pattern(self.pattern)
        offsets = find_matches(data, pattern, mask, start=start, end=end)
        return target_path, data, replacement, offsets

    def _check_match_count(self, offsets: list[int]) -> str | None:
        if len(offsets) != self.expected_matches:
            return (
                f"expected {self.expected_matches} match(es), found {len(offsets)} at offsets {format_offsets(offsets)}"
            )
        return None

    def _details(self, offsets: list[int], data: bytes, replacement: bytes) -> dict[str, object]:
        """Byte-level record of what this op did, for the manifest: where it
        matched and the exact before/after bytes. This is the evidence a
        reviewer needs to confirm a binary patch without re-deriving it."""
        details: dict[str, object] = {
            "offsets": [hex(o) for o in offsets],
            "before": data[offsets[0] : offsets[0] + len(replacement)].hex(" ") if offsets else "",
            "after": replacement.hex(" "),
        }
        if len(offsets) > 1:
            details["before_by_offset"] = [data[o : o + len(replacement)].hex(" ") for o in offsets]
        if self.note:
            details["note"] = self.note
        if self.symbol:
            details["symbol"] = self.symbol
        return details

    def dry_run(self, ctx: PatchContext) -> PatchResult:
        try:
            target_path, data, replacement, offsets = self._plan(ctx)
        except (FileNotFoundError, PatternError, NotMachOError, AmbiguousArchError, ArchNotFoundError) as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))

        error = self._check_match_count(offsets)
        if error:
            return PatchResult(op_id=self.op_id, status="failed", message=error)
        details = self._details(offsets, data, replacement)
        details["file"] = str(target_path.resolve().relative_to(ctx.bundle.root.resolve()))
        return PatchResult(op_id=self.op_id, status="dry_run_ok", details=details)

    def apply(self, ctx: PatchContext) -> PatchResult:
        try:
            target_path, data, replacement, offsets = self._plan(ctx)
        except (FileNotFoundError, PatternError, NotMachOError, AmbiguousArchError, ArchNotFoundError) as e:
            return PatchResult(op_id=self.op_id, status="failed", message=str(e))

        error = self._check_match_count(offsets)
        if error:
            return PatchResult(op_id=self.op_id, status="failed", message=error)

        details = self._details(offsets, data, replacement)
        details["file"] = str(target_path.resolve().relative_to(ctx.bundle.root.resolve()))
        buf = bytearray(data)
        for offset in offsets:
            buf[offset : offset + len(replacement)] = replacement
        target_path.write_bytes(bytes(buf))

        return PatchResult(
            op_id=self.op_id,
            status="applied",
            message=f"replaced {len(offsets)} match(es) at {format_offsets(offsets)}",
            files_touched=[target_path],
            macho_modified=True,
            category="modified",
            details=details,
        )
