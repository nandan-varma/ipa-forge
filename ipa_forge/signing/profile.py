# SPDX-License-Identifier: GPL-3.0-or-later
"""Provisioning profile parsing and early validation.

The profile is treated as authoritative input: it is rejected up front when
expired or bundle-id-incompatible rather than discovered only at codesign
time, per TN3125's model of profile/cert/entitlement as a compatibility set.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ipa_forge.signing.backend import decode_provisioning_profile


class ProfileError(Exception):
    pass


@dataclass
class ProvisioningProfile:
    uuid: str
    name: str
    team_identifier: str
    application_identifier: str
    expiration_date: datetime.datetime
    entitlements: dict[str, Any]
    provisioned_devices: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        expiry = self.expiration_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=datetime.UTC)
        return datetime.datetime.now(datetime.UTC) >= expiry

    @property
    def bundle_id_pattern(self) -> str:
        """The bundle id (or wildcard `*`) this profile authorizes, with the
        team-id prefix stripped from `application-identifier`."""
        prefix = f"{self.team_identifier}."
        if self.application_identifier.startswith(prefix):
            return self.application_identifier[len(prefix) :]
        return self.application_identifier


def parse_provisioning_profile(path: Path) -> ProvisioningProfile:
    raw = decode_provisioning_profile(path)
    try:
        return ProvisioningProfile(
            uuid=raw["UUID"],
            name=raw["Name"],
            team_identifier=raw["TeamIdentifier"][0],
            application_identifier=raw["Entitlements"]["application-identifier"],
            expiration_date=raw["ExpirationDate"],
            entitlements=raw["Entitlements"],
            provisioned_devices=raw.get("ProvisionedDevices", []),
            raw=raw,
        )
    except (KeyError, IndexError) as e:
        raise ProfileError(f"provisioning profile {path} is missing required field {e}") from e


def validate_profile(profile: ProvisioningProfile, bundle_id: str) -> None:
    if profile.is_expired:
        raise ProfileError(
            f"provisioning profile '{profile.name}' ({profile.uuid}) expired on {profile.expiration_date}"
        )
    pattern = profile.bundle_id_pattern
    if pattern != "*" and pattern != bundle_id:
        raise ProfileError(f"provisioning profile '{profile.name}' authorizes '{pattern}', not '{bundle_id}'")


@dataclass
class ProfilePool:
    """A set of parsed provisioning profiles, each paired with its original
    .mobileprovision file (needed to embed the raw file later), resolved
    per-bundle-id at signing time -- so nested extensions and watch apps can
    be signed with their own profile instead of always reusing the main
    app's."""

    entries: list[tuple[ProvisioningProfile, Path]]

    def select_for(self, bundle_id: str) -> tuple[ProvisioningProfile, Path]:
        exact = [e for e in self.entries if e[0].bundle_id_pattern == bundle_id]
        if len(exact) > 1:
            # F5: silently picking the first of several equally-valid profiles
            # would mask a configuration mistake -- fail loudly instead.
            raise ProfileError(
                f"multiple supplied profiles authorize '{bundle_id}': " + ", ".join(sorted(e[0].name for e in exact))
            )
        if exact:
            return exact[0]

        wildcard = [e for e in self.entries if e[0].bundle_id_pattern == "*"]
        if len(wildcard) > 1:
            raise ProfileError("multiple supplied wildcard profiles: " + ", ".join(sorted(e[0].name for e in wildcard)))
        if wildcard:
            return wildcard[0]

        # A single supplied profile is the common case (one app, no
        # extensions) and is used for every target, matching the pre-pool
        # behavior exactly. Ambiguity is only an error once >1 profile is
        # supplied and none of them actually authorizes this bundle id.
        if len(self.entries) == 1:
            return self.entries[0]

        available = ", ".join(sorted({e[0].bundle_id_pattern for e in self.entries}))
        raise ProfileError(
            f"no supplied provisioning profile authorizes bundle id '{bundle_id}' "
            f"(available: {available}); supply a matching --profile for it"
        )


def load_profile_pool(profile_paths: list[Path]) -> ProfilePool:
    if not profile_paths:
        raise ProfileError("at least one provisioning profile is required")

    entries = []
    for path in profile_paths:
        profile = parse_provisioning_profile(path)
        if profile.is_expired:
            raise ProfileError(
                f"provisioning profile '{profile.name}' ({profile.uuid}) at {path} expired on {profile.expiration_date}"
            )
        entries.append((profile, path))
    return ProfilePool(entries)
