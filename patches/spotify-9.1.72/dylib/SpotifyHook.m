// SpotifyHook.m — entry point. Runs after the ObjC runtime has mapped all
// images, so NSClassFromString works for every app/framework class. Each
// feature init is isolated in @try: a failure in one logs and degrades
// gracefully — the app must never crash because of the mod.
#import "SpotifyHook.h"

static void safeInit(const char *name, void (^block)(void)) {
    @try {
        block();
        os_log(spotLog(), "SpotifyMod: %s ready", name);
    } @catch (NSException *e) {
        os_log(spotLog(), "SpotifyMod: %s failed: %@", name, e);
    }
}

__attribute__((constructor))
static void SpotifyModInit(void) {
    os_log(spotLog(), "SpotifyMod init");
    safeInit("sideload", ^{ SpotifySideloadFixInit(); });
    safeInit("session-protection", ^{ SpotifySessionProtectionInit(); });
    safeInit("premium", ^{ SpotifyPremiumPatchInit(); });
    os_log(spotLog(), "SpotifyMod init complete");
}
