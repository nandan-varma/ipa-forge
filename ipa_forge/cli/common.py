# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared CLI helpers. The extraction helper lives in the bundle domain
(ipa_forge.bundle.ipa.validate_and_extract); this module re-exports it so
CLI code reads cleanly, and provides the --app-dir resolution used by the
`forge hooks` and `forge analysis` commands to skip re-extraction during
iteration."""

from __future__ import annotations

from pathlib import Path

import typer

from ipa_forge.bundle.ipa import validate_and_extract as validated_extract  # noqa: F401


def resolve_app_path(ipa: Path | None, app_dir: Path | None, dest: Path) -> Path:
    """Return the app bundle to analyze: the already-extracted ``app_dir``
    when given, otherwise extract ``ipa`` into ``dest``.

    Exactly one of the two inputs must be set — passing both is a mistake
    (the dir would silently take precedence over a fresh extract) and passing
    neither leaves nothing to analyze.
    """
    if app_dir is not None and ipa is not None:
        raise ValueError("pass either --ipa or --app-dir, not both")
    if app_dir is not None:
        return app_dir
    if ipa is None:
        raise ValueError("--ipa is required when --app-dir is not given")
    return validated_extract(ipa, dest)


def extract_or_use(ipa: Path | None, app_dir: Path | None, tmp: Path) -> Path:
    """`resolve_app_path`, with resolution errors reported as a clean
    single-line CLI error instead of a traceback."""
    try:
        return resolve_app_path(ipa, app_dir, tmp)
    except ValueError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
