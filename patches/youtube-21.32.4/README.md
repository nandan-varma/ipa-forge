# YouTube 21.32.4 — patch set

Target: `com.google.ios.youtube` v21.32.4 (arm64, thin binaries — no `arch:`
needed). All definitions are dry-run validated against the real decrypted IPA
with `forge patch --dry-run`.

## What's here

| File | Effect | Status |
| --- | --- | --- |
| `youtube-21.32.4.yaml` | Safe cosmetic: display name + signed-out 90s preview video swap | dry-run OK |
| `youtube-adblock.yaml` | **Player ad removal** via `dylib_inject` of `libYTHook.dylib` | dry-run OK |
| `youtube-21.32.4-full.yaml` | Everything above in one file (one-command patching) | dry-run OK |

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
