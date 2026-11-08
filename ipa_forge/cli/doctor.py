# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only prerequisite checks, scoped to the workflow the user requests."""

from __future__ import annotations

import json
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from ipa_forge.patch.lint import lint_definition
from ipa_forge.patch.loader import PatchLoadError, load_patch_definition
from ipa_forge.patches import discover_patch_sets, patches_root


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    remedy: str = ""


def doctor(
    objc: bool = typer.Option(False, "--objc", help="Also check tools for Objective-C analysis and hooks"),
    signing: bool = typer.Option(False, "--signing", help="Also check signing tools (does not validate credentials)"),
    gui: bool = typer.Option(False, "--gui", help="Also check the configured patch-set root"),
    definition: Path | None = typer.Option(None, "--definition", help="Lint a definition and check its hook tools"),
    json_output: bool = typer.Option(False, "--json", help="Emit structured prerequisite checks"),
) -> None:
    """Check archive tools and optional workflow prerequisites without changing anything.

    Tool presence does not prove a signing identity/profile is valid or a
    hook attaches. Use a dry-run, signing verification, and device testing.
    """
    checks: list[Check] = []
    if definition is not None:
        try:
            lint_definition(definition)
            loaded = load_patch_definition(definition)
            objc = objc or bool(loaded.hooks)
            checks.append(Check("definition", True, str(definition)))
        except PatchLoadError as e:
            checks.append(Check("definition", False, str(e), "Fix the definition, then run forge lint again."))
    tools = ["unzip", "zip"]
    if objc:
        tools += ["lipo", "otool"]
    if signing:
        tools += ["codesign", "security"]
    if objc or signing:
        checks.append(
            Check(
                "macos",
                platform.system() == "Darwin",
                platform.system(),
                "Use macOS with Xcode Command Line Tools for Objective-C analysis or signing.",
            )
        )
    for tool in tools:
        location = shutil.which(tool)
        remedy = (
            "Install Xcode Command Line Tools on macOS: xcode-select --install"
            if tool in {"lipo", "otool", "codesign", "security"}
            else f"Install the {tool} command using your OS package manager."
        )
        checks.append(Check(tool, location is not None, location or "not found on PATH", "" if location else remedy))
    if gui:
        root = patches_root()
        sets = discover_patch_sets(root)
        checks.append(
            Check(
                "patch_sets",
                bool(sets),
                f"{len(sets)} valid patch set(s) in {root}",
                "" if sets else "Set IPA_FORGE_PATCHES_DIR to a directory containing <app>/<app>.yaml and its assets.",
            )
        )
    ok = all(check.ok for check in checks)
    if json_output:
        typer.echo(json.dumps({"schema_version": 1, "ok": ok, "checks": [asdict(c) for c in checks]}, indent=2))
    else:
        for check in checks:
            typer.echo(f"{'OK' if check.ok else 'FAIL'} {check.name}: {check.detail}")
            if not check.ok:
                typer.echo(f"  Fix: {check.remedy}")
        typer.echo("Checks cover tool presence and requested inputs; credentials and device behavior are not verified.")
    raise typer.Exit(code=0 if ok else 1)
