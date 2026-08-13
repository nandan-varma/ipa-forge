# Extensibility notes

## Adding a new patch operation type

1. Implement the `PatchOperation` protocol (`ipa_forge/patch/base.py`):
   `dry_run(ctx) -> PatchResult` and `apply(ctx) -> PatchResult`. Look at
   `patch/resource.py` for the simplest example.
2. Add a pydantic spec class to `patch/schema.py` with a `type: Literal[...]`
   discriminator field, and add it to the `PatchSpec` union.
3. Wire it in `patch/loader.py::build_operations`.
4. If it mutates a Mach-O file, decide where it belongs in
   `patch/engine.py::_apply_order_rank` -- resource-only ops run first,
   binary-offset patches next, Mach-O-load-command edits (which can shift
   binary layout) last. A completely new mutation category should get its
   own rank rather than reusing an existing one if its ordering constraints
   differ.
5. Add unit tests exercising both the dry-run failure paths and a real apply,
   following `tests/unit/test_resources.py` or `tests/unit/test_binary_patch.py`.

The core engine (`pipeline.py`, `patch/engine.py`, `patch/resolver.py`) never
needs to change for a new operation type -- that's the point of the
`PatchOperation` protocol.

## Implementing AltStoreCredentialProvider

`signing/provider.py::AltStoreCredentialProvider` is currently a stub. A real
implementation would need to:

- Obtain a signing identity + provisioning profile through AltServer's own
  Apple-account pairing flow, rather than assuming one is already sitting in
  the local Keychain (`LocalIdentityProvider`'s assumption).
- Implement the same four abstract methods (`list_identities`, `sign`,
  `verify`, `dump_entitlements`) -- `pipeline.py` and `cli/main.py` are
  already written against the `SigningProvider` interface, not against
  `LocalIdentityProvider` directly, so no other code should need to change.
- Handle the account-level constraints AltStore Classic itself enforces
  (7-day expiry, active-app count, App-ID-per-week limits) as *its own*
  concern -- `ipa_forge`'s job stops at producing a correctly signed IPA; see
  `docs/architecture.md`'s AltStore flow diagram.

## Linux-only analysis mode

Everything except `ipa_forge/signing/` runs without macOS: extraction,
repacking, plist inspection, patch resolution, resource patching, and binary
pattern analysis/modification (`bundle/`, `patch/`, `machO/arch.py`,
`machO/injector.py`). This means `forge inspect`, `forge validate`, and
`forge patch --dry-run` (up through the dry-run gate) all work on Linux
today without any code changes -- only the signing stages
(`load_provisioning_profile` onward) require `codesign`/`security` and
therefore fail on non-macOS. There is no runtime OS check gating this; it
falls out naturally from which modules a given code path imports.

## Known v1 scope limits (not bugs, just not built yet)

- **GUI single-file upload**: `gui/app.py`'s `/patch` endpoint accepts one
  patch-definition file with no sibling `assets/` directory, so
  `resource_replace`/`resource_add` operations that reference external
  source files aren't usable from the GUI yet (the CLI has no such limit,
  since `--patches` reads off a real filesystem path with its assets
  alongside it). A real fix would accept a zip of the patch directory rather
  than a single file.
- **Per-extension provisioning profiles**: `signing/pipeline.py::sign_bundle`
  reconciles every nested target's entitlements against the *same* supplied
  profile. Real app extensions often need their own profile matching their
  own bundle id. Multi-profile signing would need a profile-selection step
  keyed by each target's own bundle id, which the inventory walker doesn't
  currently expose (it tracks Mach-O structure, not each nested bundle's own
  `Info.plist`).
- **No `plist_edit` patch type**: Info.plist is read for bundle/version
  resolution but isn't itself a patch target in v1. Would follow the same
  `PatchOperation` pattern as `resource_replace`.
