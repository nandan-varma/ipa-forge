# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end pipeline orchestration: the 17 stages described in the
architecture doc, from raw .ipa in to AltStore-Classic-ready .ipa out.
"""

from __future__ import annotations

import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa, load_bundle, repack_ipa
from ipa_forge.bundle.models import AppBundle
from ipa_forge.hooks.binary import analyze_bundle
from ipa_forge.hooks.verify import HookDecl, verify_hooks
from ipa_forge.hooks.verify import failing as hook_failures
from ipa_forge.manifest import Manifest, ProfileManifestEntry, sha256_of
from ipa_forge.patch.base import PatchContext
from ipa_forge.patch.engine import apply_all, dry_run_all
from ipa_forge.patch.loader import PatchLoadError, build_operations, load_patch_definition
from ipa_forge.patch.resolver import resolve_definitions
from ipa_forge.patch.schema import PatchDefinition
from ipa_forge.signing.backend import SigningBackendError
from ipa_forge.signing.pipeline import sign_bundle, sign_target_path
from ipa_forge.signing.profile import ProfileError, load_profile_pool, validate_profile
from ipa_forge.signing.provider import LocalIdentityProvider, SigningProvider, VerifyResult, resolve_identity
from ipa_forge.validators.archive_validator import validate_final_archive
from ipa_forge.validators.bundle_validator import validate_bundle
from ipa_forge.validators.ipa_validator import IpaValidationError, validate_ipa_structure


class PipelineError(Exception):
    pass


@dataclass
class PipelineResult:
    manifest: Manifest
    output_path: Path | None
    verify_results: list[VerifyResult] = field(default_factory=list)


def _hook_decls(definition: PatchDefinition) -> list[HookDecl]:
    return [
        HookDecl(
            class_name=h.class_name,
            selector=h.selector,
            kind=h.kind,
            added=h.added,
            required=h.required,
        )
        for h in (definition.hooks or [])
    ]


def _verify_definition_hooks(bundle: AppBundle, definition: PatchDefinition) -> list[dict[str, object]]:
    """Verify the definition's declared hooks against the app's main binary.
    Returns the hook report (list of dicts). Raises PipelineError when a
    required hook cannot attach."""
    decls = _hook_decls(definition)
    if not decls:
        return []
    analysis = analyze_bundle(bundle)
    results = verify_hooks(analysis, decls)
    bad_required = [r for r in hook_failures(results) if r.required]
    if bad_required:
        detail = "; ".join(f"{r.class_name} {r.selector}: {r.status} ({r.detail})" for r in bad_required)
        raise PipelineError(f"required hook verification failed: {detail}")
    return [
        {
            "class": r.class_name,
            "selector": r.selector,
            "kind": r.kind,
            "status": r.status,
            "detail": r.detail,
            "required": r.required,
        }
        for r in results
    ]


def run_pipeline(
    ipa_path: Path,
    patch_definition_path: Path,
    identity_query: str,
    profile_paths: list[Path],
    output_path: Path,
    *,
    provider: SigningProvider | None = None,
    dry_run: bool = False,
    no_sign: bool = False,
    allow_version_mismatch: bool = False,
) -> PipelineResult:
    """profile_paths accepts one or more .mobileprovision files. A single
    profile signs every target, exactly as before per-extension profiles
    existed. Supplying more than one lets nested app extensions / watch apps
    be matched and signed with their own profile by their own bundle id --
    see signing/pipeline.py::sign_bundle and signing/profile.py::ProfilePool."""
    provider = provider or LocalIdentityProvider()

    with tempfile.TemporaryDirectory(prefix="ipa_forge_") as tmp:
        work_dir = Path(tmp)

        # Stages 1-3: validate + extract, inventory, parse Info.plist
        try:
            validate_ipa_structure(ipa_path)
        except IpaValidationError as e:
            raise PipelineError(str(e)) from e
        app_path = extract_ipa(ipa_path, work_dir / "extracted")
        bundle = load_bundle(app_path)
        validate_bundle(bundle)

        # Stage 4: resolve applicable patch definitions (bundle_id + version match)
        try:
            definition = load_patch_definition(patch_definition_path)
        except PatchLoadError as e:
            raise PipelineError(str(e)) from e
        matched = resolve_definitions(bundle, [definition], ignore_version=allow_version_mismatch)
        ops = [op for d in matched for op in build_operations(d)]
        if not ops:
            # F1: a single user-supplied definition that matches nothing is
            # almost always a mistake (typo'd bundle id or version range).
            # Warn in dry-run so version-gate checks still work; refuse to
            # produce an unpatched IPA in a real run.
            warnings.warn(
                f"patch definition '{patch_definition_path}' matches 0 patch operations for "
                f"{bundle.bundle_id} v{bundle.version} (definition targets "
                f"{definition.target.bundle_id}); nothing will be applied",
                stacklevel=2,
            )
            if not dry_run:
                raise PipelineError(
                    f"patch definition '{patch_definition_path}' matches no operations for "
                    f"{bundle.bundle_id} v{bundle.version} (definition targets "
                    f"{definition.target.bundle_id}); refusing to produce an unpatched IPA"
                )

        if (
            allow_version_mismatch
            and bundle.bundle_id == definition.target.bundle_id
            and bundle.version != getattr(definition.target.version, "exact", None)
        ):
            warnings.warn(
                f"version mismatch allowed: definition targets "
                f"{definition.target.bundle_id} "
                f"{getattr(definition.target.version, 'exact', '?')} but the IPA is "
                f"{bundle.bundle_id} v{bundle.version}; hook verification below "
                f"is the safety net",
                stacklevel=2,
            )

        # Stage 4.5: verify declared runtime hooks against the actual binary --
        # catches silent hook no-ops on version drift before anything mutates.
        hook_report = _verify_definition_hooks(bundle, definition)
        ctx = PatchContext(bundle=bundle, patch_source_dir=patch_definition_path.parent)

        # Stage 5: dry-run gate -- hard fail before anything mutates
        dry_results = dry_run_all(ops, ctx)
        failed_dry = [r for r in dry_results if r.status != "dry_run_ok"]
        if failed_dry:
            raise PipelineError(
                "patch dry-run validation failed: " + "; ".join(f"{r.op_id}: {r.message}" for r in failed_dry)
            )

        if dry_run:
            manifest = Manifest.from_patch_results(
                ipa_path, bundle.bundle_id, bundle.version, bundle.build, dry_results
            )
            manifest.hook_report = hook_report
            return PipelineResult(manifest=manifest, output_path=None)

        # Stages 6-8: apply resources -> binary patches -> dylib injection (fixed order)
        results = apply_all(ops, ctx)
        failed_apply = [r for r in results if r.status == "failed"]
        if failed_apply:
            raise PipelineError(
                "patch application failed: " + "; ".join(f"{r.op_id}: {r.message}" for r in failed_apply)
            )

        # Stage 9: re-validate bundle consistency post-mutation
        validate_bundle(bundle)

        # Stage 10: emit manifest, before signing
        manifest = Manifest.from_patch_results(ipa_path, bundle.bundle_id, bundle.version, bundle.build, results)
        manifest.hook_report = hook_report

        if no_sign:
            # Unsigned output for AltStore-style installers, which perform
            # their own signing (and profile generation) at install time.
            # The payload is patched but carries no code signature, matching
            # what AltStore Classic accepts as input.
            repack_ipa(bundle.extraction_root, output_path)
            validate_final_archive(output_path, work_dir / "final_check", expect_profile=False)
            manifest.output_sha256 = sha256_of(output_path)
            return PipelineResult(manifest=manifest, output_path=output_path)

        try:
            # Stage 11: load + validate provisioning profile(s)
            profiles = load_profile_pool(profile_paths)
            main_profile, _ = profiles.select_for(bundle.bundle_id)
            validate_profile(main_profile, bundle.bundle_id)
            manifest.profile = ProfileManifestEntry(
                uuid=main_profile.uuid,
                team_id=main_profile.team_identifier,
                expiration=str(main_profile.expiration_date),
            )

            # Stages 12-13 (entitlement reconciliation + profile embedding, per
            # target -- each profile-bearing target selects its own profile by
            # its own bundle id) and stage 14 (recursive bottom-up codesign):
            identity = resolve_identity(provider, identity_query)
            sign_bundle(bundle, provider, identity, profiles)

            # Stage 15: verify every signed bundle/dylib, then a final deep+strict pass on the app bundle
            sign_paths = {sign_target_path(t) for t in bundle.executables}
            sign_paths.discard(bundle.root)
            verify_results = [provider.verify(p) for p in sign_paths]
            verify_results.append(provider.verify(bundle.root, deep=True))
            failed_verify = [v for v in verify_results if not v.ok]
            if failed_verify:
                raise PipelineError(
                    "codesign verification failed: " + "; ".join(f"{v.target}: {v.message}" for v in failed_verify)
                )
        except (ProfileError, SigningBackendError) as e:
            raise PipelineError(str(e)) from e

        # Stage 16: repackage
        repack_ipa(bundle.extraction_root, output_path)

        # Stage 17: final validation -- re-extract the produced IPA from scratch
        validate_final_archive(output_path, work_dir / "final_check")

        manifest.output_sha256 = sha256_of(output_path)
        return PipelineResult(manifest=manifest, output_path=output_path, verify_results=verify_results)
