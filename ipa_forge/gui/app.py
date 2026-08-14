# SPDX-License-Identifier: GPL-3.0-or-later
"""Local web GUI wrapping the same ipa_forge.pipeline used by the CLI.

Novice flow: pick an IPA file -> the GUI auto-detects the app and the
matching patch set, warns (non-blocking) if the patch set targets a
different version, then one "Patch" button produces an unsigned IPA for
AltStore. No signing identity, no profiles, no YAML editing required.

Single-user, local-only: request state lives in module-level dicts. The page
is a self-contained static template (gui/index.html) with an inline fetch
flow — no build step, works offline.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ipa_forge.bundle.ipa import load_bundle
from ipa_forge.cli.common import validated_extract
from ipa_forge.patches import find_patch_sets_for_bundle
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.validators.ipa_validator import IpaValidationError

app = FastAPI(title="ipa-forge")

_WORK_DIR = Path(tempfile.mkdtemp(prefix="ipa_forge_gui_"))
_outputs: dict[str, tuple[Path, str]] = {}
_OUTPUTS_MAX = 20


def _package_version() -> str:
    try:
        return _installed_version("ipa-forge")
    except PackageNotFoundError:
        return "0.1.0"


_FORM_HTML = (
    (Path(__file__).parent / "index.html").read_text(encoding="utf-8").replace("__VERSION__", _package_version())
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _FORM_HTML


@app.post("/detect")
async def detect(ipa: UploadFile = File(...)) -> JSONResponse:
    """Analyze an uploaded IPA: bundle id, version, matching patch sets, and
    a version-mismatch warning (informational — patching is still allowed)."""
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)
    try:
        ipa_path = request_dir / Path(ipa.filename or "upload.ipa").name
        ipa_path.write_bytes(await ipa.read())
        try:
            app_path = validated_extract(ipa_path, request_dir / "extracted")
            bundle = load_bundle(app_path)
        except (ValueError, IpaValidationError) as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

        patch_sets = []
        for ps in find_patch_sets_for_bundle(bundle.bundle_id):
            match = ps.version_exact is None or ps.version_exact == bundle.version
            patch_sets.append(
                {
                    "name": ps.name,
                    "target_version": ps.version_exact or ps.version_spec,
                    "matches": match,
                }
            )
        return JSONResponse(
            {
                "bundle_id": bundle.bundle_id,
                "version": bundle.version,
                "build": bundle.build,
                "patch_sets": patch_sets,
                # a warning when the app has a patch set but the version differs
                "mismatch": bool(patch_sets) and not any(p["matches"] for p in patch_sets),
            }
        )
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)


@app.post("/patch")
async def patch(
    ipa: UploadFile = File(...),
    patch_set: str = Form(...),
    identity: str | None = Form(None),
    profile: list[UploadFile] | None = File(None),
    dry_run: bool = Form(False),
    no_sign: bool = Form(True),
) -> JSONResponse:
    """Patch an IPA with a discovered patch set. Defaults to unsigned output
    for AltStore (no identity/profile needed); the version-mismatch warning
    is non-blocking — the hooks gate still guards what attaches."""
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)
    try:
        ipa_path = request_dir / Path(ipa.filename or "upload.ipa").name
        ipa_path.write_bytes(await ipa.read())

        from ipa_forge.patches import discover_patch_sets

        definition = None
        for ps in discover_patch_sets():
            if ps.name == patch_set:
                definition = ps.definition
                break
        if definition is None:
            return JSONResponse(status_code=400, content={"error": f"unknown patch set '{patch_set}'"})

        profile_paths: list[Path] = []
        if not dry_run and not no_sign:
            if not identity or not identity.strip():
                return JSONResponse(status_code=400, content={"error": "identity is required for signed output"})
            if not profile:
                return JSONResponse(
                    status_code=400, content={"error": "at least one profile is required for signed output"}
                )
            profile_dir = request_dir / "profiles"
            profile_dir.mkdir()
            for i, upload in enumerate(profile or []):
                dest = profile_dir / f"{i}_{Path(upload.filename or 'profile.mobileprovision').name}"
                dest.write_bytes(await upload.read())
                profile_paths.append(dest)

        output_path = request_dir / f"patched_{ipa_path.name}"
        try:
            result = run_pipeline(
                ipa_path,
                definition,
                identity or "",
                profile_paths,
                output_path,
                dry_run=dry_run,
                no_sign=no_sign,
                allow_version_mismatch=True,
            )
        except PipelineError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

        response: dict = {"manifest": json.loads(result.manifest.to_json())}
        if result.output_path is not None:
            token = uuid.uuid4().hex
            final_path = _WORK_DIR / f"{token}.ipa"
            result.output_path.replace(final_path)
            _outputs[token] = (final_path, f"patched_{ipa_path.name}")
            _evict_outputs()
            response["download_url"] = f"/download/{token}"
        return JSONResponse(response)
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)


def _evict_outputs() -> None:
    while len(_outputs) > _OUTPUTS_MAX:
        token = next(iter(_outputs))
        path, _ = _outputs.pop(token)
        path.unlink(missing_ok=True)


@app.get("/download/{token}")
def download(token: str):
    entry = _outputs.get(token)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "not found"})
    path, display_name = entry
    if not path.is_file():
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, filename=display_name)
