// YTFreedom.h — shared header for the YTFreedom hook dylib (YouTube 21.32.4).
//
// Declares the settings keys, the hook plumbing (plain ObjC-runtime
// swizzling, no substrate), and the informal protocols used to call
// YouTube's settings-UI classes. Every non-plumbing selector used here was
// verified present in the 21.32.4 binary (forge hooks + strings).

#ifndef YTFREEDOM_H
#define YTFREEDOM_H

#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <os/log.h>

#define YT_BUNDLE_ID @"com.google.ios.youtube"
#define YT_NAME @"YouTube"
#define YTFREEDOM_VERSION @"0.4.0"

// ---------------------------------------------------------------------------
// Settings keys (NSUserDefaults, prefix YTFreedom)
// ---------------------------------------------------------------------------
#define KBackgroundPlayback      @"YTFreedomBackgroundPlayback"
#define KDisablesShortsPiP       @"YTFreedomDisablesShortsPiP"
#define KHideAutoPlayToggle      @"YTFreedomHideAutoPlayToggle"
#define KHideCaptionsButton      @"YTFreedomHideCaptionsButton"
#define KHidePrevButton          @"YTFreedomHidePrevButton"
#define KHideNextButton          @"YTFreedomHideNextButton"
#define KReplacePrevNextButtons  @"YTFreedomReplacePrevNextButtons"
#define KRemoveDarkOverlay       @"YTFreedomRemoveDarkOverlay"
#define KHideWaterMark           @"YTFreedomHideWaterMark"
#define KHideEndScreenCards      @"YTFreedomHideEndScreenCards"
#define KHideSuggestedVideo      @"YTFreedomHideSuggestedVideo"
#define KHidePaidPromoOverlay    @"YTFreedomHidePaidPromoOverlay"
#define KHideFullAction          @"YTFreedomHideFullscreenActions"
#define KHideFullvidTitle        @"YTFreedomHideFullscreenTitle"
#define KDisablesShowRemaining   @"YTFreedomDisablesShowRemaining"
#define KAlwaysShowRemaining     @"YTFreedomAlwaysShowRemaining"
#define KAlwaysShowSeekbar       @"YTFreedomAlwaysShowSeekbar"
#define KRemoveAmbiant           @"YTFreedomRemoveAmbiant"
#define KStopAutoplayVideo       @"YTFreedomStopAutoplayVideo"
#define KAutoExitFullScreen      @"YTFreedomAutoExitFullscreen"
#define KAutoFullScreen          @"YTFreedomAutoFullscreen"
#define KPortFull                @"YTFreedomPortraitFullscreen"
#define KDisablesCaptions        @"YTFreedomAutoDisableCaptions"
#define KDisableHints            @"YTFreedomDisableHints"
#define KForceMiniPlayer         @"YTFreedomForceMiniPlayer"
#define KFixesSlowMiniPlayer     @"YTFreedomFixesSlowMiniPlayer"
#define KDisablesNewMiniPlayer   @"YTFreedomDisablesNewMiniPlayer"
#define KDisablesDoubleTap       @"YTFreedomDisablesDoubleTap"
#define KDisablesLongHold        @"YTFreedomDisablesLongHold"
#define KHideContentWarning      @"YTFreedomHideContentWarning"
#define KOldQualityPicker        @"YTFreedomOldQualityPicker"
#define KExtraSpeed              @"YTFreedomExtraSpeed"
#define KGestureControls         @"YTFreedomGestureControls"
#define KGestureActivationArea   @"YTFreedomGestureActivationArea"
#define KLeftSideGesture         @"YTFreedomLeftSideGesture"
#define KRightSideGesture        @"YTFreedomRightSideGesture"
#define KGestureHUD              @"YTFreedomGestureHUD"
#define KGestureHUDSize          @"YTFreedomGestureHUDSize"
#define KGestureHUDPosition      @"YTFreedomGestureHUDPosition"
#define KHideLikeButton          @"YTFreedomHideLikeButton"
#define KHideDisLikeButton       @"YTFreedomHideDislikeButton"
#define KHideShareButton         @"YTFreedomHideShareButton"
#define KHideDownloadButton      @"YTFreedomHideDownloadButton"
#define KHideClipButton          @"YTFreedomHideClipButton"
#define KHideRemixButton         @"YTFreedomHideRemixButton"
#define KHideSaveButton          @"YTFreedomHideSaveButton"
#define KHideYTLogo              @"YTFreedomHideYTLogo"
#define KPremiumLogo             @"YTFreedomPremiumLogo"
#define KHideNoti                @"YTFreedomHideNotificationButton"
#define KHideSearch              @"YTFreedomHideSearchButton"
#define KHideVoiceSearch         @"YTFreedomHideVoiceSearchButton"
#define KHideCastButtonNav       @"YTFreedomHideCastButtonNav"
#define KHideCastButtonPlayer    @"YTFreedomHideCastButtonPlayer"
#define KDefaultTab              @"YTFreedomDefaultTab"
#define KHideTabIndi             @"YTFreedomHideTabIndicators"
#define KHideTabLabels           @"YTFreedomHideTabLabels"
#define KHideHomeTab             @"YTFreedomHideHomeTab"
#define KHideShortsTab           @"YTFreedomHideShortsTab"
#define KHideCreateButton        @"YTFreedomHideCreateButton"
#define KHideSubscriptTab        @"YTFreedomHideSubscriptionsTab"
#define KHideSubbar              @"YTFreedomHideSubbar"
#define KHideGenMusicShelf       @"YTFreedomHideMusicShelf"
#define KHideFeedPost            @"YTFreedomHideFeedPost"
#define KHideShortsShelf         @"YTFreedomHideShortsShelf"
#define KHideSearchHis           @"YTFreedomHideSearchHistory"
#define KHideSubButton           @"YTFreedomHideSubButton"
#define KHideShoppingButton      @"YTFreedomHideShoppingButton"
#define KHideMemberButton        @"YTFreedomHideMemberButton"
#define KHideShortsLikeButton    @"YTFreedomHideShortsLikeButton"
#define KHideShortsDisLikeButton @"YTFreedomHideShortsDislikeButton"
#define KHideShortsCommentButton @"YTFreedomHideShortsCommentButton"
#define KHideShortsShareButton   @"YTFreedomHideShortsShareButton"
#define KHideShortsRemixButton   @"YTFreedomHideShortsRemixButton"
#define KHideShortsMetaButton    @"YTFreedomHideShortsMetaButton"
#define KHideShortsProducts      @"YTFreedomHideShortsProducts"
#define KHideShortsRecbar        @"YTFreedomHideShortsRecbar"
#define KHideShortsCommit        @"YTFreedomHideShortsCommit"
#define KHideShortsSubscriptButton @"YTFreedomHideShortsSubscribeButton"
#define KHideShortsLiveButton    @"YTFreedomHideShortsLiveButton"
#define KHideShortsLensButton    @"YTFreedomHideShortsLensButton"
#define KHideShortsTrendsButton  @"YTFreedomHideShortsTrendsButton"
#define KHideShortsToVideo       @"YTFreedomHideShortsToVideo"
#define KEnablesShortsQuality    @"YTFreedomEnablesShortsQuality"
#define KShowShortsSeekbar       @"YTFreedomShowShortsSeekbar"
#define KBlockUpgradeDialogs     @"YTFreedomBlockUpgradeDialogs"
#define KHideAreYouThereDialog   @"YTFreedomHideAreYouThereDialog"
#define KDisablesSnackBar        @"YTFreedomDisablesSnackBar"
#define KHideStartupAni          @"YTFreedomHideStartupAnimations"
#define KHidePlayInNextQueue     @"YTFreedomHidePlayInNextQueue"
#define KHideLikeDislikeVotes    @"YTFreedomHideLikeDislikeVotes"
#define KOLEDTheme               @"YTFreedomOLEDTheme"
#define KOLEDKeyboard            @"YTFreedomOLEDKeyboard"
#define KDownloadManager         @"YTFreedomDownloadManager"
#define KDownloadSaveToPhotos    @"YTFreedomDownloadSaveToPhotos"
#define KDownloadPreferDRCAudio  @"YTFreedomDownloadPreferDRCAudio"
#define KAutoClearCache          @"YTFreedomAutoClearCache"

// G18 YTLite extras / G6 gestures keys
#define KRedProgressBar           @"YTFreedomRedProgressBar"
#define KNoRelatedVideos          @"YTFreedomNoRelatedVideos"
#define KStickyNavbar             @"YTFreedomStickyNavbar"
#define KCopyTimestampedLink      @"YTFreedomCopyTimestampedLink"
#define KRemoveDownloadMenu       @"YTFreedomRemoveDownloadMenu"
#define KRemoveWatchLaterMenu     @"YTFreedomRemoveWatchLaterMenu"
#define KRemoveSaveToPlaylistMenu @"YTFreedomRemoveSaveToPlaylistMenu"
#define KRemoveShareMenu          @"YTFreedomRemoveShareMenu"
#define KRemoveNotInterestedMenu  @"YTFreedomRemoveNotInterestedMenu"
#define KRemoveDontRecommendMenu  @"YTFreedomRemoveDontRecommendMenu"
#define KRemoveReportMenu         @"YTFreedomRemoveReportMenu"

// New-IPA UX toggles (uYouEnhanced lineage + 21.32.4 config flags)
#define KDisableRatePrompts        @"YTFreedomDisableRatePrompts"
#define KHideHUDMessages           @"YTFreedomHideHUDMessages"
#define KHidePlayerHeatmap         @"YTFreedomHidePlayerHeatmap"
#define KShortsPlaybackSpeed       @"YTFreedomShortsPlaybackSpeed"
#define KMuteButtonPlayer          @"YTFreedomMuteButtonPlayer"
#define KInlineShortsPlayback      @"YTFreedomInlineShortsPlayback"
#define KChapterSeek               @"YTFreedomChapterSeek"

// Best-UX batch (restore removed gestures / reveal native settings)
#define KPinchToFullscreen         @"YTFreedomPinchToFullscreen"
#define KTapToSeek                 @"YTFreedomTapToSeek"
#define KReduceOverlays            @"YTFreedomReducePlayerOverlays"
#define KHQAAudio                  @"YTFreedomHighQualityAudio"
#define KAnimatedPreviews          @"YTFreedomAnimatedPreviews"
#define KDisablePullToFull         @"YTFreedomDisablePullToFullscreen"

#define IS_ENABLED(key)   [[NSUserDefaults standardUserDefaults] boolForKey:(key)]
#define INTFORVAL(key)    (int)[[NSUserDefaults standardUserDefaults] integerForKey:(key)]
#define SET_BOOL(key, v)  [[NSUserDefaults standardUserDefaults] setBool:(v) forKey:(key)]
#define SET_INT(key, v)   [[NSUserDefaults standardUserDefaults] setInteger:(v) forKey:(key)]

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------
static inline os_log_t ytfLog(void) {
    static os_log_t log;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        log = os_log_create("com.nandan.ytfreedom", "hook");
    });
    return log;
}

// ---------------------------------------------------------------------------
// Hook plumbing — replace an IMP with a block IMP, return the original IMP.
// No-op (NULL) when the class/method is absent, so hooks are safe against
// class drift across app versions.
// ---------------------------------------------------------------------------
static inline IMP ytfHookInstance(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) {
        os_log(ytfLog(), "YTFreedom: inst %s not found on %s", sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel, imp_implementationWithBlock(block), method_getTypeEncoding(m));
    os_log(ytfLog(), "YTFreedom: hooked -[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

static inline IMP ytfHookClass(Class cls, SEL sel, id block) {
    if (!cls) return NULL;
    Method m = class_getClassMethod(cls, sel);
    if (!m) {
        os_log(ytfLog(), "YTFreedom: class %s not found on %s", sel_getName(sel), class_getName(cls));
        return NULL;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(object_getClass(cls), sel, imp_implementationWithBlock(block),
                        method_getTypeEncoding(m));
    os_log(ytfLog(), "YTFreedom: hooked +[%s %s]", class_getName(cls), sel_getName(sel));
    return orig;
}

// logos' %new: add a method that doesn't exist yet. encoding e.g. "@@:" or "B@:".
static inline void ytfAddInstanceMethod(Class cls, SEL sel, id block, const char *encoding) {
    if (!cls) return;
    if (!class_getInstanceMethod(cls, sel)) {
        class_addMethod(cls, sel, imp_implementationWithBlock(block), encoding);
        os_log(ytfLog(), "YTFreedom: added -[%s %s]", class_getName(cls), sel_getName(sel));
    }
}

// Hook a YTColdConfig/YTHotConfig BOOL getter; returns the override value
// when the toggle is on, else chains to the original (server/A-B) value.
static inline void ytfHookConfigBool(Class cls, SEL sel, BOOL (^override)(void)) {
    if (!cls) return;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) {
        os_log(ytfLog(), "YTFreedom: config flag %s not found on %s",
               sel_getName(sel), class_getName(cls));
        return;
    }
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel, imp_implementationWithBlock(^BOOL(id self) {
        return override() ? YES : ((BOOL(*)(id, SEL))orig)(self, sel);
    }), method_getTypeEncoding(m));
}

// ---------------------------------------------------------------------------
// Informal protocols so we can call YouTube's settings-UI classes with
// compile-time syntax while dispatching to the real (untyped) methods.
// ---------------------------------------------------------------------------
@protocol YTFreedomSettingsItemHooks <NSObject>
@property (nonatomic) BOOL on;
@property (nonatomic) BOOL hasSwitch;
@property (nonatomic, strong) id settingIcon;
@property (nonatomic) long long settingItemId;
@property (nonatomic, copy) id switchBlock;
@property (nonatomic, copy) id selectBlock;
@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NSString *titleDescription;
@end

@protocol YTFreedomIconHooks <NSObject>
@property (nonatomic) int iconType;
@end

@protocol YTFreedomAlertHooks <NSObject>
@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NSString *subtitle;
- (void)show;
@end

// ---------------------------------------------------------------------------
// Shared cross-file helpers. Exactly ONE hook per method is installed across
// the whole dylib, so features that share a hook point (ads + element
// hiding on _ASDisplayView, ad + feed section filtering on
// YTInnerTubeCollectionViewController, ad + paid overlays on
// YTMainAppVideoPlayerOverlayViewController) funnel through these.
// ---------------------------------------------------------------------------
NSArray *ytfFilterAdSections(NSArray *sections);          // AdBlock.m
NSArray *ytfFilterFeedSections(NSArray *sections);        // FeedShorts.m
void ytfConfigureASDisplayView(void);                     // FeedShorts.m (owns the hook)
void ytfConfigureCollectionView(void);                    // FeedShorts.m (owns the hook)
void ytfConfigurePlayerOverlayInsertion(void);            // PlayerFeatures.m (owns the hook)

// ---------------------------------------------------------------------------
// Area init functions (each in its own translation unit; called by the
// constructor in YTFreedom.m).
// ---------------------------------------------------------------------------
void YTFreedomSignInFixInit(void);
void YTFreedomAdBlockInit(void);
void YTFreedomSettingsUIInit(void);
void YTFreedomPlayerInit(void);
void YTFreedomPlayerGesturesInit(void);
void YTFreedomNavbarTabbarInit(void);
void YTFreedomFeedShortsInit(void);
void YTFreedomMiscInit(void);
void YTFreedomAppearanceInit(void);

#endif
