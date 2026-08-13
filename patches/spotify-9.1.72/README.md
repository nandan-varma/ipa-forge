# Spotify 9.1.72 — essential mod (from-scratch, no Eevee)

Target: `com.spotify.client` v9.1.72 (decrypted, thin arm64). Injects a
**from-scratch plain-ObjC hook dylib** (`SpotifyHook.dylib`, built by
`dylib/build.sh`) via ipa-forge. No Swift, no substrate, no third-party tweak
binary — the same load model as the YouTube set.

> Why not EeveeSpotify? The Swift/Orion dylib + SwiftProtobuf framework
> crashes at launch when loaded via `LC_LOAD_DYLIB` (its constructor runs
> before the app's runtime is ready, and the renamed protobuf module still
> fights the copy statically embedded in SpotifyShared). This dylib is the
> essential feature set reimplemented with plain ObjC-runtime swizzling,
> which attaches safely at load like the YouTube dylib.

## Features (essential, in priority order)

1. **Sideload shim** (`SideloadFix.m`) — keychain access-group rebind
   (fishhook on `SecItem*`), never-nil app-group container, CloudKit neuter.
   Required for sign-in to work/persist on a re-signed Spotify.
2. **Session protection** (`SessionProtection.m`) — blocks forced logout
   (`SPTAuthSessionImplementation logout/destroy/logoutWithReason:`,
   `SPTAuthLegacyLoginControllerImplementation destroySession/
   forgetStoredCredentials/invalidate`) and cancels the network calls that
   drive it (DeleteToken, token/revoke, session/purge, signup/public,
   apresolve, bootstrap/customize re-fetches after a 30s startup grace).
3. **Premium unlock** (`PremiumPatch.m` + `PBProto.m`) — intercepts the
   bootstrap and `/v1/customize` responses (via `SPTDataLoaderService` /
   `SPTCoreURLSessionDataDelegate`), rewrites the `UcsResponse` protobuf with
   a generic wire-format editor:
   - account attributes → premium: `catalogue/type/player-license/
     financial-product = premium`, `on-demand/shuffle-eligible/offline/
     high-bitrate/unrestricted = true`, trial/upsell keys removed
   - assigned feature values → ads off (`enable_ads` and every
     `enable_*_ad`/`enable_sponsored_*` = false, ad scopes removed),
     capping removed, lyrics-share forced on
   - canned responses for the DAC (empty = no ad), account-validate,
     trials-facade, premium-marketing, screenconfig, session-invalidation.

## Building

```bash
patches/spotify-9.1.72/dylib/build.sh    # -> build/SpotifyHook.dylib
```

## Applying

```bash
forge patch --ipa com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify-9.1.72/spotify-mod.yaml --dry-run   # hooks gate
forge patch --ipa com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify-9.1.72/spotify-mod.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/SpotifyMod_9.1.72_unsigned.ipa
```

The definition strips `PlugIns/` (widget/intents/notifications) and `Watch/`
— AltStore's Team-ID bundle-id suffix breaks embedded extension/watch ids
(`IXErrorDomain Code=2`), and the watch app can't be provisioned by a free
AltStore account anyway.

## Verified on 9.1.72

Every hook declared in `spotify-mod.yaml` verified attaching via
`forge hooks verify` against the main binary + SpotifyShared.framework (the
`SPTDataLoaderService` hooks live in the framework — forge's multi-binary
analysis covers them). The wire schema (field numbers for
`BootstrapMessage`/`UcsResponse`/`AssignedValue`/`AccountAttribute`) was
derived from the EeveeSpotify generated protobuf models and validated with a
round-trip test binary.

## Debugging

`SpotifyMod` logs to the system log (`com.nandan.spotifymod`):
```bash
log stream --predicate 'subsystem == "com.nandan.spotifymod"'
```
Watch for `hooked -[...]` at launch (attachment), `patched bootstrap/customize`
(premium rewrite firing), and `cancelled <url>` (session-protection blocking).
