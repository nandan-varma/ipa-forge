# SPDX-License-Identifier: GPL-3.0-or-later
"""SigningProvider abstraction: decouples the pipeline from *how* signing happens."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ipa_forge.bundle.plist import write_plist
from ipa_forge.signing.backend import (
    Identity,
    SigningBackendError,
    codesign_dump_entitlements,
    codesign_sign,
    codesign_verify,
    list_identities,
)


@dataclass
class SignResult:
    target: Path
    identity: str
    entitlements: dict[str, Any]


@dataclass
class VerifyResult:
    target: Path
    ok: bool
    message: str = ""


class SigningProvider(ABC):
    @abstractmethod
    def list_identities(self) -> list[Identity]: ...

    @abstractmethod
    def sign(self, target: Path, entitlements: dict[str, Any], identity: str) -> SignResult: ...

    @abstractmethod
    def verify(self, target: Path, deep: bool = False) -> VerifyResult: ...

    @abstractmethod
    def dump_entitlements(self, target: Path) -> dict[str, Any]: ...


class LocalIdentityProvider(SigningProvider):
    """Signs using a codesigning identity already present in the local macOS Keychain."""

    def list_identities(self) -> list[Identity]:
        return list_identities()

    def sign(self, target: Path, entitlements: dict[str, Any], identity: str) -> SignResult:
        entitlements_path = target.parent / f".{target.name}.entitlements.plist"
        write_plist(entitlements_path, entitlements)
        try:
            codesign_sign(target, identity, entitlements_path)
        finally:
            entitlements_path.unlink(missing_ok=True)
        return SignResult(target=target, identity=identity, entitlements=entitlements)

    def verify(self, target: Path, deep: bool = False) -> VerifyResult:
        try:
            codesign_verify(target, deep=deep)
        except SigningBackendError as e:
            return VerifyResult(target=target, ok=False, message=str(e))
        return VerifyResult(target=target, ok=True)

    def dump_entitlements(self, target: Path) -> dict[str, Any]:
        return codesign_dump_entitlements(target)


def resolve_identity(provider: SigningProvider, query: str) -> str:
    """Resolve a codesigning identity SHA-1 hash or unique name substring to
    its canonical SHA-1 hash, failing loudly (with the candidate list) on
    zero or multiple matches rather than guessing."""
    identities = provider.list_identities()

    for identity in identities:
        if identity.sha1.lower() == query.lower():
            return identity.sha1

    matches = [i for i in identities if query.lower() in i.name.lower()]
    if len(matches) == 1:
        return matches[0].sha1

    available = "\n".join(f"  {i.sha1}  {i.name}" for i in identities) or "  (none found)"
    if not matches:
        raise SigningBackendError(f"no codesigning identity matches '{query}'. Available:\n{available}")
    raise SigningBackendError(f"'{query}' matches multiple codesigning identities, be more specific:\n{available}")


class AltStoreCredentialProvider(SigningProvider):
    """Reserved for future AltStore-account-based signing (Apple ID pairing via
    AltServer, rather than a local Keychain identity). Not implemented in v1:
    an externally supplied cert/profile pair is not necessarily equivalent to
    the credentials AltServer obtains through its own Apple authentication
    flow, so this is intentionally left as a stub rather than guessed at."""

    def list_identities(self) -> list[Identity]:
        raise NotImplementedError("AltStoreCredentialProvider is not implemented in v1")

    def sign(self, target: Path, entitlements: dict[str, Any], identity: str) -> SignResult:
        raise NotImplementedError("AltStoreCredentialProvider is not implemented in v1")

    def verify(self, target: Path, deep: bool = False) -> VerifyResult:
        raise NotImplementedError("AltStoreCredentialProvider is not implemented in v1")

    def dump_entitlements(self, target: Path) -> dict[str, Any]:
        raise NotImplementedError("AltStoreCredentialProvider is not implemented in v1")
