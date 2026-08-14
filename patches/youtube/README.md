# YouTube 21.32.4 — patch set

Target: `com.google.ios.youtube` v21.32.4 (arm64, thin binaries — no `arch:`
needed). All definitions are dry-run validated against the real decrypted IPA
with `forge patch --dry-run`.

> **New here?** Read [`PLAYBOOK.md`](./PLAYBOOK.md) first — it is the complete
> runbook from a fresh IPA to a working mod, including how to port this set
> to a future YouTube version.

## What's here

| File | Effect | Status |
| --- | --- | --- |
| `youtube.yaml` | **The mod** (single canonical definition): adblock + sign-in fix + settings + all feature toggles via `libYTHook.dylib`, **plus extension stripping** (required for AltStore install) | dry-run OK |

> One definition per app — the version lives in `target.version` inside the
> YAML (the directory is just the app name). Discoverable by the GUI and
> `forge hooks` via `ipa_forge.patches`.

## Why extensions are stripped (and what you lose)

AltStore appends your Team ID to the main bundle id at install
(`com.google.ios.youtube` → `com.google.ios.youtube.<teamID>`). iOS requires every
embedded app extension's id to start with the parent id, but the stock extensions
keep `com.google.ios.youtube.<Name>` — so install fails with
`IXErrorDomain Code=2 Failed to set app extension placeholders`. The free-account
App-ID cap (~3) is also blown by 6 extension ids. Both the adblock set and the
full set remove `Extensions/` and `PlugIns/` (dayanch96's own releases strip
them too).

Lost: home-screen widget, Share-to-YouTube, Siri intents, and push-notification
extensions (push is unavailable on free sideload accounts anyway). Core playback,
ads removal, downloads, and all patched features are unaffected — the main
Info.plist references none of them.

## Feature overview (`youtube.yaml`)

The dylib (see `SOURCES.md` for attribution) implements, all behind the in-app
**Settings → YTFreedom** section:

- **Ads**: player pre/mid/post-roll, feed cards, Shorts ads (AdBlock.m)
- **Sideload sign-in**: OAuth safety-page fix + SSO keychain persistence (SignInFix.m)
- **Player**: bar toggles, overlay/UI, playback behavior, old quality picker, extra speeds,
  edge gestures, background playback, Shorts PiP (PlayerFeatures.m, PlayerGestures.m)
- **Navbar / Tab bar**: logo, buttons, sticky navbar, tabs, default tab (NavbarTabbar.m)
- **Feed / Shorts**: subbar, shelves, search history, buttons, quality, seekbar (FeedShorts.m)
- **Misc**: upgrade dialogs, snackbar, startup animations, menu-item removal, silent vote,
  promo blockers (MiscFeatures.m)
- **Appearance**: OLED theme + keyboard (Appearance.m)
- **Preferences**: import/export/reset, cache management (SettingsUI.m)

Progress and per-goal verification live in `ROADMAP.md`.

### Ad removal detail (AdBlock.m)

Covers every layer of the modern ads pipeline:

- **Data** — `YTPlayerResponse` gets new `playerAdsArray`/`adSlotsArray`
  (empty arrays, queried by the pipeline); `enableSkippableAd -> YES`.
- **Playback** — `YTLocalPlaybackController createAdsPlaybackCoordinator -> nil`;
  `MDXSessionImpl adPlaying:` no-op; adapter backstops
  (`YTAdBreakResponseReceivedOpportunityAdapterV2` / `YTAdBreakRendererAdapter`).
- **Request** — `YTAdsInnerTubeContextDecorator` and
  `YTAccountScopedAdsInnerTubeContextDecorator decorateContext:` call through
  with nil; `YTAdShieldUtils spamSignalsDictionary*` empty.
- **Feed** — `YTInnerTubeCollectionViewController` filters sections by
  `YTIElementRenderer` ad detection; `_ASDisplayView` removes
  `eml.expandable_metadata.vpp` / hides `eml.ad_layout.*`; product-in-video
  overlay dropped; Shorts ad reels filtered via `isAdVideo`.

Verified absent in 21.32.4 (superseded/renamed): `YTIPlayerResponse
isMonetized:`, `YTDataUtils spamSignalsDictionary`, `YTISectionListViewController`,
`YTWatchBreakController`, `YTInstreamAdsCoordinator`, `YTAdsPlayerModule`,
`YTReelInfinitePlaybackDataSource`.

## Sideload sign-in fix (same dylib)

AltStore installs the app under a changed bundle id
(`com.google.ios.youtube` → `com.google.ios.youtube.<teamID>`), which breaks
Google's SSO/GAIA flow in two ways — both fixed by `libYTHook.dylib`:

1. **"You can't sign in to this app because Google can't confirm that it's
   safe."** The SSO RPC layer appends device-fingerprint query params
   (`system_version`, `app_version`, `kdlc`, `kss`, `lib_ver`,
   `device_model`) to the sign-in URL; Google's risk engine uses them to
   detect the modified build and refuses. `SSORPCService
   URLFromURL:withAdditionalFragmentParameters:` is hooked to strip them
   (AhmedBafkir gist / therealFoxster's YTSideloadSignInFix).
2. **SSO token persistence.** Google's keychain classes ask for access
   groups that no longer exist under the re-signed bundle; every entry
   point (`SSOKeychainHelper`/`SSOKeychainCore`/`SSOKeychain`
   `accessGroup`/`sharedAccessGroup`, `SSOFolsomKeychainUtils
   sharedAccessGroup`, `GULKeychainStorage`, `GNPEncryptionConfiguration`,
   `FIRInstallationsStore`, `CHMConfiguration`) is routed to the real
   group (derived from `bundleSeedID`), and app-group container lookups
   redirect to `Documents/AppGroup`.

Supporting identity spoofing so Google frameworks see the stock app
(IAmYouTube set: `YTVersionUtils`, `GCKBUtils`, `GPCDeviceInfo`, `OGLBundle`,
`GVROverlayView`, `SSOClientLogin`, `SSOConfiguration`, `YTHotConfig`;
`NSBundle` main-bundle spoof; `GULAppEnvironmentUtil isFromAppStore`;
`APMAEU isFAS`). Hook set is the union of YouMod's `Sideloading.x` (adapted
from YTLite + uYouEnhanced) and YTSideloadSignInFix; every class and
selector was verified present in the 21.32.4 binary with
`forge hooks verify --ipa <decrypted.ipa> --patches youtube.yaml`
(only `OGLPhenotypeFlagServiceImpl` is absent and is skipped).

### Build the dylib

```bash
patches/youtube/dylib/build.sh
```

(arm64 iOS dylib, plain ObjC-runtime swizzling in an `__attribute__((constructor))` —
no substrate/ellekit dependency; loads via a plain `LC_LOAD_DYLIB`.)

### Hook targets — how they were found (reproducible)

```bash
# dump a class's methods (classes, superclass, inst/class selectors)
forge hooks extract --ipa youtube-21.32.4-decrypted.ipa --class YTLocalPlaybackController
# search classes by name
forge hooks extract --ipa youtube-21.32.4-decrypted.ipa --search "AdBreak|ControlFlow"
# verify every hook the mod declares against the binary (also runs in --dry-run)
forge hooks verify --ipa youtube-21.32.4-decrypted.ipa --patches youtube.yaml
# scan the dylib sources for hook calls and check each
forge hooks audit --ipa youtube-21.32.4-decrypted.ipa --dir dylib/
```

The engine walks `__objc_classlist`/`__objc_methlist`/`__objc_selrefs` of the
arm64 slice (chained-fixup aware; fat binaries are thinned with lipo). See
`ipa-forge`'s `docs/patch-reference.md` → "The `hooks` block".

## Try it (dry run)

```bash
forge patch --ipa /path/to/youtube-21.32.4-decrypted.ipa \
  --patches patches/youtube/youtube.yaml \
  --output /tmp/youtube-patched.ipa --dry-run
```

## Real run (signing)

`forge patch` requires `--identity` (Keychain codesigning identity) and
`--profile` (a `.mobileprovision` authorizing `com.google.ios.youtube`). The
app has six extensions (AppMigration, Intents, NotificationContent,
NotificationService, Share, WidgetKit) — supply one profile per extension
bundle id or a wildcard profile. AltStore Classic performs its own signing at
install time regardless.
