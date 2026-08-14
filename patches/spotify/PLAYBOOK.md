# Playbook — Spotify 9.1.72 (SpotifyMod)

The Spotify-specific runbook. The generic procedure lives in
[`ipa-forge/docs/adding-an-app.md`](../../docs/adding-an-app.md); this file
is the concrete application.

## Where everything lives

| Path | What it is |
| --- | --- |
| `spotify.yaml` | The definition (strip + stage + weak link + `hooks:`) |
| `dylib/` | SpotifyHook sources: `SpotifyHook.h/.m`, `SpotifyFeatures.m` (feature catalog — single source of truth), `SideloadFix.m`, `SessionProtection.m`, `PremiumPatch.m` + `PBProto.m` (wire-format editor), `AdBlock.m`, `SettingsUI.m` |
| `dylib-test/` | Minimal do-nothing dylib (`spotify-test.yaml`) for isolating launch crashes |
| `/Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa` | Base IPA (decrypted) |

## Build & deliver

```bash
cd /Users/nandan/dev/ipa-forge && source .venv/bin/activate
patches/spotify/dylib/build.sh                # -> build/SpotifyHook.dylib
forge patch --ipa /Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify/spotify.yaml \
  --output /tmp/x.ipa --dry-run                      # hooks gate (15/16 attach)
forge patch --ipa /Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify/spotify.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/SpotifyMod_v0.0.1.ipa
```

Bump `SPOTIFYMOD_VERSION` in `dylib/SpotifyHook.h` and the IPA file name on
every pass (v0.0.1, v0.0.2, ...); the About section shows the same version.
Update `TESTING.md` per pass.

## Features (all toggleable in Settings → SpotifyMod, default ON)

Settings are organized by the catalog in `dylib/SpotifyFeatures.m`:

- **Essentials** — Premium unlock, Ad blocker, Session protection.
- **Interface** — opt-in: Hide Premium & Create tabs (one switch, both
  tabs together).
- **Advanced** — App-group fix; Ad blocking strength (Standard / Aggressive;
  Aggressive adds free-tier re-fetch suppression after a 30s startup grace).
- **Future** — disabled roadmap rows (Downloads unlock, Audio quality selector,
  Startup tab, Settings import/export).
- **About** — version, reset-all.

Every change needs a relaunch (a “Restart to apply” pill confirms).

## The load model (why it doesn't crash)

Plain ObjC-runtime swizzling only. The constructor is inert — hooks install
on the main run loop after launch, `@try`-isolated per feature, and the
dylib is `LC_LOAD_WEAK_DYLIB` (a load failure degrades instead of aborting).
This matches the community-proven load model; the earlier Swift/Orion attempt
crashed at launch (constructor too early) and the first ObjC port crashed on
a fishhook SecItem recursion (a segfault `@try` can't catch) — both are
documented in git history and `README.md`.

## Debugging

`com.nandan.spotifymod` os_log subsystem: watch for `hooked -[…]` at
install, `<feature> ready|disabled`, `patched bootstrap/customize`,
`cancelled <url>`.

## Porting to a newer Spotify

1. New decrypted IPA → bump `target.version` in `spotify.yaml`.
2. `forge patch --dry-run` → the hooks report shows what broke.
3. `forge hooks diff --old 9.1.72.ipa --new <new>.ipa --patches spotify.yaml`
   — exact regressions.
4. Fix the dylib sources, rebuild, regenerate the hooks block
   (`forge hooks manifest --dir dylib/ --required hooks-required.txt`) plus
   the hand-declared helper/loop hooks.
5. Rebuild + deliver (see [`adding-a-feature.md`](../../docs/adding-a-feature.md)
   for per-feature conventions).
