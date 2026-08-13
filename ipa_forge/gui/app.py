# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal local web GUI wrapping the same ipa_forge.pipeline used by the CLI.

Single-user, local-only tool -- request state lives in module-level dicts,
which is intentionally not safe for concurrent multi-user deployment (this
is meant to run on localhost next to AltServer, not as a hosted service).
"""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ipa_forge.pipeline import PipelineError, run_pipeline

app = FastAPI(title="ipa-forge")

_WORK_DIR = Path(tempfile.mkdtemp(prefix="ipa_forge_gui_"))
_outputs: dict[str, Path] = {}

_FORM_HTML = """<!doctype html>
<html>
<head><title>ipa-forge</title></head>
<body style="font-family: sans-serif; max-width: 640px; margin: 2rem auto;">
<h1>ipa-forge</h1>
<p>Patch and re-sign an IPA for AltStore Classic sideloading.</p>
<form action="/patch" method="post" enctype="multipart/form-data">
  <p>IPA: <input type="file" name="ipa" required></p>
  <p>Patch definition (YAML/JSON): <input type="file" name="patches" required></p>
  <p>Provisioning profile (.mobileprovision): <input type="file" name="profile" required></p>
  <p>Signing identity (SHA-1 or name substring): <input type="text" name="identity" required></p>
  <p><label><input type="checkbox" name="dry_run" value="1"> Dry run only</label></p>
  <p><button type="submit">Patch</button></p>
</form>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _FORM_HTML


@app.post("/patch")
async def patch(
    ipa: UploadFile = File(...),
    patches: UploadFile = File(...),
    profile: UploadFile = File(...),
    identity: str = Form(...),
    dry_run: bool = Form(False),
) -> JSONResponse:
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)

    ipa_path = request_dir / ipa.filename
    patches_path = request_dir / patches.filename
    profile_path = request_dir / profile.filename
    for upload, dest in ((ipa, ipa_path), (patches, patches_path), (profile, profile_path)):
        dest.write_bytes(await upload.read())

    output_path = request_dir / f"patched_{ipa_path.name}"

    try:
        result = run_pipeline(ipa_path, patches_path, identity, profile_path, output_path, dry_run=dry_run)
    except PipelineError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    response: dict = {"manifest": json.loads(result.manifest.to_json())}
    if result.output_path is not None:
        token = uuid.uuid4().hex
        _outputs[token] = result.output_path
        response["download_url"] = f"/download/{token}"
    return JSONResponse(response)


@app.get("/download/{token}")
def download(token: str):
    path = _outputs.get(token)
    if path is None or not path.is_file():
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, filename=path.name)
