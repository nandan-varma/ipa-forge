# Spotify 9.1.72 — SpotifyMod (from-scratch)

> **New here?** Read [`PLAYBOOK.md`](PLAYBOOK.md) for the runbook, then the
> generic guides: [`adding-an-app.md`](../../docs/adding-an-app.md) and
> [`adding-a-feature.md`](../../docs/adding-a-feature.md).

Target: `com.spotify.client` v9.1.72 (decrypted, thin arm64). Injects a
**from-scratch plain-ObjC hook dylib** (`SpotifyHook.dylib`, built by
`dylib/build.sh`) via ipa-forge. No Swift, no substrate, no third-party tweak
binary — the same load model as the YouTube set.

All hooks are plain ObjC-runtime swizzling installed after launch (the
dylib's constructor is inert) and loaded weakly — the load model proven by
community Spotify mods. No Swift, no substrate, no third-party tweak
binaries.

## Features (essential, in priority order)

> **v3 crash fix (deduced):** the v2 launch crash was infinite recursion in the
> keychain shim — `spotAccessGroupID()` called `SecItemCopyMatching`, which had
> already been rebound to the wrapper, so the wrapper called itself until the
> stack overflowed at load. The access group is now captured **before**
> rebinding and wrappers read the cached value. Every feature init is also
> isolated in `@try` — a failure in one logs (`com.nandan.spotifymod`) and
> degrades instead of crashing.

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
     trials-facade, premium-marketing, screenconfig, session-invalidation,
     and the premium-plan endpoints (plan row, badge, overview).

## Building

```bash
patches/spotify/dylib/build.sh    # -> build/SpotifyHook.dylib
```

## Applying

```bash
forge patch --ipa com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify/spotify.yaml --dry-run   # hooks gate
forge patch --ipa com.spotify.client_9.1.72_und3fined.ipa \
  --patches patches/spotify/spotify.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/SpotifyMod_9.1.72_unsigned.ipa
```

The definition strips `PlugIns/` (widget/intents/notifications) and `Watch/`
— AltStore's Team-ID bundle-id suffix breaks embedded extension/watch ids
(`IXErrorDomain Code=2`), and the watch app can't be provisioned by a free
AltStore account anyway.

## Verified on 9.1.72

Every hook declared in `spotify.yaml` verified attaching via
`forge hooks verify` against the main binary + SpotifyShared.framework (the
`SPTDataLoaderService` hooks live in the framework — forge's multi-binary
analysis covers them). The wire schema (field numbers for
`BootstrapMessage`/`UcsResponse`/`AssignedValue`/`AccountAttribute` and the
premium-plan messages) was derived from analyzing the responses and
validated with round-trip test binaries.

## Settings

Settings → **SpotifyMod** (an inline row at the top of Spotify's settings
list) opens a settings screen with four sections, driven entirely by the
feature catalog in `dylib/SpotifyFeatures.m` (the single source of truth):

- **Essentials** — Premium unlock, Ad blocker, Session protection (all ON).
- **Interface** — opt-in bottom-bar tweak (OFF by default): Hide Premium &
  Create tabs (one switch, both tabs together).
- **Advanced** — rarely-changed: App-group fix + **Ad blocking strength**
  dropdown (Standard / Aggressive). Aggressive (default) also suppresses
  free-tier re-fetch after a 30s startup grace.
- **Future** — not-yet-implemented features rendered as disabled rows
  (Downloads unlock, Audio quality selector, Startup tab, Settings
  import/export).
- **About** — mod version, reset-all, relaunch note.

Every change shows a “Restart to apply” pill — toggles are read when hooks
install, so changes apply on relaunch. Not everything is a switch: strength
and future dropdowns use a checkmark picker.

## Testing

See [`TESTING.md`](TESTING.md) — the per-version device test sheet.

## Debugging

`SpotifyMod` logs to the system log (`com.nandan.spotifymod`):

```bash
log stream --predicate 'subsystem == "com.nandan.spotifymod"'
```

Watch for `hooked -[...]` at launch (attachment), `patched bootstrap/customize`
(premium rewrite firing), and `cancelled <url>` (session-protection blocking).
