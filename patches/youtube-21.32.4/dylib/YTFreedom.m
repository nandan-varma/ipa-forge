// YTFreedom.m — dylib entry point. Registers defaults and dispatches to each
// feature area's init function. Loaded via a plain LC_LOAD_DYLIB; the
// constructor runs after the ObjC runtime has mapped all images, so
// NSClassFromString works for every app class here.

#import "YTFreedom.h"

__attribute__((constructor))
static void YTFreedomInit(void) {
    NSDictionary *defaults = @{
        KBackgroundPlayback: @YES,
        KAutoClearCache: @YES,
        KPremiumLogo: @YES,
        KHideCreateButton: @YES,
        KHideCastButtonNav: @YES,
        KHideCastButtonPlayer: @YES,
        KOldQualityPicker: @YES,
        KDownloadManager: @YES,
        KDownloadSaveToPhotos: @YES,
        KGestureActivationArea: @(1),
        KLeftSideGesture: @(1),
        KRightSideGesture: @(2),
        KGestureHUDSize: @(1),
        KGestureHUDPosition: @(0),
        KDefaultTab: @(0),
        KDisableRatePrompts: @YES,
        KPinchToFullscreen: @YES,
        KReduceOverlays: @YES,
        KHQAAudio: @YES,
    };
    [[NSUserDefaults standardUserDefaults] registerDefaults:defaults];

    YTFreedomSignInFixInit();
    YTFreedomAdBlockInit();
    YTFreedomSettingsUIInit();
    YTFreedomPlayerInit();
    YTFreedomPlayerGesturesInit();
    YTFreedomNavbarTabbarInit();
    YTFreedomFeedShortsInit();
    YTFreedomMiscInit();
    YTFreedomAppearanceInit();

    os_log(ytfLog(), "YTFreedom v%@ init complete", YTFREEDOM_VERSION);
}
