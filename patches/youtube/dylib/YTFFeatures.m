// YTFFeatures.m - the YTFreedom feature catalog. SINGLE SOURCE OF TRUTH.
//
// Every setting the dylib exposes is declared exactly once here. The table
// drives:
//   1. NSUserDefaults registration  (YTFreedom.m registerDefaults:)
//   2. The in-app settings UI       (SettingsUI.m: groups, order, kinds,
//                                    restart hints, beta labels)
// Hooks read the same keys via IS_ENABLED(<key>) / INTFORVAL(<key>) with the
// K* macros from YTFreedom.h - the key string in this file is the single
// canonical spelling.
//
// Adding a feature: add one +spec row here (title/detail/group/default/
// restart/beta), then implement its hooks. Removing a feature: delete the row
// and its hooks.
//
// Group ids are declared in kGroups below. Order in kGroups = order in the
// settings UI; order inside a group = table order here. Curated, frequently
// used groups come first; rarely-changed and experimental groups live under
// the Advanced section at the bottom.
//
// Binary truth: every selector/identifier the dylib hooks is verified against
// com.google.ios.youtube 21.32.4 (otool + strings; see ROADMAP.md →
// "binary-verified findings"). Features marked beta=YES may not work on
// device - keep them under Advanced.

#import "YTFreedom.h"

@implementation YTFFeatureSpec
+ (instancetype)switchSpec:(NSString *)key title:(NSString *)title detail:(NSString *)detail
                     group:(NSString *)group defaultValue:(BOOL)dv restart:(BOOL)restart beta:(BOOL)beta {
    YTFFeatureSpec *s = [self new];
    s.key = key; s.title = title; s.detail = detail; s.group = group;
    s.kind = YTFFeatureSwitch; s.defaultValue = dv; s.restartRequired = restart; s.beta = beta;
    return s;
}
+ (instancetype)choiceSpec:(NSString *)key title:(NSString *)title detail:(NSString *)detail
                     group:(NSString *)group defaultValue:(NSInteger)dv restart:(BOOL)restart {
    YTFFeatureSpec *s = [self new];
    s.key = key; s.title = title; s.detail = detail; s.group = group;
    s.kind = YTFFeatureChoices; s.defaultValue = dv; s.restartRequired = restart;
    return s;
}
+ (instancetype)hiddenSwitch:(NSString *)key group:(NSString *)group defaultValue:(BOOL)dv {
    YTFFeatureSpec *s = [self new];
    s.key = key; s.title = key; s.group = group;
    s.kind = YTFFeatureSwitch; s.defaultValue = dv; s.hidden = YES;
    return s;
}
+ (instancetype)hiddenInt:(NSString *)key group:(NSString *)group intDefault:(NSInteger)dv {
    YTFFeatureSpec *s = [self new];
    s.key = key; s.title = key; s.group = group;
    s.kind = YTFFeatureChoices; s.defaultValue = dv; s.hidden = YES;
    return s;
}
@end

@implementation YTFGroupSpec
+ (instancetype)group:(NSString *)g title:(NSString *)title detail:(NSString *)detail
            container:(BOOL)container topLevel:(BOOL)top {
    YTFGroupSpec *s = [self new];
    s.group = g; s.title = title; s.detail = detail; s.container = container; s.isTopLevel = top;
    return s;
}
@end

// --- Groups (order = UI order; top-level first, Advanced sub-groups last) ---
static NSArray<YTFGroupSpec *> *kGroups(void) {
    static NSArray *groups;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        groups = @[
            [YTFGroupSpec group:@"player" title:@"Player" detail:nil container:NO topLevel:YES],
            [YTFGroupSpec group:@"appearance" title:@"Appearance" detail:nil container:NO topLevel:YES],
            [YTFGroupSpec group:@"shorts" title:@"Shorts" detail:nil container:NO topLevel:YES],
            [YTFGroupSpec group:@"feed" title:@"Feed" detail:nil container:NO topLevel:YES],
            [YTFGroupSpec group:@"navigation" title:@"Navigation" detail:nil container:NO topLevel:YES],
            [YTFGroupSpec group:@"tabbar" title:@"Tab bar" detail:nil container:NO topLevel:YES],
            [YTFGroupSpec group:@"advanced" title:@"Advanced"
                          detail:@"Rarely changed settings and experimental flags"
                        container:YES topLevel:YES],
            [YTFGroupSpec group:@"prefs" title:@"Preferences" detail:nil container:YES topLevel:YES],
            // Advanced sub-groups (rendered inside the Advanced section).
            [YTFGroupSpec group:@"advplayer" title:@"Advanced player"
                          detail:@"Demoted from Player - may work, verify on device"
                        container:NO topLevel:NO],
            [YTFGroupSpec group:@"ab" title:@"A/B Testing"
                          detail:@"Server-config flags - outcomes vary per device; flip + relaunch"
                        container:NO topLevel:NO],
            [YTFGroupSpec group:@"menu" title:@"Menu items"
                          detail:@"Remove entries from the video ... menu"
                        container:NO topLevel:NO],
            [YTFGroupSpec group:@"system" title:@"System"
                          detail:@"Dialogs, toasts, startup behavior"
                        container:NO topLevel:NO],
            [YTFGroupSpec group:@"settings" title:@"Settings sections"
                          detail:@"Hide sections from the app's Settings screen"
                        container:NO topLevel:NO],
            [YTFGroupSpec group:@"beta" title:@"Beta"
                          detail:@"Targets absent from 21.32.4 - test & report so each is rewired or dropped"
                        container:NO topLevel:NO],
        ];
    });
    return groups;
}

// --- The catalog. Order within a group = settings row order. ----------------
static NSArray<YTFFeatureSpec *> *kFeatures(void) {
    static NSArray *features;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        features = @[
            // ---- Player (curated) ----
            [YTFFeatureSpec switchSpec:KBackgroundPlayback title:@"Background playback"
                                detail:@"Audio continues with screen off"
                                 group:@"player" defaultValue:YES restart:YES beta:NO],
            // Old quality picker + Extra speeds are NOT working on 21.32.4 (the app
            // version-gates them and the menu rows never render) - moved to Beta.
            [YTFFeatureSpec switchSpec:KExtraSpeed title:@"Extra speeds (beta)"
                                detail:@"Speed menu from 0.25x to 10x - does not work on 21.32.4"
                                 group:@"beta" defaultValue:NO restart:YES beta:YES],
            [YTFFeatureSpec switchSpec:KOldQualityPicker title:@"Old quality picker (beta)"
                                detail:@"Classic grid quality menu - does not work on 21.32.4"
                                 group:@"beta" defaultValue:NO restart:YES beta:YES],
            [YTFFeatureSpec switchSpec:KMuteButtonPlayer title:@"Mute button"
                                detail:@"Mute control in the player bar"
                                 group:@"player" defaultValue:YES restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KGestureControls title:@"Gesture controls"
                                detail:@"Edge swipes adjust brightness, volume or speed"
                                 group:@"player" defaultValue:YES restart:NO beta:NO],
            [YTFFeatureSpec choiceSpec:KLeftSideGesture title:@"Left edge swipe"
                                detail:@"What the left-edge swipe controls"
                                 group:@"player" defaultValue:1 restart:NO],
            [YTFFeatureSpec choiceSpec:KRightSideGesture title:@"Right edge swipe"
                                detail:@"What the right-edge swipe controls"
                                 group:@"player" defaultValue:2 restart:NO],
            [YTFFeatureSpec switchSpec:KGestureHUD title:@"Gesture HUD"
                                detail:@"Show a % indicator during gestures"
                                 group:@"player" defaultValue:YES restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KLoopVideo title:@"Loop video"
                                detail:@"Restart playback when the video ends"
                                 group:@"player" defaultValue:NO restart:NO beta:NO],

            // ---- Appearance ----
            [YTFFeatureSpec switchSpec:KOLEDTheme title:@"OLED theme"
                                detail:@"True black dark theme"
                                 group:@"appearance" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KOLEDKeyboard title:@"OLED keyboard"
                                detail:@"True black keyboard in dark mode"
                                 group:@"appearance" defaultValue:NO restart:YES beta:NO],

            // ---- Shorts ----
            [YTFFeatureSpec switchSpec:KHideShortsLikeButton title:@"Hide like button"
                                detail:@"Filtered from the server-sent action rail"
                                 group:@"shorts" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideShortsDisLikeButton title:@"Hide dislike button"
                                detail:nil group:@"shorts" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideShortsCommentButton title:@"Hide comment button"
                                detail:nil group:@"shorts" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideShortsShareButton title:@"Hide share button"
                                detail:nil group:@"shorts" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideShortsMetaButton title:@"Hide metadata button"
                                detail:nil group:@"shorts" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KEnablesShortsQuality title:@"Enable quality selector"
                                detail:@"Quality option in the Shorts ... menu"
                                 group:@"shorts" defaultValue:NO restart:NO beta:NO],

            // ---- Feed ----
            [YTFFeatureSpec switchSpec:KHideSubbar title:@"Hide channel filter bar"
                                detail:nil group:@"feed" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideShortsShelf title:@"Hide Shorts shelf"
                                detail:nil group:@"feed" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSearchHis title:@"Hide search history"
                                detail:nil group:@"feed" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KNoRelatedVideos title:@"Hide related videos"
                                detail:@"Watch page suggestions"
                                 group:@"feed" defaultValue:NO restart:NO beta:NO],

            // ---- Navigation ----
            [YTFFeatureSpec switchSpec:KHideYTLogo title:@"Hide YouTube logo"
                                detail:nil group:@"navigation" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KPremiumLogo title:@"Premium logo"
                                detail:nil group:@"navigation" defaultValue:YES restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideNoti title:@"Hide notification button"
                                detail:nil group:@"navigation" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSearch title:@"Hide search button"
                                detail:nil group:@"navigation" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideVoiceSearch title:@"Hide voice search button"
                                detail:nil group:@"navigation" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideCastButtonNav title:@"Hide cast button"
                                detail:nil group:@"navigation" defaultValue:YES restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KStickyNavbar title:@"Sticky navigation bar"
                                detail:nil group:@"navigation" defaultValue:NO restart:NO beta:NO],

            // ---- Tab bar ----
            [YTFFeatureSpec choiceSpec:KDefaultTab title:@"Default tab"
                                detail:@"Home / Shorts / Subscriptions / Library / You"
                                 group:@"tabbar" defaultValue:0 restart:YES],

            // ---- Advanced player (beta - may work) ----
            [YTFFeatureSpec switchSpec:KHideAutoPlayToggle title:@"Hide autoplay toggle"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideCaptionsButton title:@"Hide captions button"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideCastButtonPlayer title:@"Hide cast button in player"
                                detail:nil group:@"advplayer" defaultValue:YES restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHidePrevButton title:@"Hide previous button"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideNextButton title:@"Hide next button"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KReplacePrevNextButtons title:@"Rewind/ffw instead of prev/next"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KRemoveDarkOverlay title:@"Remove dark overlay"
                                detail:@"Gradient behind the controls"
                                 group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideEndScreenCards title:@"Hide endscreen cards"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideSuggestedVideo title:@"Hide suggested video on finish"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHidePaidPromoOverlay title:@"Hide paid promo overlay"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideWaterMark title:@"Hide watermark"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KDisablesDoubleTap title:@"Disable double-tap seek"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KDisablesLongHold title:@"Disable long-press"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KAutoExitFullScreen title:@"Exit fullscreen on finish"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KDisablesCaptions title:@"Auto-disable captions"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KDisablesShowRemaining title:@"Disable remaining-time toggle"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KAlwaysShowRemaining title:@"Always show remaining time"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideFullAction title:@"Hide fullscreen actions"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideFullvidTitle title:@"Hide fullscreen title"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KStopAutoplayVideo title:@"Stop autoplay"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideContentWarning title:@"Skip content warning"
                                detail:@"Auto-confirm age/content warnings"
                                 group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KAutoFullScreen title:@"Auto fullscreen"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KPortFull title:@"Portrait fullscreen"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KDisablePullToFull title:@"Disable pull-to-fullscreen"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KTapToSeek title:@"Tap progress bar to seek"
                                detail:nil group:@"advplayer" defaultValue:NO restart:YES beta:YES],
            [YTFFeatureSpec switchSpec:KHidePlayerHeatmap title:@"Hide player heatmap"
                                detail:nil group:@"advplayer" defaultValue:NO restart:YES beta:YES],
            [YTFFeatureSpec switchSpec:KRedProgressBar title:@"Red progress bar"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KCopyTimestampedLink title:@"Copy timestamped link on pause"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KDisableHints title:@"Disable hints"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KForceMiniPlayer title:@"Force miniplayer"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KAlwaysShowSeekbar title:@"Always show seekbar"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideLikeButton title:@"Hide like button (watch page)"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideDisLikeButton title:@"Hide dislike button (watch page)"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShareButton title:@"Hide share button (watch page)"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideDownloadButton title:@"Hide download button (watch page)"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideSaveButton title:@"Hide save button (watch page)"
                                detail:nil group:@"advplayer" defaultValue:NO restart:NO beta:YES],

            // ---- A/B Testing (server-config flags, verified in the binary) ----
            [YTFFeatureSpec switchSpec:KChapterSeek title:@"Inline chapter seek"
                                detail:@"Tap chapters/segments to seek inline"
                                 group:@"ab" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KPinchToFullscreen title:@"Pinch to fullscreen"
                                detail:nil group:@"ab" defaultValue:YES restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KReduceOverlays title:@"Reduce player overlays setting"
                                detail:nil group:@"ab" defaultValue:YES restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KHQAAudio title:@"High-quality audio setting"
                                detail:nil group:@"ab" defaultValue:YES restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KShowShortsSeekbar title:@"Shorts seekbar"
                                detail:nil group:@"ab" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KShortsPlaybackSpeed title:@"Shorts speed from ... menu"
                                detail:nil group:@"ab" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KInlineShortsPlayback title:@"Inline Shorts shelf playback"
                                detail:nil group:@"ab" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KDisablesShortsPiP title:@"Disable Shorts PiP"
                                detail:nil group:@"ab" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KDisablesNewMiniPlayer title:@"Disable new miniplayer"
                                detail:nil group:@"ab" defaultValue:NO restart:YES beta:NO],

            // ---- Menu items ----
            [YTFFeatureSpec switchSpec:KRemoveDownloadMenu title:@"Remove Download"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KRemoveWatchLaterMenu title:@"Remove Watch later"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KRemoveSaveToPlaylistMenu title:@"Remove Save to playlist"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KRemoveShareMenu title:@"Remove Share"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KRemoveNotInterestedMenu title:@"Remove Not interested"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KRemoveDontRecommendMenu title:@"Remove Don't recommend channel"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KRemoveReportMenu title:@"Remove Report"
                                detail:nil group:@"menu" defaultValue:NO restart:NO beta:NO],

            // ---- System ----
            [YTFFeatureSpec switchSpec:KBlockUpgradeDialogs title:@"Block upgrade dialogs"
                                detail:nil group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KHideAreYouThereDialog title:@"Hide 'Are you there?' dialog"
                                detail:nil group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KDisablesSnackBar title:@"Disable snackbar"
                                detail:nil group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KHideStartupAni title:@"Hide startup animations"
                                detail:nil group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KHidePlayInNextQueue title:@"Hide 'Play next in queue'"
                                detail:nil group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KHideLikeDislikeVotes title:@"Hide like/dislike votes"
                                detail:@"Silent voting"
                                 group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KDisableRatePrompts title:@"Disable rate prompts"
                                detail:nil group:@"system" defaultValue:YES restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KHideHUDMessages title:@"Hide HUD messages"
                                detail:nil group:@"system" defaultValue:NO restart:YES beta:NO],
            [YTFFeatureSpec switchSpec:KSponsorBlock title:@"SponsorBlock"
                                detail:@"Skip sponsor segments (sends video IDs to api.sponsor.ajay.app)"
                                 group:@"system" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KKeepScreenOn title:@"Keep screen on"
                                detail:@"Prevent auto-lock/dimming while a video plays (DEMC-style)"
                                 group:@"system" defaultValue:NO restart:NO beta:NO],

            // ---- Settings sections (hide rows from the app's Settings screen) ----
            [YTFFeatureSpec switchSpec:KHideSAccountSection title:@"Hide Account section"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSAutoplaySection title:@"Hide Autoplay section"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSTryNewFeatures title:@"Hide 'Try new features' section"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSVideoQualityPrefs title:@"Hide Video quality preferences"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSNotifications title:@"Hide Notifications section"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSManageHistory title:@"Hide Manage all history"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSYourData title:@"Hide 'Your data in YouTube'"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSPrivacy title:@"Hide Privacy section"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],
            [YTFFeatureSpec switchSpec:KHideSLiveChat title:@"Hide Live chat section"
                                detail:nil group:@"settings" defaultValue:NO restart:NO beta:NO],

            // ---- Beta (targets absent from 21.32.4 - unverified) ----
            [YTFFeatureSpec switchSpec:KHideGenMusicShelf title:@"Hide music playlists shelf"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideFeedPost title:@"Hide feed posts"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideSubButton title:@"Hide subscribe button"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShoppingButton title:@"Hide shop button"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideMemberButton title:@"Hide memberships button"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideClipButton title:@"Hide clip button"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideRemixButton title:@"Hide remix button"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsRemixButton title:@"Shorts: hide remix"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsProducts title:@"Shorts: hide products"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsRecbar title:@"Shorts: hide rec bar"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsCommit title:@"Shorts: hide commit pill"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsSubscriptButton title:@"Shorts: hide subscribe"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsLiveButton title:@"Shorts: hide live"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsLensButton title:@"Shorts: hide lens"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsTrendsButton title:@"Shorts: hide trends"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],
            [YTFFeatureSpec switchSpec:KHideShortsToVideo title:@"Shorts: hide to-video"
                                detail:nil group:@"beta" defaultValue:NO restart:NO beta:YES],

            // ---- Hidden defaults (fixed, not exposed in the UI) ----
            [YTFFeatureSpec hiddenSwitch:KHideCreateButton group:@"navigation" defaultValue:YES],
            [YTFFeatureSpec hiddenInt:KGestureActivationArea group:@"player" intDefault:1],
            [YTFFeatureSpec hiddenInt:KGestureHUDSize group:@"player" intDefault:1],
            [YTFFeatureSpec hiddenInt:KGestureHUDPosition group:@"player" intDefault:0],

            // ---- Preferences (rendered inside the Preferences section) ----
            [YTFFeatureSpec switchSpec:KAutoClearCache title:@"Auto-clear cache"
                                detail:@"Clear cache on launch"
                                 group:@"prefs" defaultValue:YES restart:YES beta:NO],
        ];
    });
    return features;
}

NSArray<YTFFeatureSpec *> *ytfFeatureSpecs(void) { return kFeatures(); }
NSArray<YTFGroupSpec *> *ytfGroupSpecs(void) { return kGroups(); }

NSArray<YTFFeatureSpec *> *ytfFeaturesInGroup(NSString *group) {
    NSMutableArray *result = [NSMutableArray array];
    for (YTFFeatureSpec *spec in kFeatures())
        if ([spec.group isEqualToString:group]) [result addObject:spec];
    return result;
}
