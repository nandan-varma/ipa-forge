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
            expiry = expiry.replace(tzinfo=datetime.timezone.utc)
        return datetime.datetime.now(datetime.timezone.utc) >= expiry

    @property
    def bundle_id_pattern(self) -> str:
        """The bundle id (or wildcard `*`) this profile authorizes, with the
        team-id prefix stripped from `application-identifier`."""
        prefix = f"{self.team_identifier}."
        if self.application_identifier.startswith(prefix):
            return self.application_identifier[len(prefix):]
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
        raise ProfileError(
            f"provisioning profile '{profile.name}' authorizes '{pattern}', not '{bundle_id}'"
        )
