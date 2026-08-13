// SpotifyHook.m — entry point. Runs after the ObjC runtime has mapped all
// images, so NSClassFromString works for every app/framework class.
#import "SpotifyHook.h"

__attribute__((constructor))
static void SpotifyModInit(void) {
    os_log(spotLog(), "SpotifyMod init");
    SpotifySideloadFixInit();
    SpotifySessionProtectionInit();
    SpotifyPremiumPatchInit();
    os_log(spotLog(), "SpotifyMod init complete");
}
