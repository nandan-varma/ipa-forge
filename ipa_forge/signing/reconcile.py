# SPDX-License-Identifier: GPL-3.0-or-later
"""Entitlement reconciliation: original app entitlements ∩ profile-authorized entitlements.

Apple's rule (TN3125): every entitlement claimed by the app must be in the
profile's allowlist; the profile may authorize more than the app claims, but
never the reverse. This module enforces that as an intersection, never a
blind copy of either side.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

# These identify the signing team/app itself rather than an app-requested
# capability; they always come from the profile, since the app's original
# values reference whatever team originally signed it.
_PROFILE_AUTHORITATIVE_KEYS = ("application-identifier", "com.apple.developer.team-identifier")


def _concretize(value: Any, bundle_id: str | None) -> Any:
    """A wildcard profile authorizes `TEAM.*`; the signed binary must claim
    the concrete `TEAM.<bundle id>` or installd rejects it (0xe8008015)."""
    if bundle_id and isinstance(value, str) and value.endswith("*"):
        return value[:-1] + bundle_id
    return value


def _allowed_list(app_value: list[Any], profile_value: Any, bundle_id: str | None) -> list[Any]:
    """Keep only list entries (e.g. keychain-access-groups) the profile's
    patterns authorize; an app entry under the original signer's team never
    matches, so fall back to the profile's own concretized entries."""
    patterns = [
        p for p in (profile_value if isinstance(profile_value, list) else [profile_value]) if isinstance(p, str)
    ]
    kept = [v for v in app_value if isinstance(v, str) and any(fnmatchcase(v, p) for p in patterns)]
    return kept or [_concretize(p, bundle_id) for p in patterns]


def reconcile_entitlements(
    app_entitlements: dict[str, Any], profile_entitlements: dict[str, Any], bundle_id: str | None = None
) -> dict[str, Any]:
    reconciled: dict[str, Any] = {}
    for key, value in app_entitlements.items():
        if key not in profile_entitlements:
            continue
        reconciled[key] = (
            _allowed_list(value, profile_entitlements[key], bundle_id) if isinstance(value, list) else value
        )

    for key in _PROFILE_AUTHORITATIVE_KEYS:
        if key in profile_entitlements:
            reconciled[key] = _concretize(profile_entitlements[key], bundle_id)

    return reconciled
