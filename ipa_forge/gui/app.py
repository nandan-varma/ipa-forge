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

from ipa_forge.analysis.classdump import render_analysis
from ipa_forge.analysis.diff import diff_analyses, render_diff
from ipa_forge.analysis.security import analyze_security, render_security_posture
from ipa_forge.analysis.strings import strings_in_bundle
from ipa_forge.bundle.ipa import load_bundle, validate_and_extract
from ipa_forge.machO.objc import analyze_bundle
from ipa_forge.patches import find_patch_sets_for_bundle
from ipa_forge.pipeline import PipelineError, run_pipeline
from ipa_forge.validators.ipa_validator import IpaValidationError

app = FastAPI(title="ipa-forge")

_WORK_DIR = Path(tempfile.mkdtemp(prefix="ipa_forge_gui_"))
_outputs: dict[str, tuple[Path, str]] = {}
_OUTPUTS_MAX = 20
# GUI textarea sanity cap -- the CLI (forge analysis strings) has no limit
# and pipes to grep instead; a browser tab rendering a multi-million-line
# response is a different failure mode worth guarding against here only.
_STRINGS_GUI_LIMIT = 2000


def _package_version() -> str:
    try:
        return _installed_version("ipa-forge")
    except PackageNotFoundError:
        return "0.1.0"


_FORM_HTML = (
    (Path(__file__).parent / "index.html").read_text(encoding="utf-8").replace("__VERSION__", _package_version())
)
_ANALYSIS_HTML = (
    (Path(__file__).parent / "analysis.html").read_text(encoding="utf-8").replace("__VERSION__", _package_version())
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _FORM_HTML


@app.get("/analysis", response_class=HTMLResponse)
def analysis_page() -> str:
    return _ANALYSIS_HTML


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
            app_path = validate_and_extract(ipa_path, request_dir / "extracted")
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


@app.get("/download/{token}", response_model=None)
def download(token: str) -> FileResponse | JSONResponse:
    entry = _outputs.get(token)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "not found"})
    path, display_name = entry
    if not path.is_file():
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, filename=display_name)


async def _extract_uploaded(request_dir: Path, ipa: UploadFile, name: str = "upload.ipa") -> Path | JSONResponse:
    """Save + extract an uploaded IPA; returns the app path or a 400
    JSONResponse on a structural/plist error, for the analysis endpoints
    below to return directly."""
    ipa_path = request_dir / Path(ipa.filename or name).name
    ipa_path.write_bytes(await ipa.read())
    try:
        return validate_and_extract(ipa_path, request_dir / "extracted")
    except (ValueError, IpaValidationError) as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/analysis/classdump")
async def analysis_classdump(
    ipa: UploadFile = File(...),
    class_name: str | None = Form(None),
    search: str | None = Form(None),
) -> JSONResponse:
    """Read-only Objective-C class-dump view -- same engine as
    `forge analysis classdump`, browsable without installing the CLI."""
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)
    try:
        app_path = await _extract_uploaded(request_dir, ipa)
        if isinstance(app_path, JSONResponse):
            return app_path
        analysis = analyze_bundle(load_bundle(app_path))
        text = render_analysis(analysis, class_filter=class_name or None, search=search or None)
        return JSONResponse({"text": text or "no matching classes/protocols/categories found"})
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)


@app.post("/analysis/strings")
async def analysis_strings(
    ipa: UploadFile = File(...),
    min_len: int = Form(4),
    search: str | None = Form(None),
) -> JSONResponse:
    """Printable-string extraction across every executable in the bundle,
    capped at `_STRINGS_GUI_LIMIT` matches for the browser (the CLI has no
    such cap)."""
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)
    try:
        app_path = await _extract_uploaded(request_dir, ipa)
        if isinstance(app_path, JSONResponse):
            return app_path
        found = strings_in_bundle(load_bundle(app_path), min_len=min_len)
        if search:
            import re

            pat = re.compile(search)
            found = [s for s in found if pat.search(s.value)]
        total = len(found)
        found = found[:_STRINGS_GUI_LIMIT]
        text = "\n".join(f"[{s.binary}] {s.value}" for s in found)
        if total > len(found):
            text += f"\n… truncated ({total} total; use the CLI for the full list)"
        return JSONResponse({"text": text or "no strings found"})
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)


@app.post("/analysis/security")
async def analysis_security(ipa: UploadFile = File(...)) -> JSONResponse:
    """PIE/encryption-flag/stack-protector/ARC posture of the main
    executable -- detection only, this never decrypts anything."""
    request_dir = _WORK_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True)
    try:
        app_path = await _extract_uploaded(request_dir, ipa)
        if isinstance(app_path, JSONResponse):
            return app_path
        bundle = load_bundle(app_path)
        posture = analyze_security(bundle.root / bundle.main_executable_name)
        return JSONResponse({"text": render_security_posture(posture)})
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)


@app.post("/analysis/diff")
async def analysis_diff(old: UploadFile = File(...), new: UploadFile = File(...)) -> JSONResponse:
    """Version-to-version survey between two uploaded builds -- same engine
    as `forge analysis diff`."""
    request_dir = _WORK_DIR / uuid.uuid4().hex
    (request_dir / "old").mkdir(parents=True)
    (request_dir / "new").mkdir(parents=True)
    try:
        old_path = await _extract_uploaded(request_dir / "old", old, "old.ipa")
        if isinstance(old_path, JSONResponse):
            return old_path
        new_path = await _extract_uploaded(request_dir / "new", new, "new.ipa")
        if isinstance(new_path, JSONResponse):
            return new_path
        bundle_old = load_bundle(old_path)
        bundle_new = load_bundle(new_path)
        diff = diff_analyses(
            analyze_bundle(bundle_old), analyze_bundle(bundle_new), bundle_old.info_plist, bundle_new.info_plist
        )
        header = f"{bundle_old.bundle_id} {bundle_old.version} -> {bundle_new.version}\n"
        return JSONResponse({"text": header + render_diff(diff)})
    finally:
        shutil.rmtree(request_dir, ignore_errors=True)
