# YouTube 21.32.4 — Feature-Port ROADMAP (YTFreedom)

Goal: port **all** features from the reference projects — [YouMod](https://github.com/Tonwalter888/YouMod)
(`Ads.x`/`Apperence.x`/`Cache.x`/`Download.x`/`Feed.x`/`Navbar.x`/`Others.x`/`Player.x`/`Settings.x`/
`Shorts.x`/`Sideloading.x`/`Tabbar.x`/`YouModPerferences.x`, built for exactly 21.32.4), [YTLite](https://github.com/dayanch96/YTLite)
(`YTLite.x`/`Settings.x`/`YTNativeShare.x`/`Sideloading.x`), and [uYouPlus](https://github.com/qnblackcat/uYouPlus) —
into the decrypted 21.32.4 IPA via ipa-forge, with a clean in-app settings UI mirroring the references.

Status legend: ✅ done · 🔄 in progress · ⬜ planned · ⛔ verified absent in 21.32.4 (skipped)

## Context

- Base IPA: `com.google.ios.youtube_21.32.4_und3fined.ipa` (decrypted, thin arm64).
- Delivery: `YouTubeMod_21.32.4_unsigned.ipa` (unsigned; AltStore signs at install).
- Hook verification is built into forge: `forge hooks extract|verify|audit` (class/method
  walk of `__objc_classlist`/`__objc_methlist`/`__objc_selrefs`, chained-fixup aware) and
  the `hooks:` block in `youtube.yaml` (159 declared, 12 required). The parser misses
  some methods; every suspicious selector was cross-checked with `strings` on the binary —
  **all confirmed present**.

### Architecture (from G0)

- One dylib `libYTHook.dylib`, plain ObjC-runtime swizzling (no substrate/logos), loaded via
  `LC_LOAD_DYLIB`. Source split per feature area, all compiled by `dylib/build.sh`:

  ```
  dylib/
    YTFreedom.h      # shared: settings keys, IS_ENABLED/INTFORVAL, hook plumbing, ytfHookConfigBool
    YTFreedom.m      # constructor: registers defaults, calls each area's init
    SignInFix.m      # sideload sign-in: SSO fingerprint strip, keychain, bundle identity
    AdBlock.m        # ad removal: player/feed/shorts + elementData killer (G19)
    SettingsUI.m     # G0 settings section + G14 preferences manager (import/export/reset/cache)
    PlayerFeatures.m # G1–G5, G18: player bar/overlay/behavior, quality, speed, YTLite extras,
                     #   consolidated overlay insertion, G20 player flags
    PlayerGestures.m # G6: edge-swipe gestures (brightness/volume/speed) + HUD
    NavbarTabbar.m   # G8, G9: navbar (logo/buttons/sticky) + tab bar
    FeedShorts.m     # G10, G11: feed/shorts toggles + consolidated _ASDisplayView/collection
                     #   hooks + G20 shorts flags + action-bar diagnostic
    MiscFeatures.m   # G7 background playback, G12 misc/promos/menu removal, G20 rate/HUD/promo
    Appearance.m     # G13: OLED theme + keyboard + surfaces
    Downloads.m      # G17 (final milestone — not yet created)
  ```

- Settings storage: `NSUserDefaults`, key prefix `YTFreedom` (e.g. `YTFreedomBackgroundPlayback`).
  Defaults registered in the constructor; every toggle read via `IS_ENABLED(key)`.
- Settings UI: a "YTFreedom" section inside the app's own Settings (category id inserted into
  `YTSettingsGroupData orderedCategories` + `YTAppSettingsPresentationData settingsCategoryOrder`,
  items built by `YTSettingsSectionItemManager` hook). Sub-sections (Player / Appearance /
  Navbar / Tab bar / Feed / Shorts / Downloading / Miscellaneous / Preferences) are pushed via
  `YTSettingsPickerViewController`. All UI classes/methods verified present in 21.32.4.
- Prompts/toasts: `YTAlertView` (infoDialog / confirmationDialogWithAction:actionTitle:) and
  `YTToastResponderEvent eventWithMessage:firstResponder:` — verified present.

## Goals (executed in order)

### G0 — Settings framework + Preferences section ✅⬜

- **Sections/sub-goals:**
  - 0.1 Split dylib into per-area files, shared `YTFreedom.h`, `build.sh` compiles `*.m`. ✅
  - 0.2 Settings keys header (all keys from the table below, defaults registration). ✅
  - 0.3 In-app "YTFreedom" settings section (category injection + item manager hook). ✅
  - 0.4 Preferences sub-section: Import / Export / Restore defaults + Clear cache +
    Auto-clear-cache toggle (from `YouModPerferences.x`).
  - 0.5 Version/about row.
- **Settings keys (all `YTFreedom*`; defaults in parentheses):**

  | Group | Key | Default |
  | --- | --- | --- |
  | Player | HideAutoPlayToggle, HideCaptionsButton, HidePrevButton, HideNextButton, ReplacePrevNextButtons, RemoveDarkOverlay, HideWaterMark, HideEndScreenCards, HideSuggestedVideo, HidePaidPromoOverlay, HideFullAction, HideFullvidTitle, DisablesShowRemaining, AlwaysShowRemaining, AlwaysShowSeekbar, RemoveAmbiantColors, StopAutoplayVideo, AutoExitFullScreen, AutoFullScreen, PortFull, DisablesCaptions, DisableHints, ForceMiniPlayer, FixesSlowMiniPlayer, DisablesNewMiniPlayer, DisablesDoubleTap, DisablesLongHold, HideContentWarning, OldQualityPicker, ExtraSpeed, GestureControls, GestureActivationArea(1), LeftSideGesture(1), RightSideGesture(2), GestureHUD, GestureHUDSize(1), GestureHUDPosition(0), HideLikeButton, HideDisLikeButton, HideShareButton, HideDownloadButton, HideClipButton, HideRemixButton, HideSaveButton | |
  | Background | BackgroundPlayback (**ON**), DisablesShortsPiP | |
  | Navbar | HideYTLogo, PremiumLogo (**ON**), HideNotificationButton, HideSearchButton, HideVoiceSearchButton, HideCastButtonNav | |
  | Tab bar | DefaultTab(0), HideTabIndicators, HideTabLabels, HideHomeTab, HideShortsTab, HideCreateButton (**ON**), HideSubscriptionsTab | |
  | Feed | HideSubbar, HideGenMusicShelf, HideFeedPost, HideShortsShelf, HideSearchHistory, HideSubButton, HideShoppingButton, HideMemberButton | |
  | Shorts | HideShortsLikeButton, HideShortsDisLikeButton, HideShortsCommentButton, HideShortsShareButton, HideShortsRemixButton, HideShortsMetaButton, HideShortsProducts, HideShortsRecbar, HideShortsCommit, HideShortsSubscriptButton, HideShortsLiveButton, HideShortsLensButton, HideShortsTrendsButton, HideShortsToVideo, EnablesShortsQuality, ShowShortsSeekbar | |
  | Misc | BlockUpgradeDialogs, HideAreYouThereDialog, DisablesSnackBar, HideStartupAnimations, HidePlayInNextQueue, HideLikeDislikeVotes, AutoClearCache (**ON**) | |
  | Appearance | OLEDTheme, OLEDKeyboard | |
  | Download | DownloadManager (**ON**), DownloadSaveToPhotos (**ON**), DownloadPreferDRCAudio | |
  | Ads | (always-on, no toggle) | |

- **Acceptance:** Settings → YTFreedom renders all groups; toggles persist across relaunch;
  import/export/restore work; no crash on any settings path.

### G1 — Player bar toggles (Player.x)

- Hide autoplay switch, captions button, prev/next buttons; replace prev/next with
  rewind/ffw; always show seekbar; remaining-time disable/always; hide fullscreen title.
- Hooks (all verified): `YTMainAppControlsOverlayView setAutoplaySwitchButtonRenderer:/
  setClosedCaptionsOrSubtitlesButtonAvailable:/setPreviousButtonHidden:/setNextButtonHidden:/
  titleViewHidden`, `YTInlinePlayerBarContainerView setShouldDisplayTimeRemaining:/
  setPlayerBarAlpha:`, `YTPlayerBarController setActiveSingleVideo:`, `YTSettings/YTSettingsImpl
  isAutoplayEnabled`, `YTColdConfig replaceNextPaddleWithFastForwardButtonForSingletonVods/
  replacePreviousPaddleWithRewindButtonForSingletonVods` (strings-verified).
- **Acceptance:** each toggle visibly affects the player bar in fullscreen/inline.

### G2 — Player overlay/UI toggles (Player.x)

- Remove dark overlay gradient, hide watermark (player + featured-channel annotation),
  hide endscreen cards, hide suggested-video endscreen, hide fullscreen action buttons,
  disable ambient (cinematic) lights, hide paid-content overlay, skip content-warning confirm.
- Hooks (verified): `YTMainAppVideoPlayerOverlayView setBackgroundVisible:isGradientBackground:/
  isWatermarkEnabled/setWatermarkEnabled:/isFullscreenActionsVisible`, `YTCreatorEndscreenView
  setHidden:/setHoverCardHidden:/setHoverCardRenderer:`, `YTAutonavEndscreenController
  showEndscreen/showEndscreenControlsInPlayerBar:`, `YTFullscreenActionsView sizeThatFits:`,
  `YTCinematicContainerView layoutSubviews/loadWithModel:/initWithFrame:`,
  `YTAnnotationsViewController loadFeaturedChannelWatermark`, `YTMainAppVideoPlayerOverlayView-
  Controller setPaidContentWithPlayerData:/playerOverlayProvider:didInsertPlayerOverlay:`
  (paid_content id), `YTInlineMutedPlaybackPlayerOverlayViewController
  setPaidContentWithPlayerData:`, `YTPlayabilityResolutionUserActionUIController(Impl)
  showConfirmAlert`.
- **Acceptance:** overlay toggles apply without breaking playback controls.

### G3 — Playback behavior toggles (Player.x)

- Stop autoplay, exit fullscreen on finish, auto-fullscreen, portrait fullscreen,
  auto-disable captions, disable hints (3 settings classes), force miniplayer,
  disable double-tap/long-hold gestures.
- Hooks (verified): `YTPlaybackConfig setStartPlayback:`, `YTWatchFlowController
  shouldExitFullScreenOnFinish`, `YTPlayerViewController loadWithPlayerTransition:
  playbackConfig:/prepareToLoadWithPlayerTransition:expectedLayout:`,
  `YTWatchViewController allowedFullScreenOrientations`, `YTSettings/YTSettingsImpl/
  YTUserDefaults areHintsDisabled/setHintsDisabled:`, `YTIMiniplayerRenderer` (+
  `hasMinimizedEndpoint`/`hasPlaybackMode` %new), `YTMainAppVideoPlayerOverlayViewController
  allowDoubleTapToSeekGestureRecognizer/allowLongPressGestureRecognizerInView:`,
  `YTMainAppVideoPlayerOverlayView setSeekAnywherePanGestureRecognizer` (strings).
- **Acceptance:** toggles behave on device (auto-fullscreen after 0.75s, hints gone, etc.).

### G4 — Video quality (Player.x / YTClassicVideoQuality)

- "Old" quality picker (redesigned controller bypass) when enabled; `%new`
  `YTIMediaQualitySettingsHotConfig enableQuickMenuVideoQualitySettings -> NO`.
- Hooks: `YTVideoQualitySwitchOriginalController setUserSelectableFormats:/dealloc`
  (parser flags setUserSelectableFormats:initWithServiceRegistryScope:parentResponder:
  sel-absent → verify exact selector via strings before porting), `YTMenuController
  actionsForRenderers:fromView:entry:shouldLogItems:firstResponder:` (menu_item_video_quality).
- **Acceptance:** quality menu shows classic picker; no crash switching formats.

### G5 — Extra playback speed (Player.x / YouSpeed)

- Speed options 0.25×–10×: replace `YTVarispeedSwitchController(Impl)` `_options`,
  `%new` `YTIPlayerHotConfig maximumPlaybackRate -> 10.0` (f@:) and
  `YTIGranularVariableSpeedConfig maximumPlaybackRate -> 1000` (d@:), plus
  `YTMenuController` hook so "Playback speed" opens the varispeed sheet directly.
- **Acceptance:** speed menu lists 13 rates; 5×/7.5×/10× actually apply; setting persists.

### G6 — Player gestures (Player.x / YTLitePlus)

- Vertical edge swipes → brightness/volume/playback-speed (left/right side configurable),
  activation-area percent, HUD with icon+percent, HUD size/position.
- Hooks: `YTWatchLayerViewController watchController:didSetPlayerViewController:` (attach
  pan), `YTPlayerViewController` +`YouModPanGesture`/`YouModGestureHUD` properties,
  `%new gestureRecognizerShouldBegin:/YouModHandlePanGesture:/gestureRecognizer:shouldBe-
  RequiredToFailByGestureRecognizer:/gestureRecognizer:shouldRecognizeSimultaneouslyWith-
  GestureRecognizer:` (needs associated-object storage since no %property in plain runtime).
- Depends on G5 (`setPlaybackRate:` speed control).
- **Acceptance:** left/right edge swipe adjusts the chosen control with HUD; center area
  unaffected; no gesture conflicts with seek/dismiss.

### G7 — Background playback (Others.x / YouTube-X)

- `YTIPlayabilityStatus isPlayableInBackground`, `YTPlaybackData isPlayableInBackground`,
  `MLVideo playableInBackground` → YES when enabled; `%new YTIBackgroundOfflineSetting-
  CategoryEntryRenderer isBackgroundEnabled -> YES`. (YTIPlayerResponse variant: selector
  exists elsewhere in 21.32.4 — skip, superseded.)
- Shorts PiP toggle: `YTColdConfig shortsPlayerGlobalConfigEnableReelsPictureInPicture(Ios)`,
  `YTHotConfig ...AllowedFromPlayer`, `YTReelModel isPiPSupported`,
  `YTReelPlayerViewController isPictureInPictureAllowed`, `YTReelWatchRootViewController
  switchToPictureInPicture`.
- **Acceptance:** audio continues with screen off / app backgrounded; PiP off in Shorts.

### G8 — Navbar / header (Navbar.x)

- Hide YT logo, premium logo swap, hide notification/search/voice-search/cast buttons.
- Hooks: `YTHeaderLogoController` (`class-unparsed` → strings-verify
  `init/setPremiumLogo:/isPremiumLogo/setTopbarLogoRenderer:`), `YTRightNavigationButtons`,
  `YTHeaderView` (verified via strings), `MDXPlaybackRouteButtonController` (cast).
- **Acceptance:** logo/buttons hide per toggle on home; premium logo shows when enabled.

### G9 — Tab bar (Tabbar.x)

- Default tab, hide indicators/labels, hide Home/Shorts/Create/Subscriptions tabs.
- Hooks: `YTPivotBarViewController/YTPivotBarView/YTPivotBarItemView/YTPivotBarIndicatorView`,
  `_ASDisplayView didMoveToWindow` (accessibility-identifier based),
  `YTAppViewController showPivotBar` (class-unparsed → strings-verify).
- **Acceptance:** tabs hide/select per toggle; no blank tab bar.

### G10 — Feed (Feed.x + Ads.x sections)

- Hide subbar, music shelf, feed posts, shorts shelf, search history/suggestions,
  subscribe/shop/membership buttons; ad-card filtering (already in AdBlock, extend if needed).
- Hooks: `YTInnerTubeCollectionViewController displaySectionsWithReloadingSectionController-
  ByRenderer:/addSectionsFromArray:` (KVC `_sectionRenderers`), `_ASDisplayView
  didMoveToWindow` (accessibility ids), `YTSearchViewController`, `YTMySubsFilterHeaderView`
  (strings-verify setChipFilterView), `YTHeaderContentComboView` (strings-verify
  setFeedHeaderScrollMode).
- **Acceptance:** feed elements hide per toggle; scrolling stays smooth.

### G11 — Shorts (Shorts.x + YTLite.x)

- Hide like/dislike/comment/share/remix/meta/products/recbar/commit/subscribe/live/lens/
  trends/to-video buttons; enable quality in Shorts; show seekbar; always player bar.
- Hooks: `YTReelWatchPlaybackOverlayView` setters (several parser-absent → strings-verify:
  setNativePivotButton:/setPivotButtonElementRenderer:/setReelLikeButton:/setReelDislikeButton:/
  setRemixButton:/setShareButton:/setViewCommentButton:), `YTReelPlayerViewController
  shouldEnablePlayerBar`, `YTReelPlayerButton titleLabel` (strings), `YTShortsPlayerViewController`
  (strings-verify quality/seekbar paths), `_ASDisplayView didMoveToWindow` (ids).
- **Acceptance:** Shorts buttons hide per toggle; player bar shows on pause when enabled.

### G12 — Miscellaneous (Others.x)

- Block upgrade dialogs, hide "Are you there?" dialog, disable snackbar, hide startup
  animations, hide "Play next in queue" menu item, silent like/dislike vote
  (drop `YTInnerTubeResponseWrapper initWithResponse:...` for like/dislike responses).
- Hooks (verified): `YTGlobalConfig shouldBlockUpgradeDialog/shouldShowUpgradeDialog/
  shouldShowUpgrade/shouldForceUpgrade`, `YTColdConfig enableYouthereCommandsOnIos/
  mainAppCoreClientIosEnableStartupAnimation`, `YTYouThereController(Impl)
  shouldShowYouTherePrompt/showYouTherePrompt`, `GOOHUDManagerInternal sharedInstance/
  showMessageMainThread:/activateOverlay:/displayHUDViewForMessage:`, `YTMenuItemVisibility-
  Handler(Impl) shouldShowServiceItemRenderer:` (iconType 251).
- **Acceptance:** dialogs suppressed; snackbar gone; startup animation skipped.

### G13 — Appearance (Apperence.x)

- OLED true-black theme + OLED keyboard.
- Hooks: `YTCommonColorPalette`, `YTColor`, `UIKeyboard/UIInputView/UIKBVisualEffectView/
  UIPredictionViewController/UIKeyboardDockView` layout (system classes — plain swizzle on
  UIKit, no classlist needed; guard with `class_getInstanceMethod`).
- **Acceptance:** dark theme becomes pure black when enabled; keyboard black in dark mode.

### G14 — Preferences manager (YouModPerferences.x)

- Import/export `YTFreedom*` NSUserDefaults keys via `UIDocumentPickerViewController`,
  restore defaults, clear cache (with size display + `YTToastResponderEvent` toast),
  auto-clear cache on launch.
- Classes: `YTAlertView` dialogs, `YTSettingsPickerViewController` rows. Depends on G0.
- **Acceptance:** export → reinstall → import restores all settings; reset clears them;
  cache size shows and clears.

### G15 — Native share sheet (YTLite YTNativeShare.x)

- Replace YouTube's share UI with the native share sheet (`UIActivityViewController`).
- Hooks from `YTNativeShare.x` (verify each selector in 21.32.4).
- **Acceptance:** Share button opens native sheet with video link/thumbnail.

### G16 — Return YouTube Dislikes (uYouPlus / YouTubeDislikesReturn)

- Show dislike counts back on the like bar. Requires a public dislikes API
  (e.g. the RYD endpoint) — decide server approach during implementation.
- **Acceptance:** dislike count renders next to the dislike button on watch pages.

### G17 — Download manager (Download.x — biggest, do last)

- Download button on the player, format picker (video/audio), NSURLSession downloads of
  `streamingData` URLs, AVFoundation merge (no ffmpegkit dependency — fallback path only),
  Photos export, background tasks, progress UI, download manager screen.
- Hooks (verified): `YTPlayerViewController` (`viewDidAppear:/viewWillDisappear:` for the
  download button + current-player tracking), `SSOAuthorization(Impl) accessToken` +
  `GNPSSOAuthorizationService` (authenticated downloads; class-unparsed → strings-verify
  `accessToken`), `_ASDisplayView` (button insertion).
- 2386-line port; break into sub-goals (button → picker → download core → manager UI →
  photos). Requires `streamingData` probe logic + cookies/headers (already in reference).
- **Acceptance:** can download a video in background, file appears in Files/Photos, UI shows
  progress; pauses/resumes survive relaunch where iOS allows.

### G18 — YTLite-only extras (YTLite.x)

- Background playback via YTLite classes (subset of G7), subscriptions filter header chips,
  hide YT shorts shelf variants, comments-section chip hiding (`YTColdConfig
  enableChipsInTheCommentsHeaderIos` — ⛔ absent, skip), `YTSectionListViewController`
  (⛔ absent — ad filtering lives in YTInnerTubeCollectionViewController already),
  `YTPlaylistMiniBarView` (⛔ setFrame sel-elsewhere — skip), `NSParagraphStyle` text
  direction hack (⛔ skip).
- **Acceptance:** each ported toggle works; everything verified-absent is documented here.

### G19 — Adblock polish (in progress)

- Feed filtering already active; add remaining `_ASDisplayView` eml.ads ids if the user
  reports feed ads; verify `YTAdsInnerTubeContextDecorator` decorates nothing on device.
- **Acceptance:** no player/feed/Shorts ads across a 30-minute mixed session.

## Explicitly out of scope / deferred

- **G15 Native share — blocked on API drift (documented).** The hook entry point
  `ELMPBShowActionSheetCommand executeWithCommandContext:handler:` and the
  `serializedShareEntity` field exist in 21.32.4, but the protobuf extension-root
  lookup the reference uses (`YTIInnertubeCommandExtensionRoot innertubeCommand`,
  `YTIUpdateShareSheetCommand updateShareSheetCommand`) and the unknown-field
  traversal API (`GPBUnknownFieldSet getField:`/`lengthDelimitedList`) are absent
  from the 21.32.4 protobuf runtime. Completing it needs either (a) re-deriving the
  extension field numbers via protobuf analysis of the binary, or (b) a simpler
  direct approach — extract the watch URL from `YTWatchController`/`YTPlayerViewController`
  and present `UIActivityViewController` from the share button. Revisit after G17.
- **G16 Return YouTube Dislikes — research updated.** Evidence that the stock
  client renders the Shorts dislike button: RYD's 21.32.4 dylib hooks
  `updateLikeButtonWithRenderer:` + `setDislikeCountText:` on the reel overlay.
  The Shorts action rail is **server-driven**: `YTReelWatchPlaybackOverlayView
  setActionBarElementRenderer:` receives a renderer whose `actionBarButtonsArray`
  (protobuf repeated field) defines the buttons; YouTube omits the dislike entry
  for some cohorts/regions (A-B). Our patch has no code path that removes it
  (the `_ASDisplayView` id-hides are inert on 21.32.4 — those ids don't exist).
  A diagnostic hook now logs the received buttons to `com.nandan.ytfreedom`
  os_log, so the device log proves what the server sent. Forcing the button
  client-side would need protobuf construction of a dislike renderer with a
  `YTIDislikeEndpoint` tap target — deferred until the diagnostic confirms it's
  worth the RE.
- **G17 Downloads (final milestone).** YouMod's `Download.x` (2386 lines) is
  self-contained (NSURLSession on `streamingData` URLs + AVFoundation merge + Photos
  export, no server). Sub-plan: (1) download button on the player via
  `YTPlayerViewController viewDidAppear:`/`viewWillDisappear:` + `_ASDisplayView`;
  (2) format picker (video/audio, DRC toggle); (3) `SSOAuthorization accessToken`
  for authenticated streams; (4) download core + progress + background session;
  (5) manager screen + Files/Photos export. Verify `SSOAuthorization(Impl)
  accessToken` + `GNPSSOAuthorizationService` selectors first.
- **SponsorBlock** (uYouPlus): defer until G17 done; decide then.
- **Watch-mini-bar / segmentable player bar** (⛔ classes absent in 21.32.4).
- **OGLPhenotypeFlagServiceImpl / YTReelInfinitePlaybackDataSource** (⛔ absent).
- **App extensions** (widgets/share/intents/notifications): deliberately stripped for
  AltStore install (IXErrorDomain Code=2 fix) — do not re-add.

## New-IPA research (G20): what 21.32.4 enables that the references don't know about

Two discovery passes over the binary + current forks:

1. **Config-flag surface (776 YTColdConfig/YTHotConfig getters)** — the A/B
   switches. Added toggles for the client-side UX wins: `iosEnableMuteButton-
   PlayerControl` (mute button), `enableInlinePlayerChapterSeek` + `SegmentSeek`
   (chapter seek), `shortsConsumptionClientGlobalConfigIosEnableShortsPlayback-
   SpeedFromMenu` (Shorts speed), `iosEnableInlinePlaybackOnShortsShelf`
   (inline Shorts shelf). All verified present; mechanism identical to the
   existing `enableIosFloatingMiniplayer` toggle.
2. **uYouEnhanced diff (157 hooked classes vs ours)** — ported the portable
   wins: `SKStoreReviewController requestReview` no-op (rate prompts),
   `YTHUDMessageView initWithMessage:dismissHandler:` -> nil (toasts),
   `YTPlayerBarHeatwaveView initWithFrame:heatmap:startTime:endTime:` nil +
   `YTPlayerBarController setHeatmap:` nil (heatmap), `YTFullscreenEngagement-
   OverlayController relatedVideosPeekingEnabled` NO (fullscreen related-videos
   peeking, tied to HideSuggestedVideo).

Not ported (documented): LowContrastMode (uYou theme feature), FRPreferences/
FRPSelectListTable/settingsReorderTable (uYou's own settings UI — we use the
native YouTube settings), BigYTMiniPlayer (needs the absent YTWatchMiniBarView),
YTReExplore, alternate-app-icons (no icon set in our build).

## Audit results (systematic pass — all 159 hooks classified)

`forge hooks audit --ipa <decrypted.ipa> --dir dylib/` classifies every hook
our dylib installs against the 21.32.4 binary (`forge hooks verify` does the
same for the `hooks:` block in `youtube.yaml`). Results: 151/159 attach;
the 8 `unverified` are classname-only classes / parser decode gaps (all
strings-confirmed present). Two earlier findings, both fixed:

- **Paid-content promo**: `YTMainAppVideoPlayerOverlayViewController
  setPaidContentWithPlayerData:` does not exist on that class in 21.32.4 (the
  old hook no-op'd). The real paths are `YTPaidContentController
  setPaidContentRenderer:` and `YTPaidContentViewController
  showPaidContentRenderer:`/`hidePaidContent` — now hooked (gated by
  HidePaidPromoOverlay).
- Everything else flagged by the parser (`setHidden:`, `setFrame:`,
  `titleLabel`, GPBMessage accessors) is either inherited from system classes
  or strings-verified present; the parser under-reports methods on
  GPBMessage subclasses and REL-flag method lists.

Additional hardening this pass: `YTIElementRenderer elementData` ad-killer
(YTLite's strongest feed/watch-next ad hook — element with ad-logging data
renders nothing; ad-layout descriptions render empty), complementing the
section-level filter. Config/A-B surfaces (player bar, menu, miniplayer,
Shorts rail) are server/hot-config driven — hook attachment is verified by
the `YTFreedom: hooked -[...]` os_log lines at launch.

## Verification loop (per goal)

1. Verify targets with `forge hooks extract --ipa <ipa> --search <regex>`
   and `forge hooks audit --ipa <ipa> --dir dylib/` (or strings on the binary).
2. Implement in the area `.m`, build dylib (`dylib/build.sh`), dry-run + build IPA.
3. On-device: toggle in Settings → apply → relaunch → confirm behavior + check
   `com.nandan.ytfreedom` os_log lines for hook-attach messages.
4. Update this ROADMAP's status column; commit per goal.

## Current status

| Goal | Status |
| --- | --- |
| G0 Settings framework | ✅ (0.1–0.5 done; needs on-device pass) |
| G1–G3 Player bar / overlay / behavior | ✅ implemented — on-device pass pending |
| G4 Old quality picker | ✅ implemented — on-device pass pending |
| G5 Extra speed (0.25×–10×) | ✅ implemented — on-device pass pending |
| G6 Player gestures | ✅ implemented (edge swipes: brightness/volume/speed + HUD) — on-device pass pending |
| G7 Background playback | ✅ implemented — on-device pass pending |
| G8–G9 Navbar/Tabbar | ✅ implemented + **You-tab (FEaccount) support** — on-device pass pending |
| G10–G11 Feed/Shorts | ✅ implemented — Shorts rail now filtered by **icon type** (no a11y ids in 21.32.4); dead id-targets moved to **Beta** — on-device pass pending |
| G12 Misc | ✅ implemented (+ NoYTPremium promo blockers, menu-item removal) — on-device pass pending |
| G13 Appearance (OLED) | ✅ fixed + expanded (pageStyle cast bug; full palette + surfaces) — on-device pass pending |
| G14 Preferences manager | ✅ implemented (import/export/reset/cache) — on-device pass pending |
| G15 Native share | ⛔ blocked on API drift — see below |
| G16 RYD dislikes | 🔄 partial research — see below |
| G17 Downloads | ⬜ final milestone — sub-plan below |
| G18 YTLite extras | ✅ portable subset done (red progress bar, related-videos hide, timestamped link on pause, menu-item removal, sticky navbar, label fitting, playlist minibar) — on-device pass pending |
| G19 Adblock polish | ✅ (promo blockers folded into G12) |
| G20 New-IPA UX batch | ✅ A/B submenu rebuilt from **otool-verified** flags (14/16 real; 2 dropped); watch action-bar re-hooked on `YTSlimVideoDetailsActionView` (covers both variants); restart pills on config-bound toggles — on-device pass pending |

### v0.0.2 r2 — binary-verified findings (record for future ports)

Verified against the 21.32.4 binary (otool `-ov` + strings; the forge parser
under-reports relative method lists, so otool is ground truth):

- **Config flags real on YTColdConfig/YTHotConfig (hookable)**: `iosEnableMuteButtonPlayerControl`,
  `enableInlinePlayerChapterSeek`, `enableInlinePlayerSegmentSeek`,
  `deprecateTabletPinchFullscreenGestures`, `enableReducePlayerOverlaysSettings`,
  `iosEnableHighQualityAudioAppSettings`,
  `premiumClientSharedConfigEnablePremiumHighQualityAudioSettingOnIos`,
  `shortsConsumptionClientGlobalConfigIosEnableShortsPlaybackSpeedFromMenu`,
  `iosEnableInlinePlaybackOnShortsShelf`, `iosEnableVideoPlayerScrubber`,
  `enableIosFloatingMiniplayer`, `shortsPlayerGlobalConfigEnableReelsPictureInPicture`(+`Ios`),
  `shortsPlayerGlobalConfigEnableReelsPictureInPictureAllowedFromPlayer` (**YTHotConfig**).
  Mute/reduce-overlays/floating-miniplayer also exist on
  `YTColdConfigWatchPlayerClientGlobalConfigImpl`.
- **Dead (selref/property only — do not hook)**: `isPinchToEnterFullscreenEnabled`,
  `enableAnimatedPreviewsSettings`.
- **A11y ids that exist**: `id.video.like.button`, `id.video.dislike.button`,
  `id.video.share.button`, `id.video.add_to.button`, `id.ui.add_to.offline.button`,
  `id.reel_pivot_button`, `id.watch.related_videos.*`. **Absent (dead targets)**: all
  other `id.reel_*` button ids, `clip_button.eml`, `id.video.remix.button`,
  `product_sticker.main_target`, `id.elements.components.suggested_action`,
  `eml.shorts-disclosures`, `id.ui.shorts_paused_state.*`, `id.reel_multi_format_link`,
  `feed_nudge.view`, `id.ui.backstage.original_post`, `eml.animated_subscribe_button`,
  `eml.header_store_button`, `id.sponsor_button`, `eml.expandable_metadata.vpp`, `eml.ad_layout.*`.
- **Watch-page action bar**: rendered by `YTSlimVideoDetailsActionView` (plain UIView,
  NOT `_ASDisplayView` — the old id-hook never fired) in two variants:
  `YTISlimVideoActionBarRenderer` (single row) and `YTISlimVideoScrollableActionBarRenderer`
  (scrollable). Hook `updateAccessibilityIdentifier`/`didMoveToWindow` on the view class.
- **Shorts rail**: server-driven via `YTReelWatchPlaybackOverlayView setActionBarElementRenderer:`
  (only surviving entry — `setNativePivotButton:`/`setReelLikeButton:` etc. are gone).
  Filter `actionBarButtonsArray` by `iconType` (like 160/301, dislike 51/302, share 48,
  comment 637/638); the diagnostic log lists every button's icon+a11y for rewiring.
- **Tab bar**: server decides the set (`fetchPivotBar`); identifiers `FEwhat_to_watch`,
  `FEshorts`, `FEsubscriptions`, `FElibrary`, `FEaccount` (You), `FEuploads` (create).
  Default-tab selection is now identifier-based with You/Library fallback.
