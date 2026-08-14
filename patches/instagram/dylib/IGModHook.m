// IGModHook.m — entry point.
//
// The constructor stays INERT. All hook installation is deferred to the main
// run loop (after launch), when every app/framework image is loaded and the
// runtime is fully up — the same late-loading model substrate uses and the
// load model proven by the YouTube/Spotify sets. Loading the dylib can
// therefore never crash the app, and a hook failure logs and degrades
// instead.
#import "IGModHook.h"

static void safeInit(const char *name, void (^block)(void)) {
    @try {
        block();
        os_log(igLog(), "IGMod: %s ready", name);
    } @catch (NSException *e) {
        os_log(igLog(), "IGMod: %s failed: %@", name, e);
    }
}

static void installAll(void) {
    os_log(igLog(), "IGMod installing hooks (post-launch)");
    // Defaults — every key is declared in IGModHook.h; the settings UI and
    // the hooks read the same spellings.
    [[NSUserDefaults standardUserDefaults] registerDefaults:@{
        kIGHideAds:             @YES,
        kIGHideStoryTray:       @NO,
        kIGNoSuggestedPosts:    @NO,
        kIGNoSuggestedReels:    @NO,
        kIGNoSuggestedAccounts: @NO,
        kIGNoStorySeen:         @NO,
        kIGNoTypingStatus:      @NO,
        kIGNoScreenshotAlerts:  @YES,
        kIGFeedDownload:        @YES,
        kIGStoryDownload:       @YES,
        kIGProfilePicDownload:  @YES,
        kIGCopyCaptions:        @YES,
        kIGDisableSafeMode:     @NO,
        kIGSettingsShortcut:    @YES,
        kIGSettingsFourFinger:  @YES,
    }];
    safeInit("adblock", ^{ IGAdBlockInit(); });
    safeInit("story-privacy", ^{ IGStoryPrivacyInit(); });
    safeInit("media-download", ^{ IGMediaDownloadInit(); });
    safeInit("copy-text", ^{ IGCopyTextInit(); });
    safeInit("safe-mode", ^{ IGSafeModeInit(); });
    safeInit("settings", ^{ IGSettingsInit(); });
    os_log(igLog(), "IGMod install complete");
}

__attribute__((constructor))
static void IGModInit(void) {
    os_log(igLog(), "IGMod loaded (inert)");
    dispatch_async(dispatch_get_main_queue(), ^{
        installAll();
    });
}
