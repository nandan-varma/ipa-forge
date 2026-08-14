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
  (7-day expiry, active-app count, App-ID-per-week limits) -- see
  `docs/architecture.md`'s AltStore flow diagram.

## Linux-only analysis mode

Everything except `ipa_forge/signing/` runs without macOS: extraction,
repacking, plist inspection, patch resolution, resource patching, and binary
pattern analysis/modification (`bundle/`, `patch/`, `machO/arch.py`,
`machO/injector.py`). This means `forge inspect`, `forge validate`, and
`forge patch --dry-run` (up through the dry-run gate) all work on Linux
today without any code changes -- only the signing stages (`load_profile_pool`
onward) require `codesign`/`security` and therefore fail on non-macOS. There
is no runtime OS check gating this; it falls out naturally from which modules
a given code path imports.

## Shipped v1 additions

The three scope limits listed in earlier revisions of this file are closed in
0.1.0, each following the same extension seams described above:

- **GUI zip upload**: `gui/uploads.py::resolve_patch_definition` accepts a
  zip of a patch directory (definition + `assets/`), so
  `resource_replace`/`resource_add` work from the GUI exactly as from the
  CLI. `safe_extract_zip` enforces zip-slip and size/member caps.
- **Per-extension provisioning profiles**: `signing/profile.py::ProfilePool`
  matches each profile-bearing target (app, app extension, watch app) to its
  own `.mobileprovision` by its own bundle id; a single profile still signs
  everything, exactly as before (see `signing/pipeline.py::sign_bundle`).
- **`plist_edit`**: a `PatchOperation` (`patch/plist.py`) for set/remove on
  bundle-relative plists -- a compact worked example of steps 1-5 above.
- **The `hooks:` block**: a patch definition may declare runtime hook targets
  (class/selector/kind/added/required) that `pipeline.py` verifies against
  the app's main binary during the dry-run gate (`ipa_forge/hooks/`). No new
  operation type -- it is a verification surface, driven by the same
  definition file. `forge hooks verify|extract|audit` expose it on the CLI.
  `added: true` declares a method the tweak adds itself (logos' %new).

## Related

- [`architecture.md`](architecture.md) — how the engine works
- [`patch-reference.md`](patch-reference.md) — the YAML contract
- [`README.md`](./README.md) — docs index
