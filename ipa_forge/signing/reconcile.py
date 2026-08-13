# SPDX-License-Identifier: GPL-3.0-or-later
"""Entitlement reconciliation: original app entitlements ∩ profile-authorized entitlements.

Apple's rule (TN3125): every entitlement claimed by the app must be in the
profile's allowlist; the profile may authorize more than the app claims, but
never the reverse. This module enforces that as an intersection, never a
blind copy of either side.
"""

from __future__ import annotations

from typing import Any

# These identify the signing team/app itself rather than an app-requested
# capability; they always come from the profile, since the app's original
# values reference whatever team originally signed it.
_PROFILE_AUTHORITATIVE_KEYS = ("application-identifier", "com.apple.developer.team-identifier")


def reconcile_entitlements(app_entitlements: dict[str, Any], profile_entitlements: dict[str, Any]) -> dict[str, Any]:
    reconciled = {key: value for key, value in app_entitlements.items() if key in profile_entitlements}

    for key in _PROFILE_AUTHORITATIVE_KEYS:
        if key in profile_entitlements:
            reconciled[key] = profile_entitlements[key]

    return reconciled
