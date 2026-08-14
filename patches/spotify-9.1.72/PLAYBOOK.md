# Playbook — Spotify 9.1.72 (SpotifyMod)

The Spotify-specific runbook. The generic procedure lives in
[`ipa-forge/docs/adding-an-app.md`](../../docs/adding-an-app.md); this file
is the concrete application.

## Where everything lives

| Path | What it is |
| --- | --- |
| `spotify-mod.yaml` | The definition (strip + stage + weak link + `hooks:`) |
| `dylib/` | SpotifyHook sources: `SpotifyHook.h/.m`, `SideloadFix.m`, `SessionProtection.m`, `PremiumPatch.m` + `PBProto.m` (wire-format editor), `AdBlock.m`, `Settings.m` |
| `dylib-test/` | Minimal do-nothing dylib (`spotify-test.yaml`) for isolating launch crashes |
| `/Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa` | Base IPA (decrypted) |

## Build & deliver

```bash
cd /Users/nandan/dev/ipa-forge && source .venv/bin/activate
patches/spotify-9.1.72/dylib/build.sh                # -> build/SpotifyHook.dylib
forge patch --ipa /Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify-9.1.72/spotify-mod.yaml \
  --output /tmp/x.ipa --dry-run                      # hooks gate (15/16 attach)
forge patch --ipa /Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify-9.1.72/spotify-mod.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/SpotifyMod_9.1.72_unsigned.ipa
```

## Features (all toggleable in Settings → SpotifyMod, default ON)

- **Premium unlock** — bootstrap + `/v1/customize` responses rewritten
  (account attributes → premium, assigned values → ads off + capping
  removed, lyrics share on); premium-plan endpoints answered with premium
  protobufs.
- **Ad blocker** — HUB JSON ad components filtered + full ad-endpoint
  network blocking (DAC, Esperanto, /ads/*, sponsored/promoted paths,
  doubleclick/aet hosts).
- **Session protection** — forced logout blocked
  (`SPTAuthSessionImplementation`, `SPTAuthLegacyLoginControllerImplementation`),
  logout/ad-driver requests cancelled.
- **App-group fix** — container fallback for the re-signed install.

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

1. New decrypted IPA → bump `target.version` in `spotify-mod.yaml`.
2. `forge patch --dry-run` → the hooks report shows what broke.
3. `forge hooks diff --old 9.1.72.ipa --new <new>.ipa --patches spotify-mod.yaml`
   — exact regressions.
4. Fix the dylib sources, rebuild, regenerate the hooks block
   (`forge hooks manifest --dir dylib/ --required hooks-required.txt`) plus
   the hand-declared helper/loop hooks.
5. Rebuild + deliver (see [`adding-a-feature.md`](../../docs/adding-a-feature.md)
   for per-feature conventions).
