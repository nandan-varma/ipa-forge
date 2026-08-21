# STATE.md — project state & operating knowledge

**Read this first in any new session.** It captures the state of the world:
what this project is, what works, where things live, decisions that matter,
and how to resume. The full documentation map is in
[`docs/README.md`](docs/README.md); the how-to guides are
[`docs/adding-an-app.md`](docs/adding-an-app.md) and
[`docs/adding-a-feature.md`](docs/adding-a-feature.md). Deferred
reverse-engineering work (disassembly, etc.) is tracked in
[`ROADMAP.md`](ROADMAP.md) — point a future session there to resume it.

## What this is

A generic, data-driven iOS IPA patcher (`forge`, Python) plus two concrete
patch sets that produce working modded IPAs for AltStore sideloading:
**YouTube 21.32.4** and **Spotify 9.1.72**. The patcher applies YAML patch
definitions (resources, binary patches, plist edits, dylib injection),
verifies every hook a dylib relies on against the actual binary, and emits an
unsigned IPA that AltStore signs at install.

## Current state (verified working on-device)

| App | Version | Patch set | Status |
| --- | --- | --- | --- |
| YouTube | 21.32.4 | `patches/youtube/youtube.yaml` | ✅ adblock + sign-in + ~75 settings toggles; sideloaded & tested |
| Spotify | 9.1.72 | `patches/spotify/spotify.yaml` | ✅ premium unlock + adblock + session protection + settings; sideloaded & tested |

Delivered IPAs live in `/Users/nandan/dev/ytlite-ipa/`:
`YouTubeMod_21.32.4_unsigned.ipa`, `SpotifyMod_9.1.72_unsigned.ipa`.

## Where things live

| Path | What |
| --- | --- |
| `ipa_forge/` | The patcher: `pipeline.py` (17-stage), `patch/` (operations), `signing/`, `machO/objc.py` (shared ObjC/Mach-O analysis engine), `hooks/` (hook verification + source scanner, built on `machO/objc.py`), `analysis/` (general-purpose IPA reverse engineering: class-dump, strings, symbols, security, diff — also built on `machO/objc.py`; see `docs/reverse-engineering.md`), `patches.py` (patch-set registry), `cli/` (`forge`, `forge hooks`, `forge analysis`), `gui/` (novice patch UI + read-only `/analysis` RE viewer), `bundle/`, `validators/` |
| `patches/youtube/`, `patches/spotify/` | The patch sets: `<app>.yaml` (single canonical definition, version inside), `dylib/` (hook sources + build.sh), `PLAYBOOK.md`/`README.md`/`SOURCES.md` |
| `docs/` | Documentation map + how-to guides + reference |
| `/tmp/eevee3`, `/tmp/spotc_ipa.ipa` | Reference material (EeveeSpotify source, a working SpotC IPA) — reclone if missing |

## How to work (the loop)

1. **Resume here** → `docs/README.md` → the app's `PLAYBOOK.md`.
2. **Build**: `dylib/build.sh` → `forge patch --dry-run` (hooks gate) →
   `forge patch --no-sign`.
3. **Device loop**: sideload via AltStore → user reports → fix → rebuild.
4. **New IPA / port**: `docs/adding-an-app.md`; use
   `forge hooks diff --old A.ipa --new B.ipa --patches <yaml>` for what broke.
5. **New feature**: `docs/adding-a-feature.md` (key → default → impl →
   settings row → hooks declaration).
6. **Hook suspicious**: `forge hooks find <selector> --ipa <ipa>` — real
   method or `referenced-only` (no IMP to swizzle)? `unverified` = likely
   attaches (declared as a method somewhere); `referenced-only` = cannot
   attach. Regenerate the manifest with
   `tools/generate_hooks_manifest.py --inplace youtube.yaml` (covers
   ytfHookConfigBool now).

## Decisions & lessons (do not undo)

- **Load model (Spotify)**: the dylib constructor is **inert** — hooks install
  on the main run loop after launch; every init is `@try`-isolated; the dylib
  is injected with **`LC_LOAD_WEAK_DYLIB`**. This matches the community-proven
  load model and is why the mod doesn't crash at launch.
- **No fishhook / no C-level rebinding** in the dylibs: the Spotify v2 crash
  was a fishhook `SecItem` recursion (a segfault `@try` can't catch), and it
  was present in every crashing build. If a future sign-in issue needs the
  keychain access-group rewrite, re-add it ONLY after launch, reading the
  group from `LSBundleProxy` entitlements (never via a rebound SecItem call),
  and guard every resolved original pointer.
- **Plain ObjC-runtime swizzling only** in the dylibs — no Swift, no
  substrate, no third-party tweak binaries. The earlier Swift/Orion attempt
  crashed at launch (constructor too early).
- **One canonical YAML per app**: `patches/<app>/<app>.yaml`. The directory
  is the package name; the version lives in `target.version` inside.
  Redundant variants were deleted — don't recreate them.
- **Extensions are always stripped** (AltStore Team-ID suffix breaks
  extension ids → `IXErrorDomain Code=2`). Watch app too.
- **Hook verification is the safety net**: every hook the dylib relies on is
  declared in the definition's `hooks:` block; `--dry-run` fails when a
  `required` hook can't attach. The version-mismatch warning in the GUI is
  non-blocking *because* of this.
- **The parser under-reports** GPBMessage methods — cross-check suspicious
  selectors with `strings <binary> | grep -cx "<selector>"`.
- **Rebranded away from Eevee/SpotC**: the Spotify set is original work;
  zero external references in the shipped dylib (verified).
- **`bundleSeedID` keychain query must never run through a rebound SecItem** —
  the access group is captured once before any rebinding, or read from
  `LSBundleProxy` entitlements.

## Remaining / pending

- **YouTube G15** (native share) — blocked on protobuf extension-root API
  drift; **G16** (RYD dislikes) — needs a force-inject; **G17** (downloads) —
  the big port, sub-plan in `patches/youtube/ROADMAP.md`.
- **On-device pass** for the latest YouTube/Spotify builds is always the
  acceptance gate; the user reports and the log
  (`com.nandan.ytfreedom` / `com.nandan.spotifymod`) drives the fix.
- Quality gates to keep green: `pytest` (with coverage ≥ 80%), `ruff`,
  `mypy` (strict-ish) — `make test lint type` (see `Makefile`).

## Session memory

This file, the docs, and the knowledge base (ctx_search: sources
`ipa-forge-docs`, `ytfreedom-patchset`, `ipa-forge-project-conventions`)
together persist everything across sessions. If this file is out of date,
update it as part of the work — it is the handoff contract.
