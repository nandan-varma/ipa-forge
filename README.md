# ipa-forge

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![repo](https://img.shields.io/badge/repo-nandan--varma%2Fipa--forge-555.svg)](https://github.com/nandan-varma/ipa-forge)

A generic, data-driven iOS IPA patcher framework: extract a user-supplied
`.ipa`, apply version-aware patches from external YAML definitions (binary
byte patches, resource replacement, dylib injection), and re-sign the result
into a standard-structure `.ipa` that AltStore Classic can install and
refresh on a real iPhone.

## Documentation

Full documentation is published at
**[ipa-forge.nandan.fyi](https://ipa-forge.nandan.fyi)**. Source lives in
[`docs/`](docs/) (a Fumadocs site, see [`docs/content/docs/`](docs/content/docs/)
for the raw `.mdx`).

| Doc | What it covers |
| --- | --- |
| [Installation](https://ipa-forge.nandan.fyi/docs/installation) | `pip`/`pipx install ipa-forge` and a 1-minute smoke test |
| [Adding a new app](https://ipa-forge.nandan.fyi/docs/adding-an-app) | **Port a new app** end-to-end (the "give me an IPA" playbook) |
| [Adding a feature](https://ipa-forge.nandan.fyi/docs/adding-a-feature) | **Add a feature** to a hook dylib (conventions) |
| [Usage](https://ipa-forge.nandan.fyi/docs/usage) | End-to-end workflow, full CLI + GUI reference, signing identity/profile setup |
| [Patch reference](https://ipa-forge.nandan.fyi/docs/patch-reference) | Complete patch-definition reference — every operation type, field, matching rule, and the `hooks:` block |
| [Troubleshooting](https://ipa-forge.nandan.fyi/docs/troubleshooting) | Every error message mapped to its cause and fix |
| [Reverse engineering](https://ipa-forge.nandan.fyi/docs/reverse-engineering) | `forge analysis`: class-dump, strings, symbols, security posture, version diffing for any IPA |
| [Architecture](https://ipa-forge.nandan.fyi/docs/architecture) | Design rationale, the 17-stage pipeline, hard constraints, hook verification (for developers) |
| [Extensibility](https://ipa-forge.nandan.fyi/docs/extensibility) | How to add new patch operation types (for developers) |
| [AltStore device testing](https://ipa-forge.nandan.fyi/docs/altstore-device-testing) | Manual AltStore Classic device-test checklist |

### Patch sets

ipa-forge ships no patch definitions or reverse-engineered specifics for any
third-party app — it's the engine, not a collection of mods. An app-specific
patch set (YAML definition + optional hook dylib) lives under a
`patches/<app>/` directory you provide yourself; see
[Adding a new app](https://ipa-forge.nandan.fyi/docs/adding-an-app) for the
shape one follows and how the engine discovers it.

## Install

```bash
pipx install ipa-forge     # recommended: isolated, globally available `forge` command
# or: pip install ipa-forge   (inside your own virtualenv)
```

This installs the `forge` CLI — `forge --version` to confirm. Full install
options (uv, editable/source installs for development) and requirements are
at [Installation](https://ipa-forge.nandan.fyi/docs/installation).

## Requirements

- Python 3.11+
- macOS with Xcode Command Line Tools (`xcode-select -p` should print a
  path) -- **only for signing**: real (non-dry-run) `forge patch` shells out
  to Apple's `codesign`/`security` tools, never reimplementing them.
  `forge inspect`/`validate`/`patch --dry-run`/`analysis` all work on Linux;
  see [`extensibility`](https://ipa-forge.nandan.fyi/docs/extensibility).
- For real signing: a codesigning identity in your Keychain
  (`security find-identity -v -p codesigning`) and a matching
  `.mobileprovision`, obtained the normal way through Xcode or AltServer's
  own account pairing.

## Quick start (novice — the GUI)

1. **Launch the GUI**: `forge gui` → open <http://127.0.0.1:8765>
2. **Drop your .ipa** into the box. The GUI detects the app and the matching
   patch set, shows a small warning if the patch set targets a different
   version (patching is still allowed — hook verification is the safety
   net), and presents one **Patch** button.
3. **Download** the patched IPA (unsigned — ready for AltStore).

No YAML editing, no signing identity, no provisioning profiles needed for
the AltStore path.

## Quickstart (CLI)

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

Try it against the repo's synthetic test fixture — no real app required, and
no need to clone the repo, just download the files:

```bash
curl -LO https://raw.githubusercontent.com/nandan-varma/ipa-forge/main/fixtures/synthetic_app.ipa
curl -LO https://raw.githubusercontent.com/nandan-varma/ipa-forge/main/fixtures/patches/example.yaml
mkdir -p assets && curl -Lo assets/patched_asset.txt \
  https://raw.githubusercontent.com/nandan-varma/ipa-forge/main/fixtures/patches/assets/patched_asset.txt

forge patch --ipa synthetic_app.ipa --patches example.yaml \
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
[`patch-reference`](https://ipa-forge.nandan.fyi/docs/patch-reference).

## Getting certificates and provisioning profiles for AltStore

AltStore Classic re-signs and installs apps using **your own** Apple ID's
development credentials, obtained through AltServer's own pairing flow --
ipa-forge doesn't manage your Apple account. How to find your codesigning
identity and a matching `.mobileprovision`, and how ipa-forge selects
profiles (exact match, wildcard, per-extension), is documented in
[`usage`](https://ipa-forge.nandan.fyi/docs/usage#signing-identity--profile). In short:

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
[`altstore-device-testing`](https://ipa-forge.nandan.fyi/docs/altstore-device-testing) for the
manual checklist.

## Disclaimer

For educational and research purposes only. You must supply your own legally obtained `.ipa`. ipa-forge is not affiliated with, endorsed by, or sponsored by Apple or by the vendor of any application you choose to patch. It distributes no copyrighted app binaries and no reverse-engineered specifics of any third-party app — only a generic patching engine that operates on YAML you supply. Patching or sideloading an app may violate that app's Terms of Service; that risk is yours to assess.

## License

GPLv3-or-later. See [`LICENSE`](LICENSE).
