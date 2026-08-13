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

Test suite is at **65 passing tests** as of the last commit
(`475fe6a Close gap: GUI multi-file/zip upload for patch assets`).
Run `pytest tests/` to confirm before continuing.

## Remaining work

### 1. Ruff (lint + format) and mypy — IN PROGRESS, not yet started for real
- Add `[tool.ruff]` config to `pyproject.toml` (line length, target-version
  py311, sensible rule set — the codebase already uses `from __future__
  import annotations` everywhere and modern `X | None` syntax throughout).
- Add `[tool.mypy]` config. Known friction points to expect:
  - `lief` is a C-extension with no type stubs → needs
    `[[tool.mypy.overrides]] module = "lief.*" ignore_missing_imports = true`.
  - `types-PyYAML` is already listed in `dev` deps for this reason.
  - pydantic v2 models should type-check cleanly out of the box.
- Run `ruff check .` and `ruff format --check .`, fix violations (prefer
  `ruff format .` for mechanical fixes, hand-fix lint findings).
- Run `mypy ipa_forge/`, fix real issues; use `# type: ignore[code]` sparingly
  and only with a comment explaining why, not blanket ignores.
- Both dependencies are already declared in `pyproject.toml`'s `dev` extra
  (`ruff>=0.6`, `mypy>=1.11`) — just need `pip install -e .[dev]` and to
  actually configure + run them.

### 2. GitHub Actions CI workflow
- `.github/workflows/ci.yml`, matrix: `ubuntu-latest` running
  `pytest tests/ -m "not macos"`, and `macos-latest` running the full
  `pytest tests/` (macOS-marked tests that need a real Keychain identity will
  skip gracefully via `pytest.skip()` on a bare CI runner — confirmed this
  behavior is already in place in `tests/conftest.py`'s `synthetic_profile`
  fixture and `test_signing.py`'s `_first_apple_development_identity()`).
- Also run `ruff check`, `ruff format --check`, and `mypy` as CI steps once
  item 1 is done.

### 3. PyPI packaging metadata + CHANGELOG + build validation
- `pyproject.toml` already has most metadata (classifiers, authors, keywords,
  project URLs — **note: the GitHub URLs currently point at a guessed
  `github.com/nandanvarma/ipa-forge`; confirm the actual intended
  org/username before this goes further**).
- Add `CHANGELOG.md` (Keep a Changelog style is fine — this is a from-scratch
  project so it can start at `## [0.1.0] - Unreleased` and list the phases
  already built).
- `python -m build` to produce sdist + wheel, then `twine check dist/*` to
  validate metadata. **Do not run `twine upload` without the user's explicit
  go-ahead and their own PyPI credentials** — confirmed name availability
  already (`ipa-forge` was unclaimed on PyPI as of this check).

### 4. Update docs to reflect closed gaps; security review pass
- `README.md`'s "Known limitations" section still lists the GUI single-file
  upload, single-profile-for-everything, and no-plist_edit limitations as
  current — **all three are now closed**, so that section needs editing to
  remove/update those three bullets.
- `docs/extensibility.md`'s "Known v1 scope limits" section has the same
  three items — same fix needed there.
- Run a focused security review over the diff since the last full review:
  particularly `ipa_forge/gui/` (upload handling, now has zip extraction),
  `ipa_forge/signing/` (profile pool selection logic), and confirm no other
  places construct filesystem paths from untrusted input without
  sanitization (the GUI upload-filename issue found and fixed during gap
  closure is exactly the class of bug to keep hunting for — check
  `ipa_forge/cli/main.py` and any place a bundle-relative `path:` from a
  patch YAML gets joined without going through
  `ipa_forge/patch/paths.py::resolve_bundle_path`).
- Consider invoking the `/security-review` skill for a structured pass
  instead of doing this ad hoc.

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
pytest tests/                     # confirm still green (65 passed as of this writing)
git log --oneline                 # confirm you're picking up after 475fe6a
```

Then continue at "Remaining work" item 1 above.
