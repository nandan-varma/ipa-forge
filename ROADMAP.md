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

- `README.md` "Known limitations": stale GUI single-file-upload bullet
  removed; `plist_edit` added to the patch-definition example.
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
