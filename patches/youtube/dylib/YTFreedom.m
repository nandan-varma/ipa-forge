// YTFreedom.m — dylib entry point. Registers defaults and dispatches to each
// feature area's init function. Loaded via a plain LC_LOAD_DYLIB; the
// constructor runs after the ObjC runtime has mapped all images, so
// NSClassFromString works for every app class here.
//
// Defaults come from the feature catalog (YTFFeatures.m) — the single source
// of truth. Do not add ad-hoc defaults here.

#import "YTFreedom.h"

__attribute__((constructor))
static void YTFreedomInit(void) {
    NSMutableDictionary *defaults = [NSMutableDictionary dictionary];
    for (YTFFeatureSpec *spec in ytfFeatureSpecs()) {
        if (spec.kind == YTFFeatureChoices)
            defaults[spec.key] = @(spec.defaultValue);
        else
            defaults[spec.key] = @(spec.defaultValue ? YES : NO);
    }
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
