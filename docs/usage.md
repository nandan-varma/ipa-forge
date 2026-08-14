# Usage Guide

Complete walkthrough of installing, patching, signing, and distributing an IPA
with ipa-forge — via the `forge` CLI and the local web GUI.

## Requirements

- **macOS** with Xcode Command Line Tools (`xcode-select -p` prints a path).
  Signing shells out to Apple's own `codesign`/`security` and is never
  reimplemented. Everything up to and including patch dry-run also works on
  Linux (see `docs/extensibility.md`).
- **Python 3.11+**.
- A **codesigning identity** in your Keychain and a matching
  **provisioning profile** (see [Signing identity & profile](#signing-identity--profile)).

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
forge --version
```

This installs the `forge` CLI.

## End-to-end workflow

### 1. Inspect the IPA

```bash
forge inspect path/to/App.ipa
```

Prints the bundle id, version, main executable, and the executable inventory in
bottom-up signing order. This tells you the `bundle_id` and `version` your
patch definition must target, and the exact executable names to patch.

### 2. Write a patch definition

See the [Patch Definition Reference](patch-reference.md) — every operation
type, field, and matching rule. At minimum:

```yaml
target:
  bundle_id: "com.example.app"
  version: { exact: "1.2.3" }
patches:
  - id: "swap-asset"
    type: resource_replace
    path: "asset.txt"
    source: "assets/patched_asset.txt"
```

### 3. Dry-run (safe, no mutation, no signing)

```bash
forge patch --ipa path/to/App.ipa --patches patches.yaml \
  --output patched.ipa --dry-run
```

`--identity` and `--profile` are **not needed** for a dry run. Every operation
must pass the dry-run gate before anything would be applied; the result line
tells you how many operations would run. If the definition's target doesn't
match the IPA, you get a warning instead of a silent no-op.

### 4. Patch and re-sign for real

```bash
forge patch --ipa path/to/App.ipa --patches patches.yaml \
  --identity "Apple Development" \
  --profile path/to/profile.mobileprovision \
  --output patched.ipa --verbose
```

`--profile` is repeatable — supply one per app extension/watch app, matched by
each target's own bundle id:

```bash
forge patch --ipa App.ipa --patches patches.yaml \
  --identity "Apple Development" \
  --profile main.mobileprovision \
  --profile extension.mobileprovision \
  --output patched.ipa
```

The output is a standard-structure `Payload/<App>.app` IPA that AltStore
Classic can install and refresh.

### 5. (Optional) Produce an AltStore source.json entry

```bash
forge export-source --ipa patched.ipa \
  --download-url https://example.com/patched.ipa \
  --output source.json
```

Emits an AltStore Classic source entry (`name`, `bundleIdentifier`, `version`,
`buildVersion`, `downloadURL`, `size`, `sha256`) for hosting the patched IPA
yourself.

### 6. Install on a device

Follow the manual AltStore Classic checklist in
[`docs/altstore_device_testing.md`](altstore_device_testing.md).

## CLI reference

Run any command with `--help` for the full option list.

### `forge inspect <ipa>`

Prints bundle metadata and the executable inventory (bottom-up signing order,
with each target's kind and bundle-relative path).

### `forge validate <ipa>`

Validates that the IPA is a well-formed archive with exactly one
`Payload/*.app`, that `Info.plist` is parseable, and that the main executable
is present — without patching or signing anything.

### `forge patch`

| Option | Meaning |
| --- | --- |
| `--ipa <path>` | Input `.ipa` (required) |
| `--patches <path>` | Patch definition YAML/JSON file (required) |
| `--identity <str>` | Codesigning identity: SHA-1 hash or unique name substring. **Not needed for `--dry-run`**; required otherwise |
| `--profile <path>` | `.mobileprovision`, repeatable (one per extension/watch app). **Not needed for `--dry-run`**; at least one required otherwise |
| `--output <path>` | Output `.ipa` path (required) |
| `--dry-run` | Validate patches without mutating or signing anything |
| `--verbose` | Print the full manifest on success |

Exit codes: `0` success, `1` any error (with a single-line `error:` message on
stderr — no tracebacks).

### `forge export-source`

| Option | Meaning |
| --- | --- |
| `--ipa <path>` | The patched, signed IPA to describe |
| `--download-url <url>` | URL the IPA will be hosted at |
| `--output <path>` | Output `source.json` path |

### `forge gui`

Launches the local web GUI on `127.0.0.1:8765` by default (override with
`--host`/`--port`). The GUI wraps the same pipeline as `forge patch`.

### `forge --version`

Prints the installed version.

## Hook verification (`forge hooks`)

Dylib tweaks silently break when a new app version renames/removes hook
targets. Three commands turn that into a checkable report:

```bash
# Verify every hook declared in a patch definition's `hooks:` block
forge hooks verify --ipa App.ipa --patches patch.yaml

# Dump the ObjC class table (classes, superclasses, method lists)
forge hooks extract --ipa App.ipa --class YTPlayerResponse
forge hooks extract --ipa App.ipa --search "AdBreak"

# Scan tweak sources for hook calls and verify each against the binary
forge hooks audit --ipa App.ipa --dir dylib/
```

**Fast iteration with `--app-dir`.** Every command re-extracts the full IPA
(seconds to tens of seconds on a large app) unless you point it at an
already-extracted bundle instead — pass `--app-dir Payload/<App>.app` (and
then omit `--ipa`) and the analyze/verify/fix loop becomes instant:

```bash
forge patch --ipa App.ipa --patches patch.yaml --output /tmp/x.ipa --dry-run
forge hooks verify --app-dir /tmp/x.app --patches patch.yaml   # no re-extract
```

A class or selector that the class-table walk *missed* (a parser gap, not a
rename) is now reported honestly: when the name exists as a string somewhere
in the binary, `missing-class` / `missing-selector` become `unverified` with
a "string present … the walk missed it" hint — the old manual
`strings <binary> | grep` cross-check is automated. Swift-mangled (`_TtC…`)
classes absent from the parsed table are reported `unverified`, never
mislabeled as system classes.

`forge patch --dry-run` also verifies the definition's `hooks:` block
automatically and prints an attach summary; `required: true` hooks that
can't attach fail the run before anything mutates. See
`docs/patch-reference.md` → "The `hooks` block".

## Porting a dylib patch set to a new app version

If your patch set injects a hook dylib, declare its hook targets in the
definition's `hooks:` block (see `docs/patch-reference.md` → "The `hooks`
block"). Then porting is:

```bash
# 1. bump target.version in the definition
# 2. dry-run: reports every hook that would silently no-op on the new binary
forge patch --ipa New.ipa --patches patch.yaml --output /tmp/x.ipa --dry-run
# 3. for each flagged hook, find what replaced the class/selector
forge hooks extract --ipa New.ipa --search "<old class substring>"
# 4. fix the tweak source, rebuild, re-run the dry-run until required hooks pass
```

A complete, YouTube-specific runbook lives at
`patches/youtube/PLAYBOOK.md`.

### Generating and diffing hook manifests

```bash
# Emit a `hooks:` block from the tweak sources (direct + unambiguous
# variable-resolved hook calls); mark load-bearing ones required:
forge hooks manifest --dir dylib/ --required hooks-required.txt

# Porting aid: compare hook attachment between two IPAs, highlight hooks
# that regressed (would no-op on the new version), exit 1 if a required
# hook broke:
forge hooks diff --old prev.ipa --new next.ipa --patches patch.yaml
```

The scanner recognizes any `<prefix>HookInstance/HookClass/AddInstanceMethod`
call with an inline `NSClassFromString(@"X")` (or a file-scoped
`cls = NSClassFromString(@"X")` assignment), plus class names passed through
a local resolver helper — any function whose body calls `NSClassFromString`
and that is invoked as `resolver("X")` at the hook call site. Helper/loop-
based hooks whose class is *passed into another function* before reaching the
hook call are not traced and must be declared manually in the definition's
`hooks:` block — which is what the YouTube/Spotify/Instagram patch sets do.

## Signing identity & profile

ipa-forge re-signs with **your own** Apple development credentials — it never
manages your Apple account.

1. **Identity**: `security find-identity -v -p codesigning` lists the
   codesigning identities in your Keychain. Pass either the full SHA-1 hash or
   a unique substring of the name (e.g. `"Apple Development"`). Ambiguous or
   unmatched substrings fail loudly, listing candidates.
2. **Profile**: profiles installed by Xcode live under
   `~/Library/MobileDevice/Provisioning Profiles/*.mobileprovision`. Inspect
   one with `security cms -D -i <profile>`.
3. The profile's `Entitlements.application-identifier` must authorize the
   bundle id being signed — exactly, or via a wildcard `TEAMID.*` profile.

`forge patch` validates profiles up front (expiry, bundle-id match) and fails
with an actionable error before touching your IPA if they don't qualify.

Profile selection rules (see `signing/profile.py::ProfilePool`):

- An **exact** bundle-id match wins; otherwise a **wildcard** (`*`) profile;
  otherwise a **single** supplied profile is used for everything (the legacy
  behavior); otherwise an error listing the available patterns.
- Two profiles authorizing the same bundle id (or two wildcards) is an
  ambiguity error, not a silent first-win.
- In single-profile mode, if the lone profile doesn't authorize an app
  extension's bundle id you get a warning (it is still embedded, matching
  legacy behavior) — supply a matching profile for that extension to silence it.

## The web GUI

`forge gui` → open <http://127.0.0.1:8765>.

- **IPA** — the `.ipa` to patch (required).
- **Patch definition** — a single `.yaml`/`.yml`/`.json`, or a **zip** of the
  patch directory (definition + its `assets/` folder) when you use
  `resource_replace`/`resource_add`. The zip must contain exactly one
  top-level definition file; its `assets/` resolve relative to it.
- **Provisioning profile(s)** — select several to sign each extension/watch
  app with its own profile (multiple selection).
- **Signing identity** — SHA-1 or name substring.
- **Dry run switch** — validates only, no signing; the profile/identity fields
  gray out. Not needed for dry runs.
- **Result card** — shows "Patched"/"Dry Run OK", the bundle/version, a
  per-operation status list, and a **Download patched.ipa** button.

The GUI is a single-user localhost tool: requests are processed in-process and
outputs are kept for download (bounded, oldest evicted). It is not designed as
a hosted multi-user service.

## What you get back

`forge patch` writes a standard `Payload/<App>.app` zip. The manifest
(`--verbose` or the GUI result card) lists every applied operation, every
file added/modified/removed, the Mach-O files touched, the profile used, and
the output SHA-256 — use it to confirm the patch did what you expected before
installing.

## Related

- [`adding-an-app.md`](adding-an-app.md) — port a new app
- [`adding-a-feature.md`](adding-a-feature.md) — add a feature
- [`patch-reference.md`](patch-reference.md) — the YAML contract
- [`troubleshooting.md`](troubleshooting.md) — errors
- [`README.md`](README.md) — docs index
