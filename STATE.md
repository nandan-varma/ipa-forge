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

A generic, data-driven iOS IPA patcher (`forge`, Python) plus three concrete
patch sets that produce working modded IPAs for AltStore sideloading:
**YouTube 21.32.4**, **Spotify 9.1.72**, and **Instagram 442.0.0**. The
patcher applies YAML patch definitions (resources, binary patches, plist
edits, dylib injection), verifies every hook a dylib relies on against the
actual binary, and emits an unsigned IPA that AltStore signs at install.

## Current state

| App | Version | Patch set | Status |
| --- | --- | --- | --- |
| YouTube | 21.32.4 | `patches/youtube/youtube.yaml` | ✅ adblock + sign-in + ~75 settings toggles; sideloaded & tested. Plus three new beta features (default OFF, **not yet on-device tested**): native share sheet, Return YouTube Dislikes, custom downloads — see `patches/youtube/ROADMAP.md` G15/G16/G17 |
| Spotify | 9.1.72 | `patches/spotify/spotify.yaml` | ✅ premium unlock + adblock + session protection + settings; sideloaded & tested |
| Instagram | 442.0.0 | `patches/instagram/instagram.yaml` | ✅ v0.3.0 — adblock + story privacy + media save (feed/stories/reels/avatars) + settings; hook-verified (43/43), **not yet reported on-device tested** in this file |

**Delivery location has moved twice across sessions — this line is the
current source of truth, not the docs that reference it.** Current build
inputs (decrypted, undefined source IPAs) live in `/Users/nandan/dev/ipa/`;
rebuilt unsigned mods are delivered to `/Users/nandan/dev/ipa/mod/`
(`com.google.ios.youtube_21.32.4_mod.ipa`, `com.spotify.client_9.1.72_mod.ipa`,
`com.burbn.instagram_442.0.0_mod.ipa`). Earlier sessions used
`/Users/nandan/dev/ytlite-ipa/` (`YouTubeMod_21.32.4_unsigned.ipa`,
`SpotifyMod_9.1.72_unsigned.ipa`) — that directory may still exist but is
not where the current builds are.

## Where things live

| Path | What |
| --- | --- |
| `ipa_forge/` | The patcher: `pipeline.py` (17-stage), `patch/` (operations), `signing/`, `machO/objc.py` (shared ObjC/Mach-O analysis engine), `hooks/` (hook verification + source scanner, built on `machO/objc.py`), `analysis/` (general-purpose IPA reverse engineering: class-dump, strings, symbols, security, diff — also built on `machO/objc.py`; see `docs/reverse-engineering.md`), `patches.py` (patch-set registry), `cli/` (`forge`, `forge hooks`, `forge analysis`), `gui/` (novice patch UI + read-only `/analysis` RE viewer), `bundle/`, `validators/` |
| `patches/youtube/`, `patches/spotify/`, `patches/instagram/` | The patch sets: `<app>.yaml` (single canonical definition, version inside), `dylib/` (hook sources + build.sh), `PLAYBOOK.md`/`README.md`/`SOURCES.md` |
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

- **YouTube G15/G16/G17 are implemented** (native share, RYD dislikes,
  custom downloads — see `patches/youtube/ROADMAP.md`), all default-OFF
  beta features, all hook-verified (`forge hooks verify`/`audit`, 0 required
  failures) but **none confirmed on-device** — none of the three had a
  usable local reference source, so they were built via direct RE against
  the 21.32.4 binary. G17 in particular carries real execution-risk
  unknowns (does the model-graph walk actually find formats at runtime?
  does the AVFoundation mux produce a playable file?) that only a device
  pass can answer. Test these before relying on them.
- **On-device pass** for the latest YouTube/Spotify/Instagram builds is
  always the acceptance gate; the user reports and the log
  (`com.nandan.ytfreedom` / `com.nandan.spotifymod` / `com.nandan.igmod`)
  drives the fix.
- A static audit pass (`forge hooks verify`/`audit` across all three patch
  sets against their target IPAs in `/Users/nandan/dev/ipa/`) found real
  undeclared-hook gaps in two of the three sets — both fixed:
  - **Spotify**: 3 hooks (Settings UI injection, Encore TabsView layout)
    existed in `dylib/*.m` but weren't in `spotify.yaml`'s `hooks:` block.
  - **Instagram**: 3 hooks (4-finger-hold settings re-attach on `UIWindow
    -addSubview:`, shake-to-open settings on `IGRootViewController
    -motionEnded:withEvent:`, reels/clips skeleton-skip on
    `UIActivityIndicatorView -startAnimating`) existed in `dylib/*.m` but
    weren't in `instagram.yaml`'s `hooks:` block. Now 43/43.
  - YouTube had no gaps (216/216 already in sync).
  In every case `--dry-run` was passing anyway, silently, because the gap
  is invisible to it by construction — the whole point of the fix below.
- **`forge hooks audit` gained a `--patches` flag** (this is how both gaps
  above were found — manually for Spotify, then with the new flag for
  Instagram, which is why Instagram wasn't caught the first pass): cross-
  checks the source scan against the definition's `hooks:` block and exits
  1 if any source-called hook isn't declared. Use it as a standard part of
  the verify loop from now on, not just `--dry-run`.
- Quality gates to keep green: `pytest` (with coverage ≥ 80%), `ruff`,
  `mypy` (strict-ish) — `make test lint type` (see `Makefile`).

## Session memory

This file, the docs, and the knowledge base (ctx_search: sources
`ipa-forge-docs`, `ytfreedom-patchset`, `ipa-forge-project-conventions`)
together persist everything across sessions. If this file is out of date,
update it as part of the work — it is the handoff contract.
