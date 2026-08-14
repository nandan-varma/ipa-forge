# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared CLI helpers (no typer coupling)."""

from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa
from ipa_forge.validators.ipa_validator import IpaValidationError, validate_ipa_structure


def validated_extract(ipa: Path, dest: Path) -> Path:
    """Structure-validate (pipeline stage 1), then extract — surfacing a clean
    error instead of a traceback for malformed input."""
    try:
        validate_ipa_structure(ipa)
    except IpaValidationError as e:
        raise ValueError(str(e)) from e
    return extract_ipa(ipa, dest)
