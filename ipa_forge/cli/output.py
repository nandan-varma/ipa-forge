# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned JSON for core commands; existing analysis/hook formats stay intact."""

from __future__ import annotations

import json
from typing import Any, NoReturn

import typer


def emit_json(**data: Any) -> None:
    typer.echo(json.dumps({"schema_version": 1, "ok": True, **data}, indent=2))


def fail(message: str, *, json_output: bool = False, code: str = "operation_failed") -> NoReturn:
    message = " ".join(message.splitlines())
    if json_output:
        typer.echo(
            json.dumps({"schema_version": 1, "ok": False, "error": {"code": code, "message": message}}), err=True
        )
    else:
        typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1) from None
