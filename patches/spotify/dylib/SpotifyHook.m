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
    [[NSUserDefaults standardUserDefaults] registerDefaults:@{
        kSMPremium: @YES, kSMAdBlock: @YES, kSMSession: @YES, kSMAppGroup: @YES,
    }];
    safeInit("sideload", ^{ SpotifySideloadFixInit(); });
    safeInit("session-protection", ^{ SpotifySessionProtectionInit(); });
    safeInit("premium", ^{ SpotifyPremiumPatchInit(); });
    safeInit("adblock", ^{ SpotifyAdBlockInit(); });
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
