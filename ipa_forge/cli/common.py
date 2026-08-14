# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared CLI helpers. The extraction helper lives in the bundle domain
(ipa_forge.bundle.ipa.validate_and_extract); this module re-exports it so
CLI code reads cleanly."""

from __future__ import annotations

from ipa_forge.bundle.ipa import validate_and_extract as validated_extract  # noqa: F401
