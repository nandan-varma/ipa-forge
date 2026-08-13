// PlayerFeatures.m — player toggles (ROADMAP G1–G5), ported from YouMod's
// Player.x (which itself adapts YouTube-X / YTClassicVideoQuality / YouSpeed
// / YTLitePlus). All hook classes and selectors verified present in the
// 21.32.4 binary (yt_inventory.py + strings); the old-quality and speed
// groups are consolidated into a single YTMenuController hook so both can
// be active at once (YouMod's %group split would collide).

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

// Runtime-called selectors on YouTube classes not in any SDK header.
@protocol YTFreedomMenuHooks <NSObject>
@optional
- (id)elementRenderer;
- (id)compatibilityOptions;
- (id)menuItemIdentifier;
- (id)button;
- (id)handler;
- (void)setHandler:(id)handler;
- (void)didPressVarispeed:(id)view;
- (void)didPressVideoQuality:(id)view;
- (id)messageForFieldNumber:(int)fieldNumber;
- (id)initWithTitle:(NSString *)title rate:(float)rate;
- (void)setActiveCaptionTrack:(id)track source:(int)source;
- (void)showFullScreen;
- (void)confirmAlertDidPressConfirm;
- (NSString *)overlayIdentifier;
- (void)setShouldDisplayTimeRemaining:(BOOL)value;
- (id)initWithServiceRegistryScope:(id)scope parentResponder:(id)responder;
- (id)addRestrictedFormats:(id)formats;
- (void)setPaused:(BOOL)paused;
- (double)mediaTime;
- (NSString *)videoID;
- (void)setVisibleSections:(NSInteger)sections;
- (id)quietProgressBarColor;
- (void)setRelatedVideosVisible:(BOOL)visible;
- (void)setFrame:(CGRect)frame;
- (UILabel *)titleLabel;
- (BOOL)stickyNavHeaderEnabled;
- (void)setStickyNavHeaderEnabled:(BOOL)enabled;
@end

// Forward declaration for the option-builder used by the varispeed hooks.
static void replaceSpeedOptions(id controller);

// --- G1: player bar ---------------------------------------------------------

static void fixPlayerBar(void) {
    static IMP orig_setAutoplayRenderer;
    orig_setAutoplayRenderer = ytfHookInstance(
        NSClassFromString(@"YTMainAppControlsOverlayView"),
        @selector(setAutoplaySwitchButtonRenderer:),
        ^void(id self, id renderer) {
            if (!IS_ENABLED(KHideAutoPlayToggle))
                ((void(*)(id, SEL, id))orig_setAutoplayRenderer)(
                    self, @selector(setAutoplaySwitchButtonRenderer:), renderer);
        });
    (void)orig_setAutoplayRenderer;

    static IMP orig_setCaptionsAvailable;
    orig_setCaptionsAvailable = ytfHookInstance(
        NSClassFromString(@"YTMainAppControlsOverlayView"),
        @selector(setClosedCaptionsOrSubtitlesButtonAvailable:),
        ^void(id self, BOOL available) {
            if (!IS_ENABLED(KHideCaptionsButton))
                ((void(*)(id, SEL, BOOL))orig_setCaptionsAvailable)(
                    self, @selector(setClosedCaptionsOrSubtitlesButtonAvailable:), available);
        });
    (void)orig_setCaptionsAvailable;

    static IMP orig_setPrevHidden;
    orig_setPrevHidden = ytfHookInstance(NSClassFromString(@"YTMainAppControlsOverlayView"),
        @selector(setPreviousButtonHidden:),
        ^void(id self, BOOL hidden) {
            ((void(*)(id, SEL, BOOL))orig_setPrevHidden)(
                self, @selector(setPreviousButtonHidden:), IS_ENABLED(KHidePrevButton) ? YES : hidden);
        });
    (void)orig_setPrevHidden;

    static IMP orig_setNextHidden;
    orig_setNextHidden = ytfHookInstance(NSClassFromString(@"YTMainAppControlsOverlayView"),
        @selector(setNextButtonHidden:),
        ^void(id self, BOOL hidden) {
            ((void(*)(id, SEL, BOOL))orig_setNextHidden)(
                self, @selector(setNextButtonHidden:), IS_ENABLED(KHideNextButton) ? YES : hidden);
        });
    (void)orig_setNextHidden;

    static IMP orig_titleViewHidden;
    orig_titleViewHidden = ytfHookInstance(NSClassFromString(@"YTMainAppControlsOverlayView"),
        @selector(titleViewHidden),
        ^BOOL(id self) {
            return IS_ENABLED(KHideFullvidTitle) ? YES
                : ((BOOL(*)(id, SEL))orig_titleViewHidden)(self, @selector(titleViewHidden));
        });
    (void)orig_titleViewHidden;

    // Autoplay master switch off.
    static IMP orig_isAutoplayEnabled;
    orig_isAutoplayEnabled = ytfHookInstance(NSClassFromString(@"YTSettings"),
        @selector(isAutoplayEnabled),
        ^BOOL(id self) {
            return IS_ENABLED(KHideAutoPlayToggle) ? NO
                : ((BOOL(*)(id, SEL))orig_isAutoplayEnabled)(self, @selector(isAutoplayEnabled));
        });
    (void)orig_isAutoplayEnabled;
    static IMP orig_isAutoplayEnabledImpl;
    orig_isAutoplayEnabledImpl = ytfHookInstance(NSClassFromString(@"YTSettingsImpl"),
        @selector(isAutoplayEnabled),
        ^BOOL(id self) {
            return IS_ENABLED(KHideAutoPlayToggle) ? NO
                : ((BOOL(*)(id, SEL))orig_isAutoplayEnabledImpl)(self, @selector(isAutoplayEnabled));
        });
    (void)orig_isAutoplayEnabledImpl;

    // Remaining-time display.
    static IMP orig_setShouldDisplayTimeRemaining;
    orig_setShouldDisplayTimeRemaining = ytfHookInstance(
        NSClassFromString(@"YTInlinePlayerBarContainerView"),
        @selector(setShouldDisplayTimeRemaining:),
        ^void(id self, BOOL value) {
            BOOL force = IS_ENABLED(KDisablesShowRemaining) ? NO
                : (IS_ENABLED(KAlwaysShowRemaining) ? YES : value);
            ((void(*)(id, SEL, BOOL))orig_setShouldDisplayTimeRemaining)(
                self, @selector(setShouldDisplayTimeRemaining:), force);
        });
    (void)orig_setShouldDisplayTimeRemaining;

    static IMP orig_setActiveVideo;
    orig_setActiveVideo = ytfHookInstance(NSClassFromString(@"YTPlayerBarController"),
        @selector(setActiveSingleVideo:),
        ^void(id self, id video) {
            ((void(*)(id, SEL, id))orig_setActiveVideo)(self, @selector(setActiveSingleVideo:), video);
            if (IS_ENABLED(KAlwaysShowRemaining) && !IS_ENABLED(KDisablesShowRemaining)) {
                id playerBar = [self valueForKey:@"playerBar"];
                id<YTFreedomMenuHooks> barHooks = playerBar;
                if ([barHooks respondsToSelector:@selector(setShouldDisplayTimeRemaining:)])
                    [barHooks setShouldDisplayTimeRemaining:YES];
            }
        });
    (void)orig_setActiveVideo;

    // Always-visible seekbar.
    static IMP orig_setPlayerBarAlpha;
    orig_setPlayerBarAlpha = ytfHookInstance(NSClassFromString(@"YTInlinePlayerBarContainerView"),
        @selector(setPlayerBarAlpha:),
        ^void(id self, CGFloat alpha) {
            ((void(*)(id, SEL, CGFloat))orig_setPlayerBarAlpha)(
                self, @selector(setPlayerBarAlpha:), IS_ENABLED(KAlwaysShowSeekbar) ? 1.0 : alpha);
        });
    (void)orig_setPlayerBarAlpha;

    // Replace prev/next paddles with rewind/ffw (VODs).
    static IMP orig_replaceNextPaddle;
    orig_replaceNextPaddle = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
        @selector(replaceNextPaddleWithFastForwardButtonForSingletonVods),
        ^BOOL(id self) {
            return IS_ENABLED(KReplacePrevNextButtons) ? YES
                : ((BOOL(*)(id, SEL))orig_replaceNextPaddle)(
                    self, @selector(replaceNextPaddleWithFastForwardButtonForSingletonVods));
        });
    (void)orig_replaceNextPaddle;
    static IMP orig_replacePrevPaddle;
    orig_replacePrevPaddle = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
        @selector(replacePreviousPaddleWithRewindButtonForSingletonVods),
        ^BOOL(id self) {
            return IS_ENABLED(KReplacePrevNextButtons) ? YES
                : ((BOOL(*)(id, SEL))orig_replacePrevPaddle)(
                    self, @selector(replacePreviousPaddleWithRewindButtonForSingletonVods));
        });
    (void)orig_replacePrevPaddle;
}

// --- G2: overlay / UI -------------------------------------------------------

static void fixOverlayUI(void) {
    static IMP orig_setBackgroundVisible;
    orig_setBackgroundVisible = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayView"),
        @selector(setBackgroundVisible:isGradientBackground:),
        ^void(id self, BOOL visible, BOOL gradient) {
            ((void(*)(id, SEL, BOOL, BOOL))orig_setBackgroundVisible)(
                self, @selector(setBackgroundVisible:isGradientBackground:),
                IS_ENABLED(KRemoveDarkOverlay) ? NO : visible, gradient);
        });
    (void)orig_setBackgroundVisible;

    static IMP orig_isWatermarkEnabled;
    orig_isWatermarkEnabled = ytfHookInstance(NSClassFromString(@"YTMainAppVideoPlayerOverlayView"),
        @selector(isWatermarkEnabled),
        ^BOOL(id self) {
            return IS_ENABLED(KHideWaterMark) ? NO
                : ((BOOL(*)(id, SEL))orig_isWatermarkEnabled)(self, @selector(isWatermarkEnabled));
        });
    (void)orig_isWatermarkEnabled;
    static IMP orig_setWatermarkEnabled;
    orig_setWatermarkEnabled = ytfHookInstance(NSClassFromString(@"YTMainAppVideoPlayerOverlayView"),
        @selector(setWatermarkEnabled:),
        ^void(id self, BOOL enabled) {
            ((void(*)(id, SEL, BOOL))orig_setWatermarkEnabled)(
                self, @selector(setWatermarkEnabled:), IS_ENABLED(KHideWaterMark) ? NO : enabled);
        });
    (void)orig_setWatermarkEnabled;

    static IMP orig_isFullscreenActionsVisible;
    orig_isFullscreenActionsVisible = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayView"),
        @selector(isFullscreenActionsVisible),
        ^BOOL(id self) {
            return IS_ENABLED(KHideFullAction) ? NO
                : ((BOOL(*)(id, SEL))orig_isFullscreenActionsVisible)(
                    self, @selector(isFullscreenActionsVisible));
        });
    (void)orig_isFullscreenActionsVisible;

    // Hide cast button in the player.
    static IMP orig_overlayLayout;
    orig_overlayLayout = ytfHookInstance(NSClassFromString(@"YTMainAppVideoPlayerOverlayView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_overlayLayout)(self, @selector(layoutSubviews));
            if (IS_ENABLED(KHideCastButtonPlayer)) {
                id routeButton = [self valueForKey:@"playbackRouteButton"];
                if ([routeButton respondsToSelector:@selector(setHidden:)])
                    [routeButton setHidden:YES];
            }
        });
    (void)orig_overlayLayout;

    // Endscreens.
    static IMP orig_setEndscreenHidden;
    orig_setEndscreenHidden = ytfHookInstance(NSClassFromString(@"YTCreatorEndscreenView"),
        @selector(setHidden:),
        ^void(id self, BOOL hidden) {
            ((void(*)(id, SEL, BOOL))orig_setEndscreenHidden)(
                self, @selector(setHidden:), IS_ENABLED(KHideEndScreenCards) ? YES : hidden);
        });
    (void)orig_setEndscreenHidden;
    static IMP orig_setHoverHidden;
    orig_setHoverHidden = ytfHookInstance(NSClassFromString(@"YTCreatorEndscreenView"),
        @selector(setHoverCardHidden:),
        ^void(id self, BOOL hidden) {
            ((void(*)(id, SEL, BOOL))orig_setHoverHidden)(
                self, @selector(setHoverCardHidden:), IS_ENABLED(KHideEndScreenCards) ? YES : hidden);
        });
    (void)orig_setHoverHidden;
    static IMP orig_setHoverRenderer;
    orig_setHoverRenderer = ytfHookInstance(NSClassFromString(@"YTCreatorEndscreenView"),
        @selector(setHoverCardRenderer:),
        ^void(id self, id renderer) {
            if (!IS_ENABLED(KHideEndScreenCards))
                ((void(*)(id, SEL, id))orig_setHoverRenderer)(
                    self, @selector(setHoverCardRenderer:), renderer);
        });
    (void)orig_setHoverRenderer;

    static IMP orig_showEndscreen;
    orig_showEndscreen = ytfHookInstance(NSClassFromString(@"YTAutonavEndscreenController"),
        @selector(showEndscreen),
        ^void(id self) {
            if (!IS_ENABLED(KHideSuggestedVideo))
                ((void(*)(id, SEL))orig_showEndscreen)(self, @selector(showEndscreen));
        });
    (void)orig_showEndscreen;
    static IMP orig_showEndscreenControls;
    orig_showEndscreenControls = ytfHookInstance(NSClassFromString(@"YTAutonavEndscreenController"),
        @selector(showEndscreenControlsInPlayerBar:),
        ^void(id self, BOOL visible) {
            ((void(*)(id, SEL, BOOL))orig_showEndscreenControls)(
                self, @selector(showEndscreenControlsInPlayerBar:),
                IS_ENABLED(KHideSuggestedVideo) ? NO : visible);
        });
    (void)orig_showEndscreenControls;

    // Fullscreen action buttons.
    static IMP orig_fullscreenActionsSize;
    orig_fullscreenActionsSize = ytfHookInstance(NSClassFromString(@"YTFullscreenActionsView"),
        @selector(sizeThatFits:),
        ^CGSize(id self, CGSize size) {
            return IS_ENABLED(KHideFullAction) ? CGSizeMake(1, 35)
                : ((CGSize(*)(id, SEL, CGSize))orig_fullscreenActionsSize)(
                    self, @selector(sizeThatFits:), size);
        });
    (void)orig_fullscreenActionsSize;

    // Ambient (cinematic) lights.
    static IMP orig_cinematicLayout;
    orig_cinematicLayout = ytfHookInstance(NSClassFromString(@"YTCinematicContainerView"),
        @selector(layoutSubviews),
        ^void(id self) {
            if (!IS_ENABLED(KRemoveAmbiant))
                ((void(*)(id, SEL))orig_cinematicLayout)(self, @selector(layoutSubviews));
        });
    (void)orig_cinematicLayout;
    static IMP orig_cinematicLoad;
    orig_cinematicLoad = ytfHookInstance(NSClassFromString(@"YTCinematicContainerView"),
        @selector(loadWithModel:),
        ^void(id self, id model) {
            if (!IS_ENABLED(KRemoveAmbiant))
                ((void(*)(id, SEL, id))orig_cinematicLoad)(self, @selector(loadWithModel:), model);
        });
    (void)orig_cinematicLoad;
    static IMP orig_cinematicInit;
    orig_cinematicInit = ytfHookInstance(NSClassFromString(@"YTCinematicContainerView"),
        @selector(initWithFrame:),
        ^id(id self, CGRect frame) {
            if (IS_ENABLED(KRemoveAmbiant)) return nil;
            return ((id(*)(id, SEL, CGRect))orig_cinematicInit)(
                self, @selector(initWithFrame:), frame);
        });
    (void)orig_cinematicInit;

    // Watermark on featured channels.
    static IMP orig_loadFeaturedChannelWatermark;
    orig_loadFeaturedChannelWatermark = ytfHookInstance(
        NSClassFromString(@"YTAnnotationsViewController"),
        @selector(loadFeaturedChannelWatermark),
        ^void(id self) {
            if (!IS_ENABLED(KHideWaterMark))
                ((void(*)(id, SEL))orig_loadFeaturedChannelWatermark)(
                    self, @selector(loadFeaturedChannelWatermark));
        });
    (void)orig_loadFeaturedChannelWatermark;

    // Skip content warnings.
    static IMP orig_showConfirmAlert;
    orig_showConfirmAlert = ytfHookInstance(
        NSClassFromString(@"YTPlayabilityResolutionUserActionUIController"),
        @selector(showConfirmAlert),
        ^void(id self) {
            if (IS_ENABLED(KHideContentWarning)) {
                id<YTFreedomMenuHooks> hooks = self;
                if ([hooks respondsToSelector:@selector(confirmAlertDidPressConfirm)])
                    [hooks confirmAlertDidPressConfirm];
                return;
            }
            ((void(*)(id, SEL))orig_showConfirmAlert)(self, @selector(showConfirmAlert));
        });
    (void)orig_showConfirmAlert;
    static IMP orig_showConfirmAlertImpl;
    orig_showConfirmAlertImpl = ytfHookInstance(
        NSClassFromString(@"YTPlayabilityResolutionUserActionUIControllerImpl"),
        @selector(showConfirmAlert),
        ^void(id self) {
            if (IS_ENABLED(KHideContentWarning)) {
                id<YTFreedomMenuHooks> hooks = self;
                if ([hooks respondsToSelector:@selector(confirmAlertDidPressConfirm)])
                    [hooks confirmAlertDidPressConfirm];
                return;
            }
            ((void(*)(id, SEL))orig_showConfirmAlertImpl)(self, @selector(showConfirmAlert));
        });
    (void)orig_showConfirmAlertImpl;
}

// --- G3: playback behavior --------------------------------------------------

static void fixPlaybackBehavior(void) {
    static IMP orig_setStartPlayback;
    orig_setStartPlayback = ytfHookInstance(NSClassFromString(@"YTPlaybackConfig"),
        @selector(setStartPlayback:),
        ^void(id self, BOOL start) {
            ((void(*)(id, SEL, BOOL))orig_setStartPlayback)(
                self, @selector(setStartPlayback:), IS_ENABLED(KStopAutoplayVideo) ? NO : start);
        });
    (void)orig_setStartPlayback;

    static IMP orig_shouldExitFullscreen;
    orig_shouldExitFullscreen = ytfHookInstance(NSClassFromString(@"YTWatchFlowController"),
        @selector(shouldExitFullScreenOnFinish),
        ^BOOL(id self) {
            return IS_ENABLED(KAutoExitFullScreen) ? YES
                : ((BOOL(*)(id, SEL))orig_shouldExitFullscreen)(self, @selector(shouldExitFullScreenOnFinish));
        });
    (void)orig_shouldExitFullscreen;

    static IMP orig_allowedOrientations;
    orig_allowedOrientations = ytfHookInstance(NSClassFromString(@"YTWatchViewController"),
        @selector(allowedFullScreenOrientations),
        ^unsigned long long(id self) {
            return IS_ENABLED(KPortFull) ? (unsigned long long)UIInterfaceOrientationMaskAllButUpsideDown
                : ((unsigned long long(*)(id, SEL))orig_allowedOrientations)(
                    self, @selector(allowedFullScreenOrientations));
        });
    (void)orig_allowedOrientations;

    // Disable hints.
    static IMP orig_areHintsDisabled;
    orig_areHintsDisabled = ytfHookInstance(NSClassFromString(@"YTSettings"),
        @selector(areHintsDisabled),
        ^BOOL(id self) {
            return IS_ENABLED(KDisableHints) ? YES
                : ((BOOL(*)(id, SEL))orig_areHintsDisabled)(self, @selector(areHintsDisabled));
        });
    (void)orig_areHintsDisabled;
    static IMP orig_setHintsDisabled;
    orig_setHintsDisabled = ytfHookInstance(NSClassFromString(@"YTSettings"),
        @selector(setHintsDisabled:),
        ^void(id self, BOOL disabled) {
            ((void(*)(id, SEL, BOOL))orig_setHintsDisabled)(
                self, @selector(setHintsDisabled:), IS_ENABLED(KDisableHints) ? YES : disabled);
        });
    (void)orig_setHintsDisabled;
    static IMP orig_areHintsDisabledImpl;
    orig_areHintsDisabledImpl = ytfHookInstance(NSClassFromString(@"YTSettingsImpl"),
        @selector(areHintsDisabled),
        ^BOOL(id self) {
            return IS_ENABLED(KDisableHints) ? YES
                : ((BOOL(*)(id, SEL))orig_areHintsDisabledImpl)(self, @selector(areHintsDisabled));
        });
    (void)orig_areHintsDisabledImpl;
    static IMP orig_setHintsDisabledImpl;
    orig_setHintsDisabledImpl = ytfHookInstance(NSClassFromString(@"YTSettingsImpl"),
        @selector(setHintsDisabled:),
        ^void(id self, BOOL disabled) {
            ((void(*)(id, SEL, BOOL))orig_setHintsDisabledImpl)(
                self, @selector(setHintsDisabled:), IS_ENABLED(KDisableHints) ? YES : disabled);
        });
    (void)orig_setHintsDisabledImpl;
    static IMP orig_areHintsDisabledUD;
    orig_areHintsDisabledUD = ytfHookInstance(NSClassFromString(@"YTUserDefaults"),
        @selector(areHintsDisabled),
        ^BOOL(id self) {
            return IS_ENABLED(KDisableHints) ? YES
                : ((BOOL(*)(id, SEL))orig_areHintsDisabledUD)(self, @selector(areHintsDisabled));
        });
    (void)orig_areHintsDisabledUD;
    static IMP orig_setHintsDisabledUD;
    orig_setHintsDisabledUD = ytfHookInstance(NSClassFromString(@"YTUserDefaults"),
        @selector(setHintsDisabled:),
        ^void(id self, BOOL disabled) {
            ((void(*)(id, SEL, BOOL))orig_setHintsDisabledUD)(
                self, @selector(setHintsDisabled:), IS_ENABLED(KDisableHints) ? YES : disabled);
        });
    (void)orig_setHintsDisabledUD;

    // Force miniplayer: %new hasMinimizedEndpoint/hasPlaybackMode -> NO.
    ytfAddInstanceMethod(NSClassFromString(@"YTIMiniplayerRenderer"),
                         sel_registerName("hasMinimizedEndpoint"),
                         ^BOOL(id self) { return NO; }, "B@:");
    ytfAddInstanceMethod(NSClassFromString(@"YTIMiniplayerRenderer"),
                         sel_registerName("hasPlaybackMode"),
                         ^BOOL(id self) { return NO; }, "B@:");

    // Disable double-tap / long-press gestures.
    static IMP orig_allowDoubleTap;
    orig_allowDoubleTap = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(allowDoubleTapToSeekGestureRecognizer),
        ^BOOL(id self) {
            return IS_ENABLED(KDisablesDoubleTap) ? NO
                : ((BOOL(*)(id, SEL))orig_allowDoubleTap)(self, @selector(allowDoubleTapToSeekGestureRecognizer));
        });
    (void)orig_allowDoubleTap;
    static IMP orig_allowLongPress;
    orig_allowLongPress = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(allowLongPressGestureRecognizerInView:),
        ^BOOL(id self, id view) {
            return IS_ENABLED(KDisablesLongHold) ? NO
                : ((BOOL(*)(id, SEL, id))orig_allowLongPress)(
                    self, @selector(allowLongPressGestureRecognizerInView:), view);
        });
    (void)orig_allowLongPress;

    // Auto-fullscreen + auto-disable captions when a video loads.
    static IMP orig_prepareToLoad;
    orig_prepareToLoad = ytfHookInstance(NSClassFromString(@"YTPlayerViewController"),
        @selector(prepareToLoadWithPlayerTransition:expectedLayout:),
        ^void(id self, id transition, id layout) {
            ((void(*)(id, SEL, id, id))orig_prepareToLoad)(
                self, @selector(prepareToLoadWithPlayerTransition:expectedLayout:), transition, layout);
            if (IS_ENABLED(KAutoFullScreen))
                [self performSelector:@selector(YTFreedomAutoFullscreen) withObject:nil afterDelay:0.75];
            if (IS_ENABLED(KDisablesCaptions))
                [self performSelector:@selector(YTFreedomTurnOffCaptions) withObject:nil afterDelay:1.0];
        });
    (void)orig_prepareToLoad;
}

// %new helpers used above (plain-runtime equivalents of YouMod's %new
// methods on YTPlayerViewController).
static void addPlayerViewControllerHelpers(void) {
    Class cls = NSClassFromString(@"YTPlayerViewController");
    if (!cls) return;

    ytfAddInstanceMethod(cls, sel_registerName("YTFreedomTurnOffCaptions"),
        ^void(id self) {
            id<YTFreedomMenuHooks> hooks = self;
            id view = [self valueForKey:@"view"];
            if ([[view superview] isKindOfClass:NSClassFromString(@"YTWatchView")]
                && [hooks respondsToSelector:@selector(setActiveCaptionTrack:source:)]) {
                [hooks setActiveCaptionTrack:nil source:0];
            }
        }, "v@:");

    ytfAddInstanceMethod(cls, sel_registerName("YTFreedomAutoFullscreen"),
        ^void(id self) {
            id watchController = [self valueForKey:@"_UIDelegate"];
            id<YTFreedomMenuHooks> hooks = watchController;
            if ([hooks respondsToSelector:@selector(showFullScreen)])
                [hooks showFullScreen];
        }, "v@:");
}

// --- G4: old quality picker -------------------------------------------------

static void fixOldQualityPicker(void) {
    ytfAddInstanceMethod(NSClassFromString(@"YTIMediaQualitySettingsHotConfig"),
                         sel_registerName("enableQuickMenuVideoQualitySettings"),
                         ^BOOL(id self) { return NO; }, "B@:");

    // Retain a redesigned controller on the original controller via an
    // associated object (logos %property equivalent).
    static const void *kRedesignedKey = &kRedesignedKey;
    static IMP orig_setUserSelectableFormats;
    orig_setUserSelectableFormats = ytfHookInstance(
        NSClassFromString(@"YTVideoQualitySwitchOriginalController"),
        @selector(setUserSelectableFormats:),
        ^void(id self, NSArray *formats) {
            id redesigned = objc_getAssociatedObject(self, kRedesignedKey);
            if (!redesigned) {
                Class rc = NSClassFromString(@"YTVideoQualitySwitchRedesignedController");
                id<YTFreedomMenuHooks> rcHooks = [rc alloc];
                if (rcHooks) {
                    redesigned = [rcHooks initWithServiceRegistryScope:nil parentResponder:nil];
                    objc_setAssociatedObject(self, kRedesignedKey, redesigned,
                                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                }
            }
            NSArray *newFormats = formats;
            if (redesigned) {
                [redesigned setValue:[self valueForKey:@"_video"] forKey:@"_video"];
                id<YTFreedomMenuHooks> rcHooks = redesigned;
                if ([rcHooks respondsToSelector:@selector(addRestrictedFormats:)])
                    newFormats = [rcHooks addRestrictedFormats:formats];
            }
            ((void(*)(id, SEL, id))orig_setUserSelectableFormats)(
                self, @selector(setUserSelectableFormats:), newFormats);
        });
    (void)orig_setUserSelectableFormats;
}

// --- G5: extra speed + consolidated menu hook -------------------------------

static const float kSpeedRates[13] = {0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 5.0, 7.5, 10.0};

// One hook for both the playback-speed and video-quality menu items
// (YouMod splits these across groups; a single hook avoids the collision).
static void fixSpeedMenu(void) {
    static IMP orig_actionsForRenderers;
    orig_actionsForRenderers = ytfHookInstance(NSClassFromString(@"YTMenuController"),
        @selector(actionsForRenderers:fromView:entry:shouldLogItems:firstResponder:),
        ^id(id self, NSMutableArray *renderers, id fromView, id entry, BOOL shouldLogItems, id firstResponder) {
            id actions = ((id(*)(id, SEL, id, id, id, BOOL, id))orig_actionsForRenderers)(
                self, @selector(actionsForRenderers:fromView:entry:shouldLogItems:firstResponder:),
                renderers, fromView, entry, shouldLogItems, firstResponder);
            if (![actions isKindOfClass:[NSArray class]]) return actions;

            BOOL wantSpeed = IS_ENABLED(KExtraSpeed);
            BOOL wantQuality = IS_ENABLED(KOldQualityPicker);
            if (!wantSpeed && !wantQuality) return actions;

            NSMutableArray *mutableActions = [actions mutableCopy];
            [renderers enumerateObjectsUsingBlock:^(id renderer, NSUInteger idx, BOOL *stop) {
                id<YTFreedomMenuHooks> hooks = renderer;
                id compat = [hooks respondsToSelector:@selector(compatibilityOptions)]
                    ? [hooks compatibilityOptions] : nil;
                if (!compat) return;
                id<YTFreedomMenuHooks> compatHooks = compat;
                id ext = [compatHooks respondsToSelector:@selector(messageForFieldNumber:)]
                    ? [compatHooks messageForFieldNumber:396644439] : nil;
                NSString *identifier = [ext respondsToSelector:@selector(menuItemIdentifier)]
                    ? [ext menuItemIdentifier] : nil;
                if (idx < mutableActions.count) {
                    id<YTFreedomMenuHooks> action = mutableActions[idx];
                    if (wantSpeed && [identifier isEqualToString:@"menu_item_playback_speed"]) {
                        [action setHandler:^{
                            if ([firstResponder respondsToSelector:@selector(didPressVarispeed:)])
                                [firstResponder didPressVarispeed:fromView];
                        }];
                        id elementView = [[(id)action valueForKey:@"button"] valueForKey:@"_elementView"];
                        [elementView setValue:@NO forKey:@"userInteractionEnabled"];
                    } else if (wantQuality && [identifier isEqualToString:@"menu_item_video_quality"]) {
                        [action setHandler:^{
                            if ([firstResponder respondsToSelector:@selector(didPressVideoQuality:)])
                                [firstResponder didPressVideoQuality:fromView];
                        }];
                        id elementView = [[(id)action valueForKey:@"button"] valueForKey:@"_elementView"];
                        [elementView setValue:@NO forKey:@"userInteractionEnabled"];
                    }
                }
            }];
            return mutableActions;
        });
    (void)orig_actionsForRenderers;

    // Extended rate options on the varispeed sheet.
    static IMP orig_varispeedInit;
    orig_varispeedInit = ytfHookInstance(NSClassFromString(@"YTVarispeedSwitchController"),
        @selector(init),
        ^id(id self) {
            self = ((id(*)(id, SEL))orig_varispeedInit)(self, @selector(init));
            replaceSpeedOptions(self);
            return self;
        });
    (void)orig_varispeedInit;
    static IMP orig_varispeedInitImpl;
    orig_varispeedInitImpl = ytfHookInstance(NSClassFromString(@"YTVarispeedSwitchControllerImpl"),
        @selector(init),
        ^id(id self) {
            self = ((id(*)(id, SEL))orig_varispeedInitImpl)(self, @selector(init));
            replaceSpeedOptions(self);
            return self;
        });
    (void)orig_varispeedInitImpl;

    // Cap raised to 10x.
    ytfAddInstanceMethod(NSClassFromString(@"YTIPlayerHotConfig"),
                         sel_registerName("maximumPlaybackRate"),
                         ^float(id self) { return 10.0f; }, "f@:");
    ytfAddInstanceMethod(NSClassFromString(@"YTIGranularVariableSpeedConfig"),
                         sel_registerName("maximumPlaybackRate"),
                         ^double(id self) { return 1000.0; }, "d@:");
}

static void replaceSpeedOptions(id controller) {
    Class optionCls = NSClassFromString(@"YTVarispeedSwitchControllerOption");
    if (!optionCls) return;
    NSMutableArray *options = [NSMutableArray array];
    for (int i = 0; i < 13; i++) {
        id<YTFreedomMenuHooks> option = [[optionCls alloc] initWithTitle:[NSString stringWithFormat:@"%.2fx", kSpeedRates[i]]
                                                                    rate:kSpeedRates[i]];
        if (option) [options addObject:option];
    }
    [controller setValue:options forKey:@"_options"];
}

// --- consolidated overlay insertion (ads + paid content) --------------------

void ytfConfigurePlayerOverlayInsertion(void) {
    static IMP orig_didInsertOverlay;
    orig_didInsertOverlay = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(playerOverlayProvider:didInsertPlayerOverlay:),
        ^void(id self, id provider, id overlay) {
            id<YTFreedomMenuHooks> overlayHooks = overlay;
            NSString *identifier = [overlayHooks respondsToSelector:@selector(overlayIdentifier)]
                ? [overlayHooks overlayIdentifier] : nil;
            if ([identifier isEqualToString:@"player_overlay_product_in_video"])
                return;  // shopping overlay — always dropped (ads)
            if ([identifier isEqualToString:@"player_overlay_paid_content"]
                && IS_ENABLED(KHidePaidPromoOverlay))
                return;
            ((void(*)(id, SEL, id, id))orig_didInsertOverlay)(
                self, @selector(playerOverlayProvider:didInsertPlayerOverlay:), provider, overlay);
        });
    (void)orig_didInsertOverlay;

    // Paid-content promo: never set on the overlay controllers.
    static IMP orig_setPaidContent;
    orig_setPaidContent = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(setPaidContentWithPlayerData:),
        ^void(id self, id data) {});
    (void)orig_setPaidContent;
    static IMP orig_setPaidContentMuted;
    orig_setPaidContentMuted = ytfHookInstance(
        NSClassFromString(@"YTInlineMutedPlaybackPlayerOverlayViewController"),
        @selector(setPaidContentWithPlayerData:),
        ^void(id self, id data) {});
    (void)orig_setPaidContentMuted;
}

// --- G18: YTLite extras -----------------------------------------------------

static void fixYTLiteExtras(void) {
    // Red progress bar (quiet/resting color).
    static IMP orig_quietProgressBarColor;
    orig_quietProgressBarColor = ytfHookInstance(
        NSClassFromString(@"YTInlinePlayerBarContainerView"),
        @selector(quietProgressBarColor),
        ^id(id self) {
            return IS_ENABLED(KRedProgressBar) ? [UIColor redColor]
                : ((id(*)(id, SEL))orig_quietProgressBarColor)(self, @selector(quietProgressBarColor));
        });
    (void)orig_quietProgressBarColor;

    // Copy timestamped link when pausing.
    static IMP orig_didPressPause;
    orig_didPressPause = ytfHookInstance(
        NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(didPressPause:),
        ^void(id self, id arg) {
            ((void(*)(id, SEL, id))orig_didPressPause)(self, @selector(didPressPause:), arg);
            if (IS_ENABLED(KCopyTimestampedLink)) {
                id<YTFreedomMenuHooks> hooks = self;
                NSInteger mediaTime = [hooks respondsToSelector:@selector(mediaTime)]
                    ? (NSInteger)[hooks mediaTime] : 0;
                NSString *videoID = [hooks respondsToSelector:@selector(videoID)]
                    ? [hooks videoID] : nil;
                if (videoID.length > 0) {
                    NSString *link = [NSString stringWithFormat:@"https://www.youtube.com/watch?v=%@&t=%lds",
                                      videoID, (long)mediaTime];
                    [UIPasteboard generalPasteboard].string = link;
                }
            }
        });
    (void)orig_didPressPause;

    // Hide related videos on watch-next results.
    static IMP orig_setVisibleSections;
    orig_setVisibleSections = ytfHookInstance(
        NSClassFromString(@"YTWatchNextResultsViewController"),
        @selector(setVisibleSections:),
        ^void(id self, NSInteger sections) {
            ((void(*)(id, SEL, NSInteger))orig_setVisibleSections)(
                self, @selector(setVisibleSections:), IS_ENABLED(KNoRelatedVideos) ? 1 : sections);
        });
    (void)orig_setVisibleSections;

    // Related videos on the endscreen.
    static IMP orig_setRelatedVideosVisible;
    orig_setRelatedVideosVisible = ytfHookInstance(
        NSClassFromString(@"YTFullscreenEngagementOverlayController"),
        @selector(setRelatedVideosVisible:),
        ^void(id self, BOOL visible) {
            ((void(*)(id, SEL, BOOL))orig_setRelatedVideosVisible)(
                self, @selector(setRelatedVideosVisible:), IS_ENABLED(KHideSuggestedVideo) ? NO : visible);
        });
    (void)orig_setRelatedVideosVisible;

    // Fit button labels (play-all / shorts) for localizations.
    static IMP orig_qtmTitleLabel;
    orig_qtmTitleLabel = ytfHookInstance(NSClassFromString(@"YTQTMButton"),
        @selector(titleLabel),
        ^id(id self) {
            UILabel *label = ((id(*)(id, SEL))orig_qtmTitleLabel)(self, @selector(titleLabel));
            if ([[(UIView *)self accessibilityIdentifier] isEqualToString:@"id.playlist.playall.button"])
                label.adjustsFontSizeToFitWidth = YES;
            return label;
        });
    (void)orig_qtmTitleLabel;
    static IMP orig_reelTitleLabel;
    orig_reelTitleLabel = ytfHookInstance(NSClassFromString(@"YTReelPlayerButton"),
        @selector(titleLabel),
        ^id(id self) {
            UILabel *label = ((id(*)(id, SEL))orig_reelTitleLabel)(self, @selector(titleLabel));
            label.adjustsFontSizeToFitWidth = YES;
            return label;
        });
    (void)orig_reelTitleLabel;

    // Playlist mini-bar minimum height (small screens).
    static IMP orig_playlistMiniBarFrame;
    orig_playlistMiniBarFrame = ytfHookInstance(NSClassFromString(@"YTPlaylistMiniBarView"),
        @selector(setFrame:),
        ^void(id self, CGRect frame) {
            if (frame.size.height < 54.0) frame.size.height = 54.0;
            ((void(*)(id, SEL, CGRect))orig_playlistMiniBarFrame)(self, @selector(setFrame:), frame);
        });
    (void)orig_playlistMiniBarFrame;
}

void YTFreedomPlayerInit(void) {
    fixPlayerBar();
    fixOverlayUI();
    fixPlaybackBehavior();
    addPlayerViewControllerHelpers();
    if (IS_ENABLED(KOldQualityPicker))
        fixOldQualityPicker();
    if (IS_ENABLED(KExtraSpeed))
        fixSpeedMenu();
    fixYTLiteExtras();
    ytfConfigurePlayerOverlayInsertion();
}
