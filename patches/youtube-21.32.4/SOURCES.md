# Sources & attribution

Everything in `youtube-21.32.4` was researched from the following projects and
verified independently against the decrypted 21.32.4 binary before porting.
Licenses of the sources apply to the adapted logic; our dylib itself is
GPL-3.0-or-later (matching ipa-forge).

| Source | Where it lives | What we took |
| --- | --- | --- |
| **YouMod** ([Tonwalter888/YouMod](https://github.com/Tonwalter888/YouMod), built for exactly 21.32.4) | cloned to `/tmp/youmod-src` (Files/*.x) + prebuilt `YouMod_21.32.4_v1.3.0.ipa` in `/Users/nandan/dev/YouModIpa` | Primary reference. Ads.x → `AdBlock.m`; Player.x → `PlayerFeatures.m` + `PlayerGestures.m`; Navbar.x/Tabbar.x → `NavbarTabbar.m`; Feed.x/Shorts.x/Sideloading.x (`_ASDisplayView` ids) → `FeedShorts.m`; Others.x → `MiscFeatures.m`; Apperence.x → `Appearance.m`; Settings.x/YouModPerferences.x → `SettingsUI.m`; Sideloading.x → `SignInFix.m` |
| **YTLite** ([dayanch96/YTLite](https://github.com/dayanch96/YTLite), local checkout `/Users/nandan/dev/ytlite-ipa/YTLite`) | `YTLite.x`, `Settings.x`, `YTNativeShare.x`, `Sideloading.x` | Keychain/bundle-identity approach for `SignInFix.m`; G18 extras (red progress bar, related-videos hide, timestamped-link on pause, menu-item removal, sticky navbar, label-fitting, playlist minibar) → `PlayerFeatures.m`/`NavbarTabbar.m`/`MiscFeatures.m`; native-share approach documented in `ROADMAP.md` (G15, API drift) |
| **uYouPlus** ([qnblackcat/uYouPlus](https://github.com/qnblackcat/uYouPlus)) | `Tweaks/uYou/com.miro.uyou_*.deb` (prebuilt, older target) | Cross-check for ad classes absent in 21.32.4 (`YTWatchBreakController`, `YTInstreamAdsCoordinator`, `YTAdsPlayerModule` — all confirmed absent); RYD class map (see G16) |
| **YTSideloadSignInFix** ([therealFoxster](https://github.com/therealFoxster/YTSideloadSignInFix)) | cloned to `/tmp/pi-github-repos/therealFoxster/YTSideloadSignInFix` | `SSORPCService URLFromURL:withAdditionalFragmentParameters:` fingerprint-strip — the actual fix for "Google can't confirm that it's safe" (also [AhmedBafkir's gist](https://gist.github.com/AhmedBafkir/0c16b806b3fb233995aa01b93da44f93)) |
| **BandarHL fixYouTubeLogin** ([gist](https://gist.github.com/BandarHL/492d50de46875f9ac7a056aad084ac10)) | via YTSideloadSignInFix | Keychain access-group fix (SSOKeychainHelper/SSOKeychainCore `accessGroup`) |
| **IAmYouTube** ([PoomSmart](https://github.com/PoomSmart/IAmYouTube)) | via YTLite/YouMod | Bundle-id/name spoofing hooks (`YTVersionUtils`, `GCKBUtils`, `GPCDeviceInfo`, …) |
| **NoYTPremium** ([PoomSmart](https://github.com/PoomSmart/NoYTPremium)) | via YouMod Ads.x / YTLite.x | Premium-promo blockers (`YTCommerceEventGroupHandler`, `YTPromoThrottleController`, …) → `MiscFeatures.m` |
| **YTClassicVideoQuality** ([PoomSmart](https://github.com/PoomSmart/YTClassicVideoQuality)) | via YouMod Player.x | Old quality picker → `PlayerFeatures.m` (G4) |
| **YouSpeed / YTLitePlus gestures** | via YouMod Player.x | Extra speeds + edge gestures → `PlayerFeatures.m`/`PlayerGestures.m` (G5/G6) |
| **YouTube Native Share** ([jkhsjdhjs](https://github.com/jkhsjdhjs/youtube-native-share)) | via YTLite `YTNativeShare.x` | G15 — documented; protobuf extension-root + unknown-field APIs changed in 21.32.4, port deferred |

## Verification tooling (built into forge)

- `forge hooks extract --ipa X --class C` / `--search RE` — walk
  `__objc_classlist`/`__objc_methlist`/`__objc_selrefs` (chained-fixup aware,
  lipo-thinned) of the arm64 slice: class existence + per-class method lists.
- `forge hooks verify --ipa X --patches Y` — verify the definition's `hooks:`
  block (159 declared in `youtube-mod.yaml`); also runs on `--dry-run`.
- `forge hooks audit --ipa X --dir dylib/` — scan tweak sources for hook calls
  and check each. The parser under-reports methods on GPBMessage subclasses;
  every flagged selector was re-checked with `strings` on the binary — all
  confirmed present except the items listed in `ROADMAP.md` ("verified absent").
- `tools/generate_hooks_manifest.py` — regenerates the `hooks:` block from the
  dylib sources (marks 12 load-bearing hooks `required: true`).
