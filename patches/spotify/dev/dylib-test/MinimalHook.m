// Minimal test dylib — does NOTHING except log when loaded. No hooks.
// Purpose: prove the injection pipeline (strip + stage + weak LC_LOAD_DYLIB)
// works on Spotify 9.1.72 before adding any feature code back.
#import <Foundation/Foundation.h>
#import <os/log.h>

__attribute__((constructor))
static void MinimalInit(void) {
    os_log(OS_LOG_DEFAULT, "SpotifyTest: minimal dylib loaded OK");
}
