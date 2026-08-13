# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal local web GUI wrapping the same ipa_forge.pipeline used by the CLI.

Single-user, local-only tool -- request state lives in module-level dicts,
which is intentionally not safe for concurrent multi-user deployment (this
is meant to run on localhost next to AltServer, not as a hosted service).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ipa_forge.gui.uploads import UploadError, resolve_patch_definition
from ipa_forge.pipeline import PipelineError, run_pipeline

app = FastAPI(title="ipa-forge")

_WORK_DIR = Path(tempfile.mkdtemp(prefix="ipa_forge_gui_"))
_outputs: dict[str, Path] = {}
_OUTPUTS_MAX = 20

_FORM_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ipa-forge</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
  label { font-weight: 600; }
  #result { margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 6px; white-space: pre-wrap; }
  #result.ok { background: #e6f4ea; border: 1px solid #34a853; }
  #result.error { background: #fce8e6; border: 1px solid #d93025; }
  #result.pending { background: #f1f3f4; border: 1px solid #9aa0a6; }
  #result a { font-weight: 600; }
  button[disabled] { opacity: 0.6; }
</style>
</head>
<body>
<h1>ipa-forge</h1>
<p>Patch and re-sign an IPA for AltStore Classic sideloading.</p>
<form id="patch-form" action="/patch" method="post" enctype="multipart/form-data">
  <p><label>IPA</label><br>
     <input type="file" name="ipa" required></p>
  <p><label>Patch definition</label><br>
     A single .yaml/.yml/.json file, or a .zip of the patch directory
     (definition + assets/) if it uses resource_replace/resource_add.<br>
     <input type="file" name="patches" required></p>
  <p><label>Provisioning profile(s) (.mobileprovision)</label><br>
     Select more than one to provide a separate profile per app
     extension/watch app, matched by bundle id (not needed for dry run).<br>
     <input type="file" name="profile" multiple></p>
  <p><label>Signing identity</label><br>
     SHA-1 or name substring, as shown by
     <code>security find-identity -v -p codesigning</code> (not needed for dry run).<br>
     <input type="text" name="identity"></p>
  <p><label><input type="checkbox" name="dry_run" value="1"> Dry run only (validate patches, no signing)</label></p>
  <p><button id="submit-btn" type="submit">Patch</button></p>
</form>
<div id="result" hidden></div>
<script>
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
  const form = document.getElementById("patch-form");
  const result = document.getElementById("result");
  const btn = document.getElementById("submit-btn");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    btn.disabled = true;
    result.hidden = false;
    result.className = "pending";
    result.textContent = "Processing…";
    try {
      const res = await fetch("/patch", { method: "POST", body: new FormData(form) });
      const body = await res.json();
      if (!res.ok) {
        result.className = "error";
        result.textContent = "Error: " + (body.error || ("HTTP " + res.status));
        return;
      }
      const m = body.manifest || {};
      const ops = (m.patches_applied || [])
        .map((p) => escapeHtml(p.id) + ": " + escapeHtml(p.status))
        .join("\n");
      const title = body.download_url ? "Patched" : "Dry run OK";
      result.className = "ok";
      result.innerHTML =
        "<strong>" + title + "</strong>\n" +
        escapeHtml(m.bundle_id || "") + " v" + escapeHtml(m.version || "") +
        (ops ? "\n" + ops : "") +
        (body.download_url
          ? "\n<a href=\"" + body.download_url + "\">Download patched IPA</a>"
          : "");
    } catch (err) {
      result.className = "error";
      result.textContent = "Request failed: " + err;
    } finally {
      btn.disabled = false;
    }
  });
</script>
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
            _outputs[token] = final_path
            _evict_outputs()
            response["download_url"] = f"/download/{token}"
        return JSONResponse(response)
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)


def _evict_outputs() -> None:
    """Drop the oldest completed outputs once the cap is exceeded."""
    while len(_outputs) > _OUTPUTS_MAX:
        token = next(iter(_outputs))
        path = _outputs.pop(token)
        path.unlink(missing_ok=True)


@app.get("/download/{token}")
def download(token: str):
    path = _outputs.get(token)
    if path is None or not path.is_file():
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, filename=path.name)
