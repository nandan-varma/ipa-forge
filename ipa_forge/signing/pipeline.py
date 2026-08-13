"""Recursive bottom-up signing orchestration + provisioning-profile embedding."""
from __future__ import annotations

import shutil
from pathlib import Path

from ipa_forge.bundle.models import AppBundle
from ipa_forge.signing.profile import ProvisioningProfile
from ipa_forge.signing.provider import SignResult, SigningProvider
from ipa_forge.signing.reconcile import reconcile_entitlements


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
        result = provider.sign(target.path, reconciled, identity)
        results.append(result)
        if target.kind == "main":
            bundle.entitlements = reconciled
    return results
