# Spotify 9.1.72 — EeveeSpotify patch set

Target: `com.spotify.client` v9.1.72 (decrypted, thin arm64). Injects
**EeveeSpotify** (the maintained open-source premium-unlock tweak, v6.6.7)
plus its sideload compat shim into the stock IPA via ipa-forge.

## What you get

- **Premium unlock** — free-account restrictions removed (unlimited skips,
  no shuffle-lock, high quality): the bootstrap response is intercepted
  (`SPTDataLoaderService` / `SPTCoreURLSessionDataDelegate`) and rewritten to
  a premium product state.
- **No ads** — HUB JSON ad components filtered (`HUBViewModelBuilderImplementation
  addJSONDictionary:`), DAC/Esperanto ad endpoints blocked, product-state
  re-fetch messages blocked so ads don't come back after hours.
- **Session protection** — Spotify can't detect and log out the non-premium
  account: `SPTAuthSessionImplementation` logout/destroy blocked, OAuth token
  expiry extended, Ably WebSocket revocation messages filtered, DeleteToken/
  customize re-fetch requests cancelled.
- **QOL** — liked-songs row on artist pages, (source permitting) custom lyrics.
- **Sideload compat shim** (`zxPluginsInject`) — keychain access-group rebind,
  CloudKit neutering, app-group container bridging. Without it the resigned
  Spotify breaks on sign-in/data.

## Building the tweak (from source)

```bash
# one-shot: EeveeSwiftProtobuf.framework + EeveeSpotify.dylib + zxPluginsInject.dylib
bash patches/spotify-9.1.72/build.sh
# stages build/EeveeSpotify.dylib, build/zxPluginsInject.dylib,
# build/EeveeSwiftProtobuf.framework, build/EeveeSpotify.bundle
```

Requires theos with Swift support (vendored at `/Users/nandan/dev/ytlite-ipa/theos`)
and the EeveeSpotify source (the DMCA'd upstream is mirrored in several forks;
`build.sh` points at a checkout, see `SOURCES` note below).

## Applying

```bash
forge patch --ipa com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify-9.1.72/spotify-mod.yaml --dry-run   # hooks gate
forge patch --ipa com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify-9.1.72/spotify-mod.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/SpotifyMod_9.1.72_unsigned.ipa
```

The definition strips `PlugIns/` (widget/intents/notifications) and `Watch/`
— AltStore appends the Team ID to the main bundle id at install, which breaks
embedded extension/watch ids (`IXErrorDomain Code=2`), exactly like the
YouTube set. The watch app also can't be provisioned by a free AltStore
account anyway.

## Verified on 9.1.72

All required hooks verified attaching via `forge hooks verify` against the
main binary + SpotifyShared.framework (the SPTDataLoaderService hooks live in
the framework — hook verification now analyzes every Mach-O in the app).
Two Eevee targets are absent in 9.1.72 and self-guarded by the tweak:
`productStateUpdated` (logging only) and the trackRows init method.
`SessionServiceImpl`/`OauthAccessTokenBridge` are Swift classes in another
module — the tweak checks them at init and continues if missing.

## Debugging

EeveeSpotify writes to the system log and a debug file:
`[EeveeSpotify]` in Console.app, or
`log stream --predicate 'eventMessage CONTAINS "EeveeSpotify"'`.
Its init logs which hook targets were found/missing on launch.
