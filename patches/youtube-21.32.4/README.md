# YouTube 21.32.4 — patch set

Target: `com.google.ios.youtube` v21.32.4 (arm64, thin binaries — no `arch:`
needed). All definitions are dry-run validated against the real decrypted IPA
with `forge patch --dry-run`.

## What's here

| File | Effect | Status |
| --- | --- | --- |
| `youtube-21.32.4.yaml` | Safe cosmetic: display name + signed-out 90s preview video swap | dry-run OK |
| `youtube-adblock.yaml` | **Player ad removal + sideload sign-in fix** via `libYTHook.dylib`, **plus extension stripping** (required for AltStore install) | dry-run OK |
| `youtube-21.32.4-full.yaml` | Everything above **plus extension stripping** (required for AltStore install) | dry-run OK |

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

## Player ad removal (`youtube-adblock.yaml`)

YouTube 21.32.4 re-architected its ad pipeline around the "ads control flow"
classes; every classic hook point used by public tweaks (`YTIPlayerResponse
isMonetized:`, `YTDataUtils spamSignalsDictionary:`, `YTAdsInnerTubeContextDecorator
decorateContext`, ...) is gone from this binary (verified by static analysis).
The from-scratch dylib targets two classes that *are* present:

- `YTAdBreakResponseReceivedOpportunityAdapterV2
  didReceiveAdBreakResponse:fromAdBreakSlot:` — modern entry point where an
  ad-break response is turned into scheduled slots. Hook drops the response.
- `YTAdBreakRendererAdapter createAds` — classic renderer path. Hook returns
  an empty array.

Both are conservative: the ad-break timeline still resolves (empty), so
content playback is not left waiting on a missing callback.

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
selector was verified present in the 21.32.4 binary with `yt_inventory.py`
(only `OGLPhenotypeFlagServiceImpl` is absent and is skipped).

### Build the dylib

```bash
patches/youtube-21.32.4/dylib/build.sh
```

(arm64 iOS dylib, plain ObjC-runtime swizzling in an `__attribute__((constructor))` —
no substrate/ellekit dependency; loads via a plain `LC_LOAD_DYLIB`.)

### Hook targets — how they were found (reproducible)

```bash
# requires the decrypted IPA extracted at /tmp/verify/Payload/YouTube.app/YouTube
python3 patches/youtube-21.32.4/tools/yt_inventory.py inventory "ControlFlow|InstreamAd"
python3 patches/youtube-21.32.4/tools/yt_inventory.py class YTAdBreakResponseReceivedOpportunityAdapterV2
```

The tool walks `__objc_classlist`/`__objc_methlist` of the arm64 slice,
decoding chained fixups and the two-level selref method-name indirection
(entry-relative offset → `__objc_selrefs` slot → selector string). Adjust
`BIN` at the top of the tool to point at your extracted binary.

## Try it (dry run)

```bash
forge patch --ipa /path/to/youtube-21.32.4-decrypted.ipa \
  --patches patches/youtube-21.32.4/youtube-21.32.4-full.yaml \
  --output /tmp/youtube-patched.ipa --dry-run
```

## Real run (signing)

`forge patch` requires `--identity` (Keychain codesigning identity) and
`--profile` (a `.mobileprovision` authorizing `com.google.ios.youtube`). The
app has six extensions (AppMigration, Intents, NotificationContent,
NotificationService, Share, WidgetKit) — supply one profile per extension
bundle id or a wildcard profile. AltStore Classic performs its own signing at
install time regardless.
