# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal local web GUI wrapping the same ipa_forge.pipeline used by the CLI.

Single-user, local-only tool -- request state lives in module-level dicts,
which is intentionally not safe for concurrent multi-user deployment (this
is meant to run on localhost next to AltServer, not as a hosted service).
The page itself is a self-contained static template (gui/index.html) with an
inline fetch flow -- no build step, no external assets, works offline.
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

from ipa_forge.gui.uploads import UploadError, resolve_patch_definition
from ipa_forge.pipeline import PipelineError, run_pipeline

app = FastAPI(title="ipa-forge")

_WORK_DIR = Path(tempfile.mkdtemp(prefix="ipa_forge_gui_"))
# token -> (path on disk, display filename for the download response)
_outputs: dict[str, tuple[Path, str]] = {}
_OUTPUTS_MAX = 20


def _package_version() -> str:
    try:
        return _installed_version("ipa-forge")
    except PackageNotFoundError:  # not installed (e.g. run from a source checkout)
        return "0.1.0"


_FORM_HTML = (
    (Path(__file__).parent / "index.html").read_text(encoding="utf-8").replace("__VERSION__", _package_version())
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _FORM_HTML


@app.post("/patch")
async def patch(
    ipa: UploadFile = File(...),
    patches: UploadFile = File(...),
    profile: list[UploadFile] | None = File(None),
    identity: str | None = Form(None),
    dry_run: bool = Form(False),
) -> JSONResponse:
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)
    try:
        # F4: signing inputs are only needed for a real (non-dry-run) run.
        if not dry_run:
            if identity is None or not identity.strip():
                return JSONResponse(status_code=400, content={"error": "identity is required unless dry_run is set"})
            if not profile:
                return JSONResponse(
                    status_code=400,
                    content={"error": "at least one provisioning profile is required unless dry_run is set"},
                )
        # Upload filenames are client-supplied and untrusted -- take only the
        # basename before joining into a filesystem path, or a crafted filename
        # like "../../etc/whatever" could write outside request_dir.
        ipa_path = request_dir / Path(ipa.filename or "upload.ipa").name
        patches_upload_path = request_dir / Path(patches.filename or "patches").name
        ipa_path.write_bytes(await ipa.read())
        patches_upload_path.write_bytes(await patches.read())

        try:
            patches_path = resolve_patch_definition(patches_upload_path, request_dir)
        except UploadError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

        profile_dir = request_dir / "profiles"
        profile_dir.mkdir()
        profile_paths = []
        for i, upload in enumerate(profile or []):
            dest = profile_dir / f"{i}_{Path(upload.filename or 'profile.mobileprovision').name}"
            dest.write_bytes(await upload.read())
            profile_paths.append(dest)

        output_path = request_dir / f"patched_{ipa_path.name}"

        try:
            result = run_pipeline(ipa_path, patches_path, identity or "", profile_paths, output_path, dry_run=dry_run)
        except PipelineError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

        response: dict = {"manifest": json.loads(result.manifest.to_json())}
        if result.output_path is not None:
            # Stash the produced IPA outside the per-request dir (cleaned up
            # in the finally below) so /download can still serve it, bounded
            # by _evict_outputs so long-running sessions don't leak disk.
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
    """Drop the oldest completed outputs once the cap is exceeded."""
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
