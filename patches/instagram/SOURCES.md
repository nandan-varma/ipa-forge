# SOURCES — Instagram 442.0.0 (IGMod)

Research lineage and attribution for the IGMod patch set.

## Where the feature/hook surface came from

- **BHInstagram** ([BandarHL/BHInstagram](https://github.com/BandarHL/BHInstagram))
  — the original open-source Instagram tweak; retired.
- **SCInsta** ([SoCuul/SCInsta](https://github.com/SoCuul/SCInsta), MIT) —
  the maintained open-source fork of BHInstagram; the feature list and the
  initial hook map (feed ad filtering, story-seen uploader, typing status,
  screenshot-observer delegate, `IGMedia`/`IGVideo`/`IGPhoto` media download
  plumbing, long-press copy, `IGSafeModeChecker`) were derived from its
  Logos sources (`src/Tweak.x`, `src/Features/*`). SCInsta is tested against
  Instagram 418.2.0.
- **RyukGram** ([faroukbmiled/RyukGram](https://github.com/faroukbmiled/RyukGram))
  — currently the most feature-rich maintained tweak, but **closed source**
  as of v1.3.x; used only as a feature-catalog reference (what users expect:
  downloads, no-ads, story/DM privacy, profile analyzer). No code was taken
  from it.

## Version drift: SCInsta (418.2.0) → our binary (442.0.0)

Every candidate hook from the SCInsta surface was verified against the
442.0.0 main executable before porting. Verified missing (class renamed or
removed — hook dropped):

- `IGSundialFeedDataSource`, `IGContextualFeedViewController`,
  `IGVideoFeedViewController`, `IGChainingFeedViewController`,
  `IGExploreListKitDataSource` (reels/explore list adapters) — reels/explore
  ad removal is now covered by the `*AdsResponseParser` nil hooks instead.
- `IGMainStoryTrayDataSource` (story-tray hide) — replaced by filtering
  `IGStoryDataController` out of the feed list.
- `IGFeedPhotoView`, `IGModernFeedVideoCell`, `IGPageMediaView` — feed media
  download now hooks the common superclass `IGFeedItemMediaCell -post`.
- `IGFeedItem` — the feed-list ad check now uses `IGAdItem` /
  `IGMedia.isMediaAd` (both verified in 442.0.0).
- `IGStoryModernVideoView` — `IGStoryVideoView` exposes `-item` directly now.
- `IGCoreTextView -text` — the property is gone; the caption lives in
  `-styledString` (`IGStyledString -attributedString`).
- `IGUser -profilePictureURL/-profilePictureUrl` — replaced by
  `-derivedProfilePicURL` (verified).
- `IGDirectRealtimeIrisThreadDelta +removeItemWithMessageId:` /
  `IGDirectMessageUpdate +removeMessageWithMessageId:` (keep-deleted-messages)
  — selectors gone in 442.0.0; feature dropped, not ported.
- `IGDirectVisualMessageViewerSession/ReplayService/ReportService` — the
  screenshot-observer delegate surface moved; the 442.0.0 equivalents
  (`IGViewController -screenshotObserver`, `IGScreenshotObserver`,
  `IGDirectVisualMessageScreenshotSafetyLogger`, and the delegate methods on
  `IGStoryViewerViewController` / `IGDirectVisualMessageViewerController` /
  `IGDirectAggregatedMediaViewerViewController`) are all hook-verified.
- `_TtC14IGFeedPlayback22IGFeedPlaybackStrategy` (feed autoplay) — not found
  in 442.0.0; feature dropped.

## Implementation

All dylib code is original work written for this repo, following the
plain-ObjC conventions of the YouTube/Spotify sets (`class_replaceMethod`
swizzling, inert constructor, `@try`-isolated feature init, runtime class
resolution). The download/save UX mirrors SCInsta's long-press pattern; the
URL extraction helpers reimplement SCInsta's `getPhotoUrl` /
`getVideoUrlForMedia` logic against the 442.0.0 accessors.

## Research artifacts

- Decrypted base: `/Users/nandan/Downloads/com.burbn.instagram_442.0.0_und3fined.ipa`
- Verification during development: `/tmp/check_ig_hooks.py` (checked every
  SCInsta-derived candidate against the 442.0.0 class table) and
  `/tmp/ig-ipa/` (extracted bundle).
