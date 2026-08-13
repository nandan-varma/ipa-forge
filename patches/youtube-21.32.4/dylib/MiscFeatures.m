// MiscFeatures.m — background playback (G7) and miscellaneous toggles (G12),
// ported from YouMod's Others.x. All hooks verified present in 21.32.4.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

@protocol YTFreedomMiscHooks <NSObject>
@optional
- (BOOL)isPlayableInBackground;
- (BOOL)playableInBackground;
- (BOOL)isPiPSupported;
- (BOOL)isPictureInPictureAllowed;
- (void)switchToPictureInPicture;
- (BOOL)shouldShowYouTherePrompt;
- (void)showYouTherePrompt;
- (BOOL)shouldShowServiceItemRenderer:(id)renderer;
- (id)icon;
- (int)iconType;
@end

// --- G7: background playback + Shorts PiP -----------------------------------

static void fixBackgroundPlayback(void) {
    if (IS_ENABLED(KBackgroundPlayback)) {
        static IMP orig_isPlayableInBackgroundStatus;
        orig_isPlayableInBackgroundStatus = ytfHookInstance(
            NSClassFromString(@"YTIPlayabilityStatus"),
            @selector(isPlayableInBackground),
            ^BOOL(id self) { return YES; });
        (void)orig_isPlayableInBackgroundStatus;

        static IMP orig_isPlayableInBackgroundData;
        orig_isPlayableInBackgroundData = ytfHookInstance(
            NSClassFromString(@"YTPlaybackData"),
            @selector(isPlayableInBackground),
            ^BOOL(id self) { return YES; });
        (void)orig_isPlayableInBackgroundData;

        static IMP orig_playableInBackgroundML;
        orig_playableInBackgroundML = ytfHookInstance(NSClassFromString(@"MLVideo"),
            @selector(playableInBackground),
            ^BOOL(id self) { return YES; });
        (void)orig_playableInBackgroundML;

        ytfAddInstanceMethod(NSClassFromString(@"YTIBackgroundOfflineSettingCategoryEntryRenderer"),
                             sel_registerName("isBackgroundEnabled"),
                             ^BOOL(id self) { return YES; }, "B@:");
    }

    if (IS_ENABLED(KDisablesShortsPiP)) {
        static IMP orig_reelsPiP;
        orig_reelsPiP = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
            @selector(shortsPlayerGlobalConfigEnableReelsPictureInPicture),
            ^BOOL(id self) { return NO; });
        (void)orig_reelsPiP;
        static IMP orig_reelsPiPIos;
        orig_reelsPiPIos = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
            @selector(shortsPlayerGlobalConfigEnableReelsPictureInPictureIos),
            ^BOOL(id self) { return NO; });
        (void)orig_reelsPiPIos;
        static IMP orig_reelsPiPAllowed;
        orig_reelsPiPAllowed = ytfHookInstance(NSClassFromString(@"YTHotConfig"),
            @selector(shortsPlayerGlobalConfigEnableReelsPictureInPictureAllowedFromPlayer),
            ^BOOL(id self) { return NO; });
        (void)orig_reelsPiPAllowed;

        static IMP orig_isPiPSupported;
        orig_isPiPSupported = ytfHookInstance(NSClassFromString(@"YTReelModel"),
            @selector(isPiPSupported),
            ^BOOL(id self) { return NO; });
        (void)orig_isPiPSupported;
        static IMP orig_isPictureInPictureAllowed;
        orig_isPictureInPictureAllowed = ytfHookInstance(
            NSClassFromString(@"YTReelPlayerViewController"),
            @selector(isPictureInPictureAllowed),
            ^BOOL(id self) { return NO; });
        (void)orig_isPictureInPictureAllowed;
        static IMP orig_switchToPiP;
        orig_switchToPiP = ytfHookInstance(NSClassFromString(@"YTReelWatchRootViewController"),
            @selector(switchToPictureInPicture),
            ^void(id self) {});
        (void)orig_switchToPiP;
    }
}

// --- G12: miscellaneous ------------------------------------------------------

static void fixMisc(void) {
    // Block upgrade dialogs.
    if (IS_ENABLED(KBlockUpgradeDialogs)) {
        static IMP orig_shouldBlockUpgrade;
        orig_shouldBlockUpgrade = ytfHookInstance(NSClassFromString(@"YTGlobalConfig"),
            @selector(shouldBlockUpgradeDialog), ^BOOL(id self) { return YES; });
        (void)orig_shouldBlockUpgrade;
        static IMP orig_shouldShowUpgradeDialog;
        orig_shouldShowUpgradeDialog = ytfHookInstance(NSClassFromString(@"YTGlobalConfig"),
            @selector(shouldShowUpgradeDialog), ^BOOL(id self) { return NO; });
        (void)orig_shouldShowUpgradeDialog;
        static IMP orig_shouldShowUpgrade;
        orig_shouldShowUpgrade = ytfHookInstance(NSClassFromString(@"YTGlobalConfig"),
            @selector(shouldShowUpgrade), ^BOOL(id self) { return NO; });
        (void)orig_shouldShowUpgrade;
        static IMP orig_shouldForceUpgrade;
        orig_shouldForceUpgrade = ytfHookInstance(NSClassFromString(@"YTGlobalConfig"),
            @selector(shouldForceUpgrade), ^BOOL(id self) { return NO; });
        (void)orig_shouldForceUpgrade;
    }

    // "Are you there?" dialog.
    if (IS_ENABLED(KHideAreYouThereDialog)) {
        static IMP orig_enableYouthereCommands;
        orig_enableYouthereCommands = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
            @selector(enableYouthereCommandsOnIos), ^BOOL(id self) { return NO; });
        (void)orig_enableYouthereCommands;

        NSArray *youThereClasses = @[
            NSClassFromString(@"YTYouThereController"),
            NSClassFromString(@"YTYouThereControllerImpl"),
        ];
        for (Class cls in youThereClasses) {
            if (!cls) continue;
            Method mShould = class_getInstanceMethod(cls, sel_registerName("shouldShowYouTherePrompt"));
            if (mShould) {
                IMP origShould = method_getImplementation(mShould);
                class_replaceMethod(cls, sel_registerName("shouldShowYouTherePrompt"),
                    imp_implementationWithBlock(^BOOL(id self) { return NO; }),
                    method_getTypeEncoding(mShould));
                (void)origShould;
            }
            Method mShow = class_getInstanceMethod(cls, sel_registerName("showYouTherePrompt"));
            if (mShow) {
                class_replaceMethod(cls, sel_registerName("showYouTherePrompt"),
                    imp_implementationWithBlock(^void(id self) {}), method_getTypeEncoding(mShow));
            }
        }
    }

    // Disable snackbar (HUD messages).
    if (IS_ENABLED(KDisablesSnackBar)) {
        static IMP orig_showMessage;
        orig_showMessage = ytfHookInstance(NSClassFromString(@"GOOHUDManagerInternal"),
            @selector(showMessageMainThread:), ^void(id self, id message) {});
        (void)orig_showMessage;
        static IMP orig_activateOverlay;
        orig_activateOverlay = ytfHookInstance(NSClassFromString(@"GOOHUDManagerInternal"),
            @selector(activateOverlay:), ^void(id self, id overlay) {});
        (void)orig_activateOverlay;
        static IMP orig_displayHUD;
        orig_displayHUD = ytfHookInstance(NSClassFromString(@"GOOHUDManagerInternal"),
            @selector(displayHUDViewForMessage:), ^void(id self, id message) {});
        (void)orig_displayHUD;
    }

    // Hide startup animations.
    static IMP orig_startupAnimation;
    orig_startupAnimation = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
        @selector(mainAppCoreClientIosEnableStartupAnimation),
        ^BOOL(id self) {
            return IS_ENABLED(KHideStartupAni) ? NO
                : ((BOOL(*)(id, SEL))orig_startupAnimation)(
                    self, @selector(mainAppCoreClientIosEnableStartupAnimation));
        });
    (void)orig_startupAnimation;

    // Disable the new floating miniplayer.
    static IMP orig_floatingMiniplayer;
    orig_floatingMiniplayer = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
        @selector(enableIosFloatingMiniplayer),
        ^BOOL(id self) {
            return IS_ENABLED(KDisablesNewMiniPlayer) ? NO
                : ((BOOL(*)(id, SEL))orig_floatingMiniplayer)(
                    self, @selector(enableIosFloatingMiniplayer));
        });
    (void)orig_floatingMiniplayer;

    // Hide "Play next in queue" menu item (icon type 251).
    if (IS_ENABLED(KHidePlayInNextQueue)) {
        NSArray *visibilityClasses = @[
            NSClassFromString(@"YTMenuItemVisibilityHandler"),
            NSClassFromString(@"YTMenuItemVisibilityHandlerImpl"),
        ];
        for (Class cls in visibilityClasses) {
            if (!cls) continue;
            Method m = class_getInstanceMethod(cls, sel_registerName("shouldShowServiceItemRenderer:"));
            if (!m) continue;
            IMP orig = method_getImplementation(m);
            class_replaceMethod(cls, sel_registerName("shouldShowServiceItemRenderer:"),
                imp_implementationWithBlock(^BOOL(id self, id renderer) {
                    id<YTFreedomMiscHooks> rendererHooks = renderer;
                    id icon = [rendererHooks respondsToSelector:@selector(icon)] ? [rendererHooks icon] : nil;
                    id<YTFreedomMiscHooks> iconHooks = icon;
                    if ([iconHooks respondsToSelector:@selector(iconType)] && [iconHooks iconType] == 251)
                        return NO;
                    return ((BOOL(*)(id, SEL, id))orig)(self, sel_registerName("shouldShowServiceItemRenderer:"), renderer);
                }), method_getTypeEncoding(m));
        }
    }

    // Silent like/dislike vote.
    if (IS_ENABLED(KHideLikeDislikeVotes)) {
        static Class likeCls, dislikeCls, removeLikeCls;
        static dispatch_once_t once;
        dispatch_once(&once, ^{
            likeCls = NSClassFromString(@"YTILikeResponse");
            dislikeCls = NSClassFromString(@"YTIDislikeResponse");
            removeLikeCls = NSClassFromString(@"YTIRemoveLikeResponse");
        });
        static IMP orig_initWithResponse;
        orig_initWithResponse = ytfHookInstance(
            NSClassFromString(@"YTInnerTubeResponseWrapper"),
            @selector(initWithResponse:cacheContext:requestStatistics:mutableSharedData:),
            ^id(id self, id response, id cacheContext, id stats, id sharedData) {
                if ([response isKindOfClass:likeCls]
                    || [response isKindOfClass:dislikeCls]
                    || [response isKindOfClass:removeLikeCls])
                    return nil;
                return ((id(*)(id, SEL, id, id, id, id))orig_initWithResponse)(
                    self, @selector(initWithResponse:cacheContext:requestStatistics:mutableSharedData:),
                    response, cacheContext, stats, sharedData);
            });
        (void)orig_initWithResponse;
    }
}

void YTFreedomMiscInit(void) {
    fixBackgroundPlayback();
    fixMisc();
}
