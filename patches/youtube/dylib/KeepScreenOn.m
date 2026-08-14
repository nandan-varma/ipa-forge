// KeepScreenOn.m — keep the display awake while a video is playing
// (reference: DontEatMyContent / DEMC). Uses the shared player-VC tracking
// from PlayerGestures.m: while a YTPlayerViewController is active, disable
// the idle timer so the screen does not dim or auto-lock mid-video.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

static void updateIdleTimer(void) {
    BOOL playing = IS_ENABLED(KKeepScreenOn) && ytfCurrentPlayerViewController() != nil;
    [UIApplication sharedApplication].idleTimerDisabled = playing;
}

void YTFreedomKeepScreenOnInit(void) {
    static dispatch_source_t timer;
    timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0,
                                   dispatch_get_main_queue());
    dispatch_source_set_timer(timer, dispatch_walltime(NULL, 0),
                              (uint64_t)(2.0 * NSEC_PER_SEC), (uint64_t)(1.0 * NSEC_PER_SEC));
    dispatch_source_set_event_handler(timer, ^{ updateIdleTimer(); });
    dispatch_resume(timer);
}
