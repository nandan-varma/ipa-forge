"""The only module in ipa_forge permitted to invoke codesign/security directly.

Per the architecture's hard constraint, Apple's code signature format is never
reimplemented -- everything here shells out to Apple's own tooling.
"""
from __future__ import annotations

import plistlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SigningBackendError(Exception):
    pass


@dataclass
class Identity:
    sha1: str
    name: str


_IDENTITY_LINE = re.compile(r'^\s*\d+\)\s+([0-9A-Fa-f]{40})\s+"(.+)"$')


def list_identities() -> list[Identity]:
    result = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SigningBackendError(f"security find-identity failed: {result.stderr}")

    identities = []
    for line in result.stdout.splitlines():
        m = _IDENTITY_LINE.match(line)
        if m:
            identities.append(Identity(sha1=m.group(1), name=m.group(2)))
    return identities


def decode_provisioning_profile(path: Path) -> dict[str, Any]:
    """Decode a .mobileprovision (a CMS-signed plist) via `security cms -D -i`,
    per Apple's own recommended inspection procedure."""
    result = subprocess.run(
        ["security", "cms", "-D", "-i", str(path)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SigningBackendError(
            f"failed to decode provisioning profile {path}: {result.stderr.decode(errors='replace')}"
        )
    return plistlib.loads(result.stdout)


def codesign_sign(target: Path, identity: str, entitlements_plist: Path) -> None:
    result = subprocess.run(
        [
            "codesign",
            "--force",
            "--sign",
            identity,
            "--entitlements",
            str(entitlements_plist),
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SigningBackendError(f"codesign failed for {target}: {result.stderr}")


def codesign_verify(target: Path, deep: bool = False) -> None:
    args = ["codesign", "--verify"]
    if deep:
        args.append("--deep")
    args += ["--strict", "--verbose=4", str(target)]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SigningBackendError(f"codesign verification failed for {target}: {result.stderr}")


def codesign_dump_entitlements(target: Path) -> dict[str, Any]:
    # `:-` is deprecated by Apple in favor of plain `-` but is the only form
    # that emits a directly-parseable plist to stdout on current codesign;
    # `-` emits a human-readable dump instead. Revisit if Apple removes it.
    result = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(target)],
        capture_output=True,
        check=False,
    )
    stderr = result.stderr.decode(errors="replace")
    if result.returncode != 0:
        if "code object is not signed at all" in stderr:
            # Expected for a freshly extracted IPA before our own signing pass
            # has run -- not an error, just "no entitlements yet".
            return {}
        raise SigningBackendError(f"failed to dump entitlements for {target}: {stderr}")
    if not result.stdout.strip():
        return {}
    return plistlib.loads(result.stdout)
