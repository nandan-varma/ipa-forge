# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-08-26

Documentation-focused release: the docs are now a published site with
AI-agent support, and the PyPI page reflects the corrected install story.
No engine behavior changes.

### Added

- Full documentation site at [ipa-forge.nandan.fyi](https://ipa-forge.nandan.fyi),
  replacing the flat in-repo Markdown docs.
- AI-agent support: `/llms.txt` (site index), `/llms-full.txt` (full site as
  Markdown), `<page>.md` for any doc page, and in-page "Copy Markdown" /
  "Open in ChatGPT/Claude/Cursor" actions.
- `Documentation` and `Changelog` project URLs on PyPI.

### Fixed

- README and docs now lead with `pip`/`pipx install ipa-forge` as the
  primary install path; `pip install -e .` is documented only as the
  from-source path for engine contributors. The previous version only
  documented the editable/source install, with no mention of the published
  package.
- Docs corrected against the actual current CLI/GUI behavior: `forge patch
  --no-sign` is now documented, every `forge hooks`/`forge analysis`
  subcommand has a complete flag reference, and the web GUI docs no longer
  describe a manual YAML/zip-upload flow that was removed from the code
  before 0.1.0 shipped.
- Removed remaining references to specific third-party app names from code
  comments, docstrings, and the GUI.

## [0.1.0] - 2026-08-25

Initial public release.

### Added

- Core patch engine: 17-stage pipeline (extract → dry-run gate → resource
  patches → binary patches → dylib injection → codesign → repackage →
  re-validate) driven entirely by external YAML patch definitions.
- Patch operation types: `binary_replace`, `resource_replace`,
  `resource_add`, `resource_remove`, `plist_edit`, `dylib_inject`.
- Hook verification (`forge hooks verify|extract|audit|find|manifest|diff`):
  cross-checks a dylib's declared runtime hook targets against the actual
  Mach-O class/method tables before signing, and `hooks audit` catches
  hooks a dylib calls but the YAML never declared.
- General-purpose IPA reverse engineering (`forge analysis
  classdump|strings|symbols|security|diff`), plus a read-only `/analysis`
  viewer in the local GUI.
- Per-extension provisioning-profile signing (repeatable `--profile`,
  `ProfilePool`).
- Local FastAPI GUI (`forge gui`) for novice-friendly patch application:
  drop an IPA, auto-detect a matching locally-discovered patch set, produce
  an unsigned output for AltStore.
- GPLv3-or-later license.

### Known limitations

- macOS-only for signing and Mach-O/ObjC analysis (`hooks/`, `analysis/`,
  `signing/`); `bundle/`, `patch/`, and dry-run work cross-platform.
- FairPlay/App Store DRM decryption is explicitly out of scope — every
  command assumes an already-decrypted `.ipa`.
- Instruction-level disassembly, struct field expansion in the type-encoding
  decoder, entitlements diffing, and Swift-native class support are not yet
  implemented.
