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
