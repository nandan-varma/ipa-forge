"""Recursive bottom-up signing orchestration + provisioning-profile embedding."""
from __future__ import annotations

import shutil
from pathlib import Path

from ipa_forge.bundle.models import AppBundle, MachOTarget
from ipa_forge.signing.profile import ProvisioningProfile
from ipa_forge.signing.provider import SignResult, SigningProvider
from ipa_forge.signing.reconcile import reconcile_entitlements

_BUNDLE_SUFFIX_BY_KIND = {"main": ".app", "framework": ".framework", "appex": ".appex", "watch_app": ".app"}


def sign_target_path(target: MachOTarget) -> Path:
    """The path codesign should actually be pointed at for this target.

    Bundle-kind executables (main app, frameworks, extensions, watch apps)
    must be signed via their *bundle directory*, not the raw executable file
    -- otherwise codesign never creates the bundle-level _CodeSignature/
    CodeResources seal covering Info.plist and other resources, and a later
    `--verify --strict` on the bundle fails with "a sealed resource is
    missing or invalid". Flat dylibs (not wrapped in a bundle) are signed
    directly.
    """
    suffix = _BUNDLE_SUFFIX_BY_KIND.get(target.kind)
    if suffix is None:
        return target.path
    for parent in target.path.parents:
        if parent.name.endswith(suffix):
            return parent
    return target.path


def embed_provisioning_profile(bundle: AppBundle, profile_path: Path) -> None:
    dest = bundle.root / "embedded.mobileprovision"
    shutil.copyfile(profile_path, dest)


def sign_bundle(
    bundle: AppBundle,
    provider: SigningProvider,
    identity: str,
    profile: ProvisioningProfile,
) -> list[SignResult]:
    """Sign every executable bottom-up. `bundle.executables` is already ordered
    deepest-nested-first by the inventory walker, so a naive linear pass over
    it satisfies "sign dependencies before dependents" without hard-coding a
    bundle layout. Each target's own original entitlements are reconciled
    against the supplied profile independently.
    """
    results: list[SignResult] = []
    for target in bundle.executables:
        original_entitlements = provider.dump_entitlements(target.path)
        reconciled = reconcile_entitlements(original_entitlements, profile.entitlements)
        result = provider.sign(sign_target_path(target), reconciled, identity)
        results.append(result)
        if target.kind == "main":
            bundle.entitlements = reconciled
    return results
