// SpotifyHook.m — entry point.
//
// v4: the constructor stays INERT. All hook installation is deferred to the
// main run loop (after launch), when every app/framework image is loaded and
// the runtime is fully up — the same late-loading model substrate uses, and
// the load model proven by community Spotify mods (weak-LC).
// Loading the dylib can therefore never crash the app, and a hook failure
// logs and degrades instead.
#import "SpotifyHook.h"

static void safeInit(const char *name, void (^block)(void)) {
    @try {
        block();
        os_log(spotLog(), "SpotifyMod: %s ready", name);
    } @catch (NSException *e) {
        os_log(spotLog(), "SpotifyMod: %s failed: %@", name, e);
    }
}

static void installAll(void) {
    os_log(spotLog(), "SpotifyMod installing hooks (post-launch)");
    // Defaults come from the feature catalog (SpotifyFeatures.m — the single
    // source of truth), never hard-coded here.
    NSMutableDictionary *defaults = [NSMutableDictionary dictionary];
    for (SMFeatureSpec *spec in smFeatureSpecs()) {
        if (spec.kind == SMFeatureSwitch) defaults[spec.key] = @(spec.defaultValue);
        else if (spec.kind == SMFeatureChoice) defaults[spec.key] = @(spec.choiceDefault);
    }
    [[NSUserDefaults standardUserDefaults] registerDefaults:defaults];
    safeInit("sideload", ^{ SpotifySideloadFixInit(); });
    safeInit("session-protection", ^{ SpotifySessionProtectionInit(); });
    safeInit("premium", ^{ SpotifyPremiumPatchInit(); });
    safeInit("adblock", ^{ SpotifyAdBlockInit(); });
    safeInit("tabbar", ^{ SpotifyTabBarFixInit(); });
    safeInit("settings", ^{ SpotifySettingsInit(); });
    os_log(spotLog(), "SpotifyMod install complete");
}

__attribute__((constructor))
static void SpotifyModInit(void) {
    os_log(spotLog(), "SpotifyMod loaded (inert)");
    dispatch_async(dispatch_get_main_queue(), ^{
        installAll();
    });
}
