# ipa-forge

A generic, data-driven iOS IPA patcher framework: extract a user-supplied
`.ipa`, apply version-aware patches from external YAML definitions (binary
byte patches, resource replacement, dylib injection), and re-sign the result
into a standard-structure `.ipa` that AltStore Classic can install and
refresh on a real iPhone.

ipa-forge never embeds, ships, or downloads any third-party app content --
you always supply your own IPA and your own signing credentials.

See [`docs/architecture.md`](docs/architecture.md) for the design and
[`docs/extensibility.md`](docs/extensibility.md) for how to extend it.

## Requirements

- macOS with Xcode Command Line Tools (`xcode-select -p` should print a
  path) -- signing requires Apple's own `codesign`/`security` tools and is
  not reimplemented. Everything up through patch dry-run also works on
  Linux; see `docs/extensibility.md`.
- Python 3.11+
- A codesigning identity in your Keychain (`security find-identity -v -p codesigning`)
  and a matching `.mobileprovision`, obtained the normal way through Xcode or
  AltServer's own account pairing.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs the `forge` CLI.

## Quickstart

```bash
# Inspect an IPA's bundle id, version, and executable inventory
forge inspect path/to/App.ipa

# Validate structure without touching anything
forge validate path/to/App.ipa

# Dry-run a patch definition (no mutation, no signing)
forge patch --ipa path/to/App.ipa --patches patches.yaml \
  --identity "Apple Development" --profile path/to/profile.mobileprovision \
  --output patched.ipa --dry-run

# Patch and re-sign for real
forge patch --ipa path/to/App.ipa --patches patches.yaml \
  --identity "Apple Development" --profile path/to/profile.mobileprovision \
  --output patched.ipa --verbose

# Launch the local web GUI (wraps the same pipeline)
forge gui
```

`--identity` accepts either a full SHA-1 hash or a unique substring of the
identity's name (as shown by `security find-identity -v -p codesigning`) --
it fails loudly, listing candidates, if the substring is ambiguous or
matches nothing.

Try it against the checked-in synthetic test fixture (no real app required):

```bash
forge patch --ipa fixtures/synthetic_app.ipa --patches fixtures/patches/example.yaml \
  --identity "Apple Development" --profile <your .mobileprovision> \
  --output /tmp/patched.ipa --verbose
```

## Writing a patch definition

```yaml
target:
  bundle_id: "com.example.synthetic"
  version:
    exact: "1.0.0"          # or: { min: "1.0.0", max: "2.0.0" }

patches:
  - id: "zero-marker-bytes"
    type: binary_replace
    executable: "TestApp"
    arch: "arm64"             # required for fat/universal binaries
    pattern: "ca fe f0 0d"    # space-separated hex, ?? = wildcard byte
    replacement: "00 00 00 00"
    expected_matches: 1        # fails loudly on 0 or >1 matches

  - id: "swap-asset"
    type: resource_replace     # also: resource_add, resource_remove
    path: "asset.txt"           # bundle-relative
    source: "assets/patched_asset.txt"  # relative to the patch definition file

  - id: "inject-hook"
    type: dylib_inject
    executable: "TestApp"
    arch: "arm64"
    install_name: "@rpath/libInjectable.dylib"   # the dylib must already be in the bundle
    load_command: "LC_LOAD_DYLIB"                 # or LC_LOAD_WEAK_DYLIB
```

See `fixtures/patches/example.yaml` and `fixtures/patches/example_dylib_inject.yaml`
for complete, working examples run by the test suite against
`fixtures/synthetic_app.ipa`.

## Getting certificates and provisioning profiles for AltStore

AltStore Classic re-signs and installs apps using **your own** Apple ID's
development credentials, obtained through AltServer's own pairing flow --
ipa-forge doesn't manage your Apple account. In practice:

1. Pair AltServer with your device and let it manage your Apple ID
   certificate/App ID the normal way (see AltStore Classic's own setup
   docs), **or** use a certificate + `.mobileprovision` from your own Xcode
   account (Xcode → Settings → Accounts → Manage Certificates).
2. Locate your local identity: `security find-identity -v -p codesigning`.
3. Locate your profile: profiles Xcode has already installed live under
   `~/Library/MobileDevice/Provisioning Profiles/*.mobileprovision`. Inspect
   one with `security cms -D -i <profile>`.
4. The profile's `Entitlements.application-identifier` must authorize the
   bundle id of the IPA you're patching (either exactly, or via a wildcard
   `TEAMID.*` profile).

`forge patch` validates the profile up front (expiry, bundle-id match) and
fails with an actionable error before touching your IPA if it doesn't
qualify.

## Known limitations

- **AltStore Classic only**, not AltStore PAL (which requires Apple
  notarization and a different distribution format).
- **Free Apple ID sideloads expire after 7 days** and are subject to
  AltStore's current limits (≤3 active sideloaded apps, ≤10 App IDs per
  rolling 7-day window) -- AltServer's background refresh re-signs before
  expiry, but these are Apple/AltStore platform constraints, not something
  ipa-forge can change or predict.
- **Paid developer accounts** are still governed by whatever Apple's current
  provisioning rules are at the time you sign -- this project doesn't
  hard-code a signing-lifetime constant.
- **Some entitlements cannot survive re-signing**: only entitlements both
  claimed by the original app *and* authorized by your supplied provisioning
  profile survive reconciliation (see `docs/architecture.md`).
- **Apps whose functionality depends on the original signing identity**
  (associated domains, push entitlements tied to the original team, App
  Store receipt validation, etc.) may not work correctly after re-signing,
  regardless of how correct the signature itself is.
- **Dylib injection is more fragile than resource replacement** -- treat it
  as an advanced operation; see `machO/injector.py`'s explicit
  INJECTED/INJECTION_SKIPPED/INJECTION_UNSUPPORTED/INJECTION_FAILED statuses.
- **The GUI's `/patch` endpoint accepts one patch-definition file only**, no
  sibling assets directory -- `resource_replace`/`resource_add` operations
  needing external source files currently only work via the CLI. See
  `docs/extensibility.md`.
- **You must have legitimate rights** to both the IPA you're patching and
  the signing credentials you use.

## Testing

```bash
pytest tests/                    # everything, including real codesign signing
pytest tests/ -m "not macos"     # skip real-signing tests (e.g. on Linux)
```

`fixtures/synthetic_app.ipa` is a real, from-scratch iOS app (no
third-party content) built via `scripts/rebuild_fixture.sh` against the iOS
SDK -- a main executable, a linked framework, an unlinked standalone dylib
(the dylib-injection target), and a resource file. It's checked in as a
binary artifact; re-run the script only if you need to change its shape.

Real-device AltStore Classic install/launch/refresh cannot be automated in
this environment -- see
[`docs/altstore_device_testing.md`](docs/altstore_device_testing.md) for the
manual checklist.
