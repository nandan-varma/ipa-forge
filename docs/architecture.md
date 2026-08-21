# Architecture

## Goal

Take a user-supplied `.ipa`, apply externally-defined patches, and produce a
correctly re-signed `.ipa` that AltStore Classic can install and refresh on a
real iPhone -- without ever reimplementing Apple's code signature format and
without any app-specific logic in the core engine.

## Hard constraints

1. **Never reimplement Apple's code signature format.** CodeDirectory, CMS
   signing, SuperBlob construction, DER entitlements, and resource sealing
   are internal formats Apple has changed repeatedly and does not treat as a
   stable API. Every actual signing operation shells out to `codesign` /
   `security` (`ipa_forge/signing/backend.py` is the *only* module allowed to
   invoke them).
2. **Patch engine and signing engine are independent subsystems**, connected
   only through the `AppBundle` model. A `PatchOperation` never calls
   `codesign` directly.
3. **The core engine is app-agnostic.** It understands patch operation
   *types* (`binary_replace`, `resource_replace`, `dylib_inject`, ...) but
   never a specific bundle id, byte pattern, or file -- those only ever come
   from user-supplied YAML.
4. **Target AltStore Classic, not AltStore PAL.** PAL requires Apple
   notarization and a different distribution package format; that's a
   different product. The output here is just a standard
   `Payload/<App>.app` IPA, which is exactly what AltStore Classic expects
   (AltStore's own error 1007 fires when an IPA *isn't* standard-structure --
   inventing a custom packaging format would be actively counterproductive).

## Component map

```
ipa_forge/
  bundle/     AppBundle model, bottom-up executable inventory walker, IPA extract/repack
  patch/      PatchOperation implementations, YAML schema, resolver, dry-run/apply engine
  machO/      LIEF-backed arch selection, dylib load-command injection, Mach-O
              detection/enumeration (detect.py), and the shared ObjC runtime
              analysis engine (objc.py -- class table, protocols, categories,
              ivars, properties, method lists+type encodings, selrefs)
  signing/    Provisioning profile parsing, entitlement reconciliation, codesign backend,
              SigningProvider abstraction, recursive bottom-up signing orchestration
  validators/ IPA / bundle / archive structural validators
  hooks/      Hook verification (the version-drift safety net) and tweak-source
              scanning, built on machO/objc.py's analysis
  analysis/   General-purpose IPA reverse engineering, also built on
              machO/objc.py: class-dump rendering, type-encoding decode,
              strings, symbols, security posture, version diffing -- see
              docs/reverse-engineering.md
  pipeline.py End-to-end stage orchestration (the 17 stages below)
  manifest.py Structured pre-signing manifest for debugging failed installs
  cli/        Typer CLI: inspect, validate, patch, export-source, gui, hooks, analysis
  gui/        FastAPI app wrapping the same pipeline in-process, plus a
              read-only reverse-engineering viewer (gui/analysis.html)
  altstore/   source.json distribution-metadata export
```

Dependency direction is one-way:

```
patch/    ──depends on──>  bundle/
signing/  ──depends on──>  bundle/
machO/    ──depends on──>  bundle/ (objc.py/detect.py read AppBundle's executable inventory)
hooks/    ──depends on──>  machO/ (the ObjC analysis engine)
analysis/ ──depends on──>  machO/ (the same engine hooks/ uses)
pipeline.py ──orchestrates──>  patch/, signing/, hooks/, validators/, manifest.py
cli/, gui/ ──call──>  pipeline.py, hooks/, analysis/
```

`patch/` and `signing/` never import from each other. `hooks/` and
`analysis/` are siblings -- both read `machO/objc.py`'s `MachOAnalysis`,
neither imports the other.

## The pipeline (`ipa_forge/pipeline.py`)

```
 1. validate + extract IPA                    (validators/ipa_validator.py)
 2. inventory bundle, bottom-up                (bundle/inventory.py)
 3. parse Info.plist                           (bundle/ipa.py: load_bundle)
 4. resolve applicable patch definitions        (patch/resolver.py)
 5. dry-run gate -- ALL ops must pass first     (patch/engine.py: dry_run_all)
 6. apply resource patches       ┐
 7. apply binary patches         ├─ fixed order (patch/engine.py: apply_all)
 8. apply dylib injection        ┘   (injection last: LIEF rewrites can shift
                                       byte offsets binary patches depend on)
 9. re-validate bundle consistency              (validators/bundle_validator.py)
10. emit manifest (pre-signing)                 (manifest.py)
11. load + validate provisioning profile        (signing/profile.py)
12. reconcile entitlements (per target)         (signing/reconcile.py)
13. embed profile                               (signing/pipeline.py)
14. recursive bottom-up codesign                (signing/pipeline.py: sign_bundle)
15. verify (per-target + final --deep --strict) (signing/provider.py)
16. repackage into standard Payload/*.app zip    (bundle/ipa.py: repack_ipa)
17. final validation: re-extract from scratch    (validators/archive_validator.py)
```

Steps 5 and 9 are hard gates: nothing mutates until every patch operation
reports `dry_run_ok`, and the bundle is re-validated immediately after
mutation, before any signing work begins.

### Why entitlement reconciliation is a dedicated step

Per Apple's TN3125, a provisioning profile authorizes who may sign, which
app, where, and which entitlements may be claimed -- the profile may
authorize *more* entitlements than the app claims, never the reverse.
`signing/reconcile.py` enforces this as an intersection (`app ∩ profile`),
never a blind copy of either side, with `application-identifier` and
`com.apple.developer.team-identifier` always taken from the profile (the
app's original values reference whichever team originally signed it).

### Why hook verification is its own stage

Dylib-injection tweaks depend on ObjC runtime hooks that newer app versions
silently break: rename or remove a class/selector and the hook no-ops with no
error. The `hooks:` block in a patch definition declares every hook the tweak
relies on; `pipeline.py` verifies it against the app's main binary (class
table + method lists + `__objc_selrefs` + `__objc_methname`, chained-fixup
aware) during the dry-run gate and fails when a `required` hook cannot attach
— before anything mutates. The verifier distinguishes three soft cases from
the hard ones: `unverified` (selector *declared* as a method somewhere — a
protocol, category, or an undecoded method list — but not in any parsed class
method list; likely attaches), `referenced-only` (selector *referenced* but
declared as no method anywhere, so there is no IMP to swizzle and the hook
cannot attach — the dead-hook detector), and `ok-inherited` (system
superclass method). `missing-class`/`missing-selector`/`elsewhere` are hard.
This turns "port to a new version" into: bump the version, read the report,
fix exactly what it flags.

The analyzer also resolves class **superclass** pointers (so a plain-UIView
view class is distinguishable from an `_ASDisplayView` one — the difference
between an id-hook that fires and one that never sees the view) and parses
relative (REL-flag) method lists, which carry the bulk of modern app config
classes (e.g. a 7,000-getter `YTColdConfig` facade). `forge hooks find
<selector>` is the reverse lookup used when a hook attaches per verify but
does nothing on device.

### Why signing targets bundle directories, not raw files

This was found empirically while testing against the synthetic fixture:
`codesign` on a bundle-kind executable (main app, framework, extension,
watch app) must be pointed at the *bundle directory*
(`Foo.framework`, `App.app`), not the raw Mach-O file inside it -- otherwise
`codesign` never creates the bundle-level `_CodeSignature/CodeResources`
seal covering `Info.plist` and other resources, and a later
`codesign --verify --strict` on the bundle fails with "a sealed resource is
missing or invalid". Flat dylibs (not wrapped in a bundle) are signed
directly. See `signing/pipeline.py::sign_target_path`.

### Why fat/universal binary writes go through the FatBinary container

Also found empirically: LIEF's `Binary.write()`, called on a single arch
slice extracted from a fat/universal Mach-O, overwrites the *entire file*
with just that thin slice -- silently discarding every other architecture.
`machO/injector.py` always writes back through the parent `FatBinary` object
instead. `patch/binary.py`'s raw byte-level read/write is unaffected by this,
since it never goes through LIEF's write path at all.

## AltStore Classic signing & refresh flow

```
 patcher output (standard .ipa)
          │
          ▼
 AltStore "My Apps" → install
          │
          ▼
 AltServer (desktop) performs the actual install over USB/Wi-Fi
          │
          ▼
 iPhone: app installed, signed by the identity ipa-forge used
          │
          ▼
 free Apple ID: 7-day signing lifetime, ≤3 active sideloads, ≤10 App IDs / 7 days
 paid account:   governed by Apple's then-current provisioning rules (not hard-coded here)
          │
          ▼
 AltStore/AltServer background refresh (re-signs in place before expiry)
```

## SigningProvider abstraction

```python
class SigningProvider(ABC):
    def list_identities(self) -> list[Identity]: ...
    def sign(self, target, entitlements, identity) -> SignResult: ...
    def verify(self, target, deep=False) -> VerifyResult: ...
    def dump_entitlements(self, target) -> dict: ...
```

`LocalIdentityProvider` is the only implementation in v1: it signs using a
codesigning identity already present in the local macOS Keychain.
`AltStoreCredentialProvider` is a deliberate stub (`NotImplementedError`) --
credentials obtained through AltServer's own Apple-account pairing flow are
not necessarily equivalent to an externally supplied certificate/profile
pair, so this is left unimplemented rather than guessed at. See
`docs/extensibility.md` for what a real implementation would need.

## Linux support boundary

Extraction, repacking, plist inspection, patch resolution, resource
patching, binary pattern analysis/modification, and dry-run all work without
macOS (`bundle/`, `patch/`, `machO/arch.py`, `machO/injector.py` have no
macOS dependency). Everything in `signing/` requires `codesign`/`security`
and therefore macOS -- this boundary is enforced by which module a caller
imports, not by a runtime OS check, matching the project's constraint that
Apple's signing internals are never reimplemented anywhere, on any platform.

## Related

- [`extensibility.md`](extensibility.md) — extending the engine
- [`patch-reference.md`](patch-reference.md) — the YAML contract
- [`usage.md`](usage.md) — CLI
- [`reverse-engineering.md`](reverse-engineering.md) — `forge analysis` (class-dump, strings, symbols, security, diff)
- [`README.md`](README.md) — docs index
