# Roadmap to public release

Work-in-progress tracker for finishing the "public release" pass on ipa-forge.
Picking this back up: read this file first, then `docs/architecture.md` and
`docs/extensibility.md` for full context. All items below were scoped and
approved by the user; nothing here needs re-litigating, just execution.

## Already done (committed)

1. **GPLv3-or-later licensing** — `LICENSE` (canonical text), SPDX headers on
   every source file, `pyproject.toml` classifiers/authors/keywords/URLs,
   README license section.
2. **Closed all 3 documented v1 gaps**:
   - `plist_edit` patch operation (`ipa_forge/patch/plist.py`)
   - Per-extension provisioning-profile signing (`ProfilePool` in
     `signing/profile.py`, `MachOTarget.bundle_id`, `--profile` is now
     repeatable on the CLI and multi-upload in the GUI)
   - GUI zip upload for patch assets (`ipa_forge/gui/uploads.py`), plus a
     path-traversal fix found and fixed along the way (upload filenames now
     sanitized via `Path(name).name`)
3. `CLAUDE.md` onboarding doc for future Claude Code sessions in this repo.

Test suite is at **72 passing tests** (65 pre-existing + 7 new CLI tests in
`tests/unit/test_cli.py`) as of this revision.
Run `pytest tests/` to confirm before continuing.

## Remaining work

### 1. Ruff (lint + format) and mypy — DONE

- `[tool.ruff]` + `[tool.mypy]` configs added to `pyproject.toml` (line
  length 120, target py311, rule set E/F/I/UP/B/SIM/BLE/TRY with TRY003
  ignored and B008's immutable-calls extended for typer/fastapi).
- `ruff check .` → 0 findings; `ruff format .` applied repo-wide (was 50
  unformatted files).
- `mypy ipa_forge/` → clean. Note: the earlier assumption that `lief` needs
  an `ignore_missing_imports` override is outdated — lief 1.0 ships its own
  type info, so the 10 findings were real `Optional` narrowing (fixed with a
  `require_slice` helper in `machO/arch.py` and a `str | None` annotation in
  `bundle/inventory.py`), not import stubs.
- Also added `pyrightconfig.json` (venv pin) for LSP-based editors.

### 2. GitHub Actions CI workflow — NOT STARTED

- `.github/workflows/ci.yml`, matrix: `ubuntu-latest` running
  `pytest tests/ -m "not macos"`, and `macos-latest` running the full
  `pytest tests/` (macOS-marked tests that need a real Keychain identity will
  skip gracefully via `pytest.skip()` on a bare CI runner — confirmed this
  behavior is already in place in `tests/conftest.py`'s `synthetic_profile`
  fixture and `test_signing.py`'s `_first_apple_development_identity()`).
- Also run `ruff check`, `ruff format --check`, and `mypy` as CI steps once
  item 1 is done.

### 3. PyPI packaging metadata + CHANGELOG + build validation — PARTIAL

- Build validation done: `python -m build` + `twine check dist/*` both pass
  (sdist + wheel).
- **Still open**: `CHANGELOG.md` (start at `## [0.1.0] - Unreleased`) and the
  guessed GitHub URLs in `pyproject.toml` (see note below).
- `pyproject.toml` already has most metadata (classifiers, authors, keywords,
  project URLs — **note: the GitHub URLs currently point at a guessed
  `github.com/nandanvarma/ipa-forge`; confirm the actual intended
  org/username before this goes further**).

### 4. Update docs to reflect closed gaps; security review pass — DONE

- `README.md`: `plist_edit` added to the patch-definition example.
- `docs/extensibility.md`: "Known v1 scope limits" replaced with a
  "Shipped v1 additions" section covering all three closed gaps.
- `CLAUDE.md`: dependency-direction wording corrected (cli also uses
  altstore/validators directly), lint/typecheck commands documented,
  `bundle/` no longer imports `validators/` (structural IPA validation is a
  pipeline stage now).
- Security review findings fixed:
  - `gui/uploads.py::safe_extract_zip` now translates extraction failures to
    `UploadError` (400, not 500) and enforces zip-bomb caps (member count /
    uncompressed size); zip-slip guard re-verified empirically against `../`,
    absolute-path, deep-traversal, and symlink two-stage attacks.
  - `gui/app.py`: per-request temp dirs cleaned up in a `finally` (output IPA
    moved to a bounded `_outputs` store, capped at 20 with eviction).
  - `patch/loader.py`: `open()` now guarded → `PatchLoadError` surfaced as
    `PipelineError` (clean CLI error instead of a traceback); same for
    `IpaValidationError` in pipeline stage 1.
  - `cli/main.py`: `inspect`/`validate` surface a clean `error:` + exit 1 on
    malformed IPAs instead of a traceback.
  - No other untrusted-path construction found: all bundle-relative YAML
    `path:` values go through `patch/paths.py::resolve_bundle_path`;
    subprocess calls are argv-list only (no shell).

### 5. Confirm + execute GitHub public repo push and PyPI publish

- **Ask the user for the actual GitHub org/username and desired repo name**
  before running `gh repo create` — the `pyproject.toml` URLs currently
  guess `nandanvarma/ipa-forge`, which needs explicit confirmation, not
  silent adoption.
- Confirm visibility (public), then `git remote add origin ...` and
  `git push -u origin main`.
- For PyPI: confirm the user has `twine` credentials configured
  (`~/.pypirc` or `TWINE_USERNAME`/`TWINE_PASSWORD`/token env vars) and
  wants to publish now vs. later; only then run `twine upload dist/*`.
- Both of these are the two genuinely irreversible/visible actions in this
  whole task — everything else (items 1-4 above) is safe to do without
  further check-ins.

### 6. Open audit findings (from the second full audit) — ALL FIXED

All nine findings from the report-only pass are now implemented, each with a
regression test. Suite grew 72 → 91.

- **F1 (fixed) Silent no-op on zero matching ops**: `pipeline.py` warns
  (dry-run) / raises `PipelineError` (real run) when the supplied definition
  resolves to zero ops. Tests: `test_cli.py::test_patch_non_matching_*`.
- **F2 (fixed) Schema errors traceback**: `loader.py` wraps
  `pydantic.ValidationError` → `PatchLoadError` (single-line message); empty
  definitions are schema errors via `patches: Field(min_length=1)`.
  Tests: `test_resolver_and_schema.py::test_load_patch_definition_*`,
  `test_cli.py::test_patch_empty_definition_is_a_clean_error`.
- **F3 (fixed) resource_remove on a directory**: dry-run requires
  `dest.is_file()`; all resource applies catch `OSError` → `PatchResult`.
  Test: `test_resources.py::test_resource_remove_rejects_directory_in_dry_run`.
- **F4 (fixed) dry-run demands signing inputs**: `--identity`/`--profile`
  optional on CLI and GUI; enforced (exit 1 / 400) only when not dry-running.
  Tests: `test_cli.py::test_patch_dry_run_without_identity_or_profile`,
  `test_gui_app.py`.
- **F5 (fixed) ProfilePool first-wins on duplicates**: `select_for` raises
  on duplicate exact or duplicate wildcard matches. Tests:
  `test_profile_pool.py::test_duplicate_*_raise_ambiguity_error`.
- **F6 (fixed) Nested profiles never bundle-id-validated**: single-profile
  mode warns when the lone profile doesn't authorize a profile-bearing
  target. Tests: `test_sign_bundle.py` (stub provider, no macOS).
- **F7 (fixed) Dead code**: `Manifest.write()` removed; `available_archs`
  kept as intended public tooling API.
- **F8 (documented) parse_version ignores non-numeric segments**: exact-vs-
  range semantics clarified in `version.py` docstring; no behavior change.
- **F9 (documented) source: paths unsandboxed**: trusted-input model
  documented in `patch/resource.py` module docstring; no behavior change.

## Quick resume checklist

```bash
cd /Users/nandan/dev/ipa-forge
source .venv/bin/activate
pytest tests/                     # 72 passing as of this revision
ruff check . && ruff format --check .
mypy ipa_forge/
git log --oneline
```

Then continue at "Remaining work" items 2, 3 (CHANGELOG/URLs), and 5.

---

# Reverse-engineering roadmap (`forge analysis`)

Future phases for `ipa_forge/analysis/` (the general-purpose IPA
reverse-engineering package — class-dump, strings, symbols, security, diff;
see [`docs/reverse-engineering.md`](docs/reverse-engineering.md) for what's
already shipped) that were scoped out of the initial build, in priority
order. Each entry names the concrete files/anchors a future session needs to
pick this up cold — point Claude Code at this file and the relevant item.

## 1. Instruction-level disassembly (capstone)

**What**: `forge analysis disasm <selector-or-symbol> --ipa App.ipa` —
disassemble one method's IMP or an arbitrary symbol's function body (arm64
only), rendered as an annotated instruction listing (branch targets resolved
to symbol names where possible).

**Why deferred**: a new heavyweight dependency (`capstone`) and a much larger
correctness surface than everything shipped so far (arm64 instruction
decoding, branch-target resolution, ObjC message-send call-site annotation
i.e. recognizing `bl _objc_msgSend` and decorating it with the resolved
selector from `x1`/register tracking). Static metadata (what shipped) has a
much better effort-to-value ratio and was the priority.

**Source of truth for the next session**:
- `ipa_forge/analysis/symbols.py::analyze_symbols` already resolves a
  symbol's `.value` (address) via LIEF — the IMP address for a given
  selector is reachable the same way (`MachOClass` doesn't currently carry
  method addresses; `parse_methods` in `ipa_forge/machO/objc.py` reads
  `imp` at entry offset `+16` for non-relative method_t (plain pointer, same
  as `sel_ptr`/`types_ptr`), or a self-relative 32-bit offset at `+8` for the
  relative (entsize-12) form — self-relative to that field's own address,
  same convention already implemented for `sel`/`types` in that function —
  **not yet extracted**, would need to be added there first).
- `pyproject.toml`'s `[project.dependencies]` — capstone would be optional
  (`[project.optional-dependencies]`), following the pattern the `dev` group
  already uses, since not every consumer needs disassembly.
- Fat-binary arch selection is already solved: `ipa_forge/machO/arch.py`
  (`load_macho`, `available_archs`) — reuse directly, same as
  `analysis/symbols.py` and `analysis/security.py` do.
- `ipa_forge/analysis/type_encoding.py::decode_method_signature` already
  reconstructs the C signature around a method — a disassembly view should
  print that signature as a header above the instruction listing.

## 2. Struct/union field expansion in the type-encoding decoder

**What**: `ipa_forge/analysis/type_encoding.py::decode_type` currently
renders `{CGRect={CGPoint=dd}{CGSize=dd}}` as just `struct CGRect` (tag name
only, no field list). Real class-dump tools expand nested field types.

**Why deferred**: correct recursive field-list rendering needs to track
per-field names too (Objective-C struct encodings often omit field names
entirely, unlike ivars/properties — the `{CGRect=dd}` form with no field
names is common), which requires a fallback to a small built-in table of
well-known Apple struct layouts (CGRect, CGPoint, CGSize, CGAffineTransform,
UIEdgeInsets, ...) for the common case where the encoding itself doesn't
carry field names.

**Source of truth**: `ipa_forge/analysis/type_encoding.py` — the `{`/`(`
branches of `decode_type()` and `read_one_type()`'s balanced-brace tokenizer
already isolate the exact substring to expand; this is additive parsing
inside that one function, no data-model changes needed.
`tests/unit/test_type_encoding.py::test_decode_struct_by_name` is the
existing behavior to keep passing (tag-name fallback should remain the
behavior for unrecognized/unnamed-field structs).

## 3. Entitlements diffing

**What**: extend `forge analysis diff` (`ipa_forge/analysis/diff.py`) to
also report entitlement changes between two builds.

**Why deferred, not just delayed**: reading entitlements requires shelling
out to `codesign -d --entitlements`, and `ipa_forge/signing/backend.py` is
the *only* module allowed to invoke `codesign`/`security` — see
`docs/architecture.md`'s "Hard constraints" section. `analysis/` is
deliberately signing-independent (works without macOS, no Keychain, no
identity). A real entitlements diff belongs as a `signing/`-side feature
(e.g. `forge inspect --entitlements`, reusing
`signing/backend.py`'s existing shell-out plumbing), not bolted onto
`analysis/diff.py` by having it import `signing/`.

**Source of truth**: `ipa_forge/signing/backend.py` (the codesign wrapper),
`ipa_forge/signing/provider.py::LocalIdentityProvider` (for the pattern of
shelling to `security`/`codesign` and parsing output).
`ipa_forge/analysis/diff.py`'s module docstring already documents this
boundary — read it first.

## 4. Swift-native class support

**What**: classes with no Objective-C interop (pure Swift, no `@objc`) are
invisible to `machO/objc.py`'s classlist walker entirely — it only walks
`__objc_classlist`. Swift's own metadata format (`__swift5_types`,
`__swift5_fieldmd`, etc.) is a different, more complex layout.

**Why deferred**: a substantial second parser, and most iOS apps worth
patching (the existing YouTube/Spotify/Instagram patch sets) are
predominantly Objective-C at the UI/hook-target layer even when Swift is
used elsewhere — the existing gap is already called out honestly rather
than silently mis-parsed (see `ipa_forge/hooks/verify.py`'s handling of
`_TtC`-mangled class names: reported `unverified`, never guessed).

**Source of truth**: `ipa_forge/hooks/verify.py`'s `_TtC` handling (search
for `startswith("_Tt")`) is the current honest-gap behavior to preserve.
`ipa_forge/machO/objc.py::_analyze_thin` is where a Swift metadata pass
would be added, structurally parallel to the existing
`__objc_protolist`/`__objc_catlist` passes.

## 5. Re-symbolication against a local dyld shared cache

**What**: on a real device dump, many imported symbols resolve into the
dyld shared cache rather than a standalone dylib — `forge analysis symbols`
reports them as bare imports with no further context. A `--shared-cache
<path>` option could resolve those against an extracted shared cache (the
`ipsw` tool's approach).

**Why deferred**: needs a shared-cache extraction/parsing dependency and
only matters for on-device dumps, not the App-Store-IPA-plus-tweak workflow
this project centers on.

**Source of truth**: `ipa_forge/analysis/symbols.py::analyze_symbols` is
where the resolution step would hook in (currently just lists
`imported_symbols` by name via LIEF's `CATEGORY.UNDEFINED` symbols).

## 6. `--format json` on the analysis commands

**What**: `forge analysis classdump/strings/symbols/security/diff --format
json` emitting the underlying dataclasses as JSON, for scripting/CI use —
today only the human-readable `render_*` text functions are exposed at the
CLI layer.

**Why deferred**: lowest priority of this list; the text output is
already `grep`-friendly per the project's established convention (see
`cli/hooks.py`'s `hooks_extract` comment on not truncating output), and no
consumer has asked for structured output yet.

**Source of truth**: every `analyze_*`/`diff_analyses` function already
returns a plain dataclass (`ipa_forge/analysis/{classdump,strings,symbols,
security,diff}.py`) — a `--format json` flag is a `dataclasses.asdict()` +
`json.dumps()` away in `ipa_forge/cli/analysis.py`, no engine changes
needed. `manifest.py::Manifest.to_json()` is the existing precedent for
this pattern elsewhere in the codebase.

## Explicitly not on this roadmap

**FairPlay/App Store DRM decryption** — not a scope-limited future phase,
a hard boundary. Every command in `analysis/` assumes an already-decrypted
`.ipa`, same as the rest of ipa-forge; decryption is DRM-circumvention
tooling, a different risk category from static analysis of a binary you
already have rights to inspect. See `ipa_forge/analysis/__init__.py`'s
module docstring.
