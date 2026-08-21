# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A generic, data-driven iOS IPA patcher: extract a user-supplied `.ipa`, apply
version-aware patches from external YAML (binary byte patches, resource
replace/add/remove, dylib injection), and re-sign the result into a
standard-structure `.ipa` that AltStore Classic can install/refresh.

Full design rationale lives in `docs/architecture.md` (component map, the
17-stage pipeline, two real bugs found empirically during implementation)
and `docs/extensibility.md` (how to add a patch operation type, known v1
scope limits). User-facing references: `docs/usage.md` (CLI/GUI workflows),
`docs/patch-reference.md` (the full YAML patch-definition contract),
`docs/reverse-engineering.md` (`forge analysis`: class-dump, strings,
symbols, security, diff), and `docs/troubleshooting.md` (error message ->
cause -> fix). Read those before making non-trivial changes to
`pipeline.py` or `signing/`. **`STATE.md`** is the project's own
session-handoff doc (current status, in-flight work, decisions not to
undo) — read it first in any new session.

## Documentation map

- `STATE.md` — session state & operating knowledge; read this first.
- `docs/README.md` — the doc index (which doc for what).
- `docs/adding-an-app.md` — port a new app end-to-end.
- `docs/adding-a-feature.md` — add a feature to a hook dylib (conventions).
- `docs/patch-reference.md` / `docs/usage.md` — YAML + CLI reference.
- `docs/reverse-engineering.md` — `forge analysis` (class-dump, strings,
  symbols, security, version diffing).
- `ROADMAP.md` — deferred work, incl. reverse-engineering roadmap
  (disassembly, Swift support, etc.) with file/anchor pointers to resume.
- The patch sets (`patches/youtube/`, `patches/spotify/`,
  `patches/instagram/` — private submodules, `git clone --recursive`) each
  have a `PLAYBOOK.md` runbook with the app-specific commands and gotchas.

## Commands

```bash
# Setup (macOS with Xcode CLT; Python 3.11+)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run all tests (includes real codesign signing against your local Keychain identity)
pytest tests/

# Run only tests that don't need macOS signing tools (e.g. to check Linux-safe code paths)
pytest tests/ -m "not macos"

# Run a single test
pytest tests/unit/test_binary_patch.py::test_binary_replace_apply_mutates_file -v

# CLI (installed as `forge` via pyproject.toml's [project.scripts])
forge inspect path/to/App.ipa
forge validate path/to/App.ipa
forge patch --ipa <ipa> --patches <patches.yaml> --identity <id> --profile <profile> --output <out.ipa> [--dry-run] [--verbose]
forge export-source --ipa <patched.ipa> --download-url <url> --output source.json
forge gui   # launches the local FastAPI GUI on 127.0.0.1:8765 (+ /analysis RE viewer)

# Hook verification (forge hooks --help): verify | extract | audit | find | manifest | diff
forge hooks verify --ipa <ipa> --patches <patches.yaml>

# General-purpose IPA reverse engineering (forge analysis --help), see docs/reverse-engineering.md
forge analysis classdump --ipa <ipa> [--class NAME | --search REGEX]
forge analysis diff --old <old.ipa> --new <new.ipa>

# Regenerate the synthetic test fixture (only needed if changing its shape)
scripts/rebuild_fixture.sh
```

Lint and typecheck (config lives in `pyproject.toml`): `ruff check .`,
`ruff format --check .`, `mypy ipa_forge/`.

## Architecture

**Hard constraint, never violate it**: Apple's code signature format
(CodeDirectory, CMS, SuperBlob, DER entitlements) is never reimplemented.
`ipa_forge/signing/backend.py` is the *only* module allowed to invoke
`codesign`/`security`; everything else shells out through it.

**Dependency direction is one-way and enforced by convention, not tooling**:
`patch/` and `signing/` both depend on `bundle/` but never on each other.
`machO/` (arch selection, dylib injection, and the shared ObjC/Mach-O
analysis engine in `machO/objc.py`) also depends on `bundle/`. `hooks/` and
`analysis/` are siblings that both depend on `machO/objc.py`'s
`MachOAnalysis` and never import each other. `pipeline.py` orchestrates
`patch/`, `signing/`, `hooks/`, `validators/`, and `manifest.py`.

**Hook verification (`ipa_forge/hooks/`)**: the `hooks:` block in a patch
definition declares the dylib's runtime hook targets; `pipeline.py` verifies
them against the app's main binary (class table + method lists + selrefs,
chained-fixup aware — parsed by `machO/objc.py`, shared with `analysis/`)
during the dry-run gate and fails when a `required` hook can't attach. This
is the safety net for version drift — a renamed/removed class silently
kills a hook otherwise. The CLI surface is `forge hooks
verify|extract|audit|find|manifest|diff`. `cli/` and `gui/` call into
`pipeline.py` for patching — neither touches `patch/` or `signing/`
directly; `cli/` additionally uses `altstore/` (export-source) and
`validators/` (inspect/validate) directly, and structural IPA validation
(stage 1) is run by the pipeline, not by `bundle/`.

**General-purpose reverse engineering (`ipa_forge/analysis/`)**:
class-dump, strings, symbols, security posture, and version diffing for
*any* IPA — not tied to a patch definition. Built on the same
`machO/objc.py` engine `hooks/` uses; CLI surface is `forge analysis
classdump|strings|symbols|security|diff`, plus a read-only `/analysis`
page in the GUI. FairPlay decryption and instruction-level disassembly are
deliberately out of scope — see `ipa_forge/analysis/__init__.py`'s
docstring and `ROADMAP.md`.

**The core engine is app-agnostic**: it understands patch operation *types*
(`binary_replace`, `resource_replace`, `dylib_inject`, ...) via the
`PatchOperation` protocol (`patch/base.py`), never a specific bundle id or
byte pattern — those only ever come from user-supplied YAML parsed by
`patch/schema.py` (pydantic) and `patch/loader.py`.

### The pipeline (`ipa_forge/pipeline.py`)

A fixed 17-stage sequence: extract → bottom-up inventory → parse Info.plist
→ resolve applicable patch definitions → **dry-run gate** (every op must
pass before anything mutates) → apply resources → apply binary patches →
apply dylib injection (deliberately last — LIEF rewrites can shift binary
offsets) → re-validate → **emit manifest** (pre-signing, for debugging) →
load/validate provisioning profile → reconcile entitlements → embed profile
→ recursive bottom-up codesign → verify → repackage → final re-validation
(re-extract from scratch). The ordering encodes real dependencies; see
`docs/architecture.md` for why each ordering constraint exists.

### Two non-obvious things found empirically (both documented + tested)

1. **`codesign` must target bundle *directories*, not raw executable
   files**, for anything that is itself a bundle (main app, `.framework`,
   `.appex`, watch app) — otherwise the `_CodeSignature/CodeResources` seal
   covering `Info.plist` never gets created and a later
   `codesign --verify --strict` fails. See
   `signing/pipeline.py::sign_target_path`.
2. **LIEF's `Binary.write()` on a single arch slice of a fat/universal
   Mach-O silently discards every other architecture.** Injection code must
   always write back through the parent `FatBinary` object
   (`fat.write(path)`), never the extracted slice directly. See
   `machO/injector.py`. `patch/binary.py`'s raw byte-offset read/write is
   unaffected since it never goes through LIEF's write path.

### Signing abstraction

`signing/provider.py::SigningProvider` is an ABC with `LocalIdentityProvider`
(signs via a Keychain identity — the only implementation that exists today)
and `AltStoreCredentialProvider` (deliberate `NotImplementedError` stub for
future AltServer-account-based signing — see `docs/extensibility.md` before
implementing it).

### Linux support boundary

`ipa_forge/signing/` needs `codesign`/`security` (macOS only). Less obvious:
`ipa_forge/machO/objc.py` (the shared ObjC/Mach-O analysis engine —
`analyze_macho`/`analyze_bundle`) shells out to `otool`/`lipo`, which are
also macOS-only, unlike the rest of `machO/` (`arch.py`, `injector.py` are
LIEF-backed and Linux-safe). This means **`hooks/` and `analysis/` are not
Linux-safe either** — both are built on `machO/objc.py`. Everything else
(`bundle/`, `patch/`, `machO/arch.py`, `machO/injector.py`, dry-run) works
without macOS. The boundary is which modules a code path imports, not a
runtime OS check — no hooks/analysis tests are `@pytest.mark.macos`-gated
today even though they need Xcode CLT, which is only a gap if someone
actually runs them on a bare Linux CI runner.

### Test fixture

`fixtures/synthetic_app.ipa` is a real, from-scratch arm64 iOS Mach-O app —
main executable + linked framework + an
*unlinked* standalone dylib (the dylib-injection target) + a resource file —
built via `scripts/rebuild_fixture.sh` directly against the iOS SDK rather
than a hand-authored Xcode project. It's checked in as a binary artifact;
tests consume it as-is. `tests/conftest.py` also has fixtures for compiling
throwaway Mach-O binaries on the fly (`compiled_macho_binary`,
`fat_macho_binary`) and for generating a self-signed test
`.mobileprovision` (`synthetic_profile`) using whatever real Apple
Development identity is in the local Keychain — tests requiring real
signing are marked `@pytest.mark.macos` and skip gracefully if no suitable
local identity/profile exists.
