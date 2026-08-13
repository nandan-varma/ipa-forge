# SPDX-License-Identifier: GPL-3.0-or-later
"""Recursive bottom-up signing orchestration + per-bundle provisioning-profile embedding."""
from __future__ import annotations

import shutil
from pathlib import Path

from ipa_forge.bundle.models import AppBundle, MachOTarget
from ipa_forge.signing.profile import ProfilePool
from ipa_forge.signing.provider import SignResult, SigningProvider
from ipa_forge.signing.reconcile import reconcile_entitlements

_BUNDLE_SUFFIX_BY_KIND = {"main": ".app", "framework": ".framework", "appex": ".appex", "watch_app": ".app"}

# Kinds that own their own Info.plist and can therefore carry their own
# embedded.mobileprovision. Frameworks/dylibs/other are signed but never
# embed a profile of their own.
_PROFILE_BEARING_KINDS = {"main", "appex", "watch_app"}


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


def embed_provisioning_profile(bundle_dir: Path, profile_path: Path) -> None:
    dest = bundle_dir / "embedded.mobileprovision"
    shutil.copyfile(profile_path, dest)


def sign_bundle(
    bundle: AppBundle,
    provider: SigningProvider,
    identity: str,
    profiles: ProfilePool,
) -> list[SignResult]:
    """Sign every executable bottom-up. `bundle.executables` is already ordered
    deepest-nested-first by the inventory walker, so a naive linear pass over
    it satisfies "sign dependencies before dependents" without hard-coding a
    bundle layout.

    Each profile-bearing target (main app, app extension, watch app) gets its
    own profile selected from the pool by its own bundle id, embedded into
    its own bundle directory, and its entitlements reconciled against that
    profile independently. Frameworks/dylibs/other have no bundle id of
    their own and are reconciled against the main app's selected profile --
    this exactly matches the single-profile behavior this project shipped
    with before per-extension profiles existed, so a single supplied profile
    still signs everything as before; only supplying multiple profiles
    changes anything.
    """
    main_profile, main_profile_path = profiles.select_for(bundle.bundle_id)

    results: list[SignResult] = []
    for target in bundle.executables:
        if target.kind in _PROFILE_BEARING_KINDS:
            if target.bundle_id:
                profile, profile_path = profiles.select_for(target.bundle_id)
            else:
                # This bundle's own Info.plist couldn't be read -- fall back
                # to the main app's profile rather than leaving it unembedded.
                profile, profile_path = main_profile, main_profile_path
            embed_provisioning_profile(sign_target_path(target), profile_path)
        else:
            profile = main_profile

        original_entitlements = provider.dump_entitlements(target.path)
        reconciled = reconcile_entitlements(original_entitlements, profile.entitlements)
        result = provider.sign(sign_target_path(target), reconciled, identity)
        results.append(result)
        if target.kind == "main":
            bundle.entitlements = reconciled
    return results
