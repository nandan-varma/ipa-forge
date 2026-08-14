# IGMod — Instagram 442.0.0 mod

A from-scratch, plain-ObjC hook dylib for the decrypted Instagram
`com.burbn.instagram` 442.0.0 IPA. No Swift, no substrate, no third-party
tweak binary — `IGModHook.dylib` is built from `dylib/*.m` and loaded via a
weak dylib load command, exactly like the YouTube/Spotify sets in this repo.

## Features

| Area | Feature | Default | How it works (hook-verified in 442.0.0) |
| --- | --- | --- | --- |
| Feed | Hide ads | ON | Filters `IGAdItem` / `IGMedia.isMediaAd` out of `IGMainFeedListAdapterDataSource -objectsForListAdapter:`, and returns nil from every `*AdsResponseParser -parsedObjectFromResponse:` (feed/story/reels/explore/search/profile) |
| Feed | Hide stories tray | OFF | Drops `IGStoryDataController` from the feed list |
| Feed | No suggested posts | OFF | Drops `IGMedia.explorePostInFeed == YES` |
| Feed | No suggested reels | OFF | Drops `IGFeedScrollableClipsModel` carousels |
| Feed | No suggested accounts | OFF | Drops `IGHScrollAYMFModel` units |
| Privacy | No story seen receipt | OFF | `IGStorySeenStateUploader` init + `networker` return nil |
| Privacy | No typing indicator | OFF | `IGDirectTypingStatusService -updateOutgoingStatusIsActive:…` no-ops |
| Privacy | No screenshot alerts | ON | `IGViewController -screenshotObserver` → nil, `IGScreenshotObserver`/`IGDirectVisualMessageScreenshotSafetyLogger` init → nil, screenshot-observer delegate methods no-op on the story/DM viewers |
| Media | Save feed posts | ON | Long-press any feed media cell → share/save (photos + videos via `IGFeedItemMediaCell -post`) |
| Media | Save stories | ON | Long-press story photo/video → share/save (`IGStoryPhotoView/IGStoryVideoView -item`) |
| Media | Save profile pictures | ON | Long-press avatar → share/save (`IGUser -derivedProfilePicURL`) |
| Media | Copy captions | ON | Long-press caption → clipboard (`IGCoreTextView.styledString.attributedString`) |
| Misc | Disable safe mode | OFF | `IGSafeModeChecker` init → nil, `crashCount` → 0 |
| Misc | Settings | — | Long-press home tab or 4-finger hold anywhere |

Saving shares through the system share sheet (downloads to a temp file
first so "Save Image"/"Save Video" work) — no photo-library permission
needed.

## Build

```bash
patches/instagram/dylib/build.sh   # requires macOS + Xcode CLT (iPhone SDK)
```

Produces `build/IGModHook.dylib` (arm64, `@rpath/IGModHook.dylib`).

## Apply

```bash
forge patch --ipa <instagram-442.0.0.ipa> --patches patches/instagram/instagram.yaml \
  --output IGMod_v0.0.1.ipa            # add --dry-run to only verify
```

The definition also strips `Extensions/` + `PlugIns/` — required because
AltStore re-signs the main bundle id with a Team-ID suffix, breaking the
embedded extension ids (IXErrorDomain Code=2). This mirrors the YouTube set.

## Verified against

`forge hooks verify --ipa <442.0.0.ipa> --patches patches/instagram/instagram.yaml`
→ **32/32 hooks attach; 0 required hook(s) failing.** Dry-run gate: 4
operations would apply. The full hook report and the verification script
used during development are documented in `PLAYBOOK.md`.

## Porting / drift

Instagram changes its class surface every couple of releases. The dylib
never links against Instagram classes — every target is resolved at runtime
(`NSClassFromString` + `respondsToSelector`) and every hook is `@try`-
isolated, so a drifted class degrades that one feature instead of crashing
the app. `forge hooks diff --old … --new …` is the porting tool; the
SCInsta-derived hook surface and what changed between 418.x and 442.0.0 is
in `SOURCES.md`.
