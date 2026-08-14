# ipa-forge

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![repo](https://img.shields.io/badge/repo-nandanvarma%2Fipa--forge-555.svg)](https://github.com/nandanvarma/ipa-forge)

A generic, data-driven iOS IPA patcher framework: extract a user-supplied
`.ipa`, apply version-aware patches from external YAML definitions (binary
byte patches, resource replacement, dylib injection), and re-sign the result
into a standard-structure `.ipa` that AltStore Classic can install and
refresh on a real iPhone.

## Documentation

Start at [`docs/README.md`](docs/README.md) — the index.

| Doc | What it covers |
| --- | --- |
| [`docs/adding-an-app.md`](docs/adding-an-app.md) | **Port a new app** end-to-end (the "give me an IPA" playbook) |
| [`docs/adding-a-feature.md`](docs/adding-a-feature.md) | **Add a feature** to a hook dylib (conventions) |
| [`docs/usage.md`](docs/usage.md) | End-to-end workflow, full CLI + GUI reference, signing identity/profile setup |
| [`docs/patch-reference.md`](docs/patch-reference.md) | Complete patch-definition reference — every operation type, field, matching rule, and the `hooks:` block |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Every error message mapped to its cause and fix |
| [`docs/architecture.md`](docs/architecture.md) | Design rationale, the 17-stage pipeline, hard constraints, hook verification (for developers) |
| [`docs/extensibility.md`](docs/extensibility.md) | How to add new patch operation types (for developers) |
| [`docs/altstore_device_testing.md`](docs/altstore_device_testing.md) | Manual AltStore Classic device-test checklist |

### Worked patch sets

| Set | Runbook | Features |
| --- | --- | --- |
| YouTube 21.32.4 | [`patches/youtube/PLAYBOOK.md`](patches/youtube/PLAYBOOK.md) | [`patches/youtube/README.md`](patches/youtube/README.md) |
| Spotify 9.1.72 | [`patches/spotify/PLAYBOOK.md`](patches/spotify/PLAYBOOK.md) | [`patches/spotify/README.md`](patches/spotify/README.md) |

## Quick start (novice — the GUI)

1. **Install**: `python3 -m venv .venv && source .venv/bin/activate && pip install -e .`
2. **Launch the GUI**: `forge gui` → open http://127.0.0.1:8765
3. **Drop your .ipa** into the box. The GUI detects the app and the matching
   patch set, shows a small warning if the patch set targets a different
   version (patching is still allowed — hook verification is the safety
   net), and presents one **Patch** button.
4. **Download** the patched IPA (unsigned — ready for AltStore).

No YAML editing, no signing identity, no provisioning profiles needed for
the AltStore path.

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

# Dry-run a patch definition (no mutation, no signing; --identity/--profile optional)
forge patch --ipa path/to/App.ipa --patches patches.yaml \
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

  - id: "set-verbose-logging"
    type: plist_edit
    action: "set"                  # or "remove" (no value needed)
    key: "CFBundleDisplayName"
    value: "Patched App"
    path: "Info.plist"             # bundle-relative; defaults to Info.plist
```

See `fixtures/patches/example.yaml` and `fixtures/patches/example_dylib_inject.yaml`
for complete, working examples run by the test suite against
`fixtures/synthetic_app.ipa`.

**This is a teaser.** The full reference — every operation type (`binary_replace`,
`resource_replace`/`add`/`remove`, `dylib_inject`, `plist_edit`), every field,
version-matching semantics, the dry-run gate, ordering rules, and a
common-mistakes checklist — is in
[`docs/patch-reference.md`](docs/patch-reference.md).

## Getting certificates and provisioning profiles for AltStore

AltStore Classic re-signs and installs apps using **your own** Apple ID's
development credentials, obtained through AltServer's own pairing flow --
ipa-forge doesn't manage your Apple account. How to find your codesigning
identity and a matching `.mobileprovision`, and how ipa-forge selects
profiles (exact match, wildcard, per-extension), is documented in
[`docs/usage.md`](docs/usage.md#signing-identity--profile). In short:

1. Pair AltServer with your device (or use a certificate + profile from your
   own Xcode account).
2. Locate your identity: `security find-identity -v -p codesigning`.
3. Locate a profile under
   `~/Library/MobileDevice/Provisioning Profiles/*.mobileprovision`.
4. The profile's `application-identifier` must authorize the IPA's bundle id
   (exactly or via a wildcard `TEAMID.*` profile).

`forge patch` validates the profile up front (expiry, bundle-id match) and
fails with an actionable error before touching your IPA if it doesn't
qualify.

## Testing

```bash
pytest tests/                    # everything, including real codesign signing
pytest tests/ -m "not macos"     # skip real-signing tests (e.g. on Linux)
```

`fixtures/synthetic_app.ipa` is a real, from-scratch iOS app built via
`scripts/rebuild_fixture.sh` against the iOS SDK -- a main executable, a
linked framework, an unlinked standalone dylib
(the dylib-injection target), and a resource file. It's checked in as a
binary artifact; re-run the script only if you need to change its shape.

Real-device AltStore Classic install/launch/refresh cannot be automated in
this environment -- see
[`docs/altstore_device_testing.md`](docs/altstore_device_testing.md) for the
manual checklist.

## License

GPLv3-or-later. See [`LICENSE`](LICENSE).
